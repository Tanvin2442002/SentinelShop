#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

if [ -f .env ]; then set -a; . ./.env; set +a; fi
BASE="http://127.0.0.1:${EDGE_PORT:-8080}"

fail() { echo "FAIL: $*" >&2; exit 1; }
pass() { echo "ok:   $*"; }

reachable=0
for _ in $(seq 1 30); do
  if curl -fs "$BASE/edge-healthz" >/dev/null 2>&1; then reachable=1; break; fi
  sleep 2
done
[ "$reachable" = 1 ] || fail "edge not reachable at $BASE"
pass "edge reachable at $BASE"

code=$(curl -s -o /dev/null -w '%{http_code}' "$BASE/")
[ "$code" = 200 ] || fail "web page returned $code, expected 200"
pass "web page served"

products=$(curl -fs "$BASE/api/products") || fail "GET /api/products failed"
count=$(printf '%s' "$products" | grep -o '"id"' | wc -l || true)
[ "$count" -eq 12 ] || fail "expected 12 products, got $count"
pass "12 products listed"

out=$(curl -fsG --data-urlencode "q=' OR 1=1 --" "$BASE/api/search")
[ "$out" = "[]" ] || fail "injection string returned data: $out"
pass "SQL injection string treated as plain text"

out=$(curl -fsG --data-urlencode "q=%" "$BASE/api/search")
[ "$out" = "[]" ] || fail "literal % matched products: $out"
pass "wildcard characters are escaped"

code=$(curl -s -o /dev/null -w '%{http_code}' -X POST "$BASE/api/login" \
  -H 'Content-Type: application/json' \
  -d '{"username":"alice","password":"definitely-wrong"}')
[ "$code" = 401 ] || fail "wrong password returned $code, expected 401"
pass "wrong password rejected with 401"

code=$(curl -s -o /dev/null -w '%{http_code}' "$BASE/api/metrics")
[ "$code" = 404 ] || fail "/api/metrics reachable through the edge ($code)"
pass "metrics endpoint is not exposed"

curl -sI "$BASE/" | grep -qi '^content-security-policy' || fail "CSP header missing"
pass "security headers present"

curl -sI "$BASE/api/products" | grep -qi '^x-trace-id' || fail "X-Trace-Id header missing"
pass "trace id header present"

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
pass "order $id placed and processed by the worker"

echo "smoke test passed"