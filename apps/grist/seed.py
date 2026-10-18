#!/usr/bin/env python3
"""Seed the showcase Grist with synthetic content through its REST API (idempotent).

Grist runs single-user (GRIST_DEFAULT_EMAIL=rea-admin@example.test, the built-in "minimal" login: visiting /login signs the
browser in as that user, there is no password). The seed signs in that way once, renames the user from the default "You"
to "Rea Admin", creates an API key (POST /api/profile/apiKey) and keeps it only in ~/capture/grist/.admin (mode 600); all
further calls use that key as a Bearer token. Seeds 2 workspaces besides "Home", 3 documents, 6 tables with typed columns
(one formula column, one reference column) and 17 records, and shares two documents with three invented people. Removes
"Rea Scratch" documents and records left by an interrupted capture. Writes seed-ids.json (ids only). Never prints the key."""
import http.cookiejar, json, os, sys, time, urllib.error, urllib.parse, urllib.request

BASE = os.environ.get("BASE_URL", "http://127.0.0.1:3220")
DIR = os.environ.get("CAPTURE_DIR", os.path.expanduser("~/capture/grist"))
ADMIN_FILE = os.path.join(DIR, ".admin")
NAME = "Rea Admin"


def log(msg): print(f"[seed] {msg}", file=sys.stderr)


def read_admin():
    if not os.path.exists(ADMIN_FILE): raise SystemExit("[seed] run up.sh first (it creates .admin)")
    return dict(l.split("=", 1) for l in open(ADMIN_FILE).read().splitlines() if "=" in l)


def wait_ready():
    for _ in range(120):
        try:
            with urllib.request.urlopen(BASE + "/status", timeout=5) as r:
                if r.status == 200: return
        except Exception: pass
        time.sleep(2)
    raise SystemExit("[seed] Grist did not become ready")


admin = {}; cookie_op = None
def api(method, path, body=None, ok404=False, raw=False):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method)
    req.add_header("Accept", "application/json"); req.add_header("X-Requested-With", "XMLHttpRequest")
    if data is not None: req.add_header("Content-Type", "application/json")
    if admin.get("GRIST_API_KEY"): req.add_header("Authorization", f"Bearer {admin['GRIST_API_KEY']}"); opener = urllib.request.build_opener()
    else: req.add_header("Origin", BASE); opener = cookie_op
    try:
        with opener.open(req, timeout=60) as r:
            t = r.read().decode()
            if raw or not t: return t or None
            try: return json.loads(t)
            except ValueError: return t  # e.g. the profile name endpoint answers plain text
    except urllib.error.HTTPError as e:
        if e.code == 404 and ok404: return None
        raise SystemExit(f"[seed] {method} {path} -> {e.code}: {e.read().decode(errors='replace')[:300]}")


wait_ready(); log(f"grist ready at {BASE}")
admin = read_admin()
if "GRIST_API_KEY" not in admin:
    jar = http.cookiejar.CookieJar(); cookie_op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    cookie_op.open(BASE + "/login", timeout=30)  # minimal login: the session becomes the default user
    key = api("POST", "/api/profile/apiKey", raw=True).strip().strip('"')
    if len(key) < 20: raise SystemExit("[seed] unexpected API key response")
    with open(ADMIN_FILE, "a") as f: f.write(f"GRIST_API_KEY={key}\n")
    os.chmod(ADMIN_FILE, 0o600); admin = read_admin(); log("API key created for the default user, kept in .admin")
me = api("GET", "/api/profile/user")
if me["name"] != NAME: api("POST", "/api/profile/user/name", {"name": NAME}); log("user renamed to Rea Admin")
org = [o for o in api("GET", "/api/orgs") if o["owner"] and o["owner"]["id"] == me["id"]][0]
ids = {"user_id": me["id"], "org_id": org["id"], "org_domain": org["domain"], "workspaces": {}, "docs": {}, "tables": {}}

SPEC = {
    "Lighthouse Rota": {
        "Night Shift Planner": {
            "Keepers": {
                "columns": [("Name", "Text"), ("Role", "Text"), ("Email", "Text"), ("Station", "Text"), ("Notes", "Text")],
                "records": [
                    {"Name": "Ada Finch", "Role": "Head Keeper", "Email": "ada.finch@example.test", "Station": "Lamp Room", "Notes": "Keeps the tide tables for January"},
                    {"Name": "Tomas Vey", "Role": "Wick Steward", "Email": "tomas.vey@example.test", "Station": "Drawer B store", "Notes": "Trims wicks to 4 mm before the 22:00 check"},
                    {"Name": "Mina Okafor", "Role": "Fire Warden", "Email": "mina.okafor@example.test", "Station": "Gallery stairs", "Notes": "Refills the fire buckets every Monday"},
                ]},
            "Shifts": {
                "columns": [("Title", "Text"), ("Keeper", "Ref:Keepers"), ("Starts", "Text"), ("Ends", "Text"), ("Summary", "Text")],
                "records": [
                    {"Title": "Shift Three", "Keeper": 1, "Starts": "22:00", "Ends": "06:00", "Summary": "Lamp check at 22:00, handover to the dawn crew"},
                    {"Title": "Dawn Watch", "Keeper": 2, "Starts": "06:00", "Ends": "14:00", "Summary": "Polish the lens and log the fog signals"},
                    {"Title": "Fog Watch", "Keeper": 3, "Starts": "14:00", "Ends": "22:00", "Summary": "Sound the horn every ninety seconds in fog"},
                ]},
            "Supplies": {
                "columns": [("Item", "Text"), ("Quantity", "Numeric"), ("Unit", "Text"), ("Location", "Text"), ("Reorder", "Bool", "$Quantity < 50")],
                "records": [
                    {"Item": "Lamp oil", "Quantity": 138, "Unit": "litres", "Location": "Saltmarsh Depot"},
                    {"Item": "Spare wicks", "Quantity": 24, "Unit": "pieces", "Location": "Drawer B"},
                    {"Item": "Chamois cloths", "Quantity": 6, "Unit": "pieces", "Location": "Lamp Room shelf"},
                ]},
        },
        "Blue Heron Kitchen Menu": {
            "Dishes": {
                "columns": [("Title", "Text"), ("Course", "Text"), ("Covers", "Int"), ("Cook", "Text"), ("Description", "Text")],
                "records": [
                    {"Title": "Smoked Kelp Broth", "Course": "starter", "Covers": 36, "Cook": "Marisol Okonkwo-Reyes", "Description": "Kelp goes in after twenty minutes of simmering"},
                    {"Title": "Tide Pool Risotto", "Course": "main", "Covers": 24, "Cook": "Rui Castellanos", "Description": "Barley risotto with samphire from the flats"},
                    {"Title": "Saltmarsh Samphire Tart", "Course": "dessert", "Covers": 18, "Cook": "Mina Okafor", "Description": "Served cold at the 22:00 handover"},
                ]},
        },
    },
    "Granite Ledger": {
        "Quarry Audit 2026": {
            "Terraces": {
                "columns": [("Name", "Text"), ("Blocks", "Int"), ("Auditor", "Text"), ("Status", "Text"), ("Notes", "Text")],
                "records": [
                    {"Name": "Terrace Seven", "Blocks": 58, "Auditor": "Rui Castellanos", "Status": "audited", "Notes": "Cart number 7 retired after the audit"},
                    {"Name": "Terrace Three", "Blocks": 112, "Auditor": "Rui Castellanos", "Status": "audited", "Notes": "Counted twice on the fourteenth"},
                    {"Name": "North Ledge", "Blocks": 97, "Auditor": "Ada Finch", "Status": "pending", "Notes": "Seaward stack still to be re-measured"},
                ]},
            "Carts": {
                "columns": [("Label", "Text"), ("Capacity", "Int"), ("Retired", "Bool"), ("Depot", "Text")],
                "records": [
                    {"Label": "Cart 7", "Capacity": 12, "Retired": True, "Depot": "Copperfield Annex"},
                    {"Label": "Cart 9", "Capacity": 14, "Retired": False, "Depot": "Saltmarsh Depot"},
                ]},
        },
    },
}

workspaces = {w["name"]: w for w in api("GET", f"/api/orgs/{org['id']}/workspaces")}
ids["workspaces"]["Home"] = workspaces["Home"]["id"]
for ws_name, docs in SPEC.items():
    if ws_name not in workspaces:
        wid = api("POST", f"/api/orgs/{org['id']}/workspaces", {"name": ws_name}); log(f"workspace {ws_name} created")
        workspaces[ws_name] = api("GET", f"/api/workspaces/{wid}")
    wid = workspaces[ws_name]["id"]; ids["workspaces"][ws_name] = wid
    existing_docs = {d["name"]: d["id"] for d in api("GET", f"/api/workspaces/{wid}")["docs"]}
    for d in [x for x in existing_docs if x.startswith("Rea Scratch")]:
        api("DELETE", f"/api/docs/{existing_docs.pop(d)}"); log(f"removed leftover doc {d}")
    for doc_name, tables in docs.items():
        if doc_name not in existing_docs:
            existing_docs[doc_name] = api("POST", f"/api/workspaces/{wid}/docs", {"name": doc_name}); log(f"doc {doc_name} created")
        doc = existing_docs[doc_name]; ids["docs"][doc_name] = doc
        have = [t["id"] for t in api("GET", f"/api/docs/{doc}/tables")["tables"]]
        for tname, spec in tables.items():
            if tname not in have:
                cols = [{"id": c[0], "fields": {"label": c[0], "type": c[1], **({"isFormula": True, "formula": c[2]} if len(c) > 2 else {})}} for c in spec["columns"]]
                api("POST", f"/api/docs/{doc}/tables", {"tables": [{"id": tname, "columns": cols}]}); log(f"table {doc_name}/{tname} created")
            rows = api("GET", f"/api/docs/{doc}/tables/{tname}/records")["records"]
            for r in [r for r in rows if str(r["fields"].get(spec["columns"][0][0], "")).startswith("Rea Scratch")]:
                api("POST", f"/api/docs/{doc}/tables/{tname}/records/delete", [r["id"]]); log(f"removed leftover record {r['id']} in {tname}")
            if not [r for r in rows if not str(r["fields"].get(spec["columns"][0][0], "")).startswith("Rea Scratch")]:
                api("POST", f"/api/docs/{doc}/tables/{tname}/records", {"records": [{"fields": f} for f in spec["records"]]}); log(f"{len(spec['records'])} records into {tname}")
            ids["tables"].setdefault(doc_name, []).append(tname)
        if "Table1" in have:
            api("POST", f"/api/docs/{doc}/apply", [["RemoveTable", "Table1"]]); log(f"removed the default Table1 from {doc_name}")

# Share two documents with invented people (no mail transport: Grist only records the grant).
api("PATCH", f"/api/docs/{ids['docs']['Night Shift Planner']}/access",
    {"delta": {"users": {"ada.finch@example.test": "editors", "tomas.vey@example.test": "viewers"}}})
api("PATCH", f"/api/docs/{ids['docs']['Quarry Audit 2026']}/access", {"delta": {"users": {"rui.castellanos@example.test": "owners"}}})
log("Night Shift Planner shared with Ada Finch (editor) and Tomas Vey (viewer); Quarry Audit 2026 with Rui Castellanos (owner)")

json.dump(ids, open(os.path.join(DIR, "seed-ids.json"), "w"), indent=1)
log("seed-ids.json written: " + json.dumps({k: (len(v) if isinstance(v, dict) else v) for k, v in ids.items()}))
