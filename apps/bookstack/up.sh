#!/usr/bin/env bash
# Generate the throwaway secrets into .admin (mode 600) on first run, then start rea-bookstack and wait until /login answers.
set -euo pipefail
cd "$(dirname "$0")"
umask 077
if [ ! -f .admin ]; then
  python3 - <<'PY'
import base64, os, secrets
fd = os.open(".admin", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
with os.fdopen(fd, "w") as f:
    f.write(f"BOOKSTACK_DB_PASSWORD={secrets.token_urlsafe(24)}\n")
    f.write(f"BOOKSTACK_DB_ROOT_PASSWORD={secrets.token_urlsafe(24)}\n")
    f.write("BOOKSTACK_APP_KEY=base64:" + base64.b64encode(os.urandom(32)).decode() + "\n")
PY
  echo "[up] wrote .admin (mode 600)" >&2
fi
docker compose -p rea-bookstack --env-file .admin -f compose.yml up -d
for i in $(seq 1 90); do
  if curl -fsS -o /dev/null http://127.0.0.1:3219/login; then echo "[up] bookstack ready after ~$((i*2)) s" >&2; exit 0; fi
  sleep 2
done
echo "[up] bookstack did not become ready" >&2; exit 1
