#!/usr/bin/env python3
"""Seed the showcase Paperless-ngx with synthetic content through its REST API (idempotent).

`python3 seed.py init` writes ~/capture/paperless/.admin (mode 600) with a generated admin password and Django secret key;
compose reads it as an env_file, and Paperless creates the superuser rea-admin from PAPERLESS_ADMIN_USER/PASSWORD at start.
`python3 seed.py` then authenticates with HTTP basic auth (no session, no CSRF) and creates, by fixed names: 4 correspondents,
5 tags, 3 document types, 2 storage paths, 3 custom fields, 5 plain-text documents (uploaded through post_document, then
patched with custom-field values), notes on 3 documents, 2 saved views, 2 groups, 2 users, 1 IMAP mail account (never polled),
1 mail rule, 1 workflow, and the application title. Writes seed-ids.json (ids only). Never prints the password."""
import base64, json, os, secrets, sys, time, urllib.error, urllib.parse, urllib.request, uuid

BASE = os.environ.get("BASE_URL", "http://127.0.0.1:3213")
DIR = os.environ.get("CAPTURE_DIR", os.path.expanduser("~/capture/paperless"))
ADMIN_FILE = os.path.join(DIR, ".admin")
USER = "rea-admin"
ACCEPT = "application/json; version=9"

def log(msg): print(f"[seed] {msg}", file=sys.stderr)

def init_admin():
    if os.path.exists(ADMIN_FILE): log(".admin exists; keeping it"); return
    fd = os.open(ADMIN_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(f"PAPERLESS_ADMIN_PASSWORD={secrets.token_urlsafe(21)}\nPAPERLESS_SECRET_KEY={secrets.token_urlsafe(48)}\n")
    log(f"wrote {ADMIN_FILE} (mode 600)")

def admin_password():
    kv = dict(line.split("=", 1) for line in open(ADMIN_FILE).read().splitlines() if "=" in line)
    return kv["PAPERLESS_ADMIN_PASSWORD"]

AUTH = None

def call(method, path, body=None, raw=None, ctype=None, ok404=False):
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    req = urllib.request.Request(BASE + path, data=data, method=method)
    req.add_header("Accept", ACCEPT); req.add_header("Authorization", AUTH)
    if data is not None: req.add_header("Content-Type", ctype or "application/json")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            txt = r.read()
            return json.loads(txt) if txt else {}
    except urllib.error.HTTPError as e:
        if e.code == 404 and ok404: return None
        raise SystemExit(f"[seed] {method} {path} -> {e.code}: {e.read().decode(errors='replace')[:500]}")

def wait_ready():
    for _ in range(150):
        try:
            with urllib.request.urlopen(BASE + "/accounts/login/", timeout=5) as r:
                if r.status == 200: return
        except Exception: pass
        time.sleep(2)
    raise SystemExit("[seed] Paperless did not become ready")

def find(collection, name, key="name"):
    q = urllib.parse.urlencode({f"{key}__iexact": name})
    res = call("GET", f"/api/{collection}/?{q}")
    hits = [r for r in res.get("results", []) if r.get(key, "").lower() == name.lower()]
    return hits[0] if hits else None

def ensure(collection, obj, key="name"):
    cur = find(collection, obj[key], key)
    if cur: return cur["id"]
    cur = call("POST", f"/api/{collection}/", obj); log(f"{collection}: created {obj[key]!r} -> {cur['id']}"); return cur["id"]

def upload(title, filename, text, fields):
    boundary = uuid.uuid4().hex; parts = []
    def add(name, value, filename=None, ctype=None):
        head = f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"' + (f'; filename="{filename}"' if filename else "") + "\r\n"
        if ctype: head += f"Content-Type: {ctype}\r\n"
        parts.append(head.encode() + b"\r\n" + (value if isinstance(value, bytes) else str(value).encode()) + b"\r\n")
    add("document", text.encode(), filename, "text/plain"); add("title", title)
    for k, v in fields.items():
        for x in (v if isinstance(v, list) else [v]): add(k, x)
    body = b"".join(parts) + f"--{boundary}--\r\n".encode()
    task = call("POST", "/api/documents/post_document/", raw=body, ctype=f"multipart/form-data; boundary={boundary}")
    for _ in range(90):
        res = call("GET", f"/api/tasks/?task_id={task}")
        if res and res[0]["status"] in ("SUCCESS", "FAILURE"):
            if res[0]["status"] == "FAILURE": raise SystemExit(f"[seed] consumption of {filename} failed: {res[0].get('result')}")
            return int(res[0]["related_document"])
        time.sleep(2)
    raise SystemExit(f"[seed] consumption of {filename} timed out")

if len(sys.argv) > 1 and sys.argv[1] == "init":
    init_admin(); sys.exit(0)

wait_ready()
AUTH = "Basic " + base64.b64encode(f"{USER}:{admin_password()}".encode()).decode()
me = call("GET", "/api/profile/"); log(f"authenticated as {me.get('email')}")
ids = {}

# Remove scratch objects an interrupted capture may have left behind.
for t in call("GET", "/api/tags/?name__istartswith=rea%20scratch").get("results", []):
    call("DELETE", f"/api/tags/{t['id']}/"); log(f"removed leftover scratch tag {t['name']}")

CORRESPONDENTS = [
    {"name": "Granite Ledger Quarry Office", "match": "", "matching_algorithm": 0},
    {"name": "Blue Heron Kitchen", "match": "", "matching_algorithm": 0},
    {"name": "Copperfield Annex Lettings", "match": "", "matching_algorithm": 0},
    {"name": "Saltmarsh Depot Stores", "match": "", "matching_algorithm": 0},
]
ids["correspondents"] = {c["name"]: ensure("correspondents", c) for c in CORRESPONDENTS}
TAGS = [
    {"name": "Inbox Triage", "color": "#2a9d8f", "is_inbox_tag": True, "match": "", "matching_algorithm": 0},
    {"name": "Tide Tables", "color": "#264653", "match": "", "matching_algorithm": 0},
    {"name": "Lamp Oil", "color": "#e9c46a", "match": "", "matching_algorithm": 0},
    {"name": "Audit Seaward Stack", "color": "#f4a261", "match": "", "matching_algorithm": 0},
    {"name": "Winter Rota", "color": "#e76f51", "match": "", "matching_algorithm": 0},
]
ids["tags"] = {t["name"]: ensure("tags", t) for t in TAGS}
DOCTYPES = [
    {"name": "Stone Count Report", "match": "", "matching_algorithm": 0},
    {"name": "Supplier Invoice", "match": "", "matching_algorithm": 0},
    {"name": "Shift Handover Note", "match": "", "matching_algorithm": 0},
]
ids["document_types"] = {t["name"]: ensure("document_types", t) for t in DOCTYPES}
PATHS = [
    {"name": "Lighthouse Rota Archive", "path": "rota/{{ correspondent }}/{{ title }}", "match": "", "matching_algorithm": 0},
    {"name": "Granite Ledger Vault", "path": "ledger/{{ created_year }}/{{ title }}", "match": "", "matching_algorithm": 0},
]
ids["storage_paths"] = {p["name"]: ensure("storage_paths", p) for p in PATHS}
FIELDS = [
    {"name": "Ledger Reference", "data_type": "string"},
    {"name": "Shift Number", "data_type": "integer"},
    {"name": "Invoice Total", "data_type": "monetary"},
]
ids["custom_fields"] = {f["name"]: ensure("custom_fields", f) for f in FIELDS}
C, T, D, P, F = ids["correspondents"], ids["tags"], ids["document_types"], ids["storage_paths"], ids["custom_fields"]

DOCS = [
    ("Granite Ledger Quarterly Stone Count", "granite-ledger-stone-count.txt",
     "Granite Ledger quarterly stone count\nNorth quarry: 412 blocks. Tidal yard: 97 blocks.\nAudited by Rui Castellanos on the fourteenth.\n",
     {"correspondent": C["Granite Ledger Quarry Office"], "document_type": D["Stone Count Report"], "storage_path": P["Granite Ledger Vault"],
      "tags": [T["Audit Seaward Stack"]], "created": "2026-03-14"},
     [("Ledger Reference", "Quarry North Stack"), ("Shift Number", 3)]),
    ("Blue Heron Kitchen Kelp Broth Invoice", "blue-heron-kelp-broth-invoice.txt",
     "Blue Heron Kitchen invoice\n36 bowls of smoked kelp broth for the night shift, served at 22:00.\nHead cook: Marisol Okonkwo-Reyes.\n",
     {"correspondent": C["Blue Heron Kitchen"], "document_type": D["Supplier Invoice"], "storage_path": P["Lighthouse Rota Archive"],
      "tags": [T["Tide Tables"]], "created": "2026-04-02"},
     [("Invoice Total", "EUR412.50"), ("Ledger Reference", "Kelp Broth Night Shift")]),
    ("Lighthouse Rota Winter Handover", "lighthouse-rota-winter-handover.txt",
     "Lighthouse Rota winter handover\nShift three starts at 22:00 and hands over at 06:00.\nAda Finch keeps the tide tables for January.\n",
     {"correspondent": C["Saltmarsh Depot Stores"], "document_type": D["Shift Handover Note"], "storage_path": P["Lighthouse Rota Archive"],
      "tags": [T["Winter Rota"], T["Tide Tables"]], "created": "2026-01-06"},
     [("Shift Number", 3), ("Ledger Reference", "Rota Ledger January")]),
    ("Copperfield Annex Lease Renewal", "copperfield-annex-lease-renewal.txt",
     "Copperfield Annex lease renewal\nThe east loft is renewed for 24 months; Mina Okafor countersigned for the lettings office.\n",
     {"correspondent": C["Copperfield Annex Lettings"], "created": "2026-02-20"},
     [("Ledger Reference", "Annex East Loft")]),
    ("Saltmarsh Depot Lamp Oil Delivery", "saltmarsh-depot-lamp-oil-delivery.txt",
     "Saltmarsh Depot delivery note\n180 litres of lamp oil delivered to bay 3 north; received by Tomas Vey.\n",
     {"correspondent": C["Saltmarsh Depot Stores"], "document_type": D["Supplier Invoice"], "tags": [T["Lamp Oil"], T["Winter Rota"]], "created": "2026-01-19"},
     [("Invoice Total", "EUR96.40"), ("Ledger Reference", "Depot Bay Three North")]),
]
ids["documents"] = {}
for title, fname, text, fields, cfs in DOCS:
    cur = find("documents", title, "title")
    doc_id = cur["id"] if cur else upload(title, fname, text, fields)
    if not cur: log(f"document {title!r} consumed -> {doc_id}")
    call("PATCH", f"/api/documents/{doc_id}/", {"custom_fields": [{"field": F[n], "value": v} for n, v in cfs]})
    ids["documents"][title] = doc_id
Dc = ids["documents"]

NOTES = {
    "Granite Ledger Quarterly Stone Count": "Rui Castellanos re-measured the seaward stack; cart number 7 is retired.",
    "Lighthouse Rota Winter Handover": "Ada Finch asked for the lamp room key to move to the Saltmarsh Depot locker.",
    "Saltmarsh Depot Lamp Oil Delivery": "Tomas Vey flagged two drums with dented lids for return.",
}
for title, note in NOTES.items():
    existing = call("GET", f"/api/documents/{Dc[title]}/notes/")
    if not any(n.get("note") == note for n in existing): call("POST", f"/api/documents/{Dc[title]}/notes/", {"note": note}); log(f"note added to {title!r}")

VIEWS = [
    {"name": "Granite Ledger Audits", "show_on_dashboard": True, "show_in_sidebar": True, "sort_field": "created", "sort_reverse": True,
     "filter_rules": [{"rule_type": 0, "value": "Granite"}]},
    {"name": "Blue Heron Kitchen Paperwork", "show_on_dashboard": False, "show_in_sidebar": True, "sort_field": "title", "sort_reverse": False,
     "filter_rules": [{"rule_type": 3, "value": str(C["Blue Heron Kitchen"])}]},
]
ids["saved_views"] = {v["name"]: ensure("saved_views", v) for v in VIEWS}
GROUPS = [
    {"name": "Quarry Auditors", "permissions": ["view_document", "view_tag", "view_correspondent", "add_note"]},
    {"name": "Kitchen Crew", "permissions": ["view_document", "add_document"]},
]
ids["groups"] = {g["name"]: ensure("groups", g) for g in GROUPS}
USERS = [
    {"username": "ada.finch", "first_name": "Ada", "last_name": "Finch", "email": "ada.finch@example.test", "is_active": True,
     "is_staff": False, "is_superuser": False, "groups": [ids["groups"]["Quarry Auditors"]], "user_permissions": []},
    {"username": "tomas.vey", "first_name": "Tomas", "last_name": "Vey", "email": "tomas.vey@example.test", "is_active": True,
     "is_staff": False, "is_superuser": False, "groups": [ids["groups"]["Kitchen Crew"]], "user_permissions": []},
]
ids["users"] = {u["username"]: ensure("users", u, "username") for u in USERS}
ACCOUNT = {"name": "Saltmarsh Depot Intake", "imap_server": "imap.saltmarsh-depot.example.test", "imap_port": 993, "imap_security": 2,
           "username": "intake@saltmarsh-depot.example.test", "password": secrets.token_urlsafe(16), "character_set": "UTF-8", "account_type": 1}
ids["mail_accounts"] = {ACCOUNT["name"]: ensure("mail_accounts", ACCOUNT)}
RULE = {"name": "Lamp Oil Delivery Notes", "account": ids["mail_accounts"][ACCOUNT["name"]], "folder": "INBOX", "filter_subject": "Lamp oil delivery",
        "maximum_age": 30, "action": 3, "attachment_type": 1, "consumption_scope": 1, "assign_title_from": 1, "assign_correspondent_from": 1,
        "assign_tags": [T["Lamp Oil"]], "order": 0, "enabled": True}
ids["mail_rules"] = {RULE["name"]: ensure("mail_rules", RULE)}
WORKFLOW = {"name": "Route Granite Ledger Scans", "order": 0, "enabled": True,
            "triggers": [{"type": 1, "sources": [1, 2, 3], "filter_filename": "*granite*", "matching_algorithm": 0, "match": ""}],
            "actions": [{"type": 1, "assign_tags": [T["Audit Seaward Stack"]], "assign_correspondent": C["Granite Ledger Quarry Office"],
                         "assign_storage_path": P["Granite Ledger Vault"]}]}
ids["workflows"] = {WORKFLOW["name"]: ensure("workflows", WORKFLOW)}

cfg = call("GET", "/api/config/")
if cfg and cfg[0].get("app_title") != "Saltmarsh Depot Archive":
    call("PATCH", f"/api/config/{cfg[0]['id']}/", {"app_title": "Saltmarsh Depot Archive"}); log("application title set")
ids["config"] = cfg[0]["id"] if cfg else None

json.dump(ids, open(os.path.join(DIR, "seed-ids.json"), "w"), indent=1)
log("seed-ids.json written: " + json.dumps({k: (list(v.values()) if isinstance(v, dict) else v) for k, v in ids.items()}))
