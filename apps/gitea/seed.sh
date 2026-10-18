#!/usr/bin/env bash
# Seed the rea-gitea instance with synthetic content through /api/v1 (basic auth). Idempotent: every step looks
# before it creates. Credentials live only in ./.admin (mode 600); nothing secret is printed.
set -euo pipefail
cd "$(dirname "$0")"
BASE=${BASE_URL:-http://127.0.0.1:3102}
PROJECT=rea-gitea
ORG=lighthouse-rota
ADMIN_FILE=.admin

genpw() { python3 -c 'import secrets,string; a=string.ascii_letters+string.digits; print("".join(secrets.choice(a) for _ in range(24)))'; }
jget() { python3 -c 'import sys,json; d=json.load(sys.stdin); print(eval(sys.argv[1], {"d": d, "a": sys.argv[2:]}))' "$@"; }

if [ ! -f "$ADMIN_FILE" ]; then
  ( umask 077; { echo "ADMIN_USER=rea-admin"; echo "ADMIN_PASS=$(genpw)"; echo "ADA_PASS=$(genpw)"; echo "RUI_PASS=$(genpw)"; } > "$ADMIN_FILE" )
fi
chmod 600 "$ADMIN_FILE"
# shellcheck disable=SC1090
. "./$ADMIN_FILE"

for _ in $(seq 1 60); do curl -fsS "$BASE/api/healthz" >/dev/null 2>&1 && break; sleep 2; done

api() { # method path [json-body] [user] [pass]
  local m=$1 p=$2 d=${3:-} u=${4:-$ADMIN_USER} pw=${5:-$ADMIN_PASS}
  if [ -n "$d" ]; then curl -sS -u "$u:$pw" -H 'Content-Type: application/json' -X "$m" "$BASE/api/v1$p" --data "$d"
  else curl -sS -u "$u:$pw" -X "$m" "$BASE/api/v1$p"; fi
}
code() { curl -sS -o /dev/null -w '%{http_code}' -u "$ADMIN_USER:$ADMIN_PASS" "$BASE/api/v1$1"; }

# 1. admin (created through the gitea CLI inside the container; password taken from .admin)
if [ "$(code /user)" != 200 ]; then
  if ! docker compose -p "$PROJECT" exec -T -u git gitea gitea admin user create --admin --username "$ADMIN_USER" \
        --password "$ADMIN_PASS" --email rea-admin@example.test --must-change-password=false >/dev/null 2>&1; then
    docker compose -p "$PROJECT" exec -T -u git gitea gitea admin user change-password --username "$ADMIN_USER" \
        --password "$ADMIN_PASS" --must-change-password=false >/dev/null
  fi
fi
[ "$(code /user)" = 200 ] || { echo "admin auth failed" >&2; exit 1; }

# 2. users
ensure_user() { # username "Full Name" password
  if [ "$(code "/users/$1")" != 200 ]; then
    api POST /admin/users "$(python3 -c 'import sys,json; print(json.dumps({"username":sys.argv[1],"full_name":sys.argv[2],"email":sys.argv[1]+"@example.test","password":sys.argv[3],"must_change_password":False,"send_notify":False,"visibility":"public"}))' "$1" "$2" "$3")" >/dev/null
  else
    api PATCH "/admin/users/$1" "$(python3 -c 'import sys,json; print(json.dumps({"login_name":sys.argv[1],"source_id":0,"password":sys.argv[2],"must_change_password":False}))' "$1" "$3")" >/dev/null
  fi
}
ensure_user ada.finch "Ada Finch" "$ADA_PASS"
ensure_user rui.castellanos "Rui Castellanos" "$RUI_PASS"

# 3. org + team
if [ "$(code "/orgs/$ORG")" != 200 ]; then
  api POST /orgs '{"username":"lighthouse-rota","full_name":"Lighthouse Rota","description":"Volunteer keepers who share the lamp-room rota and the galley at Pelican Point.","location":"Pelican Point","visibility":"public","repo_admin_change_team_access":true}' >/dev/null
fi
TEAM_ID=$(api GET "/orgs/$ORG/teams" | jget 'next((t["id"] for t in d if t["name"]=="keepers"), "")')
if [ -z "$TEAM_ID" ]; then
  TEAM_ID=$(api POST "/orgs/$ORG/teams" '{"name":"keepers","description":"Keepers with write access to every rota repository.","permission":"write","includes_all_repositories":true,"can_create_org_repo":false,"units":["repo.code","repo.issues","repo.pulls","repo.releases","repo.wiki","repo.projects"]}' | jget 'd["id"]')
fi
api PUT "/teams/$TEAM_ID/members/ada.finch" >/dev/null
api PUT "/teams/$TEAM_ID/members/rui.castellanos" >/dev/null

# 4. repos
ensure_repo() { # name description
  if [ "$(code "/repos/$ORG/$1")" != 200 ]; then
    api POST "/orgs/$ORG/repos" "$(python3 -c 'import sys,json; print(json.dumps({"name":sys.argv[1],"description":sys.argv[2],"auto_init":True,"default_branch":"main","readme":"Default","private":False}))' "$1" "$2")" >/dev/null
  fi
  for _ in $(seq 1 30); do [ "$(api GET "/repos/$ORG/$1/branches" | jget 'len(d)')" != 0 ] 2>/dev/null && break; sleep 1; done
}
ensure_repo granite-ledger "Quarterly ledger and oil log for the Pelican Point lamp room."
ensure_repo blue-heron-kitchen "Galley recipes and chowder-night planning for the keepers."

ensure_file() { # repo path message content [branch]
  local repo=$1 path=$2 msg=$3 content=$4 branch=${5:-main}
  if [ "$(code "/repos/$ORG/$repo/contents/$path?ref=$branch")" != 200 ]; then
    api POST "/repos/$ORG/$repo/contents/$path" "$(python3 -c 'import sys,json,base64; print(json.dumps({"branch":sys.argv[1],"message":sys.argv[2],"content":base64.b64encode(sys.argv[3].encode()).decode(),"author":{"name":"Ada Finch","email":"ada.finch@example.test"},"committer":{"name":"Ada Finch","email":"ada.finch@example.test"}}))' "$branch" "$msg" "$content")" >/dev/null
  fi
}
ensure_file granite-ledger ledger/2026-q1.csv "Add the Q1 2026 ledger" $'date,item,amount\n2026-01-09,lamp oil (20 L),84.00\n2026-02-14,work party ferry tickets,12.40\n2026-03-14,brass hinge,9.75\n'
ensure_file granite-ledger docs/rota.md "Add the keepers rota" $'# Keepers rota\n\n| week | lamp room | galley |\n|---|---|---|\n| 1 | Ada Finch | Rui Castellanos |\n| 2 | Rui Castellanos | Ada Finch |\n'

# 5. labels + milestone (granite-ledger)
ensure_label() { # repo name color description -> id
  local id; id=$(api GET "/repos/$ORG/$1/labels" | jget 'next((l["id"] for l in d if l["name"]==a[0]), "")' "$2")
  if [ -z "$id" ]; then id=$(api POST "/repos/$ORG/$1/labels" "$(python3 -c 'import sys,json; print(json.dumps({"name":sys.argv[1],"color":sys.argv[2],"description":sys.argv[3]}))' "$2" "$3" "$4")" | jget 'd["id"]'); fi
  echo "$id"
}
L_HIGH=$(ensure_label granite-ledger high-tide d73a4a "Blocks the next lamp-room handover")
L_LOW=$(ensure_label granite-ledger low-tide 1d76db "Nice to have before Spring Tide")
MS_ID=$(api GET "/repos/$ORG/granite-ledger/milestones?state=all" | jget 'next((m["id"] for m in d if m["title"]=="Spring Tide"), "")')
if [ -z "$MS_ID" ]; then MS_ID=$(api POST "/repos/$ORG/granite-ledger/milestones" '{"title":"Spring Tide","description":"Everything the keepers need before the spring tide inspection.","due_on":"2026-11-30T00:00:00Z"}' | jget 'd["id"]'); fi

# 6. issues
ensure_issue() { # repo title body extra-json -> number
  local n; n=$(api GET "/repos/$ORG/$1/issues?state=all&type=issues&limit=50" | jget 'next((i["number"] for i in d if i["title"]==a[0]), "")' "$2")
  if [ -z "$n" ]; then
    n=$(api POST "/repos/$ORG/$1/issues" "$(python3 -c 'import sys,json; b={"title":sys.argv[1],"body":sys.argv[2]}; b.update(json.loads(sys.argv[3])); print(json.dumps(b))' "$2" "$3" "$4")" | jget 'd["number"]')
  fi
  echo "$n"
}
I1=$(ensure_issue granite-ledger "Lamp-room oil log is missing the March entries" "The ledger for March 2026 stops at the 14th. Ada has the paper log; it needs transcribing into ledger/2026-q1.csv." "{\"labels\":[$L_HIGH],\"milestone\":$MS_ID}")
I2=$(ensure_issue granite-ledger "Reconcile the galley float with the quarterly CSV" "The petty-cash float disagrees with ledger/2026-q1.csv by 12.40." "{\"labels\":[$L_LOW],\"assignees\":[\"ada.finch\"],\"milestone\":$MS_ID}")
I3=$(ensure_issue granite-ledger "Replace the brass hinge on the ledger cabinet" "Hinge replaced during the February work party; closing." "{}")
api PATCH "/repos/$ORG/granite-ledger/issues/$I3" '{"state":"closed"}' >/dev/null
I4=$(ensure_issue blue-heron-kitchen "Chowder night needs a vegetarian option" "Rui suggests a smoked-paprika white bean stew for the next chowder night." "{}")

# 7. comments (one by the admin, one by rui.castellanos)
ensure_comment() { # repo number body [user pass]
  local present; present=$(api GET "/repos/$ORG/$1/issues/$2/comments" | jget 'any(c["body"]==a[0] for c in d)' "$3")
  if [ "$present" != True ]; then
    api POST "/repos/$ORG/$1/issues/$2/comments" "$(python3 -c 'import sys,json; print(json.dumps({"body":sys.argv[1]}))' "$3")" "${4:-$ADMIN_USER}" "${5:-$ADMIN_PASS}" >/dev/null
  fi
}
ensure_comment granite-ledger "$I1" "Found the paper log in the lamp-room drawer; transcribing it this weekend."
ensure_comment granite-ledger "$I2" "The 12.40 is the ferry tickets for the February work party; the receipt is clipped to the paper float." rui.castellanos "$RUI_PASS"

# 8. branch + PR on granite-ledger
BR=spring-tide-shifts
if [ "$(code "/repos/$ORG/granite-ledger/branches/$BR")" != 200 ]; then
  api POST "/repos/$ORG/granite-ledger/branches" "{\"new_branch_name\":\"$BR\",\"old_branch_name\":\"main\"}" >/dev/null
fi
ensure_file granite-ledger docs/spring-tide-shifts.md "Add the spring tide shift roster" $'# Spring tide shifts\n\n| night | keeper |\n|---|---|\n| Mon | Ada Finch |\n| Tue | Rui Castellanos |\n| Wed | Ada Finch |\n' "$BR"
PR_N=$(api GET "/repos/$ORG/granite-ledger/pulls?state=all" | jget 'next((p["number"] for p in d if p["title"]=="Add the spring tide shift roster"), "")')
if [ -z "$PR_N" ]; then
  PR_N=$(api POST "/repos/$ORG/granite-ledger/pulls" "{\"head\":\"$BR\",\"base\":\"main\",\"title\":\"Add the spring tide shift roster\",\"body\":\"Pairs each night of the spring tide week with a keeper. Refs #$I1.\"}" | jget 'd["number"]')
fi

# 9. API token for the capture script (scoped; stored only in .admin)
if ! grep -q '^API_TOKEN=' "$ADMIN_FILE"; then
  api DELETE /users/rea-admin/tokens/rea-capture >/dev/null 2>&1 || true
  TOK=$(api POST /users/rea-admin/tokens '{"name":"rea-capture","scopes":["read:user","read:organization","read:repository","write:issue","read:admin","read:misc","read:notification"]}' | jget 'd["sha1"]')
  echo "API_TOKEN=$TOK" >> "$ADMIN_FILE"
fi

# 10. ids for capture.mjs (no secrets)
python3 - "$TEAM_ID" "$L_HIGH" "$L_LOW" "$MS_ID" "$I1" "$I2" "$I3" "$I4" "$PR_N" <<'PY' > seed.json
import sys, json
t, lh, ll, ms, i1, i2, i3, i4, pr = sys.argv[1:]
json.dump({"org": "lighthouse-rota", "team_id": int(t), "users": ["ada.finch", "rui.castellanos"],
           "repos": {"granite-ledger": {"files": ["README.md", "ledger/2026-q1.csv", "docs/rota.md"], "issues": [int(i1), int(i2), int(i3)],
                                        "closed_issue": int(i3), "pr": int(pr), "branch": "spring-tide-shifts",
                                        "labels": {"high-tide": int(lh), "low-tide": int(ll)}, "milestone": {"Spring Tide": int(ms)}},
                     "blue-heron-kitchen": {"files": ["README.md"], "issues": [int(i4)]}}}, sys.stdout, indent=1)
PY
echo "seeded: team=$TEAM_ID labels=$L_HIGH,$L_LOW milestone=$MS_ID issues=$I1,$I2,$I3 (closed $I3) bhk-issue=$I4 pr=$PR_N"
