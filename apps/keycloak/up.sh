#!/usr/bin/env bash
# Generate the throwaway bootstrap credential (once) into .admin (mode 600) and start Keycloak. Never prints the values.
set -euo pipefail
cd "$(dirname "$0")"
if [ ! -f .admin ]; then
  umask 077
  python3 -c 'import secrets; print("KC_BOOTSTRAP_PASSWORD=" + secrets.token_urlsafe(21)); print("KC_ADMIN_PASSWORD=" + secrets.token_urlsafe(21))' > .admin
  chmod 600 .admin
fi
set -a; . ./.admin; set +a
docker compose -p rea-keycloak -f compose.yml up -d
for i in $(seq 1 90); do
  st=$(docker inspect --format '{{.State.Health.Status}}' rea-keycloak-keycloak-1 2>/dev/null || true)
  [ "$st" = healthy ] && { echo "keycloak healthy after $((i*2))s"; exit 0; }
  sleep 2
done
echo "keycloak not healthy"; exit 1
