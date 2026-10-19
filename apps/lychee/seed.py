#!/usr/bin/env python3
"""Seed the showcase Lychee with synthetic albums, photos, tags and users through its v2 API (idempotent).

The admin "rea-admin" gets a password generated at run time, kept only in ~/capture/lychee/.admin (mode 600) and handed
to `php artisan lychee:create_user` through an environment variable. The seed session is kept open at the end and its
session cookie is stored in .admin as session_secret, so the capture scenario starts signed in through a storage seed
(Lychee answers the anonymous Gallery::Init with dropbox_api_key "disabled", which the credential gate refuses, so the
capture must not load any page before it is signed in). Every image is generated here (stdlib zlib + struct
PNGs: gradients, stripes, rings, horizons); nothing is downloaded. Writes seed-ids.json (ids only). Never prints secrets."""
import http.cookiejar, json, os, secrets, struct, subprocess, sys, time, urllib.error, urllib.parse, urllib.request, uuid, zlib

BASE = os.environ.get("BASE_URL", "http://127.0.0.1:3402")
DIR = os.environ.get("CAPTURE_DIR", os.path.expanduser("~/capture/lychee"))
ADMIN_FILE = os.path.join(DIR, ".admin")
USER = "rea-admin"
COMPOSE = ["docker", "compose", "-p", "rea-lychee", "-f", os.path.join(DIR, "compose.yml")]


def log(msg): print(f"[seed] {msg}", file=sys.stderr)


# ---------- generated images ----------
def png(w, h, pixel):
    rows = []
    for y in range(h):
        row = bytearray(b"\x00")
        for x in range(w): row += bytes(pixel(x, y))
        rows.append(bytes(row))
    chunk = lambda t, d: struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(b"".join(rows), 9)) + chunk(b"IEND", b""))

def mix(a, b, t): return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))

def vgradient(top, bottom): return lambda w, h: (lambda x, y: mix(top, bottom, y / max(1, h - 1)))
def hgradient(left, right): return lambda w, h: (lambda x, y: mix(left, right, x / max(1, w - 1)))
def hstripes(colors, band): return lambda w, h: (lambda x, y: colors[(y // band) % len(colors)])
def vstripes(colors, band): return lambda w, h: (lambda x, y: colors[(x // band) % len(colors)])
def checker(a, b, cell): return lambda w, h: (lambda x, y: a if ((x // cell) + (y // cell)) % 2 == 0 else b)
def rings(bg, fg, step):
    return lambda w, h: (lambda x, y: fg if int((((x - w / 2) ** 2 + (y - h / 2) ** 2) ** 0.5) // step) % 2 == 0 else bg)
def disc(bg, fg, r):
    return lambda w, h: (lambda x, y: fg if (x - w / 2) ** 2 + (y - h / 2) ** 2 <= (r * min(w, h)) ** 2 else bg)
def horizon(sky, sea, sun):
    def make(w, h):
        def px(x, y):
            if y > h * 0.6: return sea
            if (x - w * 0.5) ** 2 + (y - h * 0.6) ** 2 <= (h * 0.22) ** 2: return sun
            return mix(sky, (250, 250, 250), y / h)
        return px
    return make


# ---------- seed content (all invented) ----------
ALBUMS = [
    {"key": "saltmarsh", "title": "Saltmarsh Depot", "parent": None, "license": "CC-BY-4.0", "copyright": "Saltmarsh Depot Camera Club",
     "description": "Rail sidings and tide gauges photographed for the Saltmarsh Depot ledger, spring census series."},
    {"key": "signalbox", "title": "Signal Box Nine", "parent": "saltmarsh", "license": "CC-BY-4.0", "copyright": "Saltmarsh Depot Camera Club",
     "description": "Night frames from signal box nine during the lamp check rota kept by Tomas Vey."},
    {"key": "lighthouse", "title": "Lighthouse Rota", "parent": None, "license": "CC0", "copyright": "Lighthouse Rota volunteers",
     "description": "Lamp-room studies from the winter rota, one frame per shift, filed by Ada Finch."},
    {"key": "lantern", "title": "Lantern Gallery Repairs", "parent": "lighthouse", "license": "CC0", "copyright": "Lighthouse Rota volunteers",
     "description": "Before and after swatches of the lantern gallery repaint, brass rail polished in week 14."},
    {"key": "heron", "title": "Blue Heron Kitchen", "parent": None, "license": "reserved", "copyright": "Blue Heron Kitchen brigade",
     "description": "Plating tests for the tide-table menu, 36 covers per sitting, head cook Mina Okafor."},
    {"key": "copperfield", "title": "Copperfield Annex", "parent": None, "license": "CC-BY-SA-4.0", "copyright": "Copperfield Annex works office",
     "description": "Facade colour swatches for the annex repaint, approved by Rui Castellanos on site visit 3."},
]

PHOTOS = [
    {"key": "tide-gauge-dawn", "album": "saltmarsh", "w": 640, "h": 360, "img": vgradient((24, 52, 96), (236, 168, 92)),
     "title": "Tide gauge at dawn, siding four", "tags": ["tide gauge", "spring census"], "taken": "2026-03-14 06:12:00",
     "description": "Dawn reading on the siding four gauge: 2.35 metres, navy-to-amber sky gradient, logged as SD-0412."},
    {"key": "ballast-stripes", "album": "saltmarsh", "w": 480, "h": 320, "img": hstripes([(118, 110, 98), (196, 188, 170), (64, 60, 56)], 16),
     "title": "Ballast wagon stripes", "tags": ["rolling stock", "spring census"], "taken": "2026-03-14 09:40:00",
     "description": "Grey and sand horizontal stripes on ballast wagon 7731, repainted for the depot open day."},
    {"key": "depot-checker", "album": "saltmarsh", "w": 320, "h": 320, "img": checker((30, 30, 30), (232, 196, 40), 40),
     "title": "Yard limit board, black and amber", "tags": ["rolling stock"], "taken": "2026-03-15 11:05:00",
     "description": "Black and amber checker board marking the yard limit, eight squares by eight, post SD-17."},
    {"key": "signal-lamp", "album": "signalbox", "w": 360, "h": 360, "img": disc((10, 12, 28), (220, 40, 36), 0.18),
     "title": "Red aspect, box nine", "tags": ["night shift", "signal lamp"], "taken": "2026-03-20 23:48:00",
     "description": "Single red aspect against a midnight-blue field, lamp check 23:48 signed by Tomas Vey."},
    {"key": "lever-frame", "album": "signalbox", "w": 480, "h": 270, "img": vstripes([(150, 28, 32), (240, 236, 228), (40, 40, 44), (232, 196, 40)], 24),
     "title": "Lever frame colours", "tags": ["night shift"], "taken": "2026-03-21 00:30:00",
     "description": "Vertical bands of signal red, white, black and amber copied from the 24-lever frame in box nine."},
    {"key": "lamp-rings", "album": "lighthouse", "w": 400, "h": 400, "img": rings((14, 20, 44), (250, 214, 120), 20),
     "title": "Fresnel rings, shift three", "tags": ["lamp room", "night shift"], "taken": "2026-01-09 03:15:00",
     "description": "Concentric gold rings on deep navy, a study of the fresnel lens at 03:15 on shift three."},
    {"key": "rota-horizon", "album": "lighthouse", "w": 640, "h": 400, "img": horizon((70, 120, 190), (24, 60, 92), (250, 200, 80)),
     "title": "Horizon from the gallery rail", "tags": ["lamp room"], "taken": "2026-01-10 07:58:00",
     "description": "Half sun on a slate-blue sea seen from the gallery rail, visibility 18 nautical miles."},
    {"key": "oil-gradient", "album": "lighthouse", "w": 320, "h": 200, "img": hgradient((60, 40, 20), (238, 210, 150)),
     "title": "Lamp oil swatch, winter budget", "tags": ["lamp room"], "taken": "2026-01-12 12:00:00",
     "description": "Brown-to-straw gradient matched to the lamp oil sample; winter budget 180 litres."},
    {"key": "gallery-before", "album": "lantern", "w": 360, "h": 240, "img": hstripes([(120, 70, 50), (150, 95, 70)], 12),
     "title": "Gallery rail before repaint", "tags": ["brass rail", "repaint"], "taken": "2026-04-02 10:00:00",
     "description": "Rust-brown banding on the lantern gallery rail before the week 14 repaint."},
    {"key": "gallery-after", "album": "lantern", "w": 360, "h": 240, "img": hgradient((200, 160, 60), (250, 232, 160)),
     "title": "Gallery rail after polish", "tags": ["brass rail", "repaint"], "taken": "2026-04-09 15:20:00",
     "description": "Polished brass gradient after the repaint; Ada Finch measured 0.4 mm of new lacquer."},
    {"key": "kelp-broth", "album": "heron", "w": 400, "h": 400, "img": disc((236, 232, 220), (52, 92, 60), 0.32),
     "title": "Smoked kelp broth plating", "tags": ["tide-table menu", "heron blue"], "taken": "2026-05-02 19:30:00",
     "description": "Deep green broth in a cream bowl, plated for the spring tide sitting, course two of five."},
    {"key": "heron-plate", "album": "heron", "w": 480, "h": 320, "img": rings((210, 226, 236), (60, 110, 160), 28),
     "title": "Heron blue charger rings", "tags": ["heron blue"], "taken": "2026-05-02 20:10:00",
     "description": "Pale and heron-blue rings of the new charger plates, order HK-208 of 40 plates."},
    {"key": "copper-swatch", "album": "copperfield", "w": 320, "h": 240, "img": vgradient((184, 115, 51), (64, 160, 140)),
     "title": "Copper to verdigris swatch", "tags": ["facade swatch"], "taken": "2026-06-18 14:00:00",
     "description": "Copper-orange fading to verdigris green, option B for the annex cornice, paint code CA-31."},
    {"key": "annex-bands", "album": "copperfield", "w": 480, "h": 320, "img": vstripes([(222, 214, 196), (184, 115, 51), (90, 96, 104)], 40),
     "title": "Annex facade bands, option C", "tags": ["facade swatch", "repaint"], "taken": "2026-06-18 14:30:00",
     "description": "Limestone, copper and slate vertical bands for option C, approved on site visit 3."},
]

USERS = [("ada.finch", "Ada Finch"), ("tomas.vey", "Tomas Vey")]


# ---------- HTTP ----------
jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))

def xsrf():
    for c in jar:
        if c.name == "XSRF-TOKEN": return urllib.parse.unquote(c.value)
    return None

def api(method, path, body=None, query=None, multipart=None, ok=(200, 201, 204)):
    url = BASE + "/api/v2/" + path + (("?" + urllib.parse.urlencode(query)) if query else "")
    headers = {"Accept": "application/json"}
    if multipart is not None:
        boundary = "----rea" + uuid.uuid4().hex
        parts = []
        for k, v in multipart.items():
            if isinstance(v, tuple):
                fname, data, ctype = v
                parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"; filename="{fname}"\r\nContent-Type: {ctype}\r\n\r\n'.encode() + data + b"\r\n")
            else:
                parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
        data = b"".join(parts) + f"--{boundary}--\r\n".encode()
        headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
    else:
        data = json.dumps(body).encode() if body is not None else None
        headers["Content-Type"] = "application/json"
    tok = xsrf()
    if tok: headers["X-XSRF-TOKEN"] = tok
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with opener.open(req, timeout=120) as r:
            raw = r.read()
            try: return json.loads(raw) if raw else None
            except ValueError: return raw.decode(errors="replace")
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:600]
        raise SystemExit(f"[seed] {method} {path} -> {e.code}: {detail}")

def wait_ready():
    for _ in range(120):
        try:
            with urllib.request.urlopen(BASE + "/up", timeout=5) as r:
                if r.status == 200: return
        except Exception: pass
        time.sleep(2)
    raise SystemExit("[seed] Lychee did not become ready")

def load_or_create_admin():
    if os.path.exists(ADMIN_FILE):
        kv = dict(line.split("=", 1) for line in open(ADMIN_FILE).read().splitlines() if "=" in line)
        if set(kv) != {"username", "password"}:
            fd = os.open(ADMIN_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w") as f: f.write(f"username={USER}\npassword={kv['password']}\n")
        return kv["password"], False
    pw = secrets.token_urlsafe(21)
    fd = os.open(ADMIN_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f: f.write(f"username={USER}\npassword={pw}\n")
    log(f"wrote {ADMIN_FILE} (mode 600)")
    return pw, True


wait_ready()
pw, fresh = load_or_create_admin()
if fresh:
    env = dict(os.environ, LYCHEE_SEED_PW=pw)
    r = subprocess.run(COMPOSE + ["exec", "-T", "-u", "www-data", "-e", "LYCHEE_SEED_PW", "lychee", "sh", "-c",
                                  f'php artisan lychee:create_user {USER} "$LYCHEE_SEED_PW" --may-administrate --may-upload --may-edit-own-settings'],
                       env=env, capture_output=True, text=True)
    if r.returncode != 0: raise SystemExit(f"[seed] create_user failed: {r.stderr[-400:]}")
    log("admin rea-admin created with artisan lychee:create_user")

opener.open(urllib.request.Request(BASE + "/gallery", headers={"Accept": "text/html"}), timeout=30).read()
api("POST", "Auth::login", {"username": USER, "password": pw}); log("seed session created")

ids = {"albums": {}, "photos": {}, "tags": {}, "users": {}}

# Remove scratch albums left behind by an interrupted capture.
root = api("GET", "Albums")
for a in root.get("albums", []):
    if a["title"].lower().startswith("rea scratch"):
        api("DELETE", "Album", {"album_ids": [a["id"]]}); log(f"removed leftover scratch album {a['title']}")

def find_album(title, parent_id):
    if parent_id is None:
        listing = api("GET", "Albums").get("albums", [])
    else:
        listing = api("GET", "Album", query={"album_id": parent_id})["resource"].get("albums", [])
    return next((a for a in listing if a["title"] == title), None)

for a in ALBUMS:
    parent_id = ids["albums"].get(a["parent"]) if a["parent"] else None
    cur = find_album(a["title"], parent_id)
    if cur is None:
        aid = api("POST", "Album", {"title": a["title"], "parent_id": parent_id})
        log(f"album {a['title']} created")
    else:
        aid = cur["id"]
    ids["albums"][a["key"]] = aid
    api("PATCH", "Album", {"album_id": aid, "title": a["title"], "license": a["license"], "description": a["description"],
                           "photo_sorting_column": "title", "photo_sorting_order": "ASC", "album_sorting_column": None,
                           "album_sorting_order": None, "album_aspect_ratio": None, "photo_layout": None, "copyright": a["copyright"],
                           "is_compact": False, "is_pinned": a["key"] == "lighthouse", "header_id": None,
                           "album_timeline": None, "photo_timeline": None})

def album_photos(aid):
    return api("GET", "Album", query={"album_id": aid})["resource"].get("photos", [])

os.makedirs(os.path.join(DIR, "images"), exist_ok=True)
for p in PHOTOS:
    aid = ids["albums"][p["album"]]
    fname = p["key"] + ".png"
    data = png(p["w"], p["h"], p["img"](p["w"], p["h"]))
    if len(data) > 60_000: raise SystemExit(f"[seed] {fname} is {len(data)} bytes; keep generated images under 60 KB")
    with open(os.path.join(DIR, "images", fname), "wb") as f: f.write(data)
    existing = {ph["title"]: ph for ph in album_photos(aid)}
    ph = existing.get(p["title"]) or existing.get(fname)
    if ph is None:
        api("POST", "Photo", multipart={"album_id": aid, "file_last_modified_time": str(int(time.time() * 1000)), "file_name": fname,
                                         "uuid_name": "", "extension": "", "chunk_number": "1", "total_chunks": "1",
                                         "file": (fname, data, "image/png")})
        for _ in range(30):
            existing = {x["title"]: x for x in album_photos(aid)}
            ph = existing.get(fname) or existing.get(p["title"])
            if ph: break
            time.sleep(1)
        if ph is None: raise SystemExit(f"[seed] upload of {fname} did not appear in its album")
        log(f"photo {fname} uploaded ({len(data)} bytes)")
    api("PATCH", "Photo", {"photo_id": ph["id"], "title": p["title"], "description": p["description"], "tags": p["tags"],
                           "license": ALBUMS[[a["key"] for a in ALBUMS].index(p["album"])]["license"],
                           "upload_date": ph.get("created_at") or "2026-10-19T00:00:00+00:00", "taken_at": p["taken"], "from_id": aid})
    ids["photos"][p["key"]] = ph["id"]

for key in ("lamp-rings", "kelp-broth", "copper-swatch"):
    api("POST", "Photo::star", {"photo_ids": [ids["photos"][key]], "is_starred": True})

tags = api("GET", "Tags")
for t in (tags.get("tags", []) if isinstance(tags, dict) else []):
    ids["tags"][t["name"]] = t["id"]

existing_users = {u["username"]: u for u in (api("GET", "UserManagement") or [])}
for uname, _display in USERS:
    if uname not in existing_users:
        api("POST", "UserManagement", {"username": uname, "password": secrets.token_urlsafe(18), "may_upload": uname == "ada.finch",
                                       "may_edit_own_settings": True})
        log(f"user {uname} created")
for u in api("GET", "UserManagement") or []:
    if u["username"] in dict(USERS): ids["users"][u["username"]] = u["id"]

# Gallery::Init reports the Dropbox key setting to admins; its default sentinel "disabled" sits in a field named like a
# credential, so blank it (no Dropbox integration either way; the UI only offers a Dropbox import entry).
api("POST", "Settings::setConfigs", {"configs": [{"key": "dropbox_key", "value": ""}]}); log("dropbox_key blanked")

# Keep this session for the capture: its cookie becomes a declared secret of the scenario's storage seed.
session = next(c.value for c in jar if c.name == "lychee_session")
kv = dict(line.split("=", 1) for line in open(ADMIN_FILE).read().splitlines() if "=" in line)
kv["session_secret"] = session
fd = os.open(ADMIN_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
with os.fdopen(fd, "w") as f: f.write("".join(f"{k}={v}\n" for k, v in kv.items()))
log("capture session cookie stored in .admin (session_secret)")
json.dump(ids, open(os.path.join(DIR, "seed-ids.json"), "w"), indent=1)
log("seed-ids.json written: " + json.dumps({k: len(v) for k, v in ids.items()}))
