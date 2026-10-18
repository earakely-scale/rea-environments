#!/usr/bin/env python3
"""Seed the showcase Sonarr with synthetic, offline settings objects through its REST API (/api/v3, idempotent).

Reads the API key Sonarr generated on first start from /config/config.xml (docker compose exec, parsed in memory), generates
the admin password, and keeps both only in ~/capture/sonarr/.admin (mode 600). Turns on forms login for user "rea-admin"
through PUT /api/v3/config/host. Then seeds 4 tags, 2 root folders, 3 custom formats, 2 quality profiles (with custom-format
scores), 2 release profiles, 1 delay profile, 2 Custom Script connections (no-op scripts), 3 import-list
exclusions and 1 auto-tagging rule. No series: adding one needs a metadata lookup that returns real shows, which the
synthetic-data rule forbids. Removes "rea-scratch" objects left by an interrupted capture. Writes seed-ids.json (ids only)."""
import json, os, re, secrets, subprocess, sys, time, urllib.error, urllib.request

BASE = os.environ.get("BASE_URL", "http://127.0.0.1:3221")
DIR = os.environ.get("CAPTURE_DIR", os.path.expanduser("~/capture/sonarr"))
ADMIN_FILE = os.path.join(DIR, ".admin")
USER = "rea-admin"


def log(msg): print(f"[seed] {msg}", file=sys.stderr)


def wait_ready():
    for _ in range(120):
        try:
            with urllib.request.urlopen(BASE + "/ping", timeout=5) as r:
                if r.status == 200: return
        except Exception: pass
        time.sleep(2)
    raise SystemExit("[seed] Sonarr did not become ready")


def load_or_create_admin():
    if os.path.exists(ADMIN_FILE):
        return dict(l.split("=", 1) for l in open(ADMIN_FILE).read().splitlines() if "=" in l)
    xml = subprocess.run(["docker", "compose", "-p", "rea-sonarr", "-f", "compose.yml", "exec", "-T", "sonarr", "cat", "/config/config.xml"],
                         cwd=DIR, capture_output=True, text=True, check=True).stdout
    key = re.search(r"<ApiKey>([0-9a-f]{32})</ApiKey>", xml).group(1)
    kv = {"SONARR_API_KEY": key, "REA_ADMIN_PASSWORD": secrets.token_urlsafe(21)}
    fd = os.open(ADMIN_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f: f.write("".join(f"{k}={v}\n" for k, v in kv.items()))
    log(f"wrote {ADMIN_FILE} (mode 600): API key from config.xml, generated admin password")
    return kv


admin = {}
def api(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method)
    req.add_header("Accept", "application/json"); req.add_header("X-Api-Key", admin["SONARR_API_KEY"])
    if data is not None: req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            t = r.read().decode(); return json.loads(t) if t else None
    except urllib.error.HTTPError as e:
        raise SystemExit(f"[seed] {method} {path} -> {e.code}: {e.read().decode(errors='replace')[:500]}")


def ensure(coll, key, items, make, query=""):
    """Create each item of `items` whose `key` value is not present yet; return {key value: id}."""
    have = {x[key]: x["id"] for x in api("GET", f"/api/v3/{coll}")}
    for name in [n for n in have if str(n).lower().startswith("rea-scratch") or str(n).lower().startswith("rea scratch")]:
        api("DELETE", f"/api/v3/{coll}/{have.pop(name)}"); log(f"removed leftover {coll} {name}")
    for it in items:
        if it[key] not in have: have[it[key]] = api("POST", f"/api/v3/{coll}{query}", make(it))["id"]; log(f"{coll} {it[key]} created")
    return {it[key]: have[it[key]] for it in items}


wait_ready(); log(f"sonarr ready at {BASE}")
admin = load_or_create_admin()
status = api("GET", "/api/v3/system/status"); log(f"sonarr {status['version']}")
host = api("GET", "/api/v3/config/host")
if host.get("username") != USER or host.get("authenticationMethod") != "forms":
    pw = admin["REA_ADMIN_PASSWORD"]
    api("PUT", f"/api/v3/config/host/{host['id']}", {**host, "authenticationMethod": "forms", "authenticationRequired": "enabled",
                                                     "username": USER, "password": pw, "passwordConfirmation": pw, "analyticsEnabled": False})
    log("forms login enabled for rea-admin")
ids = {}

TAGS = ["lighthouse-rota", "granite-ledger", "blue-heron-kitchen", "saltmarsh-depot"]
ids["tags"] = ensure("tag", "label", [{"label": t} for t in TAGS], lambda it: it)
T = ids["tags"]

ids["rootfolders"] = ensure("rootfolder", "path", [{"path": "/data/lighthouse-rota-archive"}, {"path": "/data/granite-ledger-films"}], lambda it: it)

CF = [("Granite Ledger Remux", r"\bremux\b"), ("Blue Heron Kitchen Subtitles", r"\bsubs?\b"), ("Saltmarsh Depot x265", r"x265|hevc")]
ids["customformats"] = ensure("customformat", "name", [{"name": n, "re": r} for n, r in CF], lambda it: {
    "name": it["name"], "includeCustomFormatWhenRenaming": False,
    "specifications": [{"name": f"{it['name']} title", "implementation": "ReleaseTitleSpecification", "negate": False, "required": True,
                        "fields": [{"name": "value", "value": it["re"]}]}]})

QP = [{"name": "Lighthouse Rota HD", "allowed": ["HDTV-720p", "HDTV-1080p", "WEBDL-1080p"], "cutoff": "HDTV-1080p", "scores": {"Granite Ledger Remux": 40, "Saltmarsh Depot x265": -10}},
      {"name": "Granite Ledger Archive SD", "allowed": ["SDTV", "DVD"], "cutoff": "DVD", "scores": {"Blue Heron Kitchen Subtitles": 25}}]
def make_profile(it):
    p = api("GET", "/api/v3/qualityprofile/schema"); p["name"] = it["name"]; p["upgradeAllowed"] = True; cutoff = None
    for item in p["items"]:
        names = [item["quality"]["name"]] if item.get("quality") else [x["quality"]["name"] for x in item.get("items", [])]
        for sub in ([item] if item.get("quality") else item["items"]):
            sub["allowed"] = sub["quality"]["name"] in it["allowed"]
        if not item.get("quality"): item["allowed"] = any(n in it["allowed"] for n in names)
        if it["cutoff"] in names: cutoff = item["quality"]["id"] if item.get("quality") else item["id"]
    p["cutoff"] = cutoff
    cf_ids = {v: k for k, v in ids["customformats"].items()}
    for fi in p.get("formatItems", []): fi["score"] = it["scores"].get(cf_ids.get(fi["format"], ""), 0)
    p["minFormatScore"] = 0; p["cutoffFormatScore"] = 0
    return p
ids["qualityprofiles"] = ensure("qualityprofile", "name", QP, make_profile)

RP = [{"name": "Copperfield Annex Preferred", "required": ["proper"], "ignored": ["cam", "telesync"], "tags": [T["lighthouse-rota"]]},
      {"name": "Tide Table Filter", "required": [], "ignored": ["sample", "trailer"], "tags": [T["saltmarsh-depot"]]}]
ids["releaseprofiles"] = ensure("releaseprofile", "name", RP, lambda it: {**it, "enabled": True, "indexerId": 0})

if not [d for d in api("GET", "/api/v3/delayprofile") if T["granite-ledger"] in d.get("tags", [])]:
    api("POST", "/api/v3/delayprofile", {"enableUsenet": True, "enableTorrent": True, "preferredProtocol": "torrent", "usenetDelay": 90,
                                          "torrentDelay": 30, "bypassIfHighestQuality": True, "bypassIfAboveCustomFormatScore": False,
                                          "minimumCustomFormatScore": 0, "order": 1, "tags": [T["granite-ledger"]]}); log("delay profile created")
ids["delayprofiles"] = {str(d["id"]): d["tags"] for d in api("GET", "/api/v3/delayprofile")}

# Connections: Sonarr test-fires every connection on save (forceSave does not skip a failing test), and the VM resolves no
# invented hostnames, so both are Custom Script connections pointing at no-op scripts that up.sh writes into /data/scripts.
NOTIF = [{"name": "Copperfield Annex Script", "path": "/data/scripts/copperfield-annex.sh", "tags": [T["lighthouse-rota"]]},
         {"name": "Night Shift Pager", "path": "/data/scripts/night-shift-pager.sh", "tags": [T["blue-heron-kitchen"]]}]
def make_notification(it):
    n = [s for s in api("GET", "/api/v3/notification/schema") if s["implementation"] == "CustomScript"][0]
    n.update({"name": it["name"], "tags": it["tags"], "onGrab": True, "onDownload": True, "onUpgrade": True, "onHealthIssue": False})
    for f in n["fields"]:
        if f["name"] == "path": f["value"] = it["path"]
    return n
ids["notifications"] = ensure("notification", "name", NOTIF, make_notification, query="?forceSave=true")

EXCL = [{"tvdbId": 990001, "title": "Granite Ledger Chronicles"}, {"tvdbId": 990002, "title": "The Saltmarsh Depot Hour"},
        {"tvdbId": 990003, "title": "Blue Heron Kitchen Nights"}]
ids["importlistexclusions"] = ensure("importlistexclusion", "title", EXCL, lambda it: it)

AT = [{"name": "Night Shift Dramas", "tag": "lighthouse-rota", "genre": "Drama"}]
ids["autotagging"] = ensure("autotagging", "name", AT, lambda it: {
    "name": it["name"], "removeTagsAutomatically": False, "tags": [T[it["tag"]]],
    "specifications": [{"name": f"{it['genre']} genre", "implementation": "GenreSpecification", "negate": False, "required": True,
                        "fields": [{"name": "value", "value": [it["genre"]]}]}]})

json.dump(ids, open(os.path.join(DIR, "seed-ids.json"), "w"), indent=1)
log("seed-ids.json written: " + json.dumps({k: len(v) for k, v in ids.items()}))
