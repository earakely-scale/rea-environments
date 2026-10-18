#!/usr/bin/env bash
# Step 7: tear down this app's compose project and volumes only; remove the unscoped HAR and the admin secret.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
export GF_ADMIN_PASSWORD="${GF_ADMIN_PASSWORD:-unused-at-teardown}"
docker compose -p rea-grafana -f "$HERE/compose.yml" down -v
rm -f "$HERE/grafana.full.har" "$HERE/.admin"
rm -rf "$HERE/profile"
