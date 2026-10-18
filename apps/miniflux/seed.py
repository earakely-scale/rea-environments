#!/usr/bin/env python3
"""Seed the showcase Miniflux with synthetic feeds through its REST API (/v1, idempotent).

`python3 seed.py init` writes ~/capture/miniflux/.admin (mode 600: admin and database passwords generated at run time,
read by compose through --env-file) and the four synthetic feed files under ./feeds (two RSS 2.0, two Atom 1.0) that the
compose `feeds` nginx service serves at http://feeds/<file> on the compose network. The channels carry no description
(an earlier capture showed the generated tasks asking for the same channel description three times).
`python3 seed.py` then creates 3 categories, subscribes to the 4 feeds (Miniflux fetches each one on creation, giving 12
entries), adds a second, non-admin user, marks one entry read and stars two, and writes seed-ids.json (ids only).
Requests use HTTP Basic auth as rea-admin. Never prints a password."""
import base64, json, os, secrets, sys, time, urllib.error, urllib.request

BASE = os.environ.get("BASE_URL", "http://127.0.0.1:3217")
DIR = os.environ.get("CAPTURE_DIR", os.path.expanduser("~/capture/miniflux"))
ADMIN_FILE = os.path.join(DIR, ".admin")
USER = "rea-admin"

def log(msg): print(f"[seed] {msg}", file=sys.stderr)

FEEDS = [
    {"file": "lighthouse-rota-bulletin.xml", "kind": "rss", "title": "Lighthouse Rota Bulletin", "category": "Coastal Operations",
     "site": "https://lighthouse-rota.example.test/",
     "items": [
         ("Winter rota published: shift three starts at 22:00", "Ada Finch", "2026-10-01T08:00:00Z",
          "Shift three hands over at 06:00; Ada Finch keeps the tide tables for January."),
         ("Lamp oil budget set at 180 litres", "Tomas Vey", "2026-10-03T09:30:00Z",
          "The winter lamp oil allowance is 180 litres per lighthouse, delivered in 12 drops."),
         ("Fog-horn compressor two back in service", "Mina Okafor", "2026-10-06T14:15:00Z",
          "Compressor two passed its pressure test at 7.5 bar after the valve swap."),
     ]},
    {"file": "granite-ledger-quarry-notes.atom", "kind": "atom", "title": "Granite Ledger Quarry Notes", "category": "Quarry and Stone",
     "site": "https://granite-ledger.example.test/",
     "items": [
         ("Quarterly stone count: 412 blocks", "Rui Castellanos", "2026-10-02T10:00:00Z",
          "412 blocks counted in the north quarry and 97 in the tidal yard; ledger GL-2291."),
         ("Cart number 7 retired", "Rui Castellanos", "2026-10-08T07:45:00Z",
          "Cart 7 is retired after a cracked axle; cart 9 takes over the seaward run."),
         ("Seaward stack re-measured at 31 metres", "Ada Finch", "2026-10-12T16:20:00Z",
          "The seaward stack now stands at 31 metres, two metres lower than in spring."),
     ]},
    {"file": "blue-heron-kitchen-specials.xml", "kind": "rss", "title": "Blue Heron Kitchen Specials", "category": "Kitchens and Supplies",
     "site": "https://blue-heron-kitchen.example.test/",
     "items": [
         ("Smoked kelp broth returns for the night shift", "Marisol Okonkwo-Reyes", "2026-10-04T18:00:00Z",
          "Served from 22:00 to the night shift of the Lighthouse Rota, two ladles each."),
         ("Tide-table menu: 36 covers per sitting", "Marisol Okonkwo-Reyes", "2026-10-09T11:00:00Z",
          "The dining room seats 36 covers per sitting; the menu changes on every spring tide."),
         ("Saffron oat bread on spring tides", "Rui Castellanos", "2026-10-13T06:30:00Z",
          "Saffron oat bread is baked at dawn on spring-tide days, 14 loaves a batch."),
     ]},
    {"file": "saltmarsh-depot-tide-log.atom", "kind": "atom", "title": "Saltmarsh Depot Tide Log", "category": "Coastal Operations",
     "site": "https://saltmarsh-depot.example.test/",
     "items": [
         ("Barge Pale Meridian docked at berth B4", "Tomas Vey", "2026-10-05T05:10:00Z",
          "Pale Meridian unloaded 40 coils of rope and 6 drums of lamp oil at berth B4."),
         ("Rope delivery delayed by the neap tide", "Tomas Vey", "2026-10-10T19:40:00Z",
          "The neap tide left only 1.2 metres at the bar; the rope drop moves to Thursday."),
         ("Copperfield Annex collects 12 drums", "Mina Okafor", "2026-10-15T12:05:00Z",
          "Mina Okafor signed for 12 drums of lamp oil for the Copperfield Annex workshop."),
     ]},
]
CATEGORIES = ["Coastal Operations", "Quarry and Stone", "Kitchens and Supplies"]

def rfc822(iso):
    t = time.strptime(iso, "%Y-%m-%dT%H:%M:%SZ"); return time.strftime("%a, %d %b %Y %H:%M:%S +0000", t)

def esc(s): return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def feed_xml(f):
    slug = f["file"].split(".")[0]
    if f["kind"] == "rss":
        items = "".join(
            f"<item><title>{esc(t)}</title><link>{f['site']}posts/{slug}-{i + 1:03d}</link>"
            f"<guid isPermaLink=\"false\">{slug}-{i + 1:03d}</guid><pubDate>{rfc822(d)}</pubDate>"
            f"<dc:creator>{esc(a)}</dc:creator><description>{esc(b)}</description></item>\n" for i, (t, a, d, b) in enumerate(f["items"]))
        return ("<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n<rss version=\"2.0\" xmlns:dc=\"http://purl.org/dc/elements/1.1/\"><channel>"
                f"<title>{esc(f['title'])}</title><link>{f['site']}</link><description></description><language>en</language>\n"
                f"{items}</channel></rss>\n")
    entries = "".join(
        f"<entry><title>{esc(t)}</title><id>urn:rea:{slug}:{i + 1:03d}</id><link href=\"{f['site']}posts/{slug}-{i + 1:03d}\"/>"
        f"<published>{d}</published><updated>{d}</updated><author><name>{esc(a)}</name></author>"
        f"<summary>{esc(b)}</summary></entry>\n" for i, (t, a, d, b) in enumerate(f["items"]))
    last = max(d for _, _, d, _ in f["items"])
    return ("<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n<feed xmlns=\"http://www.w3.org/2005/Atom\">"
            f"<title>{esc(f['title'])}</title><id>urn:rea:{slug}</id>"
            f"<link href=\"{f['site']}\"/><updated>{last}</updated>\n{entries}</feed>\n")

def init():
    os.makedirs(os.path.join(DIR, "feeds"), exist_ok=True)
    for f in FEEDS:
        open(os.path.join(DIR, "feeds", f["file"]), "w").write(feed_xml(f))
    log(f"wrote {len(FEEDS)} feed files to {DIR}/feeds")
    if os.path.exists(ADMIN_FILE): log(".admin exists; keeping it"); return
    fd = os.open(ADMIN_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as fh:
        fh.write(f"MINIFLUX_ADMIN_PASSWORD={secrets.token_urlsafe(18)}\nMINIFLUX_DB_PASSWORD={secrets.token_urlsafe(18)}\n")
    log(f"wrote {ADMIN_FILE} (mode 600)")

if len(sys.argv) > 1 and sys.argv[1] == "init":
    init(); sys.exit(0)

PW = dict(l.split("=", 1) for l in open(ADMIN_FILE).read().splitlines() if "=" in l)["MINIFLUX_ADMIN_PASSWORD"]
AUTH = "Basic " + base64.b64encode(f"{USER}:{PW}".encode()).decode()

def api(method, path, body=None, quiet=False):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + "/v1/" + path, data=data, method=method)
    req.add_header("Authorization", AUTH); req.add_header("Accept", "application/json")
    if data is not None: req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read(); return (json.loads(raw) if raw else {}), r.status
    except urllib.error.HTTPError as e:
        if quiet: return None, e.code
        raise SystemExit(f"[seed] {method} /v1/{path} -> {e.code}: {e.read().decode(errors='replace')[:300]}")

for _ in range(120):
    try:
        with urllib.request.urlopen(BASE + "/healthcheck", timeout=5) as r:
            if r.read().strip() == b"OK": break
    except Exception: pass
    time.sleep(2)
else:
    raise SystemExit("[seed] Miniflux did not become ready")
me, _ = api("GET", "me"); ver, _ = api("GET", "version", quiet=True)
log(f"signed in as {me['username']} (Miniflux {(ver or {}).get('version', '?')})")

ids = {"users": {USER: me["id"]}, "categories": {}, "feeds": {}, "entries": {}}

cats = {c["title"]: c["id"] for c in api("GET", "categories")[0]}
for c in cats:
    if c.startswith("Rea scratch"):
        api("DELETE", f"categories/{cats[c]}"); log("removed a leftover scratch category")
for title in CATEGORIES:
    if title not in cats:
        cats[title] = api("POST", "categories", {"title": title})[0]["id"]; log(f"category '{title}' created")
    ids["categories"][title] = cats[title]

feeds = {f["feed_url"]: f for f in api("GET", "feeds")[0]}
for f in FEEDS:
    url = f"http://feeds/{f['file']}"
    if url not in feeds:
        fid = api("POST", "feeds", {"feed_url": url, "category_id": cats[f["category"]]})[0]["feed_id"]; log(f"subscribed to '{f['title']}'")
    else:
        fid = feeds[url]["id"]
    ids["feeds"][f["title"]] = fid
    for e in api("GET", f"feeds/{fid}/entries?limit=50&order=published_at&direction=asc")[0]["entries"]:
        ids["entries"][e["title"]] = e["id"]
expected = sum(len(f["items"]) for f in FEEDS)
if len(ids["entries"]) != expected: raise SystemExit(f"[seed] expected {expected} entries, found {len(ids['entries'])}")

users = {u["username"]: u["id"] for u in api("GET", "users")[0]}
if "mina-okafor" not in users:
    # A second, non-admin reader; its password is random and discarded (nothing signs in as this user).
    users["mina-okafor"] = api("POST", "users", {"username": "mina-okafor", "password": secrets.token_urlsafe(18), "is_admin": False})[0]["id"]
    log("user mina-okafor created")
ids["users"]["mina-okafor"] = users["mina-okafor"]

E = ids["entries"]
api("PUT", "entries", {"entry_ids": [E["Cart number 7 retired"], E["Lamp oil budget set at 180 litres"]], "status": "read"})
for title in ("Quarterly stone count: 412 blocks", "Smoked kelp broth returns for the night shift"):
    if not api("GET", f"entries/{E[title]}")[0]["starred"]:
        api("PUT", f"entries/{E[title]}/bookmark"); log(f"starred '{title}'")
api("PUT", f"users/{me['id']}", {"timezone": "UTC", "entry_sorting_direction": "desc"})

json.dump(ids, open(os.path.join(DIR, "seed-ids.json"), "w"), indent=1)
log("seed-ids.json written (" + ", ".join(f"{k}={len(v)}" for k, v in ids.items()) + ")")
