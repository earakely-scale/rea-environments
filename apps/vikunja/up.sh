#!/usr/bin/env bash
# Generate the service secret, the admin password and the crew accounts' password (once) into .admin (mode 600) and start Vikunja. Never prints the values.
set -euo pipefail
cd "$(dirname "$0")"
if [ ! -f .admin ]; then
  umask 077
  python3 -c 'import secrets; print("VIKUNJA_SERVICE_SECRET=" + secrets.token_urlsafe(32)); print("VIKUNJA_ADMIN_PASSWORD=" + secrets.token_urlsafe(21)); print("VIKUNJA_CREW_PASSWORD=" + secrets.token_urlsafe(21))' > .admin
  chmod 600 .admin
fi
VIKUNJA_SERVICE_SECRET=$(sed -n 's/^VIKUNJA_SERVICE_SECRET=//p' .admin) docker compose -p rea-vikunja -f compose.yml up -d
for i in $(seq 1 90); do
  st=$(docker inspect --format '{{.State.Health.Status}}' rea-vikunja-vikunja-1 2>/dev/null || true)
  [ "$st" = healthy ] && { echo "vikunja healthy after $((i*2))s"; exit 0; }
  sleep 2
done
echo "vikunja not healthy"; exit 1
