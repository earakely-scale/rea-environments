#!/usr/bin/env python3
"""Seed the showcase Komga with synthetic content through its REST API (idempotent by name).

Run make_library.py first (it writes the CBZ files that compose mounts read-only at /data). This script claims the
server for rea-admin@example.test (POST /api/v1/claim, password generated at run time into ~/capture/komga/.admin, mode
600), then uses basic auth to: create the library "Copperfield Annex Shelf" on /data/annex and wait for the scan and
analysis (3 series, 7 books from ComicInfo.xml), patch series metadata (summary, status, age rating, extra tags), create
2 collections and 2 read lists, create 2 users, and record read progress on 2 books. Writes seed-ids.json (ids only).
Never prints the password."""
import base64, json, os, secrets, sys, time, urllib.error, urllib.request

BASE = os.environ.get("BASE_URL", "http://127.0.0.1:3231")
DIR = os.environ.get("CAPTURE_DIR", os.path.expanduser("~/capture/komga"))
ADMIN_FILE = os.path.join(DIR, ".admin")
EMAIL = "rea-admin@example.test"


def log(msg): print(f"[seed] {msg}", file=sys.stderr)


def password():
    if os.path.exists(ADMIN_FILE):
        return dict(l.split("=", 1) for l in open(ADMIN_FILE).read().splitlines() if "=" in l)["KOMGA_ADMIN_PASSWORD"]
    pw = "Rea-" + secrets.token_urlsafe(18)
    fd = os.open(ADMIN_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f: f.write(f"KOMGA_ADMIN_PASSWORD={pw}\n")  # the login email is the fixed constant EMAIL
    log(f"wrote {ADMIN_FILE} (mode 600)"); return pw


def api(method, path, body=None, headers=None, auth=True):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method)
    req.add_header("Accept", "application/json")
    if data is not None: req.add_header("Content-Type", "application/json")
    if auth: req.add_header("Authorization", AUTH["h"])
    for k, v in (headers or {}).items(): req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read(); return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raise SystemExit(f"[seed] {method} {path} -> {e.code}: {e.read().decode(errors='replace')[:300]}")


AUTH = {"h": ""}
for _ in range(90):
    try:
        with urllib.request.urlopen(BASE + "/api/v1/claim", timeout=5) as r:
            claim = json.loads(r.read()); break
    except Exception: pass
    time.sleep(3)
else: raise SystemExit("[seed] Komga did not become ready")
pw = password()
if not claim.get("isClaimed"):
    api("POST", "/api/v1/claim", headers={"X-Komga-Email": EMAIL, "X-Komga-Password": pw}, auth=False); log("server claimed for rea-admin")
AUTH["h"] = "Basic " + base64.b64encode(f"{EMAIL}:{pw}".encode()).decode()
log(f"komga ready at {BASE}")

ids = {"library": None, "series": {}, "books": {}, "collections": {}, "readlists": {}, "users": {}}
libs = {l["name"]: l for l in api("GET", "/api/v1/libraries")}
lib = libs.get("Copperfield Annex Shelf")
if lib is None:
    lib = api("POST", "/api/v1/libraries", {
        "name": "Copperfield Annex Shelf", "root": "/data/annex", "importComicInfoBook": True, "importComicInfoSeries": True,
        "importComicInfoCollection": False, "importComicInfoReadList": False, "importComicInfoSeriesAppendVolume": True,
        "importEpubBook": True, "importEpubSeries": True, "importMylarSeries": True, "importLocalArtwork": True, "importBarcodeIsbn": False,
        "scanForceModifiedTime": False, "scanOnStartup": False, "scanInterval": "DISABLED", "scanCbx": True, "scanPdf": True, "scanEpub": True,
        "scanDirectoryExclusions": ["#recycle", "@eaDir", "@Recycle"], "repairExtensions": False, "convertToCbz": False,
        "emptyTrashAfterScan": True, "seriesCover": "FIRST", "hashFiles": True, "hashPages": False, "hashKoreader": False,
        "analyzeDimensions": True, "oneshotsDirectory": None})
    log("library created; waiting for scan and analysis")
ids["library"] = lib["id"]
for _ in range(100):
    books = api("GET", f"/api/v1/books?library_id={lib['id']}&size=50")["content"]
    if len(books) == 7 and all(b["media"]["status"] == "READY" for b in books) and all(b["metadata"]["title"] != b["name"] for b in books): break
    time.sleep(3)
else: raise SystemExit(f"[seed] scan incomplete: {len(books)} books")
series = {s["name"]: s for s in api("GET", f"/api/v1/series?library_id={lib['id']}&size=50")["content"]}
KEY = {"Lighthouse Rota": "lighthouse-rota", "Granite Ledger": "granite-ledger", "Blue Heron Kitchen": "blue-heron-kitchen"}
for name, s in series.items(): ids["series"][KEY[name]] = s["id"]
for b in books: ids["books"][f"{KEY[b['seriesTitle']]}-{int(float(b['metadata']['number'])):02d}"] = b["id"]
log(f"{len(series)} series, {len(books)} books ready")

SERIES_META = {
    "lighthouse-rota": {"summary": "A lighthouse crew keeps the winter rota at Granite Point, one watch at a time.", "status": "ONGOING",
                        "ageRating": 12, "tags": ["night shift", "lighthouse", "winter rota"], "totalBookCount": 6},
    "granite-ledger": {"summary": "Quarry audits and a ledger that never quite balances, told by its auditor.", "status": "ENDED",
                       "ageRating": 10, "tags": ["quarry", "audit", "ledger"]},
    "blue-heron-kitchen": {"summary": "Recipes that follow the tides in a small fishing kitchen.", "status": "HIATUS",
                           "ageRating": 8, "tags": ["cooking", "tides"]},
}
for key, meta in SERIES_META.items():
    api("PATCH", f"/api/v1/series/{ids['series'][key]}/metadata", meta)

colls = {c["name"]: c for c in api("GET", "/api/v1/collections?size=50")["content"]}
for key, name, ordered, members in (("night-shift-reading", "Night Shift Reading", False, ["lighthouse-rota", "blue-heron-kitchen"]),
                                    ("quarry-and-depot-files", "Quarry and Depot Files", True, ["granite-ledger", "lighthouse-rota"])):
    c = colls.get(name) or api("POST", "/api/v1/collections", {"name": name, "ordered": ordered, "seriesIds": [ids["series"][m] for m in members]})
    ids["collections"][key] = c["id"]
rls = {r["name"]: r for r in api("GET", "/api/v1/readlists?size=50")["content"]}
r = rls.get("Granite Ledger audit order") or api("POST", "/api/v1/readlists", {
    "name": "Granite Ledger audit order", "summary": "Read both quarry issues before the rota winter, as Rui Castellanos filed them.",
    "ordered": True, "bookIds": [ids["books"]["granite-ledger-01"], ids["books"]["granite-ledger-02"], ids["books"]["lighthouse-rota-02"]]})
ids["readlists"]["granite-ledger-audit-order"] = r["id"]
r = rls.get("Blue Heron tasting order") or api("POST", "/api/v1/readlists", {
    "name": "Blue Heron tasting order", "summary": "Kitchen issues first, then the night watch that eats the broth.",
    "ordered": True, "bookIds": [ids["books"]["blue-heron-kitchen-01"], ids["books"]["blue-heron-kitchen-02"], ids["books"]["lighthouse-rota-03"]]})
ids["readlists"]["blue-heron-tasting-order"] = r["id"]

users = {u["email"]: u for u in api("GET", "/api/v2/users")}
ids["users"]["rea-admin"] = users[EMAIL]["id"]
for email, roles in (("ada.finch@example.test", ["PAGE_STREAMING", "FILE_DOWNLOAD"]), ("rui.castellanos@example.test", ["PAGE_STREAMING"])):
    u = users.get(email) or api("POST", "/api/v2/users", {"email": email, "password": secrets.token_urlsafe(16), "roles": roles,
                                                          "sharedLibraries": {"all": True, "libraryIds": []}})
    ids["users"][email.split("@")[0]] = u["id"]

api("PATCH", f"/api/v1/books/{ids['books']['lighthouse-rota-01']}/read-progress", {"completed": True})
api("PATCH", f"/api/v1/books/{ids['books']['lighthouse-rota-02']}/read-progress", {"page": 2})
json.dump(ids, open(os.path.join(DIR, "seed-ids.json"), "w"), indent=1)
log("seed-ids.json written: " + json.dumps(ids))
