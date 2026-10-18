#!/usr/bin/env python3
"""Seed the showcase Memos with synthetic content through its JSON REST API (/api/v1, idempotent where practical).

The first account, "rea-admin" (display name Rea Admin, rea-admin@example.test), is created with POST /api/v1/users on
the fresh instance and becomes ADMIN. Three more users are created by the admin. All passwords are generated at run
time and kept only in ~/capture/memos/.admin (mode 600); access tokens from POST /api/v1/auth/signin live in this
process only. Seeds memos with tags, a pinned one, a task list, a location, an archived one, comments, reactions, a
reference relation, a space with a member and a pending invitation, a second space (Mina Okafor's) with a pending
invitation for the admin, a space memo, a saved memo view, a user bio and the
admin's general settings. Writes seed-ids.json (resource names only, no secrets). Never prints a password or token."""
import json, os, secrets, sys, time, urllib.error, urllib.parse, urllib.request

BASE = os.environ.get("BASE_URL", "http://127.0.0.1:3205")
DIR = os.environ.get("CAPTURE_DIR", os.path.expanduser("~/capture/memos"))
ADMIN_FILE = os.path.join(DIR, ".admin")
USERS = {  # username -> (display name, email, bio)
    "rea-admin": ("Rea Admin", "rea-admin@example.test", "Keeper of the Lighthouse Rota since the spring census."),
    "ada-finch": ("Ada Finch", "ada.finch@example.test", "Keeps the tide tables for the winter rota."),
    "rui-castellanos": ("Rui Castellanos", "rui.castellanos@example.test", "Audits the Granite Ledger stone counts."),
    "mina-okafor": ("Mina Okafor", "mina.okafor@example.test", "Relief keeper on Blue Heron Spit."),
}

def log(msg): print(f"[seed] {msg}", file=sys.stderr)

def load_passwords():
    kv = {}
    if os.path.exists(ADMIN_FILE):
        kv = dict(l.split("=", 1) for l in open(ADMIN_FILE).read().splitlines() if "=" in l)
    changed = False
    for u in USERS:
        k = "MEMOS_" + u.upper().replace("-", "_") + "_PASSWORD"
        if k not in kv: kv[k] = secrets.token_urlsafe(18); changed = True
    if changed:
        fd = os.open(ADMIN_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f: f.write("".join(f"{k}={v}\n" for k, v in kv.items()))
        log(f"wrote {ADMIN_FILE} (mode 600)")
    return {u: kv["MEMOS_" + u.upper().replace("-", "_") + "_PASSWORD"] for u in USERS}

def api(method, path, body=None, tok=None, ok=()):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method)
    req.add_header("Accept", "application/json")
    if data is not None: req.add_header("Content-Type", "application/json")
    if tok: req.add_header("Authorization", "Bearer " + tok)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read(); return (json.loads(raw) if raw else {}), r.status
    except urllib.error.HTTPError as e:
        if e.code in ok: return None, e.code
        raise SystemExit(f"[seed] {method} {path} -> {e.code}: {e.read().decode(errors='replace')[:400]}")

def wait_ready():
    for _ in range(60):
        try:
            with urllib.request.urlopen(BASE + "/api/v1/instance/profile", timeout=5) as r:
                if r.status == 200: return json.loads(r.read())
        except Exception: pass
        time.sleep(2)
    raise SystemExit("[seed] Memos did not become ready")

def signin(u, pw):
    d, _ = api("POST", "/api/v1/auth/signin", {"passwordCredentials": {"username": u, "password": pw}})
    return d["accessToken"]

prof = wait_ready(); log(f"memos {prof.get('version')} ready at {BASE}")
pws = load_passwords()
if prof.get("needsSetup"):
    dn, em, _ = USERS["rea-admin"]
    api("POST", "/api/v1/users", {"username": "rea-admin", "password": pws["rea-admin"], "role": "ADMIN", "displayName": dn, "email": em})
    log("first account rea-admin created (ADMIN)")
tok = {"rea-admin": signin("rea-admin", pws["rea-admin"])}
for u, (dn, em, bio) in USERS.items():
    cur, st = api("GET", f"/api/v1/users/{u}", tok=tok["rea-admin"], ok=(404,))
    if cur is None:
        api("POST", "/api/v1/users", {"username": u, "password": pws[u], "role": "USER", "displayName": dn, "email": em}, tok=tok["rea-admin"]); log(f"user {u} created")
        cur, _ = api("GET", f"/api/v1/users/{u}", tok=tok["rea-admin"])
    if cur.get("description") != bio:
        api("PATCH", f"/api/v1/users/{u}?updateMask=description", {"name": f"users/{u}", "description": bio}, tok=tok["rea-admin"])
    if u not in tok: tok[u] = signin(u, pws[u])
ids = {"users": {u: f"users/{u}" for u in USERS}, "memos": {}, "comments": {}, "spaces": {}, "views": {}}

def all_memos(t):
    out = []
    for state in ("NORMAL", "ARCHIVED"):
        d, _ = api("GET", f"/api/v1/memos?pageSize=200&state={state}", tok=t); out += d.get("memos", [])
    return out

def ensure_memo(key, user, memo):
    for m in all_memos(tok[user]):
        if m["content"] == memo["content"] and m["creator"] == f"users/{user}": ids["memos"][key] = m["name"]; return m["name"]
    d, _ = api("POST", "/api/v1/memos", memo, tok=tok[user]); log(f"memo {key} created")
    ids["memos"][key] = d["name"]; return d["name"]

MEMOS = [  # single-line contents stay under 80 characters so they read as one answerable value
    ("winter-rota", "rea-admin", {"content": "#lighthouse-rota Shift three at Granite Point Light runs 22:00 to 06:00.", "visibility": "PROTECTED"}),
    ("stone-count", "rea-admin", {"content": "#granite-ledger Stone count GL-2291: 412 blocks in the north quarry.", "visibility": "PUBLIC"}),
    ("kitchen", "rea-admin", {"content": "#blue-heron-kitchen Blue Heron Kitchen serves 36 covers per sitting.", "visibility": "PUBLIC",
                              "location": {"placeholder": "Blue Heron Spit boathouse", "latitude": 12.5, "longitude": -31.25}}),
    ("lamp-oil", "rea-admin", {"content": "#saltmarsh-depot Order SO-4471: 180 litres of lamp oil delivered.", "visibility": "PRIVATE"}),
    ("checklist", "rea-admin", {"content": "Granite Ledger checklist #granite-ledger\n\n- [ ] Re-measure the seaward stack\n- [x] Retire cart number 7", "visibility": "PROTECTED"}),
    ("beacon", "rea-admin", {"content": "#copperfield-annex Copperfield Annex beacon converted to an LED cluster.", "visibility": "PROTECTED"}),
    ("tide-table", "ada-finch", {"content": "#lighthouse-rota January low water at Granite Point: 04:12 on the third.", "visibility": "PROTECTED"}),
    ("cart-seven", "rui-castellanos", {"content": "#granite-ledger Cart number 7 retired; wheels sent to the annex workshop.", "visibility": "PUBLIC"}),
]
for key, user, memo in MEMOS: ensure_memo(key, user, memo)

# pin the winter rota (the pinned flag is ignored on create) and archive the beacon memo
m, _ = api("GET", f"/api/v1/{ids['memos']['winter-rota']}", tok=tok["rea-admin"])
if not m.get("pinned"):
    api("PATCH", f"/api/v1/{ids['memos']['winter-rota']}?updateMask=pinned", {"name": ids["memos"]["winter-rota"], "pinned": True}, tok=tok["rea-admin"]); log("winter rota pinned")
# archive the beacon memo
m, _ = api("GET", f"/api/v1/{ids['memos']['beacon']}", tok=tok["rea-admin"])
if m["state"] != "ARCHIVED":
    api("PATCH", f"/api/v1/{ids['memos']['beacon']}?updateMask=state", {"name": ids["memos"]["beacon"], "state": "ARCHIVED"}, tok=tok["rea-admin"]); log("beacon memo archived")

def ensure_comment(key, user, on, content):
    d, _ = api("GET", f"/api/v1/{ids['memos'][on]}/comments", tok=tok[user])
    for c in d.get("memos", []):
        if c["content"] == content: ids["comments"][key] = c["name"]; return
    c, _ = api("POST", f"/api/v1/{ids['memos'][on]}/comments", {"content": content, "visibility": "PROTECTED"}, tok=tok[user]); log(f"comment {key} created")
    ids["comments"][key] = c["name"]

ensure_comment("ada-on-rota", "ada-finch", "winter-rota", "I will bring the January tide tables to the handover.")
ensure_comment("rui-on-count", "rui-castellanos", "stone-count", "Count confirmed at the tidal yard; two blocks are cracked.")
ensure_comment("admin-on-tide", "rea-admin", "tide-table", "Thanks Ada, copied into the rota binder.")

def ensure_reaction(user, on, rtype):
    name = ids["memos"][on]
    d, _ = api("GET", f"/api/v1/{name}/reactions", tok=tok[user])
    if any(r["creator"] == f"users/{user}" and r["reactionType"] == rtype for r in d.get("reactions", [])): return
    api("POST", f"/api/v1/{name}/reactions", {"name": name, "reaction": {"contentId": name, "reactionType": rtype}}, tok=tok[user]); log(f"reaction {rtype} by {user} on {on}")

ensure_reaction("mina-okafor", "stone-count", "👍")
ensure_reaction("ada-finch", "winter-rota", "🎉")
ensure_reaction("rui-castellanos", "kitchen", "❤️")

# checklist references the stone count
rel, _ = api("GET", f"/api/v1/{ids['memos']['checklist']}/relations", tok=tok["rea-admin"])
if not any(r["type"] == "REFERENCE" for r in rel.get("relations", [])):
    api("PATCH", f"/api/v1/{ids['memos']['checklist']}/relations", {"name": ids["memos"]["checklist"], "relations": [
        {"memo": {"name": ids["memos"]["checklist"]}, "relatedMemo": {"name": ids["memos"]["stone-count"]}, "type": "REFERENCE"}]}, tok=tok["rea-admin"]); log("relation set")

# a space with one accepted member and one pending invitation, and a memo placed in it
sp, _ = api("GET", "/api/v1/spaces", tok=tok["rea-admin"])
space = next((s for s in sp.get("spaces", []) if s["title"] == "Saltmarsh Depot Crew"), None)
if space is None:
    space, _ = api("POST", "/api/v1/spaces", {"title": "Saltmarsh Depot Crew", "description": "Keepers and quartermasters of the Saltmarsh Depot.", "icon": {"lucide": "anchor"}}, tok=tok["rea-admin"]); log("space created")
ids["spaces"]["crew"] = space["name"]
inv, _ = api("GET", f"/api/v1/{space['name']}/invitations", tok=tok["rea-admin"])
mem, _ = api("GET", f"/api/v1/{space['name']}/members", tok=tok["rea-admin"])
member_users = json.dumps(mem)
for u in ("ada-finch", "mina-okafor"):
    if f"users/{u}" in member_users or f"users/{u}" in json.dumps(inv): continue
    api("POST", f"/api/v1/{space['name']}/invitations", {"invitee": f"users/{u}", "role": "USER"}, tok=tok["rea-admin"]); log(f"{u} invited")
if "users/ada-finch" not in member_users:
    api("POST", f"/api/v1/{space['name']}/invitations/ada-finch:accept", {"name": f"{space['name']}/invitations/ada-finch"}, tok=tok["ada-finch"]); log("ada-finch accepted")
# a second space owned by Mina Okafor with a pending invitation for the admin (shows up in the admin's own invitation list)
sp2, _ = api("GET", "/api/v1/spaces", tok=tok["mina-okafor"])
kitchen_space = next((s for s in sp2.get("spaces", []) if s["title"] == "Blue Heron Kitchen Rota"), None)
if kitchen_space is None:
    kitchen_space, _ = api("POST", "/api/v1/spaces", {"title": "Blue Heron Kitchen Rota", "description": "Night-shift supper rota for the Heron Flats keepers.", "icon": {"lucide": "soup"}}, tok=tok["mina-okafor"]); log("space Blue Heron Kitchen Rota created by mina-okafor")
ids["spaces"]["kitchen"] = kitchen_space["name"]
inv2, _ = api("GET", f"/api/v1/{kitchen_space['name']}/invitations", tok=tok["mina-okafor"])
if "users/rea-admin" not in json.dumps(inv2):
    api("POST", f"/api/v1/{kitchen_space['name']}/invitations", {"invitee": "users/rea-admin", "role": "USER"}, tok=tok["mina-okafor"]); log("rea-admin invited to the kitchen space (left pending)")
ensure_memo("crew-meeting", "rea-admin", {"content": "#saltmarsh-depot Crew meeting at the Copperfield Annex boathouse, 18:30.", "visibility": "SPACE", "space": space["name"]})

# a saved memo view and the admin's general settings
vw, _ = api("GET", "/api/v1/users/rea-admin/views", tok=tok["rea-admin"])
view = next((v for v in vw.get("memoViews", vw.get("views", [])) if v["title"] == "Granite Ledger notes"), None)
if view is None:
    view, _ = api("POST", "/api/v1/users/rea-admin/views", {"title": "Granite Ledger notes", "filter": "\"granite-ledger\" in tags"}, tok=tok["rea-admin"]); log("memo view created")
ids["views"]["granite"] = view["name"]
api("PATCH", "/api/v1/users/rea-admin/settings/GENERAL?updateMask=memo_visibility,locale",
    {"name": "users/rea-admin/settings/GENERAL", "generalSetting": {"locale": "en", "memoVisibility": "PROTECTED"}}, tok=tok["rea-admin"])

json.dump(ids, open(os.path.join(DIR, "seed-ids.json"), "w"), indent=1)
log("seed-ids.json written")
