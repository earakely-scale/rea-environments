#!/usr/bin/env python3
"""Fill cards/TEMPLATE.md for one app from apps/SUMMARY.json, the bundle's tasks/INDEX.md and an episodes table.

Usage: make_card.py --app ghost --title "Ghost" --license MIT --authors "the Ghost Foundation" --repo GhostEnv-REA
                    --bundle DIR --summary apps/SUMMARY.json --episodes EPISODES.json --export-pr 4976 --out card.md
EPISODES.json: {"models": {"<model>": {"tasks": N, "passed": M, "tool_calls_mean": x, "input_tokens_mean": y}}, "count": N}"""
import argparse, json, re
from pathlib import Path

ap = argparse.ArgumentParser()
for k in ("app", "title", "license", "authors", "repo", "bundle", "summary", "out"): ap.add_argument(f"--{k}", required=True)
ap.add_argument("--episodes"); ap.add_argument("--apps"); ap.add_argument("--export-pr", default="4976"); ap.add_argument("--scenario-pr"); ap.add_argument("--template", default=str(Path(__file__).resolve().parent.parent / "cards" / "TEMPLATE.md"))
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
failed = {}
for e in ep.get("episodes", []):
    if e.get("score") != 1.0: failed.setdefault(e["model"], []).append(e["task"])
notes = [f"`{m}` missed " + ", ".join(f"`{t}`" for t in sorted(ts)) + "." for m, ts in failed.items()]
app_notes = json.load(open(a.apps)).get(a.app, {}).get("episode_notes") if a.apps else None
if app_notes: notes.append(app_notes)
if ep["models"] and not notes: notes.append("Every recorded episode passed.")
REASONS = {"other-origin": "other origins", "ui-page-or-asset": "UI pages or assets", "non-json": "non-JSON replies such as bodiless 204 writes"}
excl = s.get("excluded") or {}
excluded_text = ("no recorded group excluded" if not excl else
                 f"{sum(excl.values())} recorded group{'s' if sum(excl.values()) != 1 else ''} excluded (" + ", ".join(f"{n} as {REASONS.get(k, k)}" for k, v in sorted(excl.items()) for n in [v]) + ")")
def seeded_text(v):
    """One readable line from summary.json's seeded_objects, which workers write as a sentence, a list or a mapping."""
    if isinstance(v, str): return v
    if isinstance(v, list): return ", ".join(seeded_text(x) for x in v)
    if isinstance(v, dict): return "; ".join(f"{k.replace('_', ' ')}: {seeded_text(x)}" for k, x in v.items())
    return str(v)
summary_doc = json.load(open(Path(a.summary).parent / a.app / "summary.json"))
seeded_line = seeded_text(summary_doc.get("seeded_objects") or "see the capture notes")
if len(seeded_line) > 600: seeded_line = seeded_line[:597].rsplit(" ", 1)[0] + "..."
public = summary_doc.get("kind") == "public-api"
scenario = summary_doc.get("capture") == "scenario"
capture_detail = (f"a `capture_browser_scenario` session REA recorded itself; capture file sha256 `{s['scoped_har_sha256']}`, {s['scoped_har_bytes']:,} bytes"
                  if scenario else f"scoped HAR sha256 `{s['scoped_har_sha256']}`, {s['scoped_har_bytes']:,} bytes")
when = summary_doc.get("captured_on", "the capture date"); fair = summary_doc.get("fair_access")
if public:
    variant = {
        "SOURCE_LINE": f"built from one recorded browser session against the public API at `{s['origin']}` on {when}. The responses are real "
                       f"public-domain records published by {a.authors}, frozen as they were served then.",
        "TASK_LINE": "each asks one factual question about a recorded record, with a distinct answer, answerable through a recorded "
                     "exchange",
        "REPLAY_TEXT": f"Reads behave like the API did on {when}. The live API keeps changing, so every answer is about the recorded "
                       "snapshot, not today, and a query the session never made falls back to the closest record. The API is read-only "
                       "and so is the environment: it has no state and no write tools. The manifest's `unknowns` say what replay cannot know.",
        "MADE_STEPS": (f"1. No instance was run: a throwaway VM opened the public API's URLs in a browser REA launched"
                       + (f", within the publisher's fair-access rules ({fair})" if fair else "") + ".\n"
                       f"2. REA's `capture-browser-scenario` visited each API URL (`goto`) and recorded every network transaction "
                       f"({seeded_line}); the environment-manifest view read that capture directly, with no HAR or scrubbing step.")
        if scenario else f"1. No instance was run: a throwaway VM called the public API directly"
                      + (f", within the publisher's fair-access rules ({fair})" if fair else "") + ".\n"
                      f"2. Playwright opened the API origin and ran a scripted sequence of read requests ({seeded_line}); the HAR was scoped "
                      "to the API, with headers and cookies removed.",
        "STATE_CELL": "None: every call is independent; the API is read-only",
        "PROVENANCE_CELL": f"Real public-domain records from {a.authors}, as served on {when}",
        "CONTENT_LICENCE": f"Recorded content: responses of the public API at `{s['origin']}`, published by {a.authors} ({a.license}); "
                           "the dataset repeats them as recorded.",
    }
else:
    variant = {
        "SOURCE_LINE": "built from one recorded browser session against a self-hosted instance seeded with synthetic data.",
        "TASK_LINE": "each asks one factual question about a seeded object, with a distinct answer that the app does not ship by "
                     "default, answerable through a recorded exchange",
        "REPLAY_TEXT": "Reads of seeded objects behave like the application. Writes return the recorded answer of the one write the "
                       "session made, and the environment has no state: a created object does not appear in a later list. This is what "
                       "makes retrieval tasks hard-gradable and write tasks weak; the manifest's `unknowns` say so.",
        "MADE_STEPS": (f"1. {a.title} ran in Docker on a throwaway VM, bound to loopback, seeded through its own API with synthetic "
                       f"records ({seeded_line}); people and projects are invented.\n"
                       "2. REA's `capture-browser-scenario` launched Chromium and drove the app's own UI, with any credential given as a declared secret; "
                       "it recorded every network transaction with credential headers and declared secrets redacted, and the "
                       "environment-manifest view read that capture directly, with no HAR or scrubbing step.")
        if scenario else f"1. {a.title} ran in Docker on a throwaway VM, bound to loopback, seeded through its own API with synthetic "
                      f"records ({seeded_line}); people and projects are invented.\n"
                      "2. Playwright drove a login, the main pages and a scripted read, write, read sequence through the app's JSON API; "
                      "the HAR was scoped to the API, the login exchange dropped, secret-looking body fields scrubbed, headers and cookies removed.",
        "STATE_CELL": "None: every call is independent; writes replay one recorded answer",
        "PROVENANCE_CELL": f"Synthetic seed data on a self-hosted {a.title}; nothing real",
        "CONTENT_LICENCE": f"Recorded content: responses generated by a self-hosted {a.title} instance over synthetic data; {a.title} is "
                           f"{a.license} software by {a.authors} and is not redistributed here beyond the recorded JSON responses.",
    }
fill = {
    **variant,
    "APP_TITLE": a.title, "APP_NAME": a.title, "APP_VERSION": s["app_version"], "APP_LICENSE": a.license, "APP_AUTHORS": a.authors,
    "TOOL_COUNT": str(s["tools"]), "TOOL_COUNT_NORULES": str(s["tools_norules"]),
    "TOOLS_BY_METHOD": ", ".join(f"{v} {k}" for k, v in sorted(s["tools_by_method"].items(), key=lambda kv: -kv[1])),
    "SCOPED_RECORDS": str(s["scoped_records"]), "ORIGIN": s["origin"], "EXCLUDED_TEXT": excluded_text,
    "PARAMS_BY_RULE": ", ".join(f"{v} `{k}`" for k, v in sorted(s["params_by_rule"].items(), key=lambda kv: -kv[1])) or "none",
    "TASK_COUNT": str(len(task_rows)), "ENV_ID": a.app, "EPISODE_COUNT": str(ep.get("count", 0)),
    "MODELS": ", ".join(f"`{m}`" for m in ep["models"]) or "no model yet",
    "CAPTURE_EVIDENCE_ID": s["capture_evidence_id"], "MANIFEST_EVIDENCE_ID": s["manifest_evidence_id"], "CONFIDENCE": s["confidence"],
    "EVIDENCE_STEP": "" if scenario else "`rea inspect-web-network-capture` retained the exchanges as Evidence; ",
    "CAPTURE_DETAIL": capture_detail, "AUTHORITY": s.get("authority", "historical-reference"), "PR_LIST": "morluto/rea#4954, #4955, #4975" + (f", #{a.export_pr} and #{a.scenario_pr}" if a.scenario_pr else f" and #{a.export_pr}"),
    "TASK_TABLE": task_table, "MODEL_BOARD": board, "EPISODE_NOTES": " ".join(notes), "REPO_NAME": a.repo,
    "SEEDED_OBJECTS": seeded_line,
}
out = tpl
for k, v in fill.items(): out = out.replace("{{" + k + "}}", str(v))
missing = re.findall(r"\{\{[A-Z_]+\}\}", out)
assert not missing, f"unfilled placeholders: {missing}"
Path(a.out).write_text(out); print(f"wrote {a.out} ({len(out)} chars)")
