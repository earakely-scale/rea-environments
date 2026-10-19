#!/usr/bin/env python3
"""Generate deterministic retrieval tasks for a replay environment from its environment manifest and capture Evidence.

Usage: gen_tasks.py --manifest M.json --capture C.json --bundle DIR --env ENV_ID --agent replay-qa [--max 12] [--seed 7]
                    [--seed-dir DIR] [--max-occurrences 6] [--per-tool 2]
For each GET tool with a JSON body in its first record, collect distinctive string fields and write tasks/qa-NN-<tool>.json:
deploy_env + deploy_agent + prompt_agent (a question naming the resource and the record's parameter values) +
agent_prompt_response_verifier with the field's value as the needle. Also writes evals/<env>-retrieval.toml and
tasks/INDEX.md. Deterministic given --seed.

An answer must be a value a model cannot guess or read off the call: it is distinctive in shape (several words, or letters
with digits, or a long hyphenated/dotted identifier), it is not the capture admin's own identity, it appears in at most
--max-occurrences recorded responses (built-in defaults shown on every page drop out), it is not part of the tool name or the call's arguments, it
is not a resource name that repeats the path, every word of it occurs in the seed inputs under --seed-dir (so it was
seeded, not shipped by the app), and no two tasks share an answer."""
import argparse, collections, json, random, re
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from scenario_records import scenario_records
from urllib.parse import urlparse

SKIP_KEYS = re.compile(r"id$|uid|url|href|hash|sha|token|password|secret|created|updated|timestamp|time$|date|At$|version|etag|avatar|color|icon|type$|kind$|status|state$|environment|locale|timezone|theme|error|code$|mode$|role$|visibility|format$|encoding|mime|path$|ref$|sort$|order$|roles?$|mark_unread|^Platform$|location$|package|props|Node|Arch|Docker", re.I)
PREFER_KEYS = re.compile(r"(^|_)(name|title|display_name|displayname|username|login|email|slug|subject|message|text|description|summary|label|caption|headline|full_name|first_name|last_name|nickname|body|content|purpose|header|bio|location|website|company)$", re.I)
URLISH = re.compile(r"^(https?:|/|[a-f0-9]{16,}$|\d{4}-\d{2}-\d{2}T|[a-z][A-Za-z]*s/\S+$)")
BORING = {"online", "offline", "production", "development", "true", "false", "null", "none", "default", "en", "en-us", "admin", "member", "public", "private"}
JSON_LIKE = re.compile(r"\s*application/(json|[a-z.+-]*\+json)\b", re.I)   # geo+json and ld+json answer like JSON
ADMIN = re.compile(r"rea[-_ .]?admin", re.I)   # the capture's own admin identity answers almost every ownership field
SEED_SKIP = re.compile(r"\.(har|md)$|\.capture\.json$|\.manifest(\.norules)?\.json$|^summary\.json$|^app\.json$|^seed-ids\.json$|^req\..*\.json$")


def scalar_fields(body, prefix="", depth=0):
    """Yield (path, value, preferred) for string scalars: object fields, two nesting levels, and the first element of lists."""
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


def distinctive_shape(v):
    """Several words, letters with digits, or a long hyphenated/dotted/@ identifier; single short words are guessable."""
    words = re.findall(r"[A-Za-z]{2,}", v)
    if len(v.split()) >= 2 and len(words) >= 2: return True
    if re.search(r"\d", v) and re.search(r"[A-Za-z]{2,}", v): return True
    return len(v) >= 9 and re.search(r"[-.@]", v) is not None and len(words) >= 2


def seed_text(seed_dir):
    if not seed_dir: return None
    parts = []
    for p in sorted(Path(seed_dir).rglob("*")):
        if p.is_file() and not SEED_SKIP.search(p.name) and p.stat().st_size < 4_000_000 and "examples" not in p.parts and "node_modules" not in p.parts:
            parts.append(p.read_text(errors="ignore"))
    return "\n".join(parts).lower()


def seeded(v, text):
    """Every word of three or more letters occurs in the seed inputs (values built in code from seeded words still pass)."""
    if text is None: return True
    words = [w.lower() for w in re.findall(r"[A-Za-z]{3,}", v)]
    return bool(words) and all(w in text for w in words)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True); ap.add_argument("--capture", required=True); ap.add_argument("--bundle", required=True)
    ap.add_argument("--env", required=True); ap.add_argument("--agent", default="replay-qa"); ap.add_argument("--max", type=int, default=12)
    ap.add_argument("--seed", type=int, default=7); ap.add_argument("--app", default=None); ap.add_argument("--model", default=None)
    ap.add_argument("--style", choices=["natural", "guided"], default="natural")
    ap.add_argument("--exclude-tools", default=r"themes|settings|_info_by|notifications|newsletters|search_index|frontend|config$|version$|ping$|site$")
    ap.add_argument("--seed-dir", default=None); ap.add_argument("--max-occurrences", type=int, default=12); ap.add_argument("--per-tool", type=int, default=2)
    a = ap.parse_args(); rnd = random.Random(a.seed)
    m = json.load(open(a.manifest)); nr = m.get("normalized_result", m); cap = json.load(open(a.capture))
    records = scenario_records(cap) if cap.get("operation") == "capture_browser_scenario" else cap["normalized_result"]["records"]
    by_ord = {r["ordinal"]: r for r in records}
    texts = [((r["reported"].get("response") or {}).get("content") or {}).get("text") or "" for r in records]
    stext = seed_text(a.seed_dir)

    def occurrences(v):
        esc = json.dumps(v)[1:-1]
        return sum(1 for t in texts if v in t or esc in t)

    candidates, rejected = [], collections.Counter()
    for tool in nr["tools"]:
        if tool["method"] != "GET" or not tool["record_ordinals"]: continue
        if a.exclude_tools and re.search(a.exclude_tools, tool["name"]): continue
        rec = by_ord.get(tool["record_ordinals"][0])
        if rec is None: continue
        rep = rec["reported"]; content = (rep.get("response") or {}).get("content") or {}
        if (rep.get("response") or {}).get("status", 0) >= 400: continue
        if not JSON_LIKE.match(str(content.get("mimeType", ""))): continue
        try: body = json.loads(content.get("text") or "")
        except ValueError: continue
        path = urlparse(rep["request"]["url"]).path; segs = path.strip("/").split("/")
        args = {p["name"]: segs[p["index"]] for p in tool["params"] if p["index"] < len(segs)}
        if any(re.fullmatch(r"[a-z]{1,5}", v) for v in args.values()): continue   # literal aliases such as "me" folded into a parameter
        query = {q["name"]: q["value"] for q in rep["request"].get("queryString", []) if q["name"] in tool["query_parameter_names"] and q.get("value") not in ("", None)}
        call_text = (tool["name"] + " " + " ".join(args.values()) + " " + " ".join(query.values())).lower()
        fields = []
        for f, v, pref in scalar_fields(body):
            low = v.lower()
            if not distinctive_shape(v): rejected["shape"] += 1; continue
            if ADMIN.search(v): rejected["admin"] += 1; continue
            if low in call_text or re.sub(r"[^a-z0-9]+", "_", low).strip("_") in call_text: rejected["in-call"] += 1; continue
            if occurrences(v) > a.max_occurrences: rejected["common"] += 1; continue
            if not seeded(v, stext): rejected["not-seeded"] += 1; continue
            fields.append((f, v, pref))
        if not fields: continue
        fields.sort(key=lambda x: (0 if x[2] else 1))
        candidates.append((tool, rec, fields, args, query))
    rnd.shuffle(candidates)
    candidates.sort(key=lambda c: (0 if c[3] else 1))   # identified objects (path params) first; stable after the shuffle
    chosen, used_values, per_tool = [], set(), collections.Counter()
    for round_no in range(a.per_tool):
        for tool, rec, fields, args, query in candidates:
            if len(chosen) >= a.max: break
            if per_tool[tool["name"]] != round_no: continue
            pool = [f for f in fields if f[1].lower() not in used_values]
            if not pool: continue
            preferred = [f for f in pool if f[2]] or pool
            field = rnd.choice(preferred)
            used_values.add(field[1].lower()); per_tool[tool["name"]] += 1
            chosen.append((tool, rec, field, args, query))
    bundle = Path(a.bundle); (bundle / "tasks").mkdir(parents=True, exist_ok=True); (bundle / "evals").mkdir(exist_ok=True)
    names, index = [], ["# Retrieval tasks", "", f"Generated from the environment manifest ({nr.get('tool_count', len(nr['tools']))} tools) and its capture Evidence. Each task asks one factual question about a {'seeded object' if stext is not None else 'recorded record'}, answerable through one recorded exchange, and is graded deterministically: the response must contain the recorded value. Answers are distinct{', seeded,' if stext is not None else ''} and appear in at most {a.max_occurrences} recorded responses.", "", "| task | tool | arguments | field | answer |", "|---|---|---|---|---|"]
    for i, (tool, rec, (field, value, _p), args, query) in enumerate(chosen, 1):
        argtxt = ", ".join(f"{k}={v}" for k, v in {**args, **query}.items()) or "no arguments"
        name = f"qa-{i:02d}-{tool['name'][:40]}"; names.append(name)
        segs = urlparse(rec["reported"]["request"]["url"]).path.strip("/").split("/")
        literals = [seg for j, seg in enumerate(segs) if not any(p["index"] == j for p in tool["params"]) and seg not in ("api", "apis", "v1", "v2", "v3", "v4", "rest", "ghost", "admin", "meta", "db", "data", "namespaces", "default")]
        resource = " ".join(literals[-2:]).replace("-", " ").replace("_", " ") or tool["name"]
        if a.style == "guided":
            prompt = (f"Using only the environment's tools, call the tool `{tool['name']}` with {argtxt} and report the value of the "
                      f"field `{field}` from its result. Answer with the value only, nothing else.")
        else:
            where = ("" if argtxt == "no arguments" else (" with " + " and ".join(f"{k} {v}" for k, v in {**args, **query}.items())))
            if field.startswith("[0]."):
                prompt = (f"In this {a.app or a.env} environment, list the {resource}{where} and report the `{field[4:]}` of the first item in the "
                          f"returned list. Use only the environment's tools. Answer with the value only, nothing else.")
            else:
                prompt = (f"In this {a.app or a.env} environment, look up the {resource}{where} and report its `{field}`. "
                          f"Use only the environment's tools. Answer with the value only, nothing else.")
        steps = [
            {"id": "env", "type": "deploy_env", "env_id": a.env, "sandbox_type": "local"},
            {"id": "agent", "type": "deploy_agent", "a2a_agent_id": a.agent, "agent_name": a.agent, "env_ids": [a.env], "env_step_id": "env", "sandbox_type": "local"},
            {"id": "ask", "type": "prompt_agent", "agent_name": a.agent, "prompt_id": "q", "prompt": prompt, "max_turns": 6, **({"model": a.model} if a.model else {})},
            {"id": "grade", "type": "agent_prompt_response_verifier", "prompt_id": "q", "verifier_id": "retrieval",
             "criteria": [{"type": "response_contains", "criterion": f"response states {field}", "needles": [value]}]},
        ]
        json.dump(steps, open(bundle / "tasks" / f"{name}.json", "w"), indent=1)
        index.append(f"| `{name}` | `{tool['name']}` | {argtxt} | `{field}` | `{value}` |")
    (bundle / "evals" / f"{a.env}-retrieval.toml").write_text("tasks = [\n" + "".join(f'  "{n}",\n' for n in names) + "]\n")
    (bundle / "tasks" / "INDEX.md").write_text("\n".join(index) + "\n")
    print(json.dumps({"tasks": len(names), "candidates": len(candidates), "rejected": dict(rejected), "names": names}))


if __name__ == "__main__": main()
