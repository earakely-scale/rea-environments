#!/usr/bin/env python3
"""Seed the showcase Baserow with synthetic content through its REST API (idempotent where practical).

Signs up the first user "Rea Admin" <rea-admin@example.test> (the first account becomes the instance admin) with a
password generated at run time and kept only in ~/capture/baserow/.admin (mode 600); the JWT access token lives in this
process only. Creates workspace "Saltmarsh Depot Cooperative", database "Lighthouse Rota" and three typed tables
(Stations, Keepers, Supply Orders) with link-row, single-select, number, boolean, date, email and long-text fields,
4-5 rows each, an edit on one row (so its history has an entry), two extra grid views with a filter and a sort, a
gallery view and a form view. Writes seed-ids.json (ids only, no secrets). Never prints the password or a token."""
import json, os, secrets, sys, time, urllib.error, urllib.request

BASE = os.environ.get("BASE_URL", "http://127.0.0.1:3204")
DIR = os.environ.get("CAPTURE_DIR", os.path.expanduser("~/capture/baserow"))
ADMIN_FILE = os.path.join(DIR, ".admin")
EMAIL, NAME = "rea-admin@example.test", "Rea Admin"
WORKSPACE, DATABASE = "Saltmarsh Depot Cooperative", "Lighthouse Rota"
TOKEN = None

def log(msg): print(f"[seed] {msg}", file=sys.stderr)

def load_or_create_admin():
    if os.path.exists(ADMIN_FILE):
        kv = dict(line.split("=", 1) for line in open(ADMIN_FILE).read().splitlines() if "=" in line)
        return kv["BASEROW_ADMIN_PASSWORD"], False
    pw = secrets.token_urlsafe(18) + "Aa1"
    fd = os.open(ADMIN_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(f"BASEROW_ADMIN_PASSWORD={pw}\n")  # the email is a fixed constant, not a secret
    log(f"wrote {ADMIN_FILE} (mode 600)")
    return pw, True

def api(method, path, body=None, ok=(), auth=True):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method)
    req.add_header("Accept", "application/json")
    if data is not None: req.add_header("Content-Type", "application/json")
    if auth and TOKEN: req.add_header("Authorization", "JWT " + TOKEN)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read()
            return (json.loads(raw) if raw else {}), r.status
    except urllib.error.HTTPError as e:
        if e.code in ok: return None, e.code
        detail = e.read().decode(errors="replace")[:400]
        raise SystemExit(f"[seed] {method} {path} -> {e.code}: {detail}")

def wait_ready():
    for _ in range(90):
        try:
            with urllib.request.urlopen(BASE + "/api/settings/", timeout=5) as r:
                if r.status == 200: return
        except Exception: pass
        time.sleep(4)
    raise SystemExit("[seed] Baserow did not become ready")

wait_ready(); log(f"baserow ready at {BASE}")
pw, fresh = load_or_create_admin()
res, st = api("POST", "/api/user/", {"name": NAME, "email": EMAIL, "password": pw, "language": "en"}, ok=(400,), auth=False)
log("first account created through POST /api/user/" if res is not None else "account existed")
res, _ = api("POST", "/api/user/token-auth/", {"email": EMAIL, "password": pw}, auth=False)  # sign-up does not return a token
TOKEN = res.get("access_token") or res.get("token")
if not TOKEN: raise SystemExit("[seed] no access token in the auth response")
ids = {"workspace": None, "database": None, "tables": {}, "fields": {}, "rows": {}, "views": {}, "filters": {}, "options": {}}

# --- workspace and database ---
wss, _ = api("GET", "/api/workspaces/")
ws = next((w for w in wss if w["name"] == WORKSPACE), None)
if ws is None: ws, _ = api("POST", "/api/workspaces/", {"name": WORKSPACE}); log("workspace created")
ids["workspace"] = ws["id"]
apps, _ = api("GET", f"/api/applications/workspace/{ws['id']}/")
db = next((a for a in apps if a["name"] == DATABASE and a["type"] == "database"), None)
if db is None: db, _ = api("POST", f"/api/applications/workspace/{ws['id']}/", {"type": "database", "name": DATABASE}); log("database created")
ids["database"] = db["id"]
# A second, small database so the applications list has more than one entry.
db2 = next((a for a in apps if a["name"] == "Granite Ledger Archive"), None)
if db2 is None: db2, _ = api("POST", f"/api/applications/workspace/{ws['id']}/", {"type": "database", "name": "Granite Ledger Archive"}); log("second database created")
ids["database2"] = db2["id"]

def ensure_table(name, primary_name, fields):
    """Create a table with a renamed primary text field and the given extra fields; drop Baserow's default fields and rows."""
    tables, _ = api("GET", f"/api/database/tables/database/{db['id']}/")
    t = next((x for x in tables if x["name"] == name), None)
    created = t is None
    if created:
        t, _ = api("POST", f"/api/database/tables/database/{db['id']}/", {"name": name}); log(f"table {name} created")
    ids["tables"][name] = t["id"]
    cur, _ = api("GET", f"/api/database/fields/table/{t['id']}/")
    prim = next(f for f in cur if f["primary"])
    if prim["name"] != primary_name: api("PATCH", f"/api/database/fields/{prim['id']}/", {"name": primary_name})
    fmap = {primary_name: prim["id"]}
    wanted = {f["name"] for f in fields}
    for f in cur:
        if not f["primary"] and f["name"] not in wanted: api("DELETE", f"/api/database/fields/{f['id']}/")
    have = {f["name"]: f for f in cur}
    for spec in fields:
        if spec["name"] in have: fmap[spec["name"]] = have[spec["name"]]["id"]; fld = have[spec["name"]]
        else: fld, _ = api("POST", f"/api/database/fields/table/{t['id']}/", spec); fmap[spec["name"]] = fld["id"]
        if spec["type"] == "single_select":
            ids["options"][f"{name}.{spec['name']}"] = {o["value"]: o["id"] for o in fld["select_options"]}
    ids["fields"][name] = fmap
    if created:  # Baserow adds two blank rows to a new table
        rows, _ = api("GET", f"/api/database/rows/table/{t['id']}/?size=200")
        blank = [r["id"] for r in rows["results"]]
        if blank: api("POST", f"/api/database/rows/table/{t['id']}/batch-delete/", {"items": blank})
    return t["id"]

def ensure_rows(table, key, items):
    tid = ids["tables"][table]
    rows, _ = api("GET", f"/api/database/rows/table/{tid}/?user_field_names=true&size=200")
    have = {r[key]: r["id"] for r in rows["results"]}
    todo = [it for it in items if it[key] not in have]
    if todo:
        out, _ = api("POST", f"/api/database/rows/table/{tid}/batch/?user_field_names=true", {"items": todo})
        for r in out["items"]: have[r[key]] = r["id"]
        log(f"{len(todo)} rows added to {table}")
    ids["rows"][table] = {it[key]: have[it[key]] for it in items}

# --- Stations ---
ensure_table("Stations", "Name", [
    {"name": "Region", "type": "text"},
    {"name": "Beam range (nm)", "type": "number", "number_decimal_places": 0},
    {"name": "Commissioned", "type": "date", "date_format": "ISO", "date_include_time": False},
    {"name": "Lamp", "type": "text"},
    {"name": "Staffed", "type": "boolean"},
    {"name": "Description", "type": "long_text"},
])
ensure_rows("Stations", "Name", [
    {"Name": "Granite Point Light", "Region": "North Shoal", "Beam range (nm)": "18", "Commissioned": "1891-05-14", "Lamp": "Fresnel second order", "Staffed": True,
     "Description": "Granite tower on the north shoal; the oldest station on the rota."},
    {"Name": "Copperfield Annex Beacon", "Region": "Copperfield Sound", "Beam range (nm)": "9", "Commissioned": "1934-09-02", "Lamp": "LED cluster", "Staffed": False,
     "Description": "Unmanned beacon on the annex pier, checked weekly from the depot."},
    {"Name": "Blue Heron Spit", "Region": "Heron Flats", "Beam range (nm)": "12", "Commissioned": "1902-03-21", "Lamp": "Acetylene retrofit", "Staffed": True,
     "Description": "Wooden lantern house on the spit; the heron colony nests behind it."},
    {"Name": "Saltmarsh Depot Tower", "Region": "Saltmarsh Reach", "Beam range (nm)": "22", "Commissioned": "1875-11-08", "Lamp": "Fresnel first order", "Staffed": True,
     "Description": "Supply depot and the longest beam on the coast."},
])

# --- Keepers ---
ensure_table("Keepers", "Name", [
    {"name": "Email", "type": "email"},
    {"name": "Station", "type": "link_row", "link_row_table_id": ids["tables"]["Stations"], "has_related_field": True},
    {"name": "Rank", "type": "single_select", "select_options": [
        {"value": "Head keeper", "color": "blue"}, {"value": "Assistant keeper", "color": "green"}, {"value": "Relief keeper", "color": "orange"}]},
    {"name": "Shifts per month", "type": "number", "number_decimal_places": 0},
    {"name": "Certified", "type": "boolean"},
    {"name": "Notes", "type": "long_text"},
])
rk = ids["options"]["Keepers.Rank"]; st_ = ids["rows"]["Stations"]
ensure_rows("Keepers", "Name", [
    {"Name": "Ada Finch", "Email": "ada.finch@example.test", "Station": [st_["Granite Point Light"]], "Rank": rk["Head keeper"], "Shifts per month": "12", "Certified": True,
     "Notes": "Keeps the tide tables for January."},
    {"Name": "Rui Castellanos", "Email": "rui.castellanos@example.test", "Station": [st_["Saltmarsh Depot Tower"]], "Rank": rk["Assistant keeper"], "Shifts per month": "11", "Certified": True,
     "Notes": "Audits the lamp-oil ledger every fortnight."},
    {"Name": "Mina Okafor", "Email": "mina.okafor@example.test", "Station": [st_["Blue Heron Spit"]], "Rank": rk["Relief keeper"], "Shifts per month": "6", "Certified": False,
     "Notes": "Covers the Heron Flats night shift on spring tides."},
    {"Name": "Tomas Vey", "Email": "tomas.vey@example.test", "Station": [st_["Copperfield Annex Beacon"]], "Rank": rk["Head keeper"], "Shifts per month": "8", "Certified": True,
     "Notes": "Rebuilt the beacon's lantern mount in March."},
    {"Name": "Ilse Marrow", "Email": "ilse.marrow@example.test", "Station": [st_["Granite Point Light"]], "Rank": rk["Assistant keeper"], "Shifts per month": "9", "Certified": False,
     "Notes": "Learning the fog-signal schedule."},
])

# --- Supply Orders ---
ensure_table("Supply Orders", "Order code", [
    {"name": "Item", "type": "text"},
    {"name": "Quantity", "type": "number", "number_decimal_places": 0},
    {"name": "Station", "type": "link_row", "link_row_table_id": ids["tables"]["Stations"], "has_related_field": False},
    {"name": "Stage", "type": "single_select", "select_options": [
        {"value": "Requested", "color": "light-orange"}, {"value": "Shipped", "color": "light-blue"}, {"value": "Delivered", "color": "light-green"}]},
    {"name": "Supplier", "type": "text"},
    {"name": "Requested by", "type": "link_row", "link_row_table_id": ids["tables"]["Keepers"], "has_related_field": False},
])
sg = ids["options"]["Supply Orders.Stage"]; kp = ids["rows"]["Keepers"]
ensure_rows("Supply Orders", "Order code", [
    {"Order code": "SO-4471", "Item": "Lamp oil, 180 litres", "Quantity": "180", "Station": [st_["Granite Point Light"]], "Stage": sg["Delivered"],
     "Supplier": "Granite Ledger Chandlery", "Requested by": [kp["Ada Finch"]]},
    {"Order code": "SO-4472", "Item": "Lens polishing cloths", "Quantity": "24", "Station": [st_["Saltmarsh Depot Tower"]], "Stage": sg["Shipped"],
     "Supplier": "Copperfield Annex Stores", "Requested by": [kp["Rui Castellanos"]]},
    {"Order code": "SO-4473", "Item": "Fog horn diaphragm", "Quantity": "2", "Station": [st_["Blue Heron Spit"]], "Stage": sg["Requested"],
     "Supplier": "Tidewater Brass Works", "Requested by": [kp["Mina Okafor"]]},
    {"Order code": "SO-4474", "Item": "Tide gauge batteries", "Quantity": "16", "Station": [st_["Copperfield Annex Beacon"]], "Stage": sg["Requested"],
     "Supplier": "Saltmarsh Depot Provisions", "Requested by": [kp["Tomas Vey"]]},
])

# Remove scratch orders left by an interrupted capture so every capture starts from the same state.
left, _ = api("GET", f"/api/database/rows/table/{ids['tables']['Supply Orders']}/?user_field_names=true&size=200")
scratch = [r["id"] for r in left["results"] if str(r.get("Order code", "")).startswith("SO-9")]
if scratch: api("POST", f"/api/database/rows/table/{ids['tables']['Supply Orders']}/batch-delete/", {"items": scratch}); log(f"removed {len(scratch)} leftover scratch orders")

# One edit so the row history of Ada Finch has an entry (12 -> 14 shifts).
ada = kp["Ada Finch"]; kf = ids["fields"]["Keepers"]
row, _ = api("GET", f"/api/database/rows/table/{ids['tables']['Keepers']}/{ada}/?user_field_names=true")
if str(row.get("Shifts per month")) != "14":
    api("PATCH", f"/api/database/rows/table/{ids['tables']['Keepers']}/{ada}/?user_field_names=true", {"Shifts per month": "14"}); log("Ada Finch edited (history entry)")

# --- extra views ---
def ensure_view(table, name, vtype, extra=None):
    tid = ids["tables"][table]
    views, _ = api("GET", f"/api/database/views/table/{tid}/")
    v = next((x for x in views if x["name"] == name), None)
    if v is None: v, _ = api("POST", f"/api/database/views/table/{tid}/", {"name": name, "type": vtype, **(extra or {})}); log(f"view {name} created")
    ids["views"][name] = v["id"]
    return v["id"]

for t, vname in (("Stations", "All stations"), ("Keepers", "Keeper roster"), ("Supply Orders", "Order book")):
    views, _ = api("GET", f"/api/database/views/table/{ids['tables'][t]}/")
    if views:
        ids["views"][f"{t} default grid"] = views[0]["id"]
        if views[0]["name"] != vname: api("PATCH", f"/api/database/views/{views[0]['id']}/", {"name": vname}); log(f"default view of {t} renamed {vname}")
vk = ensure_view("Keepers", "Certified keepers", "grid", {"filter_type": "AND"})
flt, _ = api("GET", f"/api/database/views/{vk}/filters/")
if not flt: f_, _ = api("POST", f"/api/database/views/{vk}/filters/", {"field": kf["Certified"], "type": "boolean", "value": "1"}); flt = [f_]
ids["filters"]["Certified keepers"] = flt[0]["id"]
srt, _ = api("GET", f"/api/database/views/{vk}/sortings/")
if not srt: api("POST", f"/api/database/views/{vk}/sortings/", {"field": kf["Shifts per month"], "order": "DESC"})
vo = ensure_view("Supply Orders", "Open orders", "grid", {"filter_type": "AND"})
flt, _ = api("GET", f"/api/database/views/{vo}/filters/")
if not flt: f_, _ = api("POST", f"/api/database/views/{vo}/filters/", {"field": ids["fields"]["Supply Orders"]["Stage"], "type": "single_select_not_equal", "value": str(sg["Delivered"])}); flt = [f_]
ids["filters"]["Open orders"] = flt[0]["id"]
ensure_view("Stations", "Station cards", "gallery")
ensure_view("Supply Orders", "Request supplies", "form", {"title": "Request supplies for your station",
            "description": "Orders reach the Saltmarsh Depot quartermaster within two tides."})

json.dump(ids, open(os.path.join(DIR, "seed-ids.json"), "w"), indent=1)
log("seed-ids.json written")
