#!/usr/bin/env python3
"""Seed the showcase Airbyte with invented content through the public REST API (/api/public/v1, idempotent).

Auth: the default application client id/secret that admin.py stored in ~/capture/airbyte/.admin (mode 600) are exchanged
for a short-lived bearer token at /api/public/v1/applications/token; the token stays in memory and is never printed.
Only connectors that need no external service: Sample Data (source-faker) sources and End-to-End Testing (/dev/null)
destinations. Seeds 2 workspaces (the default one renamed), 4 sources, 3 destinations, 3 connections, 3 tags, and runs one
sync job to completion so the jobs collection has a finished record. Writes seed-ids.json (ids only, no secrets)."""
import json, os, sys, time, urllib.error, urllib.request

BASE = os.environ.get("BASE_URL", "http://127.0.0.1:3302"); API = "/api/public/v1"
DIR = os.environ.get("CAPTURE_DIR", os.path.expanduser("~/capture/airbyte"))
FAKER = "dfd88b22-b603-4c3d-aad7-3701784586b1"      # Sample Data (airbyte/source-faker)
DEVNULL = "a7bcc9d8-13b3-4e49-b80d-d020b90045e3"    # End-to-End Testing (/dev/null) (airbyte/destination-dev-null)

MAIN_WS = "Lighthouse Rota Pipelines"; SECOND_WS = "Saltmarsh Depot Sandbox"
SOURCES = [  # (workspace, name, faker count, faker seed)
    (MAIN_WS, "Blue Heron Kitchen Orders", 250, 11),
    (MAIN_WS, "Granite Ledger Stone Census", 400, 29),
    (MAIN_WS, "Copperfield Annex Visitor Log", 120, 5),
    (SECOND_WS, "Saltmarsh Depot Tide Readings", 60, 3),
]
DESTINATIONS = [
    (MAIN_WS, "Copperfield Annex Null Sink"),
    (MAIN_WS, "Lighthouse Rota Quiet Drain"),
    (SECOND_WS, "Saltmarsh Depot Dev Null"),
]
CONNECTIONS = [  # (name, source, destination, schedule)
    ("Blue Heron Kitchen nightly orders feed", "Blue Heron Kitchen Orders", "Copperfield Annex Null Sink",
     {"scheduleType": "cron", "cronExpression": "0 30 2 * * ?"}),
    ("Granite Ledger census to Quiet Drain", "Granite Ledger Stone Census", "Lighthouse Rota Quiet Drain", {"scheduleType": "manual"}),
    ("Saltmarsh Depot tide readings relay", "Saltmarsh Depot Tide Readings", "Saltmarsh Depot Dev Null", {"scheduleType": "manual"}),
]
TAGS = [(MAIN_WS, "Quarry Audit", "4F7A5B"), (MAIN_WS, "Kitchen Night Shift", "C2733C"), (SECOND_WS, "Tide Table Crew", "2E6F9E")]
TAGGED = {"Blue Heron Kitchen nightly orders feed": "Kitchen Night Shift", "Granite Ledger census to Quiet Drain": "Quarry Audit"}
SYNC_CONNECTION = "Granite Ledger census to Quiet Drain"


def log(msg): print(f"[seed] {msg}", file=sys.stderr)


kv = dict(l.split("=", 1) for l in open(os.path.join(DIR, ".admin")).read().splitlines() if "=" in l)
_tok = {"v": None, "at": 0.0}


def raw(method, path, body=None, token=None):
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode() if body is not None else None, method=method)
    req.add_header("Accept", "application/json"); req.add_header("Content-Type", "application/json")
    if token: req.add_header("Authorization", "Bearer " + token)
    with urllib.request.urlopen(req, timeout=120) as r:
        data = r.read(); ct = r.headers.get("content-type") or ""
        return r.status, (json.loads(data) if data and "json" in ct else None)


def token():
    if not _tok["v"] or time.time() - _tok["at"] > 600:
        _, t = raw("POST", f"{API}/applications/token", {"client_id": kv["AIRBYTE_CLIENT_ID"], "client_secret": kv["AIRBYTE_CLIENT_SECRET"],
                                                         "grant-type": "client_credentials"})
        _tok["v"], _tok["at"] = t["access_token"], time.time()
    return _tok["v"]


def api(method, path, body=None):
    try: return raw(method, API + path, body, token())[1]
    except urllib.error.HTTPError as e:
        raise SystemExit(f"[seed] {method} {path} -> {e.code}: {e.read().decode(errors='replace')[:500]}")


def wait_ready():
    for _ in range(180):
        try:
            if raw("GET", "/api/v1/health")[0] == 200: return
        except Exception: pass
        time.sleep(2)
    raise SystemExit("[seed] Airbyte did not become ready")


def by_name(items, name): return next((x for x in items if x.get("name") == name), None)


wait_ready(); log("airbyte healthy")
# Finish the first-run setup screen (organization name, no anonymous usage data) so the web UI opens on its sign-in page.
cfg = raw("GET", "/api/v1/instance_configuration")[1]
if not cfg.get("initialSetupComplete"):
    raw("POST", "/api/v1/instance_configuration/setup", {"email": kv["AIRBYTE_ADMIN_EMAIL"], "organizationName": "Lighthouse Rota",
                                                         "anonymousDataCollection": False, "initialSetupComplete": True,
                                                         "displaySetupWizard": False}, token())
    log("instance setup completed")
org = api("GET", "/organizations")["data"][0]["organizationId"]
ws = api("GET", "/workspaces?limit=50")["data"]
main = by_name(ws, MAIN_WS) or by_name(ws, "Default Workspace")
if main["name"] != MAIN_WS:
    main = api("PATCH", f"/workspaces/{main['workspaceId']}", {"name": MAIN_WS}); log(f"renamed the default workspace to {MAIN_WS}")
second = by_name(ws, SECOND_WS)
if not second: second = api("POST", "/workspaces", {"name": SECOND_WS, "organizationId": org}); log(f"workspace {SECOND_WS} created")
WS = {MAIN_WS: main["workspaceId"], SECOND_WS: second["workspaceId"]}
ids = {"organization": org, "workspaces": WS, "sources": {}, "destinations": {}, "connections": {}, "tags": {}, "jobs": []}

# Remove scratch sources left behind by an interrupted capture so every capture starts from the same state.
for w in WS.values():
    for s in api("GET", f"/sources?workspaceIds={w}&limit=100")["data"]:
        if s["name"].startswith("Rea scratch"): api("DELETE", f"/sources/{s['sourceId']}"); log(f"removed leftover {s['name']}")
    for t in api("GET", f"/tags?workspaceIds={w}")["data"]:
        if t["name"].startswith("Rea scratch"): api("DELETE", f"/tags/{t['tagId']}"); log(f"removed leftover {t['name']}")

for w, name, count, seed in SOURCES:
    cur = by_name(api("GET", f"/sources?workspaceIds={WS[w]}&limit=100")["data"], name)
    if not cur:
        cur = api("POST", "/sources", {"name": name, "workspaceId": WS[w], "definitionId": FAKER,
                                      "configuration": {"sourceType": "faker", "count": count, "seed": seed, "records_per_slice": 100,
                                                        "always_updated": False, "parallelism": 2}})
        log(f"source {name} created")
    ids["sources"][name] = cur["sourceId"]

for w, name in DESTINATIONS:
    cur = by_name(api("GET", f"/destinations?workspaceIds={WS[w]}&limit=100")["data"], name)
    if not cur:
        cur = api("POST", "/destinations", {"name": name, "workspaceId": WS[w], "definitionId": DEVNULL,
                                           "configuration": {"destinationType": "dev-null", "test_destination": {"test_destination_type": "SILENT"}}})
        log(f"destination {name} created")
    ids["destinations"][name] = cur["destinationId"]

for w, name, color in TAGS:
    cur = by_name(api("GET", f"/tags?workspaceIds={WS[w]}")["data"], name)
    if not cur: cur = api("POST", "/tags", {"name": name, "color": color, "workspaceId": WS[w]}); log(f"tag {name} created")
    ids["tags"][name] = cur["tagId"]

for name, src, dst, sched in CONNECTIONS:
    allc = api("GET", "/connections?limit=100&" + "&".join(f"workspaceIds={w}" for w in WS.values()))["data"]
    cur = by_name(allc, name)
    if not cur:
        cur = api("POST", "/connections", {"name": name, "sourceId": ids["sources"][src], "destinationId": ids["destinations"][dst],
                                          "schedule": sched, "status": "active", "namespaceDefinition": "destination"})
        log(f"connection {name} created")
    ids["connections"][name] = cur["connectionId"]

for cname, tname in TAGGED.items():
    c = api("GET", f"/connections/{ids['connections'][cname]}")
    if not any(t.get("name") == tname for t in c.get("tags") or []):
        color = next(x[2] for x in TAGS if x[1] == tname)
        api("PATCH", f"/connections/{c['connectionId']}", {"tags": [{"tagId": ids["tags"][tname], "name": tname, "color": color, "workspaceId": WS[MAIN_WS]}]})
        log(f"tagged {cname} with {tname}")

# one finished sync job
cid = ids["connections"][SYNC_CONNECTION]
jobs = api("GET", f"/jobs?connectionId={cid}&limit=5")["data"]
done = [j for j in jobs if j.get("status") == "succeeded"]
if not done:
    live = [j for j in jobs if j.get("status") in ("pending", "running", "incomplete")]
    job = live[0] if live else api("POST", "/jobs", {"connectionId": cid, "jobType": "sync"})
    log(f"sync job {job['jobId']} started")
    for _ in range(90):
        job = api("GET", f"/jobs/{job['jobId']}")
        if job["status"] not in ("pending", "running", "incomplete"): break
        time.sleep(10)
    log(f"sync job {job['jobId']} ended {job['status']} rows={job.get('rowsSynced')}")
    done = [job]
ids["jobs"] = [j["jobId"] for j in done]
json.dump(ids, open(os.path.join(DIR, "seed-ids.json"), "w"), indent=1)
log("wrote seed-ids.json")
