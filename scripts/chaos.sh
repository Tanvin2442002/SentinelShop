#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

if grep -qE '=(true|[1-9]|0\.[0-9])' chaos/active.env; then
  echo "chaos is already active: run make chaos-revert first" >&2
  exit 1
fi

flags=(CHAOS_LATENCY_MS CHAOS_ERROR_RATE CHAOS_SLOW_DB CHAOS_MEMORY_LEAK)
values=(1500 0.4 true true)
i=$((RANDOM % 4))

sed -i "s/^${flags[$i]}=.*/${flags[$i]}=${values[$i]}/" chaos/active.env
git add chaos/active.env
git commit -q -m "chore: update runtime config" >/dev/null 2>&1
