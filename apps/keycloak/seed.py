#!/usr/bin/env python3
"""Seed the showcase Keycloak with a synthetic realm through the Admin REST API (idempotent).

up.sh starts Keycloak with a temporary bootstrap admin ("rea-bootstrap") whose password, and the permanent admin password,
are generated at run time into ~/capture/keycloak/.admin (mode 600). This script creates the permanent master-realm admin
"rea-admin" (realm role "admin"), deletes the bootstrap user, then seeds the realm "lighthouse-rota": 3 realm roles,
3 groups (+1 subgroup) with role mappings, 4 users with group memberships, 2 public clients with 3 client roles,
1 client scope, 2 organizations (one member) and a copied browser authentication flow. Writes seed-ids.json (ids only).
Never prints a credential. Tokens come from the admin-cli password grant and live only in this process."""
import json, os, sys, time, urllib.error, urllib.parse, urllib.request

BASE = os.environ.get("BASE_URL", "http://127.0.0.1:3210")
DIR = os.environ.get("CAPTURE_DIR", os.path.expanduser("~/capture/keycloak"))
REALM = "lighthouse-rota"; R = f"/admin/realms/{REALM}"

def log(msg): print(f"[seed] {msg}", file=sys.stderr)

adm = dict(l.split("=", 1) for l in open(os.path.join(DIR, ".admin")).read().splitlines() if "=" in l)
_tok = {"v": None, "exp": 0, "user": None}

def token(user, pw):
    data = urllib.parse.urlencode({"grant_type": "password", "client_id": "admin-cli", "username": user, "password": pw}).encode()
    req = urllib.request.Request(BASE + "/realms/master/protocol/openid-connect/token", data=data, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as r: t = json.loads(r.read())
    except urllib.error.HTTPError as e:
        err = json.loads(e.read() or b"{}")
        if e.code in (400, 401) and err.get("error") == "invalid_grant": return None
        raise SystemExit(f"[seed] token request -> {e.code} {err.get('error')}: {err.get('error_description')}")
    _tok.update(v=t["access_token"], exp=time.time() + t["expires_in"] - 15, user=user); return True

def api(method, path, body=None, ok404=False, raw=None):
    if time.time() > _tok["exp"]: token(_tok["user"], adm["KC_ADMIN_PASSWORD"] if _tok["user"] == "rea-admin" else adm["KC_BOOTSTRAP_PASSWORD"])
    data = raw.encode() if raw is not None else (json.dumps(body).encode() if body is not None else None)
    req = urllib.request.Request(BASE + path, data=data, method=method)
    req.add_header("Authorization", "Bearer " + _tok["v"]); req.add_header("Accept", "application/json")
    if data is not None: req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            txt = r.read(); loc = r.headers.get("Location")
            return (json.loads(txt) if txt else None), r.status, loc
    except urllib.error.HTTPError as e:
        if e.code == 404 and ok404: return None, 404, None
        if e.code == 409 and method == "POST": return None, 409, None
        raise SystemExit(f"[seed] {method} {path} -> {e.code}: {e.read().decode(errors='replace')[:300]}")

def wait_ready():
    for _ in range(150):
        try:
            with urllib.request.urlopen(BASE + "/realms/master/.well-known/openid-configuration", timeout=5) as r:
                if r.status == 200: return
        except Exception: pass
        time.sleep(2)
    raise SystemExit("[seed] Keycloak did not become ready")

wait_ready(); log(f"keycloak ready at {BASE}")

# --- permanent admin: rea-admin replaces the temporary bootstrap admin ---
if not token("rea-admin", adm["KC_ADMIN_PASSWORD"]):
    if not token("rea-bootstrap", adm["KC_BOOTSTRAP_PASSWORD"]): raise SystemExit("[seed] neither admin can log in")
    api("POST", "/admin/realms/master/users", {"username": "rea-admin", "enabled": True, "email": "rea-admin@example.test", "emailVerified": True,
        "firstName": "Rea", "lastName": "Admin", "credentials": [{"type": "password", "value": adm["KC_ADMIN_PASSWORD"], "temporary": False}]})
    uid = api("GET", "/admin/realms/master/users?username=rea-admin&exact=true")[0][0]["id"]
    role = api("GET", "/admin/realms/master/roles/admin")[0]
    api("POST", f"/admin/realms/master/users/{uid}/role-mappings/realm", [role])
    if not token("rea-admin", adm["KC_ADMIN_PASSWORD"]): raise SystemExit("[seed] rea-admin cannot log in")
    log("permanent admin rea-admin created")
for u in api("GET", "/admin/realms/master/users?username=rea-bootstrap&exact=true")[0]:
    api("DELETE", f"/admin/realms/master/users/{u['id']}"); log("bootstrap admin removed")
ver = api("GET", "/admin/serverinfo")[0]["systemInfo"]["version"]; log(f"keycloak version {ver}")

# --- realm ---
if api("GET", R, ok404=True)[1] == 404:
    api("POST", "/admin/realms", {"realm": REALM, "enabled": True, "displayName": "Lighthouse Rota Identity",
        "loginWithEmailAllowed": True, "registrationAllowed": False, "rememberMe": True})
    log("realm created")
api("PUT", R, {"displayName": "Lighthouse Rota Identity", "organizationsEnabled": True, "rememberMe": True})
ids = {"realm": REALM, "keycloak_version": ver, "users": {}, "groups": {}, "clients": {}, "roles": {}, "client_roles": {},
       "client_scopes": {}, "organizations": {}, "flows": {}}

# Remove scratch users left by an interrupted capture so every capture starts from the same state.
for u in api("GET", f"{R}/users?search=rea-scratch&max=50")[0]:
    api("DELETE", f"{R}/users/{u['id']}"); log(f"removed leftover scratch user {u['username']}")

ROLES = [("tide-keeper", "Keeps the tide tables and signs the night log at the lamp gallery."),
         ("quarry-auditor", "Audits the Granite Ledger stone counts every quarter."),
         ("galley-steward", "Runs the Blue Heron Kitchen galley rota and orders kelp.")]
for name, desc in ROLES:
    api("POST", f"{R}/roles", {"name": name, "description": desc})
    ids["roles"][name] = api("GET", f"{R}/roles/{name}")[0]["id"]

GROUPS = [("Night Shift", "Lamp watch from 22:00 to 06:00; hands over at the Saltmarsh Depot bell.", "tide-keeper"),
          ("Quarry Crew", "Counts granite blocks in the north quarry and the tidal yard.", "quarry-auditor"),
          ("Galley Team", "Cooks and stewards for the Blue Heron Kitchen tide-table menu.", "galley-steward")]
group_desc = True
def find_group(name, parent=None):
    lst = api("GET", f"{R}/groups/{parent}/children?max=50" if parent else f"{R}/groups?search={urllib.parse.quote(name)}&exact=true")[0]
    return next((g for g in lst if g["name"] == name), None)
def make_group(name, desc, parent=None):
    global group_desc
    g = find_group(name, parent)
    if g: return g["id"]
    url = f"{R}/groups/{parent}/children" if parent else f"{R}/groups"
    body = {"name": name, **({"description": desc} if group_desc else {})}
    try: api("POST", url, body)
    except SystemExit as e:
        if "400" not in str(e): raise
        group_desc = False; api("POST", url, {"name": name}); log("groups have no description field in this version")
    return find_group(name, parent)["id"]
for name, desc, role in GROUPS:
    gid = make_group(name, desc); ids["groups"][name] = gid
    rr = api("GET", f"{R}/roles/{role}")[0]
    api("POST", f"{R}/groups/{gid}/role-mappings/realm", [rr])
ids["groups"]["Lamp Room Crew"] = make_group("Lamp Room Crew", "Trims wicks and polishes the Fresnel lens before dusk.", ids["groups"]["Night Shift"])

USERS = [("ada.finch", "Ada", "Finch", ["Night Shift", "Lamp Room Crew"], True),
         ("rui.castellanos", "Rui", "Castellanos", ["Quarry Crew"], True),
         ("mina.okafor", "Mina", "Okafor", ["Galley Team"], True),
         ("tomas.vey", "Tomas", "Vey", ["Night Shift"], False)]
for uname, first, last, groups, enabled in USERS:
    cur = api("GET", f"{R}/users?username={uname}&exact=true")[0]
    if not cur:
        api("POST", f"{R}/users", {"username": uname, "firstName": first, "lastName": last, "email": f"{uname}@example.test",
                                   "emailVerified": True, "enabled": enabled})
        cur = api("GET", f"{R}/users?username={uname}&exact=true")[0]; log(f"user {uname} created")
    uid = cur[0]["id"]; ids["users"][uname] = uid
    for g in groups: api("PUT", f"{R}/users/{uid}/groups/{ids['groups'][g]}")

CLIENTS = [("granite-ledger-portal", "Granite Ledger Portal", "Stone-count dashboard for the quarry auditors.",
            [("ledger-viewer", "Reads the quarterly stone counts."), ("ledger-editor", "Corrects tallies after an audit.")]),
           ("blue-heron-kitchen-till", "Blue Heron Kitchen Till", "Point-of-sale app for the tide-table menu sittings.",
            [("till-operator", "Opens and closes the till for each sitting.")])]
for cid, name, desc, croles in CLIENTS:
    cur = api("GET", f"{R}/clients?clientId={cid}")[0]
    if not cur:
        api("POST", f"{R}/clients", {"clientId": cid, "name": name, "description": desc, "publicClient": True, "protocol": "openid-connect",
                                     "standardFlowEnabled": True, "directAccessGrantsEnabled": False, "redirectUris": [f"/{cid}/*"]})
        cur = api("GET", f"{R}/clients?clientId={cid}")[0]; log(f"client {cid} created")
    cu = cur[0]["id"]; ids["clients"][cid] = cu
    for rname, rdesc in croles:
        api("POST", f"{R}/clients/{cu}/roles", {"name": rname, "description": rdesc})
        ids["client_roles"][rname] = api("GET", f"{R}/clients/{cu}/roles/{rname}")[0]["id"]
# client role mappings: Rui edits the ledger, Mina operates the till
gl = ids["clients"]["granite-ledger-portal"]; bh = ids["clients"]["blue-heron-kitchen-till"]
api("POST", f"{R}/users/{ids['users']['rui.castellanos']}/role-mappings/clients/{gl}", [api("GET", f"{R}/clients/{gl}/roles/ledger-editor")[0]])
api("POST", f"{R}/users/{ids['users']['mina.okafor']}/role-mappings/clients/{bh}", [api("GET", f"{R}/clients/{bh}/roles/till-operator")[0]])

cs = next((s for s in api("GET", f"{R}/client-scopes")[0] if s["name"] == "tide-tables"), None)
if not cs:
    api("POST", f"{R}/client-scopes", {"name": "tide-tables", "description": "Grants read access to the published tide tables.",
                                        "protocol": "openid-connect", "attributes": {"include.in.token.scope": "true", "display.on.consent.screen": "true",
                                        "consent.screen.text": "Read the Lighthouse Rota tide tables"}})
    cs = next(s for s in api("GET", f"{R}/client-scopes")[0] if s["name"] == "tide-tables"); log("client scope created")
ids["client_scopes"]["tide-tables"] = cs["id"]
api("PUT", f"{R}/clients/{gl}/optional-client-scopes/{cs['id']}")

ORGS = [("Copperfield Annex", "copperfield-annex", "Contractor crew that repaints the lamp gallery every spring.", "copperfield-annex.example.test"),
        ("Saltmarsh Depot", "saltmarsh-depot", "Supply depot for lamp oil, rope and dried kelp.", "saltmarsh-depot.example.test")]
for name, alias, desc, dom in ORGS:
    cur = [o for o in api("GET", f"{R}/organizations?search={urllib.parse.quote(name)}&exact=true")[0] if o["name"] == name]
    if not cur:
        api("POST", f"{R}/organizations", {"name": name, "alias": alias, "description": desc, "enabled": True, "domains": [{"name": dom, "verified": False}]})
        cur = [o for o in api("GET", f"{R}/organizations?search={urllib.parse.quote(name)}&exact=true")[0] if o["name"] == name]; log(f"organization {alias} created")
    ids["organizations"][alias] = cur[0]["id"]
sd = ids["organizations"]["saltmarsh-depot"]
if not any(m["username"] == "mina.okafor" for m in api("GET", f"{R}/organizations/{sd}/members")[0]):
    api("POST", f"{R}/organizations/{sd}/members", raw=json.dumps(ids["users"]["mina.okafor"]))

flows = api("GET", f"{R}/authentication/flows")[0]
fl = next((f for f in flows if f["alias"] == "granite gate browser"), None)
if not fl:
    api("POST", f"{R}/authentication/flows/browser/copy", {"newName": "granite gate browser"})
    fl = next(f for f in api("GET", f"{R}/authentication/flows")[0] if f["alias"] == "granite gate browser"); log("flow copied")
api("PUT", f"{R}/authentication/flows/{fl['id']}", {**fl, "description": "Browser login used by the Granite Ledger kiosks in the quarry office."})
ids["flows"]["granite gate browser"] = fl["id"]

json.dump(ids, open(os.path.join(DIR, "seed-ids.json"), "w"), indent=1)
log("seed-ids.json written: " + json.dumps(ids))
