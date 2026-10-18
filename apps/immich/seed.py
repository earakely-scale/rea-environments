#!/usr/bin/env python3
"""Seed the showcase Immich with synthetic content through its REST API (idempotent).

Creates the admin through POST /api/auth/admin-sign-up (name "Rea Admin", rea-admin@example.test) with a password generated
at run time and kept only in ~/capture/immich/.admin (mode 600). A bearer token is created for this script only (login) and
revoked at the end (logout). Turns machine learning and the version check off in the system config, marks onboarding done,
then seeds 2 more users, 5 generated PNG photos (stdlib zlib/struct) with descriptions and ratings, 3 albums, 4 tags (one
nested), 2 people attached to photos through manual faces, 2 shared links, 1 album comment, 1 partner share, 1 external
library and 1 notification. Writes seed-ids.json (ids only, no secrets). Never prints a password or a token."""
import json, os, secrets, struct, sys, time, urllib.error, urllib.request, uuid, zlib

BASE = os.environ.get("BASE_URL", "http://127.0.0.1:3207")
DIR = os.environ.get("CAPTURE_DIR", os.path.expanduser("~/capture/immich"))
ADMIN_FILE = os.path.join(DIR, ".admin")
EMAIL, NAME = "rea-admin@example.test", "Rea Admin"
TOKEN = None


def log(msg): print(f"[seed] {msg}", file=sys.stderr)


def load_or_create_admin():
    if os.path.exists(ADMIN_FILE):
        kv = dict(line.split("=", 1) for line in open(ADMIN_FILE).read().splitlines() if "=" in line)
        return kv["IMMICH_ADMIN_PASSWORD"]
    pw = secrets.token_urlsafe(21)
    fd = os.open(ADMIN_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(f"IMMICH_ADMIN_PASSWORD={pw}\n")  # the email is not a secret and appears in API replies
    log(f"wrote {ADMIN_FILE} (mode 600)")
    return pw


def api(method, path, body=None, raw=None, ctype=None, ok=()):
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    req = urllib.request.Request(BASE + "/api" + path, data=data, method=method)
    req.add_header("Accept", "application/json")
    if data is not None: req.add_header("Content-Type", ctype or "application/json")
    if TOKEN: req.add_header("Authorization", "Bearer " + TOKEN)
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
    for _ in range(150):
        try:
            with urllib.request.urlopen(BASE + "/api/server/ping", timeout=5) as r:
                if r.status == 200: return
        except Exception: pass
        time.sleep(2)
    raise SystemExit("[seed] Immich did not become ready")


def png(width, height, base, stripe):
    """A small RGB PNG: a solid base colour with a diagonal stripe, so every image has its own checksum."""
    rows = b""
    for y in range(height):
        row = bytearray([0])
        for x in range(width):
            row += bytes(stripe if (x + y) % 16 < 4 else base)
        rows += bytes(row)
    chunk = lambda tag, data: struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(rows, 9)) + chunk(b"IEND", b""))


def multipart(fields, file_field, filename, content, mime):
    boundary = "----rea" + uuid.uuid4().hex
    out = b""
    for k, v in fields.items():
        out += f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode()
    out += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"{file_field}\"; filename=\"{filename}\"\r\n"
            f"Content-Type: {mime}\r\n\r\n").encode() + content + b"\r\n"
    out += f"--{boundary}--\r\n".encode()
    return out, f"multipart/form-data; boundary={boundary}"


wait_ready(); log(f"immich ready at {BASE}")
pw = load_or_create_admin()
cfg, _ = api("GET", "/server/config")
if not cfg.get("isInitialized"):
    api("POST", "/auth/admin-sign-up", {"email": EMAIL, "name": NAME, "password": pw}); log("admin created through admin-sign-up")
else:
    log("server already initialized; reusing .admin")
login, _ = api("POST", "/auth/login", {"email": EMAIL, "password": pw})
TOKEN = login["accessToken"]; admin_id = login["userId"]; log("seed login ok (token kept in memory only)")

# System config: no machine-learning container here, no outbound version check.
sc, _ = api("GET", "/system-config")
sc["machineLearning"]["enabled"] = False
sc["newVersionCheck"]["enabled"] = False
api("PUT", "/system-config", sc); log("machine learning and version check disabled")
api("POST", "/system-metadata/admin-onboarding", {"isOnboarded": True})
api("PUT", "/users/me/onboarding", {"isOnboarded": True}); log("onboarding marked done")

ids = {"admin": admin_id, "users": {}, "assets": {}, "albums": {}, "tags": {}, "people": {}, "shared_links": {},
       "libraries": {}, "notifications": {}, "activities": {}}

# Remove scratch albums left behind by an interrupted capture so every capture starts from the same state.
for al in api("GET", "/albums")[0]:
    if al["albumName"].startswith("Rea scratch album"):
        api("DELETE", f"/albums/{al['id']}"); log(f"removed leftover scratch album {al['id']}")

USERS = [
    {"name": "Ada Finch", "email": "ada.finch@example.test", "storageLabel": "ada-finch"},
    {"name": "Rui Castellanos", "email": "rui.castellanos@example.test", "storageLabel": "rui-castellanos"},
]
existing = {u["email"]: u for u in api("GET", "/admin/users")[0]}
for u in USERS:
    cur = existing.get(u["email"])
    if cur is None:
        cur, _ = api("POST", "/admin/users", {**u, "password": secrets.token_urlsafe(18), "notify": False, "shouldChangePassword": False})
        log(f"user {u['email']} created")
    ids["users"][u["storageLabel"]] = cur["id"]

PHOTOS = [
    ("lighthouse-rota-lamp-room.png", (200, 160, 40), (90, 60, 10), "2026-01-11T22:05:00.000Z",
     "Lamp room of the Lighthouse Rota before the 22:00 hand-over; the brass lens was polished by Ada Finch.", 5, True),
    ("granite-ledger-north-quarry.png", (120, 120, 128), (60, 60, 70), "2026-02-14T10:30:00.000Z",
     "North quarry face for the Granite Ledger count: 412 blocks tallied, audit reference GL-2291.", 4, False),
    ("blue-heron-kitchen-pass.png", (40, 90, 160), (230, 230, 240), "2026-03-02T19:45:00.000Z",
     "Blue Heron Kitchen pass at the first sitting: smoked kelp broth for 36 covers.", 3, False),
    ("copperfield-annex-stairwell.png", (170, 90, 50), (240, 200, 160), "2026-03-20T08:15:00.000Z",
     "Copperfield Annex east stairwell after the repaint; banister colour Quarry Moss.", 2, False),
    ("saltmarsh-depot-cart-7.png", (60, 130, 90), (20, 40, 30), "2026-04-05T16:00:00.000Z",
     "Saltmarsh Depot loading bay with cart number 7, retired by Tomas Vey on the fifth of April.", 4, True),
]
for fname, base, stripe, when, desc, rating, fav in PHOTOS:
    body, ctype = multipart({"fileCreatedAt": when, "fileModifiedAt": when, "filename": fname}, "assetData", fname,
                            png(96, 72, base, stripe), "image/png")
    res, st = api("POST", "/assets", raw=body, ctype=ctype)
    aid = res["id"]; key = fname[:-4]; ids["assets"][key] = aid
    log(f"asset {fname} -> {res.get('status')}")
    api("PUT", f"/assets/{aid}", {"description": desc, "rating": rating, "isFavorite": fav})

A = ids["assets"]; U = ids["users"]
ALBUMS = [
    {"albumName": "Lighthouse Rota Night Shift", "description": "Photos from the winter night shift, three keepers on a 22:00 to 06:00 rota.",
     "assets": ["lighthouse-rota-lamp-room", "saltmarsh-depot-cart-7"], "share": [("ada-finch", "editor")]},
    {"albumName": "Granite Ledger Field Notes", "description": "Quarry counts and audit photos for the quarterly stone ledger.",
     "assets": ["granite-ledger-north-quarry", "copperfield-annex-stairwell"], "share": []},
    {"albumName": "Blue Heron Kitchen Menus", "description": "Tide-table menus and plating from the seaward kitchen at Granite Point.",
     "assets": ["blue-heron-kitchen-pass"], "share": [("rui-castellanos", "viewer")]},
]
have = {al["albumName"]: al for al in api("GET", "/albums")[0]}
for al in ALBUMS:
    cur = have.get(al["albumName"])
    if cur is None:
        cur, _ = api("POST", "/albums", {"albumName": al["albumName"], "description": al["description"],
                                         "assetIds": [A[k] for k in al["assets"]],
                                         "albumUsers": [{"userId": U[u], "role": r} for u, r in al["share"]]})
        log(f"album {al['albumName']} created")
    ids["albums"][al["albumName"]] = cur["id"]

TAGS = [("Saltmarsh Depot", "#2e7d5b", None), ("Cart Inventory", "#8a6d3b", "Saltmarsh Depot"),
        ("Copperfield Annex", "#b5562b", None), ("Tide Tables", "#2b5fb5", None)]
tags_by_value = {t["value"]: t for t in api("GET", "/tags")[0]}
for name, color, parent in TAGS:
    value = f"{parent}/{name}" if parent else name
    cur = tags_by_value.get(value)
    if cur is None:
        body = {"name": name, "color": color}
        if parent: body["parentId"] = ids["tags"][parent]
        cur, _ = api("POST", "/tags", body); log(f"tag {value} created")
    ids["tags"][value] = cur["id"]
T = ids["tags"]
for tag, assets in [("Saltmarsh Depot", ["saltmarsh-depot-cart-7"]), ("Saltmarsh Depot/Cart Inventory", ["saltmarsh-depot-cart-7"]),
                    ("Copperfield Annex", ["copperfield-annex-stairwell"]),
                    ("Tide Tables", ["blue-heron-kitchen-pass", "lighthouse-rota-lamp-room"])]:
    api("PUT", "/tags/assets", {"tagIds": [T[tag]], "assetIds": [A[a] for a in assets]})

PEOPLE = [("Mina Okafor", "1987-06-21", "granite-ledger-north-quarry"), ("Tomas Vey", "1979-11-03", "saltmarsh-depot-cart-7")]
for pname, birth, asset in PEOPLE:
    found = api("GET", f"/search/person?name={urllib.request.quote(pname)}&withHidden=true")[0]
    cur = next((p for p in found if p["name"] == pname), None)
    if cur is None:
        cur, _ = api("POST", "/people", {"name": pname, "birthDate": birth}); log(f"person {pname} created")
        api("POST", "/faces", {"assetId": A[asset], "personId": cur["id"], "imageWidth": 96, "imageHeight": 72,
                               "x": 30, "y": 20, "width": 24, "height": 24})
    ids["people"][pname] = cur["id"]

LINKS = [
    {"type": "ALBUM", "albumId": ids["albums"]["Lighthouse Rota Night Shift"], "slug": "lighthouse-night-shift",
     "description": "Night shift photos for the relief crew at Granite Point", "allowDownload": False, "showMetadata": True},
    {"type": "INDIVIDUAL", "assetIds": [A["copperfield-annex-stairwell"]], "slug": "copperfield-stairwell-repaint",
     "description": "Stairwell repaint proof for the Copperfield Annex committee", "allowDownload": True, "showMetadata": False},
]
links = {l.get("slug"): l for l in api("GET", "/shared-links")[0]}
for l in LINKS:
    cur = links.get(l["slug"])
    if cur is None: cur, _ = api("POST", "/shared-links", l); log(f"shared link {l['slug']} created")
    ids["shared_links"][l["slug"]] = cur["id"]

night = ids["albums"]["Lighthouse Rota Night Shift"]
acts = api("GET", f"/activities?albumId={night}")[0]
COMMENT = "Lens polished and wicks trimmed before the 22:00 hand-over."
cur = next((a for a in acts if a.get("comment") == COMMENT), None)
if cur is None: cur, _ = api("POST", "/activities", {"albumId": night, "type": "comment", "comment": COMMENT}); log("album comment added")
ids["activities"]["night-shift-comment"] = cur["id"]

partners = api("GET", "/partners?direction=shared-by")[0]
if not any(p["id"] == U["ada-finch"] for p in partners):
    api("POST", "/partners", {"sharedWithId": U["ada-finch"]}); log("partner share with Ada Finch created")

libs = {l["name"]: l for l in api("GET", "/libraries")[0]}
LIB = "Saltmarsh Depot Archive"
cur = libs.get(LIB)
if cur is None:
    cur, _ = api("POST", "/libraries", {"ownerId": admin_id, "name": LIB, "importPaths": [], "exclusionPatterns": ["**/scratch-negatives/**"]})
    log("external library created")
ids["libraries"][LIB] = cur["id"]

NOTE = {"title": "Granite Ledger audit due", "description": "Rui Castellanos closes the quarterly stone count on the fourteenth.",
        "level": "info", "type": "Custom", "userId": admin_id}
notes = {n["title"]: n for n in api("GET", "/notifications")[0]}
cur = notes.get(NOTE["title"])
if cur is None: cur, _ = api("POST", "/admin/notifications", NOTE); log("notification created")
ids["notifications"]["audit-due"] = cur["id"]

api("POST", "/auth/logout"); TOKEN = None; log("seed token revoked")
json.dump(ids, open(os.path.join(DIR, "seed-ids.json"), "w"), indent=1)
log("seed-ids.json written: " + json.dumps(ids))
