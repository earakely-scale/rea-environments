#!/usr/bin/env bash
# Tear down the showcase Keycloak and its volume, then remove the capture secrets. The placeholder only satisfies the
# compose file's required-variable check; nothing is started.
set -euo pipefail
cd "$(dirname "$0")"
KC_BOOTSTRAP_PASSWORD=unused docker compose -p rea-keycloak -f compose.yml down -v
rm -f keycloak.full.har .admin req.*.json
