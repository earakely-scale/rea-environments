#!/usr/bin/env bash
# Airbyte 2.4.0 (helm chart V2 2.4.0) through abctl v0.30.4 in a kind cluster, ingress on port 3302. Telemetry off.
set -euo pipefail
export DO_NOT_TRACK=1
~/.local/bin/abctl local install --chart-version 2.4.0 --port 3302 --insecure-cookies --no-browser --values "$HOME/capture/airbyte/values.yaml"
