#!/usr/bin/env python3
"""Seed the showcase PhotoPrism (public auth mode, loopback only) with synthetic, obviously invented content (idempotent).

Generates 12 PNG images with the stdlib (zlib + struct: gradients, stripes, rings, checks; 160-640 px, each under 60 KB),
copies them into the originals volume in three folders, indexes them through POST /api/v1/index, then sets titles,
captions, keywords, notes, artists, dates and coordinates through PUT /api/v1/photos/{uid}, marks favourites, attaches
labels, and creates four albums holding the photos. Removes any other album (scratch albums left by an earlier capture).
Writes seed-ids.json (uids and names only).

`python3 seed.py admin` (before `docker compose up`) writes .admin (mode 600): user=rea-admin and a generated password that
compose passes to PhotoPrism as the initial admin password. In public auth mode the UI needs no login, but its session
calls still answer with the fixed public-mode session id and access token (the UI sends the token back as X-Auth-Token and
GET /api/v1/session echoes it as access_token). This script reads both through POST /api/v1/session and stores them in
.admin as public_session_token and public_access_token; the scenario declares them as secrets, so REA redacts them from
every recorded body. Nothing secret is printed."""
import json, os, secrets, struct, subprocess, sys, tempfile, time, urllib.error, urllib.request, zlib

BASE = os.environ.get("BASE_URL", "http://127.0.0.1:3401")
DIR = os.path.dirname(os.path.abspath(__file__))
CONTAINER = "rea-photoprism-photoprism-1"
ADMIN_FILE = os.path.join(DIR, ".admin")


def read_admin():
    if not os.path.exists(ADMIN_FILE): return {}
    return dict(line.split("=", 1) for line in open(ADMIN_FILE).read().splitlines() if "=" in line)


def write_admin(kv):
    fd = os.open(ADMIN_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f: f.write("".join(f"{k}={v}\n" for k, v in kv.items()))
    os.chmod(ADMIN_FILE, 0o600)


def log(msg): print(f"[seed] {msg}", file=sys.stderr)


def api(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method)
    req.add_header("Accept", "application/json")
    if data is not None: req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            raw = r.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raise SystemExit(f"[seed] {method} {path} -> {e.code}: {e.read().decode(errors='replace')[:300]}")


def png(width, height, pixel):
    """Encode an RGB PNG; pixel(x, y) -> (r, g, b). Rows use the Sub filter so gradients and stripes compress well."""
    rows = bytearray()
    for y in range(height):
        rows.append(1); prev = (0, 0, 0)
        for x in range(width):
            p = pixel(x, y)
            rows.extend(((p[0] - prev[0]) & 255, (p[1] - prev[1]) & 255, (p[2] - prev[2]) & 255)); prev = p
    def chunk(tag, data): return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(bytes(rows), 9)) + chunk(b"IEND", b""))


def lerp(a, b, t): return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def hgrad(c1, c2, w): return lambda x, y: lerp(c1, c2, x / max(1, w - 1))
def vgrad(c1, c2, h): return lambda x, y: lerp(c1, c2, y / max(1, h - 1))
def stripes(c1, c2, band): return lambda x, y: c1 if (x // band) % 2 == 0 else c2
def hstripes(c1, c2, band): return lambda x, y: c1 if (y // band) % 2 == 0 else c2
def checks(c1, c2, cell): return lambda x, y: c1 if ((x // cell) + (y // cell)) % 2 == 0 else c2
def rings(c1, c2, cx, cy, band): return lambda x, y: c1 if int(((x - cx) ** 2 + (y - cy) ** 2) ** 0.5) // band % 2 == 0 else c2
def disc(bg, fg, cx, cy, r): return lambda x, y: fg if (x - cx) ** 2 + (y - cy) ** 2 <= r * r else bg
def diag(c1, c2, band): return lambda x, y: c1 if ((x + y) // band) % 2 == 0 else c2

NAVY, SKY, ORANGE, SAND, TEAL, RED, GREEN, CREAM, PURPLE, GOLD, SLATE, WHITE = (
    (20, 40, 110), (120, 180, 235), (240, 130, 30), (225, 200, 150), (20, 140, 140), (200, 40, 40),
    (40, 150, 60), (245, 235, 210), (110, 50, 150), (230, 180, 30), (90, 100, 115), (250, 250, 250))

# file (folder/name), size, painter, title, caption, keywords, notes, artist, taken, lat, lng, labels, favorite
PHOTOS = [
    ("saltmarsh-depot/20240312_071500.png", (640, 360), lambda w, h: vgrad(SKY, NAVY, h), "Saltmarsh Depot dawn sky gradient",
     "Sky fading from pale blue to navy over the Saltmarsh Depot loading bay", "saltmarsh, dawn, gradient", "Frame SD-0312 from the depot roof camera",
     "Ada Finch", "2024-03-12T07:15:00Z", 53.6271, 0.2214, ["Tide Gauge"], True),
    ("saltmarsh-depot/20240312_073000.png", (480, 320), lambda w, h: hstripes(NAVY, WHITE, 20), "Depot tide board stripes",
     "Navy and white horizontal bands painted on the Saltmarsh Depot tide board", "saltmarsh, stripes, tide board", "Sixteen bands, each twenty pixels tall",
     "Ada Finch", "2024-03-12T07:30:00Z", 53.6273, 0.2219, ["Tide Gauge", "Signal Paint"], False),
    ("saltmarsh-depot/20240313_160500.png", (400, 400), lambda w, h: rings(TEAL, SAND, 200, 200, 25), "Teal ripple rings on the slipway",
     "Concentric teal and sand rings around the Saltmarsh Depot slipway drain", "saltmarsh, rings, slipway", "Ring band width twenty-five pixels",
     "Rui Castellanos", "2024-03-13T16:05:00Z", 53.6268, 0.2207, ["Water Pattern"], False),
    ("saltmarsh-depot/20240314_090000.png", (320, 240), lambda w, h: checks(GOLD, SLATE, 40), "Gold and slate crate checks",
     "Chequered gold and slate crate lids stacked at the Saltmarsh Depot", "saltmarsh, checks, crates", "Crate lot SD-77 counted by Rui Castellanos",
     "Rui Castellanos", "2024-03-14T09:00:00Z", 53.6275, 0.2225, ["Crate Lot"], True),
    ("copperfield-annex/20240402_101000.png", (640, 427), lambda w, h: hgrad(ORANGE, RED, w), "Copperfield Annex kiln glow",
     "Orange to red sideways glow from the Copperfield Annex kiln door", "copperfield, kiln, gradient", "Kiln four at nine hundred degrees",
     "Mina Okafor", "2024-04-02T10:10:00Z", 52.4862, -1.8904, ["Kiln Light"], True),
    ("copperfield-annex/20240402_103500.png", (360, 360), lambda w, h: disc(CREAM, ORANGE, 180, 180, 120), "Copper disc on cream",
     "A single orange copper disc centred on a cream workbench", "copperfield, disc, copper", "Disc diameter two hundred forty pixels",
     "Mina Okafor", "2024-04-02T10:35:00Z", 52.4865, -1.8911, ["Kiln Light", "Signal Paint"], False),
    ("copperfield-annex/20240403_141500.png", (500, 300), lambda w, h: diag(PURPLE, CREAM, 30), "Annex diagonal awning",
     "Purple and cream diagonal awning stripes over the Copperfield Annex door", "copperfield, diagonal, awning", "Awning repainted in week fourteen",
     "Tomas Vey", "2024-04-03T14:15:00Z", 52.4859, -1.8899, ["Signal Paint"], False),
    ("copperfield-annex/20240404_083000.png", (240, 320), lambda w, h: stripes(GREEN, CREAM, 16), "Green ledger spines",
     "Green and cream vertical spines of the Copperfield Annex ledgers", "copperfield, stripes, ledgers", "Shelf C holds fifteen ledger spines",
     "Tomas Vey", "2024-04-04T08:30:00Z", 52.4861, -1.8902, ["Crate Lot"], False),
    ("blue-heron-kitchen/20240520_190000.png", (480, 480), lambda w, h: rings(SKY, WHITE, 240, 240, 30), "Blue Heron Kitchen plate rings",
     "Sky blue and white rings of the Blue Heron Kitchen tasting plate", "heron, plate, rings", "Plate service for table nine",
     "Ada Finch", "2024-05-20T19:00:00Z", 50.3712, -4.1427, ["Water Pattern"], True),
    ("blue-heron-kitchen/20240520_193000.png", (300, 200), lambda w, h: vgrad(GOLD, ORANGE, h), "Heron saffron broth gradient",
     "Gold to orange gradient of the Blue Heron Kitchen saffron broth", "heron, broth, gradient", "Broth batch BH-12 for the tide-table menu",
     "Mina Okafor", "2024-05-20T19:30:00Z", 50.3714, -4.1431, ["Kiln Light"], False),
    ("blue-heron-kitchen/20240521_120000.png", (420, 280), lambda w, h: checks(TEAL, CREAM, 35), "Teal tablecloth checks",
     "Teal and cream chequered tablecloth at the Blue Heron Kitchen window seat", "heron, checks, tablecloth", "Window seat booked by Tomas Vey",
     "Tomas Vey", "2024-05-21T12:00:00Z", 50.3710, -4.1425, ["Signal Paint"], False),
    ("blue-heron-kitchen/20240522_210000.png", (200, 160), lambda w, h: disc(NAVY, GOLD, 100, 80, 50), "Lantern moon over the heron pier",
     "Gold lantern disc against a navy night above the Blue Heron Kitchen pier", "heron, night, lantern", "Lantern lit at twenty-one hundred",
     "Rui Castellanos", "2024-05-22T21:00:00Z", 50.3708, -4.1440, ["Tide Gauge"], False),
]

ALBUMS = [
    ("Saltmarsh Depot Survey", "Roof camera frames and tide boards from the Saltmarsh Depot spring survey.", "Survey", "Saltmarsh Depot",
     [0, 1, 2, 3], True),
    ("Copperfield Annex Workshop", "Kiln, copper and ledger studies from the Copperfield Annex workshop week.", "Workshop", "Copperfield Annex",
     [4, 5, 6, 7], False),
    ("Blue Heron Kitchen Tasting Night", "Plates, broth and lanterns from the Blue Heron Kitchen tasting night.", "Kitchen", "Blue Heron Kitchen",
     [8, 9, 10, 11], False),
    ("Granite Ledger Colour Study", "Every frame with a bold painted pattern, picked by Ada Finch for the Granite Ledger colour study.", "Study", "Lighthouse Rota",
     [1, 3, 5, 6, 10], True),
]


def wait_ready():
    for _ in range(120):
        try:
            with urllib.request.urlopen(BASE + "/api/v1/status", timeout=5) as r:
                if r.status == 200: return
        except Exception: pass
        time.sleep(2)
    raise SystemExit("[seed] PhotoPrism did not become ready")


def put_originals():
    tmp = tempfile.mkdtemp(prefix="pp-seed-")
    for p in PHOTOS:
        rel, (w, h), painter = p[0], p[1], p[2]
        data = png(w, h, painter(w, h))
        if len(data) > 60_000: raise SystemExit(f"[seed] {rel} is {len(data)} bytes; over 60 KB")
        out = os.path.join(tmp, rel); os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "wb") as f: f.write(data)
    for folder in sorted({p[0].split("/")[0] for p in PHOTOS}):
        subprocess.run(["docker", "cp", os.path.join(tmp, folder), f"{CONTAINER}:/photoprism/originals/"], check=True, capture_output=True)
    log(f"copied {len(PHOTOS)} generated PNGs into the originals volume")


if sys.argv[1:] == ["admin"]:
    kv = read_admin()
    if "password" not in kv:
        kv = {"user": "rea-admin", "password": secrets.token_urlsafe(18)}; write_admin(kv); log(f"wrote {ADMIN_FILE} (mode 600)")
    else: log(".admin already present")
    sys.exit(0)

wait_ready()
kv = read_admin()
if "password" not in kv: raise SystemExit("[seed] run `python3 seed.py admin` before starting compose")
pub = api("POST", "/api/v1/session", {})
kv["public_session_token"] = pub["session_id"]; kv["public_access_token"] = pub["access_token"]; write_admin(kv)
log("stored the public session id and access token in .admin for the scenario's declared secrets")
put_originals()
api("POST", "/api/v1/index", {"path": "/", "rescan": False, "cleanup": False}); log("index finished")

found = {}
for _ in range(30):
    items = api("GET", "/api/v1/photos?count=100&offset=0&merged=true&order=oldest&public=false&quality=0")
    for it in items:
        for f in it.get("Files") or []:
            found[f.get("Name")] = it["UID"]
        found.setdefault(it.get("FileName"), it["UID"])
    if all(p[0] in found for p in PHOTOS): break
    time.sleep(2)
missing = [p[0] for p in PHOTOS if p[0] not in found]
if missing: raise SystemExit(f"[seed] not indexed: {missing}")

ids = {"photos": {}, "albums": {}, "labels": {}}
for p in PHOTOS:
    rel, _, _, title, caption, keywords, notes, artist, taken, lat, lng, labels, fav = p
    uid = found[rel]
    photo_id = api("GET", f"/api/v1/photos/{uid}")["ID"]   # Details are only saved when they name their PhotoID
    api("PUT", f"/api/v1/photos/{uid}", {
        "Title": title, "TitleSrc": "manual", "Caption": caption, "CaptionSrc": "manual",
        "TakenAt": taken, "TakenAtLocal": taken, "TakenSrc": "manual", "TimeZone": "UTC",
        "Year": int(taken[:4]), "Month": int(taken[5:7]), "Day": int(taken[8:10]),
        "Lat": lat, "Lng": lng, "PlaceSrc": "manual",
        "Details": {"PhotoID": photo_id, "Keywords": keywords, "KeywordsSrc": "manual", "Notes": notes, "NotesSrc": "manual",
                    "Subject": title, "SubjectSrc": "manual", "Artist": artist, "ArtistSrc": "manual",
                    "Copyright": "Synthetic image, Lighthouse Rota archive", "CopyrightSrc": "manual",
                    "License": "CC0 synthetic test image", "LicenseSrc": "manual"},
    })
    have = {l["Label"]["Name"] for l in (api("GET", f"/api/v1/photos/{uid}").get("Labels") or []) if l.get("Label")}
    for name in labels:
        if name not in have: api("POST", f"/api/v1/photos/{uid}/label", {"Name": name, "Priority": 10})
    if fav: api("POST", f"/api/v1/photos/{uid}/like")
    ids["photos"][title] = uid
log(f"{len(PHOTOS)} photos titled, labelled and dated")

for lab in api("GET", "/api/v1/labels?count=100&all=true"):
    ids["labels"][lab["Name"]] = lab["UID"]

existing = api("GET", "/api/v1/albums?count=100&type=album")
seeded_titles = {a[0] for a in ALBUMS}
for a in existing:
    if a["Title"] not in seeded_titles:
        api("DELETE", f"/api/v1/albums/{a['UID']}"); log(f"removed leftover album {a['Title']}")
existing = [a for a in existing if a["Title"] in seeded_titles]
have = {a["Title"]: a["UID"] for a in existing}
for title, desc, cat, loc, members, fav in ALBUMS:
    uid = have.get(title)
    if not uid:
        uid = api("POST", "/api/v1/albums", {"Title": title, "Description": desc, "Category": cat, "Location": loc, "Favorite": fav})["UID"]
        log(f"album {title} created")
    api("PUT", f"/api/v1/albums/{uid}", {"Title": title, "Description": desc, "Category": cat, "Location": loc, "Favorite": fav,
                                          "Notes": f"Curated by {PHOTOS[members[0]][7]} for the showcase."})
    api("POST", f"/api/v1/albums/{uid}/photos", {"photos": [found[PHOTOS[i][0]] for i in members]})
    ids["albums"][title] = uid
log(f"{len(ALBUMS)} albums ready")

with open(os.path.join(DIR, "seed-ids.json"), "w") as f: json.dump(ids, f, indent=1)
log("wrote seed-ids.json")
