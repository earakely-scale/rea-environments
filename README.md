# REA Environments

Forty-four RL environments for the [AgentEnv Framework](https://www.agentenvframework.com), each generated from one
recorded browser session with [REA](https://github.com/morluto/rea): REA turns the capture into an **environment
manifest** (the API's tool surface, with every parameter labelled by the rule that inferred it and every unknown stated),
and `rea environment-export` writes an agentenv bundle that replays the recorded exchanges, cites the Evidence behind
each answer and executes nothing. Tasks are retrieval questions graded deterministically against the recorded values.

There are two kinds:

- **Self-hosted** (37): an open-source or source-available application run on a throwaway VM and seeded with invented
  data, so nothing recorded is real.
- **Public API** (7): six U.S. government APIs and the Art Institute of Chicago's collection API, recorded live with no
  key or login within each publisher's access rules. The data is real (public domain or CC0), frozen as it was served on
  the capture date.

Thirty-nine were captured as HARs with Playwright. The five newest (Lychee, PhotoPrism, Pinry, the Art Institute of
Chicago and the Library of Congress) were captured by REA itself with `rea capture-browser-scenario`, with no HAR or
scrubbing step; see [CAPTURE-SCENARIO.md](CAPTURE-SCENARIO.md).

All of them are in the Hub collection
[REA Environments on AgentEnv](https://huggingface.co/collections/earakely-scale/rea-environments-on-agentenv-6ad48fc54339527205162f82),
and the [overview Space](https://huggingface.co/spaces/earakely-scale/rea-environments) has a diagram of the pipeline,
baseline results and a filterable gallery of all forty-four.

| environment | kind | capture | application | licence | tools | recorded exchanges | `gpt-oss-120b:groq` | `GLM-5.3-Flash:zai-org` | dataset |
|---|---|---|---|---|---|---|---|---|---|
| airbyte | self-hosted | HAR | Airbyte 2.4.0 | Elastic License 2.0 | 25 | 64 | 11 / 11 | 11 / 11 | [AirbyteEnv-REA](https://huggingface.co/datasets/earakely-scale/AirbyteEnv-REA) |
| artic-collection | public API | scenario | Art Institute of Chicago API | CC0 1.0 | 11 | 26 | 11 / 12 | 12 / 12 | [ArticCollectionEnv-REA](https://huggingface.co/datasets/earakely-scale/ArticCollectionEnv-REA) |
| baserow | self-hosted | HAR | Baserow 2.4.1 | MIT | 31 | 83 | 12 / 12 | 12 / 12 | [BaserowEnv-REA](https://huggingface.co/datasets/earakely-scale/BaserowEnv-REA) |
| bookstack | self-hosted | HAR | BookStack 26.09.1 | MIT | 31 | 65 | 12 / 12 | 12 / 12 | [BookStackEnv-REA](https://huggingface.co/datasets/earakely-scale/BookStackEnv-REA) |
| directus | self-hosted | HAR | Directus 11.17.4 | BSL-1.1 | 43 | 90 | 12 / 12 | 12 / 12 | [DirectusEnv-REA](https://huggingface.co/datasets/earakely-scale/DirectusEnv-REA) |
| espocrm | self-hosted | HAR | EspoCRM 10.0.10 | AGPL-3.0 | 88 | 131 | 12 / 12 | 12 / 12 | [EspoCRMEnv-REA](https://huggingface.co/datasets/earakely-scale/EspoCRMEnv-REA) |
| federal-register | public API | HAR | Federal Register API | U.S. public domain | 10 | 52 | 9 / 10 | 9 / 10 | [FederalRegisterEnv-REA](https://huggingface.co/datasets/earakely-scale/FederalRegisterEnv-REA) |
| ghost | self-hosted | HAR | Ghost 5.130 | MIT | 36 | 76 | 12 / 12 | 12 / 12 | [GhostEnv-REA](https://huggingface.co/datasets/earakely-scale/GhostEnv-REA) |
| gitea | self-hosted | HAR | Gitea 28.1.0 | MIT | 77 | 97 | 12 / 12 | 11 / 12 | [GiteaEnv-REA](https://huggingface.co/datasets/earakely-scale/GiteaEnv-REA) |
| grafana | self-hosted | HAR | Grafana 13.2.4 | AGPL-3.0 | 48 | 105 | 12 / 12 | 12 / 12 | [GrafanaEnv-REA](https://huggingface.co/datasets/earakely-scale/GrafanaEnv-REA) |
| grist | self-hosted | HAR | Grist 1.7.21 | Apache-2.0 | 31 | 65 | 11 / 12 | 12 / 12 | [GristEnv-REA](https://huggingface.co/datasets/earakely-scale/GristEnv-REA) |
| grocy | self-hosted | HAR | Grocy 4.7.1 | MIT | 45 | 75 | 11 / 12 | 12 / 12 | [GrocyEnv-REA](https://huggingface.co/datasets/earakely-scale/GrocyEnv-REA) |
| homebox | self-hosted | HAR | Homebox 0.27.0 | AGPL-3.0 | 28 | 91 | 10 / 10 | 10 / 10 | [HomeboxEnv-REA](https://huggingface.co/datasets/earakely-scale/HomeboxEnv-REA) |
| immich | self-hosted | HAR | Immich 3.3.3 | AGPL-3.0 | 45 | 120 | 12 / 12 | 12 / 12 | [ImmichEnv-REA](https://huggingface.co/datasets/earakely-scale/ImmichEnv-REA) |
| jellyfin | self-hosted | HAR | Jellyfin 10.10.7 | GPL-2.0 | 34 | 72 | 12 / 12 | 12 / 12 | [JellyfinEnv-REA](https://huggingface.co/datasets/earakely-scale/JellyfinEnv-REA) |
| keycloak | self-hosted | HAR | Keycloak 26.8.1 | Apache-2.0 | 40 | 73 | 12 / 12 | 12 / 12 | [KeycloakEnv-REA](https://huggingface.co/datasets/earakely-scale/KeycloakEnv-REA) |
| komga | self-hosted | HAR | Komga 1.29.1 | MIT | 42 | 116 | 11 / 12 | 11 / 12 | [KomgaEnv-REA](https://huggingface.co/datasets/earakely-scale/KomgaEnv-REA) |
| linkding | self-hosted | HAR | linkding 1.47.0 | MIT | 23 | 64 | 11 / 12 | 12 / 12 | [LinkdingEnv-REA](https://huggingface.co/datasets/earakely-scale/LinkdingEnv-REA) |
| listmonk | self-hosted | HAR | listmonk 6.2 | AGPL-3.0 | 29 | 68 | 12 / 12 | 12 / 12 | [ListmonkEnv-REA](https://huggingface.co/datasets/earakely-scale/ListmonkEnv-REA) |
| loc-photos | public API | scenario | Library of Congress JSON API (photos) | U.S. public domain | 11 | 29 | 11 / 12 | 12 / 12 | [LocPhotosEnv-REA](https://huggingface.co/datasets/earakely-scale/LocPhotosEnv-REA) |
| lychee | self-hosted | scenario | Lychee 6.10.4 | MIT | 15 | 134 | 11 / 12 | 12 / 12 | [LycheeEnv-REA](https://huggingface.co/datasets/earakely-scale/LycheeEnv-REA) |
| mattermost | self-hosted | HAR | Mattermost Team Edition 12.0.0 | Mattermost licences | 37 | 129 | 11 / 12 | 12 / 12 | [MattermostEnv-REA](https://huggingface.co/datasets/earakely-scale/MattermostEnv-REA) |
| mealie | self-hosted | HAR | Mealie 3.28 | AGPL-3.0 | 39 | 139 | 12 / 12 | 12 / 12 | [MealieEnv-REA](https://huggingface.co/datasets/earakely-scale/MealieEnv-REA) |
| memos | self-hosted | HAR | Memos 0.31.0 | MIT | 26 | 67 | 12 / 12 | 12 / 12 | [MemosEnv-REA](https://huggingface.co/datasets/earakely-scale/MemosEnv-REA) |
| metabase | self-hosted | HAR | Metabase 0.64.2.8 | AGPL-3.0 | 42 | 120 | 12 / 12 | 12 / 12 | [MetabaseEnv-REA](https://huggingface.co/datasets/earakely-scale/MetabaseEnv-REA) |
| miniflux | self-hosted | HAR | Miniflux 2.3.3 | Apache-2.0 | 22 | 86 | 7 / 7 | 7 / 7 | [MinifluxEnv-REA](https://huggingface.co/datasets/earakely-scale/MinifluxEnv-REA) |
| n8n | self-hosted | HAR | n8n 1.123.85 | Sustainable Use License | 30 | 72 | 9 / 9 | 9 / 9 | [N8nEnv-REA](https://huggingface.co/datasets/earakely-scale/N8nEnv-REA) |
| navidrome | self-hosted | HAR | Navidrome 0.64.2 | GPL-3.0 | 25 | 71 | 12 / 12 | 12 / 12 | [NavidromeEnv-REA](https://huggingface.co/datasets/earakely-scale/NavidromeEnv-REA) |
| noaa-tides | public API | HAR | NOAA Tides and Currents API | U.S. public domain | 12 | 56 | 9 / 9 | 9 / 9 | [NoaaTidesEnv-REA](https://huggingface.co/datasets/earakely-scale/NoaaTidesEnv-REA) |
| nocodb | self-hosted | HAR | NocoDB 2026.09.1 | AGPL-3.0 | 28 | 105 | 12 / 12 | 12 / 12 | [NocoDBEnv-REA](https://huggingface.co/datasets/earakely-scale/NocoDBEnv-REA) |
| nomad | self-hosted | HAR | HashiCorp Nomad 1.11.3 | BUSL-1.1 | 39 | 131 | 12 / 12 | 12 / 12 | [NomadEnv-REA](https://huggingface.co/datasets/earakely-scale/NomadEnv-REA) |
| openfda | public API | HAR | openFDA | U.S. public domain | 9 | 53 | 12 / 12 | 12 / 12 | [OpenFdaEnv-REA](https://huggingface.co/datasets/earakely-scale/OpenFdaEnv-REA) |
| paperless | self-hosted | HAR | Paperless-ngx 2.20 | GPL-3.0 | 41 | 108 | 12 / 12 | 12 / 12 | [PaperlessNgxEnv-REA](https://huggingface.co/datasets/earakely-scale/PaperlessNgxEnv-REA) |
| photoprism | self-hosted | scenario | PhotoPrism 261007 | AGPL-3.0 | 13 | 277 | 10 / 10 | 10 / 10 | [PhotoPrismEnv-REA](https://huggingface.co/datasets/earakely-scale/PhotoPrismEnv-REA) |
| pinry | self-hosted | scenario | Pinry 2.1.13 | BSD-2-Clause | 12 | 568 | 6 / 6 | 6 / 6 | [PinryEnv-REA](https://huggingface.co/datasets/earakely-scale/PinryEnv-REA) |
| redpanda-console | self-hosted | HAR | Redpanda Console 3.12.0 | BSL-1.1 | 37 | 87 | 8 / 8 | 8 / 8 | [RedpandaConsoleEnv-REA](https://huggingface.co/datasets/earakely-scale/RedpandaConsoleEnv-REA) |
| sentry | self-hosted | HAR | Sentry 26.9.0 | FSL-1.1-Apache-2.0 | 34 | 72 | 12 / 12 | 12 / 12 | [SentryEnv-REA](https://huggingface.co/datasets/earakely-scale/SentryEnv-REA) |
| shlink | self-hosted | HAR | Shlink 5.1.7 | MIT | 17 | 66 | 7 / 7 | 7 / 7 | [ShlinkEnv-REA](https://huggingface.co/datasets/earakely-scale/ShlinkEnv-REA) |
| sonarr | self-hosted | HAR | Sonarr 4.0.20.3014 | GPL-3.0 | 48 | 98 | 12 / 12 | 12 / 12 | [SonarrEnv-REA](https://huggingface.co/datasets/earakely-scale/SonarrEnv-REA) |
| treasury-fiscal-data | public API | HAR | Treasury Fiscal Data API | U.S. public domain | 16 | 52 | 8 / 12 | 12 / 12 | [TreasuryFiscalDataEnv-REA](https://huggingface.co/datasets/earakely-scale/TreasuryFiscalDataEnv-REA) |
| umami | self-hosted | HAR | Umami 3.4 | MIT | 49 | 100 | 11 / 12 | 12 / 12 | [UmamiEnv-REA](https://huggingface.co/datasets/earakely-scale/UmamiEnv-REA) |
| usgs-earthquakes | public API | HAR | USGS Earthquake Catalog 2.8.1 | U.S. public domain | 10 | 53 | 7 / 7 | 7 / 7 | [UsgsEarthquakesEnv-REA](https://huggingface.co/datasets/earakely-scale/UsgsEarthquakesEnv-REA) |
| vault | self-hosted | HAR | HashiCorp Vault 1.21.4 | BUSL-1.1 | 43 | 85 | 11 / 12 | 12 / 12 | [VaultEnv-REA](https://huggingface.co/datasets/earakely-scale/VaultEnv-REA) |
| vikunja | self-hosted | HAR | Vikunja 2.7 | AGPL-3.0-or-later | 28 | 102 | 12 / 12 | 12 / 12 | [VikunjaEnv-REA](https://huggingface.co/datasets/earakely-scale/VikunjaEnv-REA) |

Across the 44 manifests: 1,400 tools over 4,393 recorded exchanges.

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
the response contains the recorded value, else 0; there is no judge. Totals over 490 tasks: `openai/gpt-oss-120b:groq`
475, `zai-org/GLM-5.3-Flash:zai-org` 487.

Each card explains its misses. Most are the model's: gpt-oss sometimes generates a tool call the provider rejects
(Mattermost, Grist, linkding, Vault, Lychee) or answers with another value (Grocy, Umami, Art Institute of Chicago), and GLM once answered a Gitea commit
question with another value. Some are the task generator's, and the cards blame the models for them:

- **Komga `qa-11`** asks for the book after a given one, but the recorded exchange is the "next book" within a read list
  and the question does not name the list. Both models called the book-level tool.
- **Federal Register `qa-01`**: the recorded title ends with a space, the models answered the trimmed title, and the
  match is literal.
- **Treasury Fiscal Data**: eight of its twelve tasks ask for a column label from the response's `meta` block rather than
  a value from the records, and such a question reads like one about the record itself. gpt-oss missed four of them.
- **Library of Congress `qa-04`**: as with Federal Register, the recorded caption ends with a space and the model's
  trimmed answer does not match literally.
- **Lychee `qa-01`** asks for the gallery title, which is text the application ships ("Lychee v6"), not seeded data;
  the seed check passed because the application's name appears in the seed script's paths.

Task counts differ (6 to 12) because the generator keeps only distinctive values and some captures had fewer.

## How an environment is made

1. **Self-hosted**: run and seed the application in Docker on a throwaway VM, bound to loopback, through its own API
   (`apps/<app>/compose.yml` or the vendor's installer, `seed.*`). **Public API**: no instance; the VM calls the API
   directly with a declared User-Agent, at most 2 requests per second and 150 requests in total.
2. **Capture** one browser session, in one of two ways. With Playwright (`apps/<app>/capture.mjs`): self-hosted, log
   in, visit the main pages, run a scripted read, write, read sequence against the JSON API; public API, open the API
   origin and run a scripted sequence of reads; record a HAR with bodies. Or with REA (`apps/<app>/scenario.json`):
   `rea capture-browser-scenario` drives Chromium through declared actions (navigate, click, fill, wait), starts signed
   in from storage seeds or signs in with declared secrets, redacts credential headers and declared secrets, and records
   every network transaction as Evidence. Writes come from the application's own forms.
3. **Scope and scrub** a HAR to the API (`tools/scope_har.py`): drop assets and the login exchange, scrub
   secret-looking fields in request and response bodies, strip headers and cookies, keep empty-body replies such as a
   204 on DELETE. A scenario capture skips this step: the manifest view excludes UI pages and assets itself.
4. **REA**: `rea inspect-web-network-capture` retains a HAR's exchanges as Evidence (a scenario capture already is); `rea inspect-analysis-view` with
   `view.kind = "environment-manifest"` projects the manifest (`apps/<app>/manifest.json`), with the opt-in rules
   `after-uid-literal`, `opaque-token` and `sibling-variance` labelled per parameter; `rea environment-export` writes the
   bundle with a Dockerfile, the manifest, the Evidence, a verifier and a smoke task.
5. **Tasks**: `tools/gen_tasks.py` derives natural-language retrieval questions from the manifest and the recorded
   bodies, each graded by `agent_prompt_response_verifier` on the recorded value. An answer must be a distinctive value,
   not the admin account, in a bounded number of responses, and unique across the tasks; for self-hosted apps it must
   also occur in the seed inputs. `agent/replay-qa` is a small OpenAI-compatible tool-calling A2A agent that plays them
   through any model endpoint.
6. **Record and publish**: `agent-env run` records the episodes; `agent-env hf publish` writes the dataset;
   `tools/make_card.py` fills `cards/TEMPLATE.md`, with wording for each kind. `tools/envbuild.py` runs steps 4 to 6 for
   one application on a VM, with a credential check on the scoped HAR or scenario capture before anything is built
   (`tools/credscan.py` runs the same check on its own; `tools/scenario_records.py` reads scenario Evidence the way the
   manifest view does).

`apps/<app>/README-notes.md` records each application's versions, digests, seed or endpoints, capture and numbers.
Every application has its inputs under `apps/` except Sentry; its row in `apps/SUMMARY.json` and its
[dataset](https://huggingface.co/datasets/earakely-scale/SentryEnv-REA) carry its numbers, manifest, bundle and card.

The REA environment commands are proposed upstream in morluto/rea#4954 (merged), #4955, #4975, #4999 and #5182
(scenario captures as manifest parents; design discussion morluto/rea#4933); until they ship in a release, each bundle installs the prerelease build from the tarball it
carries.

## What the captures showed

`apps/SUMMARY.json` has the numbers per application. With the four format rules alone the 44 manifests would have
1,692 tools; the opt-in rules bring that to 1,400 by templating identifiers the format rules leave literal. Some
opaque ids stay literal in tool names, such as Komga's read-list routes, which is what makes its `qa-11` question
ambiguous. REA's numeric rule also reads the version segment of Sentry's `/api/0/` as an id, so every Sentry tool carries
an `id` parameter.

Two public APIs were planned and not built. SEC EDGAR refuses requests whose User-Agent carries no contact email, and
the captures do not send anyone's address. The National Weather Service answers only GeoJSON and JSON-LD, which the task
generator skipped then. openFDA and NOAA Tides and Currents took their places. Among the scenario captures, The Met
Collection API projected only three tools, because its object ids merge into one templated tool, and the NASA Image
and Video Library's Collection+JSON bodies nest record fields deeper than the task generator reads. The Art Institute of
Chicago and the Library of Congress took their places.

The scenario captures also showed what to expect from `capture-browser-scenario` today: a scenario should end with a
short wait, or the response body of a write made by its last action can be lost; the response bodies a scenario keeps
cannot be chosen by media type, so CSS and JavaScript bodies count against the manifest view's budget (one Pinry capture
needed a 20,000-byte body limit); image responses are UI assets unless an API path serves them; and a redirect is its
own transaction, so Django's trailing-slash redirect gave Pinry two tools for one resource.

## Corrections

- **Ghost v0.1.1**: the first Ghost capture kept the API key secrets of the throwaway instance's built-in integrations
  in one response body, because the scope tool then scrubbed request bodies only. The instance no longer exists. The
  scope tool now scrubs response bodies too, and Ghost was rebuilt and republished as v0.1.1.
- **Umami**: a check on response bodies caught the session token that `GET /api/me` returns before Umami was
  published, and that exchange was dropped.

## Licence

Code in this repository: Apache-2.0. Recorded content in the datasets: for self-hosted environments, responses generated
by self-hosted instances over synthetic data; the applications remain under their own licences and are not
redistributed here: Airbyte Elastic License 2.0 (ELv2), Baserow MIT, BookStack MIT, Directus BSL-1.1, EspoCRM AGPL-3.0, Ghost MIT, Gitea MIT, Grafana AGPL-3.0, Grist Apache-2.0, Grocy MIT, HashiCorp Nomad BUSL-1.1, HashiCorp Vault BUSL-1.1, Homebox AGPL-3.0, Immich AGPL-3.0, Jellyfin GPL-2.0, Keycloak Apache-2.0, Komga MIT, Lychee MIT, Mealie AGPL-3.0, Memos MIT, Metabase AGPL-3.0, Miniflux Apache-2.0, Navidrome GPL-3.0, NocoDB AGPL-3.0, Paperless-ngx GPL-3.0, PhotoPrism AGPL-3.0, Pinry BSD-2-Clause, Redpanda Console BSL-1.1, Sentry FSL-1.1-Apache-2.0, Shlink MIT, Sonarr GPL-3.0, Umami MIT, Vikunja AGPL-3.0-or-later, linkding MIT, listmonk AGPL-3.0, n8n Sustainable Use License 1.0 (fair-code; .ee files under the n8n Enterprise License), and Mattermost Team Edition under the Mattermost licences. For public-API
environments, responses of public APIs published by the institution named on each card: U.S. government APIs (public
domain) and the Art Institute of Chicago's collection data (CC0 1.0).
