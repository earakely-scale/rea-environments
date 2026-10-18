#!/usr/bin/env bash
# Tear down the showcase Mealie and its volume, then remove the capture secrets.
set -euo pipefail
cd "$(dirname "$0")"
docker compose -p rea-mealie -f compose.yml down -v
rm -f mealie.full.har .admin req.*.json
