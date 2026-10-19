#!/usr/bin/env python3
"""Seed the showcase Redpanda Console with invented streaming data (idempotent, stdlib only).

Redpanda Console's free edition has no login, so there is no admin account and no .admin file. Topics, their configs,
JSON messages and schema subjects go through the Console REST API (http://127.0.0.1:3305/api/); consumer groups are made
by consuming through the broker's HTTP Proxy on loopback (http://127.0.0.1:18082) and committing chosen offsets, so some
groups show lag. Writes seed-ids.json (names only). Every name, person and place is invented."""
import base64, json, os, sys, time, urllib.error, urllib.request

CONSOLE = os.environ.get("BASE_URL", "http://127.0.0.1:3305")
PROXY = os.environ.get("PROXY_URL", "http://127.0.0.1:18082")
DIR = os.environ.get("CAPTURE_DIR", os.path.expanduser("~/capture/redpanda-console"))
KBIN = "application/vnd.kafka.binary.v2+json"; KV2 = "application/vnd.kafka.v2+json"


def log(msg): print(f"[seed] {msg}", file=sys.stderr)


def call(method, url, body=None, ctype="application/json", accept="application/json", ok=()):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Accept", accept)
    if data is not None or method == "DELETE": req.add_header("Content-Type", ctype)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read()
            try: return (json.loads(raw) if raw else {}), r.status
            except ValueError: return {"text": raw.decode(errors="replace")}, r.status
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:400]
        if e.code in ok: return {"error": detail}, e.code
        raise SystemExit(f"[seed] {method} {url} -> {e.code}: {detail}")


def api(method, path, body=None, ok=()): return call(method, CONSOLE + path, body, ok=ok)


def wait_ready():
    for _ in range(120):
        try:
            with urllib.request.urlopen(CONSOLE + "/api/brokers", timeout=5) as r:
                if r.status == 200 and json.loads(r.read()): return
        except Exception: pass
        time.sleep(2)
    raise SystemExit("[seed] Console did not become ready")


def b64(obj):
    raw = obj if isinstance(obj, bytes) else (obj.encode() if isinstance(obj, str) else json.dumps(obj, separators=(",", ":")).encode())
    return base64.b64encode(raw).decode()


TOPICS = [
    {"name": "granite-ledger.stone-counts", "partitions": 3, "configs": {"cleanup.policy": "delete", "retention.ms": "604800000"}},
    {"name": "blue-heron-kitchen.tide-orders", "partitions": 2, "configs": {"cleanup.policy": "delete", "retention.ms": "259200000"}},
    {"name": "lighthouse-rota.shift-handover", "partitions": 1, "configs": {"cleanup.policy": "compact"}},
    {"name": "copperfield-annex.lamp-oil-deliveries", "partitions": 2, "configs": {"cleanup.policy": "delete", "max.message.bytes": "262144"}},
    {"name": "saltmarsh-depot.crate-manifests", "partitions": 1, "configs": {"cleanup.policy": "compact,delete", "retention.ms": "1209600000"}},
]

MESSAGES = {
    "granite-ledger.stone-counts": [
        ("north-quarry", {"quarry": "North Quarry", "blocks": 412, "auditor": "Rui Castellanos", "reference": "GL-2291"}),
        ("tidal-yard", {"quarry": "Tidal Yard", "blocks": 97, "auditor": "Rui Castellanos", "reference": "GL-2292"}),
        ("north-quarry", {"quarry": "North Quarry", "blocks": 405, "auditor": "Mina Okafor", "reference": "GL-2301"}),
        ("west-cut", {"quarry": "West Cut", "blocks": 58, "auditor": "Mina Okafor", "reference": "GL-2302"}),
        ("tidal-yard", {"quarry": "Tidal Yard", "blocks": 101, "auditor": "Tomas Vey", "reference": "GL-2310"}),
        ("west-cut", {"quarry": "West Cut", "blocks": 61, "auditor": "Tomas Vey", "reference": "GL-2311"}),
    ],
    "blue-heron-kitchen.tide-orders": [
        ("order-1104", {"dish": "Kelp and barley broth", "covers": 36, "head_cook": "Marisol Okonkwo-Reyes", "sitting": "high tide"}),
        ("order-1105", {"dish": "Smoked mackerel on rye", "covers": 22, "head_cook": "Marisol Okonkwo-Reyes", "sitting": "low tide"}),
        ("order-1106", {"dish": "Samphire omelette", "covers": 14, "head_cook": "Ada Finch", "sitting": "night shift"}),
        ("order-1107", {"dish": "Lamp-oil lemon cake", "covers": 30, "head_cook": "Ada Finch", "sitting": "high tide"}),
    ],
    "lighthouse-rota.shift-handover": [
        ("shift-three", {"from_keeper": "Ada Finch", "to_keeper": "Tomas Vey", "lamp_hours": 8, "note": "Fog horn checked twice"}),
        ("shift-one", {"from_keeper": "Tomas Vey", "to_keeper": "Mina Okafor", "lamp_hours": 8, "note": "Lens polished at dawn"}),
        ("shift-two", {"from_keeper": "Mina Okafor", "to_keeper": "Ada Finch", "lamp_hours": 8, "note": "Tide tables updated for January"}),
    ],
    "copperfield-annex.lamp-oil-deliveries": [
        ("delivery-77", {"litres": 180, "carrier": "Saltmarsh Depot wagon", "signed_by": "Rui Castellanos"}),
        ("delivery-78", {"litres": 120, "carrier": "Saltmarsh Depot wagon", "signed_by": "Ada Finch"}),
        ("delivery-79", {"litres": 240, "carrier": "Copperfield barge", "signed_by": "Mina Okafor"}),
        ("delivery-80", {"litres": 90, "carrier": "Copperfield barge", "signed_by": "Tomas Vey"}),
    ],
    "saltmarsh-depot.crate-manifests": [
        ("crate-sd-401", {"contents": "rope coils", "crates": 12, "bay": "Bay Four", "checked_by": "Mina Okafor"}),
        ("crate-sd-402", {"contents": "lamp wicks", "crates": 40, "bay": "Bay Two", "checked_by": "Tomas Vey"}),
        ("crate-sd-403", {"contents": "salted cod", "crates": 6, "bay": "Bay Four", "checked_by": "Rui Castellanos"}),
        ("crate-sd-404", {"contents": "granite chisels", "crates": 3, "bay": "Bay One", "checked_by": "Ada Finch"}),
        ("crate-sd-405", {"contents": "lens cloths", "crates": 25, "bay": "Bay Two", "checked_by": "Mina Okafor"}),
    ],
}

# group -> {topic: fraction of each partition's messages committed}; below 1.0 leaves lag on purpose.
GROUPS = {
    "granite-ledger-auditors": {"granite-ledger.stone-counts": 1.0},
    "blue-heron-kitchen-pass": {"blue-heron-kitchen.tide-orders": 0.5},
    "lighthouse-rota-keepers": {"lighthouse-rota.shift-handover": 1.0, "copperfield-annex.lamp-oil-deliveries": 0.5},
    "saltmarsh-depot-tally": {"saltmarsh-depot.crate-manifests": 0.6},
}

KEEPER = {"type": "record", "name": "Keeper", "namespace": "com.example.rota", "doc": "A keeper on the Lighthouse Rota.",
          "fields": [{"name": "name", "type": "string"}, {"name": "station", "type": "string", "default": "Granite Point"}]}
SHIFT = {"type": "record", "name": "ShiftHandover", "namespace": "com.example.rota", "doc": "Handover between two keepers.",
         "fields": [{"name": "from_keeper", "type": "com.example.rota.Keeper"}, {"name": "to_keeper", "type": "com.example.rota.Keeper"},
                    {"name": "lamp_hours", "type": "int"}, {"name": "note", "type": "string"}]}
STONE_V1 = {"type": "record", "name": "StoneCount", "namespace": "com.example.granite", "doc": "Quarterly stone count for the Granite Ledger.",
            "fields": [{"name": "quarry", "type": "string"}, {"name": "blocks", "type": "int"}, {"name": "auditor", "type": "string"}]}
STONE_V2 = {**STONE_V1, "fields": STONE_V1["fields"] + [{"name": "reference", "type": "string", "default": "GL-0000"}]}
TIDE_ORDER = {"$schema": "http://json-schema.org/draft-07/schema#", "title": "TideOrder", "description": "An order at the Blue Heron Kitchen.",
              "type": "object", "properties": {"dish": {"type": "string"}, "covers": {"type": "integer"}, "head_cook": {"type": "string"},
                                               "sitting": {"type": "string", "enum": ["high tide", "low tide", "night shift"]}},
              "required": ["dish", "covers"]}
CRATE_PROTO = ('syntax = "proto3";\npackage example.saltmarsh;\n\n// A crate manifest line at the Saltmarsh Depot.\n'
               'message CrateManifest {\n  string contents = 1;\n  int32 crates = 2;\n  string bay = 3;\n  string checked_by = 4;\n}\n')
SCHEMAS = [  # (subject, type, schema text, references, compatibility override)
    ("lighthouse-rota.keeper", "AVRO", json.dumps(KEEPER), [], None),
    ("lighthouse-rota.shift-handover-value", "AVRO", json.dumps(SHIFT),
     [{"name": "com.example.rota.Keeper", "subject": "lighthouse-rota.keeper", "version": 1}], "FULL"),
    ("granite-ledger.stone-counts-value", "AVRO", json.dumps(STONE_V1), [], None),
    ("granite-ledger.stone-counts-value", "AVRO", json.dumps(STONE_V2), [], None),
    ("blue-heron-kitchen.tide-orders-value", "JSON", json.dumps(TIDE_ORDER), [], "FORWARD"),
    ("saltmarsh-depot.crate-manifests-value", "PROTOBUF", CRATE_PROTO, [], None),
]


def main():
    wait_ready(); log(f"console ready at {CONSOLE}")
    ids = {"topics": {}, "groups": {}, "subjects": {}}
    have = {t["topicName"] for t in api("GET", "/api/topics")[0].get("topics", [])}
    for t in api("GET", "/api/topics")[0].get("topics", []):   # scratch topics from an interrupted capture
        if t["topicName"].startswith("rea-scratch"): api("DELETE", f"/api/topics/{t['topicName']}"); log(f"removed leftover {t['topicName']}")
    for t in TOPICS:
        if t["name"] not in have:
            api("POST", "/api/topics", {"topicName": t["name"], "partitionCount": t["partitions"], "replicationFactor": 1,
                                        "configs": [{"name": k, "value": v} for k, v in t["configs"].items()]})
            log(f"topic {t['name']} created")
        parts, _ = api("GET", f"/api/topics/{t['name']}/partitions")
        high = sum(p.get("waterMarkHigh", 0) for p in parts.get("partitions", []))
        if high == 0:
            recs = [{"key": b64(k), "value": b64(v), "headers": [{"key": "source", "value": b64("rea-seed")}], "partitionId": -1}
                    for k, v in MESSAGES[t["name"]]]
            api("POST", "/api/topics-records", {"topicNames": [t["name"]], "compressionType": 0, "useTransactions": False, "records": recs})
            log(f"produced {len(recs)} messages to {t['name']}")
        ids["topics"][t["name"]] = t["partitions"]
    time.sleep(1)

    groups = {g["groupId"] for g in api("GET", "/api/consumer-groups")[0].get("consumerGroups", []) if g.get("topicOffsets")}
    for gid, topics in GROUPS.items():
        ids["groups"][gid] = sorted(topics)
        if gid in groups: continue
        inst = f"{gid}-seed"
        call("DELETE", f"{PROXY}/consumers/{gid}/instances/{inst}", ctype=KV2, accept=KV2, ok=(404,))   # left by an interrupted run
        made, _ = call("POST", f"{PROXY}/consumers/{gid}", {"name": inst, "format": "binary", "auto.offset.reset": "earliest",
                                                           "auto.commit.enable": "false"}, ctype=KV2, accept=KV2)
        base = made["base_uri"]
        call("POST", f"{base}/subscription", {"topics": sorted(topics)}, ctype=KV2, accept=KV2)
        got = []
        for _ in range(15):
            batch, _ = call("GET", f"{base}/records?timeout=2000&max_bytes=1000000", accept=KBIN)
            got += batch if isinstance(batch, list) else []
            if len(got) >= sum(len(MESSAGES[t]) for t in topics): break
        offs = []
        for topic, frac in topics.items():
            parts, _ = api("GET", f"/api/topics/{topic}/partitions")
            for p in parts["partitions"]:
                hi = p.get("waterMarkHigh", 0)
                if hi: offs.append({"topic": topic, "partition": p["id"], "offset": max(1, int(hi * frac)) if frac < 1 else hi})
        call("POST", f"{base}/offsets", {"partitions": offs}, ctype=KV2, accept=KV2)
        call("DELETE", base, ctype=KV2, accept=KV2, ok=(404,))
        log(f"group {gid}: read {len(got)} messages, committed {len(offs)} partition offsets")

    subjects = {s.get("name") for s in (api("GET", "/api/schema-registry/subjects")[0] or [])} if True else set()
    done = {}
    for subject, stype, text, refs, compat in SCHEMAS:
        n = done.get(subject, 0) + 1; done[subject] = n
        if subject in subjects:
            det, st = api("GET", f"/api/schema-registry/subjects/{subject}/versions/latest", ok=(404,))
            if st == 200 and len(det.get("versions", [])) >= n: continue
        res, _ = api("POST", f"/api/schema-registry/subjects/{subject}/versions",
                     {"schema": text, "schemaType": stype, "references": refs, "params": {"normalize": False}})
        log(f"schema {subject} v{n} registered (id {res.get('id')})")
        if compat: api("PUT", f"/api/schema-registry/config/{subject}", {"compatibility": compat})
    for subject in done:
        det, _ = api("GET", f"/api/schema-registry/subjects/{subject}/versions/latest")
        ids["subjects"][subject] = [v["version"] for v in det.get("versions", [])]
    with open(os.path.join(DIR, "seed-ids.json"), "w") as f: json.dump(ids, f, indent=1)
    log("wrote seed-ids.json")


if __name__ == "__main__":
    main()
