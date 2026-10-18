# n8n 1.x capture notes (rea showcase)

- App: `n8nio/n8n:1.123.85`, digest `n8nio/n8n@sha256:8d4e5a2b73e5ac3bdbd1cc310f5bb0a12897851e700413cf8674b6bf0f374d5a`
  (label `org.opencontainers.image.version` 1.123.85; built on a hardened Node 24.13.1 / Alpine 3.22 base). 1.123.85 is
  the newest 1.x tag on Docker Hub (upstream has moved to 2.x). SQLite (image default) in the `n8n-data` volume.
  Compose project `rea-n8n`, loopback-only port `127.0.0.1:3218 -> 5678`, `N8N_EDITOR_BASE_URL`/`WEBHOOK_URL`
  `http://127.0.0.1:3218/`, `N8N_SECURE_COOKIE=false` (plain http), telemetry, version notifications, templates,
  personalisation and the hiring banner disabled, task runners enabled, manual executions saved.
- Licence: **Sustainable Use License 1.0** (fair-code, source-available, not OSI open source; upstream `LICENSE.md`), with
  files that have `.ee` in their name or directory under the n8n Enterprise License. The image carries no licence file;
  the text was read from the upstream repository. Only recorded JSON responses over synthetic data are published.
- Tooling on the VM: rea 6.6.0, playwright-core 1.58.2, snap Chromium 155 (`chromium.launch`, `--no-sandbox`), node v24,
  python 3.12, docker 29.9.1.

## Surprises
- **Readiness lies early.** `/healthz/readiness` answers `{"status":"ok"}` while migrations still run and before `/rest`
  is mounted (`Cannot GET /rest/settings`); compose's healthcheck and seed.py wait for `/rest/settings` instead.
- **Manual runs need a trigger name.** `POST /rest/workflows/{id}/run` with only `workflowData` fails with a 500
  ("Cannot read properties of undefined (reading 'nodeName')"); with `triggerToStartFrom: {name: <trigger node>}`, as the
  editor's Execute button sends it, the run succeeds and the execution is saved (mode `manual`).
- **Revoked-token collision.** Logout revokes the JWT; a second seed run that signs in within the same second gets a
  byte-identical JWT, which is still revoked (401). seed.py waits 1.1 s before signing in.
- **No second user.** Inviting a member puts an `inviteAcceptUrl` (a sign-up link for that instance) into every
  `/rest/users` reply, so the instance has only the owner.
- **Data tables** (module `data-table`, active in this build) work on the community plan; **folders** are disabled
  (`folders.enabled=false`, 403). Workflows accept a `description`.
- **Bootstrap repetition.** A full page load re-runs the editor bootstrap (settings, current user, roles 10 KB, projects,
  licence...); the first capture with `page.goto` for every page kept 143 records and wrote a 178 MB HAR. capture.mjs
  now navigates inside the SPA through its Vue router (`#app.__vue_app__...$router.push`).
- **Brackets in queries.** The users settings page requests `/rest/users?sortBy[]=...` with raw brackets, which makes rea's
  HAR `uri` format check reject the whole capture, so the capture does not visit that page.
- **JSON-valued query parameters.** The editor's list calls pass `filter={"isArchived":false}` and similar JSON strings.
  When such a record is the first record of a tool, the generated task asks the agent to pass that JSON string, and on
  the way to the replay server the string arrives as an object and fails the tool's `string` schema
  ("data/filter must be string"); gpt-oss worked around it by double-escaping, GLM-5.3-Flash did not (first eval: 9/11).
  capture.mjs now signs in with `?redirect=/settings/personal` and makes the scripted `/rest/workflows` and
  `/rest/executions` reads (plain query values) before visiting the list pages, so those tools' first records have no
  JSON values.
- **Outbound call.** The editor fetched dynamic banners from `api.n8n.io/api/banners` once (other-origin, dropped by
  scoping); `N8N_DYNAMIC_BANNERS_ENABLED=false` was not set.
- **Ids.** Workflow, tag, project and data-table ids are 16-character mixed-case strings that the `opaque-token` rule
  did not template; `sibling-variance` merged them where two or more were recorded (workflows/{workflow_id},
  data-tables/{data_table_id}/rows and /columns, workflows/{workflow_id}/executions/last-successful). It also merged
  `/rest/projects/personal`, `/my-projects`, `/count` and the project id into one `projects/{project_id}` tool (the
  conflation rea's limitations warn about; excluded from task generation). Ids recorded once stay literal, so the scratch
  tag/workflow write tools and the data-table paths carry ids in their names.

## Pipeline (all under ~/capture/n8n on the VM)
1. `python3 seed.py init` writes `.admin` (mode 600: owner password and `N8N_ENCRYPTION_KEY`, generated at run time).
   `docker compose -p rea-n8n -f compose.yml --env-file .admin up -d`; SQLite migrations and start take under a minute.
2. `python3 seed.py`: owner through `POST /rest/owner/setup` (Rea Admin, rea-admin@example.test), cookie session via
   `POST /rest/login`, then 5 tags, 4 workflows from core nodes only (Manual/Schedule Trigger, Edit Fields, If, No
   Operation, a sticky note; no credentials), a manual run of two of them (executions 1 and 2, both success), and 2 data
   tables with typed columns and 7 rows. Idempotent (looks up tags, workflows, executions and tables by name first) and
   removes `Rea scratch*` workflows left by an interrupted capture. Logs out. Writes `seed-ids.json` (ids only).
3. `NODE_PATH=~/capture/node_modules node capture.mjs`: UI sign-in at `/signin?redirect=/settings/personal`, the scripted
   workflows and executions list reads, then SPA navigation to the Granite Ledger canvas, the Blue Heron executions tab,
   `/home/executions`, the data tables page, `/settings/personal`, `/home/credentials`, `/home/workflows`; then 40 more
   scripted calls (42 in total; the `browser-id` header the session is bound to is read from localStorage): users, tags
   with usage counts, workflow list, each workflow by id, a tag filter (`{"tags":["Quarterly Audit"]}`) and a text
   filter, active workflows, executions (list, per workflow, by id, last successful per workflow), personal project,
   my projects, project by id, data tables (project list, global list, columns and rows of both tables, a row filter on
   `barge = Ember Compass`), credentials (empty), then a scratch tag POST, PATCH, list, DELETE, list and a scratch workflow
   POST, PATCH (with `versionId`), GET, archive, DELETE, GET (404). Full HAR 23 MB, 329 entries (deleted after scoping).
4. `python3 -I ~/capture/scope_har.py n8n.full.har n8n.scoped.har --origin http://127.0.0.1:3218 --keep-regex '^/rest/'
   --drop-regex 'login|logout|signup|password|session|token|oauth|csrf|/rest/settings|/rest/push|/rest/owner|/rest/invitations'`
   -> kept 72 (GET 65, POST 3, PATCH 2, DELETE 2; 200 x71, 404 x1); dropped path 249 (243 `/assets` files, 3 `/static`,
   `/types/nodes.json` and `/types/credentials.json`, the sign-in shell), auth 6 (`/rest/settings` x3, `/rest/login` x2,
   `POST /rest/ai/sessions/metadata` 403), other-origin 1 (`api.n8n.io/api/banners`), non-json 1
   (`/rest/external-secrets/secrets`, 404 HTML), big-body 0. 189,640 bytes, sha256
   `ad32e5104208daeb3488f6feefce0f189fe6ade22e3857907a10213009a022a3`.
   Credential check (counts only): owner password and encryption key 0, auth cookie and browser-id values 0, `eyJ`
   (JWT prefix) 0, `Bearer `/`hf_`/`ghp_`/`phc_` 0, secret/token/apiKey/password keys with values 0, `inviteAcceptUrl` 0.
5. `python3 ~/showcase/envbuild.py all n8n` (manifest, bundle, smoke, eval, card): see below.
6. `docker compose -p rea-n8n -f compose.yml down -v`; `n8n.full.har`, `.admin`, `req.*.json` removed.

## Manifest facts
- With rules: 30 tools (GET 23, POST 3, PATCH 2, DELETE 2), 6 templated groups, parameters `sibling-variance` 5 and
  `numeric` 1 (executions/{id}); `after-uid-literal` and `opaque-token` matched nothing. 24 query-parameter names across
  tools, 11 distinct (filter, includeData, includeFolders, includeGlobal, includeScopes, limit, skip, sortBy, take,
  withUsageCount, workflowId); 5 tools with a body shape (POST tags, PATCH tags, POST workflows, PATCH workflows, POST
  archive); statuses 200/404; 0 excluded; coverage complete-within-view 30/30; 9 limitations; capture evidence
  `ev_2df554f077a7336e5d535fa9e49df0b2d984c88dfc06c774e0343f26f9176a3e` (72 records, observed), manifest
  `ev_3141f2074cbb0bf27bbe9cedb95b7c69f2de89841d3fb0212660b7dfac094db8` (view digest
  `16b9e566b91c27ac57150c25b8c359fa4fbe7e9259493cf7e47361d41bba6dfd`), no-rules manifest
  `ev_a6e30b54d36f0e81d484db6ab668ed1fd871269bae2ec56d11f39deabd198283`.
- Without rules: 40 tools (GET 33, POST 3, PATCH 2, DELETE 2), only the numeric execution id templated.
- `exclude_tools` keeps editor plumbing (settings, module settings, licence, call-to-action, roles, counts, limits,
  insights, active workflows, credentials, AI, community nodes) and the conflated `projects/{project_id}` tool out of
  task generation; 11 candidates remain and all 11 become tasks.

## Tasks and episodes
Bundle: 11 retrieval tasks from 11 candidates. Smoke passed (30 tools listed, 26.4 s). Eval:
`openai/gpt-oss-120b:groq` 10/11, `zai-org/GLM-5.3-Flash:zai-org` 11/11, one tool call per answered task. Card and dry
publish: `~/showcase/datasets/n8n` (22 episodes). Tasks cover the last successful execution of a workflow and a
workflow by id (workflow name), data-table columns (first column name), an execution by id (workflow name), data-table
rows (barge of the first row), the execution list, the project's and the global data-table lists (first table name), the
workflow list, users (owner email) and tags. The gpt-oss miss is a hallucinated tool name: it completed the 60-character
truncated `..._rows_by_data` into `..._rows_by_data_table_id`, which the provider rejected (see `episode_notes`).
The first eval of this environment (before capture.mjs made the plain-query reads first) gave gpt-oss 11/11 and
GLM-5.3-Flash 9/11, both GLM misses being the JSON-valued `filter` argument described above; those runs were purged by
the re-run.

## Rebuild, 2026-10-18

After review, the shared task generator was tightened: an answer must be a distinctive value that occurs in this app's seed and capture inputs, never the admin account's own identity, in at most 16 recorded responses, and unique across the tasks; each tool gets at most two tasks. Bundle, smoke, eval and card were re-run from the same capture. The bundle and eval numbers earlier in this file describe the first build; these are the published ones.

- bundle: 9 retrieval tasks from 8 recorded reads with an eligible field (up to two tasks per tool); field values rejected: not distinctive 2, in too many responses 2, admin identity 1.
- smoke: passed.
- eval `openai/gpt-oss-120b:groq`: 9/9.
- eval `zai-org/GLM-5.3-Flash:zai-org`: 9/9.
- card and dry publish: 18 episodes, dataset 6.6 MB.
