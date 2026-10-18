#!/usr/bin/env python3
"""Seed the showcase Grocy with synthetic household data through its REST API (idempotent).

Grocy creates its database on the first GET / (migrations run there) with one default user, admin/admin. This script
signs in through the web form with those defaults once, renames that user to rea-admin with a password generated at run
time (kept only in ~/capture/grocy/.admin, mode 600), signs in again as rea-admin and seeds through /api with the session
cookie the web UI also uses. Seeds locations, quantity units, product groups, shopping locations, products with stock,
two shopping lists with items, chores, batteries, task categories, tasks, equipment, a recipe and two extra users.
Writes seed-ids.json (ids only, no secrets). Never prints the password."""
import base64, http.cookiejar, json, os, secrets, sys, time, urllib.error, urllib.parse, urllib.request

BASE = os.environ.get("BASE_URL", "http://127.0.0.1:3222")
DIR = os.environ.get("CAPTURE_DIR", os.path.expanduser("~/capture/grocy"))
ADMIN_FILE = os.path.join(DIR, ".admin")
USER = "rea-admin"


def log(msg): print(f"[seed] {msg}", file=sys.stderr)


def load_or_create_admin():
    if os.path.exists(ADMIN_FILE):
        kv = dict(line.split("=", 1) for line in open(ADMIN_FILE).read().splitlines() if "=" in line)
        return kv["GROCY_ADMIN_PASSWORD"]
    pw = secrets.token_urlsafe(21)
    fd = os.open(ADMIN_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(f"GROCY_ADMIN_PASSWORD={pw}\n")  # the user name is a fixed constant, not a secret
    log(f"wrote {ADMIN_FILE} (mode 600)")
    return pw


jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))


def login(username, password):
    """Sign in through the web form (the page base64-encodes the password client-side); True when the session is valid."""
    jar.clear()
    data = urllib.parse.urlencode({"username": username, "password_base64": base64.b64encode(password.encode()).decode()}).encode()
    req = urllib.request.Request(BASE + "/login", data=data, method="POST")
    try:
        with opener.open(req, timeout=30) as r:
            final = r.geturl()
    except urllib.error.HTTPError as e:
        raise SystemExit(f"[seed] login form -> {e.code}")
    return "/login" not in urllib.parse.urlparse(final).path


def api(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + "/api" + path, data=data, method=method)
    req.add_header("Accept", "application/json")
    if data is not None: req.add_header("Content-Type", "application/json")
    try:
        with opener.open(req, timeout=30) as r:
            raw = r.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:400]
        raise SystemExit(f"[seed] {method} /api{path} -> {e.code}: {detail}")


def wait_ready():
    for _ in range(120):
        try:
            with urllib.request.urlopen(BASE + "/login", timeout=5) as r:
                if r.status == 200: break
        except Exception: pass
        time.sleep(2)
    else:
        raise SystemExit("[seed] Grocy did not become ready")
    # The first GET / runs the schema migrations (the login form answers 500 before that); it then redirects to /login.
    with opener.open(BASE + "/", timeout=60) as r: r.read()


wait_ready()
pw = load_or_create_admin()
if login(USER, pw):
    log("signed in as rea-admin (already renamed)")
else:
    if not login("admin", "admin"):
        raise SystemExit("[seed] neither rea-admin nor the default admin can sign in")
    users = api("GET", "/users")
    default = next(u for u in users if u["username"] == "admin")
    api("PUT", f"/users/{default['id']}", {"username": USER, "first_name": "Rea", "last_name": "Admin", "password": pw})
    log("default admin renamed to rea-admin with a generated password")
    if not login(USER, pw): raise SystemExit("[seed] rea-admin cannot sign in after the rename")
    if login("admin", "admin"): raise SystemExit("[seed] the default admin/admin still signs in")
    login(USER, pw)
info = api("GET", "/system/info"); log(f"grocy {info['grocy_version']['Version']} ready at {BASE}")

ids = {}


def upsert(entity, obj, key="name"):
    """Create the object unless one with the same key exists; returns its id."""
    rows = api("GET", f"/objects/{entity}")
    cur = next((r for r in rows if r.get(key) == obj[key]), None)
    if cur is None:
        oid = int(api("POST", f"/objects/{entity}", obj)["created_object_id"]); log(f"{entity}: created {obj[key]!r} ({oid})")
    else:
        oid = cur["id"]
    ids.setdefault(entity, {})[obj[key]] = oid
    return oid


def rename(entity, oid, obj):
    api("PUT", f"/objects/{entity}/{oid}", obj); ids.setdefault(entity, {})[obj["name"]] = oid


# Remove scratch products left behind by an interrupted capture so every capture starts from the same state.
for p in api("GET", "/objects/products"):
    if p["name"].startswith("Rea Scratch"):
        api("DELETE", f"/objects/products/{p['id']}"); log(f"removed leftover scratch product {p['id']}")

# Two more household members.
for uname, first, last in (("afinch", "Ada", "Finch"), ("rcastellanos", "Rui", "Castellanos")):
    if not any(u["username"] == uname for u in api("GET", "/users")):
        api("POST", "/users", {"username": uname, "first_name": first, "last_name": last, "password": secrets.token_urlsafe(18)})
        log(f"user {uname} created")
users = {u["username"]: u["id"] for u in api("GET", "/users")}
ids["users"] = users

# The defaults Grocy creates (location "Fridge", shopping list "Shopping list") get synthetic names.
fridge = next((l for l in api("GET", "/objects/locations") if l["name"] in ("Fridge", "Saltmarsh Depot Cold Room")), None)
if fridge:
    rename("locations", fridge["id"], {"name": "Saltmarsh Depot Cold Room", "description": "Walk-in cold room behind the depot loading bay, kept at 3 degrees.", "is_freezer": 0})
loc_cold = ids["locations"]["Saltmarsh Depot Cold Room"]
loc_larder = upsert("locations", {"name": "Copperfield Annex Larder", "description": "Dry larder on the annex mezzanine, shelves A to F."})
loc_lockers = upsert("locations", {"name": "Granite Ledger Lockers", "description": "Steel lockers beside the quarry office for lamp stores."})

qu_piece = next(q["id"] for q in api("GET", "/objects/quantity_units") if q["name"] == "Piece")
qu_pack = next(q["id"] for q in api("GET", "/objects/quantity_units") if q["name"] == "Pack")
qu_crate = upsert("quantity_units", {"name": "Crate", "name_plural": "Crates", "description": "Wooden crate of twelve, stamped with the depot mark."})
qu_tin = upsert("quantity_units", {"name": "Tin", "name_plural": "Tins", "description": "Sealed tin as delivered by the co-op cart."})
ids["quantity_units"].update({"Piece": qu_piece, "Pack": qu_pack})

pg_rations = upsert("product_groups", {"name": "Tide Rations", "description": "Shelf-stable food for the night shift of the Lighthouse Rota."})
pg_lamp = upsert("product_groups", {"name": "Lamp Supplies", "description": "Wicks, oil and mantles for the north lamp."})

sl_market = upsert("shopping_locations", {"name": "Blue Heron Kitchen Market", "description": "Quayside stall run by Mina Okafor, open on Tuesdays."})
sl_coop = upsert("shopping_locations", {"name": "Lighthouse Rota Co-op", "description": "Members' co-op on Granite Point that delivers on Fridays."})

PRODUCTS = [
    ("Smoked Kelp Broth", "Jarred broth from Blue Heron Kitchen for the 22:00 shift change.", loc_cold, qu_tin, pg_rations, sl_market, 6, 14),
    ("Granite Salt Flakes", "Hand-raked salt from the Saltmarsh Depot pans, batch SD-118.", loc_larder, qu_pack, pg_rations, sl_coop, 2, 365),
    ("Heron Rye Crackers", "Twice-baked rye crackers packed by Tomas Vey.", loc_larder, qu_pack, pg_rations, sl_market, 4, 60),
    ("Lamp Wick Bundle", "Cotton wicks cut to 14 cm for the north lamp.", loc_lockers, qu_piece, pg_lamp, sl_coop, 10, 0),
    ("Copperfield Lamp Oil", "Paraffin lamp oil in crates; the winter budget is 180 litres.", loc_lockers, qu_crate, pg_lamp, sl_coop, 3, 0),
]
for name, desc, loc, qu, pg, sl, mins, bbd in PRODUCTS:
    upsert("products", {"name": name, "description": desc, "location_id": loc, "qu_id_purchase": qu, "qu_id_stock": qu,
                        "qu_id_consume": qu, "qu_id_price": qu, "product_group_id": pg, "shopping_location_id": sl,
                        "min_stock_amount": mins, "default_best_before_days": bbd})
P = ids["products"]

# Stock: one purchase per product, only when the product has no stock yet.
STOCK = [("Smoked Kelp Broth", 8, 3.40, "2026-11-30", loc_cold, sl_market, "Delivered by Mina Okafor in a cool box"),
         ("Granite Salt Flakes", 5, 2.15, "2027-09-30", loc_larder, sl_coop, "Batch SD-118 from the east pans"),
         ("Heron Rye Crackers", 3, 4.75, "2026-12-15", loc_larder, sl_market, "Packed by Tomas Vey on Monday"),
         ("Lamp Wick Bundle", 24, 0.60, "2999-12-31", loc_lockers, sl_coop, "Cut to 14 cm, two dozen"),
         ("Copperfield Lamp Oil", 2, 38.00, "2999-12-31", loc_lockers, sl_coop, "Crates 7 and 8 from the co-op")]
for name, amount, price, bbd, loc, sl, note in STOCK:
    if not api("GET", f"/stock/products/{P[name]}/entries"):
        api("POST", f"/stock/products/{P[name]}/add", {"amount": amount, "price": price, "best_before_date": bbd, "location_id": loc,
                                                      "shopping_location_id": sl, "transaction_type": "purchase", "note": note})
        log(f"stock added for {name}")

default_list = next((s for s in api("GET", "/objects/shopping_lists") if s["name"] in ("Shopping list", "Saltmarsh Depot Restock")), None)
if default_list:
    rename("shopping_lists", default_list["id"], {"name": "Saltmarsh Depot Restock", "description": "Weekly restock for the depot cold room and larder."})
list_restock = ids["shopping_lists"]["Saltmarsh Depot Restock"]
list_night = upsert("shopping_lists", {"name": "Lighthouse Rota Night Shift", "description": "Supplies the night crew asks for before the winter rota."})
ITEMS = [(list_restock, P["Heron Rye Crackers"], 4, "Ask Mina Okafor for the caraway rye"),
         (list_restock, P["Smoked Kelp Broth"], 6, "Only the small tins fit the cold room shelf"),
         (list_night, P["Copperfield Lamp Oil"], 2, "Two crates before the winter shift plan starts"),
         (list_night, None, 1, "Spare mantle for the north lamp")]
existing_items = api("GET", "/objects/shopping_list")
for lst, prod, amount, note in ITEMS:
    cur = next((i for i in existing_items if i.get("note") == note), None)
    if cur is None:
        body = {"shopping_list_id": lst, "amount": amount, "note": note} | ({"product_id": prod} if prod else {})
        cur = {"id": int(api("POST", "/objects/shopping_list", body)["created_object_id"])}; log(f"shopping list item {note!r} created")
    ids.setdefault("shopping_list", {})[note] = cur["id"]

CHORES = [("Polish the Lighthouse Lens", "Polish the lens with chamois before dusk, gallery side first.", "dynamic-regular", 7),
          ("Rotate the Kelp Barrels", "Turn each kelp barrel a quarter turn so the brine settles.", "dynamic-regular", 3),
          ("Sweep the Copperfield Annex", "Sweep the annex mezzanine and log any loose crates.", "manually", 0)]
for name, desc, ptype, days in CHORES:
    upsert("chores", {"name": name, "description": desc, "period_type": ptype, "period_days": days, "assignment_type": "no-assignment",
                      "track_date_only": 0, "rollover": 0})
C = ids["chores"]
if not api("GET", f"/chores/{C['Polish the Lighthouse Lens']}").get("last_tracked"):
    api("POST", f"/chores/{C['Polish the Lighthouse Lens']}/execute", {"tracked_time": "2026-10-14 18:30:00", "done_by": users["afinch"]})
    log("chore execution tracked")

BATTERIES = [("Foghorn Remote Cell", "Rechargeable cell for the foghorn remote on the gallery.", "Foghorn remote, gallery level", 30),
             ("Tide Gauge Pack", "Lithium pack powering the tide gauge at Saltmarsh Depot.", "Tide gauge, east jetty", 90)]
for name, desc, used_in, days in BATTERIES:
    upsert("batteries", {"name": name, "description": desc, "used_in": used_in, "charge_interval_days": days})
B = ids["batteries"]
if not api("GET", f"/batteries/{B['Foghorn Remote Cell']}").get("last_charged"):
    api("POST", f"/batteries/{B['Foghorn Remote Cell']}/charge", {"tracked_time": "2026-10-09 07:15:00"}); log("battery charge tracked")

tc_rounds = upsert("task_categories", {"name": "Depot Rounds", "description": "Weekly rounds of the Saltmarsh Depot stores."})
tc_lamp = upsert("task_categories", {"name": "Lamp Watch", "description": "Jobs that keep the north lamp burning through winter."})
upsert("tasks", {"name": "Recount the Granite Ledger crates", "description": "Recount crates on shelf C against ledger reference GL-2291.",
                 "due_date": "2026-11-02", "category_id": tc_rounds, "assigned_to_user_id": users["afinch"]})
upsert("tasks", {"name": "Order winter lamp mantles", "description": "Order six mantles from the Lighthouse Rota Co-op before the first frost.",
                 "due_date": "2026-11-15", "category_id": tc_lamp, "assigned_to_user_id": users["rcastellanos"]})

upsert("equipment", {"name": "Copperfield Annex Dehydrator", "description": "Four-tray kelp dehydrator; the manual is kept in the annex office."})
upsert("equipment", {"name": "Saltmarsh Depot Chest Scale", "description": "Platform scale for weighing salt sacks, calibrated each spring."})

rid = upsert("recipes", {"name": "Tide-Table Kelp Stew", "description": "Kelp broth stew for the night shift, ready in forty minutes.", "base_servings": 4, "desired_servings": 4})
if not [x for x in api("GET", "/objects/recipes_pos") if x["recipe_id"] == rid]:
    api("POST", "/objects/recipes_pos", {"recipe_id": rid, "product_id": P["Smoked Kelp Broth"], "amount": 2, "qu_id": qu_tin, "note": "Warm the broth slowly"})
    api("POST", "/objects/recipes_pos", {"recipe_id": rid, "product_id": P["Granite Salt Flakes"], "amount": 1, "qu_id": qu_pack, "note": "A pinch only"})
    log("recipe positions created")

json.dump(ids, open(os.path.join(DIR, "seed-ids.json"), "w"), indent=1)
log("seed-ids.json written: " + json.dumps({k: list(v.values()) for k, v in ids.items()}))
