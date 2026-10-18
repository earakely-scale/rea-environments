#!/usr/bin/env python3
"""Seed the showcase Homebox with synthetic content through its REST API /api/v1 (idempotent).

Registers the user "Rea Admin" (rea-admin@example.test) with a password generated at run time and kept only in
~/capture/homebox/.admin (mode 600); a bearer token is created for this script only (login) and revoked at the end (logout).
Renames the collection (group), removes the default tags and locations that registration creates, then seeds 2 entity types,
5 tags (one nested), 4 locations (one nested), 6 items with custom fields, prices, serials and notes, 3 maintenance entries
and 1 item template. Writes seed-ids.json (ids only, no secrets). Never prints a password or a token."""
import json, os, secrets, sys, time, urllib.error, urllib.parse, urllib.request

BASE = os.environ.get("BASE_URL", "http://127.0.0.1:3208")
DIR = os.environ.get("CAPTURE_DIR", os.path.expanduser("~/capture/homebox"))
ADMIN_FILE = os.path.join(DIR, ".admin")
EMAIL, NAME = "rea-admin@example.test", "Rea Admin"
TOKEN = None
DEFAULT_TAGS = {"Appliances", "Electronics", "Furniture", "IOT", "Home Decor", "Office", "Tools", "Kitchen", "Outdoor", "Toys", "Books"}
DEFAULT_LOCATIONS = {"Attic", "Basement", "Bathroom", "Bedroom", "Garage", "Kitchen", "Living Room", "Office", "Patio", "Yard", "Closet", "Laundry"}


def log(msg): print(f"[seed] {msg}", file=sys.stderr)


def load_or_create_admin():
    if os.path.exists(ADMIN_FILE):
        kv = dict(line.split("=", 1) for line in open(ADMIN_FILE).read().splitlines() if "=" in line)
        return kv["HOMEBOX_ADMIN_PASSWORD"], False
    pw = secrets.token_urlsafe(21)
    fd = os.open(ADMIN_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(f"HOMEBOX_ADMIN_PASSWORD={pw}\n")  # the email is not a secret and appears in API replies
    log(f"wrote {ADMIN_FILE} (mode 600)")
    return pw, True


def api(method, path, body=None, ok=()):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + "/api/v1" + path, data=data, method=method)
    req.add_header("Accept", "application/json")
    if data is not None: req.add_header("Content-Type", "application/json")
    if TOKEN: req.add_header("Authorization", TOKEN)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            text = r.read()
            try: return (json.loads(text) if text else {}), r.status
            except ValueError: return {}, r.status
    except urllib.error.HTTPError as e:
        if e.code in ok: return None, e.code
        detail = e.read().decode(errors="replace")[:400]
        raise SystemExit(f"[seed] {method} {path} -> {e.code}: {detail}")


def wait_ready():
    for _ in range(120):
        try:
            with urllib.request.urlopen(BASE + "/api/v1/status", timeout=5) as r:
                if r.status == 200: return json.loads(r.read())
        except Exception: pass
        time.sleep(2)
    raise SystemExit("[seed] Homebox did not become ready")


status = wait_ready(); log(f"homebox {status['build']['version']} ready at {BASE}")
pw, new = load_or_create_admin()
if new:
    api("POST", "/users/register", {"email": EMAIL, "name": NAME, "password": pw}); log("user registered")
login, _ = api("POST", "/users/login", {"username": EMAIL, "password": pw, "stayLoggedIn": False})
TOKEN = login["token"]; log("seed login ok (token kept in memory only)")

ids = {"group": None, "entity_types": {}, "tags": {}, "locations": {}, "items": {}, "maintenance": {}, "templates": {}}
grp, _ = api("PUT", "/groups", {"name": "Copperfield Annex Stores", "currency": "EUR"}); ids["group"] = grp["id"]
log("collection renamed to Copperfield Annex Stores (EUR)")


def all_entities():
    res, _ = api("GET", "/entities?page=1&pageSize=500")
    return {e["name"]: e for e in res["items"]}


# Remove the defaults registration creates, and scratch items left behind by an interrupted capture.
for t in api("GET", "/tags")[0]:
    if t["name"] in DEFAULT_TAGS: api("DELETE", f"/tags/{t['id']}")
tree, _ = api("GET", "/entities/tree")
for node in tree:
    if node["name"] in DEFAULT_LOCATIONS and not node.get("children"): api("DELETE", f"/entities/{node['id']}")
for name, e in all_entities().items():
    if name.startswith("Rea scratch"): api("DELETE", f"/entities/{e['id']}"); log(f"removed leftover {name}")
log("default tags and locations removed")

types = {t["name"]: t for t in api("GET", "/entity-types")[0]}
for name, is_loc, icon in [("Storage Room", True, "mdi-warehouse"), ("Spare Part", False, "mdi-cog")]:
    if name not in types:
        cur, _ = api("POST", "/entity-types", {"name": name, "isLocation": is_loc, "icon": icon}); types[name] = cur; log(f"entity type {name} created")
ids["entity_types"] = {k: v["id"] for k, v in types.items()}
TY = ids["entity_types"]

TAGS = [("Lighthouse Rota", "#d4a017", "Gear signed out for the lighthouse night shift.", None),
        ("Calibration Due", "#c0392b", "Needs recalibration before the spring census.", None),
        ("Kitchen Brass", "#b8860b", "Brassware and copper from the Blue Heron Kitchen.", None),
        ("Spare Parts", "#5d6d7e", "Replacement parts kept in reserve at the depot.", None),
        ("Lens Spares", "#2e86c1", "Spare optics for the Fresnel lens.", "Spare Parts")]
have = {t["name"]: t for t in api("GET", "/tags")[0]}
for name, color, desc, parent in TAGS:
    if name not in have:
        body = {"name": name, "color": color, "description": desc}
        if parent: body["parentId"] = ids["tags"][parent]
        have[name], _ = api("POST", "/tags", body); log(f"tag {name} created")
    ids["tags"][name] = have[name]["id"]
TG = ids["tags"]

LOCATIONS = [
    ("Saltmarsh Depot", "Location", None, "Tin-roofed depot behind the dunes; the key is held by Tomas Vey."),
    ("Granite Ledger Vault", "Storage Room", "Saltmarsh Depot", "Locked stone room under the depot where the audit ledgers are kept."),
    ("Copperfield Annex Workshop", "Location", None, "Bench room on the annex ground floor, run by Mina Okafor."),
    ("Blue Heron Kitchen Pantry", "Storage Room", None, "Cold pantry next to the pass; brassware lives on the top shelf."),
]
ents = all_entities()
for name, ty, parent, desc in LOCATIONS:
    cur = ents.get(name)
    if cur is None:
        body = {"name": name, "description": desc, "entityTypeId": TY[ty]}
        if parent: body["parentId"] = ids["locations"][parent]
        cur, _ = api("POST", "/entities", body); log(f"location {name} created")
    ids["locations"][name] = cur["id"]
L = ids["locations"]

ITEMS = [
    {"name": "Fresnel Lens Polishing Kit", "type": "Item", "parent": "Saltmarsh Depot", "quantity": 1,
     "description": "Chamois cloths, rouge paste and a soft brush for the second-order lens.",
     "manufacturer": "Finch and Vey Optics", "modelNumber": "FLK-412", "serialNumber": "LR-0097-SD",
     "purchaseFrom": "Granite Point Chandlery", "purchasePrice": 184.5, "purchaseDate": "2025-11-03T00:00:00Z",
     "notes": "Ada Finch signs the kit out for the 22:00 shift.", "warrantyDetails": "One year on the brush heads",
     "insured": True, "tags": ["Lighthouse Rota", "Lens Spares"],
     "fields": [{"type": "text", "name": "Lens Grade", "textValue": "Second-order"}, {"type": "number", "name": "Cloth Count", "numberValue": 12}]},
    {"name": "Tide Gauge Logger", "type": "Item", "parent": "Granite Ledger Vault", "quantity": 1,
     "description": "Pressure logger that records the tide every six minutes.",
     "manufacturer": "Saltmarsh Instrument Works", "modelNumber": "TGL-7", "serialNumber": "TG-2291-GL",
     "purchaseFrom": "Copperfield Annex Surplus", "purchasePrice": 312.0, "purchaseDate": "2025-06-21T00:00:00Z",
     "notes": "Battery swapped in August; datum checked by Rui Castellanos.", "warrantyDetails": "Two years, seals excluded",
     "insured": True, "tags": ["Calibration Due", "Lighthouse Rota"],
     "fields": [{"type": "text", "name": "Datum", "textValue": "Granite Point Chart Datum"}, {"type": "boolean", "name": "Waterproofed", "booleanValue": True}]},
    {"name": "Copper Stockpot 40 L", "type": "Item", "parent": "Blue Heron Kitchen Pantry", "quantity": 2,
     "description": "Tin-lined stockpots used for the smoked kelp broth.",
     "manufacturer": "Heron Forge", "modelNumber": "CSP-40", "serialNumber": "BH-0036-KP",
     "purchaseFrom": "Blue Heron Kitchen Supply", "purchasePrice": 96.75, "purchaseDate": "2024-09-12T00:00:00Z",
     "notes": "Marisol keeps the lids on the lower rack.", "warrantyDetails": "",
     "insured": False, "tags": ["Kitchen Brass"],
     "fields": [{"type": "text", "name": "Lining", "textValue": "Tin"}, {"type": "number", "name": "Capacity Litres", "numberValue": 40}]},
    {"name": "Quarry Tally Counter", "type": "Item", "parent": "Copperfield Annex Workshop", "quantity": 3,
     "description": "Four-digit hand counters used for the quarterly stone count.",
     "manufacturer": "Ledgerline Tools", "modelNumber": "QTC-412", "serialNumber": "GL-0412-QT",
     "purchaseFrom": "Granite Point Chandlery", "purchasePrice": 22.4, "purchaseDate": "2026-01-14T00:00:00Z",
     "notes": "Counter three skips on the hundreds wheel.", "warrantyDetails": "",
     "insured": False, "tags": ["Calibration Due"],
     "fields": [{"type": "text", "name": "Assigned To", "textValue": "Rui Castellanos"}]},
    {"name": "Brass Lamp Wick Trimmer", "type": "Item", "parent": "Copperfield Annex Workshop", "quantity": 1,
     "description": "Scissor trimmer with a catch tray for the lamp wicks.",
     "manufacturer": "Heron Forge", "modelNumber": "WT-22", "serialNumber": "CA-0022-WT",
     "purchaseFrom": "Copperfield Annex Surplus", "purchasePrice": 41.0, "purchaseDate": "2025-03-30T00:00:00Z",
     "notes": "Blade sharpened by Mina Okafor in March.", "warrantyDetails": "",
     "insured": False, "tags": ["Lighthouse Rota", "Kitchen Brass"],
     "fields": [{"type": "text", "name": "Blade Steel", "textValue": "Carbon"}]},
    {"name": "Spare Lamp Mantle Pack", "type": "Spare Part", "parent": "Saltmarsh Depot", "quantity": 24,
     "description": "Silk mantles for the paraffin lamp, boxed in dozens.",
     "manufacturer": "Finch and Vey Optics", "modelNumber": "MNT-24", "serialNumber": "SD-0024-MP",
     "purchaseFrom": "Granite Point Chandlery", "purchasePrice": 58.0, "purchaseDate": "2026-02-02T00:00:00Z",
     "notes": "Reorder when fewer than six remain.", "warrantyDetails": "",
     "insured": False, "tags": ["Spare Parts"],
     "fields": [{"type": "text", "name": "Mantle Size", "textValue": "Number 3 silk"}]},
]
ents = all_entities()
for it in ITEMS:
    cur = ents.get(it["name"])
    if cur is None:
        cur, _ = api("POST", "/entities", {"name": it["name"], "entityTypeId": TY[it["type"]], "parentId": L[it["parent"]]})
        log(f"item {it['name']} created")
    full = {k: it[k] for k in ("name", "description", "quantity", "manufacturer", "modelNumber", "serialNumber", "purchaseFrom",
                               "purchasePrice", "purchaseDate", "notes", "warrantyDetails", "insured", "fields")}
    full.update({"id": cur["id"], "entityTypeId": TY[it["type"]], "parentId": L[it["parent"]], "tagIds": [TG[t] for t in it["tags"]],
                 "archived": False, "lifetimeWarranty": False})
    api("PUT", f"/entities/{cur['id']}", full)  # PUT replaces the whole entity, so every field is sent
    ids["items"][it["name"]] = cur["id"]
I = ids["items"]

MAINT = [("Tide Gauge Logger", {"name": "Recalibrate tide gauge", "description": "Zero against the Granite Point benchmark before the spring census.", "scheduledDate": "2026-11-14", "cost": "60"}),
         ("Copper Stockpot 40 L", {"name": "Re-tin the lining", "description": "Fresh tin lining after the summer service.", "completedDate": "2026-08-20", "cost": "38"}),
         ("Fresnel Lens Polishing Kit", {"name": "Replace chamois cloths", "description": "Twelve new cloths from the chandlery.", "scheduledDate": "2026-12-01", "cost": "15.5"})]
for item, entry in MAINT:
    cur = next((m for m in api("GET", f"/entities/{I[item]}/maintenance?status=both")[0] if m["name"] == entry["name"]), None)
    if cur is None: cur, _ = api("POST", f"/entities/{I[item]}/maintenance", entry); log(f"maintenance {entry['name']} created")
    ids["maintenance"][entry["name"]] = cur["id"]

TPL = {"name": "Lighthouse Spare Part", "description": "Template for parts kept for the lamp room.", "defaultName": "Lamp room spare",
       "defaultManufacturer": "Finch and Vey Optics", "defaultQuantity": 1, "defaultLocationId": L["Saltmarsh Depot"],
       "defaultTagIds": [TG["Spare Parts"]], "notes": "Count spares on the first Monday of the month.",
       "fields": [{"type": "text", "name": "Shelf", "textValue": "Depot shelf B"}]}
cur = next((t for t in api("GET", "/templates")[0] if t["name"] == TPL["name"]), None)
if cur is None: cur, _ = api("POST", "/templates", TPL); log("template created")
ids["templates"][TPL["name"]] = cur["id"]

api("POST", "/users/logout"); TOKEN = None; log("seed token revoked")
json.dump(ids, open(os.path.join(DIR, "seed-ids.json"), "w"), indent=1)
log("seed-ids.json written: " + json.dumps(ids))
