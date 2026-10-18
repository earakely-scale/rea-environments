# replay-qa

A generic tool-calling A2A agent for agent-env bundles. It knows nothing about any particular environment: every
MCP tool the env exposes is offered to the model as a function tool, the model's tool calls are run against the env
and their results fed back, and the loop ends when the model answers without calling a tool. The final assistant text
is the task's response, which a deterministic `agent_prompt_response_verifier` can grade.

## The loop

1. `deploy_agent` starts the container and registers the env's MCP URL through `urn:agentenv:mcp-config/v1`; the
   agent opens one MCP session per registered server and lists its tools. A tool name two servers share is prefixed
   with the server's alias; names are squeezed into `[A-Za-z0-9_-]{1,64}`.
2. `prompt_agent` sends the prompt. The history starts with the system prompt and the prompt; each turn is one
   OpenAI-compatible chat completion with every tool attached.
3. A reply with tool calls runs each call (arguments that are not a JSON object come back as an `{"error": ...}`
   result) and appends the results as `tool` messages, clipped to `REPLAY_QA_TOOL_RESULT_CHARS` (16000) characters.
   A reply with text and no tool call is the answer. A reply with neither is nudged once per turn.
4. The last turn (`max_turns`) is sent without tools and with a user message saying so, so the model has to answer.

The result carries the answer as its text part, a `structured_output` summary (model, end reason, turns, tool calls,
tokens, seconds), `Usage`, and a native trajectory in the `replay-qa-chat/1` format: `{"model", "messages", "turns",
"tools", "usage", "end_reason", "errors"}` where `messages` is the chat history (OpenAI roles, nested
`tool_calls`, `tool` results with `tool_call_id` and `name`, plus `reasoning` and `finish_reason` on assistant
messages). agentenv-hf reads it as `chat`.

## Configuration

Through `urn:agentenv:agent-config/v1`, which `prompt_agent` fills from the task step, `agent-env run --model`,
or the bundle's defaults:

| field | default | meaning |
|---|---|---|
| `model` | `openai/gpt-oss-120b:groq` (also `metadata.default_model` in `agent.toml`) | model name sent as-is to the endpoint |
| `max_turns` | 6 | model calls per task; the last one gets no tools |
| `system_prompt` | a one-line "answer with the tools, reply with the answer only" | replaces the default when set |
| `model_params` | `{"max_tokens": 1024}` | chat-completions parameters; known ones as keyword arguments, the rest in `extra_body` |
| `timeout_seconds` | 600 | a turn does not start past it |

The endpoint comes from the environment `deploy_agent` injects: `LITELLM_BASE_URL` (a `/v1` suffix is added when
missing) and `LITELLM_API_KEY`, resolved from `[model]` in `.agentenv/config.toml`; `LITELLM_EXTRA_HEADERS`
(a JSON object, from `[model.headers]`) is sent on every request when present.

## Limits

- Chat completions only: no Anthropic Messages or OpenAI Responses route, so reasoning shows up only where the
  provider returns it as `reasoning`/`reasoning_content`.
- Non-streaming requests, so a provider that only reports usage on streams reports none.
- No peer agents, skills, snapshots or triggers; a task that needs them wants another agent.
- Tool results are clipped, not summarised; a tool whose answer is larger than the clip loses its tail.
- Failures of the endpoint or the env end the task as an `infra_error`; a model that never answers ends it with an
  empty response and `end_reason: no_answer`.
