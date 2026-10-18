#!/usr/bin/env python3
"""Start and seed the showcase Directus with synthetic content through its REST API (idempotent).

On the first run writes ~/capture/directus/.admin (mode 600) with KEY, SECRET and ADMIN_PASSWORD generated at run time;
compose.yml reads that file as env_file, so the project is started from here (`docker compose up -d`) once it exists.
Directus bootstraps the sqlite database and the admin rea-admin@example.com on first start. The script signs in with
the JSON auth mode (token kept in process memory only, logged out at the end) and seeds two collections with fields and
items (crew_rota, provisions), folders, an uploaded text file, roles, a policy with permissions, two users, a bookmark,
an Insights dashboard with a panel, a manual flow and an item comment. Writes seed-ids.json (ids only, no secrets)."""
import json, os, secrets, subprocess, sys, time, urllib.error, urllib.parse, urllib.request

BASE = os.environ.get("BASE_URL", "http://127.0.0.1:3223")
DIR = os.environ.get("CAPTURE_DIR", os.path.expanduser("~/capture/directus"))
ADMIN_FILE = os.path.join(DIR, ".admin")
EMAIL = "rea-admin@example.com"


def log(msg): print(f"[seed] {msg}", file=sys.stderr)


def load_or_create_admin():
    if not os.path.exists(ADMIN_FILE):
        fd = os.open(ADMIN_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(f"KEY={secrets.token_hex(16)}\nSECRET={secrets.token_urlsafe(32)}\nADMIN_PASSWORD={secrets.token_urlsafe(21)}\n")
        log(f"wrote {ADMIN_FILE} (mode 600)")
    kv = dict(line.split("=", 1) for line in open(ADMIN_FILE).read().splitlines() if "=" in line)
    return kv["ADMIN_PASSWORD"]


def healthy():
    try:
        with urllib.request.urlopen(BASE + "/server/health", timeout=5) as r: return r.status == 200
    except Exception: return False


pw = load_or_create_admin()
if not healthy():
    subprocess.run(["docker", "compose", "-p", "rea-directus", "-f", os.path.join(DIR, "compose.yml"), "up", "-d"], check=True, cwd=DIR,
                   stdout=subprocess.DEVNULL)
    log("compose project rea-directus started")
for _ in range(120):
    if healthy(): break
    time.sleep(2)
else:
    raise SystemExit("[seed] Directus did not become healthy")

TOKEN = None


def api(method, path, body=None, ok=(200, 204), raw=None, ctype=None):
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    req = urllib.request.Request(BASE + path, data=data, method=method)
    req.add_header("Accept", "application/json")
    if data is not None: req.add_header("Content-Type", ctype or "application/json")
    if TOKEN: req.add_header("Authorization", "Bearer " + TOKEN)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            out = r.read()
            return json.loads(out) if out else {}
    except urllib.error.HTTPError as e:
        if e.code in ok: return {}
        detail = e.read().decode(errors="replace")[:400]
        raise SystemExit(f"[seed] {method} {path} -> {e.code}: {detail}")


auth = api("POST", "/auth/login", {"email": EMAIL, "password": pw, "mode": "json"})["data"]
TOKEN, REFRESH = auth["access_token"], auth["refresh_token"]
info = api("GET", "/server/info"); log(f"directus {info['data'].get('version')} ready at {BASE}; signed in")
q = urllib.parse.quote
ids = {}


def first(path, field, value):
    """Return the first row of a list endpoint whose `field` equals `value`, or None."""
    rows = api("GET", f"{path}?filter={q(json.dumps({field: {'_eq': value}}))}&limit=1")["data"]
    return rows[0] if rows else None


# Remove scratch items left behind by an interrupted capture so every capture starts from the same state.
if api("GET", "/collections/provisions", ok=(200, 403, 404)).get("data"):
    for row in api("GET", f"/items/provisions?filter={q(json.dumps({'title': {'_starts_with': 'Rea Scratch'}}))}")["data"]:
        api("DELETE", f"/items/provisions/{row['id']}"); log(f"removed leftover scratch provision {row['id']}")

# --- collections with fields ---
COLLECTIONS = {
    "crew_rota": {
        "meta": {"icon": "badge", "note": "Who keeps which watch for the Lighthouse Rota.", "display_template": "{{name}}", "sort_field": None},
        "fields": [("name", "string", "input", "Crew member as written on the rota board."),
                   ("role_title", "string", "input", "Job title on the rota."),
                   ("shift", "string", "select-dropdown", "Dawn, Day, Evening or Night."),
                   ("watch_station", "string", "input", "Where the watch is kept."),
                   ("notes", "text", "input-multiline", "Free notes from the rota keeper.")]},
    "provisions": {
        "meta": {"icon": "inventory_2", "note": "Stores held at the Saltmarsh Depot for the rota.", "display_template": "{{title}}"},
        "fields": [("title", "string", "input", "Provision name as stencilled on the crate."),
                   ("category", "string", "input", "Food, Lamp or Workshop."),
                   ("quantity", "integer", "input", "Units on hand."),
                   ("unit", "string", "input", "Counting unit."),
                   ("storage_bay", "string", "input", "Depot bay where the provision is kept."),
                   ("supplier_note", "string", "input", "Who supplies it and when.")]},
}
for coll, spec in COLLECTIONS.items():
    if not api("GET", f"/collections/{coll}", ok=(200, 403, 404)).get("data"):
        fields = [{"field": "id", "type": "integer", "meta": {"hidden": True, "interface": "input", "readonly": True},
                   "schema": {"is_primary_key": True, "has_auto_increment": True}}]
        for name, ftype, iface, note in spec["fields"]:
            meta = {"interface": iface, "note": note}
            if name == "shift": meta["options"] = {"choices": [{"text": t, "value": t} for t in ("Dawn", "Day", "Evening", "Night")]}
            fields.append({"field": name, "type": ftype, "meta": meta, "schema": {}})
        api("POST", "/collections", {"collection": coll, "meta": spec["meta"], "schema": {}, "fields": fields}); log(f"collection {coll} created")
ids["collections"] = list(COLLECTIONS)

CREW = [
    {"name": "Ada Finch", "role_title": "Tide Table Keeper", "shift": "Night", "watch_station": "North Lamp Gallery", "notes": "Keeps the January tide tables."},
    {"name": "Rui Castellanos", "role_title": "Quarry Auditor", "shift": "Day", "watch_station": "Granite Ledger Office", "notes": "Audited stone count GL-2291."},
    {"name": "Mina Okafor", "role_title": "Market Liaison", "shift": "Day", "watch_station": "Blue Heron Kitchen", "notes": "Runs the Tuesday quayside stall."},
    {"name": "Tomas Vey", "role_title": "Cracker Baker", "shift": "Dawn", "watch_station": "Copperfield Annex", "notes": "Packs the rye crackers on Mondays."},
    {"name": "Marisol Okonkwo-Reyes", "role_title": "Head Cook", "shift": "Evening", "watch_station": "Blue Heron Kitchen", "notes": "Pairs kelp broth with the 22:00 shift."},
]
PROVISIONS = [
    {"title": "Saffron Tide Biscuits", "category": "Food", "quantity": 48, "unit": "tins", "storage_bay": "Bay C2", "supplier_note": "Baked by Tomas Vey every Monday."},
    {"title": "Pale Meridian Tea", "category": "Food", "quantity": 12, "unit": "bricks", "storage_bay": "Bay A1", "supplier_note": "Pressed bricks from the Lighthouse Rota Co-op."},
    {"title": "Ember Compass Matches", "category": "Lamp", "quantity": 300, "unit": "boxes", "storage_bay": "Bay B4", "supplier_note": "Wax-dipped, kept away from the lamp oil."},
    {"title": "Silver Anvil Rivets", "category": "Workshop", "quantity": 900, "unit": "pieces", "storage_bay": "Bay D1", "supplier_note": "For the Granite Ledger cart repairs."},
    {"title": "Northern Quill Ink", "category": "Workshop", "quantity": 6, "unit": "bottles", "storage_bay": "Bay A3", "supplier_note": "Iron-gall ink for the rota ledger."},
]
for coll, rows, key in (("crew_rota", CREW, "name"), ("provisions", PROVISIONS, "title")):
    for row in rows:
        cur = first(f"/items/{coll}", key, row[key])
        if cur is None: cur = api("POST", f"/items/{coll}", row)["data"]; log(f"{coll}: {row[key]} created")
        ids.setdefault(coll, {})[row[key]] = cur["id"]

# --- folders and one uploaded text file ---
parent = first("/folders", "name", "Lighthouse Rota Archive") or api("POST", "/folders", {"name": "Lighthouse Rota Archive"})["data"]
child = first("/folders", "name", "Granite Ledger Scans") or api("POST", "/folders", {"name": "Granite Ledger Scans", "parent": parent["id"]})["data"]
ids["folders"] = {"Lighthouse Rota Archive": parent["id"], "Granite Ledger Scans": child["id"]}
f = first("/files", "title", "Granite Ledger tally GL-2291")
if f is None:
    boundary = "rea" + secrets.token_hex(8)
    content = b"Granite Ledger tally GL-2291\nNorth quarry: 412 blocks\nTidal yard: 97 blocks\nAudited by Rui Castellanos.\n"
    parts = []
    for name, value in (("title", "Granite Ledger tally GL-2291"), ("description", "Quarterly stone count audited by Rui Castellanos."),
                        ("folder", child["id"])):
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode())
    parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="granite-ledger-gl-2291.txt"\r\n'
                 f'Content-Type: text/plain\r\n\r\n'.encode() + content + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    f = api("POST", "/files", raw=b"".join(parts), ctype=f"multipart/form-data; boundary={boundary}")["data"]; log("file uploaded")
ids["files"] = {"Granite Ledger tally GL-2291": f["id"]}

# --- access: a policy with permissions, two roles, two users ---
pol = first("/policies", "name", "Rota Editing")
if pol is None:
    pol = api("POST", "/policies", {"name": "Rota Editing", "icon": "edit_note", "description": "Create and update crew rota entries and read provisions.",
                                     "app_access": True, "admin_access": False})["data"]
    for coll, action in (("crew_rota", "create"), ("crew_rota", "read"), ("crew_rota", "update"), ("provisions", "read")):
        api("POST", "/permissions", {"policy": pol["id"], "collection": coll, "action": action, "fields": ["*"]})
    log("policy Rota Editing with 4 permissions created")
ids["policies"] = {"Rota Editing": pol["id"]}
ROLES = [("Rota Editors", "Keepers of the crew rota for the Lighthouse Rota.", "badge"),
         ("Depot Viewers", "Read-only visitors to the Saltmarsh Depot stores.", "visibility")]
for name, desc, icon in ROLES:
    r = first("/roles", "name", name)
    if r is None:
        r = api("POST", "/roles", {"name": name, "description": desc, "icon": icon})["data"]; log(f"role {name} created")
        if name == "Rota Editors": api("POST", "/access", {"role": r["id"], "policy": pol["id"]})
    ids.setdefault("roles", {})[name] = r["id"]
USERS = [
    {"first_name": "Ada", "last_name": "Finch", "email": "ada.finch@example.com", "title": "Tide Table Keeper", "location": "North Lamp Gallery",
     "description": "Keeps the tide tables for the winter rota.", "role": ids["roles"]["Rota Editors"], "status": "active"},
    {"first_name": "Rui", "last_name": "Castellanos", "email": "rui.castellanos@example.com", "title": "Quarry Auditor", "location": "Granite Ledger Office",
     "description": "Counts granite by lamplight and audits the ledger.", "role": ids["roles"]["Depot Viewers"], "status": "active"},
]
for u in USERS:
    cur = first("/users", "email", u["email"])
    if cur is None: cur = api("POST", "/users", u)["data"]; log(f"user {u['email']} created")
    ids.setdefault("users", {})[u["email"]] = cur["id"]
me = api("GET", "/users/me")["data"]
# last_page is where the Data Studio lands after sign-in; reset it so every capture starts on the crew rota.
api("PATCH", "/users/me", {"first_name": "Rea", "last_name": "Admin", "title": "Rota Archivist", "location": "Granite Point",
                           "last_page": "/content/crew_rota"})
ids["users"]["rea-admin"] = me["id"]

# --- bookmark, Insights dashboard with a panel, a manual flow, a comment ---
bm = first("/presets", "bookmark", "Night shift crew")
if bm is None:
    bm = api("POST", "/presets", {"bookmark": "Night shift crew", "collection": "crew_rota", "icon": "nightlight", "layout": "tabular",
                                  "filter": {"shift": {"_eq": "Night"}}})["data"]; log("bookmark created")
ids["presets"] = {"Night shift crew": bm["id"]}
dash = first("/dashboards", "name", "Depot Overview")
if dash is None:
    dash = api("POST", "/dashboards", {"name": "Depot Overview", "icon": "space_dashboard", "note": "Provisions and rota at a glance for the depot."})["data"]
    log("dashboard created")
ids["dashboards"] = {"Depot Overview": dash["id"]}
panel = first("/panels", "name", "Provisions on hand")
if panel is None:
    panel = api("POST", "/panels", {"dashboard": dash["id"], "name": "Provisions on hand", "icon": "inventory_2", "type": "metric",
                                    "note": "Sum of quantity across all provisions.", "position_x": 1, "position_y": 1, "width": 12, "height": 6,
                                    "show_header": True, "options": {"collection": "provisions", "field": "quantity", "function": "sum"}})["data"]
    log("panel created")
ids["panels"] = {"Provisions on hand": panel["id"]}
flow = first("/flows", "name", "Announce new provisions")
if flow is None:
    flow = api("POST", "/flows", {"name": "Announce new provisions", "icon": "campaign", "status": "inactive", "trigger": "manual",
                                  "description": "Posts a note to the rota board when a provision arrives.", "accountability": "all",
                                  "options": {"collections": ["provisions"], "location": "item"}})["data"]
    log("flow created")
ids["flows"] = {"Announce new provisions": flow["id"]}
com = first("/comments", "comment", "Ada swaps the January night watch with Tomas Vey.")
if com is None:
    com = api("POST", "/comments", {"collection": "crew_rota", "item": str(ids["crew_rota"]["Ada Finch"]),
                                    "comment": "Ada swaps the January night watch with Tomas Vey."})["data"]; log("comment created")
ids["comments"] = {"night watch swap": com["id"]}

api("POST", "/auth/logout", {"refresh_token": REFRESH, "mode": "json"})
json.dump(ids, open(os.path.join(DIR, "seed-ids.json"), "w"), indent=1)
log("seed-ids.json written: " + json.dumps({k: (list(v.values()) if isinstance(v, dict) else v) for k, v in ids.items()}))
