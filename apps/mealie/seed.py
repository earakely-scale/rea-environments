#!/usr/bin/env python3
"""Seed the showcase Mealie with synthetic content through its REST API (/api, idempotent).

First replaces the documented default admin password (changeme@example.com / MyPassword) with the one up.sh generated into
~/capture/mealie/.admin (mode 600) and renames the account to rea-admin (Rea Admin, rea-admin@example.test); renames the group
to "Lighthouse Rota" and the household to "Blue Heron Kitchen"; creates the crew account mina-okafor (password also in .admin).
Then: 3 categories, 4 tags, 2 tools, 3 foods, 2 units, 5 recipes written from JSON (POST /api/recipes for the slug, then PUT of
the full recipe with description, yield, times, ingredients, instructions, notes, categories, tags and tools; no URL
scraping), 2 cookbooks with query filters, 2 shopping lists with items, 3 meal-plan entries, and 2 comments by Mina.
Writes seed-ids.json (ids and slugs only). Never prints a credential."""
import json, os, sys, time, urllib.error, urllib.parse, urllib.request, uuid

BASE = os.environ.get("BASE_URL", "http://127.0.0.1:3212")
DIR = os.environ.get("CAPTURE_DIR", os.path.expanduser("~/capture/mealie"))
adm = dict(l.split("=", 1) for l in open(os.path.join(DIR, ".admin")).read().splitlines() if "=" in l)
DEFAULT_EMAIL, DEFAULT_PW = "changeme@example.com", "MyPassword"   # Mealie's documented first-run admin, replaced below
EMAIL = "rea-admin@example.test"
TOK = {}

def log(msg): print(f"[seed] {msg}", file=sys.stderr)

def api(method, path, body=None, ok=(), who="admin"):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method)
    req.add_header("Accept", "application/json")
    if data is not None: req.add_header("Content-Type", "application/json")
    if who in TOK: req.add_header("Authorization", "Bearer " + TOK[who])
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read(); return (json.loads(raw) if raw else None), r.status
    except urllib.error.HTTPError as e:
        if e.code in ok: return None, e.code
        raise SystemExit(f"[seed] {method} {path} -> {e.code}: {e.read().decode(errors='replace')[:400]}")

def login(user, pw):
    data = urllib.parse.urlencode({"username": user, "password": pw, "remember_me": "false"}).encode()
    try:
        with urllib.request.urlopen(urllib.request.Request(BASE + "/api/auth/token", data=data, method="POST"), timeout=30) as r:
            return json.loads(r.read())["access_token"]
    except urllib.error.HTTPError as e:
        if e.code in (401, 403): return None
        raise SystemExit(f"[seed] login -> {e.code}")

for _ in range(120):
    try:
        with urllib.request.urlopen(BASE + "/api/app/about", timeout=5) as r: about = json.loads(r.read()); break
    except Exception: time.sleep(2)
else: raise SystemExit("[seed] Mealie did not become ready")
log(f"mealie {about['version']} ready at {BASE}")

# --- admin: replace the default password first, then rename ---
TOK["admin"] = login(EMAIL, adm["MEALIE_ADMIN_PASSWORD"]) or login(DEFAULT_EMAIL, adm["MEALIE_ADMIN_PASSWORD"])
if not TOK["admin"]:
    TOK["admin"] = login(DEFAULT_EMAIL, DEFAULT_PW)
    if not TOK["admin"]: raise SystemExit("[seed] neither the configured nor the default admin can log in")
    api("PUT", "/api/users/password", {"currentPassword": DEFAULT_PW, "newPassword": adm["MEALIE_ADMIN_PASSWORD"]})
    log("default admin password replaced")
    TOK["admin"] = login(DEFAULT_EMAIL, adm["MEALIE_ADMIN_PASSWORD"])   # the password change revokes the old token
me, _ = api("GET", "/api/users/self")
if me["username"] != "rea-admin" or me["email"] != EMAIL:
    api("PUT", f"/api/users/{me['id']}", {**{k: me[k] for k in ("id", "admin", "group", "household", "advanced", "canInvite", "canManage", "canManageHousehold", "canOrganize", "authMethod") if k in me},
                                         "username": "rea-admin", "fullName": "Rea Admin", "email": EMAIL})
    TOK["admin"] = login(EMAIL, adm["MEALIE_ADMIN_PASSWORD"]); me, _ = api("GET", "/api/users/self"); log("admin renamed to rea-admin")
grp, _ = api("GET", "/api/groups/self"); hh, _ = api("GET", "/api/households/self")
if grp["name"] != "Lighthouse Rota":
    api("PUT", f"/api/admin/groups/{grp['id']}", {"id": grp["id"], "name": "Lighthouse Rota"}); log("group renamed")
if hh["name"] != "Blue Heron Kitchen":
    api("PUT", f"/api/admin/households/{hh['id']}", {"id": hh["id"], "groupId": grp["id"], "name": "Blue Heron Kitchen"}); log("household renamed")
TOK["admin"] = login(EMAIL, adm["MEALIE_ADMIN_PASSWORD"]); me, _ = api("GET", "/api/users/self")
ids = {"version": about["version"], "users": {"rea-admin": me["id"]}, "group": grp["id"], "household": hh["id"], "categories": {}, "tags": {},
       "tools": {}, "foods": {}, "units": {}, "recipes": {}, "cookbooks": {}, "shopping_lists": {}, "shopping_items": {}, "mealplans": {}, "comments": {}}

# --- crew account ---
users, _ = api("GET", "/api/admin/users?perPage=50")
if not any(u["username"] == "mina-okafor" for u in users["items"]):
    api("POST", "/api/admin/users", {"username": "mina-okafor", "fullName": "Mina Okafor", "email": "mina.okafor@example.test",
        "password": adm["MEALIE_CREW_PASSWORD"], "admin": False, "group": me["group"], "household": me["household"]}); log("user mina-okafor created")
TOK["mina"] = login("mina.okafor@example.test", adm["MEALIE_CREW_PASSWORD"])
ids["users"]["mina-okafor"] = api("GET", "/api/users/self", who="mina")[0]["id"]

# Remove scratch recipes left by an interrupted capture so every capture starts from the same state.
for r in api("GET", "/api/recipes?search=rea%20scratch&perPage=50")[0]["items"]:
    api("DELETE", f"/api/recipes/{r['slug']}"); log(f"removed leftover scratch recipe {r['slug']}")

def organizer(kind, name):
    # list-and-match: GET /api/organizers/tags/slug/<missing> answers 500 rather than 404 in this version
    cur = next((x for x in api("GET", f"/api/organizers/{kind}?perPage=100")[0]["items"] if x["name"] == name), None)
    if cur is None: cur, _ = api("POST", f"/api/organizers/{kind}", {"name": name}); log(f"{kind} {name} created")
    return cur
CATS = ["Tide-Table Suppers", "Quarry Lunches", "Night-Shift Snacks"]
TAGS = ["smoked-kelp", "one-pot", "night-shift", "foraged"]
TOOLS = ["Cast-iron kettle", "Kelp smoker"]
cat = {n: organizer("categories", n) for n in CATS}; tag = {n: organizer("tags", n) for n in TAGS}; tool = {n: organizer("tools", n) for n in TOOLS}
for d, src in (("categories", cat), ("tags", tag), ("tools", tool)): ids[d] = {n: o["id"] for n, o in src.items()}

def find_by_name(path, name):
    items = api("GET", f"{path}?perPage=100")[0]["items"]
    return next((x for x in items if x["name"] == name), None)
FOODS = [("dried kelp", "Bladderwrack dried on the Saltmarsh Depot racks."), ("pearl barley", "Polished barley for the lamp-watch stew."),
         ("samphire", "Marsh samphire picked at low tide behind the depot.")]
for name, desc in FOODS:
    f = find_by_name("/api/foods", name) or api("POST", "/api/foods", {"name": name, "description": desc})[0]; ids["foods"][name] = f["id"]
UNITS = [("crate", "cr", "A Saltmarsh Depot supply crate."), ("ladle", "ld", "The Blue Heron Kitchen serving ladle.")]
for name, abbr, desc in UNITS:
    u = find_by_name("/api/units", name) or api("POST", "/api/units", {"name": name, "abbreviation": abbr, "description": desc})[0]; ids["units"][name] = u["id"]

RECIPES = [
 {"name": "Smoked Kelp Broth", "description": "Blue Heron Kitchen's spring-tide starter, ladled from one cast-iron kettle.",
  "recipeYield": "36 bowls", "recipeServings": 36, "prepTime": "20 minutes", "performTime": "1 hour 30 minutes", "totalTime": "1 hour 50 minutes",
  "ingredients": ["2 kg dried kelp, smoked over driftwood", "6 litres fish stock", "4 leeks, sliced thin", "1 tablespoon cracked pepper"],
  "steps": ["Soak the dried kelp for one hour.", "Simmer the kelp with the leeks for ninety minutes.", "Ladle at 22:00 for the night shift."],
  "notes": [("Service", "Serve to the Lighthouse Rota night shift at 22:00.")], "cats": ["Tide-Table Suppers"], "tags": ["smoked-kelp", "one-pot"], "tools": ["Cast-iron kettle", "Kelp smoker"]},
 {"name": "Granite Ledger Oat Bars", "description": "Dense oat bars packed for the north quarry count.",
  "recipeYield": "24 bars", "recipeServings": 24, "prepTime": "15 minutes", "performTime": "35 minutes", "totalTime": "50 minutes",
  "ingredients": ["600 g rolled oats", "200 g honey", "150 g butter", "100 g dried apricots, chopped"],
  "steps": ["Melt the butter with the honey.", "Fold in the oats and apricots.", "Press into a tray and bake for 35 minutes."],
  "notes": [("Packing", "Wrap in pairs; one pair per counter on the tidal-yard shift.")], "cats": ["Quarry Lunches"], "tags": ["one-pot"], "tools": []},
 {"name": "Lamp-Watch Barley Stew", "description": "Kept warm on the gallery stove from 22:00 to 06:00.",
  "recipeYield": "12 bowls", "recipeServings": 12, "prepTime": "25 minutes", "performTime": "2 hours", "totalTime": "2 hours 25 minutes",
  "ingredients": ["400 g pearl barley", "3 carrots, diced", "2 onions, diced", "3 litres vegetable stock"],
  "steps": ["Sweat the onions and carrots.", "Add the barley and stock and simmer for two hours.", "Hold on the gallery stove until the 06:00 handover."],
  "notes": [("Handover", "Whoever hands over at 06:00 scrapes the pot.")], "cats": ["Tide-Table Suppers"], "tags": ["night-shift", "one-pot"], "tools": ["Cast-iron kettle"]},
 {"name": "Saltmarsh Samphire Hash", "description": "Samphire and potato hash from the Saltmarsh Depot garden.",
  "recipeYield": "6 plates", "recipeServings": 6, "prepTime": "10 minutes", "performTime": "20 minutes", "totalTime": "30 minutes",
  "ingredients": ["500 g samphire, rinsed twice", "800 g potatoes, boiled and cubed", "2 eggs per plate"],
  "steps": ["Fry the potatoes until crisp.", "Toss in the samphire for two minutes.", "Top each plate with two eggs."],
  "notes": [("Salt", "Samphire is salty enough; add no salt.")], "cats": ["Quarry Lunches"], "tags": ["foraged"], "tools": []},
 {"name": "Copperfield Ginger Tea", "description": "Ginger and honey tea brewed for the Copperfield Annex painters.",
  "recipeYield": "1 flask", "recipeServings": 4, "prepTime": "5 minutes", "performTime": "10 minutes", "totalTime": "15 minutes",
  "ingredients": ["40 g fresh ginger, sliced", "2 tablespoons honey", "1 litre water"],
  "steps": ["Simmer the ginger for ten minutes.", "Stir in the honey and pour into the flask."],
  "notes": [("Flask", "The blue flask belongs to the Copperfield Annex crew.")], "cats": ["Night-Shift Snacks"], "tags": ["night-shift"], "tools": []},
]
def slim(o): return {"id": o["id"], "name": o["name"], "slug": o["slug"]}
for r in RECIPES:
    slug = r["name"].lower().replace(" ", "-")
    cur, st = api("GET", f"/api/recipes/{slug}", ok=(404,))
    if cur is None:
        slug, _ = api("POST", "/api/recipes", {"name": r["name"]}); cur, _ = api("GET", f"/api/recipes/{slug}"); log(f"recipe {slug} created")
    if cur.get("description") != r["description"]:
        cur.update({k: r[k] for k in ("description", "recipeYield", "recipeServings", "prepTime", "performTime", "totalTime")})
        cur["recipeIngredient"] = [{"note": t, "display": t, "quantity": 0, "unit": None, "food": None, "referenceId": str(uuid.uuid4())} for t in r["ingredients"]]
        cur["recipeInstructions"] = [{"id": str(uuid.uuid4()), "title": "", "summary": "", "text": t, "ingredientReferences": []} for t in r["steps"]]
        cur["notes"] = [{"title": a, "text": b} for a, b in r["notes"]]
        cur["recipeCategory"] = [slim(cat[c]) for c in r["cats"]]; cur["tags"] = [slim(tag[t]) for t in r["tags"]]; cur["tools"] = [slim(tool[t]) for t in r["tools"]]
        api("PUT", f"/api/recipes/{slug}", cur); log(f"recipe {slug} written")
    ids["recipes"][slug] = cur["id"]
RID = {s: i for s, i in ids["recipes"].items()}

COOKBOOKS = [("Spring Tide Menu", "Everything served on spring-tide nights at the Blue Heron Kitchen.", "Tide-Table Suppers"),
             ("Quarry Packs", "Portable food for the Granite Ledger counting days.", "Quarry Lunches")]
books = api("GET", "/api/households/cookbooks?perPage=50")[0]["items"]
for name, desc, c in COOKBOOKS:
    b = next((x for x in books if x["name"] == name), None)
    if not b:
        b, _ = api("POST", "/api/households/cookbooks", {"name": name, "description": desc, "public": False,
                   "queryFilterString": f'recipe_category.id IN ["{ids["categories"][c]}"]'}); log(f"cookbook {name} created")
    ids["cookbooks"][name] = b["id"]

LISTS = [("Saltmarsh Depot order", [("Twelve crates of dried kelp", 12, "crate", "dried kelp"), ("Four sacks of pearl barley", 4, None, "pearl barley")]),
         ("Granite Ledger pantry", [("Rolled oats for 24 bars", 1, None, None), ("Two jars of heather honey", 2, None, None)])]
lists = api("GET", "/api/households/shopping/lists?perPage=50")[0]["items"]
for name, items in LISTS:
    l = next((x for x in lists if x["name"] == name), None) or api("POST", "/api/households/shopping/lists", {"name": name})[0]
    ids["shopping_lists"][name] = l["id"]
    have = {i["note"] for i in (api("GET", f"/api/households/shopping/lists/{l['id']}")[0].get("listItems") or [])}
    for note, qty, unit, food in items:
        if note not in have:
            body = {"shoppingListId": l["id"], "note": note, "quantity": qty, **({"unitId": ids["units"][unit]} if unit else {}), **({"foodId": ids["foods"][food]} if food else {})}
            api("POST", "/api/households/shopping/items", body)
    for i in api("GET", f"/api/households/shopping/lists/{l['id']}")[0].get("listItems") or []: ids["shopping_items"][i["note"]] = i["id"]

PLANS = [("2026-11-14", "dinner", "smoked-kelp-broth", "", ""), ("2026-11-15", "lunch", "granite-ledger-oat-bars", "", ""),
         ("2026-11-16", "side", None, "Kelp delivery day", "Twelve crates arrive from the Saltmarsh Depot before noon.")]
plans = api("GET", "/api/households/mealplans?start_date=2026-11-14&end_date=2026-11-16&perPage=50")[0]["items"]
for date, kind, slug, title, text in PLANS:
    p = next((x for x in plans if x["date"] == date and x["entryType"] == kind), None)
    if not p:
        p, _ = api("POST", "/api/households/mealplans", {"date": date, "entryType": kind, "title": title, "text": text, **({"recipeId": RID[slug]} if slug else {})})
        log(f"meal plan {date} {kind} created")
    ids["mealplans"][f"{date} {kind}"] = p["id"]

COMMENTS = [("smoked-kelp-broth", "Halve the pepper when the day shift eats it."), ("granite-ledger-oat-bars", "These held together through the whole tidal-yard count.")]
for slug, text in COMMENTS:
    cur = [c for c in api("GET", f"/api/recipes/{slug}/comments", who="mina")[0] if c["text"] == text]
    c = cur[0] if cur else api("POST", "/api/comments", {"recipeId": RID[slug], "text": text}, who="mina")[0]
    ids["comments"][slug] = c["id"]
json.dump(ids, open(os.path.join(DIR, "seed-ids.json"), "w"), indent=1)
log("seed-ids.json written: " + json.dumps(ids))
