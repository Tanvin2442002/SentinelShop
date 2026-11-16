#!/bin/sh
FILE=/etc/nginx/blocklist/blocklist.conf
(
  last=""
  while true; do
    now=$(md5sum "$FILE" 2>/dev/null | cut -d' ' -f1)
    if [ -n "$last" ] && [ "$now" != "$last" ]; then
      nginx -t -q && nginx -s reload
    fi
    last="$now"
    sleep 1
  done
) &
