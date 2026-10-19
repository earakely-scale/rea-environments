#!/usr/bin/env python3
"""Initialise, unseal and seed the showcase Vault with invented configuration through its HTTP API (idempotent).

Initialises with one key share (sys/init), unseals, and keeps the unseal key and root token only in ~/capture/vault/.admin
(mode 600) together with the generated password of the UI admin `rea-admin` (userpass). Never prints any of them.
Seeds: 2 KV v2 mounts with 6 configuration entries (owner/region/rotation_days/tier-style keys, invented values, custom
metadata), 4 ACL policies (+ the rea-admin policy), 2 auth methods (userpass, approle without roles), 4 identity entities with
metadata, 4 entity aliases on userpass, 3 identity groups. Removes scratch objects left by an interrupted capture.
Writes seed-ids.json (ids, names and accessors only, no secrets) for capture.mjs."""
import json, os, secrets, sys, time, urllib.error, urllib.request

BASE = os.environ.get("BASE_URL", "http://127.0.0.1:3303")
DIR = os.environ.get("CAPTURE_DIR", os.path.expanduser("~/capture/vault"))
ADMIN_FILE = os.path.join(DIR, ".admin")


def log(msg): print(f"[seed] {msg}", file=sys.stderr)


def read_admin():
    if not os.path.exists(ADMIN_FILE): return {}
    return dict(l.split("=", 1) for l in open(ADMIN_FILE).read().splitlines() if "=" in l)


def write_admin(kv):
    fd = os.open(ADMIN_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f: f.write("".join(f"{k}={v}\n" for k, v in kv.items()))
    os.chmod(ADMIN_FILE, 0o600)


def api(method, path, body=None, token=None, ok404=False):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method)
    req.add_header("Accept", "application/json")
    if data is not None: req.add_header("Content-Type", "application/json")
    if token: req.add_header("X-Vault-Token", token)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read()
            return (json.loads(raw) if raw else {}), r.status
    except urllib.error.HTTPError as e:
        if e.code == 404 and ok404: return None, 404
        detail = e.read().decode(errors="replace")[:300]
        raise SystemExit(f"[seed] {method} {path} -> {e.code}: {detail}")


def wait_ready():
    for _ in range(90):
        try:
            with urllib.request.urlopen(BASE + "/v1/sys/seal-status", timeout=5) as r:
                if r.status == 200: return json.loads(r.read())
        except Exception: pass
        time.sleep(2)
    raise SystemExit("[seed] Vault did not answer")


st = wait_ready(); log(f"vault {st.get('version')} initialized={st['initialized']} sealed={st['sealed']}")
adm = read_admin()
if not st["initialized"]:
    init, _ = api("PUT", "/v1/sys/init", {"secret_shares": 1, "secret_threshold": 1})
    adm = {"VAULT_UNSEAL_KEY": init["keys_base64"][0], "VAULT_ROOT_TOKEN": init["root_token"],
           "VAULT_ADMIN_USER": "rea-admin", "VAULT_ADMIN_PASSWORD": secrets.token_urlsafe(21)}
    write_admin(adm); log(f"initialised with one key share; material written to {ADMIN_FILE} (mode 600)")
elif "VAULT_ROOT_TOKEN" not in adm:
    raise SystemExit("[seed] Vault is initialised but .admin is missing; tear the volume down and start again")
if api("GET", "/v1/sys/seal-status")[0]["sealed"]:
    api("PUT", "/v1/sys/unseal", {"key": adm["VAULT_UNSEAL_KEY"]}); log("unsealed")
ROOT = adm["VAULT_ROOT_TOKEN"]
for _ in range(30):
    h, _ = api("GET", "/v1/sys/seal-status")
    if not h["sealed"]: break
    time.sleep(1)
time.sleep(2)


def call(method, path, body=None, ok404=False): return api(method, path, body, token=ROOT, ok404=ok404)


ids = {"mounts": {}, "auth": {}, "policies": [], "kv": {}, "entities": {}, "aliases": {}, "groups": {}}

# --- secrets engines (KV v2) ---
MOUNTS = {
    "rota-config": "Shift and station settings for the Lighthouse Rota",
    "ledger-config": "Quarry audit settings kept by the Granite Ledger crew",
}
have, _ = call("GET", "/v1/sys/mounts")
for name, desc in MOUNTS.items():
    if f"{name}/" not in have["data"]:
        call("POST", f"/v1/sys/mounts/{name}", {"type": "kv", "description": desc, "options": {"version": "2"}}); log(f"mount {name} enabled")
time.sleep(2)
have, _ = call("GET", "/v1/sys/mounts")
for name in MOUNTS: ids["mounts"][name] = have["data"][f"{name}/"]["accessor"]

# --- auth methods (userpass for the UI admin, approle listed but without roles) ---
AUTH = {"userpass": "Crew sign-in for the Lighthouse Rota console", "approle": "Machine sign-in reserved for the Saltmarsh Depot scanners"}
have, _ = call("GET", "/v1/sys/auth")
for name, desc in AUTH.items():
    if f"{name}/" not in have["data"]:
        call("POST", f"/v1/sys/auth/{name}", {"type": name, "description": desc}); log(f"auth {name} enabled")
have, _ = call("GET", "/v1/sys/auth")
for name in AUTH: ids["auth"][name] = have["data"][f"{name}/"]["accessor"]

# --- ACL policies ---
POLICIES = {
    "lighthouse-rota-read": 'path "rota-config/data/lighthouse-rota/*" {\n  capabilities = ["read", "list"]\n}\npath "rota-config/metadata/lighthouse-rota/*" {\n  capabilities = ["read", "list"]\n}\n',
    "granite-ledger-ops": 'path "ledger-config/data/granite-ledger/*" {\n  capabilities = ["create", "read", "update", "list"]\n}\npath "ledger-config/metadata/granite-ledger/*" {\n  capabilities = ["read", "list"]\n}\n',
    "blue-heron-kitchen-menu": 'path "rota-config/data/blue-heron-kitchen/*" {\n  capabilities = ["create", "read", "update"]\n}\n',
    "saltmarsh-depot-audit": 'path "rota-config/metadata/saltmarsh-depot/*" {\n  capabilities = ["read", "list"]\n}\npath "rota-config/data/copperfield-annex/*" {\n  capabilities = ["read"]\n}\n',
    "rea-admin": 'path "*" {\n  capabilities = ["create", "read", "update", "patch", "delete", "list", "sudo"]\n}\n',
}
for name, hcl in POLICIES.items():
    call("PUT", f"/v1/sys/policies/acl/{name}", {"policy": hcl})
ids["policies"] = [p for p in POLICIES if p != "rea-admin"]
log(f"{len(POLICIES)} policies written")

# the UI admin (password generated above, kept only in .admin)
call("POST", "/v1/auth/userpass/users/rea-admin", {"password": adm["VAULT_ADMIN_PASSWORD"], "token_policies": "rea-admin", "token_ttl": "2h"})
log("userpass user rea-admin written")

# --- KV v2 configuration entries (configuration-like keys, invented values) ---
KV = [
    ("rota-config", "lighthouse-rota/shift-plan",
     {"owner": "Ada Finch", "region": "Granite Point North", "rotation_days": "14", "tier": "night watch tier",
      "shift_window": "22:00 to 06:00", "lamp_oil_litres": "180", "handover_desk": "Tide Table Desk"},
     {"steward": "Ada Finch", "review_board": "Lighthouse Rota Council"}),
    ("rota-config", "lighthouse-rota/tide-tables",
     {"owner": "Tomas Vey", "region": "Saltmarsh Point South", "rotation_days": "28", "tier": "almanac tier",
      "publication": "January tide almanac", "chart_reference": "LR-TIDE-0117"}, None),
    ("rota-config", "blue-heron-kitchen/menu-cycle",
     {"owner": "Mina Okafor", "region": "Tidewater Quay", "rotation_days": "7", "tier": "galley standard",
      "covers_per_sitting": "36 covers", "head_cook": "Marisol Okonkwo-Reyes"},
     {"steward": "Mina Okafor", "review_board": "Blue Heron Tasting Panel"}),
    ("rota-config", "saltmarsh-depot/inventory",
     {"owner": "Tomas Vey", "region": "Saltmarsh Flats East", "rotation_days": "30", "tier": "bulk storage tier",
      "bay_count": "12 covered bays", "forklift_fleet": "three electric forklifts"},
     {"steward": "Tomas Vey", "review_board": "Saltmarsh Depot Yard Committee"}),
    ("rota-config", "copperfield-annex/archive",
     {"owner": "Rui Castellanos", "region": "Copperfield Hill", "rotation_days": "90", "tier": "cold archive tier",
      "shelf_code": "CA-ROW-0417", "humidity_band": "between 40 and 45 percent"}, None),
    ("ledger-config", "granite-ledger/quarry-audit",
     {"owner": "Rui Castellanos", "region": "North Quarry Terrace", "rotation_days": "120", "tier": "audited stone count",
      "audit_reference": "GL-2291", "block_count": "412 blocks north quarry", "tidal_yard_count": "97 blocks tidal yard"},
     {"steward": "Rui Castellanos", "review_board": "Granite Ledger Audit Circle"}),
]
for mount, key, data, custom in KV:
    cur, _ = call("GET", f"/v1/{mount}/data/{key}", ok404=True)
    if cur is None or cur["data"]["data"] != data:
        call("POST", f"/v1/{mount}/data/{key}", {"data": data}); log(f"kv {mount}/{key} written")
    if custom:
        call("POST", f"/v1/{mount}/metadata/{key}", {"custom_metadata": custom, "max_versions": 10})
    ids["kv"].setdefault(mount, []).append(key)

# --- identity entities, aliases on userpass, groups ---
ENTITIES = {
    "ada-finch": ({"display_name": "Ada Finch", "team": "Lighthouse Rota", "desk": "Tide Table Desk", "email": "ada.finch@example.test"}, ["lighthouse-rota-read"]),
    "rui-castellanos": ({"display_name": "Rui Castellanos", "team": "Granite Ledger", "desk": "North Quarry Audit Desk", "email": "rui.castellanos@example.test"}, ["granite-ledger-ops"]),
    "mina-okafor": ({"display_name": "Mina Okafor", "team": "Blue Heron Kitchen", "desk": "Galley Planning Desk", "email": "mina.okafor@example.test"}, ["blue-heron-kitchen-menu"]),
    "tomas-vey": ({"display_name": "Tomas Vey", "team": "Saltmarsh Depot", "desk": "Bulk Store Ledger Desk", "email": "tomas.vey@example.test"}, ["saltmarsh-depot-audit"]),
}
for name, (meta, pols) in ENTITIES.items():
    call("POST", f"/v1/identity/entity/name/{name}", {"metadata": meta, "policies": pols})
    ent, _ = call("GET", f"/v1/identity/entity/name/{name}")
    ids["entities"][name] = ent["data"]["id"]
    alias_name = name.replace("-", ".")
    if not any(a["name"] == alias_name for a in ent["data"].get("aliases") or []):
        call("POST", "/v1/identity/entity-alias", {"name": alias_name, "canonical_id": ent["data"]["id"], "mount_accessor": ids["auth"]["userpass"]})
    ent, _ = call("GET", f"/v1/identity/entity/name/{name}")
    ids["aliases"][alias_name] = next(a["id"] for a in ent["data"]["aliases"] if a["name"] == alias_name)
log(f"{len(ENTITIES)} entities with aliases")
GROUPS = {
    "granite-ledger-crew": ({"purpose": "Quarry audits and stone counts", "meets": "first Monday at the north quarry"}, ["rui-castellanos", "tomas-vey"], ["granite-ledger-ops"]),
    "blue-heron-kitchen-staff": ({"purpose": "Menus that follow the tides", "meets": "Thursday tasting at Tidewater Quay"}, ["mina-okafor", "ada-finch"], ["blue-heron-kitchen-menu"]),
    "copperfield-annex-reviewers": ({"purpose": "Cold archive reviews for Copperfield Annex", "meets": "quarterly in the annex reading room"}, ["rui-castellanos"], ["saltmarsh-depot-audit"]),
}
for name, (meta, members, pols) in GROUPS.items():
    call("POST", f"/v1/identity/group/name/{name}", {"type": "internal", "metadata": meta, "policies": pols,
                                                      "member_entity_ids": [ids["entities"][m] for m in members]})
    g, _ = call("GET", f"/v1/identity/group/name/{name}"); ids["groups"][name] = g["data"]["id"]
log(f"{len(GROUPS)} groups")

# --- leftovers from an interrupted capture ---
call("DELETE", "/v1/rota-config/metadata/scratch/rea-scratch-note")
call("DELETE", "/v1/sys/policies/acl/rea-scratch-policy")
left, _ = call("GET", "/v1/identity/entity/name/rea-scratch-entity", ok404=True)
if left: call("DELETE", "/v1/identity/entity/name/rea-scratch-entity"); log("removed leftover scratch entity")

json.dump(ids, open(os.path.join(DIR, "seed-ids.json"), "w"), indent=1)
log("wrote seed-ids.json")
