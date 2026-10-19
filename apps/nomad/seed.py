#!/usr/bin/env python3
"""Seed the showcase Nomad dev agent with invented namespaces, a node pool, node metadata and jobs (idempotent).

The dev agent runs with ACLs off, so there is no admin account and no credential to keep: every call is anonymous on the
loopback HTTP API. Seeds 2 namespaces, 1 node pool, dynamic metadata on the dev node, 5 jobs (2 service, 2 batch of which one
periodic, 1 parameterized with one dispatched child) across the namespaces, and a second version of one service job.
Task drivers are raw_exec running /bin/sleep or a one-line echo inside the agent container. Writes seed-ids.json."""
import json, os, sys, time, urllib.error, urllib.request

BASE = os.environ.get("BASE_URL", "http://127.0.0.1:3304")
DIR = os.environ.get("CAPTURE_DIR", os.path.expanduser("~/capture/nomad"))
REGION, DC = "saltmarsh", "granite-point"

def log(msg): print(f"[seed] {msg}", file=sys.stderr)

def api(method, path, body=None, ok404=False):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method)
    req.add_header("Accept", "application/json")
    if data is not None: req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read()
            try: return (json.loads(raw) if raw else {}), r.status
            except ValueError: return {}, r.status
    except urllib.error.HTTPError as e:
        if e.code == 404 and ok404: return None, 404
        raise SystemExit(f"[seed] {method} {path} -> {e.code}: {e.read().decode(errors='replace')[:400]}")

def wait_ready():
    for _ in range(90):
        try:
            nodes, _ = api("GET", "/v1/nodes")
            if nodes and nodes[0]["Status"] == "ready": return nodes[0]
        except Exception: pass
        time.sleep(2)
    raise SystemExit("[seed] Nomad dev node did not become ready")

def sleeper(name, meta, cpu=40, mem=32):
    return {"Name": name, "Driver": "raw_exec", "Config": {"command": "/bin/sleep", "args": ["86400"]},
            "Resources": {"CPU": cpu, "MemoryMB": mem}, "Meta": meta}

def echo(name, line, meta):
    return {"Name": name, "Driver": "raw_exec", "Config": {"command": "/bin/sh", "args": ["-c", f"echo '{line}'"]},
            "Resources": {"CPU": 40, "MemoryMB": 32}, "Meta": meta}

def job(jid, ns, typ, meta, groups, **extra):
    return {"ID": jid, "Name": jid, "Namespace": ns, "Region": REGION, "Type": typ, "Datacenters": [DC], "Meta": meta,
            "TaskGroups": groups, **extra}

node = wait_ready(); log(f"dev node {node['Name']} ready ({node['Version']})")

# Purge scratch jobs left behind by an interrupted capture so every capture starts from the same state.
for left in api("GET", "/v1/jobs?namespace=*&prefix=rea-scratch")[0] or []:
    api("DELETE", f"/v1/job/{left['ID']}?namespace={left['Namespace']}&purge=true"); log(f"purged leftover {left['ID']}")

NAMESPACES = [
    {"Name": "lighthouse-rota", "Description": "Night shifts, lamp oil and tide tables for the Lighthouse Rota",
     "Meta": {"steward": "Ada Finch", "shift_pattern": "three shifts from 22:00 to 06:00"}},
    {"Name": "granite-ledger", "Description": "Quarry audits and stone counts for the Granite Ledger",
     "Meta": {"steward": "Rui Castellanos", "ledger_series": "GL-2291 quarterly series"}},
]
for ns in NAMESPACES:
    api("PUT", f"/v1/namespace/{ns['Name']}", ns); log(f"namespace {ns['Name']} upserted")

POOL = {"Name": "saltmarsh-depot", "Description": "Cold-store hosts at the Saltmarsh Depot (no hosts enrolled yet)",
        "Meta": {"steward": "Tomas Vey", "loading_bay": "bay 4 beside the eel smokehouse"}}
api("PUT", "/v1/node/pools", POOL); log("node pool saltmarsh-depot upserted")

api("POST", f"/v1/client/metadata?node_id={node['ID']}", {"Meta": {"cabinet": "Copperfield Annex cabinet 7", "caretaker": "Mina Okafor"}})
log("dev node metadata set")

KITCHEN_V0 = job("blue-heron-kitchen-orders", "lighthouse-rota", "service",
    {"steward": "Mina Okafor", "kitchen_menu": "smoked kelp broth with tide-table bread", "covers": "36 covers per sitting"},
    [{"Name": "tide-table-counter", "Count": 2, "Meta": {"counter_lead": "Marisol Okonkwo-Reyes", "sitting": "second sitting at 21:30"},
      "Tasks": [sleeper("order-board", {"board_label": "Blue Heron order board"})]},
     {"Name": "kelp-smoker", "Count": 1, "Meta": {"smoker_batch": "kelp batch K-17 from the north cove"},
      "Tasks": [sleeper("smoker-timer", {"timer_label": "kelp smoke timer"}), sleeper("ash-log", {"log_label": "smoker ash log"}, cpu=20, mem=16)]}],
    Priority=60)
KITCHEN_V1 = json.loads(json.dumps(KITCHEN_V0))
KITCHEN_V1["Meta"]["kitchen_menu"] = "neap tide menu with oat crackers"

JOBS = [
    KITCHEN_V0,
    job("lighthouse-rota-night-watch", "lighthouse-rota", "service",
        {"steward": "Ada Finch", "watch_rule": "lamp checked every forty minutes", "lamp_oil": "180 litres for the winter"},
        [{"Name": "lamp-room", "Count": 1, "Meta": {"keeper": "Tomas Vey", "lens_order": "second-order Fresnel lens"},
          "Tasks": [sleeper("lamp-watch", {"watch_label": "night watch log"})]}], Priority=70),
    job("granite-ledger-stone-count", "granite-ledger", "batch",
        {"auditor": "Rui Castellanos", "ledger_ref": "GL-2291", "tally": "412 blocks in the north quarry"},
        [{"Name": "quarry-tally", "Count": 1, "Meta": {"yard": "97 blocks in the tidal yard"},
          "RestartPolicy": {"Attempts": 0, "Mode": "fail"},
          "Tasks": [echo("count-blocks", "412 blocks counted in the north quarry", {"cart": "cart number 7 retired"})]}]),
    job("granite-ledger-seaward-remeasure", "granite-ledger", "batch",
        {"auditor": "Rui Castellanos", "schedule_note": "Monday dawn remeasure of the seaward stack"},
        [{"Name": "seaward-stack", "Count": 1, "Meta": {"stack": "seaward stack of 58 blocks"},
          "Tasks": [echo("remeasure", "seaward stack remeasured", {"tape": "thirty-metre survey tape"})]}],
        Periodic={"Enabled": True, "Spec": "0 6 * * 1", "SpecType": "cron", "ProhibitOverlap": True, "TimeZone": "UTC"}),
    job("saltmarsh-depot-cold-store", "default", "service",
        {"steward": "Tomas Vey", "cold_store": "eel smokehouse cold room at 3 degrees"},
        [{"Name": "cold-room", "Count": 1, "Meta": {"shelf_plan": "twelve shelves of smoked eel"},
          "Tasks": [sleeper("thermometer", {"probe_label": "cold room probe"})]}], NodePool="saltmarsh-depot"),
    job("copperfield-annex-ledger-sync", "granite-ledger", "batch",
        {"clerk": "Mina Okafor", "archive": "Copperfield Annex archive shelf 3"},
        [{"Name": "ledger-copy", "Count": 1, "RestartPolicy": {"Attempts": 0, "Mode": "fail"},
          "Tasks": [echo("copy-ledger", "ledger copied to the annex", {"binder": "green cloth binder"})]}],
        ParameterizedJob={"Payload": "optional", "MetaRequired": ["ledger_ref"], "MetaOptional": ["requested_by"]}),
]

ids = {"node": {"id": node["ID"], "name": node["Name"]}, "jobs": {}, "namespaces": [n["Name"] for n in NAMESPACES], "node_pool": POOL["Name"]}
for j in JOBS:
    cur, _ = api("GET", f"/v1/job/{j['ID']}?namespace={j['Namespace']}", ok404=True)
    if cur is None:
        api("POST", "/v1/jobs", {"Job": j}); log(f"job {j['Namespace']}/{j['ID']} registered ({j['Type']})")
    ids["jobs"][j["ID"]] = j["Namespace"]

time.sleep(3)
vers, _ = api("GET", f"/v1/job/{KITCHEN_V1['ID']}/versions?namespace=lighthouse-rota")
if len(vers.get("Versions", [])) < 2:
    for _ in range(30):  # wait for the first deployment to settle before registering version 1
        deps, _ = api("GET", f"/v1/job/{KITCHEN_V1['ID']}/deployments?namespace=lighthouse-rota")
        if deps and deps[0]["Status"] != "running": break
        time.sleep(2)
    api("POST", "/v1/jobs", {"Job": KITCHEN_V1}); log("blue-heron-kitchen-orders version 1 registered (menu change)")

kids, _ = api("GET", "/v1/jobs?namespace=granite-ledger&prefix=copperfield-annex-ledger-sync/dispatch")
if not kids:
    d, _ = api("POST", "/v1/job/copperfield-annex-ledger-sync/dispatch?namespace=granite-ledger",
               {"Meta": {"ledger_ref": "GL-2291", "requested_by": "Mina Okafor"}})
    log(f"dispatched {d['DispatchedJobID']}"); ids["dispatched"] = d["DispatchedJobID"]
else:
    ids["dispatched"] = kids[0]["ID"]

time.sleep(20)  # let allocations run, the batch tasks finish and the kitchen deployment go healthy
for jid, ns in list(ids["jobs"].items()) + [(ids["dispatched"], "granite-ledger")]:
    allocs, _ = api("GET", f"/v1/job/{jid}/allocations?namespace={ns}")
    s, _ = api("GET", f"/v1/job/{jid}?namespace={ns}")
    log(f"{ns}/{jid}: status {s['Status']}, {len(allocs)} allocations " + ",".join(sorted({a['ClientStatus'] for a in allocs})))
    ids.setdefault("allocations", {})[jid] = [a["ID"] for a in allocs]
evals, _ = api("GET", "/v1/evaluations?namespace=*")
ids["blocked_evals"] = [e["ID"] for e in evals if e["Status"] == "blocked"]
deps, _ = api("GET", "/v1/deployments?namespace=*")
ids["deployments"] = {d["ID"]: f"{d['JobID']} v{d['JobVersion']} {d['Status']}" for d in deps}
json.dump(ids, open(os.path.join(DIR, "seed-ids.json"), "w"), indent=1)
log("seed-ids.json written")
