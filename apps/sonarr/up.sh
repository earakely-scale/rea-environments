#!/usr/bin/env bash
# Start rea-sonarr, wait until /ping answers, create the two root-folder directories and the two no-op connection scripts.
set -euo pipefail
cd "$(dirname "$0")"
docker compose -p rea-sonarr -f compose.yml up -d
for i in $(seq 1 90); do
  if curl -fsS -o /dev/null http://127.0.0.1:3221/ping; then
    docker compose -p rea-sonarr -f compose.yml exec -T sonarr sh -c 'mkdir -p /data/lighthouse-rota-archive /data/granite-ledger-films /data/scripts && for s in copperfield-annex night-shift-pager; do printf "#!/bin/sh\nexit 0\n" > /data/scripts/$s.sh; chmod 755 /data/scripts/$s.sh; done && chown -R abc:abc /data'
    echo "[up] sonarr ready after ~$((i*2)) s" >&2; exit 0
  fi
  sleep 2
done
echo "[up] sonarr did not become ready" >&2; exit 1
