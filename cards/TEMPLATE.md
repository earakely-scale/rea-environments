# {{APP_TITLE}} on AgentEnv, from a REA capture

<!-- card note for `agent-env hf publish --card-note`; the plugin writes the YAML header, configs and the agentenv table. -->

**What this is.** A replay environment of **{{APP_NAME}} {{APP_VERSION}}** ({{APP_LICENSE}}), built from one recorded
browser session against a self-hosted instance seeded with synthetic data. [REA](https://github.com/morluto/rea)
projected the capture into an **environment manifest** ({{TOOL_COUNT}} tools), and `rea environment-export` wrote the
bundle you can run from this dataset. Every tool call replays a retained record from the capture, cites the record and
the Evidence it came from, and nothing executes {{APP_NAME}}. Tasks are graded deterministically, with no judge.

## What's in it

- **{{TOOL_COUNT}} tools** ({{TOOLS_BY_METHOD}}) over {{SCOPED_RECORDS}} recorded exchanges on `{{ORIGIN}}`; {{EXCLUDED_COUNT}}
  recorded groups excluded as UI pages, assets or other origins.
- **Path parameters**: {{PARAMS_BY_RULE}}. REA's four format rules (numeric, uuid, hex, iso-date) applied unconditionally;
  the three opt-in rules (`after-uid-literal`, `opaque-token`, `sibling-variance`) were requested and are labelled per
  parameter. Without them the manifest has {{TOOL_COUNT_NORULES}} tools, one per literal path.
- **Unknowns** the manifest states explicitly: authorization model, response semantics beyond recorded exchanges, state
  transitions between tools.
- **{{TASK_COUNT}} retrieval tasks** (`evals/{{ENV_ID}}-retrieval.toml`): each asks one factual question answerable through
  exactly one recorded exchange; reward 1 if the response contains the recorded value, else 0. Plus `smoke`, which
  deploys the environment and checks replay through the MCP endpoint.
- **{{EPISODE_COUNT}} recorded episodes** by {{MODELS}} through the Hugging Face router, with their chat transcripts.
- **Provenance**: capture `{{CAPTURE_EVIDENCE_ID}}` (scoped HAR sha256 `{{HAR_SHA256}}`, {{HAR_BYTES}} bytes), manifest view
  `{{MANIFEST_EVIDENCE_ID}}`, confidence `{{CONFIDENCE}}`, authority `historical-reference`. The REA build is a prerelease of
  the environment commands proposed upstream in morluto/rea#4954, #4955, #4975 and #{{EXPORT_PR}}; the bundle installs it
  from the tarball it ships, so the environment runs without waiting for an npm release.

## What replay means, and does not

A tool call returns the recorded response whose path and query values best match the arguments, with
`replay.exact_match` telling you whether it matched exactly or fell back to the closest record. Reads of seeded objects
behave like the application. Writes return the recorded answer of the one write the session made, and the environment
has no state: a created object does not appear in a later list. This is what makes retrieval tasks hard-gradable and
write tasks weak; the manifest's `unknowns` say so.

## Tasks and grading

{{TASK_TABLE}}

## Episodes

{{MODEL_BOARD}}

{{EPISODE_NOTES}}

## Run it yourself

```bash
uv tool install agentenv-framework --with 'agentenv-hf @ git+https://github.com/earakely-scale/agentenv-hf-plugin@v0.3.0'
agent-env hf run earakely-scale/{{REPO_NAME}} --bundle {{ENV_ID}} --task smoke          # Docker, no model
agent-env hf run earakely-scale/{{REPO_NAME}} --bundle {{ENV_ID}} --eval {{ENV_ID}}-retrieval --model openai/gpt-oss-120b:groq
```

The retrieval eval needs a model endpoint: set `[model] base_url` and `api_key` in `.agentenv/config.toml` (the Hugging
Face router works with any `hf_` token). The bundle's `agents/replay-qa` is a small OpenAI-compatible tool-calling agent;
any A2A agent can replace it.

## How it was made

1. {{APP_NAME}} ran in Docker on a throwaway VM, bound to loopback, seeded through its own API with synthetic records
   ({{SEEDED_OBJECTS}}); people and projects are invented.
2. Playwright drove a login, the main pages and a scripted read, write, read sequence through the app's JSON API; the
   HAR was scoped to the API, the login exchange dropped, secret-looking body fields scrubbed, headers and cookies removed.
3. `rea inspect-web-network-capture` retained the exchanges as Evidence; `rea inspect-analysis-view` projected the
   `environment-manifest` view; `rea environment-export` wrote this bundle; `gen_tasks.py` derived the retrieval tasks
   from the manifest and the recorded bodies; `agent-env run` recorded the episodes; `agent-env hf publish` wrote this
   dataset. Scripts: https://github.com/earakely-scale/rea-environments.

## Compared with PortSimEnv on AgentEnv

| | PortSimEnv-AgentEnv | {{APP_TITLE}} (this dataset) |
|---|---|---|
| Environment | A simulation: a container quay, ships, cranes, weather, with A2A ship agents | A replay of a real application's API, captured from one session |
| Observation | Tool results computed by the simulator as the week unfolds | Recorded responses, cited to Evidence |
| Action space | Planning tools (`check_plan`, `confirm_berths`, `advance`, `message_agent`) | {{TOOL_COUNT}} tools mirroring the application's endpoints |
| State | Full: a virtual clock, triggers, frozen windows, agents that answer | None: every call is independent; writes replay one recorded answer |
| Reward | Deterministic, against a CP-SAT optimum or a re-planner anchor; continuous 0 to 1 | Deterministic, recorded-value match; 0 or 1 per task |
| What it measures | Planning under uncertainty and negotiation | Tool discovery, parameter inference and faithful retrieval in a real API |
| Data provenance | Real 2024 port calls and weather; simulated workloads | Synthetic seed data on a self-hosted {{APP_NAME}}; nothing real |
| How it was built | Hand-written plugin, months of work | Generated from a capture in one scripted pass |
| Where it is strong | Long-horizon decisions with hard rewards | Breadth: any app you can capture becomes an environment |

The two are complementary: PortSimEnv shows what a hand-built simulation can grade; this dataset shows how far a capture
alone gets you, and the manifest's `unknowns` list exactly what a stateful version would still have to specify.

## Licence and credits

Bundle code and tasks: Apache-2.0. Recorded content: responses generated by a self-hosted {{APP_NAME}} instance over
synthetic data; {{APP_NAME}} is {{APP_LICENSE}} software by {{APP_AUTHORS}} and is not redistributed here beyond the
recorded JSON responses. REA is MIT software by morluto; AgentEnv Framework is Apache-2.0 by Scale AI.
