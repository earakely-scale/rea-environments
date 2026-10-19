#!/usr/bin/env python3
"""Scan captures for credential material in request AND response bodies, query strings and URLs.
Usage: credscan.py FILE...   (HAR, rea capture JSON or capture_browser_scenario Evidence). Prints key paths and value shapes only, never values."""
import json, re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
from scenario_records import scenario_records  # noqa: E402
KEY = re.compile(r"(^|[_-])(access_?token|refresh_?token|id_?token|auth_?token|token|api_?key|apikey|x-api-key|secret|client_?secret|password|passwd|pw|session_?id|sessionid|session_?token|jwt|private_?key|salt|signature|totp|otp|key_?secret)$", re.I)
JWT = re.compile(r"eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{4,}")
SHAPES = re.compile(r"hf_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9_-]{16,}|ghp_[A-Za-z0-9]{20,}|xox[bpa]-[A-Za-z0-9-]{10,}|Bearer\s+[A-Za-z0-9._~+/-]{16,}")
BENIGN = {"<scrubbed>", "", None, True, False}
def walk(o, path, hits):
    if isinstance(o, dict):
        for k, v in o.items():
            p = f"{path}.{k}"
            if KEY.search(str(k)) and isinstance(v, str) and v not in BENIGN and len(v) >= 6 and not v.startswith(("<", "[REDACTED")):
                hits.append(("key", p, f"len={len(v)}"))
            walk(v, p, hits)
    elif isinstance(o, list):
        for i, v in enumerate(o[:200]): walk(v, f"{path}[{i}]" if i < 1 else f"{path}[]", hits)
    elif isinstance(o, str):
        if JWT.search(o): hits.append(("jwt", path, "jwt-shaped"))
        if SHAPES.search(o): hits.append(("shape", path, SHAPES.search(o).group(0)[:5] + "…"))
def bodies(entry):
    req, res = entry.get("request", {}), entry.get("response", {})
    out = [("url", req.get("url") or "")]
    for q in req.get("queryString", []) or []: out.append((f"query.{q.get('name')}", q.get("value", "")))
    out.append(("req", ((req.get("postData") or {}).get("text")) or ""))
    out.append(("res", ((res.get("content") or {}).get("text")) or ""))
    return out
for f in sys.argv[1:]:
    d = json.load(open(f))
    entries = d["log"]["entries"] if "log" in d else [r["reported"] for r in scenario_records(d)] if d.get("operation") == "capture_browser_scenario" else [r.get("reported", {}) for r in d["normalized_result"]["records"]]
    hits = []
    for i, e in enumerate(entries):
        method = (e.get("request") or {}).get("method", "?"); url = (e.get("request") or {}).get("url") or ""
        path = re.sub(r"^https?://[^/]+", "", url).split("?")[0]
        for kind, text in bodies(e):
            if kind.startswith("query.") and KEY.search(kind[6:]) and text: hits.append(("query", f"{method} {path} ?{kind[6:]}", f"len={len(text)}"))
            if not text or not isinstance(text, str): continue
            try: obj = json.loads(text)
            except Exception: obj = None
            h = []
            if obj is not None: walk(obj, kind, h)
            else:
                if JWT.search(text): h.append(("jwt", kind, "jwt-shaped"))
                if SHAPES.search(text): h.append(("shape", kind, "shape"))
            for kk, p, info in h: hits.append((kk, f"{method} {path} {p}", info))
    uniq = sorted(set(hits))
    print(f"{f.split('/')[-1]}: {len(uniq)} distinct hits")
    for kk, p, info in uniq[:25]: print(f"   {kk:6} {p[:150]}  [{info}]")
