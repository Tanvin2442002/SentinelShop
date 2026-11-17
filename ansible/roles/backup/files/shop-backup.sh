#!/bin/bash
set -euo pipefail
umask 077
out="${BACKUP_DIR}/shop-$(date +%F-%H%M%S).sql.gz"
pg_dump | gzip > "${out}.tmp"
mv "${out}.tmp" "$out"
find "$BACKUP_DIR" -name 'shop-*.sql.gz' -mtime +7 -delete
