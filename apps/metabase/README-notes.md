# Metabase capture notes (rea showcase, batch 2, vm1)

- App: `metabase/metabase:v0.64.2.8` (the AGPL-3.0 open-source image; the enterprise image is a different repository),
  digest `metabase/metabase@sha256:3b968d64944840ec0ed452a94fb58301a0a8d8e4fe6d632a5956014a91a2b635`, version reported by
  `GET /api/session/properties` as tag `v0.64.2.8`, build hash `0f5961a`, date 2026-10-16. Licence checked in the repository's
  `LICENSE.txt` at the tag: everything outside `enterprise/` is AGPL, and binaries at hub.docker.com/metabase/metabase are AGPL.
- Compose project `rea-metabase`, loopback-only port `127.0.0.1:3201 -> 3000`, embedded H2 application database on the
  `metabase-data` volume (`MB_DB_FILE=/metabase-data/metabase.db`), `JAVA_OPTS=-Xmx2g`, update checks and anonymous tracking
  off, `MB_LOAD_SAMPLE_CONTENT=false` so there is no "Examples" collection. Healthcheck `curl /api/health` -> `{"status":"ok"}`;
  healthy after 45 s on the VM (8 vCPU, 30 GB).
- Tooling on the VM: rea 6.6.0, playwright-core 1.58.2, Chromium 155.0.8059.79 (snap; Playwright's default temp profile
  worked, the `USER_DATA_DIR` fallback was not needed), node v24.22.0, python 3.12.3, Docker 29.9.1 / Compose v5.6.0,
  agent-env 0.9.1334.

## Pipeline (all under ~/capture/metabase on the VM)
1. `docker compose -p rea-metabase -f compose.yml up -d`.
2. `python3 seed.py` (stdlib urllib, idempotent by name; re-run twice without changes):
   - `GET /api/session/properties` gives the one-time `setup-token`; `POST /api/setup` creates the admin "Rea Admin"
     (`rea-admin@example.test`, site "Lighthouse Rota Analytics") with a password generated at run time into `.admin`
     (mode 600). The returned session id is held in memory and sent as `X-Metabase-Session`; `DELETE /api/session` at the end.
   - `MB_LOAD_SAMPLE_CONTENT=false` also skips the bundled Sample Database, so the seed adds it with
     `POST /api/database/sample_database` and waits for the first sync before reading table and field ids.
   - Content: users Ada Finch, Rui Castellanos, Mina Okafor; group "Night Shift Analysts" (Ada, Mina); collections
     "Granite Ledger", "Blue Heron Kitchen", "Saltmarsh Depot" (nested in Granite Ledger); 5 saved questions (legacy MBQL
     count by category through the PRODUCT_ID foreign key, MBQL average rating by category, native SQL sign-ups by source,
     MBQL five-star review count, and a model over ORDERS); dashboards "Granite Ledger Overview" and "Blue Heron Kitchen
     Service Board" (2 question cards + 1 text card each, set with `PUT /api/dashboard/{id}` dashcards); timeline "Granite
     Ledger milestones" with 2 events; native-query snippet "Saltmarsh Depot gizmo filter"; segment "Granite Ledger large
     orders"; synthetic descriptions on table PRODUCTS and fields PRODUCTS.CATEGORY and ORDERS.TOTAL; bookmarks on one card
     and one dashboard. Deletes any leftover "Rea scratch*" card. Writes `seed-ids.json` (ids only).
   - The table and field rows themselves (Orders, Products, "Some example data for you to play around with.", the
     Doohickey/Gadget/Gizmo/Widget categories) are Metabase's own bundled sample data, not ours.
3. `NODE_PATH=~/capture/node_modules node metabase/capture.mjs`: UI login at `/auth/login` (the `metabase.SESSION` cookie
   carries the in-page fetches), then the scripted fetch sequence, then the UI pages, then the write path:
   - reads: collections list and 3 collections by id, 2 collection item lists, cards list and 5 cards by id, 2 card query
     runs (`POST /api/card/{id}/query`, 202 with JSON), dashboards list and 2 by id, timelines with events, timeline by id,
     2 timeline events, snippets list and by id, segments list and by id, users list and 3 by id, groups list and by id,
     database 1, table PRODUCTS, 2 fields; searches `q=granite`, `q=saltmarsh&models=card`, `GET /api/user?query=okafor`;
   - UI pages: `/` (landing after login), `/collection/6`, `/dashboard/1`, `/question/1`, `/collection/8`, `/admin/people`;
   - writes: `POST /api/card` (native scratch question), `PUT /api/card/{id}` (rename), `GET`, `DELETE` (204), `GET` (404),
     then the Saltmarsh Depot items again.
   The reads run before the UI pages on purpose: in the first capture the UI's dashboard request came first and carried a
   random `dashboard_load_id` query value, which the generated task then asked the model to pass. Full HAR 52.5 MB
   (deleted after scoping).
4. `python3 -I ~/capture/scope_har.py metabase.full.har metabase.scoped.har --origin http://127.0.0.1:3201 --keep-regex '^/api/'
   --drop-regex 'login|logout|signup|password|session|token|oauth|csrf|^/api/metabot/|^/api/setting/|^/api/user-key-value/|^/api/collection/trash'`
   -> kept 120 (GET 112, POST 6, PUT 1, DELETE 1); dropped path 201, auth/noise 29, non-json 0, big-body 0, over-max 0.
   Without the four noise patterns the scope kept 141 (UI polling of metabot permissions, `setting/version-info`,
   user-key-value and the trash collection). The 29 also include 8 `GET /api/session/properties` (119-126 KB each).
   Statuses: 200 x112, 202 x5 (query runs), 204 x1 (DELETE), 401 x1 (UI probe of `/api/user/current` before sign-in,
   text/plain), 404 x1 (re-read of the deleted card, text/plain). 515,053 bytes, sha256
   `cd791130c103bf19299b14221ac2c27ae0bc9f8ae16e604c82ac4b34631a2d8a`. Credential grep: admin password 0 hits,
   `hf_`/`ghp_`/`Bearer ` 0, `metabase.SESSION` 0, no `<scrubbed>` markers needed.
5. `python3 ~/showcase/envbuild.py all metabase`: manifest, bundle, smoke, eval for both models, card + dry publish.

## Manifest facts
- Capture Evidence `ev_ae41d6f2a19b032ad77cd55df2547050605d49d7877db2e63b47c49647324924` (120 records, observed).
- With rules: manifest `ev_97964117e7834ff3666205d78ca1a191235de72b54f4aa6bc0f96899674581a8`, confidence inferred, authority
  historical-reference, **42 tools** (GET 37, POST 3, PUT 1, DELETE 1), 23 templated groups, 25 path parameters, all from the
  unconditional `numeric` rule (one route has three: `POST /api/dashboard/{id}/dashcard/{id_2}/card/{id_3}/query`);
  31 query-parameter names across tools (19 distinct: can-query, context, dashboard_load_id, exclude-archived,
  exclude-other-user-collections, f, include, include-library, limit, models, offset, pinned-state, q, query,
  show-dashboard-questions, sort-column, sort-direction, status, tenancy); 4 tools with a body shape (POST card, PUT card,
  POST card query, POST dashcard query); 0 excluded groups; coverage complete-within-view 42/42; 9 limitations; unknowns
  authorization-model, response-semantics, state-transition.
- Without rules: `ev_84f096bec5f1ed85a460a85f07e3fd430869a4d65443c30f1b86c0e3f01e4cac`, also 42 tools and 23 templated groups.
  Every id in Metabase's API is an integer, so the numeric rule does all the templating and the opt-in rules have nothing
  to merge (no opaque tokens, no uid-literal pairs, no literal siblings).
- UI-generated tools besides the scripted ones: activity popular_items/recents, automagic-dashboards candidates, bookmark,
  card query_metadata (47 KB), collection root/tree/items metadata/dashboard-question-candidates, dashboard query_metadata
  (56 KB), database schemas, permissions membership, pulse form_input, user/current.

## Build results
- Bundle: 12 retrieval tasks from 25 candidate GET tools. `exclude_tools` keeps the large or UI-plumbing reads out of the
  task set (query_metadata, settings, session, version/health, metabot, bookmark, activity, automagic, candidates,
  form_input, schemas, items_metadata, trash). Several tasks ask for a nested field (`creator.email`,
  `last-edit-info.first_name`, `members[0].common_name`, `table.db.name`), which the models read correctly.
- Smoke passed (26.6 s; the agent image was already built on this VM).
- Eval: `openai/gpt-oss-120b:groq` **12/12**, `zai-org/GLM-5.3-Flash:zai-org` **12/12**; one tool call per episode,
  mean input tokens 10,368 and 13,488; about 55-65 s per task, four tasks at a time.
- Dry publish: 13 tasks, 25 runs (24 eval episodes + smoke) in `~/showcase/datasets/metabase`, 7.1 MB; scans clean.

## Surprises
- `MB_LOAD_SAMPLE_CONTENT=false` removes the Sample Database too, not only the Examples collection; the API endpoint
  `POST /api/database/sample_database` restores just the database.
- Saved questions accept legacy MBQL and are stored as MBQL 5 (`lib/type: mbql/query`, `stages`); a segment definition
  must be a full query (`database`, `type`, `query`), a bare inner query is rejected with "Query must include :lib/type or :type".
- `envbuild.py manifest` treats every value in `.admin` as a secret and fails if it appears in the HAR. The admin email
  is in every user payload, so `.admin` here holds only the password; the email is a fixed constant in seed.py and capture.mjs.
- `make_card.py` renders `seeded_objects` with `str()`, so summary.json carries a one-line `seeded_objects` sentence for the
  card and the structured list in `seeded_objects_detail`.

## Teardown
`docker compose -p rea-metabase -f compose.yml down -v` (container, `rea-metabase_metabase-data` volume and network removed);
`metabase.full.har`, `.admin`, `req.*` files deleted on the VM.

## Rebuild, 2026-10-18

After review, the shared task generator was tightened: an answer must be a distinctive value that occurs in this app's seed and capture inputs, never the admin account's own identity, in at most 12 recorded responses, and unique across the tasks; each tool gets at most two tasks. Bundle, smoke, eval and card were re-run from the same capture. The bundle and eval numbers earlier in this file describe the first build; these are the published ones.

- bundle: 12 retrieval tasks from 16 recorded reads with an eligible field (up to two tasks per tool); field values rejected: not distinctive 79, not in the seed inputs 6, admin identity 29, in too many responses 29.
- smoke: passed.
- eval `openai/gpt-oss-120b:groq`: 12/12.
- eval `zai-org/GLM-5.3-Flash:zai-org`: 12/12.
- card and dry publish: 24 episodes, dataset 7.1 MB.
