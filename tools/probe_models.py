#!/usr/bin/env python3
"""Probe which Hugging Face router model:provider pairs accept a tool-calling request with the token in secrets.yaml.
Prints status codes and error text only; the token is never printed. Also purges local task instances of a model that never ran."""
import json, os, sqlite3, sys, urllib.request, yaml
tok = yaml.safe_load(open("secrets/secrets.yaml"))["HF_ROUTER_TOKEN"]
H = {"Authorization": "Bearer " + tok, "Content-Type": "application/json"}
def req(url, body=None):
    r = urllib.request.Request(url, data=json.dumps(body).encode() if body else None, headers=H, method="POST" if body else "GET")
    try:
        with urllib.request.urlopen(r, timeout=90) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:160]
    except Exception as e:
        return -1, str(e)[:160]
code, models = req("https://router.huggingface.co/v1/models")
rows = models["data"] if isinstance(models, dict) else []
want = ["openai/gpt-oss-20b", "Qwen/Qwen3-32B", "moonshotai/Kimi-K2-Instruct-0905", "meta-llama/Llama-4-Scout-17B-16E-Instruct",
        "meta-llama/Llama-3.3-70B-Instruct", "zai-org/GLM-5.3-Flash", "Qwen/Qwen3-235B-A22B-Instruct-2507", "deepseek-ai/DeepSeek-V3.2",
        "MiniMaxAI/MiniMax-M2.5", "Qwen/Qwen3-Coder-480B-A35B-Instruct", "mistralai/Mistral-Small-3.2-24B-Instruct-2506",
        "meta-llama/Llama-4-Maverick-17B-128E-Instruct", "moonshotai/Kimi-K2.5", "Qwen/Qwen3-Next-80B-A3B-Instruct"]
ok_providers = {"groq", "cerebras", "sambanova", "fireworks-ai", "novita", "nebius", "nscale", "hyperbolic", "featherless-ai", "cohere", "scaleway", "publicai", "zai-org"}
byid = {m["id"]: m for m in rows}
print("models listed:", len(rows))
cands = []
for w in want:
    m = byid.get(w)
    if not m:
        print("  absent:", w); continue
    provs = [(p.get("provider"), p.get("supports_tools")) for p in m.get("providers", [])]
    desc = []
    for p, t in provs:
        tag = "" if t is None else ("+tools" if t else "-tools")
        desc.append(str(p) + tag)
        if p in ok_providers and t is not False:
            cands.append(w + ":" + str(p))
    print("  " + w + " -> " + ", ".join(desc))
print("== probing", len(cands), "candidates ==")
tools = [{"type": "function", "function": {"name": "get_time", "description": "Current time", "parameters": {"type": "object", "properties": {"tz": {"type": "string"}}, "required": ["tz"]}}}]
for c in cands:
    code, body = req("https://router.huggingface.co/v1/chat/completions", {"model": c, "messages": [{"role": "user", "content": "What time is it in Paris? Use the tool."}], "tools": tools, "tool_choice": "auto", "max_tokens": 64})
    if code == 200:
        ch = body["choices"][0]["message"]; tc = ch.get("tool_calls") or []
        msg = "tool_calls=%d" % len(tc) + ((" name=" + tc[0]["function"]["name"]) if tc else (" content=" + repr(str(ch.get("content"))[:40])))
    else:
        msg = str(body)[:120].replace("\n", " ")
    print("  %s %s: %s" % (code, c, msg))
if "--purge" in sys.argv:
    model = sys.argv[sys.argv.index("--purge") + 1]
    con = sqlite3.connect(os.path.expanduser("~/.local/state/agent-env/document_store/local.db"))
    ids = [rowid for rowid, doc in con.execute("select rowid, doc from docs_task_instances") if ((json.loads(doc).get("context") or {}).get("agent_model") == model)]
    con.executemany("delete from docs_task_instances where rowid=?", [(i,) for i in ids]); con.commit()
    print("deleted instance docs for", model, ":", len(ids))
