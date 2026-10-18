#!/usr/bin/env python3
"""Seed a fresh NocoDB on 127.0.0.1:3103 with one base, two tables and 8 rows each. Idempotent.

The throwaway admin password is generated on first run and kept only in ./.admin (mode 600).
The JWT returned by signup/signin is held in memory for this process only and never written anywhere."""
import json, os, secrets, sys, urllib.request, urllib.error

BASE = os.environ.get("BASE_URL", "http://127.0.0.1:3103")
HERE = os.path.dirname(os.path.abspath(__file__))
ADMIN_FILE = os.path.join(HERE, ".admin")
EMAIL = "rea-admin@example.test"
BASE_TITLE = "Lighthouse Rota"

VESSELS = [
    {"name": "Granite Ledger", "flag": "Panama", "length_m": 189.5, "status": "Active"},
    {"name": "Blue Heron", "flag": "Liberia", "length_m": 142, "status": "In Port"},
    {"name": "Saffron Tide", "flag": "Malta", "length_m": 228.4, "status": "Active"},
    {"name": "Copper Lantern", "flag": "Marshall Islands", "length_m": 97, "status": "Laid Up"},
    {"name": "Northern Quill", "flag": "Norway", "length_m": 164.2, "status": "Active"},
    {"name": "Pale Meridian", "flag": "Singapore", "length_m": 199, "status": "In Port"},
    {"name": "Ember Compass", "flag": "Greece", "length_m": 120.6, "status": "Laid Up"},
    {"name": "Silver Anvil", "flag": "Cyprus", "length_m": 176.3, "status": "Active"},
]
PORT_CALLS = [
    {"vessel": "Granite Ledger", "berth": "Berth A1", "eta": "2026-10-20", "cranes": 3},
    {"vessel": "Blue Heron", "berth": "Berth B4", "eta": "2026-10-21", "cranes": 2},
    {"vessel": "Saffron Tide", "berth": "Berth A3", "eta": "2026-10-22", "cranes": 4},
    {"vessel": "Copper Lantern", "berth": "Berth C2", "eta": "2026-10-23", "cranes": 1},
    {"vessel": "Northern Quill", "berth": "Berth B1", "eta": "2026-10-24", "cranes": 2},
    {"vessel": "Pale Meridian", "berth": "Berth A2", "eta": "2026-10-25", "cranes": 3},
    {"vessel": "Ember Compass", "berth": "Berth C1", "eta": "2026-10-26", "cranes": 1},
    {"vessel": "Silver Anvil", "berth": "Berth B3", "eta": "2026-10-27", "cranes": 2},
]
STATUS_OPTIONS = [{"title": "Active", "color": "#cfdffe"}, {"title": "In Port", "color": "#d0f1fd"}, {"title": "Laid Up", "color": "#ffdaf6"}]


def req(method, path, body=None, token=None):
    data = None if body is None else json.dumps(body).encode()
    r = urllib.request.Request(BASE + path, data=data, method=method)
    r.add_header("content-type", "application/json")
    r.add_header("accept", "application/json")
    if token:
        r.add_header("xc-auth", token)
    try:
        with urllib.request.urlopen(r, timeout=60) as resp:
            text = resp.read().decode()
            return resp.status, (json.loads(text) if text else None)
    except urllib.error.HTTPError as e:
        text = e.read().decode()
        try:
            return e.code, json.loads(text)
        except ValueError:
            return e.code, {"raw": text[:300]}


def log(msg):
    print(f"[seed] {msg}", file=sys.stderr)


def load_or_create_password():
    if os.path.exists(ADMIN_FILE):
        for line in open(ADMIN_FILE):
            if line.startswith("password="):
                return line.split("=", 1)[1].strip()
    pw = secrets.token_urlsafe(18) + "Aa1!"
    fd = os.open(ADMIN_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(f"email={EMAIL}\npassword={pw}\n")
    os.chmod(ADMIN_FILE, 0o600)
    return pw


def auth(pw):
    st, body = req("POST", "/api/v1/auth/user/signup", {"email": EMAIL, "password": pw})
    if st == 200 and body and body.get("token"):
        log("signup ok (super admin created)")
        return body["token"]
    log(f"signup returned {st}; trying signin")
    st, body = req("POST", "/api/v1/auth/user/signin", {"email": EMAIL, "password": pw})
    if st != 200 or not body.get("token"):
        raise SystemExit(f"auth failed: {st} {json.dumps(body)[:200]}")
    log("signin ok")
    return body["token"]


def ensure_base(tok):
    st, body = req("GET", "/api/v2/meta/bases", token=tok)
    assert st == 200, (st, body)
    for b in body.get("list", []):
        if b.get("title") == BASE_TITLE:
            log(f"base exists {b['id']}")
            return b["id"]
    st, body = req("POST", "/api/v2/meta/bases", {"title": BASE_TITLE, "description": "Synthetic berth planning board for the Lighthouse Rota showcase"}, token=tok)
    assert st == 200, (st, body)
    log(f"base created {body['id']}")
    return body["id"]


def ensure_table(tok, base_id, title, columns):
    st, body = req("GET", f"/api/v2/meta/bases/{base_id}/tables", token=tok)
    assert st == 200, (st, body)
    for t in body.get("list", []):
        if t.get("title") == title:
            log(f"table {title} exists {t['id']}")
            return t["id"]
    payload = {"title": title, "table_name": title.lower().replace(" ", "_"), "columns": columns}
    st, body = req("POST", f"/api/v2/meta/bases/{base_id}/tables", payload, token=tok)
    assert st == 200, (st, body)
    log(f"table {title} created {body['id']}")
    return body["id"]


def ensure_rows(tok, table_id, rows):
    st, body = req("GET", f"/api/v2/tables/{table_id}/records?limit=1", token=tok)
    assert st == 200, (st, body)
    total = (body.get("pageInfo") or {}).get("totalRows", 0)
    if total >= len(rows):
        log(f"table {table_id} already has {total} rows")
        return
    st, body = req("POST", f"/api/v2/tables/{table_id}/records", rows, token=tok)
    assert st == 200, (st, body)
    log(f"inserted {len(body)} rows into {table_id}")


def main():
    pw = load_or_create_password()
    tok = auth(pw)
    base_id = ensure_base(tok)
    vessels_cols = [
        {"title": "Id", "column_name": "id", "uidt": "ID"},
        {"title": "name", "column_name": "name", "uidt": "SingleLineText", "pv": True},
        {"title": "flag", "column_name": "flag", "uidt": "SingleLineText"},
        {"title": "length_m", "column_name": "length_m", "uidt": "Number"},
        {"title": "status", "column_name": "status", "uidt": "SingleSelect", "dtxp": "'Active','In Port','Laid Up'", "colOptions": {"options": STATUS_OPTIONS}},
    ]
    port_cols = [
        {"title": "Id", "column_name": "id", "uidt": "ID"},
        {"title": "vessel", "column_name": "vessel", "uidt": "SingleLineText", "pv": True},
        {"title": "berth", "column_name": "berth", "uidt": "SingleLineText"},
        {"title": "eta", "column_name": "eta", "uidt": "Date"},
        {"title": "cranes", "column_name": "cranes", "uidt": "Number"},
    ]
    vessels_id = ensure_table(tok, base_id, "Vessels", vessels_cols)
    port_id = ensure_table(tok, base_id, "Port Calls", port_cols)
    ensure_rows(tok, vessels_id, VESSELS)
    ensure_rows(tok, port_id, PORT_CALLS)
    ids = {"base_id": base_id, "vessels_table_id": vessels_id, "port_calls_table_id": port_id}
    with open(os.path.join(HERE, "ids.json"), "w") as f:
        json.dump(ids, f, indent=1)
    print(json.dumps(ids))


if __name__ == "__main__":
    main()
