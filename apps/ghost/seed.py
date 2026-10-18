#!/usr/bin/env python3
"""Seed the showcase Ghost with synthetic content through the Admin API (idempotent).

Creates the owner via the setup API (name "Rea Admin", email rea-admin@example.test, blog "Lighthouse Rota") with a
password generated at run time and kept only in ~/capture/ghost/.admin (mode 600). A session cookie is created for this
script only and destroyed at the end. Seeds 2 tags, 2 published posts, 1 draft, 1 page, 1 member, and updates the owner bio.
Writes seed-ids.json (ids and slugs only, no secrets) for capture.mjs. Never prints the password."""
import http.cookiejar, json, os, secrets, sys, time, urllib.error, urllib.request

BASE = os.environ.get("BASE_URL", "http://127.0.0.1:3105")
DIR = os.environ.get("CAPTURE_DIR", os.path.expanduser("~/capture/ghost"))
ADMIN_FILE = os.path.join(DIR, ".admin")
EMAIL, NAME, TITLE = "rea-admin@example.test", "Rea Admin", "Lighthouse Rota"

def log(msg): print(f"[seed] {msg}", file=sys.stderr)

def load_or_create_admin():
    if os.path.exists(ADMIN_FILE):
        kv = dict(line.split("=", 1) for line in open(ADMIN_FILE).read().splitlines() if "=" in line)
        return kv["GHOST_ADMIN_PASSWORD"]
    pw = secrets.token_urlsafe(21)
    fd = os.open(ADMIN_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(f"GHOST_ADMIN_EMAIL={EMAIL}\nGHOST_ADMIN_PASSWORD={pw}\n")
    log(f"wrote {ADMIN_FILE} (mode 600)")
    return pw

jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))

def api(method, path, body=None, ok404=False):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method)
    # Ghost's session CSRF check derives the origin from Origin/Referer on every request.
    req.add_header("Origin", BASE); req.add_header("Accept", "application/json")
    if data is not None: req.add_header("Content-Type", "application/json")
    try:
        with opener.open(req, timeout=30) as r:
            raw = r.read()
            try: return (json.loads(raw) if raw else {}), r.status
            except ValueError: return {}, r.status  # e.g. the session endpoint answers 201 "Created" as text
    except urllib.error.HTTPError as e:
        if e.code == 404 and ok404: return None, 404
        detail = e.read().decode(errors="replace")[:400]
        raise SystemExit(f"[seed] {method} {path} -> {e.code}: {detail}")

def wait_ready():
    for _ in range(120):
        try:
            with urllib.request.urlopen(BASE + "/ghost/api/admin/site/", timeout=5) as r:
                if r.status == 200: return json.loads(r.read())["site"]
        except Exception: pass
        time.sleep(2)
    raise SystemExit("[seed] Ghost did not become ready")

site = wait_ready(); log(f"ghost version {site.get('version')} ready at {BASE}")
pw = load_or_create_admin()
setup, _ = api("GET", "/ghost/api/admin/authentication/setup/")
if not setup["setup"][0]["status"]:
    api("POST", "/ghost/api/admin/authentication/setup/", {"setup": [{"name": NAME, "email": EMAIL, "password": pw, "blogTitle": TITLE}]})
    log("owner created through the setup API")
else:
    log("setup already done; reusing .admin")
api("POST", "/ghost/api/admin/session/", {"username": EMAIL, "password": pw}); log("seed session created")

ids = {"tags": {}, "posts": {}, "pages": {}, "members": {}, "users": {}}

# Remove scratch posts left behind by an interrupted capture so every capture starts from the same state.
left, _ = api("GET", "/ghost/api/admin/posts/?filter=slug:~^'rea-scratch-post'&limit=50&fields=id,slug")
for sp in left.get("posts", []):
    api("DELETE", f"/ghost/api/admin/posts/{sp['id']}/"); log(f"removed leftover scratch post {sp['slug']}")

TAGS = [
    {"name": "Granite Ledger", "slug": "granite-ledger", "description": "Stone counts and quarry audits for the rota."},
    {"name": "Blue Heron Kitchen", "slug": "blue-heron-kitchen", "description": "Menus that follow the tides."},
]
for t in TAGS:
    cur, st = api("GET", f"/ghost/api/admin/tags/slug/{t['slug']}/", ok404=True)
    if cur is None: cur, _ = api("POST", "/ghost/api/admin/tags/", {"tags": [t]}); log(f"tag {t['slug']} created")
    ids["tags"][t["slug"]] = cur["tags"][0]["id"]

POSTS = [
    {"title": "Granite Ledger: Quarterly Stone Count", "slug": "granite-ledger-quarterly-stone-count", "status": "published", "featured": True,
     "custom_excerpt": "412 blocks counted, audited by Rui Castellanos.", "tags": [{"name": "Granite Ledger"}],
     "html": "<p>The Granite Ledger closes the quarter with 412 blocks counted in the north quarry and 97 in the tidal yard.</p>"
             "<p>Rui Castellanos audited the tally on the fourteenth; the ledger reference number is GL-2291.</p>"
             "<h2>Next steps</h2><ul><li>Re-measure the seaward stack</li><li>Retire cart number 7</li></ul>"},
    {"title": "Blue Heron Kitchen opens its tide-table menu", "slug": "blue-heron-kitchen-tide-table-menu", "status": "published",
     "custom_excerpt": "36 covers per sitting; the menu follows the tides.", "tags": [{"name": "Blue Heron Kitchen"}],
     "html": "<p>Blue Heron Kitchen now serves 36 covers per sitting, with the menu changing on every spring tide.</p>"
             "<p>Head cook Marisol Okonkwo-Reyes pairs smoked kelp broth with the night shift of the Lighthouse Rota at 22:00.</p>"},
    {"title": "Lighthouse Rota: winter shift plan (draft)", "slug": "lighthouse-rota-winter-shift-draft", "status": "draft",
     "tags": [{"name": "Granite Ledger"}, {"name": "Blue Heron Kitchen"}],
     "html": "<p>Draft: shift three starts at 22:00 and hands over at 06:00; Ada Finch keeps the tide tables for January.</p>"
             "<p>Lamp oil budget for the winter: 180 litres.</p>"},
]
for p in POSTS:
    cur, st = api("GET", f"/ghost/api/admin/posts/slug/{p['slug']}/", ok404=True)
    if cur is None: cur, _ = api("POST", "/ghost/api/admin/posts/?source=html", {"posts": [p]}); log(f"post {p['slug']} created ({p['status']})")
    ids["posts"][p["slug"]] = cur["posts"][0]["id"]

PAGE = {"title": "About the Lighthouse Rota", "slug": "about-the-lighthouse-rota", "status": "published",
        "html": "<p>The Lighthouse Rota is a synthetic publication used to exercise the Ghost Admin API. Every name, number and place here is invented.</p>"
                "<p>Editor: Rea Admin. Contact: rea-admin@example.test.</p>"}
cur, st = api("GET", f"/ghost/api/admin/pages/slug/{PAGE['slug']}/", ok404=True)
if cur is None: cur, _ = api("POST", "/ghost/api/admin/pages/?source=html", {"pages": [PAGE]}); log("page created")
ids["pages"][PAGE["slug"]] = cur["pages"][0]["id"]

MEMBER = {"name": "Ada Finch", "email": "ada.finch@example.test", "note": "Keeps the tide tables for the winter rota.", "labels": [{"name": "Rota Crew"}]}
cur, _ = api("GET", "/ghost/api/admin/members/?filter=email:'ada.finch@example.test'")
if not cur["members"]: cur, _ = api("POST", "/ghost/api/admin/members/", {"members": [MEMBER]}); log("member created")
ids["members"]["ada-finch"] = cur["members"][0]["id"]

me, _ = api("GET", "/ghost/api/admin/users/me/")
owner_id = me["users"][0]["id"]
api("PUT", f"/ghost/api/admin/users/{owner_id}/", {"users": [{"bio": "Keeper of the Lighthouse Rota since the spring census; counts granite by lamplight.", "location": "Granite Point"}]})
log("owner bio updated"); ids["users"]["rea-admin"] = owner_id

api("DELETE", "/ghost/api/admin/session/"); log("seed session destroyed")
json.dump(ids, open(os.path.join(DIR, "seed-ids.json"), "w"), indent=1)
log("seed-ids.json written: " + json.dumps(ids))
