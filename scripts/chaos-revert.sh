#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

c=$(git log -1 --format=%H --grep='^chore: update runtime config$')
[ -n "$c" ] || { echo "no chaos commit found" >&2; exit 1; }

git checkout "$c~1" -- chaos/active.env
git diff --cached --quiet || git commit -q -m "chore: restore runtime config"
