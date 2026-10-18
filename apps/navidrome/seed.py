#!/usr/bin/env python3
"""Seed the showcase Navidrome with a synthetic library and objects (idempotent).

`python3 seed.py music` writes ./music before the first start: 3 albums by 3 invented artists, 10 tracks, each a short
silent MPEG-1 Layer III file (stdlib struct only) with an ID3v2.3 tag (title, artist, album artist, album, track, year,
genre, composer, comment). `python3 seed.py` then creates the admin through POST /auth/createAdmin (user "rea-admin",
password generated at run time into ~/capture/navidrome/.admin, mode 600), waits for the library scan, and seeds through
the native API /api (header x-nd-authorization: Bearer <JWT>, kept in memory only): the admin's display name and email,
1 more user, the library name, 2 playlists with tracks, 2 internet radio stations, an album share and a playlist share, plus stars and ratings
through the Subsonic API. Writes seed-ids.json (ids only, no secrets). Never prints a password or a token."""
import hashlib, json, os, secrets, struct, sys, time, urllib.error, urllib.parse, urllib.request

BASE = os.environ.get("BASE_URL", "http://127.0.0.1:3233")
DIR = os.environ.get("CAPTURE_DIR", os.path.expanduser("~/capture/navidrome"))
ADMIN_FILE = os.path.join(DIR, ".admin")
USER = "rea-admin"
TOKEN = None

LIBRARY = [
    ("The Saltmarsh Lanterns", "Tide Tables", 2024, "Coastal Folk", "Mina Okafor", [
        ("Spring Tide at Granite Point", "Recorded in the lamp room on the night of the spring census."),
        ("Lamp Oil Waltz", "Three-quarter time for the 180 litres of winter lamp oil."),
        ("Saltmarsh Depot Blues", "Written while Tomas Vey rewired the tide logger."),
        ("Cart Number Seven", "A farewell to the depot cart retired on the fifth of April."),
    ]),
    ("Ada Finch Quartet", "Night Shift at the Lamp Room", 2025, "Chamber Jazz", "Ada Finch", [
        ("Twenty-Two Hundred Hours", "Opens every night shift of the Lighthouse Rota."),
        ("Brass Lens Polka", "Played on the brass lens with a chamois cloth for percussion."),
        ("Hand-over at Six", "The quiet tune for the 06:00 hand-over."),
    ]),
    ("Granite Ledger Choir", "Quarry Hymns", 2023, "Choral", "Rui Castellanos", [
        ("Four Hundred and Twelve Blocks", "A counting hymn for the north quarry tally."),
        ("Audit on the Fourteenth", "Sung by the auditors before the ledger closes."),
        ("Tidal Yard Lament", "Ninety-seven blocks left in the tidal yard."),
    ]),
]


def log(msg): print(f"[seed] {msg}", file=sys.stderr)


def id3(frames):
    def frame(fid, payload): return fid.encode() + struct.pack(">I", len(payload)) + b"\x00\x00" + payload
    body = b""
    for fid, value in frames:
        if fid == "COMM": body += frame(fid, b"\x00eng\x00" + value.encode("latin-1"))
        else: body += frame(fid, b"\x00" + value.encode("latin-1"))
    body += b"\x00" * 256  # padding
    n = len(body)
    return b"ID3\x03\x00\x00" + bytes([(n >> 21) & 0x7F, (n >> 14) & 0x7F, (n >> 7) & 0x7F, n & 0x7F]) + body


def silent_mp3(seconds):
    # MPEG-1 Layer III, 128 kbit/s, 44.1 kHz, stereo, no CRC: 417-byte frames, all-zero side info decodes as silence.
    frame = b"\xFF\xFB\x90\x00" + b"\x00" * 413
    return frame * int(seconds * 44100 / 1152)


def write_music():
    root = os.path.join(DIR, "music")
    for artist, album, year, genre, composer, tracks in LIBRARY:
        d = os.path.join(root, artist, album); os.makedirs(d, exist_ok=True)
        for n, (title, comment) in enumerate(tracks, 1):
            tag = id3([("TIT2", title), ("TPE1", artist), ("TPE2", artist), ("TALB", album), ("TRCK", f"{n}/{len(tracks)}"),
                       ("TYER", str(year)), ("TCON", genre), ("TCOM", composer), ("COMM", comment)])
            with open(os.path.join(d, f"{n:02d} - {title}.mp3"), "wb") as f: f.write(tag + silent_mp3(4 + n))
    log(f"music written under {root}")


def api(method, path, body=None, ok=(), raw=False):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method)
    req.add_header("Accept", "application/json")
    if data is not None: req.add_header("Content-Type", "application/json")
    if TOKEN: req.add_header("x-nd-authorization", "Bearer " + TOKEN)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            text = r.read()
            return (json.loads(text) if text else {}), r.status
    except urllib.error.HTTPError as e:
        if e.code in ok: return None, e.code
        raise SystemExit(f"[seed] {method} {path} -> {e.code}: {e.read().decode(errors='replace')[:300]}")


def subsonic(endpoint, pw, **params):
    salt = secrets.token_hex(6)
    q = {"u": USER, "t": hashlib.md5((pw + salt).encode()).hexdigest(), "s": salt, "v": "1.16.1", "c": "rea-seed", "f": "json", **params}
    with urllib.request.urlopen(f"{BASE}/rest/{endpoint}?{urllib.parse.urlencode(q, doseq=True)}", timeout=60) as r:
        doc = json.loads(r.read())["subsonic-response"]
    if doc.get("status") != "ok": raise SystemExit(f"[seed] subsonic {endpoint}: {doc.get('error')}")
    return doc


if len(sys.argv) > 1 and sys.argv[1] == "music":
    write_music(); sys.exit(0)

for _ in range(120):
    try:
        with urllib.request.urlopen(BASE + "/ping", timeout=5) as r:
            if r.status == 200: break
    except Exception: pass
    time.sleep(2)
else:
    raise SystemExit("[seed] Navidrome did not become ready")
log(f"navidrome ready at {BASE}")

if os.path.exists(ADMIN_FILE):
    pw = dict(l.split("=", 1) for l in open(ADMIN_FILE).read().splitlines() if "=" in l)["NAVIDROME_ADMIN_PASSWORD"]
else:
    pw = secrets.token_urlsafe(21)
    fd = os.open(ADMIN_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f: f.write(f"NAVIDROME_ADMIN_PASSWORD={pw}\n")
    log(f"wrote {ADMIN_FILE} (mode 600)")
res, st = api("POST", "/auth/createAdmin", {"username": USER, "password": pw}, ok=(403, 409, 400, 401))
if res: log("admin created through /auth/createAdmin")
login, _ = api("POST", "/auth/login", {"username": USER, "password": pw})
TOKEN = login["token"]; admin_id = login["id"]; log("seed login ok (token kept in memory only)")

subsonic("startScan", pw)
for _ in range(90):
    s = subsonic("getScanStatus", pw)["scanStatus"]
    if not s.get("scanning") and s.get("count", 0) >= 10: break
    time.sleep(2)
log(f"library scanned: {s.get('count')} tracks")

ids = {"admin": admin_id, "users": {}, "libraries": {}, "artists": {}, "albums": {}, "songs": {}, "playlists": {}, "radios": {}, "shares": {}}
api("PUT", f"/api/user/{admin_id}", {"id": admin_id, "userName": USER, "name": "Rea Admin", "email": "rea-admin@example.test", "isAdmin": True})

libs, _ = api("GET", "/api/library")
lib = libs[0]
if lib["name"] != "Saltmarsh Depot Archive":
    api("PUT", f"/api/library/{lib['id']}", {**lib, "name": "Saltmarsh Depot Archive"}); log("library renamed")
ids["libraries"]["Saltmarsh Depot Archive"] = lib["id"]

users = {u["userName"]: u for u in api("GET", "/api/user")[0]}
if "mina.okafor" not in users:
    cur, _ = api("POST", "/api/user", {"userName": "mina.okafor", "name": "Mina Okafor", "email": "mina.okafor@example.test",
                                       "password": secrets.token_urlsafe(18), "isAdmin": False, "libraryIds": [lib["id"]]})
    users["mina.okafor"] = cur; log("user mina.okafor created")
ids["users"]["mina.okafor"] = users["mina.okafor"]["id"]

for a in api("GET", "/api/artist?_start=0&_end=50")[0]:
    ids["artists"][a["name"]] = a["id"]
for a in api("GET", "/api/album?_start=0&_end=50")[0]:
    ids["albums"][a["name"]] = a["id"]
songs = api("GET", "/api/song?_start=0&_end=100&_sort=title&_order=ASC")[0]
for s in songs: ids["songs"][s["title"]] = s["id"]
S = ids["songs"]; AL = ids["albums"]
log(f"{len(ids['artists'])} artists, {len(AL)} albums, {len(S)} songs")

PLAYLISTS = [
    ("Lighthouse Rota Night Mix", "For the 22:00 to 06:00 shift; keep the volume under the foghorn.", True,
     ["Twenty-Two Hundred Hours", "Lamp Oil Waltz", "Spring Tide at Granite Point", "Hand-over at Six"]),
    ("Blue Heron Kitchen Prep", "Prep-list music for the first sitting of 36 covers.", False,
     ["Brass Lens Polka", "Cart Number Seven", "Tidal Yard Lament"]),
]
have = {p["name"]: p for p in api("GET", "/api/playlist?_start=0&_end=50")[0]}
for name, comment, public, tracks in PLAYLISTS:
    cur = have.get(name)
    if cur is None:
        cur, _ = api("POST", "/api/playlist", {"name": name, "comment": comment, "public": public})
        api("POST", f"/api/playlist/{cur['id']}/tracks", {"ids": [S[t] for t in tracks]}); log(f"playlist {name} created")
    ids["playlists"][name] = cur["id"]

RADIOS = [("Copperfield Annex Radio", "http://radio.example.test/copperfield-annex", "http://copperfield-annex.example.test/"),
          ("Granite Point Shipping Forecast", "http://radio.example.test/granite-point-forecast", "http://granite-point.example.test/")]
have = {r["name"]: r for r in api("GET", "/api/radio")[0]}
for name, stream, home in RADIOS:
    cur = have.get(name)
    if cur is None: cur, _ = api("POST", "/api/radio", {"name": name, "streamUrl": stream, "homePageUrl": home}); log(f"radio {name} created")
    ids["radios"][name] = cur["id"]

shares = api("GET", "/api/share")[0]
SHARES = [("quarry-hymns", AL["Quarry Hymns"], "album", "Quarry Hymns for the Granite Ledger auditors", False),
          ("night-mix", ids["playlists"]["Lighthouse Rota Night Mix"], "playlist", "Night Mix for the relief crew at Granite Point", True)]
for key, rid, rtype, desc, dl in SHARES:
    cur = next((s for s in shares if s.get("description") == desc), None)
    if cur is None:
        cur, _ = api("POST", "/api/share", {"resourceIds": rid, "resourceType": rtype, "description": desc, "downloadable": dl})
        log(f"{rtype} share created")
    ids["shares"][key] = cur["id"]

subsonic("star", pw, albumId=AL["Night Shift at the Lamp Room"], id=S["Spring Tide at Granite Point"])
subsonic("setRating", pw, id=S["Lamp Oil Waltz"], rating=5)
subsonic("setRating", pw, id=S["Audit on the Fourteenth"], rating=3)
subsonic("setRating", pw, id=AL["Tide Tables"], rating=4)
log("stars and ratings set")
TOKEN = None
json.dump(ids, open(os.path.join(DIR, "seed-ids.json"), "w"), indent=1)
log("seed-ids.json written: " + json.dumps(ids))
