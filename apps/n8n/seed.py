#!/usr/bin/env python3
"""Seed the showcase n8n with synthetic workflows through the REST API its own editor uses (/rest/*, idempotent).

`python3 seed.py init` writes ~/capture/n8n/.admin (mode 600): the owner password and the instance encryption key, both
generated at run time; compose reads the key with --env-file. `python3 seed.py` then creates the owner through
`POST /rest/owner/setup` (Rea Admin, rea-admin@example.test), signs in with a cookie session, creates 5 tags and 4
workflows built only from core nodes (manual or schedule trigger, Edit Fields, If, No Operation, a sticky note; no
credentials), runs two of them manually so executions exist and creates 2 data tables with rows; writes seed-ids.json
(ids only).
Never prints a password or the key."""
import http.cookiejar, json, os, secrets, sys, time, urllib.error, urllib.parse, urllib.request

BASE = os.environ.get("BASE_URL", "http://127.0.0.1:3218")
DIR = os.environ.get("CAPTURE_DIR", os.path.expanduser("~/capture/n8n"))
ADMIN_FILE = os.path.join(DIR, ".admin")
EMAIL = "rea-admin@example.test"

def log(msg): print(f"[seed] {msg}", file=sys.stderr)

def init():
    if os.path.exists(ADMIN_FILE): log(".admin exists; keeping it"); return
    fd = os.open(ADMIN_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:   # n8n wants 8-64 characters with a digit and an upper-case letter
        f.write(f"N8N_OWNER_PASSWORD={secrets.token_urlsafe(18)}Aa1\nN8N_ENCRYPTION_KEY={secrets.token_urlsafe(32)}\n")
    log(f"wrote {ADMIN_FILE} (mode 600)")

if len(sys.argv) > 1 and sys.argv[1] == "init":
    init(); sys.exit(0)

PW = dict(l.split("=", 1) for l in open(ADMIN_FILE).read().splitlines() if "=" in l)["N8N_OWNER_PASSWORD"]
jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))

def api(method, path, body=None, quiet=False):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + "/rest/" + path, data=data, method=method)
    req.add_header("Accept", "application/json")
    if data is not None: req.add_header("Content-Type", "application/json")
    try:
        with opener.open(req, timeout=60) as r:
            raw = r.read(); return (json.loads(raw) if raw else {}), r.status
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:300]
        if quiet: return {"error": detail}, e.code
        raise SystemExit(f"[seed] {method} /rest/{path} -> {e.code}: {detail}")

# /healthz/readiness answers ok while migrations still run and before /rest is mounted; wait for /rest/settings instead.
for _ in range(120):
    try:
        with urllib.request.urlopen(BASE + "/rest/settings", timeout=5) as r:
            if r.status == 200: break
    except Exception: pass
    time.sleep(2)
else:
    raise SystemExit("[seed] n8n did not become ready")
settings, _ = api("GET", "settings")
log(f"n8n ready at {BASE}")

if settings["data"]["userManagement"].get("showSetupOnFirstLoad"):
    api("POST", "owner/setup", {"email": EMAIL, "firstName": "Rea", "lastName": "Admin", "password": PW}); log("owner created through /rest/owner/setup")
# A JWT issued in the same second as one revoked by a previous run's logout is identical and stays revoked; wait a second.
time.sleep(1.1)
api("POST", "login", {"emailOrLdapLoginId": EMAIL, "password": PW})
log(f"seed session created (n8n {api('GET', 'settings')[0]['data'].get('versionCli')})")

ids = {"tags": {}, "workflows": {}, "executions": {}, "projects": {}, "users": {}}
me, _ = api("GET", "login"); ids["users"]["rea-admin"] = me["data"]["id"]
proj, _ = api("GET", "projects/personal"); ids["projects"]["personal"] = proj["data"]["id"]

tags = {t["name"]: t["id"] for t in api("GET", "tags")[0]["data"]}
for name in ("Granite Ledger", "Blue Heron Kitchen", "Lighthouse Rota", "Saltmarsh Depot", "Quarterly Audit"):
    if name not in tags: tags[name] = api("POST", "tags", {"name": name})[0]["data"]["id"]; log(f"tag '{name}' created")
    ids["tags"][name] = tags[name]

def setnode(name, pos, fields):
    return {"parameters": {"assignments": {"assignments": [
                {"id": f"a{i}", "name": k, "value": v, "type": "number" if isinstance(v, (int, float)) else "string"}
                for i, (k, v) in enumerate(fields)]}, "options": {}},
            "name": name, "type": "n8n-nodes-base.set", "typeVersion": 3.4, "position": pos}

def manual(name): return {"parameters": {}, "name": name, "type": "n8n-nodes-base.manualTrigger", "typeVersion": 1, "position": [0, 0]}
def noop(name, pos): return {"parameters": {}, "name": name, "type": "n8n-nodes-base.noOp", "typeVersion": 1, "position": pos}
def chain(*names): return {a: {"main": [[{"node": b, "type": "main", "index": 0}]]} for a, b in zip(names, names[1:])}

WORKFLOWS = [
    {"name": "Granite Ledger stone count digest", "description": "Totals the quarterly block count for the Granite Ledger and names the auditor.", "tags": ["Granite Ledger", "Quarterly Audit"],
     "nodes": [manual("Start stone count"),
               setnode("Count north quarry blocks", [220, 0], [("quarry", "north quarry"), ("blocks", 412), ("auditor", "Rui Castellanos"), ("reference", "GL-2291")]),
               noop("Ledger closed for the quarter", [440, 0]),
               {"parameters": {"content": "Quarterly stone count for the Granite Ledger; audited by Rui Castellanos.", "height": 160, "width": 300},
                "name": "Sticky Note", "type": "n8n-nodes-base.stickyNote", "typeVersion": 1, "position": [0, -220]}],
     "connections": chain("Start stone count", "Count north quarry blocks", "Ledger closed for the quarter"), "run": True},
    {"name": "Blue Heron Kitchen sitting planner", "description": "Plans each tide-table sitting and decides on the second dining room.", "tags": ["Blue Heron Kitchen"],
     "nodes": [manual("Start sitting plan"),
               setnode("Plan tide-table sitting", [220, 0], [("covers", 36), ("head_cook", "Marisol Okonkwo-Reyes"), ("broth", "smoked kelp")]),
               {"parameters": {"conditions": {"options": {"caseSensitive": True, "leftValue": "", "typeValidation": "strict", "version": 2},
                    "conditions": [{"id": "c1", "leftValue": "={{ $json.covers }}", "rightValue": 30, "operator": {"type": "number", "operation": "gt"}}],
                    "combinator": "and"}, "options": {}},
                "name": "More than 30 covers?", "type": "n8n-nodes-base.if", "typeVersion": 2.2, "position": [440, 0]},
               noop("Open the second dining room", [660, -100]), noop("Single room is enough", [660, 100])],
     "connections": {**chain("Start sitting plan", "Plan tide-table sitting", "More than 30 covers?"),
                     "More than 30 covers?": {"main": [[{"node": "Open the second dining room", "type": "main", "index": 0}],
                                                       [{"node": "Single room is enough", "type": "main", "index": 0}]]}}, "run": True},
    {"name": "Lighthouse Rota shift handover", "description": "Writes the nightly shift-three handover note for the rota keepers.", "tags": ["Lighthouse Rota"],
     "nodes": [{"parameters": {"rule": {"interval": [{"field": "cronExpression", "expression": "0 22 * * *"}]}},
                "name": "Every night at 22:00", "type": "n8n-nodes-base.scheduleTrigger", "typeVersion": 1.2, "position": [0, 0]},
               setnode("Write handover note", [220, 0], [("shift", "three"), ("hands_over_at", "06:00"), ("tide_tables", "Ada Finch")])],
     "connections": chain("Every night at 22:00", "Write handover note"), "run": False},
    {"name": "Saltmarsh Depot barge drop log", "description": "Logs each barge drop at the Saltmarsh Depot with berth and drum count.", "tags": ["Saltmarsh Depot", "Quarterly Audit"],
     "nodes": [manual("Start drop log"),
               setnode("Record barge drop", [220, 0], [("barge", "Pale Meridian"), ("berth", "B4"), ("drums_of_lamp_oil", 6), ("barge_master", "Tomas Vey")])],
     "connections": chain("Start drop log", "Record barge drop"), "run": False},
]
existing = {w["name"]: w for w in api("GET", "workflows")[0]["data"]}
for w in existing:
    if w.startswith("Rea scratch"):
        api("DELETE", f"workflows/{existing[w]['id']}", quiet=True); log("removed a leftover scratch workflow")
for w in WORKFLOWS:
    if w["name"] in existing:
        wid = existing[w["name"]]["id"]
    else:
        body = {"name": w["name"], "description": w["description"], "nodes": w["nodes"], "connections": w["connections"], "active": False,
                "settings": {"executionOrder": "v1", "saveManualExecutions": True}, "tags": [tags[t] for t in w["tags"]], "pinData": {}}
        wid = api("POST", "workflows", body)[0]["data"]["id"]; log(f"workflow '{w['name']}' created")
    ids["workflows"][w["name"]] = wid

def executions(wid):
    q = urllib.parse.urlencode({"filter": json.dumps({"workflowId": wid}), "limit": 10})
    return api("GET", f"executions?{q}")[0]["data"]["results"]

for w in WORKFLOWS:
    if not w["run"]: continue
    wid = ids["workflows"][w["name"]]
    if not executions(wid):
        full = api("GET", f"workflows/{wid}")[0]["data"]
        # The editor's "Execute workflow" button posts the workflow and names the trigger to start from.
        res, code = api("POST", f"workflows/{wid}/run", {"workflowData": full, "triggerToStartFrom": {"name": w["nodes"][0]["name"]}}, quiet=True)
        log(f"manual run of '{w['name']}' -> {code}")
        for _ in range(30):
            if executions(wid): break
            time.sleep(1)
    runs = executions(wid)
    if not runs: raise SystemExit(f"[seed] no execution recorded for '{w['name']}'")
    ids["executions"][w["name"]] = runs[0]["id"]

# Data tables (the data-table module is active in this build): two small tables with typed columns and rows.
pid = ids["projects"]["personal"]; ids["dataTables"] = {}
TABLES = [
    {"name": "Lamp Oil Drops", "columns": [("lighthouse", "string"), ("litres", "number"), ("barge", "string"), ("signed_by", "string")],
     "rows": [{"lighthouse": "Granite Point Light", "litres": 180, "barge": "Pale Meridian", "signed_by": "Ada Finch"},
              {"lighthouse": "Tidewater Steps Light", "litres": 165, "barge": "Pale Meridian", "signed_by": "Rui Castellanos"},
              {"lighthouse": "Copperfield Beacon", "litres": 140, "barge": "Ember Compass", "signed_by": "Mina Okafor"},
              {"lighthouse": "Saltmarsh Bar Light", "litres": 120, "barge": "Ember Compass", "signed_by": "Tomas Vey"}]},
    {"name": "Quarry Block Tally", "columns": [("quarry", "string"), ("blocks", "number"), ("auditor", "string")],
     "rows": [{"quarry": "North quarry", "blocks": 412, "auditor": "Rui Castellanos"},
              {"quarry": "Tidal yard", "blocks": 97, "auditor": "Rui Castellanos"},
              {"quarry": "Seaward stack", "blocks": 58, "auditor": "Ada Finch"}]},
]
have, code = api("GET", f"projects/{pid}/data-tables?take=50", quiet=True)
have = {t["name"]: t["id"] for t in ((have or {}).get("data") or {}).get("data", [])} if code == 200 else {}
for t in TABLES:
    if t["name"] not in have:
        res, code = api("POST", f"projects/{pid}/data-tables", {"name": t["name"], "columns": [{"name": n, "type": ty} for n, ty in t["columns"]]}, quiet=True)
        if code not in (200, 201): log(f"data table '{t['name']}' not created ({code}: {str(res)[:160]})"); continue
        have[t["name"]] = res["data"]["id"]
        res, code = api("POST", f"projects/{pid}/data-tables/{have[t['name']]}/insert", {"data": t["rows"], "returnType": "id"}, quiet=True)
        log(f"data table '{t['name']}' created, {len(t['rows'])} rows inserted ({code})")
    ids["dataTables"][t["name"]] = have[t["name"]]

# No second user: an invitation would put an accept URL (a sign-up capability for that instance) into every /rest/users reply.
api("POST", "logout", {}, quiet=True); log("seed session closed")
json.dump(ids, open(os.path.join(DIR, "seed-ids.json"), "w"), indent=1)
log("seed-ids.json written (" + ", ".join(f"{k}={len(v)}" for k, v in ids.items()) + ")")
