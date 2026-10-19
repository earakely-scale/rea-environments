#!/usr/bin/env python3
"""Build, evaluate and package one REA replay environment on a batch VM.

Usage (on the VM, as ubuntu):  python3 ~/showcase/envbuild.py STEP APP [options]
Steps, in order (`all` runs manifest..card):
  manifest   rea capture + environment-manifest views (with and without the opt-in rules), credential grep, summary entry
  bundle     rea environment-export with the prerelease tarball, the replay-qa agent, generated retrieval tasks
  smoke      agent-env run <bundle> --task smoke
  eval       purge this bundle's previous runs for each model, then run the retrieval eval once per model
  card       episode stats, the dataset card note, a dry `agent-env hf publish --out`, forbidden-token and placeholder scans
  publish    real publish to the Hub (orchestrator only; needs HF_TOKEN in the environment)
  status     print the step results recorded so far
Inputs live in ~/capture/APP/: app.json, capture.mjs, APP.scoped.har, summary.json, README-notes.md, plus compose.yml and
seed.* for a self-hosted app (app.json "kind": "self-hosted", the default) but not for a public API ("kind": "public-api").
Every step writes ~/showcase/status/APP.json and exits non-zero with a reason on failure."""
import argparse, hashlib, json, os, re, shutil, sqlite3, subprocess, sys, tempfile, time
from pathlib import Path

sys.path.insert(0, str(Path.home() / "showcase" / "work" / "tools"))
from scenario_records import scenario_records  # noqa: E402  (shared with gen_tasks.py)

HOME = Path.home(); CAP = HOME / "capture"; SC = HOME / "showcase"; WORK = SC / "work"
AE = str(SC / ".venv/bin/agent-env"); PY = str(SC / ".venv/bin/python")
TARBALL = SC / "rea-agents.tgz"
MODELS = ["openai/gpt-oss-120b:groq", "zai-org/GLM-5.3-Flash:zai-org"]
RULES = ["after-uid-literal", "opaque-token", "sibling-variance"]
COLLECTION = "earakely-scale/rea-environments-on-agentenv-6ad48fc54339527205162f82"
DB = HOME / ".local/state/agent-env/document_store/local.db"
SECRET_SHAPES = re.compile(r"hf_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9_-]{16,}|ghp_[A-Za-z0-9]{20,}|xox[bp]-[A-Za-z0-9-]{10,}|Bearer [A-Za-z0-9._~+/-]{20,}")
FORBIDDEN = re.compile(os.environ.get("ENVBUILD_FORBID_REGEX") or r"(?!)", re.I)  # words that must not reach a dataset
CRED_KEY = re.compile(r"(^|[_-])(access_?token|refresh_?token|id_?token|auth_?token|token|api_?key|apikey|secret|client_?secret|password|passwd|session_?token|jwt|private_?key)$", re.I)
JWT = re.compile(r"eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{4,}")
REQUIRED_META = ["app", "title", "repo", "license", "authors", "hf_license", "version", "domain"]
REQUIRED_BY_KIND = {"self-hosted": ["image", "port"], "public-api": ["origin"]}


def credential_paths(entries):
    """Key paths in request or response JSON bodies holding credential-like values (not masks, scrubbed or REA redaction markers)."""
    hits = set()
    def walk(o, path):
        if isinstance(o, dict):
            for k, v in o.items():
                if CRED_KEY.search(str(k)) and isinstance(v, str) and len(v) >= 6 and not set(v) <= {"*"} and not v.startswith(("<", "[REDACTED")):
                    hits.add(f"{path}.{k}")
                walk(v, f"{path}.{k}")
        elif isinstance(o, list):
            for x in o[:200]: walk(x, path + "[]")
        elif isinstance(o, str) and JWT.search(o): hits.add(path + " (jwt-shaped)")
    for e in entries:
        where = e["request"]["method"] + " " + re.sub(r"^https?://[^/]+", "", e["request"].get("url") or "<redacted>").split("?")[0]
        for side, text in (("req", (e["request"].get("postData") or {}).get("text")), ("res", ((e.get("response") or {}).get("content") or {}).get("text"))):
            if not text: continue
            try: walk(json.loads(text), f"{where} {side}")
            except ValueError: pass
    return sorted(hits)


def fail(app, step, reason, **extra):
    record(app, step, {"ok": False, "reason": reason, **extra})
    print(json.dumps({"step": step, "ok": False, "reason": reason, **extra}, indent=1)); sys.exit(1)


def record(app, step, result):
    (SC / "status").mkdir(parents=True, exist_ok=True); p = SC / "status" / f"{app}.json"
    st = json.loads(p.read_text()) if p.exists() else {}
    st[step] = {**result, "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}; p.write_text(json.dumps(st, indent=1))


def run(cmd, log=None, timeout=3600, cwd=SC):
    """Run a command with output streamed to its log as it happens (tail -f works), then return (rc, output)."""
    if log is None:
        fd, tmp = tempfile.mkstemp(prefix="envbuild-", suffix=".log"); os.close(fd); path = Path(tmp)
    else:
        path = Path(log); path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as out:
        try:
            rc = subprocess.run(cmd, cwd=cwd, stdout=out, stderr=subprocess.STDOUT, text=True, timeout=timeout).returncode
        except subprocess.TimeoutExpired:
            rc = 124
    text = path.read_text(errors="ignore")
    if log is None: path.unlink(missing_ok=True)
    return rc, text


def meta_of(app):
    p = CAP / app / "app.json"
    if not p.exists(): fail(app, "meta", f"missing {p}")
    m = json.loads(p.read_text()); m.setdefault("kind", "self-hosted")
    if m["kind"] not in REQUIRED_BY_KIND: fail(app, "meta", f"app.json kind must be one of {sorted(REQUIRED_BY_KIND)}")
    missing = [k for k in REQUIRED_META + REQUIRED_BY_KIND[m["kind"]] if k not in m]
    if missing: fail(app, "meta", f"app.json lacks {missing}")
    if m["app"] != app: fail(app, "meta", "app.json app does not match the step argument")
    return m


def load_json_output(text):
    i = text.find("{")
    return json.loads(text[i:]) if i >= 0 else None


def scenario_capture(app, d):
    """The worker's capture_browser_scenario Evidence and its transactions as HAR-like entries with decoded bodies."""
    capfile = d / f"{app}.capture.json"
    if not capfile.exists(): fail(app, "manifest", f"missing {capfile}; run rea capture-browser-scenario first")
    raw_ev = capfile.read_text(errors="ignore"); ev = json.loads(raw_ev)
    if ev.get("operation") != "capture_browser_scenario": fail(app, "manifest", "the capture file is not capture_browser_scenario Evidence")
    entries = [r["reported"] for r in scenario_records(ev) if "request" in r["reported"]]
    return ev, raw_ev, entries


def step_manifest(app):
    m = meta_of(app); d = CAP / app; har = d / f"{app}.scoped.har"
    scenario = m.get("capture") == "scenario"
    if scenario:
        cap, raw_ev, scenario_entries = scenario_capture(app, d)
        raw = json.dumps(scenario_entries)   # decoded bodies, so the scans below see real text
    else:
        if not har.exists(): fail(app, "manifest", f"missing {har}; run scope_har.py first")
        raw = har.read_text(errors="ignore")
    secrets = []
    adm = d / ".admin"
    if adm.exists():
        for line in adm.read_text().splitlines():
            if "=" in line:
                k, v = line.split("=", 1); v = v.strip()
                if re.search(r"pass|secret|key|token", k, re.I) and len(v) >= 6 and v in raw: secrets.append(k)
    shapes = sorted(set(x[:6] for x in SECRET_SHAPES.findall(raw)))
    if secrets or shapes: fail(app, "manifest", "credential material in the scoped HAR", admin_values=secrets, token_shapes=shapes)
    if FORBIDDEN.search(raw): fail(app, "manifest", "forbidden word in the scoped HAR (rename the seed data)")
    entries = scenario_entries if scenario else json.loads(raw)["log"]["entries"]; methods = {}
    creds = credential_paths(entries)
    if creds: fail(app, "manifest", "credential-like values in request or response bodies; drop or scrub those exchanges", paths=creds[:20])
    for e in entries: methods[e["request"]["method"]] = methods.get(e["request"]["method"], 0) + 1
    low, high = (20, 1024) if scenario else (40, 160)
    if not (low <= len(entries) <= high): fail(app, "manifest", f"capture has {len(entries)} records; aim for {low}-{high}", methods=methods)
    if scenario:
        raw = raw_ev   # size and digest below describe the capture file itself
    else:
        rc, out = run(["rea", "inspect-web-network-capture", str(har), "har", "--format", "json"], timeout=600)
        cap = load_json_output(out)
        if rc != 0 or not cap or "evidence_id" not in cap: fail(app, "manifest", "inspect-web-network-capture failed", tail=out[-1500:])
        (d / f"{app}.capture.json").write_text(json.dumps(cap))
    views = {}
    for label, rules in (("rules", RULES), ("norules", [])):
        req = d / f"req.{label}.json"
        view = {"kind": "environment-manifest", **({"template_rules": rules} if rules else {})}
        req.write_text(json.dumps({"source": {"kind": "inline", "evidence": cap}, "view": view}))
        rc, out = run(["rea", "inspect-analysis-view", str(req), "--format", "json"], timeout=600)
        req.unlink(missing_ok=True); man = load_json_output(out)
        if rc != 0 or not man or "normalized_result" not in man:
            fail(app, "manifest", f"environment-manifest view ({label}) failed; if resource_constraint, scope fewer or smaller records", tail=out[-1500:])
        views[label] = man
    (d / f"{app}.manifest.json").write_text(json.dumps(views["rules"], indent=1))
    (d / f"{app}.manifest.norules.json").write_text(json.dumps(views["norules"], indent=1))
    nr = views["rules"]["normalized_result"]; tools = nr["tools"]
    by_method, by_rule, excl = {}, {}, {}
    for t in tools:
        by_method[t["method"]] = by_method.get(t["method"], 0) + 1
        for p in t["params"]: by_rule[p["rule"]] = by_rule.get(p["rule"], 0) + 1
    for e in nr["excluded"]: excl[e["reason"]] = excl.get(e["reason"], 0) + 1
    entry = {
        "app_version": m["version"], "origin": nr["origin"], "manifest_name": nr["name"], "scoped_records": len(entries),
        "methods": methods, "scoped_har_bytes": len(raw.encode()), "scoped_har_sha256": hashlib.sha256(raw.encode()).hexdigest(),
        "capture_evidence_id": cap["evidence_id"], "manifest_evidence_id": views["rules"]["evidence_id"],
        "manifest_norules_evidence_id": views["norules"]["evidence_id"], "tools": len(tools), "tools_by_method": by_method,
        "tools_norules": len(views["norules"]["normalized_result"]["tools"]), "templated_groups": nr["templated_groups"],
        "params_by_rule": by_rule, "params_total": sum(by_rule.values()),
        "query_names": sum(len(t["query_parameter_names"]) for t in tools),
        "tools_with_body_shape": sum(1 for t in tools if t.get("body_shape")), "excluded": excl,
        "unknowns": [u["kind"] for u in nr["unknowns"]], "confidence": views["rules"]["confidence"],
        "authority": views["rules"]["authority"], "view_digest": nr["view_digest"], "parent_digest": nr["parent_digest"],
    }
    if entry["tools"] < 8: fail(app, "manifest", f"only {entry['tools']} tools; capture more distinct API reads", entry=entry)
    if m["kind"] == "self-hosted" and not any(k != "GET" for k in by_method): fail(app, "manifest", "no write tools; the capture needs at least one POST/PUT/PATCH/DELETE", entry=entry)
    summary = d / "summary.json"
    if not summary.exists(): fail(app, "manifest", "write ~/capture/APP/summary.json first (seeded_objects at least)")
    if "seeded_objects" not in json.loads(summary.read_text()): fail(app, "manifest", "summary.json lacks seeded_objects")
    wa = WORK / "apps"; (wa / app).mkdir(parents=True, exist_ok=True)
    for f in (f"{app}.capture.json", f"{app}.manifest.json", f"{app}.manifest.norules.json", "summary.json"):
        shutil.copy2(d / f, wa / app / f)
    allp = wa / "SUMMARY.json"; s = json.loads(allp.read_text()) if allp.exists() else {}
    s[app] = entry; allp.write_text(json.dumps(s, indent=1))
    record(app, "manifest", {"ok": True, **{k: entry[k] for k in ("tools", "tools_norules", "tools_by_method", "params_by_rule", "scoped_records", "excluded")}})
    print(json.dumps({"step": "manifest", "ok": True, "entry": entry}, indent=1))


def step_bundle(app):
    m = meta_of(app); d = CAP / app; b = SC / "bundles" / app
    if not (d / f"{app}.manifest.json").exists(): fail(app, "bundle", "run the manifest step first")
    shutil.rmtree(b, ignore_errors=True)
    rc, out = run(["rea", "environment-export", str(d / f"{app}.manifest.json"), "--evidence", str(d / f"{app}.capture.json"), str(b),
                   "--package-tarball", str(TARBALL), "--name", app, "--format", "json"], timeout=600)
    res = load_json_output(out)
    if rc != 0 or not res or not (b / "tasks" / "smoke.json").exists(): fail(app, "bundle", "environment-export failed", tail=out[-1500:])
    shutil.copytree(WORK / "agent" / "replay-qa", b / "agents" / "replay-qa")
    gen = [PY, str(WORK / "tools" / "gen_tasks.py"), "--manifest", str(d / f"{app}.manifest.json"), "--capture", str(d / f"{app}.capture.json"),
           "--bundle", str(b), "--env", app, "--agent", "replay-qa", "--app", m["title"], "--max", "12",
           "--max-occurrences", str(m.get("max_occurrences", 12))] + (["--seed-dir", str(d)] if m["kind"] == "self-hosted" else [])
    if m.get("exclude_tools"): gen += ["--exclude-tools", m["exclude_tools"]]
    rc, out = run(gen, timeout=300); g = load_json_output(out)
    if rc != 0 or not g: fail(app, "bundle", "gen_tasks failed", tail=out[-1500:])
    if g["tasks"] < 6: fail(app, "bundle", f"only {g['tasks']} retrieval tasks from {g['candidates']} candidates; capture more GET reads of seeded objects")
    purged = purge(app)   # new tasks: every earlier run of this bundle, smoke included, is stale
    ap = WORK / "tools" / "apps.json"; apps = json.loads(ap.read_text()) if ap.exists() else {}
    apps[app] = {k: m[k] for k in ("title", "license", "authors", "repo", "hf_license")} | ({"episode_notes": m["episode_notes"]} if m.get("episode_notes") else {})
    ap.write_text(json.dumps(apps, indent=2))
    record(app, "bundle", {"ok": True, "tasks": g["tasks"], "candidates": g["candidates"], "rejected": g.get("rejected"), "purged_runs": purged, "files": len(res.get("files", []))})
    print(json.dumps({"step": "bundle", "ok": True, "tasks": g["tasks"], "candidates": g["candidates"], "names": g["names"]}, indent=1))


def step_smoke(app):
    b = SC / "bundles" / app; (SC / "runs").mkdir(exist_ok=True); log = SC / "runs" / f"{app}-smoke.log"
    rc, out = run([AE, "run", str(b), "--task", "smoke"], log=log, timeout=2400)
    ok = rc == 0 and re.search(r"tasks/smoke\.json v\d+: passed", out) is not None
    tail = "\n".join(out.strip().splitlines()[-8:])
    if not ok: fail(app, "smoke", "smoke task did not pass", log=str(log), tail=tail)
    record(app, "smoke", {"ok": True, "tail": tail}); print(json.dumps({"step": "smoke", "ok": True, "tail": tail}, indent=1))


def bundle_prefixes(app):
    b = (SC / "bundles" / app).resolve()
    return (f"@local/{b}/", "@local/~/" + os.path.relpath(b, HOME) + "/")


def purge(app, model=None):
    if not DB.exists(): return 0
    con = sqlite3.connect(DB); pre = bundle_prefixes(app); ids = []
    for rowid, doc in con.execute("select rowid, doc from docs_task_instances"):
        d = json.loads(doc)
        if not d.get("task_id", "").startswith(pre): continue
        if model and (d.get("context") or {}).get("agent_model") != model: continue
        if "/smoke" in d.get("task_id", "") and model: continue
        ids.append(rowid)
    con.executemany("delete from docs_task_instances where rowid=?", [(i,) for i in ids]); con.commit(); return len(ids)


def step_eval(app, models):
    b = SC / "bundles" / app; results = {}
    for model in models:
        purged = purge(app, model); tag = model.replace("/", "_").replace(":", "_"); log = SC / "runs" / f"{app}-{tag}.log"
        rc, out = run([AE, "run", str(b), "--eval", f"{app}-retrieval", "--model", model], log=log, timeout=3600)
        m = re.search(r"(\d+) of (\d+) passed", out); provider = sorted(set(re.findall(r"Error code: (4\d\d)", out)))
        missed = sorted(set(re.findall(r"tasks/(qa-[^ :]+)\.json v\d+: (?:failed|scored below 1)", out)))
        why = {}
        for t in missed:
            line = next((l for l in out.splitlines() if f"tasks/{t}.json v" in l and ("failed" in l or "scored below 1" in l)), "")
            code = re.search(r"Error code: (\d{3})", line)
            if code and code.group(1) == "400" and "tool call" in line.lower():
                why[t] = "the model provider rejected a malformed tool call the model generated (HTTP 400), so the episode ended without an answer"
            elif code:
                why[t] = f"the model provider returned HTTP {code.group(1)}, so the episode ended without an answer"
            elif "failed at step" in line:
                why[t] = "the episode failed before the model answered"
            else:
                why[t] = "the model's answer did not contain the expected value"
        results[model] = {"passed": int(m.group(1)) if m else 0, "total": int(m.group(2)) if m else None, "provider_errors": provider,
                          "missed": missed, "why": why, "purged_before": purged, "log": str(log)}
    record(app, "eval", {"ok": all(r["total"] for r in results.values()), "models": results})
    print(json.dumps({"step": "eval", "models": results}, indent=1))
    if not all(r["total"] for r in results.values()): sys.exit(1)


def scan_text(text):
    hits = []
    if FORBIDDEN.search(text): hits.append("forbidden word")
    if SECRET_SHAPES.search(text): hits.append("token-shaped string")
    if re.search(r"\{\{[A-Z_]+\}\}", text): hits.append("unfilled placeholder")
    return hits


def step_card(app):
    m = meta_of(app)
    for sub in ("cards", "episodes", "datasets"): (SC / sub).mkdir(exist_ok=True)
    shutil.copy2(CAP / app / "summary.json", WORK / "apps" / app / "summary.json")
    st = json.loads((SC / "status" / f"{app}.json").read_text())
    reasons = {}
    for model, r in (st.get("eval", {}).get("models") or {}).items():
        for t, w in (r.get("why") or {}).items(): reasons.setdefault(w, []).append(f"`{model.split('/')[-1]}` on `{t}`")
    notes = " ".join(f"Miss{'es' if len(v) > 1 else ''} by {', '.join(v)}: {w}." for w, v in reasons.items())
    ap = WORK / "tools" / "apps.json"; apps = json.loads(ap.read_text()) if ap.exists() else {}
    apps[app] = {k: m[k] for k in ("title", "license", "authors", "repo", "hf_license")} | ({"episode_notes": notes} if notes else {})
    ap.write_text(json.dumps(apps, indent=2))
    rc, out = run([PY, str(WORK / "tools" / "episode_stats.py"), "--db", str(DB), "--bundle-path", str(SC / "bundles" / app),
                   "--out", str(SC / "episodes" / f"{app}.json")])
    if rc != 0: fail(app, "card", "episode_stats failed", tail=out[-800:])
    ep = json.loads((SC / "episodes" / f"{app}.json").read_text())
    if len(ep.get("models", {})) < 2: fail(app, "card", f"episodes recorded for {list(ep.get('models', {}))}; run the eval for both models")
    rc, out = run([PY, str(WORK / "tools" / "make_card.py"), "--app", app, "--title", m["title"], "--license", m["license"], "--authors", m["authors"],
                   "--repo", m["repo"], "--bundle", str(SC / "bundles" / app), "--summary", str(WORK / "apps" / "SUMMARY.json"),
                   "--episodes", str(SC / "episodes" / f"{app}.json"), "--apps", str(WORK / "tools" / "apps.json"), "--export-pr", "4999", "--scenario-pr", "5182",
                   "--out", str(SC / "cards" / f"{app}.md"), "--template", str(WORK / "cards" / "TEMPLATE.md")])
    if rc != 0: fail(app, "card", "make_card failed", tail=out[-1200:])
    out_dir = SC / "datasets" / app; shutil.rmtree(out_dir, ignore_errors=True)
    rc, out = run([AE, "hf", "publish", str(SC / "bundles" / app), "--name", app, "--out", str(out_dir), "--runs", "all", "--reward", "retrieval",
                   "--license", m["hf_license"], "--card-note", str(SC / "cards" / f"{app}.md")], timeout=900)
    if rc != 0 or not (out_dir / "README.md").exists(): fail(app, "card", "dry publish failed", tail=out[-1500:])
    problems = {}
    for f in [SC / "cards" / f"{app}.md", out_dir / "README.md"] + sorted((out_dir / "raw").glob("*.jsonl")):
        hits = scan_text(f.read_text(errors="ignore"))
        if hits: problems[str(f.relative_to(SC))] = hits
    size = sum(p.stat().st_size for p in out_dir.rglob("*") if p.is_file())
    if problems: fail(app, "card", "dataset scan found problems", problems=problems)
    boards = {k: f"{v['passed']}/{v['tasks']}" for k, v in ep["models"].items()}
    record(app, "card", {"ok": True, "episodes": ep["count"], "boards": boards, "dataset_bytes": size, "dry_publish": out.strip().splitlines()[-1][:200]})
    print(json.dumps({"step": "card", "ok": True, "episodes": ep["count"], "boards": boards, "dataset_bytes": size}, indent=1))


def step_publish(app):
    m = meta_of(app)
    if not os.environ.get("HF_TOKEN"): fail(app, "publish", "HF_TOKEN is not set")
    rc, out = run([AE, "hf", "publish", str(SC / "bundles" / app), "--name", app, "--repo", f"earakely-scale/{m['repo']}", "--runs", "all",
                   "--reward", "retrieval", "--license", m["hf_license"], "--card-note", str(SC / "cards" / f"{app}.md"), "--tag", "v0.1.0",
                   "--collection", COLLECTION], timeout=1800)
    url = re.search(r"https://huggingface\.co/datasets/\S+", out)
    if rc != 0: fail(app, "publish", "publish failed", tail=out[-1500:])
    record(app, "publish", {"ok": True, "url": url.group(0) if url else None}); print(json.dumps({"step": "publish", "ok": True, "url": url.group(0) if url else None}))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("step", choices=["manifest", "bundle", "smoke", "eval", "card", "all", "rebuild", "publish", "status", "purge"]); ap.add_argument("app")
    ap.add_argument("--models", default=",".join(MODELS)); ap.add_argument("--model", default=None)
    a = ap.parse_args(); models = [x for x in a.models.split(",") if x]
    if a.step == "status":
        p = SC / "status" / f"{a.app}.json"; print(p.read_text() if p.exists() else "{}"); return
    if a.step == "purge": print(json.dumps({"purged": purge(a.app, a.model)})); return
    steps = {"all": ["manifest", "bundle", "smoke", "eval", "card"], "rebuild": ["bundle", "smoke", "eval", "card"]}.get(a.step, [a.step])
    for s in steps:
        {"manifest": step_manifest, "bundle": step_bundle, "smoke": step_smoke, "card": step_card, "publish": step_publish}.get(s, lambda x: step_eval(x, models))(a.app)


if __name__ == "__main__":
    main()
