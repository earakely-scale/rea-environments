# REA Environments showcase: five RL environments on Hugging Face

Goal: use the rea stack (environment-manifest view, environment-serve, environment-export) to turn five open-source,
self-hosted applications into agentenv environments, record agent episodes, and publish each as a Hugging Face dataset
with agentenv-hf, documented to the standard of earakely-scale/PortSimEnv-AgentEnv and compared against it.

## Applications (all open source, self-hosted on a throwaway VM, synthetic seed data only)
| env | app | domain | image / arch | API surface captured |
|---|---|---|---|---|
| grafana | Grafana 13.2 | observability dashboards | grafana/grafana (arm64+amd64) | /api/* and /apis/*.grafana.app |
| gitea | Gitea | code hosting (GitHub-like) | gitea/gitea (multi-arch) | /api/v1/* |
| nocodb | NocoDB | spreadsheet-database (Airtable-like) | nocodb/nocodb (multi-arch) | /api/v1/db/* and /api/v2/* |
| mattermost | Mattermost Team Edition | team chat (Slack-like) | mattermost-team-edition (amd64 only) | /api/v4/* |
| ghost | Ghost 5 | publishing / CMS | ghost:5-alpine (multi-arch) | /ghost/api/admin/* |

## Infrastructure
- One EC2 VM in us-west-2, Ubuntu 24.04 amd64 (ami-07f3a2cfd03d8ee81), m6i.xlarge or larger,
  a public subnet, temporary key pair + SG (22 from the operator's address only),
  Docker + Node 24 + Chromium + playwright-core, agentenv-framework 0.9.1334 in a venv, the rea stack tarball from
  `npm pack` of feat/environment-export. Everything torn down at the end; secrets only as 600 files, removed before teardown.
- The laptop orchestrates (ssh/scp/aws) and holds the agentenv stores the publish reads from, or the VM holds them and the
  dataset folders come back by scp (`agent-env hf publish --out`).

## Pipeline per app (deterministic, scripted)
1. docker compose up; seed synthetic data through the app's API (users, projects, records, messages, posts) with fixed
   names; nothing personal, no real credentials beyond the throwaway admin.
2. Playwright (installed Chromium) logs in, visits the main pages, and issues a scripted read/write/read sequence through
   `fetch` from the page; HAR with bodies.
3. Scope: drop static assets and the login exchange; scrub secret-looking body fields; strip headers/cookies.
4. rea: `inspect-web-network-capture ... har` (chunked if the view budget demands) -> `inspect-analysis-view`
   environment-manifest with the three opt-in rules -> `environment-export --package-tarball`.
5. Add tasks: `tasks/smoke.json` (export's), plus 8-12 retrieval tasks per env: deploy_env + deploy_agent (bundle agent)
   + prompt_agent (question about recorded facts, prompt_id) + agent_prompt_response_verifier (response_contains /
   response_regex_present with the recorded value). Reward = deterministic, no judge. An `evals/<env>-eval.toml`
   listing the tasks.
6. Agent: `agents/replay-qa/` in the bundle: a small A2A agent (agentenv-framework-protocol[agent] + openai) that runs an
   OpenAI-compatible tool-calling loop over the env's MCP tools with a turn cap, modelled on PortSimEnv's portsim-llm
   but generic; model through agent-env's `[model]` endpoint (Hugging Face router, HF token as a local secret).
7. Run: `agent-env run <bundle>` for every task with one or two open models via the HF router; keep runs in the stores.
8. Publish: `agent-env hf publish <bundle> --repo earakely-scale/<App>Env-REA --license <app-appropriate> --card-note
   <card.md> --tag v0.1.0 --collection <REA Environments>`; card note written per env.

## Documentation contract (each dataset card, mirroring PortSimEnv's card structure)
- Hero: one sentence on the app and the capture; a replay example.
- What's in it: tools (count, by method), parameters (by rule), excluded groups, unknowns; the manifest's evidence ids and
  the capture's sha256; the rea version/stack used (prerelease build pending upstream PRs #4954/#4955/#4975/#49xx).
- What replay means and does not mean (honest limits: retrieval rewards well, writes replay recorded answers; no state).
- Tasks and grading (deterministic verifiers, reward 0/1 per task; eval aggregation).
- Episodes: which models, how many tool calls, pass rates (a small model board).
- How to run (`agent-env hf run earakely-scale/<App>Env-REA --bundle <env>`), prerequisites, model endpoint config.
- Comparison with PortSimEnv-AgentEnv: simulation vs capture replay; CP-SAT optimum grading vs recorded-fact grading;
  virtual clock/triggers/A2A ship agents vs stateless replay; what each is good for (planning vs tool-use/retrieval);
  table of observation space, action space, reward, state, determinism, data provenance, licence.
- Licence and credits: app licence (Grafana AGPL-3.0, Gitea MIT, NocoDB AGPL-3.0, Mattermost (team edition) MIT/Apache
  server, Ghost MIT), recorded content is synthetic data produced on our instances; bundle code Apache-2.0.
- Hard rule: no Scale-internal delivery formats or infrastructure named; no Linear ids.

## Public GitHub repo
earakely-scale/rea-environments (new, public, Apache-2.0): capture scripts per app, seeding, the pipeline runner, the
replay-qa agent source, task generators, cards, and a README that links the five datasets and the upstream rea PRs.
