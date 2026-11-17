#!/usr/bin/env bash
set -euo pipefail

BASE="${BASE:-http://127.0.0.1:8088}"

fail() { echo "FAIL: $*" >&2; exit 1; }
pass() { echo "ok:   $*"; }

reachable=0
for _ in $(seq 1 30); do
  if curl -fs "$BASE/api/readyz" >/dev/null 2>&1; then reachable=1; break; fi
  sleep 2
done
[ "$reachable" = 1 ] || fail "ingress not ready at $BASE"
pass "ingress reachable at $BASE and catalog-api ready"

code=$(curl -s -o /dev/null -w '%{http_code}' "$BASE/")
[ "$code" = 200 ] || fail "web page returned $code, expected 200"
pass "web page served"

count=$(curl -fs "$BASE/api/products" | grep -o '"id"' | wc -l)
[ "$count" -eq 12 ] || fail "expected 12 products, got $count"
pass "12 products listed"

code=$(curl -s -o /dev/null -w '%{http_code}' -X POST "$BASE/api/login" \
  -H 'Content-Type: application/json' \
  -d '{"username":"alice","password":"definitely-wrong"}')
[ "$code" = 401 ] || fail "wrong password returned $code, expected 401"
pass "wrong password rejected with 401"

code=$(curl -s -o /dev/null -w '%{http_code}' "$BASE/api/metrics")
[ "$code" = 404 ] || fail "/api/metrics reachable through the ingress ($code)"
pass "metrics endpoint is not exposed"

resp=$(curl -fs -X POST "$BASE/api/orders" \
  -H 'Content-Type: application/json' -d '{"product_id":1,"quantity":1}')
id=$(printf '%s' "$resp" | sed -n 's/.*"id":\([0-9]*\).*/\1/p')
[ -n "$id" ] || fail "order not created: $resp"
status=""
for _ in $(seq 1 20); do
  status=$(curl -fs "$BASE/api/orders/$id" | sed -n 's/.*"status":"\([A-Z]*\)".*/\1/p')
  [ "$status" = COMPLETED ] && break
  sleep 1
done
[ "$status" = COMPLETED ] || fail "order $id ended as '$status', expected COMPLETED"
pass "order $id placed through the ingress and processed by the worker"

echo "k3d smoke test passed"
