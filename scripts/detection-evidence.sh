#!/usr/bin/env bash
set -uo pipefail
set -a; . ./.env; set +a

OUT="${1:-evidence/detection}"
D="docker compose -f docker-compose.yml -f docker-compose.detection.yml"
mkdir -p "$OUT/cases"

alerts() { $D exec -T wazuh-manager sh -c 'grep -c shop_attack /var/ossec/logs/alerts/alerts.json'; }
probe()  { $D exec -T attacker wget -qO- "http://127.0.0.1:9000/probe?path=/api/products"; }
host()   { curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:${EDGE_PORT}/api/products"; }

BLOCK_TTL_SECONDS=30 $D up -d --no-deps responder > /dev/null 2>&1
sleep 5

{
for a in bruteforce sqli xss traversal scan404; do
  before=$(alerts)
  result=$($D exec -T attacker python attack.py --"$a" | tail -n 1)
  sleep 6
  blocked=$(probe)
  ok=$(host)
  sleep 8
  after=$(alerts)
  echo "$a | $result | alerts +$((after - before)) | attacker $blocked | normal client $ok"
  sleep 30
done
} | tee "$OUT/attacks-summary.txt"

$D exec -T responder cat /data/audit.jsonl > "$OUT/audit.jsonl"
$D exec -T responder ls /data/cases < /dev/null | while read -r f; do
  $D exec -T responder cat "/data/cases/$f" < /dev/null > "$OUT/cases/$f"
done
$D exec -T wazuh-manager sh -c 'grep shop_attack /var/ossec/logs/alerts/alerts.json' > "$OUT/wazuh-alerts.jsonl"
grep -m1 '"expired"' "$OUT/audit.jsonl" > "$OUT/expiry-line.json"
echo "saved in $OUT"
