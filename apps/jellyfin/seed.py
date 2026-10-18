#!/usr/bin/env python3
"""Generate tiny synthetic media, start and seed the showcase Jellyfin through its REST API (idempotent).

1. Writes ~/capture/jellyfin/media/ with python3 stdlib only: one-second silent WAV tracks carrying RIFF INFO tags
   (title, artist, album, genre, year, track, comment), small PNG pictures (zlib + struct) and two minimal EPUB books
   (zipfile, with an OPF title, creator, description, publisher and subject). compose.yml mounts it read-only at /media.
2. Starts the compose project if Jellyfin is not answering, then completes the startup wizard through /Startup/*
   (admin rea-admin, password generated at run time into ~/capture/jellyfin/.admin, mode 600, password only).
3. Signs in with POST /Users/AuthenticateByName (the access token stays in process memory) and creates three libraries
   over the media folders, scans them, sets an Overview and tags on the albums, photos and books, creates two more users,
   a playlist, a collection and favourites. Writes seed-ids.json (ids only, no secrets). Never prints the password."""
import json, os, secrets, struct, subprocess, sys, time, urllib.error, urllib.parse, urllib.request, zipfile, zlib

BASE = os.environ.get("BASE_URL", "http://127.0.0.1:3224")
DIR = os.environ.get("CAPTURE_DIR", os.path.expanduser("~/capture/jellyfin"))
MEDIA = os.path.join(DIR, "media")
ADMIN_FILE = os.path.join(DIR, ".admin")
USER = "rea-admin"
CLIENT = 'MediaBrowser Client="rea-seed", Device="seed-script", DeviceId="rea-seed-0001", Version="1.0.0"'


def log(msg): print(f"[seed] {msg}", file=sys.stderr)


# ---------- 1. synthetic media ----------
MUSIC = {
    ("Ada Finch Quartet", "Lighthouse Rota Suite", "Coastal Folk", 2026): [
        ("Granite Ledger", "Opening theme of the suite, played on the north gallery."),
        ("Tide Table Waltz", "A slow waltz for the January tide tables."),
        ("Lamp Oil Reel", "A quick reel counted in 180 beats, one per litre."),
    ],
    ("Blue Heron Kitchen Band", "Saltmarsh Depot Sessions", "Kitchen Jazz", 2025): [
        ("Copperfield Annex Shuffle", "Recorded live in the annex mezzanine."),
        ("Kelp Broth Blues", "Written for the 22:00 shift change."),
    ],
}
PHOTOS = {"Saltmarsh Depot Survey": [("North Quay Bollards", (40, 90, 140)), ("Granite Ledger Cart Seven", (120, 110, 100)),
                                     ("Copperfield Annex Roof", (180, 90, 50))]}
BOOKS = [("The Rye Cracker Almanac", "Tomas Vey", "Twice-baked recipes and the Monday packing rota of the Copperfield Annex.",
          "Copperfield Annex Press", "Baking"),
         ("Quayside Market Ledger", "Mina Okafor", "Tuesday stall accounts from the Blue Heron Kitchen Market, kept in iron-gall ink.",
          "Lighthouse Rota Press", "Accounts")]


def info_chunk(tags):
    body = b"INFO"
    for key, val in tags:
        data = val.encode() + b"\x00"
        if len(data) % 2: data += b"\x00"
        body += key.encode() + struct.pack("<I", len(data)) + data
    return b"LIST" + struct.pack("<I", len(body)) + body


def write_wav(path, tags, seconds=1, rate=8000):
    pcm = b"\x80" * (rate * seconds)  # unsigned 8-bit silence
    fmt = b"fmt " + struct.pack("<IHHIIHH", 16, 1, 1, rate, rate, 1, 8)
    data = b"data" + struct.pack("<I", len(pcm)) + pcm
    lst = info_chunk(tags)
    riff = b"WAVE" + fmt + lst + data
    open(path, "wb").write(b"RIFF" + struct.pack("<I", len(riff)) + riff)


def write_png(path, rgb, w=64, h=48):
    raw = b"".join(b"\x00" + bytes(rgb) * w for _ in range(h))
    def chunk(t, d): return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    open(path, "wb").write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
                           + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def write_epub(path, title, author, desc, publisher, subject):
    uid = "urn:uuid:" + "-".join(("rea0", title.lower().replace(" ", "")[:12]))
    opf = f"""<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="2.0" unique-identifier="bookid">
 <metadata xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:opf="http://www.idpf.org/2007/opf">
  <dc:title>{title}</dc:title><dc:creator opf:role="aut">{author}</dc:creator><dc:description>{desc}</dc:description>
  <dc:publisher>{publisher}</dc:publisher><dc:subject>{subject}</dc:subject><dc:language>en</dc:language>
  <dc:date>2026-03-14</dc:date><dc:identifier id="bookid">{uid}</dc:identifier>
 </metadata>
 <manifest><item id="ch1" href="ch1.xhtml" media-type="application/xhtml+xml"/><item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/></manifest>
 <spine toc="ncx"><itemref idref="ch1"/></spine>
</package>"""
    ncx = f"""<?xml version="1.0" encoding="UTF-8"?><ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1"><head><meta name="dtb:uid" content="{uid}"/></head><docTitle><text>{title}</text></docTitle><navMap><navPoint id="p1" playOrder="1"><navLabel><text>One</text></navLabel><content src="ch1.xhtml"/></navPoint></navMap></ncx>"""
    ch1 = f"""<?xml version="1.0" encoding="UTF-8"?><html xmlns="http://www.w3.org/1999/xhtml"><head><title>{title}</title></head><body><h1>{title}</h1><p>{desc}</p></body></html>"""
    container = """<?xml version="1.0"?><container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles></container>"""
    with zipfile.ZipFile(path, "w") as z:
        z.writestr(zipfile.ZipInfo("mimetype"), "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        z.writestr("META-INF/container.xml", container, compress_type=zipfile.ZIP_DEFLATED)
        z.writestr("OEBPS/content.opf", opf, compress_type=zipfile.ZIP_DEFLATED)
        z.writestr("OEBPS/toc.ncx", ncx, compress_type=zipfile.ZIP_DEFLATED)
        z.writestr("OEBPS/ch1.xhtml", ch1, compress_type=zipfile.ZIP_DEFLATED)


def make_media():
    if os.path.exists(os.path.join(MEDIA, ".done")): return
    for (artist, album, genre, year), tracks in MUSIC.items():
        d = os.path.join(MEDIA, "music", artist, album); os.makedirs(d, exist_ok=True)
        for n, (title, comment) in enumerate(tracks, 1):
            write_wav(os.path.join(d, f"{n:02d} - {title}.wav"), [("INAM", title), ("IART", artist), ("IPRD", album), ("IGNR", genre),
                                                                  ("ICRD", str(year)), ("ITRK", str(n)), ("ICMT", comment)])
    for album, pics in PHOTOS.items():
        d = os.path.join(MEDIA, "photos", album); os.makedirs(d, exist_ok=True)
        for name, rgb in pics: write_png(os.path.join(d, name.lower().replace(" ", "-") + ".png"), rgb)
    d = os.path.join(MEDIA, "books"); os.makedirs(d, exist_ok=True)
    for title, author, desc, pub, subj in BOOKS:
        write_epub(os.path.join(d, f"{title}.epub"), title, author, desc, pub, subj)
    open(os.path.join(MEDIA, ".done"), "w").write("generated by seed.py\n")
    log(f"media written under {MEDIA}")


# ---------- 2. start + wizard ----------
def load_or_create_admin():
    if os.path.exists(ADMIN_FILE):
        kv = dict(line.split("=", 1) for line in open(ADMIN_FILE).read().splitlines() if "=" in line)
        return kv["JELLYFIN_ADMIN_PASSWORD"]
    pw = secrets.token_urlsafe(21)
    fd = os.open(ADMIN_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f: f.write(f"JELLYFIN_ADMIN_PASSWORD={pw}\n")  # the user name is a constant, not a secret
    log(f"wrote {ADMIN_FILE} (mode 600)")
    return pw


TOKEN = None


def api(method, path, body=None, ok=(), query=None):
    url = BASE + path + ("?" + urllib.parse.urlencode(query, doseq=True) if query else "")
    data = json.dumps(body).encode() if body is not None else (b"" if method in ("POST", "PUT") else None)
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Accept", "application/json")
    if data is not None: req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", CLIENT + (f', Token="{TOKEN}"' if TOKEN else ""))
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            raw = r.read()
            try: return json.loads(raw) if raw else {}
            except ValueError: return {}
    except urllib.error.HTTPError as e:
        if e.code in ok: return None
        detail = e.read().decode(errors="replace")[:400]
        raise SystemExit(f"[seed] {method} {path} -> {e.code}: {detail}")


def public_info():
    try:
        with urllib.request.urlopen(BASE + "/System/Info/Public", timeout=5) as r: return json.loads(r.read())
    except Exception: return None


make_media()
pw = load_or_create_admin()
if public_info() is None:
    subprocess.run(["docker", "compose", "-p", "rea-jellyfin", "-f", os.path.join(DIR, "compose.yml"), "up", "-d"], check=True, cwd=DIR,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    log("compose project rea-jellyfin started")
for _ in range(150):
    pub = public_info()
    if pub: break
    time.sleep(2)
else:
    raise SystemExit("[seed] Jellyfin did not answer")
log(f"jellyfin {pub.get('Version')} answering at {BASE}")
if not pub.get("StartupWizardCompleted"):
    for _ in range(30):  # the wizard endpoints answer 503 until the server has finished starting
        if api("GET", "/Startup/Configuration", ok=(503,)) is not None: break
        time.sleep(2)
    api("POST", "/Startup/Configuration", {"UICulture": "en-US", "MetadataCountryCode": "US", "PreferredMetadataLanguage": "en"})
    api("GET", "/Startup/User")
    api("POST", "/Startup/User", {"Name": USER, "Password": pw})
    api("POST", "/Startup/RemoteAccess", {"EnableRemoteAccess": True, "EnableAutomaticPortMapping": False})
    api("POST", "/Startup/Complete")
    log("startup wizard completed (admin rea-admin)")
    time.sleep(3)

auth = api("POST", "/Users/AuthenticateByName", {"Username": USER, "Pw": pw})
TOKEN = auth["AccessToken"]; uid = auth["User"]["Id"]; log("signed in as rea-admin")
ids = {"users": {USER: uid}}

# ---------- 3. libraries ----------
LIBS = [("Lighthouse Rota Music", "music", "/media/music"), ("Saltmarsh Depot Photos", "homevideos", "/media/photos"),
        ("Copperfield Annex Reading Room", "books", "/media/books")]
existing = {f["Name"]: f for f in api("GET", "/Library/VirtualFolders")}
for name, ctype, path in LIBS:
    if name not in existing:
        api("POST", "/Library/VirtualFolders", {"LibraryOptions": {"EnableRealtimeMonitor": False, "SaveLocalMetadata": False,
                                                                   "PathInfos": [{"Path": path}]}},
            query={"name": name, "collectionType": ctype, "refreshLibrary": "false"})
        log(f"library {name} created")
api("POST", "/Library/Refresh")
want = sum(len(t) for t in MUSIC.values())
for _ in range(90):
    time.sleep(2)
    got = api("GET", "/Items", query={"userId": uid, "recursive": "true", "includeItemTypes": "Audio,Photo,Book"})
    if got["TotalRecordCount"] >= want + sum(len(p) for p in PHOTOS.values()) + len(BOOKS): break
log(f"scan found {got['TotalRecordCount']} audio/photo/book items")
ids["libraries"] = {f["Name"]: f["ItemId"] for f in api("GET", "/Library/VirtualFolders")}


def items(types, **extra):
    q = {"userId": uid, "recursive": "true", "includeItemTypes": types, "fields": "Overview,Tags,Genres,Path"} | extra
    return api("GET", "/Items", query=q)["Items"]


def update(item_id, **changes):
    """Edit metadata the way the web client's editor does: read the full item, change fields, post it back."""
    dto = api("GET", f"/Items/{item_id}", query={"userId": uid})
    dto.update(changes)
    api("POST", f"/Items/{item_id}", dto)


ALBUM_NOTES = {"Lighthouse Rota Suite": ("Three tunes the Ada Finch Quartet plays for the winter rota.", ["night shift", "lighthouse"]),
               "Saltmarsh Depot Sessions": ("Kitchen jazz taped between sittings at Blue Heron Kitchen.", ["kitchen", "live"])}
for a in items("MusicAlbum"):
    ids.setdefault("albums", {})[a["Name"]] = a["Id"]
    note, tags = ALBUM_NOTES.get(a["Name"], (None, None))
    if note and a.get("Overview") != note: update(a["Id"], Overview=note, Tags=tags); log(f"album {a['Name']} annotated")
for t in items("Audio"): ids.setdefault("tracks", {})[t["Name"]] = t["Id"]
for ar in api("GET", "/Artists", query={"userId": uid})["Items"]:
    ids.setdefault("artists", {})[ar["Name"]] = ar["Id"]
    note = {"Ada Finch Quartet": "Lamp-room quartet led by Ada Finch, keeper of the tide tables.",
            "Blue Heron Kitchen Band": "House band of Blue Heron Kitchen, fronted by Marisol Okonkwo-Reyes."}.get(ar["Name"])
    if note and api("GET", f"/Artists/{urllib.parse.quote(ar['Name'])}", query={"userId": uid}).get("Overview") != note:
        update(ar["Id"], Overview=note); log(f"artist {ar['Name']} annotated")
PHOTO_NOTES = {"north-quay-bollards": "Bollards 1 to 6 on the north quay, surveyed by Rui Castellanos.",
               "granite-ledger-cart-seven": "Cart number 7, retired after the quarterly stone count.",
               "copperfield-annex-roof": "Slate roof of the Copperfield Annex after the October gale."}
for p in items("Photo"):
    ids.setdefault("photos", {})[p["Name"]] = p["Id"]
    note = PHOTO_NOTES.get(p["Name"].lower().replace(" ", "-"))
    if note and p.get("Overview") != note: update(p["Id"], Overview=note); log(f"photo {p['Name']} annotated")
for pa in items("PhotoAlbum"): ids.setdefault("photo_albums", {})[pa["Name"]] = pa["Id"]
BOOK_NOTES = {b[0]: b for b in BOOKS}
for b in items("Book"):
    ids.setdefault("books", {})[b["Name"]] = b["Id"]
    meta = BOOK_NOTES.get(b["Name"])
    if meta and b.get("Overview") != meta[2]: update(b["Id"], Overview=meta[2], Tags=[meta[4]]); log(f"book {b['Name']} annotated")

# ---------- users, playlist, collection, favourites ----------
users = {u["Name"]: u["Id"] for u in api("GET", "/Users")}
for name in ("Ada Finch", "Rui Castellanos"):
    if name not in users:
        users[name] = api("POST", "/Users/New", {"Name": name, "Password": secrets.token_urlsafe(18)})["Id"]; log(f"user {name} created")
ids["users"] = users
tr = ids["tracks"]
pl = [p for p in items("Playlist") if p["Name"] == "Night Watch Mix"]
if pl: plid = pl[0]["Id"]
else:
    plid = api("POST", "/Playlists", {"Name": "Night Watch Mix", "Ids": [tr["Tide Table Waltz"], tr["Kelp Broth Blues"], tr["Granite Ledger"]],
                                      "UserId": uid, "MediaType": "Audio"})["Id"]
    log("playlist Night Watch Mix created")
ids["playlists"] = {"Night Watch Mix": plid}
pl = [p for p in items("Playlist") if p["Name"] == "Night Watch Mix"]
if pl and pl[0].get("Overview") != "Three tracks for the 22:00 to 06:00 watch.":
    update(plid, Overview="Three tracks for the 22:00 to 06:00 watch."); log("playlist annotated")
bs = [b for b in items("BoxSet") if b["Name"] == "Granite Ledger Sessions"]
if bs: bsid = bs[0]["Id"]
else:
    alb = ids["albums"]
    bsid = api("POST", "/Collections", query={"name": "Granite Ledger Sessions", "ids": f"{alb['Lighthouse Rota Suite']},{alb['Saltmarsh Depot Sessions']}"})["Id"]
    log("collection Granite Ledger Sessions created")
ids["collections"] = {"Granite Ledger Sessions": bsid}
bs = [b for b in items("BoxSet") if b["Name"] == "Granite Ledger Sessions"]
if bs and bs[0].get("Overview") != "Every recording made for the Lighthouse Rota, in one shelf.":
    update(bsid, Overview="Every recording made for the Lighthouse Rota, in one shelf."); log("collection annotated")
for t in ("Lamp Oil Reel", "Copperfield Annex Shuffle"): api("POST", f"/UserFavoriteItems/{tr[t]}", query={"userId": uid})

# Remove scratch playlists left behind by an interrupted capture so every capture starts from the same state.
for p in items("Playlist"):
    if p["Name"].startswith("Rea Scratch"): api("DELETE", f"/Items/{p['Id']}"); log(f"removed leftover scratch playlist {p['Id']}")

api("POST", "/Sessions/Logout")
TOKEN = None
json.dump(ids, open(os.path.join(DIR, "seed-ids.json"), "w"), indent=1)
log("seed-ids.json written: " + json.dumps({k: len(v) for k, v in ids.items()}))
