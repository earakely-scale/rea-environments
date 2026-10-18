#!/usr/bin/env bash
# Step 2: seed synthetic Grafana content through the HTTP API with basic auth. Idempotent (check-then-create).
# Secrets come from ./.admin (ADMIN_PASSWORD, ADA_PASSWORD) and are passed to curl via a config fd, never argv.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
BASE="${BASE_URL:-http://127.0.0.1:3101}"
# shellcheck disable=SC1091
set -a; source "$HERE/.admin"; set +a
gapi() { # gapi METHOD PATH [JSON]
  local m="$1" p="$2" body="${3:-}"
  if [ -n "$body" ]; then
    curl -sS -K <(printf 'user = "rea-admin:%s"\n' "$ADMIN_PASSWORD") -X "$m" -H 'Content-Type: application/json' -H 'Accept: application/json' --data "$body" "$BASE$p"
  else
    curl -sS -K <(printf 'user = "rea-admin:%s"\n' "$ADMIN_PASSWORD") -X "$m" -H 'Accept: application/json' "$BASE$p"
  fi
}
gcode() { curl -sS -o /dev/null -w '%{http_code}' -K <(printf 'user = "rea-admin:%s"\n' "$ADMIN_PASSWORD") "$BASE$1"; }
jget() { python3 -c 'import sys,json; d=json.load(sys.stdin); print(eval(sys.argv[1], {"d": d, "sys": sys}))' "$@"; }

for i in $(seq 1 60); do curl -fsS "$BASE/api/health" >/dev/null 2>&1 && break; sleep 2; done
VERSION=$(curl -fsS "$BASE/api/health" | jget 'd["version"]')
echo "grafana version: $VERSION"

# 1 folder
if [ "$(gcode /api/folders/lighthouse-rota)" = "404" ]; then
  gapi POST /api/folders '{"uid":"lighthouse-rota","title":"Lighthouse Rota"}' >/dev/null; echo "created folder lighthouse-rota"
else echo "folder lighthouse-rota exists"; fi

# 1 testdata datasource
if [ "$(gcode /api/datasources/uid/rea-testdata)" = "404" ]; then
  gapi POST /api/datasources '{"uid":"rea-testdata","name":"Rea Testdata","type":"grafana-testdata-datasource","access":"proxy","isDefault":true}' >/dev/null; echo "created datasource rea-testdata"
else echo "datasource rea-testdata exists"; fi

# 2 dashboards
if [ "$(gcode /api/dashboards/uid/granite-ledger)" = "404" ]; then
  gapi POST /api/dashboards/db '{"folderUid":"lighthouse-rota","overwrite":false,"message":"seed","dashboard":{"uid":"granite-ledger","title":"Granite Ledger Overview","tags":["ledger","finance"],"timezone":"utc","schemaVersion":39,"panels":[{"id":1,"type":"text","title":"Ledger Notes","gridPos":{"x":0,"y":0,"w":12,"h":6},"options":{"mode":"markdown","content":"Granite Ledger reconciles 14 quarry accounts every Monday."}},{"id":2,"type":"text","title":"Shift Handover","gridPos":{"x":12,"y":0,"w":12,"h":6},"options":{"mode":"markdown","content":"Night Shift signs off the ledger at 06:00 UTC."}}]}}' >/dev/null; echo "created dashboard granite-ledger"
else echo "dashboard granite-ledger exists"; fi
if [ "$(gcode /api/dashboards/uid/blue-heron-kitchen)" = "404" ]; then
  gapi POST /api/dashboards/db '{"folderUid":"lighthouse-rota","overwrite":false,"message":"seed","dashboard":{"uid":"blue-heron-kitchen","title":"Blue Heron Kitchen Ops","tags":["kitchen","ops"],"timezone":"utc","schemaVersion":39,"panels":[{"id":1,"type":"timeseries","title":"Oven Temperature","gridPos":{"x":0,"y":0,"w":24,"h":8},"datasource":{"type":"grafana-testdata-datasource","uid":"rea-testdata"},"targets":[{"refId":"A","scenarioId":"random_walk","seriesCount":1,"alias":"oven-c"}]}]}}' >/dev/null; echo "created dashboard blue-heron-kitchen"
else echo "dashboard blue-heron-kitchen exists"; fi

# 1 team
TEAM_ID=$(gapi GET '/api/teams/search?name=Night%20Shift' | jget '(d["teams"][0]["id"] if d["teams"] else "")')
if [ -z "$TEAM_ID" ]; then
  TEAM_ID=$(gapi POST /api/teams '{"name":"Night Shift","email":"night-shift@example.test"}' | jget 'd["teamId"]'); echo "created team Night Shift id=$TEAM_ID"
else echo "team Night Shift exists id=$TEAM_ID"; fi

# 1 extra user (viewer) in the team
if [ "$(gcode '/api/users/lookup?loginOrEmail=ada.finch')" = "404" ]; then
  USER_ID=$(gapi POST /api/admin/users "$(python3 -c 'import json,os; print(json.dumps({"name":"Ada Finch","email":"ada.finch@example.test","login":"ada.finch","password":os.environ["ADA_PASSWORD"]}))')" | jget 'd["id"]'); echo "created user ada.finch id=$USER_ID"
else USER_ID=$(gapi GET '/api/users/lookup?loginOrEmail=ada.finch' | jget 'd["id"]'); echo "user ada.finch exists id=$USER_ID"; fi
gapi PATCH "/api/org/users/$USER_ID" '{"role":"Viewer"}' >/dev/null
if ! gapi GET "/api/teams/$TEAM_ID/members" | jget 'any(m["userId"]==int(sys.argv[2]) for m in d)' "$USER_ID" | grep -q True; then
  gapi POST "/api/teams/$TEAM_ID/members" "{\"userId\":$USER_ID}" >/dev/null; echo "added ada.finch to Night Shift"
else echo "ada.finch already in Night Shift"; fi

# 2 annotations on the first dashboard (fixed timestamps: 2026-10-01T06:00Z and 2026-10-02T09:30Z)
N_ANN=$(gapi GET '/api/annotations?dashboardUID=granite-ledger&tags=seed&limit=10' | jget 'len(d)')
if [ "$N_ANN" -lt 2 ]; then
  gapi POST /api/annotations '{"dashboardUID":"granite-ledger","panelId":1,"time":1790834400000,"timeEnd":1790835000000,"tags":["seed","handover"],"text":"Night Shift handover: ledger balanced at 06:00"}' >/dev/null
  gapi POST /api/annotations '{"dashboardUID":"granite-ledger","panelId":2,"time":1790933400000,"tags":["seed","audit"],"text":"Quarterly audit of the Granite Ledger started"}' >/dev/null
  echo "created 2 annotations"
else echo "annotations exist ($N_ANN)"; fi

# 1 playlist
N_PL=$(gapi GET '/api/playlists?query=Lighthouse' | jget 'len(d)')
if [ "$N_PL" -lt 1 ]; then
  gapi POST /api/playlists '{"name":"Lighthouse Rotation","interval":"5m","items":[{"type":"dashboard_by_uid","value":"granite-ledger"},{"type":"dashboard_by_uid","value":"blue-heron-kitchen"}]}' >/dev/null; echo "created playlist Lighthouse Rotation"
else echo "playlist exists"; fi

python3 - "$VERSION" "$TEAM_ID" "$USER_ID" > "$HERE/seed-ids.json" <<'PY'
import json, sys
print(json.dumps({"grafana_version": sys.argv[1], "folder_uid": "lighthouse-rota", "datasource_uid": "rea-testdata",
  "dashboard_uids": ["granite-ledger", "blue-heron-kitchen"], "team_id": int(sys.argv[2]), "team_name": "Night Shift",
  "user_id": int(sys.argv[3]), "user_login": "ada.finch", "playlist_name": "Lighthouse Rotation", "annotation_tags": ["seed"]}, indent=2))
PY
echo "seed done"; cat "$HERE/seed-ids.json"
