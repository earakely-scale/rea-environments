# Capture contract for the showcase apps (binding for the capture agents)

VM: see showcase/vm/vm.env (IID, IP, PEM). ssh: `ssh -i $PEM -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null ubuntu@$IP`.
On the VM: Docker + compose, Node 24, `rea` 6.6.0 build with the environment-manifest view (global), ~/capture with
playwright-core 1.58.2, Chromium at the path provisioning reported, python3. Never print the PEM or any token.

## Per-app ownership (ports on 127.0.0.1 only, never 0.0.0.0; one compose project per app)
| app | compose project | host port | image |
|---|---|---|---|
| grafana | rea-grafana | 3101 | grafana/grafana:latest |
| gitea | rea-gitea | 3102 | gitea/gitea:latest (sqlite) |
| nocodb | rea-nocodb | 3103 | nocodb/nocodb:latest (sqlite) |
| mattermost | rea-mattermost | 3104 | mattermost/mattermost-team-edition:latest + postgres:16-alpine |
| ghost | rea-ghost | 3105 | ghost:5-alpine (sqlite, url http://127.0.0.1:3105) |

## Steps (all scripted, idempotent, under ~/capture/<app>/ on the VM)
1. compose.yml binding only 127.0.0.1:<port>; `docker compose -p <project> up -d`; wait for the app's health/readiness URL.
2. seed.sh or seed.py: create the throwaway admin (user `rea-admin`, password generated at run time, kept only in a 600
   file ~/capture/<app>/.admin, never in the HAR, never in any report) and SYNTHETIC content with fixed names, enough for
   10-12 later retrieval questions: e.g. Gitea: 2 users, 2 repos, 4 issues, 2 labels, 1 milestone, 2 comments; NocoDB: 1 base,
   2 tables, 8 rows; Mattermost: 1 team, 3 channels, 2 users, 12 posts, 1 reaction; Ghost: 4 posts (2 published, 1 draft, 1
   page), 2 tags, 1 member; Grafana: 1 folder, 2 dashboards, 1 datasource, 1 team, 1 extra user, 2 annotations. Content must be
   obviously synthetic: project names like "Lighthouse Rota", "Granite Ledger", "Blue Heron Kitchen", people like "Ada Finch",
   "Rui Castellanos". Do not name any proprietary delivery format or internal infrastructure.
3. capture.mjs (playwright-core, channel-less `chromium.launch({ executablePath })`, `recordHar: {content: "embed", mode: "full"}`):
   log in through the UI, visit the main pages, then run a scripted sequence from inside the page with `fetch` against the
   app's own JSON API: list collections, read each seeded object by id, 1-2 searches with query parameters, one create, one
   update, one delete of a scratch object, and re-reads. Keep the API record count between 60 and 140 and avoid endpoints with
   huge bodies (plugin catalogs, asset bundles). Print the HAR path.
4. Scope and scrub with ~/capture/scope_har.py (shipped from showcase/tools/scope_har.py): `--origin http://127.0.0.1:<port>`;
   add `--keep-regex` for the app's API prefix (Ghost: ^/ghost/api/; Mattermost: ^/api/v4/; Gitea: ^/api/v1/; NocoDB: ^/api/;
   Grafana: ^/api/|^/apis/). Check the summary: kept 60-140, methods include GET and at least one POST/PUT/PATCH/DELETE.
   Then grep the scoped HAR for the admin password and any `hf_`/`ghp_`/`Bearer ` tokens: zero hits required.
5. rea: `rea inspect-web-network-capture /abs/<app>.scoped.har har --format json > <app>.capture.json` then
   `rea inspect-analysis-view req.json --format json > <app>.manifest.json` where req.json is
   {"source":{"kind":"inline","evidence":<capture.json>},"view":{"kind":"environment-manifest","template_rules":["after-uid-literal","opaque-token","sibling-variance"]}}.
   If the view returns resource_constraint, lower --max-records / --max-body and redo from step 4. Also run the view WITHOUT
   template_rules and save <app>.manifest.norules.json for the card's comparison.
6. summary.json: tools (count, by method), params by rule, query names count, excluded groups by reason, unknowns, confidence,
   evidence ids (capture + manifest view), scoped HAR sha256 and byte size, record count, the admin-free check result, app image
   digest, app version string from its API.
7. `docker compose -p <project> down -v`; remove the HAR with bodies that was NOT scoped (keep only the scoped one), remove .admin.
8. scp back to the laptop: showcase/apps/<app>/{compose.yml,seed.*,capture.mjs,<app>.scoped.har,<app>.capture.json,<app>.manifest.json,<app>.manifest.norules.json,summary.json,README-notes.md}.

## Hard rules
- Everything is synthetic; no real names, emails of real people, or external services. Apps bind to loopback only.
- Never name proprietary delivery formats or internal infrastructure; never write issue-tracker ids; never print secrets; no credentials in HARs (verify by grep).
- Keep per-app total under ~12 MB of artefacts. Record exact versions. Report precisely; never claim a check you did not run.
