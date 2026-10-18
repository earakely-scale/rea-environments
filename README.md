# REA Environments

Twenty-nine RL environments for the [AgentEnv Framework](https://www.agentenvframework.com), each generated from one
recorded browser session against a self-hosted open-source application with [REA](https://github.com/morluto/rea): REA
turns the capture into an **environment manifest** (the application's tool surface, with every parameter labelled by the
rule that inferred it and every unknown stated), and `rea environment-export` writes an agentenv bundle that replays the
recorded exchanges, cites the Evidence behind each answer and executes nothing. Tasks are retrieval questions graded
deterministically against the recorded values. Everything here is synthetic data on throwaway instances.

All of them are in the Hub collection
[REA Environments on AgentEnv](https://huggingface.co/collections/earakely-scale/rea-environments-on-agentenv-6ad48fc54339527205162f82).
The first five (Ghost, Gitea, Grafana, Mattermost, NocoDB) were built one at a time; the other twenty-four were built
in one batch, three applications per VM on eight VMs, with the same tools.

| environment | application | licence | tools | recorded exchanges | `gpt-oss-120b:groq` | `GLM-5.3-Flash:zai-org` | dataset |
|---|---|---|---|---|---|---|---|
| baserow | Baserow 2.4.1 | MIT | 31 | 83 | 12 / 12 | 12 / 12 | [BaserowEnv-REA](https://huggingface.co/datasets/earakely-scale/BaserowEnv-REA) |
| bookstack | BookStack 26.09.1 | MIT | 31 | 65 | 12 / 12 | 12 / 12 | [BookStackEnv-REA](https://huggingface.co/datasets/earakely-scale/BookStackEnv-REA) |
| directus | Directus 11.17.4 | BSL-1.1 | 43 | 90 | 12 / 12 | 12 / 12 | [DirectusEnv-REA](https://huggingface.co/datasets/earakely-scale/DirectusEnv-REA) |
| espocrm | EspoCRM 10.0.10 | AGPL-3.0 | 88 | 131 | 12 / 12 | 12 / 12 | [EspoCRMEnv-REA](https://huggingface.co/datasets/earakely-scale/EspoCRMEnv-REA) |
| ghost | Ghost 5.130 | MIT | 36 | 76 | 12 / 12 | 12 / 12 | [GhostEnv-REA](https://huggingface.co/datasets/earakely-scale/GhostEnv-REA) |
| gitea | Gitea 28.1.0 | MIT | 77 | 97 | 12 / 12 | 11 / 12 | [GiteaEnv-REA](https://huggingface.co/datasets/earakely-scale/GiteaEnv-REA) |
| grafana | Grafana 13.2.4 | AGPL-3.0 | 48 | 105 | 12 / 12 | 12 / 12 | [GrafanaEnv-REA](https://huggingface.co/datasets/earakely-scale/GrafanaEnv-REA) |
| grist | Grist 1.7.21 | Apache-2.0 | 31 | 65 | 11 / 12 | 12 / 12 | [GristEnv-REA](https://huggingface.co/datasets/earakely-scale/GristEnv-REA) |
| grocy | Grocy 4.7.1 | MIT | 45 | 75 | 11 / 12 | 12 / 12 | [GrocyEnv-REA](https://huggingface.co/datasets/earakely-scale/GrocyEnv-REA) |
| homebox | Homebox 0.27.0 | AGPL-3.0 | 28 | 91 | 10 / 10 | 10 / 10 | [HomeboxEnv-REA](https://huggingface.co/datasets/earakely-scale/HomeboxEnv-REA) |
| immich | Immich 3.3.3 | AGPL-3.0 | 45 | 120 | 12 / 12 | 12 / 12 | [ImmichEnv-REA](https://huggingface.co/datasets/earakely-scale/ImmichEnv-REA) |
| jellyfin | Jellyfin 10.10.7 | GPL-2.0 | 34 | 72 | 12 / 12 | 12 / 12 | [JellyfinEnv-REA](https://huggingface.co/datasets/earakely-scale/JellyfinEnv-REA) |
| keycloak | Keycloak 26.8.1 | Apache-2.0 | 40 | 73 | 12 / 12 | 12 / 12 | [KeycloakEnv-REA](https://huggingface.co/datasets/earakely-scale/KeycloakEnv-REA) |
| komga | Komga 1.29.1 | MIT | 42 | 116 | 11 / 12 | 11 / 12 | [KomgaEnv-REA](https://huggingface.co/datasets/earakely-scale/KomgaEnv-REA) |
| linkding | linkding 1.47.0 | MIT | 23 | 64 | 11 / 12 | 12 / 12 | [LinkdingEnv-REA](https://huggingface.co/datasets/earakely-scale/LinkdingEnv-REA) |
| listmonk | listmonk 6.2 | AGPL-3.0 | 29 | 68 | 12 / 12 | 12 / 12 | [ListmonkEnv-REA](https://huggingface.co/datasets/earakely-scale/ListmonkEnv-REA) |
| mattermost | Mattermost Team Edition 12.0.0 | Mattermost licences | 37 | 129 | 11 / 12 | 12 / 12 | [MattermostEnv-REA](https://huggingface.co/datasets/earakely-scale/MattermostEnv-REA) |
| mealie | Mealie 3.28 | AGPL-3.0 | 39 | 139 | 12 / 12 | 12 / 12 | [MealieEnv-REA](https://huggingface.co/datasets/earakely-scale/MealieEnv-REA) |
| memos | Memos 0.31.0 | MIT | 26 | 67 | 12 / 12 | 12 / 12 | [MemosEnv-REA](https://huggingface.co/datasets/earakely-scale/MemosEnv-REA) |
| metabase | Metabase 0.64.2.8 | AGPL-3.0 | 42 | 120 | 12 / 12 | 12 / 12 | [MetabaseEnv-REA](https://huggingface.co/datasets/earakely-scale/MetabaseEnv-REA) |
| miniflux | Miniflux 2.3.3 | Apache-2.0 | 22 | 86 | 7 / 7 | 7 / 7 | [MinifluxEnv-REA](https://huggingface.co/datasets/earakely-scale/MinifluxEnv-REA) |
| n8n | n8n 1.123.85 | Sustainable Use License | 30 | 72 | 9 / 9 | 9 / 9 | [N8nEnv-REA](https://huggingface.co/datasets/earakely-scale/N8nEnv-REA) |
| navidrome | Navidrome 0.64.2 | GPL-3.0 | 25 | 71 | 12 / 12 | 12 / 12 | [NavidromeEnv-REA](https://huggingface.co/datasets/earakely-scale/NavidromeEnv-REA) |
| nocodb | NocoDB 2026.09.1 | AGPL-3.0 | 28 | 105 | 12 / 12 | 12 / 12 | [NocoDBEnv-REA](https://huggingface.co/datasets/earakely-scale/NocoDBEnv-REA) |
| paperless | Paperless-ngx 2.20 | GPL-3.0 | 41 | 108 | 12 / 12 | 12 / 12 | [PaperlessNgxEnv-REA](https://huggingface.co/datasets/earakely-scale/PaperlessNgxEnv-REA) |
| shlink | Shlink 5.1.7 | MIT | 17 | 66 | 7 / 7 | 7 / 7 | [ShlinkEnv-REA](https://huggingface.co/datasets/earakely-scale/ShlinkEnv-REA) |
| sonarr | Sonarr 4.0.20.3014 | GPL-3.0 | 48 | 98 | 12 / 12 | 12 / 12 | [SonarrEnv-REA](https://huggingface.co/datasets/earakely-scale/SonarrEnv-REA) |
| umami | Umami 3.4 | MIT | 49 | 100 | 11 / 12 | 12 / 12 | [UmamiEnv-REA](https://huggingface.co/datasets/earakely-scale/UmamiEnv-REA) |
| vikunja | Vikunja 2.7 | AGPL-3.0-or-later | 28 | 102 | 12 / 12 | 12 / 12 | [VikunjaEnv-REA](https://huggingface.co/datasets/earakely-scale/VikunjaEnv-REA) |

Across the 29 manifests: 1,103 tools over 2,654 recorded exchanges.

Each dataset holds the bundle, its tasks, the recorded episodes with chat transcripts, and a card that documents the
capture, the manifest, what replay means and does not, the grading, and a comparison with
[PortSimEnv on AgentEnv](https://huggingface.co/datasets/earakely-scale/PortSimEnv-AgentEnv), a hand-built simulation
environment on the same framework. Run one with the [agentenv-hf](https://github.com/earakely-scale/agentenv-hf-plugin) plugin:

```bash
uv tool install agentenv-framework --with 'agentenv-hf @ git+https://github.com/earakely-scale/agentenv-hf-plugin@v0.3.0'
agent-env hf run earakely-scale/KeycloakEnv-REA --bundle keycloak --task smoke
agent-env hf run earakely-scale/KeycloakEnv-REA --bundle keycloak --eval keycloak-retrieval --model openai/gpt-oss-120b:groq
```

The eval needs a model endpoint: set `[model] base_url` and `api_key` in `.agentenv/config.toml` (the Hugging Face
router at `https://router.huggingface.co/v1` works with any `hf_` token; `tools/probe_models.py` checks which
model:provider pairs accept tool calls with yours).

## Results

Every task was run once per model through the Hugging Face router with the bundle's `replay-qa` agent. Reward is 1 when
the response contains the recorded value, else 0; there is no judge. Totals over 333 tasks: `openai/gpt-oss-120b:groq`
327, `zai-org/GLM-5.3-Flash:zai-org` 331.

Each card explains its misses. In the first five, gpt-oss called a Mattermost tool name that does not exist and the
provider rejected the call, and GLM answered a Gitea commit question with another value. In the batch:

- **Malformed tool calls**: on Grist and linkding, the provider rejected a tool call gpt-oss generated (HTTP 400), so
  the episode ended without an answer.
- **Different values**: gpt-oss answered one Grocy and one Umami question with a value other than the recorded one.
- **An ambiguous task**: Komga's `qa-11` asks for the book after a given one, but the recorded exchange is the "next
  book" within a read list and the question does not name the list. Both models called the book-level tool and gave
  that answer. The generated question is at fault, not the models.

Most applications have 12 tasks. Homebox has 10, n8n 9, and Miniflux and Shlink 7, because the generator keeps only
distinctive seeded values (below) and those captures had fewer.

## How an environment is made

1. **Run and seed** the application in Docker, bound to loopback, through its own API (`apps/<app>/compose.yml`,
   `seed.*`): invented projects, people and records.
2. **Capture** one browser session with Playwright (`apps/<app>/capture.mjs`): log in, visit the main pages, run a
   scripted read, write, read sequence against the application's JSON API; record a HAR with bodies.
3. **Scope and scrub** the HAR to the API (`tools/scope_har.py`): drop assets and the login exchange, scrub
   secret-looking fields in request and response bodies, strip headers and cookies, keep empty-body replies such as a
   204 on DELETE.
4. **REA**: `rea inspect-web-network-capture` retains the exchanges as Evidence; `rea inspect-analysis-view` with
   `view.kind = "environment-manifest"` projects the manifest (`apps/<app>/manifest.json`), with the opt-in rules
   `after-uid-literal`, `opaque-token` and `sibling-variance` labelled per parameter; `rea environment-export` writes the
   bundle with a Dockerfile, the manifest, the Evidence, a verifier and a smoke task.
5. **Tasks**: `tools/gen_tasks.py` derives natural-language retrieval questions from the manifest and the recorded
   bodies, each graded by `agent_prompt_response_verifier` on the recorded value. An answer must be a distinctive value
   that occurs in the app's seed and capture inputs, not the admin account, in a bounded number of responses, and
   unique across the tasks. `agent/replay-qa` is a small OpenAI-compatible tool-calling A2A agent that plays them
   through any model endpoint.
6. **Record and publish**: `agent-env run` records the episodes; `agent-env hf publish` writes the dataset;
   `tools/make_card.py` fills `cards/TEMPLATE.md`. `tools/envbuild.py` runs steps 4 to 6 for one application on a
   VM, with a credential check on the scoped HAR before anything is built.

`apps/<app>/README-notes.md` records each application's versions, digests, seed, capture and numbers.

The REA environment commands are proposed upstream in morluto/rea#4954 (merged), #4955, #4975 and #4999 (design
discussion morluto/rea#4933); until they ship in a release, each bundle installs the prerelease build from the tarball it
carries.

## What the captures showed

`apps/SUMMARY.json` has the numbers per application. With the four format rules alone the 29 manifests would have 1,282
tools; the opt-in rules bring that to 1,103 by templating identifiers the format rules leave literal. In the batch,
`sibling-variance` templated parameters in Grist, Komga, Mealie, Memos, n8n, Navidrome and Shlink, and `opaque-token`
in EspoCRM; everything else was numeric ids or UUIDs. Some opaque ids stay literal in tool names, such as Komga's
read-list routes, which is what makes its `qa-11` question ambiguous.

## Corrections

- **Ghost v0.1.1**: the first Ghost capture kept the API key secrets of the throwaway instance's built-in integrations
  in one response body, because the scope tool then scrubbed request bodies only. The instance no longer exists. The
  scope tool now scrubs response bodies too, and Ghost was rebuilt and republished as v0.1.1.
- **Umami**: a check on response bodies caught the session token that `GET /api/me` returns before Umami was
  published, and that exchange was dropped.

## Licence

Code in this repository: Apache-2.0. Recorded content in the datasets: responses generated by self-hosted instances over
synthetic data; the applications remain under their own licences and are not redistributed here: Baserow MIT, BookStack MIT, Directus BSL-1.1, EspoCRM AGPL-3.0, Ghost MIT, Gitea MIT, Grafana AGPL-3.0, Grist Apache-2.0, Grocy MIT, Homebox AGPL-3.0, Immich AGPL-3.0, Jellyfin GPL-2.0, Keycloak Apache-2.0, Komga MIT, Mealie AGPL-3.0, Memos MIT, Metabase AGPL-3.0, Miniflux Apache-2.0, Navidrome GPL-3.0, NocoDB AGPL-3.0, Paperless-ngx GPL-3.0, Shlink MIT, Sonarr GPL-3.0, Umami MIT, Vikunja AGPL-3.0-or-later, linkding MIT, listmonk AGPL-3.0, n8n Sustainable Use License 1.0 (fair-code; .ee files under the n8n Enterprise License),
and Mattermost Team Edition under the Mattermost licences.
