#!/usr/bin/env bash
# Generate the throwaway session secret into .admin (mode 600) on first run, then start rea-grist and wait until /status answers.
set -euo pipefail
cd "$(dirname "$0")"
umask 077
if [ ! -f .admin ]; then
  python3 -c 'import os,secrets; fd=os.open(".admin", os.O_WRONLY|os.O_CREAT|os.O_TRUNC, 0o600); os.write(fd, f"GRIST_SESSION_SECRET={secrets.token_urlsafe(32)}\n".encode())'
  echo "[up] wrote .admin (mode 600)" >&2
fi
docker compose -p rea-grist --env-file .admin -f compose.yml up -d
for i in $(seq 1 90); do
  if curl -fsS -o /dev/null http://127.0.0.1:3220/status; then echo "[up] grist ready after ~$((i*2)) s" >&2; exit 0; fi
  sleep 2
done
echo "[up] grist did not become ready" >&2; exit 1
