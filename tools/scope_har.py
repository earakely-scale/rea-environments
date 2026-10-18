#!/usr/bin/env python3
"""Scope a Playwright HAR to an application's API traffic and scrub secrets before it reaches rea.

Usage: scope_har.py IN.har OUT.har --origin http://127.0.0.1:PORT [--keep-regex REGEX] [--drop-regex REGEX] [--max-body BYTES] [--max-records N]
Keeps entries on the origin whose path matches --keep-regex (default: ^/api/|^/apis/|^/ghost/api/) and whose content type is
JSON-like, drops anything matching --drop-regex (default: login|logout|signup|password|session|token|oauth|csrf), scrubs
secret-looking JSON fields in request and response bodies (password/secret/token/apikey/api_key/authorization/cookie) to
"<scrubbed>", keeps only
content-type/accept headers and no cookies, drops entries whose response body exceeds --max-body, and keeps at most
--max-records entries (the largest bodies go first). Prints a JSON summary to stderr."""
import argparse, json, re, sys
from urllib.parse import urlparse

SECRET_KEYS = re.compile(r"password|passwd|secret|token|apikey|api_key|authorization|cookie|private_key", re.I)
JSONISH = re.compile(r"application/(json|[a-z.+-]*\+json)|text/plain|text/markdown", re.I)

def scrub(obj):
    if isinstance(obj, dict):
        return {k: ("<scrubbed>" if SECRET_KEYS.search(k) and isinstance(v, (str, int, float)) else scrub(v)) for k, v in obj.items()}
    if isinstance(obj, list):
        return [scrub(x) for x in obj]
    return obj

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src"); ap.add_argument("dst"); ap.add_argument("--origin", required=True)
    ap.add_argument("--keep-regex", default=r"^/api/|^/apis/|^/ghost/api/")
    ap.add_argument("--drop-regex", default=r"login|logout|signup|password|session|token|oauth|csrf")
    ap.add_argument("--max-body", type=int, default=60_000); ap.add_argument("--max-records", type=int, default=150)
    a = ap.parse_args()
    har = json.load(open(a.src)); keep, scrubbed, dropped = [], 0, {"other-origin": 0, "path": 0, "non-json": 0, "auth": 0, "big-body": 0, "over-max": 0}
    keep_re, drop_re = re.compile(a.keep_regex), re.compile(a.drop_regex, re.I)
    for e in har["log"]["entries"]:
        u = urlparse(e["request"]["url"]); origin = f"{u.scheme}://{u.netloc}"
        if origin != a.origin: dropped["other-origin"] += 1; continue
        if drop_re.search(u.path): dropped["auth"] += 1; continue
        if not keep_re.search(u.path): dropped["path"] += 1; continue
        mime = (e["response"].get("content") or {}).get("mimeType", "")
        text = (e["response"].get("content") or {}).get("text") or ""
        empty_api_reply = e["response"].get("status") in (204, 202) or (not text and not mime)
        if not JSONISH.search(mime) and not empty_api_reply: dropped["non-json"] += 1; continue
        if len(text.encode()) > a.max_body: dropped["big-body"] += 1; continue
        for holder in (e["request"].get("postData"), e["response"].get("content")):
            if holder and holder.get("text"):
                try:
                    body = json.loads(holder["text"]); clean = scrub(body)
                    if clean != body: holder["text"] = json.dumps(clean); scrubbed += 1
                except ValueError: pass
        e["request"]["headers"] = [h for h in e["request"]["headers"] if h["name"].lower() in ("content-type", "accept")]
        e["response"]["headers"] = [h for h in e["response"]["headers"] if h["name"].lower() == "content-type"]
        e["request"]["cookies"] = []; e["response"]["cookies"] = []
        keep.append(e)
    if len(keep) > a.max_records:
        keep.sort(key=lambda e: len(((e["response"].get("content") or {}).get("text") or "")), reverse=True)
        dropped["over-max"] = len(keep) - a.max_records; keep = keep[len(keep) - a.max_records:]
        keep.sort(key=lambda e: e["startedDateTime"])
    har["log"]["entries"] = keep
    json.dump(har, open(a.dst, "w"))
    methods = {}
    for e in keep: methods[e["request"]["method"]] = methods.get(e["request"]["method"], 0) + 1
    print(json.dumps({"kept": len(keep), "scrubbed_bodies": scrubbed, "dropped": dropped, "methods": methods, "bytes": sum(len(json.dumps(e)) for e in keep)}), file=sys.stderr)

if __name__ == "__main__": main()
