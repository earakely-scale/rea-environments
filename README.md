# REA Environments

Five RL environments for the [AgentEnv Framework](https://www.agentenvframework.com), each generated from one recorded
browser session against a self-hosted open-source application with [REA](https://github.com/morluto/rea): REA turns the
capture into an **environment manifest** (the application's tool surface, with every parameter labelled by the rule that
inferred it and every unknown stated), and `rea environment-export` writes an agentenv bundle that replays the recorded
exchanges, cites the Evidence behind each answer and executes nothing. Tasks are retrieval questions graded
deterministically against the recorded values. Everything here is synthetic data on throwaway instances.

| environment | application | tools | recorded exchanges | dataset |
|---|---|---|---|---|
| grafana | Grafana 13.2.4 | 48 | 105 | [earakely-scale/GrafanaEnv-REA](https://huggingface.co/datasets/earakely-scale/GrafanaEnv-REA) |
| gitea | Gitea 28.1.0 | 77 | 97 | [earakely-scale/GiteaEnv-REA](https://huggingface.co/datasets/earakely-scale/GiteaEnv-REA) |
| nocodb | NocoDB 2026.09.1 | 28 | 105 | [earakely-scale/NocoDBEnv-REA](https://huggingface.co/datasets/earakely-scale/NocoDBEnv-REA) |
| mattermost | Mattermost Team Edition 12.0.0 | 37 | 129 | [earakely-scale/MattermostEnv-REA](https://huggingface.co/datasets/earakely-scale/MattermostEnv-REA) |
| ghost | Ghost 5.130 | 36 | 76 | [earakely-scale/GhostEnv-REA](https://huggingface.co/datasets/earakely-scale/GhostEnv-REA) |

All five are in the Hub collection
[REA Environments on AgentEnv](https://huggingface.co/collections/earakely-scale/rea-environments-on-agentenv-6ad48fc54339527205162f82).

Each dataset holds the bundle, its tasks, the recorded episodes with chat transcripts, and a card that documents the
capture, the manifest, what replay means and does not, the grading, and a comparison with
[PortSimEnv on AgentEnv](https://huggingface.co/datasets/earakely-scale/PortSimEnv-AgentEnv), a hand-built simulation
environment on the same framework. Run one with the [agentenv-hf](https://github.com/earakely-scale/agentenv-hf-plugin) plugin:

```bash
uv tool install agentenv-framework --with 'agentenv-hf @ git+https://github.com/earakely-scale/agentenv-hf-plugin@v0.3.0'
agent-env hf run earakely-scale/GhostEnv-REA --bundle ghost --task smoke
agent-env hf run earakely-scale/GhostEnv-REA --bundle ghost --eval ghost-retrieval --model openai/gpt-oss-120b:groq
```

The eval needs a model endpoint: set `[model] base_url` and `api_key` in `.agentenv/config.toml` (the Hugging Face
router at `https://router.huggingface.co/v1` works with any `hf_` token; `tools/probe_models.py` checks which
model:provider pairs accept tool calls with yours).

## Results

Each environment has 12 retrieval tasks; every task was run once per model through the Hugging Face router, with the
bundle's `replay-qa` agent (one tool call per question is the expected shape). Reward is 1 when the response contains
the recorded value, else 0; there is no judge.

| environment | `openai/gpt-oss-120b:groq` | `zai-org/GLM-5.3-Flash:zai-org` |
|---|---|---|
| grafana | 12 / 12 | 12 / 12 |
| gitea | 12 / 12 | 11 / 12 |
| nocodb | 12 / 12 | 12 / 12 |
| mattermost | 11 / 12 | 12 / 12 |
| ghost | 12 / 12 | 12 / 12 |
| **total** | **59 / 60** | **59 / 60** |

Both misses are model errors, not replay errors, and each card says which: on Mattermost, gpt-oss called a tool
named `get_users_teams_threads_by_uid_uid_3` that does not exist (the three-parameter route is
`get_users_teams_threads_by_uid_uid_2_uid`) and the provider rejected the call; on Gitea, GLM answered a commit
question with a value other than the recorded one. Generated names for routes with several same-rule parameters are
the hard part of these environments. Every episode, including the misses, is in the dataset with its transcript.

## How an environment is made

1. **Run and seed** the application in Docker, bound to loopback, through its own API (`apps/<app>/compose.yml`,
   `seed.*`): invented projects, people and records.
2. **Capture** one browser session with Playwright (`apps/<app>/capture.mjs`): log in, visit the main pages, run a
   scripted read, write, read sequence against the application's JSON API; record a HAR with bodies.
3. **Scope and scrub** the HAR to the API (`tools/scope_har.py`): drop assets and the login exchange, scrub
   secret-looking body fields, strip headers and cookies, keep empty-body replies such as a 204 on DELETE.
4. **REA**: `rea inspect-web-network-capture` retains the exchanges as Evidence; `rea inspect-analysis-view` with
   `view.kind = "environment-manifest"` projects the manifest (`apps/<app>/manifest.json`), with the opt-in rules
   `after-uid-literal`, `opaque-token` and `sibling-variance` labelled per parameter; `rea environment-export` writes the
   bundle with a Dockerfile, the manifest, the Evidence, a verifier and a smoke task.
5. **Tasks**: `tools/gen_tasks.py` derives natural-language retrieval questions from the manifest and the recorded
   bodies, each graded by `agent_prompt_response_verifier` on the recorded value; `agent/replay-qa` is a small
   OpenAI-compatible tool-calling A2A agent that plays them through any model endpoint.
6. **Record and publish**: `agent-env run` records the episodes; `agent-env hf publish` writes the dataset;
   `tools/make_card.py` fills `cards/TEMPLATE.md`.

The REA environment commands are proposed upstream in morluto/rea#4954, #4955, #4975 and #4999 (design discussion
morluto/rea#4933); until they ship in a release, each bundle installs the prerelease build from the tarball it carries.

## What the five captures showed

`apps/SUMMARY.json` has the numbers. Across the five applications, 226 tools over 512 recorded exchanges; REA's four
format rules templated the numeric ids of Gitea and Grafana, while the opaque identifiers of NocoDB, Mattermost and
Ghost needed the opt-in `opaque-token` rule; `sibling-variance` recovered Grafana's `/api/plugins/{plugin_id}/settings`
and folded a literal `me` alias into Mattermost's `{uid}`, which the cards call out. Owner and repository names stay
literal everywhere, as they should. Details per application are in `apps/<app>/README-notes.md`.

## Licence

Code in this repository: Apache-2.0. Recorded content in the datasets: responses generated by self-hosted instances over
synthetic data; the applications remain under their own licences (Grafana AGPL-3.0, Gitea MIT, NocoDB AGPL-3.0,
Mattermost Team Edition under the Mattermost licences, Ghost MIT) and are not redistributed here.
