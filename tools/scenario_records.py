"""Read capture_browser_scenario Evidence the way REA's environment manifest does.

One HAR-shaped record per network transaction, in request order; the ordinal is the transaction's zero-based position.
Bodies are decoded here (strict UTF-8, BOM kept) so the build tools can read and scan them as text."""
import base64, codecs
from urllib.parse import parse_qsl, urlsplit

def _text(body):
    if not body or body.get("state") != "captured": return None
    raw = base64.b64decode(body["content"])
    try: return codecs.decode(raw, "utf-8", "strict")
    except UnicodeDecodeError: return None

def _header(headers, name):
    if not headers or headers.get("state") != "captured": return None
    for item in headers.get("items", []):
        if item["name"].lower() == name: return item.get("value")
    return None

def scenario_records(evidence):
    items = evidence["normalized_result"]["events"]["items"]
    requests, counts, responses, contents = [], {}, {}, {}
    for event in items:
        kind = event["kind"]
        if kind == "request":
            requests.append(event); counts[event["transaction_id"]] = counts.get(event["transaction_id"], 0) + 1
        elif kind == "response": responses.setdefault(event["transaction_id"], []).append(event)
        elif kind == "network-content": contents.setdefault(event["source_event_sequence"], []).append(event)
    records = []
    for ordinal, request in enumerate(requests):
        tid = request["transaction_id"]; resp = responses.get(tid, [])
        response = resp[0] if len(resp) == 1 else None
        req_c = contents.get(request["sequence"], []); res_c = contents.get(response["sequence"], []) if response else []
        if counts[tid] != 1 or len(resp) > 1 or len(req_c) > 1 or len(res_c) > 1:
            records.append({"ordinal": ordinal, "reported": {}}); continue
        req_body = req_c[0] if req_c else None; res_body = res_c[0] if res_c else None
        url = None if request["url"]["redacted"] else request["url"]["url"]
        reported = {"request": {"method": request["method"], "url": url}}
        if url: reported["request"]["queryString"] = [{"name": k, "value": v} for k, v in parse_qsl(urlsplit(url).query, keep_blank_values=True)]
        text = _text(req_body["body"]) if req_body else None
        mime = (req_body["body"].get("media_type") if req_body and req_body["body"].get("state") == "captured" else None) or (_header(req_body["headers"], "content-type") if req_body else None)
        if text is not None and mime: reported["request"]["postData"] = {"mimeType": mime, "text": text}
        if response:
            body = res_body["body"] if res_body else None
            mime = (body.get("media_type") if body and body.get("state") == "captured" else None) or (_header(res_body["headers"], "content-type") if res_body else None) or ""
            content = {"mimeType": mime}
            decoded = _text(body) if body else None
            if decoded is not None: content["text"] = decoded
            reported["response"] = {"status": response["status"], "content": content}
        records.append({"ordinal": ordinal, "reported": reported})
    return records
