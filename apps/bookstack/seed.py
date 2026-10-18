#!/usr/bin/env python3
"""Seed the showcase BookStack with synthetic content through its REST API (idempotent).

First run: signs in through the web form with the image's documented default admin (admin@admin.com / password), creates an
API token for that user through the web form (the only way BookStack issues tokens), then renames the default admin through
PUT /api/users/1 to "Rea Admin" <rea-admin@example.test> with a password generated at run time. The password and the token
live only in ~/capture/bookstack/.admin (mode 600); nothing secret is printed. Later runs reuse the token from .admin.
Seeds 2 roles, 3 users, 5 books, 3 shelves, 5 chapters, 8 pages, 2 link attachments and 2 comments, all invented, hands nine
items to other owners (content-permissions API, three with a role view grant), and
removes any "Rea Scratch" objects left by an interrupted capture. Writes seed-ids.json (ids only)."""
import http.cookiejar, json, os, re, secrets, sys, time, urllib.error, urllib.parse, urllib.request

BASE = os.environ.get("BASE_URL", "http://127.0.0.1:3219")
DIR = os.environ.get("CAPTURE_DIR", os.path.expanduser("~/capture/bookstack"))
ADMIN_FILE = os.path.join(DIR, ".admin")
EMAIL, NAME = "rea-admin@example.test", "Rea Admin"
DEFAULT_EMAIL, DEFAULT_PASSWORD = "admin@admin.com", "password"  # documented first-boot admin of the image


def log(msg): print(f"[seed] {msg}", file=sys.stderr)


def read_admin():
    if not os.path.exists(ADMIN_FILE): raise SystemExit("[seed] run up.sh first (it creates .admin)")
    return dict(l.split("=", 1) for l in open(ADMIN_FILE).read().splitlines() if "=" in l)


def append_admin(**kv):
    with open(ADMIN_FILE, "a") as f:
        for k, v in kv.items(): f.write(f"{k}={v}\n")
    os.chmod(ADMIN_FILE, 0o600)


def wait_ready():
    for _ in range(120):
        try:
            with urllib.request.urlopen(BASE + "/login", timeout=5) as r:
                if r.status == 200: return
        except Exception: pass
        time.sleep(2)
    raise SystemExit("[seed] BookStack did not become ready")


def web_login(email, password):
    """Form sign-in; returns a cookie opener when the credentials work, else None."""
    jar = http.cookiejar.CookieJar(); op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    html = op.open(BASE + "/login", timeout=30).read().decode()
    csrf = re.search(r'name="_token" value="([^"]+)"', html).group(1)
    r = op.open(BASE + "/login", urllib.parse.urlencode({"_token": csrf, "email": email, "password": password}).encode(), timeout=30)
    return op if not r.url.rstrip("/").endswith("/login") else None


def create_token(op, user_id, name):
    html = op.open(f"{BASE}/api-tokens/{user_id}/create", timeout=30).read().decode()
    csrf = re.findall(r'name="_token" value="([^"]+)"', html)[-1]
    r = op.open(f"{BASE}/api-tokens/{user_id}/create", urllib.parse.urlencode({"_token": csrf, "name": name, "expires_at": ""}).encode(), timeout=30)
    page = r.read().decode()
    tid = re.search(r'id="token_id"[^>]*value="([^"]+)"', page, re.S).group(1)
    sec = re.search(r'<input type="text" readonly="readonly" value="([^"]+)"', page).group(1)  # shown once after creation
    return tid, sec


admin = {}
def api(method, path, body=None, ok404=False):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method)
    req.add_header("Accept", "application/json"); req.add_header("Authorization", f"Token {admin['BOOKSTACK_TOKEN_ID']}:{admin['BOOKSTACK_TOKEN_SECRET']}")
    if data is not None: req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read(); return (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        if e.code == 404 and ok404: return None
        raise SystemExit(f"[seed] {method} {path} -> {e.code}: {e.read().decode(errors='replace')[:400]}")


def all_of(coll):
    return api("GET", f"/api/{coll}?count=500")["data"]


wait_ready(); log(f"bookstack ready at {BASE}")
admin = read_admin()
if "REA_ADMIN_PASSWORD" not in admin:
    append_admin(REA_ADMIN_PASSWORD=secrets.token_urlsafe(21)); admin = read_admin(); log("generated the admin password into .admin")
if "BOOKSTACK_TOKEN_ID" not in admin:
    op = web_login(EMAIL, admin["REA_ADMIN_PASSWORD"]) or web_login(DEFAULT_EMAIL, DEFAULT_PASSWORD)
    if op is None: raise SystemExit("[seed] neither the renamed nor the default admin can sign in")
    tid, sec = create_token(op, 1, "rea-seed")
    append_admin(BOOKSTACK_TOKEN_ID=tid, BOOKSTACK_TOKEN_SECRET=sec); admin = read_admin(); log("API token created through the web form, kept in .admin")

me = api("GET", "/api/users/1")
if me["email"] != EMAIL:
    api("PUT", "/api/users/1", {"name": NAME, "email": EMAIL, "password": admin["REA_ADMIN_PASSWORD"]})
    log("default admin renamed to Rea Admin with a generated password")
ids = {"roles": {}, "users": {"rea-admin": 1}, "books": {}, "shelves": {}, "chapters": {}, "pages": {}, "attachments": {}, "comments": {}}

# Leftovers from an interrupted capture (the capture creates and deletes one scratch book).
for b in all_of("books"):
    if b["name"].startswith("Rea Scratch"): api("DELETE", f"/api/books/{b['id']}"); log(f"removed leftover {b['name']}")

ROLES = [
    {"display_name": "Tide Clerks", "description": "Keep the tide tables and the night watch log.", "permissions": ["content-export", "page-create-all", "page-update-all"]},
    {"display_name": "Quarry Auditors", "description": "Audit stone counts in the Granite Ledger each quarter.", "permissions": ["content-export"]},
]
roles = {r["display_name"]: r["id"] for r in all_of("roles")}
for r in ROLES:
    if r["display_name"] not in roles: roles[r["display_name"]] = api("POST", "/api/roles", r)["id"]; log(f"role {r['display_name']} created")
    ids["roles"][r["display_name"]] = roles[r["display_name"]]

USERS = [
    {"name": "Ada Finch", "email": "ada.finch@example.test", "roles": ["Editor", "Tide Clerks"], "language": "en"},
    {"name": "Rui Castellanos", "email": "rui.castellanos@example.test", "roles": ["Viewer", "Quarry Auditors"], "language": "en"},
    {"name": "Mina Okafor", "email": "mina.okafor@example.test", "roles": ["Editor"], "language": "en"},
]
users = {u["email"]: u["id"] for u in all_of("users")}
for u in USERS:
    if u["email"] not in users:
        body = {**u, "roles": [roles[x] for x in u["roles"]], "send_invite": False, "password": secrets.token_urlsafe(18)}  # never used, never stored
        users[u["email"]] = api("POST", "/api/users", body)["id"]; log(f"user {u['name']} created")
    ids["users"][u["email"].split("@")[0]] = users[u["email"]]

BOOKS = [
    {"name": "Lamp Room Procedures", "description": "Wick trimming, lens polishing and the 22:00 lamp check.", "tags": [{"name": "site", "value": "Lighthouse Rota"}, {"name": "shift", "value": "night"}]},
    {"name": "Tide Table Almanac", "description": "Spring and neap tides logged by Ada Finch for the winter rota.", "tags": [{"name": "keeper", "value": "Ada Finch"}]},
    {"name": "Quarry Audit Manual", "description": "How the Granite Ledger counts blocks in the north quarry.", "tags": [{"name": "ledger", "value": "GL-2291"}]},
    {"name": "Saltmarsh Depot Inventory", "description": "Crates, ropes and lamp oil stored at the Saltmarsh Depot.", "tags": [{"name": "site", "value": "Saltmarsh Depot"}]},
    {"name": "Blue Heron Kitchen Recipes", "description": "Kelp broth and tide-table menus for 36 covers a sitting.", "tags": [{"name": "cook", "value": "Marisol Okonkwo-Reyes"}]},
]
books = {b["name"]: b["id"] for b in all_of("books")}
for b in BOOKS:
    if b["name"] not in books: books[b["name"]] = api("POST", "/api/books", b)["id"]; log(f"book {b['name']} created")
    ids["books"][b["name"]] = books[b["name"]]

SHELVES = [
    {"name": "Lighthouse Rota Handbooks", "description": "Everything the night shift needs at the lamp.", "books": ["Lamp Room Procedures", "Tide Table Almanac"], "tags": [{"name": "team", "value": "Night Shift"}]},
    {"name": "Granite Ledger Archive", "description": "Quarry audits kept by Rui Castellanos since the spring census.", "books": ["Quarry Audit Manual"], "tags": [{"name": "auditor", "value": "Rui Castellanos"}]},
    {"name": "Copperfield Annex Stores", "description": "Depot and kitchen manuals filed at the Copperfield Annex.", "books": ["Saltmarsh Depot Inventory", "Blue Heron Kitchen Recipes"], "tags": [{"name": "site", "value": "Copperfield Annex"}]},
]
shelves = {s["name"]: s["id"] for s in all_of("shelves")}
for s in SHELVES:
    if s["name"] not in shelves: shelves[s["name"]] = api("POST", "/api/shelves", {**s, "books": [books[x] for x in s["books"]]})["id"]; log(f"shelf {s['name']} created")
    ids["shelves"][s["name"]] = shelves[s["name"]]

CHAPTERS = [
    {"book": "Lamp Room Procedures", "name": "Wick and Lens Care", "description": "Trim wicks to 4 mm and polish the lens with chamois.", "tags": [{"name": "tool", "value": "wick shears"}]},
    {"book": "Lamp Room Procedures", "name": "Night Watch Handover", "description": "Handover at 06:00 between shift three and the dawn crew.", "tags": [{"name": "shift", "value": "three"}]},
    {"book": "Tide Table Almanac", "name": "Winter Spring Tides", "description": "January spring tides peak at 5.8 metres off Granite Point.", "tags": [{"name": "month", "value": "January"}]},
    {"book": "Quarry Audit Manual", "name": "North Quarry Counts", "description": "Block tallies per terrace, audited on the fourteenth.", "tags": [{"name": "auditor", "value": "Rui Castellanos"}]},
    {"book": "Saltmarsh Depot Inventory", "name": "Lamp Oil Ledger", "description": "Winter lamp oil budget of 180 litres, issued weekly.", "tags": [{"name": "unit", "value": "litres"}]},
]
chapters = {(c["book_id"], c["name"]): c["id"] for c in all_of("chapters")}
for c in CHAPTERS:
    key = (books[c["book"]], c["name"])
    if key not in chapters:
        chapters[key] = api("POST", "/api/chapters", {"book_id": books[c["book"]], "name": c["name"], "description": c["description"], "tags": c["tags"]})["id"]; log(f"chapter {c['name']} created")
    ids["chapters"][c["name"]] = chapters[key]

PAGES = [
    {"chapter": "Wick and Lens Care", "name": "Trimming the Wick", "tags": [{"name": "drawer", "value": "B"}],
     "markdown": "Trim the wick to 4 mm before the 22:00 lamp check.\n\nTomas Vey keeps the spare wicks in drawer B of the lamp room."},
    {"chapter": "Night Watch Handover", "name": "Shift Three Handover Checklist", "tags": [{"name": "handover", "value": "06:00"}],
     "markdown": "1. Log the lamp hours.\n2. Hand the tide clock key to the dawn crew.\n3. Note fog signals in the red ledger."},
    {"book": "Lamp Room Procedures", "name": "Lamp Room Safety Notice", "tags": [{"name": "priority", "value": "high"}],
     "markdown": "No open flame on the gallery stairs. Fire buckets are refilled every Monday by Mina Okafor."},
    {"chapter": "Winter Spring Tides", "name": "January Tide Readings", "tags": [{"name": "gauge", "value": "Granite Point"}],
     "markdown": "Highest reading: 5.8 m on the ninth at 04:12. Lowest: 0.3 m on the twenty-third."},
    {"chapter": "North Quarry Counts", "name": "Terrace Seven Tally", "tags": [{"name": "terrace", "value": "seven"}],
     "markdown": "Terrace seven holds 58 blocks. Cart number 7 was retired after the audit."},
    {"chapter": "Lamp Oil Ledger", "name": "October Oil Issues", "tags": [{"name": "month", "value": "October"}],
     "markdown": "Issued 42 litres in October; 138 litres remain for the winter."},
    {"book": "Saltmarsh Depot Inventory", "name": "Rope Store Layout", "tags": [{"name": "aisle", "value": "C"}],
     "markdown": "Manila ropes hang in aisle C; the spare halyards sit on the top rack."},
    {"book": "Blue Heron Kitchen Recipes", "name": "Smoked Kelp Broth", "tags": [{"name": "course", "value": "starter"}],
     "markdown": "Simmer the stock for twenty minutes, add smoked kelp, serve at 22:00 to the night shift."},
]
pages = {p["name"]: p["id"] for p in all_of("pages")}
for p in PAGES:
    if p["name"] not in pages:
        parent = {"chapter_id": ids["chapters"][p["chapter"]]} if "chapter" in p else {"book_id": books[p["book"]]}
        pages[p["name"]] = api("POST", "/api/pages", {**parent, "name": p["name"], "markdown": p["markdown"], "tags": p["tags"]})["id"]; log(f"page {p['name']} created")
    ids["pages"][p["name"]] = pages[p["name"]]

ATTACHMENTS = [
    {"name": "Wick Gauge Diagram", "page": "Trimming the Wick", "link": "https://example.test/lighthouse-rota/wick-gauge.pdf"},
    {"name": "Terrace Seven Survey Sheet", "page": "Terrace Seven Tally", "link": "https://example.test/granite-ledger/terrace-seven.csv"},
]
atts = {a["name"]: a["id"] for a in all_of("attachments")}
for a in ATTACHMENTS:
    if a["name"] not in atts: atts[a["name"]] = api("POST", "/api/attachments", {"name": a["name"], "uploaded_to": pages[a["page"]], "link": a["link"]})["id"]; log(f"attachment {a['name']} created")
    ids["attachments"][a["name"]] = atts[a["name"]]

COMMENTS = [
    {"page": "Shift Three Handover Checklist", "html": "<p>Mina Okafor confirms the lens was polished at 05:40.</p>"},
    {"page": "Smoked Kelp Broth", "html": "<p>Add the kelp only after the stock has simmered for twenty minutes.</p>"},
]
existing = all_of("comments")
for c in COMMENTS:
    pid = pages[c["page"]]; hit = [x for x in existing if x.get("commentable_id", x.get("entity_id")) == pid]
    cid = hit[0]["id"] if hit else api("POST", "/api/comments", {"page_id": pid, "html": c["html"]})["id"]
    if not hit: log(f"comment on {c['page']} created")
    ids["comments"][c["page"]] = cid

# Hand some items to the other people (owner) and give one role an explicit view grant, so owners and grants differ per item.
OWNERS = [
    ("bookshelf", ids["shelves"]["Granite Ledger Archive"], "rui.castellanos", [("Quarry Auditors", True)]),
    ("book", ids["books"]["Tide Table Almanac"], "ada.finch", []),
    ("book", ids["books"]["Quarry Audit Manual"], "rui.castellanos", [("Quarry Auditors", True)]),
    ("book", ids["books"]["Blue Heron Kitchen Recipes"], "mina.okafor", []),
    ("chapter", ids["chapters"]["Winter Spring Tides"], "ada.finch", [("Tide Clerks", True)]),
    ("page", ids["pages"]["Lamp Room Safety Notice"], "mina.okafor", []),
    ("page", ids["pages"]["January Tide Readings"], "ada.finch", []),
    ("page", ids["pages"]["Terrace Seven Tally"], "rui.castellanos", []),
    ("page", ids["pages"]["Smoked Kelp Broth"], "mina.okafor", []),
]
for ctype, cid, who, grants in OWNERS:
    body = {"owner_id": ids["users"][who]}
    if grants: body["role_permissions"] = [{"role_id": roles[r], "view": v, "create": False, "update": False, "delete": False} for r, v in grants]
    api("PUT", f"/api/content-permissions/{ctype}/{cid}", body)
log(f"owners/grants set on {len(OWNERS)} items")

json.dump(ids, open(os.path.join(DIR, "seed-ids.json"), "w"), indent=1)
log("seed-ids.json written: " + json.dumps({k: len(v) for k, v in ids.items()}))
