#!/usr/bin/env bash
# Tear down the showcase Vikunja and its volume, then remove the capture secrets. The placeholder only satisfies the
# compose file's required-variable check; nothing is started.
set -euo pipefail
cd "$(dirname "$0")"
VIKUNJA_SERVICE_SECRET=unused docker compose -p rea-vikunja -f compose.yml down -v
rm -f vikunja.full.har .admin req.*.json
