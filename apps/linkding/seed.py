#!/usr/bin/env python3
"""Seed the showcase linkding with synthetic content through its REST API (idempotent by URL / name).

`python3 seed.py init` writes ~/capture/linkding/.admin (mode 600) with LD_SUPERUSER_PASSWORD generated at run time; compose
reads it through env_file so linkding creates the superuser `rea-admin` on first start. `python3 seed.py` then signs in
through the Django login form (session cookie + CSRF token, both in memory only) and seeds over /api/: 6 bookmarks with
example.test URLs, notes and tags (2 archived, 1 unread), 1 extra tag, 2 bundles, and a text asset on one bookmark.
Bookmarks are created with disable_scraping / disable_html_snapshot, so nothing fetches the invented URLs.
Writes seed-ids.json (ids only). Never prints a secret."""
import http.cookiejar, json, os, re, secrets, sys, time, urllib.error, urllib.parse, urllib.request

BASE = os.environ.get("BASE_URL", "http://127.0.0.1:3203")
DIR = os.environ.get("CAPTURE_DIR", os.path.expanduser("~/capture/linkding"))
ADMIN_FILE = os.path.join(DIR, ".admin")
USER = "rea-admin"


def log(msg): print(f"[seed] {msg}", file=sys.stderr)


if sys.argv[1:] == ["init"]:
    if os.path.exists(ADMIN_FILE): log(".admin already exists"); sys.exit(0)
    fd = os.open(ADMIN_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f: f.write(f"LD_SUPERUSER_PASSWORD=Rea-{secrets.token_urlsafe(18)}\n")
    log(f"wrote {ADMIN_FILE} (mode 600)"); sys.exit(0)

PW = dict(l.split("=", 1) for l in open(ADMIN_FILE).read().splitlines() if "=" in l)["LD_SUPERUSER_PASSWORD"]
jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))


def csrf(): return next((c.value for c in jar if "csrf" in c.name.lower()), "")  # linkding renames Django's cookies


def call(method, path, data=None, ctype=None, accept="application/json"):
    req = urllib.request.Request(BASE + path, data=data, method=method)
    req.add_header("Accept", accept); req.add_header("Origin", BASE); req.add_header("Referer", BASE + "/")
    if ctype: req.add_header("Content-Type", ctype)
    if method not in ("GET", "HEAD"): req.add_header("X-CSRFToken", csrf())
    try:
        with opener.open(req, timeout=30) as r: return r.status, r.read()
    except urllib.error.HTTPError as e:
        raise SystemExit(f"[seed] {method} {path} -> {e.code}: {e.read().decode(errors='replace')[:300]}")


def api(method, path, body=None):
    st, raw = call(method, path, json.dumps(body).encode() if body is not None else None, "application/json" if body is not None else None)
    return json.loads(raw) if raw else {}


for _ in range(60):
    try:
        with urllib.request.urlopen(BASE + "/health", timeout=5) as r:
            if r.status == 200: health = json.loads(r.read()); break
    except Exception: pass
    time.sleep(2)
else: raise SystemExit("[seed] linkding did not become ready")
log(f"linkding {health.get('version')} ready at {BASE}")

# --- session login through the Django form ---
st, html = call("GET", "/login/", accept="text/html")
token = re.search(rb'name="csrfmiddlewaretoken" value="([^"]+)"', html).group(1).decode()
form = urllib.parse.urlencode({"username": USER, "password": PW, "csrfmiddlewaretoken": token}).encode()
call("POST", "/login/", form, "application/x-www-form-urlencoded", accept="text/html")
if not any("session" in c.name for c in jar): raise SystemExit(f"[seed] login failed (cookies: {sorted(c.name for c in jar)})")
log(f"seed session created (cookie names {sorted(c.name for c in jar)})")

ids = {"bookmarks": {}, "tags": {}, "bundles": {}, "assets": {}}
have = {b["url"]: b for b in api("GET", "/api/bookmarks/?limit=100")["results"] + api("GET", "/api/bookmarks/archived/?limit=100")["results"]}
for b in list(have.values()):  # scratch bookmarks left by an interrupted capture
    if "scratch" in b["url"]: api("DELETE", f"/api/bookmarks/{b['id']}/"); log(f"removed leftover {b['url']}")

BOOKMARKS = [
    ("granite-count", "https://granite-ledger.example.test/quarterly-count", "Granite Ledger quarterly stone count",
     "412 blocks counted in the north quarry and 97 in the tidal yard.", "Audited by Rui Castellanos; ledger reference GL-2291.",
     ["granite-ledger", "audit"], False, False),
    ("heron-menu", "https://blue-heron-kitchen.example.test/tide-table-menu", "Blue Heron Kitchen tide-table menu",
     "Thirty-six covers per sitting; smoked kelp broth on spring tides.", "Head cook Marisol Okonkwo-Reyes calls service at 22:00.",
     ["blue-heron-kitchen", "menus"], False, True),
    ("depot-gates", "https://saltmarsh-depot.example.test/gate-log", "Saltmarsh Depot gate log",
     "Open-time log for gates 1 to 4 at the depot.", "Gate 3 stayed open for 11 minutes after the night round; Mina Okafor to check the latch.",
     ["saltmarsh-depot", "audit"], False, False),
    ("annex-carts", "https://copperfield-annex.example.test/cart-register", "Copperfield Annex cart register",
     "Register of hand carts lent to the quarry crews.", "Cart number 7 retired; replaced by the annex hand cart.",
     ["copperfield-annex", "granite-ledger"], True, False),
    ("rota-winter", "https://lighthouse-rota.example.test/winter-shifts", "Lighthouse Rota winter shift plan",
     "Shift three runs 22:00 to 06:00 through January.", "Ada Finch keeps the tide tables; lamp oil budget 180 litres.",
     ["lighthouse-rota"], False, False),
    ("tide-january", "https://lighthouse-rota.example.test/tide-tables-january", "Tide tables for January",
     "Spring tides on the 3rd and the 18th.", "Superseded by the February tables; kept for the Tomas Vey handover.",
     ["lighthouse-rota", "blue-heron-kitchen"], True, False),
]
for key, url, title, desc, notes, tags, archived, unread in BOOKMARKS:
    b = have.get(url) or api("POST", "/api/bookmarks/?disable_scraping&disable_html_snapshot", {
        "url": url, "title": title, "description": desc, "notes": notes, "tag_names": tags, "is_archived": archived,
        "unread": unread, "shared": False})
    ids["bookmarks"][key] = b["id"]

tags = {t["name"]: t for t in api("GET", "/api/tags/?limit=100")["results"]}
if "night-shift" not in tags: tags["night-shift"] = api("POST", "/api/tags/", {"name": "night-shift"})
for name, t in tags.items(): ids["tags"][name] = t["id"]

bundles = {b["name"]: b for b in api("GET", "/api/bundles/")["results"]}
BUNDLES = [("quarry-depot", {"name": "Quarry and depot audits", "search": "", "any_tags": "granite-ledger saltmarsh-depot", "all_tags": "", "excluded_tags": "menus"}),
           ("kitchen", {"name": "Blue Heron reading list", "search": "kelp", "any_tags": "", "all_tags": "blue-heron-kitchen", "excluded_tags": ""})]
for key, body in BUNDLES:
    b = bundles.get(body["name"]) or api("POST", "/api/bundles/", body)
    ids["bundles"][key] = b["id"]

# a small text asset on the Granite Ledger bookmark (multipart upload)
bid = ids["bookmarks"]["granite-count"]
assets = api("GET", f"/api/bookmarks/{bid}/assets/")["results"] if True else []
asset = next((a for a in assets if a.get("display_name") == "granite-ledger-gl-2291-tally.txt"), None)
if asset is None:
    boundary = "rea" + secrets.token_hex(8)
    content = b"Granite Ledger tally GL-2291\nnorth quarry: 412 blocks\ntidal yard: 97 blocks\nauditor: Rui Castellanos\n"
    body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"granite-ledger-gl-2291-tally.txt\"\r\n"
            f"Content-Type: text/plain\r\n\r\n").encode() + content + f"\r\n--{boundary}--\r\n".encode()
    st, raw = call("POST", f"/api/bookmarks/{bid}/assets/upload/", body, f"multipart/form-data; boundary={boundary}")
    asset = json.loads(raw)
ids["assets"]["granite-tally"] = asset["id"]

call("POST", "/logout/", b"", "application/x-www-form-urlencoded", accept="text/html"); log("seed session ended")
json.dump(ids, open(os.path.join(DIR, "seed-ids.json"), "w"), indent=1)
log("seed-ids.json written: " + json.dumps(ids))
