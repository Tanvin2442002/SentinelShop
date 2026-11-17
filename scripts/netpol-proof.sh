#!/usr/bin/env bash
set -uo pipefail

NS=shop
IMG="${IMG:-k3d-shop-registry:5000/postgres:16.16-alpine}"
rc=0
kubectl -n "$NS" wait --for=condition=Ready pod -l app=postgres --timeout=60s >/dev/null || exit 1
kubectl -n "$NS" wait --for=condition=Ready pod -l app=redis --timeout=60s >/dev/null || exit 1

probe() {
  kubectl -n "$NS" run "$1" --rm -i --restart=Never --quiet --image="$IMG" --labels="app=$2" \
    --command -- sh -c "sleep 2; nc -w 3 $3 $4 </dev/null && echo OPEN || echo BLOCKED" 2>/dev/null | tail -1
}

check() {
  local label=$1 host=$2 port=$3 want=$4 got
  got=$(probe "np-$label-$host" "$label" "$host" "$port")
  if [ "$got" = "$want" ]; then
    echo "ok:   $label -> $host:$port $got"
  else
    echo "FAIL: $label -> $host:$port got '$got', expected $want"
    rc=1
  fi
}

check order-worker postgres 5432 OPEN
check order-worker redis 6379 OPEN
check seed postgres 5432 OPEN
check seed redis 6379 BLOCKED
check intruder postgres 5432 BLOCKED
check intruder redis 6379 BLOCKED

echo
echo "app still works through the ingress:"
bash "$(dirname "$0")/k3d-smoke.sh" || rc=1
exit $rc
