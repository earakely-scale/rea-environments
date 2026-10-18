#!/usr/bin/env python3
"""Fill cards/TEMPLATE.md for one app from apps/SUMMARY.json, the bundle's tasks/INDEX.md and an episodes table.

Usage: make_card.py --app ghost --title "Ghost" --license MIT --authors "the Ghost Foundation" --repo GhostEnv-REA
                    --bundle DIR --summary apps/SUMMARY.json --episodes EPISODES.json --export-pr 4976 --out card.md
EPISODES.json: {"models": {"<model>": {"tasks": N, "passed": M, "tool_calls_mean": x, "input_tokens_mean": y}}, "count": N}"""
import argparse, json, re
from pathlib import Path

ap = argparse.ArgumentParser()
for k in ("app", "title", "license", "authors", "repo", "bundle", "summary", "out"): ap.add_argument(f"--{k}", required=True)
ap.add_argument("--episodes"); ap.add_argument("--export-pr", default="4976"); ap.add_argument("--template", default=str(Path(__file__).resolve().parent.parent / "cards" / "TEMPLATE.md"))
a = ap.parse_args()
s = json.load(open(a.summary))[a.app]; tpl = open(a.template).read()
index = (Path(a.bundle) / "tasks" / "INDEX.md").read_text().splitlines()
task_rows = [l for l in index if l.startswith("| `qa-")]
task_table = "\n".join(["| task | tool | arguments | field | answer |", "|---|---|---|---|---|", *task_rows])
ep = json.load(open(a.episodes)) if a.episodes and Path(a.episodes).exists() else {"models": {}, "count": 0}
if ep["models"]:
    board = ["| model | tasks | passed | pass rate | mean tool calls | mean input tokens |", "|---|---|---|---|---|---|"]
    for m, r in ep["models"].items():
        board.append(f"| `{m}` | {r['tasks']} | {r['passed']} | {r['passed']/max(r['tasks'],1):.0%} | {r.get('tool_calls_mean', 0):.1f} | {r.get('input_tokens_mean', 0):,.0f} |")
    board = "\n".join(board) + "\n\nEvery episode is in the `episodes` config with its transcript; rewards are the deterministic verifier scores."
else:
    board = "No episodes recorded yet."
fill = {
    "APP_TITLE": a.title, "APP_NAME": a.title, "APP_VERSION": s["app_version"], "APP_LICENSE": a.license, "APP_AUTHORS": a.authors,
    "TOOL_COUNT": str(s["tools"]), "TOOL_COUNT_NORULES": str(s["tools_norules"]),
    "TOOLS_BY_METHOD": ", ".join(f"{v} {k}" for k, v in sorted(s["tools_by_method"].items(), key=lambda kv: -kv[1])),
    "SCOPED_RECORDS": str(s["scoped_records"]), "ORIGIN": s["origin"], "EXCLUDED_COUNT": str(sum(s["excluded"].values())),
    "PARAMS_BY_RULE": ", ".join(f"{v} `{k}`" for k, v in sorted(s["params_by_rule"].items(), key=lambda kv: -kv[1])) or "none",
    "TASK_COUNT": str(len(task_rows)), "ENV_ID": a.app, "EPISODE_COUNT": str(ep.get("count", 0)),
    "MODELS": ", ".join(f"`{m}`" for m in ep["models"]) or "no model yet",
    "CAPTURE_EVIDENCE_ID": s["capture_evidence_id"], "MANIFEST_EVIDENCE_ID": s["manifest_evidence_id"], "CONFIDENCE": s["confidence"],
    "HAR_SHA256": s["scoped_har_sha256"], "HAR_BYTES": f"{s['scoped_har_bytes']:,}", "EXPORT_PR": a.export_pr,
    "TASK_TABLE": task_table, "MODEL_BOARD": board, "REPO_NAME": a.repo,
    "SEEDED_OBJECTS": json.load(open(Path(a.summary).parent / a.app / "summary.json")).get("seeded_objects", "see the capture notes"),
}
out = tpl
for k, v in fill.items(): out = out.replace("{{" + k + "}}", str(v))
missing = re.findall(r"\{\{[A-Z_]+\}\}", out)
assert not missing, f"unfilled placeholders: {missing}"
Path(a.out).write_text(out); print(f"wrote {a.out} ({len(out)} chars)")
