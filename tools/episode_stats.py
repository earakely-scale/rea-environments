#!/usr/bin/env python3
"""Summarize recorded runs of a bundle's retrieval tasks per model from agent-env's local document store.

Usage: episode_stats.py --db ~/.local/state/agent-env/document_store/local.db --bundle-path /abs/bundles/<app> --out EPISODES.json
Reads docs_task_instances rows whose task_id starts with @local/<bundle-path> and whose task is a qa-* task; groups by
context.agent_model; reports tasks, passed (verifier score 1.0), mean tool calls, mean input tokens when the trajectory
records usage (read through the object store file URL)."""
import argparse, json, os, sqlite3, statistics, urllib.parse
from pathlib import Path

ap = argparse.ArgumentParser(); ap.add_argument("--db", required=True); ap.add_argument("--bundle-path", required=True); ap.add_argument("--out", required=True)
a = ap.parse_args()
bundle = str(Path(a.bundle_path).expanduser().resolve()); prefix_variants = {f"@local/{bundle}/", "@local/~/" + os.path.relpath(bundle, Path.home()) + "/"}
con = sqlite3.connect(os.path.expanduser(a.db)); rows = [json.loads(r[0]) for r in con.execute("select doc from docs_task_instances")]
per_model = {}; episodes = []
for d in rows:
    tid = d.get("task_id", "")
    if not any(tid.startswith(p) for p in prefix_variants): continue
    task = tid.rsplit("/", 1)[-1]
    if not task.startswith("qa-") or d.get("status") not in ("completed", "failed"): continue
    ctx = d.get("context") or {}; model = ctx.get("agent_model") or "unknown"
    ver = ((ctx.get("metadata") or {}).get("verifications") or {}).get("retrieval") or {}
    score = ver.get("score"); pr = (ctx.get("prompt_responses") or [{}])[0]
    tool_calls = pr.get("tool_call_count"); in_tok = None
    url = pr.get("agent_trajectory_object_url") or pr.get("agent_trajectory_s3_uri")
    if url and url.startswith("file://"):
        try:
            traj = json.load(open(urllib.parse.unquote(url[len("file://"):]))); usage = traj.get("usage") or {}
            in_tok = usage.get("input_tokens") or usage.get("prompt_tokens")
        except Exception: pass
    episodes.append({"task": task, "model": model, "score": score, "tool_calls": tool_calls, "input_tokens": in_tok, "status": d.get("status"), "instance": d.get("instance_id")})
    m = per_model.setdefault(model, {"tasks": 0, "passed": 0, "tool_calls": [], "input_tokens": []})
    m["tasks"] += 1; m["passed"] += 1 if score == 1.0 else 0
    if isinstance(tool_calls, (int, float)): m["tool_calls"].append(tool_calls)
    if isinstance(in_tok, (int, float)): m["input_tokens"].append(in_tok)
out = {"count": len(episodes), "models": {m: {"tasks": v["tasks"], "passed": v["passed"], "tool_calls_mean": statistics.mean(v["tool_calls"]) if v["tool_calls"] else 0, "input_tokens_mean": statistics.mean(v["input_tokens"]) if v["input_tokens"] else 0} for m, v in per_model.items()}, "episodes": episodes}
json.dump(out, open(a.out, "w"), indent=1); print(json.dumps({"count": out["count"], "models": out["models"]}))
