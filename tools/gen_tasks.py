#!/usr/bin/env python3
"""Generate deterministic retrieval tasks for a replay environment from its environment manifest and capture Evidence.

Usage: gen_tasks.py --manifest M.json --capture C.json --bundle DIR --env ENV_ID --agent replay-qa [--max 12] [--seed 7]
For each GET tool with a JSON object or array body in its first record, pick distinctive scalar fields (strings 3-80 chars
with letters, not urls/ids/hashes/dates) and write tasks/qa-NN-<tool>.json: deploy_env + deploy_agent + prompt_agent (a
question naming the tool's path and the parameter values of the record) + agent_prompt_response_verifier with the field's
value as the needle. Also writes evals/<env>-retrieval.toml and tasks/INDEX.md. Deterministic given --seed."""
import argparse, collections, json, random, re
from pathlib import Path
from urllib.parse import urlparse

SKIP_KEYS = re.compile(r"id$|uid|url|href|hash|sha|token|password|secret|created|updated|timestamp|time$|date|At$|version|etag|avatar|color|icon|type$|kind$|status|state$|environment|locale|timezone|theme|error|code$|mode$|role$|visibility|format$|encoding|mime|path$|ref$|sort$|order$|roles?$|mark_unread|^Platform$|location$|package|props|Node|Arch|Docker", re.I)
PREFER_KEYS = re.compile(r"(^|_)(name|title|display_name|displayname|username|login|email|slug|subject|message|text|description|summary|label|caption|headline|full_name|first_name|last_name|nickname|body|content|purpose|header|bio|location|website|company)$", re.I)
URLISH = re.compile(r"^(https?:|/|[a-f0-9]{16,}$|\d{4}-\d{2}-\d{2}T)")
BORING = {"online", "offline", "production", "development", "true", "false", "null", "none", "default", "en", "en-us", "admin", "member", "public", "private"}

def scalar_fields(body, prefix="", depth=0):
    """Yield (path, value, preferred) for distinctive string scalars: object fields, one nesting level, and the first element of lists."""
    if isinstance(body, list):
        if body and isinstance(body[0], dict): yield from scalar_fields(body[0], prefix + "[0].", depth)
        return
    if not isinstance(body, dict): return
    for k, v in body.items():
        if isinstance(v, dict) and depth < 2: yield from scalar_fields(v, f"{prefix}{k}.", depth + 1); continue
        if isinstance(v, list) and depth < 2 and v and isinstance(v[0], dict): yield from scalar_fields(v[0], f"{prefix}{k}[0].", depth + 1); continue
        if not isinstance(v, str): continue
        if SKIP_KEYS.search(k) or URLISH.match(v) or not re.search(r"[A-Za-z]{3,}", v) or re.search(r"notify_props|\.key$", prefix + k): continue
        if v.strip().lower() in BORING or not (3 <= len(v) <= 80) or "\n" in v or "{" in v or "<" in v: continue
        yield (prefix + k, v, bool(PREFER_KEYS.search(k)))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True); ap.add_argument("--capture", required=True); ap.add_argument("--bundle", required=True)
    ap.add_argument("--env", required=True); ap.add_argument("--agent", default="replay-qa"); ap.add_argument("--max", type=int, default=12)
    ap.add_argument("--seed", type=int, default=7); ap.add_argument("--app", default=None); ap.add_argument("--model", default=None)
    ap.add_argument("--style", choices=["natural", "guided"], default="natural")
    ap.add_argument("--exclude-tools", default=r"themes|settings|_info_by|notifications|newsletters|search_index|frontend|config$|version$|ping$|site$")
    a = ap.parse_args(); rnd = random.Random(a.seed)
    m = json.load(open(a.manifest)); nr = m.get("normalized_result", m); cap = json.load(open(a.capture)); records = cap["normalized_result"]["records"]
    by_ord = {r["ordinal"]: r for r in records}
    candidates = []
    for tool in nr["tools"]:
        if tool["method"] != "GET" or not tool["record_ordinals"]: continue
        if a.exclude_tools and re.search(a.exclude_tools, tool["name"]): continue
        rec = by_ord.get(tool["record_ordinals"][0]);
        if rec is None: continue
        rep = rec["reported"]; content = (rep.get("response") or {}).get("content") or {}
        if (rep.get("response") or {}).get("status", 0) >= 400: continue
        if not str(content.get("mimeType", "")).startswith("application/json"): continue
        try: body = json.loads(content.get("text") or "")
        except ValueError: continue
        fields = [f for f in scalar_fields(body) if f[2]] or list(scalar_fields(body))
        if not fields: continue
        path = urlparse(rep["request"]["url"]).path; segs = path.strip("/").split("/")
        args = {p["name"]: segs[p["index"]] for p in tool["params"] if p["index"] < len(segs)}
        if any(re.fullmatch(r"[a-z]{1,5}", v) for v in args.values()): continue   # literal aliases such as "me" folded into a parameter
        query = {q["name"]: q["value"] for q in rep["request"].get("queryString", []) if q["name"] in tool["query_parameter_names"]}
        candidates.append((tool, rec, fields, args, query))
    rnd.shuffle(candidates)
    seen, chosen = collections.Counter(), []
    for c in sorted(candidates, key=lambda c: (0 if c[3] else 1)):   # identified objects (path params) first
        if seen[c[0]["name"]] >= 1 and len(candidates) > a.max: continue
        seen[c[0]["name"]] += 1; chosen.append(c)
        if len(chosen) >= a.max: break
    bundle = Path(a.bundle); (bundle / "tasks").mkdir(parents=True, exist_ok=True); (bundle / "evals").mkdir(exist_ok=True)
    names, index = [], ["# Retrieval tasks", "", f"Generated from the environment manifest ({nr.get('tool_count', len(nr['tools']))} tools) and its capture Evidence. Each task asks one factual question answerable through exactly one recorded exchange and is graded deterministically: the response must contain the recorded value.", "", "| task | tool | arguments | field | answer |", "|---|---|---|---|---|"]
    for i, (tool, rec, fields, args, query) in enumerate(chosen, 1):
        field, value, _preferred = rnd.choice(fields)
        argtxt = ", ".join(f"{k}={v}" for k, v in {**args, **query}.items()) or "no arguments"
        name = f"qa-{i:02d}-{tool['name'][:40]}"; names.append(name)
        segs = urlparse(rec["reported"]["request"]["url"]).path.strip("/").split("/")
        literals = [seg for i, seg in enumerate(segs) if not any(p["index"] == i for p in tool["params"]) and seg not in ("api", "apis", "v1", "v2", "v4", "ghost", "admin", "meta", "db", "data", "namespaces", "default")]
        resource = " ".join(literals[-2:]).replace("-", " ") or tool["name"]
        if a.style == "guided":
            prompt = (f"Using only the environment's tools, call the tool `{tool['name']}` with {argtxt} and report the value of the "
                      f"field `{field}` from its result. Answer with the value only, nothing else.")
        else:
            where = ("" if argtxt == "no arguments" else (" with " + " and ".join(f"{k} {v}" for k, v in {**args, **query}.items())))
            if field.startswith("[0]."):
                prompt = (f"In this {a.app or a.env} environment, list the {resource}{where} and report the `{field[4:]}` of the first entry. "
                          f"Use only the environment's tools. Answer with the value only, nothing else.")
            else:
                prompt = (f"In this {a.app or a.env} environment, look up the {resource}{where} and report its `{field}`. "
                          f"Use only the environment's tools. Answer with the value only, nothing else.")
        steps = [
            {"id": "env", "type": "deploy_env", "env_id": a.env, "sandbox_type": "local"},
            {"id": "agent", "type": "deploy_agent", "agent_name": a.agent, "env_ids": [a.env], "env_step_id": "env", "sandbox_type": "local"},
            {"id": "ask", "type": "prompt_agent", "agent_name": a.agent, "prompt_id": "q", "prompt": prompt, "max_turns": 6, **({"model": a.model} if a.model else {})},
            {"id": "grade", "type": "agent_prompt_response_verifier", "prompt_id": "q", "verifier_id": "retrieval",
             "criteria": [{"type": "response_contains", "criterion": f"response states {field}", "needles": [value]}]},
        ]
        json.dump(steps, open(bundle / "tasks" / f"{name}.json", "w"), indent=1)
        index.append(f"| `{name}` | `{tool['name']}` | {argtxt} | `{field}` | `{value}` |")
    (bundle / "evals" / f"{a.env}-retrieval.toml").write_text("tasks = [\n" + "".join(f'  "{n}",\n' for n in names) + "]\n")
    (bundle / "tasks" / "INDEX.md").write_text("\n".join(index) + "\n")
    print(json.dumps({"tasks": len(names), "candidates": len(candidates), "names": names}))

if __name__ == "__main__": main()
