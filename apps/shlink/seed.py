#!/usr/bin/env python3
"""Seed the showcase Shlink with synthetic short URLs and visits through its REST API (/rest/v3, idempotent).

Shlink has no users and no bundled web UI; the REST API authenticates with an API key. The key is generated once with
`shlink api-key:generate` inside the container and kept only in ~/capture/shlink/.admin (mode 600); it is sent as the
X-Api-Key header and never printed. Seeds 8 short URLs (custom slugs plus one generated code) with titles, tags, a
custom domain, validity windows, a visit cap and redirect rules; then simulated visits from synthetic user agents and
referers (each short code is opened with redirects disabled) and two orphan visits. Long URLs and referers use the
reserved .test domain so nothing real is linked. Writes seed-ids.json (short codes, tags and domains only)."""
import json, os, re, subprocess, sys, time, urllib.error, urllib.parse, urllib.request

BASE = os.environ.get("BASE_URL", "http://127.0.0.1:3206")
DIR = os.environ.get("CAPTURE_DIR", os.path.expanduser("~/capture/shlink"))
ADMIN_FILE = os.path.join(DIR, ".admin")
COMPOSE = ["docker", "compose", "-p", "rea-shlink", "-f", os.path.join(DIR, "compose.yml")]
CUSTOM_DOMAIN = "links.saltmarsh.example.test"

def log(msg): print(f"[seed] {msg}", file=sys.stderr)

def wait_ready():
    for _ in range(90):
        try:
            with urllib.request.urlopen(BASE + "/rest/health", timeout=5) as r:
                if r.status == 200: return json.loads(r.read())
        except Exception: pass
        time.sleep(2)
    raise SystemExit("[seed] Shlink did not become ready")

def api_key():
    if os.path.exists(ADMIN_FILE):
        kv = dict(l.split("=", 1) for l in open(ADMIN_FILE).read().splitlines() if "=" in l)
        if kv.get("SHLINK_API_KEY"): return kv["SHLINK_API_KEY"]
    out = subprocess.run(COMPOSE + ["exec", "-T", "shlink", "shlink", "api-key:generate", "--name=rea-capture", "--no-ansi"],
                         capture_output=True, text=True, timeout=120)
    m = re.search(r'"([^"\s]{20,})"', out.stdout) or re.search(r"key:?\s+(\S{20,})", out.stdout, re.I)
    if out.returncode != 0 or not m: raise SystemExit(f"[seed] api-key:generate failed (rc={out.returncode}); output not shown because it may hold a key")
    fd = os.open(ADMIN_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f: f.write(f"SHLINK_API_KEY={m.group(1)}\n")
    log(f"API key generated with `shlink api-key:generate` and written to {ADMIN_FILE} (mode 600)")
    return m.group(1)

def api(method, path, body=None, ok=()):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method)
    req.add_header("Accept", "application/json"); req.add_header("X-Api-Key", KEY)
    if data is not None: req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read(); return (json.loads(raw) if raw else {}), r.status
    except urllib.error.HTTPError as e:
        if e.code in ok: return None, e.code
        raise SystemExit(f"[seed] {method} {path} -> {e.code}: {e.read().decode(errors='replace')[:400]}")

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k): return None
visitor = urllib.request.build_opener(NoRedirect)

def visit(path, ua, referer=None, host=None):
    hdrs = {"User-Agent": ua, **({"Referer": referer} if referer else {}), **({"Host": host} if host else {})}
    req = urllib.request.Request(BASE + path, method="GET", headers=hdrs)
    try: visitor.open(req, timeout=15).read()
    except urllib.error.HTTPError as e: return e.code
    return 200

h = wait_ready(); log(f"shlink {h.get('version')} ready at {BASE}")
KEY = api_key()

# Remove what an interrupted capture or probe may have left: scratch short URLs and the orphan "scratch" tag.
for code in ("rea-scratch", "rea-scratch-1", "rea-scratch-2", "rea-probe"):
    if api("GET", f"/rest/v3/short-urls/{code}", ok=(404,))[0] is not None:
        api("DELETE", f"/rest/v3/short-urls/{code}"); log(f"removed leftover {code}")
if "scratch" in api("GET", "/rest/v3/tags")[0]["tags"]["data"]:
    api("DELETE", "/rest/v3/tags?tags%5B%5D=scratch"); log("removed leftover tag scratch")

SHORT_URLS = [
    {"customSlug": "granite-ledger", "longUrl": "https://granite-ledger.example.test/quarterly-stone-count", "title": "Granite Ledger quarterly stone count",
     "tags": ["granite-ledger", "lighthouse-rota"], "maxVisits": 500},
    {"customSlug": "tide-tables", "longUrl": "https://lighthouse-rota.example.test/tide-tables/january", "title": "January tide tables for Granite Point",
     "tags": ["lighthouse-rota"], "crawlable": True},
    {"customSlug": "blue-heron-menu", "longUrl": "https://blue-heron-kitchen.example.test/menu/spring-tide", "title": "Blue Heron Kitchen spring-tide menu",
     "tags": ["blue-heron-kitchen"]},
    {"customSlug": "depot-manifest", "domain": CUSTOM_DOMAIN, "longUrl": "https://saltmarsh-depot.example.test/manifests/so-4471", "title": "Saltmarsh Depot lamp-oil manifest SO-4471",
     "tags": ["saltmarsh-depot"]},
    {"customSlug": "annex-rebuild", "longUrl": "https://copperfield-annex.example.test/beacon/led-cluster", "title": "Copperfield Annex beacon rebuild notes",
     "tags": ["copperfield-annex"], "validUntil": "2027-03-31T23:59:59+00:00"},
    {"customSlug": "rota-binder", "longUrl": "https://lighthouse-rota.example.test/binder", "title": "Lighthouse Rota binder index",
     "tags": ["lighthouse-rota"], "validSince": "2026-01-01T00:00:00+00:00"},
    {"customSlug": "kelp-broth", "longUrl": "https://blue-heron-kitchen.example.test/recipes/smoked-kelp-broth", "title": "Smoked kelp broth recipe card",
     "tags": ["blue-heron-kitchen"], "forwardQuery": False},
    {"longUrl": "https://lighthouse-rota.example.test/handover/night-shift", "title": "Night shift handover checklist", "tags": ["lighthouse-rota"],
     "findIfExists": True, "shortCodeLength": 6},
]
ids = {"short_codes": {}, "tags": [], "domains": [CUSTOM_DOMAIN]}
for s in SHORT_URLS:
    slug = s.get("customSlug")
    cur = None
    if slug:
        q = f"?domain={urllib.parse.quote(s['domain'])}" if s.get("domain") else ""
        cur, _ = api("GET", f"/rest/v3/short-urls/{slug}{q}", ok=(404,))
    if cur is None:
        cur, _ = api("POST", "/rest/v3/short-urls", s); log(f"short URL {cur['shortCode']} created" + (" or found (findIfExists)" if not slug else ""))
    ids["short_codes"][s["title"]] = {"shortCode": cur["shortCode"], "domain": cur.get("domain")}

# redirect rules on the tide tables: Android devices get the compact view, ?shift=night goes to the night-shift page
rr, _ = api("GET", "/rest/v3/short-urls/tide-tables/redirect-rules")
if not rr.get("redirectRules"):
    api("POST", "/rest/v3/short-urls/tide-tables/redirect-rules", {"redirectRules": [
        {"longUrl": "https://lighthouse-rota.example.test/tide-tables/january?view=compact", "conditions": [{"type": "device", "matchValue": "android", "matchKey": None}]},
        {"longUrl": "https://lighthouse-rota.example.test/tide-tables/night-shift", "conditions": [{"type": "query-param", "matchKey": "shift", "matchValue": "night"}]},
    ]}); log("redirect rules set on tide-tables")

# simulated visits, oldest first, so that every visits list starts with a different visitor
vs, _ = api("GET", "/rest/v3/visits")
if (vs["visits"]["nonOrphanVisits"]["total"] + vs["visits"]["orphanVisits"]["total"]) == 0:
    plan = [
        ("/kelp-broth", "GalleyTablet/1.2 (Blue Heron Kitchen pass)", "https://keepers-board.example.test/kitchen"),
        ("/annex-rebuild", "LampWright/0.7 (Copperfield Annex workshop)", None),
        ("/granite-ledger", "QuarryClipboard/5.0 (north quarry)", "https://keepers-board.example.test/ledger"),
        ("/tide-tables", "KeeperConsole/2.0 (Saltmarsh Depot Tower)", "https://keepers-board.example.test/rota"),
        ("/rota-binder", "KeeperConsole/2.0 (Saltmarsh Depot Tower)", None),
        ("/blue-heron-menu", "GalleyTablet/1.4 (Blue Heron Kitchen)", "https://keepers-board.example.test/kitchen"),
        ("/depot-manifest", "DepotScanner/0.9 (Saltmarsh Depot quay)", None, CUSTOM_DOMAIN),
        ("/granite-ledger", "KeeperConsole/2.1 (Granite Point Light)", "https://keepers-board.example.test/ledger"),
        ("/tide-tables", "TideTableReader/3.2 (Copperfield Annex)", None),
    ]
    for path, ua, ref, *host in plan:
        visit(path, ua, ref, host[0] if host else None); time.sleep(1.1)  # distinct timestamps keep the newest-first order stable
    visit("/", "LostLantern/1.0 (base URL)"); time.sleep(1.1)
    visit("/no-such-rota", "LostLantern/1.1 (mistyped short code)")
    log(f"{len(plan)} short-URL visits and 2 orphan visits recorded")

tags, _ = api("GET", "/rest/v3/tags"); ids["tags"] = tags["tags"]["data"]
json.dump(ids, open(os.path.join(DIR, "seed-ids.json"), "w"), indent=1)
log("seed-ids.json written")
