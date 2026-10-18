#!/usr/bin/env python3
"""Seed the showcase listmonk with synthetic content through its REST API (idempotent). Nothing is ever sent.

`python3 seed.py init` writes ~/capture/listmonk/.admin (mode 600) with a generated admin password and database password;
compose reads it as an env_file and `listmonk --install` creates the admin rea-admin from LISTMONK_ADMIN_USER/PASSWORD.
`python3 seed.py` then logs in through the admin login form (session cookie for this script only, logged out at the end) and
removes the install-time samples (2 sample lists, 2 sample subscribers, the test campaign, and the 4 sample templates after
making "Tide Table Letter" the default, because their bodies link to the project's website), sets the root URL, site name,
from address and update check through PUT /api/settings/{key}, names the admin profile Rea Admin <rea-admin@example.test>,
and creates, by fixed names: 4 lists, 6 subscribers (subscriptions preconfirmed, so no opt-in mail), 3 templates, 3 draft
campaigns, 1 user role, 1 list role, 1 user, 1 media image (generated PNG). Writes seed-ids.json (ids only)."""
import http.cookiejar, json, os, secrets, struct, sys, time, urllib.error, urllib.parse, urllib.request, uuid, zlib

BASE = os.environ.get("BASE_URL", "http://127.0.0.1:3214")
DIR = os.environ.get("CAPTURE_DIR", os.path.expanduser("~/capture/listmonk"))
ADMIN_FILE = os.path.join(DIR, ".admin")
USER = "rea-admin"

def log(msg): print(f"[seed] {msg}", file=sys.stderr)

def init_admin():
    if os.path.exists(ADMIN_FILE): log(".admin exists; keeping it"); return
    db = secrets.token_urlsafe(18)
    fd = os.open(ADMIN_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(f"LISTMONK_ADMIN_PASSWORD={secrets.token_urlsafe(21)}\nPOSTGRES_PASSWORD={db}\nLISTMONK_db__password={db}\n")
    log(f"wrote {ADMIN_FILE} (mode 600)")

jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))

def call(method, path, body=None, raw=None, ctype=None, soft=False):
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    req = urllib.request.Request(BASE + path, data=data, method=method)
    req.add_header("Accept", "application/json")
    if data is not None: req.add_header("Content-Type", ctype or "application/json")
    try:
        with opener.open(req, timeout=60) as r:
            txt = r.read(); return json.loads(txt) if txt else {}
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors='replace')[:300]
        if soft: log(f"{method} {path} -> {e.code}: {detail} (continuing)"); return None
        raise SystemExit(f"[seed] {method} {path} -> {e.code}: {detail}")

def wait_ready():
    for _ in range(150):
        try:
            with urllib.request.urlopen(BASE + "/health", timeout=5) as r:
                if r.status == 200: return
        except Exception: pass
        time.sleep(2)
    raise SystemExit("[seed] listmonk did not become ready")

def login():
    pw = dict(l.split("=", 1) for l in open(ADMIN_FILE).read().splitlines() if "=" in l)["LISTMONK_ADMIN_PASSWORD"]
    opener.open(urllib.request.Request(BASE + "/admin/login"), timeout=30).read()
    form = urllib.parse.urlencode({"username": USER, "password": pw, "next": "/admin"}).encode()
    with opener.open(urllib.request.Request(BASE + "/admin/login", data=form, method="POST"), timeout=30) as r: r.read()
    if not any(c.name == "session" for c in jar): raise SystemExit("[seed] login did not set a session cookie")

def png(w, h, rgb):
    raw = b"".join(b"\x00" + bytes(rgb) * w for _ in range(h))
    chunk = lambda t, d: struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")

if len(sys.argv) > 1 and sys.argv[1] == "init":
    init_admin(); sys.exit(0)

wait_ready(); login(); me = call("GET", "/api/profile")["data"]; log(f"logged in as {me['username']}")
ids = {}

def by_name(path, name, key="name"):
    res = call("GET", path)["data"]; items = res["results"] if isinstance(res, dict) and "results" in res else res
    return next((x for x in items if x.get(key) == name), None)

# Remove the install-time sample data so every record in the capture is the synthetic set below.
for c in call("GET", "/api/campaigns?per_page=all&no_body=true")["data"]["results"]:
    if c["name"] in ("Test campaign", "Welcome to listmonk"): call("DELETE", f"/api/campaigns/{c['id']}"); log("removed sample campaign")
for s in call("GET", "/api/subscribers?per_page=all")["data"]["results"]:
    if s["email"] in ("john@example.com", "anon@example.com"): call("DELETE", f"/api/subscribers/{s['id']}"); log(f"removed sample subscriber {s['id']}")
for l in call("GET", "/api/lists?per_page=all")["data"]["results"]:
    if l["name"] in ("Default list", "Opt-in list"): call("DELETE", f"/api/lists/{l['id']}"); log(f"removed sample list {l['name']}")

# Remove scratch lists an interrupted capture may have left behind.
for l in call("GET", "/api/lists?per_page=all&query=" + urllib.parse.quote("Rea scratch"))["data"]["results"]:
    call("DELETE", f"/api/lists/{l['id']}"); log(f"removed leftover scratch list {l['name']}")

LISTS = [
    {"name": "Lighthouse Rota Dispatch", "type": "public", "optin": "single", "tags": ["rota", "weekly"],
     "description": "Weekly shift notes for the lamp keepers of the Lighthouse Rota."},
    {"name": "Granite Ledger Members", "type": "private", "optin": "single", "tags": ["ledger"],
     "description": "Quarterly stone counts for holders of the Granite Ledger."},
    {"name": "Blue Heron Kitchen Regulars", "type": "public", "optin": "double", "tags": ["kitchen", "menus"],
     "description": "Tide-table menus and supper sittings at Blue Heron Kitchen."},
    {"name": "Saltmarsh Depot Notices", "type": "private", "optin": "single", "tags": ["depot"],
     "description": "Delivery windows and bay assignments at the Saltmarsh Depot."},
]
ids["lists"] = {}
for l in LISTS:
    cur = by_name("/api/lists?per_page=all", l["name"]) or call("POST", "/api/lists", l)["data"]
    ids["lists"][l["name"]] = cur["id"]
L = ids["lists"]; log(f"lists: {L}")

SUBS = [
    {"email": "ada.finch@example.test", "name": "Ada Finch", "status": "enabled", "lists": [L["Lighthouse Rota Dispatch"], L["Granite Ledger Members"]],
     "attribs": {"city": "Granite Point", "shift": "night", "duty": "tide-table keeper"}},
    {"email": "rui.castellanos@example.test", "name": "Rui Castellanos", "status": "enabled", "lists": [L["Granite Ledger Members"]],
     "attribs": {"city": "Copperfield", "duty": "ledger auditor", "blocks_counted": 412}},
    {"email": "mina.okafor@example.test", "name": "Mina Okafor", "status": "enabled", "lists": [L["Blue Heron Kitchen Regulars"]],
     "attribs": {"city": "Saltmarsh", "favourite_dish": "smoked kelp broth"}},
    {"email": "tomas.vey@example.test", "name": "Tomas Vey", "status": "enabled", "lists": [L["Saltmarsh Depot Notices"], L["Lighthouse Rota Dispatch"]],
     "attribs": {"bay": "3 north", "duty": "depot receiving clerk"}},
    {"email": "marisol.okonkwo-reyes@example.test", "name": "Marisol Okonkwo-Reyes", "status": "enabled", "lists": [L["Blue Heron Kitchen Regulars"]],
     "attribs": {"duty": "head cook", "sittings": 2}},
    {"email": "bram.ostergaard@example.test", "name": "Bram Ostergaard", "status": "blocklisted", "lists": [L["Saltmarsh Depot Notices"]],
     "attribs": {"note": "returned two dented drums"}},
]
ids["subscribers"] = {}
for s in SUBS:
    q = urllib.parse.quote(f"subscribers.email = '{s['email']}'")
    found = call("GET", f"/api/subscribers?per_page=5&query={q}")["data"]["results"]
    cur = found[0] if found else call("POST", "/api/subscribers", {**s, "preconfirm_subscriptions": True})["data"]
    ids["subscribers"][s["name"]] = cur["id"]
log(f"subscribers: {ids['subscribers']}")

CONTENT = '{{ template "content" . }}'
TEMPLATES = [
    {"name": "Tide Table Letter", "type": "campaign",
     "body": f'<html><body style="font-family: Georgia, serif; background: #eef4f7"><h2>Lighthouse Rota</h2>{CONTENT}<p>High water tables are kept by Ada Finch.</p></body></html>'},
    {"name": "Granite Ledger Digest", "type": "campaign",
     "body": f'<html><body style="font-family: Helvetica, sans-serif"><h1>Granite Ledger</h1>{CONTENT}<p>Counts audited by Rui Castellanos.</p></body></html>'},
    {"name": "Depot Delivery Receipt", "type": "tx", "subject": "Saltmarsh Depot delivery receipt",
     "body": '<p>Your delivery to bay {{ .Tx.Data.bay }} was received by the Saltmarsh Depot.</p>'},
]
ids["templates"] = {}
for t in TEMPLATES:
    cur = by_name("/api/templates?no_body=true", t["name"]) or call("POST", "/api/templates", t)["data"]
    ids["templates"][t["name"]] = cur["id"]
log(f"templates: {ids['templates']}")
SAMPLE_TEMPLATES = ("Default campaign template", "Default archive template", "Sample transactional template", "Sample visual template")
if any(t["name"] in SAMPLE_TEMPLATES for t in call("GET", "/api/templates?no_body=true")["data"]):
    call("PUT", f"/api/templates/{ids['templates']['Tide Table Letter']}/default")
    for t in call("GET", "/api/templates?no_body=true")["data"]:
        if t["name"] in SAMPLE_TEMPLATES and call("DELETE", f"/api/templates/{t['id']}", soft=True) is not None: log(f"removed sample template {t['name']}")

CAMPAIGNS = [
    {"name": "Winter Rota Briefing", "subject": "Shift three now starts at 22:00", "lists": [L["Lighthouse Rota Dispatch"]],
     "from_email": "Lighthouse Rota <rota@example.test>", "content_type": "richtext", "messenger": "email", "type": "regular",
     "tags": ["rota", "winter"], "template_id": ids["templates"]["Tide Table Letter"],
     "body": "<p>Shift three starts at 22:00 and hands over at 06:00. Lamp oil budget for the winter: 180 litres.</p>"},
    {"name": "Granite Ledger Quarterly Count", "subject": "412 blocks counted in the north quarry", "lists": [L["Granite Ledger Members"]],
     "from_email": "Granite Ledger <ledger@example.test>", "content_type": "richtext", "messenger": "email", "type": "regular",
     "tags": ["ledger", "quarterly"], "template_id": ids["templates"]["Granite Ledger Digest"],
     "body": "<p>The north quarry holds 412 blocks and the tidal yard 97. Cart number 7 is retired.</p>"},
    {"name": "Blue Heron Kitchen Spring Menu", "subject": "Smoked kelp broth returns with the spring tide", "lists": [L["Blue Heron Kitchen Regulars"]],
     "from_email": "Blue Heron Kitchen <kitchen@example.test>", "content_type": "markdown", "messenger": "email", "type": "regular",
     "tags": ["kitchen"], "template_id": ids["templates"]["Tide Table Letter"],
     "body": "## Spring menu\n\n36 covers per sitting. Head cook Marisol Okonkwo-Reyes serves smoked kelp broth at the 19:30 sitting."},
]
ids["campaigns"] = {}
for c in CAMPAIGNS:
    found = call("GET", "/api/campaigns?per_page=all&query=" + urllib.parse.quote(c["name"]))["data"]["results"]
    cur = next((x for x in found if x["name"] == c["name"]), None) or call("POST", "/api/campaigns", c)["data"]
    ids["campaigns"][c["name"]] = cur["id"]
log(f"campaigns (all drafts): {ids['campaigns']}")

ROLE = {"name": "Ledger Auditor", "permissions": ["subscribers:get", "campaigns:get", "lists:get_all", "templates:get"]}
cur = by_name("/api/roles/users", ROLE["name"]) or call("POST", "/api/roles/users", ROLE)["data"]
ids["user_roles"] = {ROLE["name"]: cur["id"]}
LROLE = {"name": "Kitchen List Editors", "lists": [{"id": L["Blue Heron Kitchen Regulars"], "permissions": ["list:get", "list:manage"]}]}
cur = by_name("/api/roles/lists", LROLE["name"]) or call("POST", "/api/roles/lists", LROLE)["data"]
ids["list_roles"] = {LROLE["name"]: cur["id"]}
NEWUSER = {"username": "ada.finch", "email": "ada.finch@example.test", "name": "Ada Finch", "type": "user", "status": "enabled",
           "password_login": False, "user_role_id": ids["user_roles"]["Ledger Auditor"], "list_role_id": ids["list_roles"]["Kitchen List Editors"]}
cur = by_name("/api/users", NEWUSER["username"], "username") or call("POST", "/api/users", NEWUSER)["data"]
ids["users"] = {NEWUSER["username"]: cur["id"]}
log(f"roles and users: {ids['user_roles']} {ids['list_roles']} {ids['users']}")

media = call("GET", "/api/media")["data"]; media = media.get("results", media) if isinstance(media, dict) else media
cur = next((m for m in media if m.get("filename") == "granite-ledger-banner.png"), None)
if not cur:
    boundary = uuid.uuid4().hex
    body = (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="granite-ledger-banner.png"\r\nContent-Type: image/png\r\n\r\n').encode() \
        + png(64, 16, (96, 110, 120)) + f"\r\n--{boundary}--\r\n".encode()
    cur = call("POST", "/api/media", raw=body, ctype=f"multipart/form-data; boundary={boundary}")["data"]; log("media uploaded")
ids["media"] = {"granite-ledger-banner.png": cur["id"]}

if me.get("email") != "rea-admin@example.test" or me.get("name") != "Rea Admin":
    call("PUT", "/api/profile", {"name": "Rea Admin", "email": "rea-admin@example.test"}); log("admin profile set to Rea Admin <rea-admin@example.test>")

SETTINGS = {"app.root_url": "http://127.0.0.1:3214", "app.site_name": "Lighthouse Rota Dispatch",
            "app.from_email": "Lighthouse Rota <rota@example.test>", "app.check_updates": False}
cur = call("GET", "/api/settings")["data"]
for k, v in SETTINGS.items():
    if cur.get(k) != v:
        call("PUT", f"/api/settings/{k}", v); log(f"setting {k} updated; waiting for the reload"); time.sleep(3); wait_ready()

call("POST", "/api/logout"); log("seed session logged out")
json.dump(ids, open(os.path.join(DIR, "seed-ids.json"), "w"), indent=1)
log("seed-ids.json written: " + json.dumps({k: list(v.values()) for k, v in ids.items()}))
