#!/usr/bin/env python3
"""Seed the showcase Metabase with synthetic content through its JSON API (idempotent by name).

First run: reads the one-time setup token from GET /api/session/properties and creates the admin through POST /api/setup
(Rea Admin, rea-admin@example.test, site "Lighthouse Rota Analytics") with a password generated at run time and kept only in
~/capture/metabase/.admin (mode 600). Later runs log in with that password. The session id is held in memory for this
script only (sent as X-Metabase-Session) and the session is deleted at the end.
Seeds on the bundled Sample Database: 3 users, 1 group, 3 collections (one nested), 5 saved questions (MBQL, native SQL and
a model), 2 dashboards with dashcards, 1 timeline with 2 events, 1 native-query snippet, 1 segment, bookmarks, and table /
field descriptions. Writes seed-ids.json (ids only, no secrets). Never prints the password or the session id."""
import json, os, secrets, sys, time, urllib.error, urllib.request

BASE = os.environ.get("BASE_URL", "http://127.0.0.1:3201")
DIR = os.environ.get("CAPTURE_DIR", os.path.expanduser("~/capture/metabase"))
ADMIN_FILE = os.path.join(DIR, ".admin")
EMAIL, FIRST, LAST, SITE = "rea-admin@example.test", "Rea", "Admin", "Lighthouse Rota Analytics"
SESSION = {"id": None}


def log(msg): print(f"[seed] {msg}", file=sys.stderr)


def load_or_create_admin():
    if os.path.exists(ADMIN_FILE):
        kv = dict(line.split("=", 1) for line in open(ADMIN_FILE).read().splitlines() if "=" in line)
        return kv["MB_ADMIN_PASSWORD"]
    pw = "Rea-" + secrets.token_urlsafe(18) + "-9"
    fd = os.open(ADMIN_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(f"MB_ADMIN_PASSWORD={pw}\n")  # the login email is a fixed, non-secret constant (EMAIL above)
    log(f"wrote {ADMIN_FILE} (mode 600)")
    return pw


def api(method, path, body=None, ok=(200, 201, 202, 204)):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method)
    req.add_header("Accept", "application/json")
    if data is not None: req.add_header("Content-Type", "application/json")
    if SESSION["id"]: req.add_header("X-Metabase-Session", SESSION["id"])
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            raw = r.read()
            try: return json.loads(raw) if raw else {}
            except ValueError: return {}
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:500]
        raise SystemExit(f"[seed] {method} {path} -> {e.code}: {detail}")


def wait_ready():
    for _ in range(90):
        try:
            with urllib.request.urlopen(BASE + "/api/health", timeout=5) as r:
                if json.loads(r.read()).get("status") == "ok": return
        except Exception: pass
        time.sleep(3)
    raise SystemExit("[seed] Metabase did not become ready")


wait_ready()
pw = load_or_create_admin()
props = api("GET", "/api/session/properties")
log(f"metabase {props['version']['tag']} ready at {BASE}")
if not props.get("has-user-setup"):
    res = api("POST", "/api/setup", {
        "token": props["setup-token"],
        "user": {"first_name": FIRST, "last_name": LAST, "email": EMAIL, "password": pw, "password_confirm": pw, "site_name": SITE},
        "prefs": {"site_name": SITE, "site_locale": "en", "allow_tracking": False},
    })
    SESSION["id"] = res["id"]; log("admin created through POST /api/setup")
else:
    SESSION["id"] = api("POST", "/api/session", {"username": EMAIL, "password": pw})["id"]; log("setup already done; logged in with .admin")

ids = {"users": {}, "groups": {}, "collections": {}, "cards": {}, "dashboards": {}, "timelines": {}, "timeline_events": {},
       "snippets": {}, "segments": {}, "tables": {}, "fields": {}, "database": None}

# --- Sample Database ids -------------------------------------------------------------------------------------------
dbs = api("GET", "/api/database")
dbs = dbs.get("data", dbs)
sample = next((d for d in dbs if d.get("is_sample") or d["name"] == "Sample Database"), None)
if sample is None:  # MB_LOAD_SAMPLE_CONTENT=false also skips the sample database; add it explicitly (no Examples collection)
    sample = api("POST", "/api/database/sample_database"); log("sample database added")
    for _ in range(60):  # wait for the initial sync so tables and fields have ids
        if len(api("GET", f"/api/database/{sample['id']}/metadata").get("tables", [])) >= 4: break
        time.sleep(3)
ids["database"] = sample["id"]
meta = api("GET", f"/api/database/{sample['id']}/metadata")
tables = {t["name"]: t for t in meta["tables"]}
def tid(t): return tables[t]["id"]
def fid(t, f): return next(x["id"] for x in tables[t]["fields"] if x["name"] == f)
for t in ("ORDERS", "PRODUCTS", "PEOPLE", "REVIEWS"): ids["tables"][t.lower()] = tid(t)
ids["fields"] = {"products_category": fid("PRODUCTS", "CATEGORY"), "orders_total": fid("ORDERS", "TOTAL"),
                 "people_source": fid("PEOPLE", "SOURCE")}

# Synthetic descriptions on the Sample Database metadata (the table/field rows themselves are Metabase's bundled sample data).
api("PUT", f"/api/table/{tid('PRODUCTS')}", {"description": "Granite Ledger catalogue mirror: every product the Copperfield Annex depot can requisition."})
api("PUT", f"/api/field/{fid('PRODUCTS', 'CATEGORY')}", {"description": "Shelf family used by the Saltmarsh Depot pickers (Doohickey, Gadget, Gizmo, Widget)."})
api("PUT", f"/api/field/{fid('ORDERS', 'TOTAL')}", {"description": "Ledger total in tide-tokens, tax included, as booked by Mina Okafor."})
log("table and field descriptions updated")

# --- people ---------------------------------------------------------------------------------------------------------
existing_users = {u["email"]: u for u in api("GET", "/api/user?status=all").get("data", [])}
USERS = [("Ada", "Finch", "ada.finch@example.test"), ("Rui", "Castellanos", "rui.castellanos@example.test"),
         ("Mina", "Okafor", "mina.okafor@example.test")]
for first, last, email in USERS:
    u = existing_users.get(email) or api("POST", "/api/user", {"first_name": first, "last_name": last, "email": email})
    ids["users"][email.split("@")[0]] = u["id"]
groups = {g["name"]: g for g in api("GET", "/api/permissions/group")}
g = groups.get("Night Shift Analysts") or api("POST", "/api/permissions/group", {"name": "Night Shift Analysts"})
ids["groups"]["night-shift-analysts"] = g["id"]
members = api("GET", f"/api/permissions/group/{g['id']}").get("members", [])
for key in ("ada.finch", "mina.okafor"):
    if not any(m.get("user_id") == ids["users"][key] for m in members):
        api("POST", "/api/permissions/membership", {"group_id": g["id"], "user_id": ids["users"][key]})
log(f"users {list(ids['users'])} and group Night Shift Analysts ready")

# --- collections ----------------------------------------------------------------------------------------------------
colls = {c["name"]: c for c in api("GET", "/api/collection") if isinstance(c.get("id"), int)}
def collection(name, desc, parent=None):
    c = colls.get(name) or api("POST", "/api/collection", {"name": name, "description": desc, "parent_id": parent})
    return c["id"]
ids["collections"]["granite-ledger"] = collection("Granite Ledger", "Quarry tallies and audit questions kept by Rui Castellanos.")
ids["collections"]["blue-heron-kitchen"] = collection("Blue Heron Kitchen", "Service-board questions for the tide-table menu; owner Mina Okafor.")
ids["collections"]["saltmarsh-depot"] = collection("Saltmarsh Depot", "Picker and shelf questions for the depot night shift.", ids["collections"]["granite-ledger"])
log(f"collections {ids['collections']}")

# --- saved questions (cards) ----------------------------------------------------------------------------------------
cards = {c["name"]: c for c in api("GET", "/api/card?f=all")}
def card(key, name, desc, coll, query, display="table", ctype="question", viz=None):
    c = cards.get(name) or api("POST", "/api/card", {"name": name, "description": desc, "collection_id": ids["collections"][coll],
                                                     "display": display, "type": ctype, "visualization_settings": viz or {},
                                                     "dataset_query": query})
    ids["cards"][key] = c["id"]

DB = sample["id"]
card("orders-by-category", "Copperfield Annex orders by shelf family",
     "Order count per product category, refreshed each Granite Ledger audit.", "granite-ledger",
     {"database": DB, "type": "query", "query": {"source-table": tid("ORDERS"), "aggregation": [["count"]],
      "breakout": [["field", fid("PRODUCTS", "CATEGORY"), {"source-field": fid("ORDERS", "PRODUCT_ID")}]]}}, display="bar")
card("rating-by-category", "Blue Heron Kitchen average rating per category",
     "Mean product rating by category, read out at the 22:00 kitchen handover.", "blue-heron-kitchen",
     {"database": DB, "type": "query", "query": {"source-table": tid("PRODUCTS"), "aggregation": [["avg", ["field", fid("PRODUCTS", "RATING"), None]]],
      "breakout": [["field", fid("PRODUCTS", "CATEGORY"), None]]}})
card("signup-sources", "Lighthouse Rota sign-ups by source",
     "Native SQL tally of PEOPLE by acquisition source for the rota census.", "saltmarsh-depot",
     {"database": DB, "type": "native", "native": {"query": "SELECT SOURCE, COUNT(*) AS SIGNUPS FROM PEOPLE GROUP BY SOURCE ORDER BY SIGNUPS DESC", "template-tags": {}}})
card("widget-reviews", "Saltmarsh Depot five-star review count",
     "How many reviews gave five stars; Ada Finch checks it before each tide-table reprint.", "saltmarsh-depot",
     {"database": DB, "type": "query", "query": {"source-table": tid("REVIEWS"), "aggregation": [["count"]],
      "filter": ["=", ["field", fid("REVIEWS", "RATING"), None], 5]}}, display="scalar")
card("ledger-model", "Granite Ledger order book",
     "Model over ORDERS used as the source for every ledger question.", "granite-ledger",
     {"database": DB, "type": "query", "query": {"source-table": tid("ORDERS"), "limit": 50}}, ctype="model")
log(f"cards {ids['cards']}")

# --- dashboards -----------------------------------------------------------------------------------------------------
dashes = {d["name"]: d for d in api("GET", "/api/dashboard?f=all")}
def dashboard(key, name, desc, coll, card_keys, text):
    d = dashes.get(name)
    if d is None:
        d = api("POST", "/api/dashboard", {"name": name, "description": desc, "collection_id": ids["collections"][coll]})
        dashcards = [{"id": -(i + 1), "card_id": ids["cards"][k], "row": i * 6, "col": 0, "size_x": 12, "size_y": 6,
                      "parameter_mappings": [], "visualization_settings": {}} for i, k in enumerate(card_keys)]
        dashcards.append({"id": -99, "card_id": None, "row": 0, "col": 12, "size_x": 12, "size_y": 3, "parameter_mappings": [],
                          "visualization_settings": {"virtual_card": {"name": None, "display": "text", "visualization_settings": {}, "dataset_query": {}, "archived": False}, "text": text}})
        api("PUT", f"/api/dashboard/{d['id']}", {"dashcards": dashcards, "tabs": []})
    ids["dashboards"][key] = d["id"]
dashboard("granite-ledger-overview", "Granite Ledger Overview", "Quarter-close board for the Granite Ledger audit (reference GL-2291).",
          "granite-ledger", ["orders-by-category", "widget-reviews"], "Audit lead: Rui Castellanos. Next count: the fourteenth.")
dashboard("blue-heron-service-board", "Blue Heron Kitchen Service Board", "Tide-table menu metrics for the 36-cover sittings.",
          "blue-heron-kitchen", ["rating-by-category", "signup-sources"], "Head cook: Marisol Okonkwo-Reyes. Night shift starts 22:00.")
log(f"dashboards {ids['dashboards']}")

# --- timeline and events --------------------------------------------------------------------------------------------
tls = api("GET", "/api/timeline?include=events&archived=false")
tl = next((t for t in tls if t["name"] == "Granite Ledger milestones"), None)
if tl is None:
    tl = api("POST", "/api/timeline", {"name": "Granite Ledger milestones", "description": "Audit dates and depot changes for the ledger.",
                                       "collection_id": ids["collections"]["granite-ledger"], "icon": "star", "default": False})
    tl["events"] = []
ids["timelines"]["granite-ledger-milestones"] = tl["id"]
EVENTS = [("Quarry audit signed off by Rui Castellanos", "412 blocks north quarry, 97 in the tidal yard.", "2026-09-14T00:00:00Z", "cloud"),
          ("Cart number 7 retired", "Replaced by the Copperfield Annex hand cart.", "2026-09-28T00:00:00Z", "warning")]
have = {e["name"]: e for e in tl.get("events", [])}
for i, (name, desc, ts, icon) in enumerate(EVENTS):
    e = have.get(name) or api("POST", "/api/timeline-event", {"timeline_id": tl["id"], "name": name, "description": desc, "timestamp": ts,
                                                              "timezone": "UTC", "time_matters": False, "icon": icon, "source": "collections"})
    ids["timeline_events"][f"event-{i + 1}"] = e["id"]

# --- native query snippet and segment -------------------------------------------------------------------------------
snips = {s["name"]: s for s in api("GET", "/api/native-query-snippet")}
s = snips.get("Saltmarsh Depot gizmo filter") or api("POST", "/api/native-query-snippet", {
    "name": "Saltmarsh Depot gizmo filter", "description": "Shelf filter the depot pickers paste into night-shift SQL.",
    "content": "CATEGORY = 'Gizmo' AND RATING >= 4"})
ids["snippets"]["saltmarsh-gizmo-filter"] = s["id"]
segs = {x["name"]: x for x in api("GET", "/api/segment")}
seg = segs.get("Granite Ledger large orders") or api("POST", "/api/segment", {
    "name": "Granite Ledger large orders", "description": "Orders whose ledger total is above 120 tide-tokens.", "table_id": tid("ORDERS"),
    "definition": {"database": DB, "type": "query", "query": {"source-table": tid("ORDERS"), "filter": [">", ["field", fid("ORDERS", "TOTAL"), None], 120]}}})
ids["segments"]["granite-large-orders"] = seg["id"]

# --- bookmarks (admin) ----------------------------------------------------------------------------------------------
marks = {(b["type"], b["item_id"]) for b in api("GET", "/api/bookmark")}
for typ, item in (("card", ids["cards"]["orders-by-category"]), ("dashboard", ids["dashboards"]["granite-ledger-overview"])):
    if (typ, item) not in marks: api("POST", f"/api/bookmark/{typ}/{item}")

# --- cleanup of scratch content left by an interrupted capture -------------------------------------------------------
for c in api("GET", "/api/card?f=all"):
    if str(c.get("name", "")).startswith("Rea scratch"):
        api("DELETE", f"/api/card/{c['id']}"); log(f"deleted leftover scratch card {c['id']}")

api("DELETE", "/api/session"); SESSION["id"] = None; log("seed session deleted")
json.dump(ids, open(os.path.join(DIR, "seed-ids.json"), "w"), indent=1)
log("seed-ids.json written: " + json.dumps(ids))
