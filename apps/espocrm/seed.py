#!/usr/bin/env python3
"""Seed the showcase EspoCRM with synthetic CRM data through its REST API (/api/v1, idempotent).

`python3 seed.py init` writes ~/capture/espocrm/.admin (mode 600) with the admin and database passwords generated at run
time; compose reads it with --env-file. The 10.0.10 image entrypoint always sets the password of a user named `admin`, so
compose lets it create `admin` and this script renames that user to `rea-admin` through the API on the first run.
`python3 seed.py` then creates 2 teams, 4 accounts, 4 contacts, 3 leads, 4 opportunities, 3 cases, 3 tasks, 2 meetings,
2 calls, 2 knowledge-base articles, 1 campaign, 1 target list and a stream post, all with fixed, obviously invented names,
and writes seed-ids.json (ids only). Requests authenticate with the `Espo-Authorization` header the web client uses for
password sign-in. Never prints a password."""
import base64, json, os, secrets, sys, time, urllib.error, urllib.parse, urllib.request

BASE = os.environ.get("BASE_URL", "http://127.0.0.1:3216")
DIR = os.environ.get("CAPTURE_DIR", os.path.expanduser("~/capture/espocrm"))
ADMIN_FILE = os.path.join(DIR, ".admin")
USER = "rea-admin"

def log(msg): print(f"[seed] {msg}", file=sys.stderr)

def read_admin():
    return dict(l.split("=", 1) for l in open(ADMIN_FILE).read().splitlines() if "=" in l)

def init():
    if os.path.exists(ADMIN_FILE):
        log(".admin exists; keeping it"); return
    fd = os.open(ADMIN_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(f"ESPO_ADMIN_PASSWORD={secrets.token_urlsafe(18)}\nESPO_DB_PASSWORD={secrets.token_urlsafe(18)}\n")
    log(f"wrote {ADMIN_FILE} (mode 600)")

if len(sys.argv) > 1 and sys.argv[1] == "init":
    init(); sys.exit(0)

PW = read_admin()["ESPO_ADMIN_PASSWORD"]
AUTH = base64.b64encode(f"{USER}:{PW}".encode()).decode()

def api(method, path, body=None, quiet=False, auth=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + "/api/v1/" + path, data=data, method=method)
    req.add_header("Espo-Authorization", auth or AUTH); req.add_header("Accept", "application/json")
    if data is not None: req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read(); return (json.loads(raw) if raw else {}), r.status
    except urllib.error.HTTPError as e:
        if quiet: return None, e.code
        detail = e.read().decode(errors="replace")[:300]
        raise SystemExit(f"[seed] {method} /api/v1/{path} -> {e.code}: {detail}")

def wait_ready():
    for _ in range(180):
        try:
            with urllib.request.urlopen(BASE + "/", timeout=5) as r:
                if r.status == 200:
                    _, code = api("GET", "App/user", quiet=True)
                    if code in (200, 401): return code
        except Exception: pass
        time.sleep(2)
    raise SystemExit("[seed] EspoCRM did not become ready")

code = wait_ready()
if code == 401:
    boot = base64.b64encode(f"admin:{PW}".encode()).decode()
    first, c2 = api("GET", "App/user", quiet=True, auth=boot)
    if c2 != 200: raise SystemExit(f"[seed] neither rea-admin nor the bootstrap admin can sign in ({c2})")
    api("PUT", f"User/{first['user']['id']}", {"userName": USER, "firstName": "Rea", "lastName": "Admin",
        "emailAddress": "rea-admin@example.test", "title": "CRM Administrator"}, auth=boot)
    log("bootstrap admin renamed to rea-admin")
    _, code = api("GET", "App/user", quiet=True)
    if code != 200: raise SystemExit(f"[seed] rea-admin cannot sign in after the rename ({code})")
me, _ = api("GET", "App/user")
log(f"signed in as {me['user']['userName']} (EspoCRM {me.get('settings', {}).get('version', '?')})")

def find(entity, field, value):
    q = urllib.parse.urlencode({"where[0][type]": "equals", "where[0][attribute]": field, "where[0][value]": value, "select": "id", "maxSize": 5})
    res, _ = api("GET", f"{entity}?{q}")
    return res["list"][0]["id"] if res.get("list") else None

def ensure(entity, key, body, field="name"):
    val = body[field] if field in body else key
    oid = find(entity, field, val)
    if oid is None:
        res, _ = api("POST", entity, body); oid = res["id"]; log(f"{entity} '{val}' created")
    return oid

# Remove scratch tasks left behind by an interrupted capture so every capture starts from the same state.
q = urllib.parse.urlencode({"where[0][type]": "startsWith", "where[0][attribute]": "name", "where[0][value]": "Rea scratch", "select": "id", "maxSize": 50})
for row in api("GET", f"Task?{q}")[0].get("list", []):
    api("DELETE", f"Task/{row['id']}"); log("removed a leftover scratch task")

ids = {k: {} for k in ("teams", "accounts", "contacts", "leads", "opportunities", "cases", "tasks", "meetings", "calls", "kb", "campaigns", "targetLists", "notes", "users")}
ids["users"]["rea-admin"] = ME = me["user"]["id"]

for name in ("Lighthouse Rota Crew", "Quarry Desk"):
    ids["teams"][name] = ensure("Team", name, {"name": name})

ACCOUNTS = [
    {"name": "Granite Ledger Holdings", "type": "Customer", "industry": "Mining", "billingAddressCity": "Granite Point",
     "billingAddressCountry": "Nowhere Isles", "sicCode": "GL-2291", "emailAddress": "office@granite-ledger.example.test",
     "description": "Quarry operator; counts 412 blocks a quarter in the north quarry."},
    {"name": "Blue Heron Kitchen", "type": "Customer", "industry": "Hospitality", "billingAddressCity": "Tidewater Steps",
     "billingAddressCountry": "Nowhere Isles", "sicCode": "BH-0036", "emailAddress": "hello@blue-heron.example.test",
     "description": "Quayside canteen serving 36 covers per sitting on a tide-table menu."},
    {"name": "Copperfield Annex", "type": "Partner", "industry": "Real Estate", "billingAddressCity": "Copperfield",
     "billingAddressCountry": "Nowhere Isles", "sicCode": "CA-7140", "emailAddress": "desk@copperfield-annex.example.test",
     "description": "Leases the old lamp workshop as a shared annex with 14 desks."},
    {"name": "Saltmarsh Depot", "type": "Reseller", "industry": "Shipping", "billingAddressCity": "Saltmarsh",
     "billingAddressCountry": "Nowhere Isles", "sicCode": "SD-5508", "emailAddress": "yard@saltmarsh-depot.example.test",
     "description": "Bonded depot moving lamp oil and rope; runs 3 flat-bed barges."},
]
for a in ACCOUNTS:
    ids["accounts"][a["name"]] = ensure("Account", a["name"], a)
acc = ids["accounts"]

CONTACTS = [
    {"firstName": "Ada", "lastName": "Finch", "accountId": acc["Granite Ledger Holdings"], "emailAddress": "ada.finch@example.test",
     "description": "Keeps the tide tables and signs off the quarterly stone count."},
    {"firstName": "Rui", "lastName": "Castellanos", "accountId": acc["Blue Heron Kitchen"], "emailAddress": "rui.castellanos@example.test",
     "description": "Head of purchasing; orders smoked kelp in 20 kg crates."},
    {"firstName": "Mina", "lastName": "Okafor", "accountId": acc["Copperfield Annex"], "emailAddress": "mina.okafor@example.test",
     "description": "Facilities lead for the annex; holds the key to desk row C."},
    {"firstName": "Tomas", "lastName": "Vey", "accountId": acc["Saltmarsh Depot"], "emailAddress": "tomas.vey@example.test",
     "description": "Barge master on the Saltmarsh run; prefers calls after 16:00."},
]
for c in CONTACTS:
    full = f"{c['firstName']} {c['lastName']}"
    oid = find("Contact", "emailAddress", c["emailAddress"])
    if oid is None: oid = api("POST", "Contact", c)[0]["id"]; log(f"Contact '{full}' created")
    ids["contacts"][full] = oid
con = ids["contacts"]

LEADS = [
    {"firstName": "Odile", "lastName": "Marchbank", "accountName": "Pewter Lantern Cooperative", "title": "Cooperative Secretary",
     "status": "In Process", "source": "Partner", "emailAddress": "odile.marchbank@example.test",
     "description": "Wants a quote for 40 lantern housings before the winter rota."},
    {"firstName": "Bram", "lastName": "Ellery-Quist", "accountName": "Driftwood Signal Works", "title": "Workshop Foreman",
     "status": "New", "source": "Web Site", "emailAddress": "bram.ellery-quist@example.test",
     "description": "Asked about refurbishing two fog-horn compressors."},
    {"firstName": "Sunniva", "lastName": "Torrance", "accountName": "Kestrel Tide Charters", "title": "Operations Manager",
     "status": "Assigned", "source": "Existing Customer", "emailAddress": "sunniva.torrance@example.test",
     "description": "Charter fleet of 6 skiffs; interested in berth bookings at Saltmarsh."},
]
for l in LEADS:
    full = f"{l['firstName']} {l['lastName']}"
    oid = find("Lead", "emailAddress", l["emailAddress"])
    if oid is None: oid = api("POST", "Lead", l)[0]["id"]; log(f"Lead '{full}' created")
    ids["leads"][full] = oid

OPPS = [
    {"name": "Granite Ledger quarry scales renewal", "accountId": acc["Granite Ledger Holdings"], "amount": 18400, "amountCurrency": "USD",
     "stage": "Negotiation", "probability": 70, "closeDate": "2026-11-20", "leadSource": "Existing Customer",
     "description": "Three weighbridge scales, five-year service plan, reference GL-Q4."},
    {"name": "Blue Heron cold-room retrofit", "accountId": acc["Blue Heron Kitchen"], "amount": 9650, "amountCurrency": "USD",
     "stage": "Proposal", "probability": 50, "closeDate": "2026-12-04", "leadSource": "Call",
     "description": "Replace the kelp cold room; Rui Castellanos wants it before spring tides."},
    {"name": "Copperfield Annex desk expansion", "accountId": acc["Copperfield Annex"], "amount": 4200, "amountCurrency": "USD",
     "stage": "Qualification", "probability": 20, "closeDate": "2027-01-15", "leadSource": "Partner",
     "description": "Six more desks in row D, pending the lamp workshop lease."},
    {"name": "Saltmarsh barge oil contract", "accountId": acc["Saltmarsh Depot"], "amount": 27300, "amountCurrency": "USD",
     "stage": "Closed Won", "probability": 100, "closeDate": "2026-10-02", "leadSource": "Campaign",
     "description": "Annual supply of 180 litres of lamp oil per lighthouse, 12 drops."},
]
for o in OPPS:
    ids["opportunities"][o["name"]] = ensure("Opportunity", o["name"], o)

CASES = [
    {"name": "Weighbridge 2 reads 40 kg heavy", "accountId": acc["Granite Ledger Holdings"], "contactId": con["Ada Finch"],
     "status": "Assigned", "priority": "High", "type": "Problem", "description": "Drift appears after rain; calibration seal number 77-B."},
    {"name": "Cold-room door seal leaking", "accountId": acc["Blue Heron Kitchen"], "contactId": con["Rui Castellanos"],
     "status": "New", "priority": "Urgent", "type": "Incident", "description": "Temperature rose to 9 degrees overnight on the north wall."},
    {"name": "Invoice copy for September barge drops", "accountId": acc["Saltmarsh Depot"], "contactId": con["Tomas Vey"],
     "status": "Closed", "priority": "Low", "type": "Question", "description": "Tomas Vey needs invoice SD-0915 re-sent to the yard office."},
]
for c in CASES:
    c["assignedUserId"] = ME
    ids["cases"][c["name"]] = ensure("Case", c["name"], c)

TASKS = [
    {"name": "Send scales service schedule to Ada Finch", "status": "Not Started", "priority": "Normal", "dateEndDate": "2026-11-03",
     "parentType": "Account", "parentId": acc["Granite Ledger Holdings"], "description": "Include the five-year plan and seal 77-B notes."},
    {"name": "Measure the Blue Heron cold room", "status": "Started", "priority": "High", "dateEndDate": "2026-10-28",
     "parentType": "Account", "parentId": acc["Blue Heron Kitchen"], "description": "Bring the long tape; the north wall is 6.4 m."},
    {"name": "Confirm row D floor plan with Mina Okafor", "status": "Deferred", "priority": "Low", "dateEndDate": "2026-12-10",
     "parentType": "Account", "parentId": acc["Copperfield Annex"], "description": "Waiting for the lamp workshop lease to be signed."},
]
for t in TASKS:
    t["assignedUserId"] = ME; t["teamsIds"] = [ids["teams"]["Quarry Desk" if "Granite" in t["description"] or "scales" in t["name"] else "Lighthouse Rota Crew"]]
    ids["tasks"][t["name"]] = ensure("Task", t["name"], t)

MEETINGS = [
    {"name": "Granite Ledger quarterly review", "status": "Planned", "dateStart": "2026-11-12 10:00:00", "dateEnd": "2026-11-12 11:30:00",
     "parentType": "Account", "parentId": acc["Granite Ledger Holdings"], "description": "Agenda: stone count, weighbridge drift, renewal terms."},
    {"name": "Saltmarsh Depot contract kickoff", "status": "Held", "dateStart": "2026-10-05 14:00:00", "dateEnd": "2026-10-05 15:00:00",
     "parentType": "Account", "parentId": acc["Saltmarsh Depot"], "description": "Held on the barge Pale Meridian; 12 drops agreed."},
]
for mt in MEETINGS:
    mt["assignedUserId"] = ME
    ids["meetings"][mt["name"]] = ensure("Meeting", mt["name"], mt)

CALLS = [
    {"name": "Call Tomas Vey about drop schedule", "status": "Held", "direction": "Outbound", "dateStart": "2026-10-09 16:30:00",
     "dateEnd": "2026-10-09 16:45:00", "parentType": "Account", "parentId": acc["Saltmarsh Depot"], "description": "Moved drop 4 to the neap tide."},
    {"name": "Inbound call from Odile Marchbank", "status": "Planned", "direction": "Inbound", "dateStart": "2026-11-02 09:15:00",
     "dateEnd": "2026-11-02 09:30:00", "description": "She will confirm the lantern housing count."},
]
for c in CALLS:
    c["assignedUserId"] = ME
    ids["calls"][c["name"]] = ensure("Call", c["name"], c)

KB = [
    {"name": "Calibrating a weighbridge after heavy rain", "status": "Published", "language": "en_US", "type": "Article",
     "body": "<p>Let the deck drain for 20 minutes, zero the indicator, then load the 500 kg test block.</p>"},
    {"name": "Cold-room door seal replacement checklist", "status": "Draft", "language": "en_US", "type": "Article",
     "body": "<p>Order seal profile CR-12, warm it to 30 degrees, fit from the hinge side.</p>"},
]
for k in KB:
    ids["kb"][k["name"]] = ensure("KnowledgeBaseArticle", k["name"], k)

ids["campaigns"]["Winter Lamp Oil Mailing"] = ensure("Campaign", "Winter Lamp Oil Mailing", {
    "name": "Winter Lamp Oil Mailing", "status": "Active", "type": "Mail", "startDate": "2026-10-01", "endDate": "2026-12-15",
    "budget": 1200, "budgetCurrency": "USD", "description": "Postcards to every keeper on the Lighthouse Rota."})
ids["targetLists"]["Lighthouse Rota Keepers"] = ensure("TargetList", "Lighthouse Rota Keepers", {
    "name": "Lighthouse Rota Keepers", "description": "Keepers and cooks who receive the winter mailing."})

POST = "Ada Finch confirmed the north quarry count: 412 blocks, audit reference GL-2291."
q = urllib.parse.urlencode({"where[0][type]": "equals", "where[0][attribute]": "post", "where[0][value]": POST, "select": "id", "maxSize": 5})
notes = api("GET", f"Note?{q}", quiet=True)[0]
if notes and notes.get("list"):
    ids["notes"]["quarry-count"] = notes["list"][0]["id"]
else:
    ids["notes"]["quarry-count"] = api("POST", "Note", {"type": "Post", "post": POST, "parentType": "Account", "parentId": acc["Granite Ledger Holdings"]})[0]["id"]
    log("stream post created")

json.dump(ids, open(os.path.join(DIR, "seed-ids.json"), "w"), indent=1)
log("seed-ids.json written (" + ", ".join(f"{k}={len(v)}" for k, v in ids.items()) + ")")
