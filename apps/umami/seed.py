#!/usr/bin/env python3
"""Seed the showcase Umami with synthetic content through its REST API (idempotent).

`python3 seed.py init` writes ~/capture/umami/.admin (mode 600): the password for rea-admin, the database password and URL,
and APP_SECRET; compose reads it as an env_file. `python3 seed.py` then signs in with the image's default admin/umami
account ONCE and renames that account to rea-admin with the generated password (so the default credential is gone), signs in
again as rea-admin (bearer token, as the web UI does), and creates by fixed names: 2 teams, 3 websites, 2 users with team
memberships, 1 short link, 1 pixel, 1 board, 2 annotations, 1 segment, 1 goal, 1 funnel; then, if the websites have no data
yet, sends about a hundred synthetic pageviews, custom events and identify calls through POST /api/send with explicit
user agents, documentation-range IPs and timestamps spread over the last six days. Writes seed-ids.json (ids only)."""
import json, os, secrets, sys, time, urllib.error, urllib.parse, urllib.request

BASE = os.environ.get("BASE_URL", "http://127.0.0.1:3215")
DIR = os.environ.get("CAPTURE_DIR", os.path.expanduser("~/capture/umami"))
ADMIN_FILE = os.path.join(DIR, ".admin")
USER = "rea-admin"

def log(msg): print(f"[seed] {msg}", file=sys.stderr)

def init_admin():
    if os.path.exists(ADMIN_FILE): log(".admin exists; keeping it"); return
    db = secrets.token_urlsafe(18)
    fd = os.open(ADMIN_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(f"UMAMI_ADMIN_PASSWORD={secrets.token_urlsafe(21)}\nPOSTGRES_PASSWORD={db}\n"
                f"DATABASE_URL=postgresql://umami:{db}@db:5432/umami\nAPP_SECRET={secrets.token_urlsafe(32)}\n")
    log(f"wrote {ADMIN_FILE} (mode 600)")

TOKEN = None
CHROME = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"

def call(method, path, body=None, auth=True, soft=False, headers=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method)
    req.add_header("Accept", "application/json"); req.add_header("User-Agent", CHROME)
    if data is not None: req.add_header("Content-Type", "application/json")
    if auth and TOKEN: req.add_header("Authorization", f"Bearer {TOKEN}")
    for k, v in (headers or {}).items(): req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            txt = r.read(); return json.loads(txt) if txt else {}
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:300]
        if soft: return None
        raise SystemExit(f"[seed] {method} {path} -> {e.code}: {detail}")

def items(res): return res.get("data", []) if isinstance(res, dict) else (res or [])

def wait_ready():
    for _ in range(150):
        try:
            with urllib.request.urlopen(BASE + "/api/heartbeat", timeout=5) as r:
                if r.status == 200: return
        except Exception: pass
        time.sleep(2)
    raise SystemExit("[seed] Umami did not become ready")

if len(sys.argv) > 1 and sys.argv[1] == "init":
    init_admin(); sys.exit(0)

wait_ready()
pw = dict(l.split("=", 1) for l in open(ADMIN_FILE).read().splitlines() if "=" in l)["UMAMI_ADMIN_PASSWORD"]
res = call("POST", "/api/auth/login", {"username": USER, "password": pw}, auth=False, soft=True)
if res is None:
    res = call("POST", "/api/auth/login", {"username": "admin", "password": "umami"}, auth=False)
    TOKEN = res["token"]
    call("POST", f"/api/users/{res['user']['id']}", {"username": USER, "password": pw}); log("default admin renamed to rea-admin with the generated password")
    res = call("POST", "/api/auth/login", {"username": USER, "password": pw}, auth=False)
TOKEN = res["token"]; ME = res["user"]["id"]; log(f"signed in as {res['user']['username']} ({res['user']['role']})")
ids = {"users": {USER: ME}}

def ensure(list_path, create_path, name, body, key="name"):
    cur = next((x for x in items(call("GET", list_path)) if x.get(key) == name), None)
    if cur: return cur["id"]
    cur = call("POST", create_path, body); log(f"{create_path}: created {name!r}")
    return (cur[0] if isinstance(cur, list) else cur)["id"]   # POST /api/teams answers [team, owner membership]

# Remove scratch websites an interrupted capture may have left behind.
for w in items(call("GET", "/api/websites?pageSize=100&includeTeams=1")):
    if w["name"].startswith("Rea scratch"): call("DELETE", f"/api/websites/{w['id']}"); log(f"removed leftover {w['name']}")

TEAMS = ["Saltmarsh Depot Analytics", "Copperfield Annex Web"]
ids["teams"] = {t: ensure("/api/teams?pageSize=100", "/api/teams", t, {"name": t}) for t in TEAMS}
SITES = [
    ("Lighthouse Rota Portal", "lighthouse-rota.example.test", ids["teams"]["Saltmarsh Depot Analytics"]),
    ("Granite Ledger Docs", "granite-ledger.example.test", None),
    ("Blue Heron Kitchen", "blue-heron-kitchen.example.test", ids["teams"]["Copperfield Annex Web"]),
]
ids["websites"] = {n: ensure("/api/websites?pageSize=100&includeTeams=1", "/api/websites", n, {"name": n, "domain": d, **({"teamId": t} if t else {})})
                   for n, d, t in SITES}
W = ids["websites"]
USERS = [("ada.finch", "user"), ("tomas.vey", "view-only")]
for u, role in USERS:
    ids["users"][u] = ensure("/api/admin/users?pageSize=100", "/api/users", u, {"username": u, "password": secrets.token_urlsafe(18), "role": role}, key="username")
for team, u, role in [("Saltmarsh Depot Analytics", "ada.finch", "team-member"), ("Copperfield Annex Web", "tomas.vey", "team-view-only")]:
    tid = ids["teams"][team]
    if not any(m.get("userId") == ids["users"][u] for m in items(call("GET", f"/api/teams/{tid}/users?pageSize=100"))):
        call("POST", f"/api/teams/{tid}/users", {"userId": ids["users"][u], "role": role}); log(f"{u} joined {team} as {role}")
ids["links"] = {"Tide Table Signup": ensure("/api/links?pageSize=100", "/api/links", "Tide Table Signup",
                {"name": "Tide Table Signup", "url": "https://lighthouse-rota.example.test/tide-tables/signup", "slug": "tide-table-signup"})}
ids["pixels"] = {"Granite Ledger Newsletter Pixel": ensure("/api/pixels?pageSize=100", "/api/pixels", "Granite Ledger Newsletter Pixel",
                 {"name": "Granite Ledger Newsletter Pixel", "slug": "granite-ledger-pixel"})}
ids["boards"] = {"Night Shift Overview": ensure("/api/boards?pageSize=100", "/api/boards", "Night Shift Overview",
                 {"type": "website", "name": "Night Shift Overview", "description": "Pageviews of the Lighthouse Rota night shift pages.",
                  "parameters": {"websiteId": W["Lighthouse Rota Portal"]}})}
DAY = 86400
now = int(time.time())
ANNOTATIONS = [("Granite Ledger Docs", 3, "Quarterly stone count published; audited by Rui Castellanos."),
               ("Blue Heron Kitchen", 2, "Spring tide menu launched with smoked kelp broth.")]
ids["annotations"] = {}
for site, days, note in ANNOTATIONS:
    path = f"/api/websites/{W[site]}/annotations"
    cur = next((a for a in items(call("GET", path)) if a.get("note") == note), None)
    if not cur:
        cur = call("POST", path, {"date": time.strftime("%Y-%m-%dT00:00:00.000Z", time.gmtime(now - days * DAY)), "allDay": True, "note": note}); log(f"annotation on {site}")
    ids["annotations"][site] = cur["id"]
ids["segments"] = {"Kelp Broth Readers": ensure(f"/api/websites/{W['Blue Heron Kitchen']}/segments?type=segment", f"/api/websites/{W['Blue Heron Kitchen']}/segments",
                   "Kelp Broth Readers", {"type": "segment", "name": "Kelp Broth Readers", "parameters": {"filters": [{"name": "path", "operator": "c", "value": "kelp"}]}})}
ids["goals"] = {"Ledger PDF Downloads": ensure(f"/api/websites/{W['Granite Ledger Docs']}/goals", f"/api/websites/{W['Granite Ledger Docs']}/goals",
                "Ledger PDF Downloads", {"name": "Ledger PDF Downloads", "description": "Visitors who download the quarterly ledger PDF.",
                                         "parameters": {"type": "event", "value": "download-ledger-pdf"}})}
ids["funnels"] = {"Rota Signup Funnel": ensure(f"/api/websites/{W['Lighthouse Rota Portal']}/funnels", f"/api/websites/{W['Lighthouse Rota Portal']}/funnels",
                  "Rota Signup Funnel", {"name": "Rota Signup Funnel", "description": "From the rota page to a completed night-shift signup.",
                                         "parameters": {"window": 60, "steps": [{"type": "path", "value": "/rota"}, {"type": "path", "value": "/rota/signup"},
                                                                                {"type": "event", "value": "rota-signup"}]}})}

# --- synthetic traffic through the public collector ---
AGENTS = [
    CHROME,
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:143.0) Gecko/20100101 Firefox/143.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_6) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.6 Safari/605.1.15",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 18_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.6 Mobile/15E148 Safari/604.1",
]
TRAFFIC = {
    "Lighthouse Rota Portal": ("lighthouse-rota.example.test",
        [("/", "Lighthouse Rota"), ("/rota", "Rota"), ("/rota/winter-shifts", "Winter Shift Plan"), ("/tide-tables", "Tide Tables for January"), ("/rota/signup", "Rota Signup")],
        [("rota-signup", {"shift": "three", "station": "Granite Point"}), ("tide-table-download", {"month": "January"})]),
    "Granite Ledger Docs": ("granite-ledger.example.test",
        [("/ledger/quarterly-count", "Quarterly Stone Count"), ("/ledger/seaward-stack", "Seaward Stack Survey"), ("/audits/rui-castellanos", "Audit Notes by Rui Castellanos")],
        [("download-ledger-pdf", {"quarter": "Q3", "blocks": 412})]),
    "Blue Heron Kitchen": ("blue-heron-kitchen.example.test",
        [("/menu/spring-tide", "Spring Tide Menu"), ("/menu/kelp-broth", "Smoked Kelp Broth"), ("/bookings", "Book a Sitting")],
        [("book-sitting", {"sitting": "19:30", "covers": 4})]),
}
REFERRERS = ["https://saltmarsh-depot.example.test/notices", "https://copperfield-annex.example.test/board", ""]

def stats_pageviews(wid):
    s = call("GET", f"/api/websites/{wid}/stats?startAt=0&endAt={now * 1000}")
    pv = s.get("pageviews", 0)
    return pv.get("value", 0) if isinstance(pv, dict) else pv

sent = 0
for si, (site, (host, pages, events)) in enumerate(TRAFFIC.items()):
    wid = W[site]
    if stats_pageviews(wid): log(f"{site} already has traffic; not sending more"); continue
    for v in range(8):   # eight visitors per site
        ua = AGENTS[(v + si) % len(AGENTS)]; ip = f"198.51.100.{10 + si * 20 + v}"
        t = now - (6 * DAY) + v * (17 * 3600) + si * 1800
        ref = REFERRERS[v % len(REFERRERS)]
        for k, (url, title) in enumerate(pages[: 2 + (v % (len(pages) - 1))]):
            referrer = ref if k == 0 else f"https://{host}{pages[k - 1][0]}"
            payload = {"website": wid, "hostname": host, "language": "en-GB", "screen": "1440x900", "url": url, "title": title,
                       **({"referrer": referrer} if referrer else {}), "ip": ip, "userAgent": ua, "timestamp": t + k * 45}
            call("POST", "/api/send", {"type": "event", "payload": payload}, auth=False); sent += 1
        if v % 2 == 0:
            name, data = events[(v // 2) % len(events)]
            payload = {"website": wid, "hostname": host, "language": "en-GB", "screen": "1440x900", "url": pages[-1][0], "title": pages[-1][1],
                       "name": name, "data": data, "ip": ip, "userAgent": ua, "timestamp": t + 300}
            call("POST", "/api/send", {"type": "event", "payload": payload}, auth=False); sent += 1
        if v in (1, 4):
            payload = {"website": wid, "hostname": host, "ip": ip, "userAgent": ua, "timestamp": t + 310,
                       "data": {"crew": "night shift" if v == 1 else "day shift", "home_station": "Saltmarsh Depot"}}
            call("POST", "/api/send", {"type": "identify", "payload": payload}, auth=False); sent += 1
if sent: log(f"sent {sent} collector calls")
for site, wid in W.items(): log(f"{site}: {stats_pageviews(wid)} pageviews")

json.dump(ids, open(os.path.join(DIR, "seed-ids.json"), "w"), indent=1)
log("seed-ids.json written (ids only)")
