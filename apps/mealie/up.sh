#!/usr/bin/env bash
# Generate the admin password and the crew account's password (once) into .admin (mode 600) and start Mealie. Never prints the value.
set -euo pipefail
cd "$(dirname "$0")"
if [ ! -f .admin ]; then
  umask 077
  python3 -c 'import secrets; print("MEALIE_ADMIN_PASSWORD=" + secrets.token_urlsafe(21)); print("MEALIE_CREW_PASSWORD=" + secrets.token_urlsafe(21))' > .admin
  chmod 600 .admin
fi
docker compose -p rea-mealie -f compose.yml up -d
for i in $(seq 1 120); do
  st=$(docker inspect --format '{{.State.Health.Status}}' rea-mealie-mealie-1 2>/dev/null || true)
  [ "$st" = healthy ] && { echo "mealie healthy after $((i*2))s"; exit 0; }
  sleep 2
done
echo "mealie not healthy"; exit 1
