#!/usr/bin/env bash
# Step 1: generate the throwaway admin secret (600 file), start Grafana on 127.0.0.1:3101, wait for /api/health.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
BASE="${BASE_URL:-http://127.0.0.1:3101}"
if [ ! -f "$HERE/.admin" ]; then
  umask 077
  gen() { head -c 48 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | head -c 24; }
  printf 'ADMIN_PASSWORD=%s\nADA_PASSWORD=%s\n' "$(gen)" "$(gen)" > "$HERE/.admin"
  chmod 600 "$HERE/.admin"
fi
# shellcheck disable=SC1091
source "$HERE/.admin"
export GF_ADMIN_PASSWORD="$ADMIN_PASSWORD"
docker compose -p rea-grafana -f "$HERE/compose.yml" up -d
for i in $(seq 1 60); do
  if out=$(curl -fsS "$BASE/api/health" 2>/dev/null); then echo "health: $out"; exit 0; fi
  sleep 2
done
echo "grafana did not become healthy" >&2; exit 1
