#!/usr/bin/env bash
# Steady synthetic traffic against the edge.
# Usage: scripts/load.sh <requests-per-second> <seconds> [order-every-N-requests]
set -euo pipefail

BASE="${BASE:-http://127.0.0.1:${EDGE_PORT:-8080}}"
RPS="${1:-5}"
SECS="${2:-60}"
ORDER_EVERY="${3:-20}"

req() {
  local i=$1
  if [ $((i % ORDER_EVERY)) -eq 0 ]; then
    curl -s -o /dev/null -X POST "$BASE/api/orders" \
      -H 'Content-Type: application/json' -d '{"product_id":1,"quantity":1}'
    return
  fi
  case $((i % 4)) in
    0) curl -s -o /dev/null "$BASE/api/products" ;;
    1) curl -s -o /dev/null "$BASE/api/products/$(( (i % 12) + 1 ))" ;;
    2) curl -s -o /dev/null "$BASE/api/search?q=a" ;;
    3) curl -s -o /dev/null "$BASE/" ;;
  esac
}

end=$((SECONDS + SECS))
n=0
while [ "$SECONDS" -lt "$end" ]; do
  for _ in $(seq 1 "$RPS"); do
    n=$((n + 1))
    req "$n" &
  done
  sleep 1
done
wait
echo "sent $n requests in ${SECS}s (~${RPS}/s)"
