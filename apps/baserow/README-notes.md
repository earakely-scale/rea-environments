# Baserow 2.4.1 capture notes (rea showcase, batch 2)

- App: `baserow/baserow:2.4.1` (the all-in-one image: Caddy, the Nuxt web frontend, the Django backend, Celery workers,
  and a bundled PostgreSQL and Redis inside the one container), digest
  `baserow/baserow@sha256:2229bc0ad9c8e1c3c44cef3324ff0501639d44a7b6f64026ebaa44f61cfb038e`. Version 2.4.1 is the
  image tag and the `info.version` of the OpenAPI document served at `/api/schema.json`; `GET /api/settings/` does not
  report a version. Licence: the repository LICENSE puts everything outside `premium/` and `enterprise/` (Baserow Open
  Source Edition) and all client-side JavaScript under MIT (Expat); the image also ships the premium/enterprise code, which
  stays locked without a licence and was not used here.
- Compose project `rea-baserow`, loopback-only `127.0.0.1:3204 -> 80`, `BASEROW_PUBLIC_URL=http://127.0.0.1:3204`, one
  named volume `baserow-data:/baserow/data` (PostgreSQL data, media). Healthcheck `curl /api/_health/` inside the container;
  healthy about 2.5 minutes after `up` on the first start (migrations plus template sync). Instance settings out of the box:
  `email_verification: no_verification`, no SMTP, sign-ups allowed.
- Tooling on the VM: rea 6.6.0, playwright-core 1.58.2, Chromium 155.0.8059.79 (snap, plain `chromium.launch`),
  node v24.22.0, python 3.12.3, docker 29.9.1, compose 5.6.0.

## Pipeline (all under ~/capture/baserow on the VM)
1. `docker compose -p rea-baserow -f compose.yml up -d`.
2. `python3 seed.py` (stdlib urllib, idempotent):
   - `POST /api/user/` signs up "Rea Admin" <rea-admin@example.test>; the first account becomes instance staff. The
     password is generated at run time into `.admin` (mode 600, password only). Sign-up returns the user without a
     token, so the seed then calls `POST /api/user/token-auth/` and keeps the JWT access token in memory only
     (`Authorization: JWT ...`).
   - Workspace "Saltmarsh Depot Cooperative", databases "Lighthouse Rota" and "Granite Ledger Archive" (empty).
   - Three tables, each created empty (Baserow adds Name/Notes/Active and two blank rows, which the seed removes), then
     typed fields and rows through `POST /api/database/rows/table/{id}/batch/?user_field_names=true`:
     Stations (4 rows), Keepers (5 rows, link to Stations, single select Rank), Supply Orders (4 rows, links to Stations
     and Keepers, single select Stage).
   - One edit (Ada Finch, Shifts per month 12 -> 14) so that her row history has an `update_rows` entry.
   - Default grid views renamed (All stations, Keeper roster, Order book); extra views: grid "Certified keepers"
     (filter `boolean = 1`, sort Shifts per month descending), grid "Open orders" (filter `single_select_not_equal`
     Delivered), gallery "Station cards", form "Request supplies" (title and description).
   - Deletes any leftover scratch order (`SO-9...`) from an interrupted capture. Writes `seed-ids.json` (ids only).
3. `NODE_PATH=~/capture/node_modules node capture.mjs`: UI login at `/login` (lands on `/all-workspaces`), then the
   workspace page, the Keepers grid, the "Certified keepers" grid, the Supply Orders grid, the Stations grid, the
   "Station cards" gallery, `/admin/users`; then 51 scripted `fetch` calls from inside the page; the row modal of
   Mina Okafor is opened near the end (row read with `include=metadata`, row history). The web UI keeps its JWT access
   token in its Vuex store (`useNuxtApp().$store.getters['auth/token']`; the refresh token is in the `jwt_token`
   cookie), so the script reads it from the store for each call and sends it as `Authorization: JWT ...`, as the UI does.
   Scripted reads: workspaces, applications (list, both databases by id, by workspace), workspace users, tables (by
   database, each of the three by id), Keepers fields, three fields by id, unique values of Supplier, rows list
   (Keepers), all 13 seeded rows by id with `user_field_names=true`, Ada Finch's history, `search=heron`,
   `filter__field_<Stage>__single_select_equal=<Requested>`, `order_by=-Shifts per month&size=3`, row names for the
   four stations, Keepers views, the form view and "Certified keepers" by id, its filters and sortings, the "Open
   orders" filter by id, the "Open orders" grid rows, the gallery rows, admin users, workspace search `query=heron`,
   trash. Write path: a scratch supply order SO-9001 is created (POST 200), edited (PATCH 200), read, deleted
   (DELETE 204, no body), read again (404) and the orders list read again.
   Raw HAR: 1,506 entries, 122.7 MB (the Nuxt chunks dominate), deleted after scoping.
4. `python3 -I ~/capture/scope_har.py baserow.full.har baserow.scoped.har --origin http://127.0.0.1:3204 --keep-regex '^/api/'`
   (default drop regex and limits) -> kept 83 (GET 80, POST 1, PATCH 1, DELETE 1); dropped path 1,421 (UI shell, JS/CSS,
   fonts, images), auth 2 (`GET /login` and `POST /api/user/token-auth/`, whose response carries the JWT pair),
   other-origin 0, non-json 0, big-body 0, over-max 0. Statuses 200 x81, 204 x1, 404 x1. Scoped HAR 157,373 bytes,
   sha256 `286207ccf9bec4e41170bbd802886c9bf3d11de51501e01faad00ffda415d93d`.
   Credential grep on the scoped HAR: admin password literal 0, `eyJ` 0, `JWT ` 0, `Bearer ` 0, `hf_`/`ghp_` 0,
   `jwt_token`/`user_session`/`access_token`/`refresh_token` 0. Only content-type/accept headers survive scoping.
5. `python3 ~/showcase/envbuild.py all baserow` (manifest, bundle, smoke, eval, card).

## Manifest facts
- Capture Evidence `ev_85d6e0f7e7c20d307a860f6c35f7e696fa6baf0e1a54f19060d77989e82fadac` (83 records, observed).
- With the three opt-in rules: evidence `ev_d41265c6d4379a907ba76eeebbfe708af1f9e04618bbab29c47d7ba9b1c2ac7c`, confidence
  `inferred`, authority `historical-reference`, 31 tools (GET 28, POST 1, PATCH 1, DELETE 1), 23 templated groups,
  27 path parameters, all from REA's built-in `numeric` rule; coverage complete-within-view 31/31, 0 excluded groups,
  9 limitations, unknowns authorization-model, response-semantics, state-transition. Body shapes on the row POST and PATCH.
- Without the rules: evidence `ev_c6d455ba21c86b13bdf6da89c040de1cfaf37dcbdd511fc54edc494a075c247c`, the same 31 tools.
  Every Baserow id is an integer (workspace 76, database 114, tables 361/362/371, fields, views, rows), so the
  unconditional `numeric` rule does all the templating and the opt-in rules have nothing left to do. The card's
  generic sentence "without them ... one per literal path" therefore reads 31 = 31 here.
- The 13 row reads across three tables collapse into one tool, `get_database_rows_table_by_id_id_2`
  (`/api/database/rows/table/{numeric}/{numeric}/`, statuses 200 and 404), with GET/PATCH/DELETE siblings on the same
  template. Query parameters stay names on the tools (15 distinct, including the per-field
  `filter__field_3539__single_select_equal` and the per-table `table__361` of the row-names endpoint, which carry ids in
  their names).
- UI-only tools kept: jobs polling, last-viewed items, user dashboard, field-rules (empty `[]` per table), views with
  `include=filters,sortings,...`, grid/gallery row pages with `include=field_options,row_metadata`, admin users `?page=1`.

## Tasks and eval
- `exclude_tools` = `settings|notifications|jobs$|last_viewed|user_dashboard|field_rules|trash$|unique_row_values`
  (UI polling and value lists); 19 candidates, 12 tasks.
- The capture order was chosen so the first record of each tool is a different object (Supply Orders table by id,
  Keepers rows list and grid, a Supply Orders row by id, the form view by id) instead of Stations everywhere.
- Smoke passed (31 tools listed). gpt-oss-120b 12/12, GLM-5.3-Flash 12/12; no provider errors, no misses.

## Seeded facts usable for retrieval questions
Stations: Granite Point Light (North Shoal, 18 nm, 1891-05-14, Fresnel second order, staffed), Copperfield Annex Beacon
(Copperfield Sound, 9 nm, 1934-09-02, LED cluster, unstaffed), Blue Heron Spit (Heron Flats, 12 nm, 1902-03-21,
Acetylene retrofit), Saltmarsh Depot Tower (Saltmarsh Reach, 22 nm, 1875-11-08, Fresnel first order).
Keepers: Ada Finch (Head keeper, Granite Point Light, 14 shifts after the edit, certified, "Keeps the tide tables for
January."), Rui Castellanos (Assistant keeper, Saltmarsh Depot Tower, 11, "Audits the lamp-oil ledger every fortnight."),
Mina Okafor (Relief keeper, Blue Heron Spit, 6, not certified), Tomas Vey (Head keeper, Copperfield Annex Beacon, 8),
Ilse Marrow (Assistant keeper, Granite Point Light, 9, "Learning the fog-signal schedule.").
Supply Orders: SO-4471 Lamp oil, 180 litres (Delivered, Granite Ledger Chandlery), SO-4472 Lens polishing cloths
(Shipped, Copperfield Annex Stores), SO-4473 Fog horn diaphragm (Requested, Tidewater Brass Works), SO-4474 Tide gauge
batteries (Requested, Saltmarsh Depot Provisions). Form view title "Request supplies for your station".

## Teardown
`docker compose -p rea-baserow -f compose.yml down -v`; `baserow.full.har`, `.admin`, `req.*.json` and the probe/explore
scripts removed on the VM.

## Rebuild, 2026-10-18

After review, the shared task generator was tightened: an answer must be a distinctive value that occurs in this app's seed and capture inputs, never the admin account's own identity, in at most 12 recorded responses, and unique across the tasks; each tool gets at most two tasks. Bundle, smoke, eval and card were re-run from the same capture. The bundle and eval numbers earlier in this file describe the first build; these are the published ones.

- bundle: 12 retrieval tasks from 14 recorded reads with an eligible field (up to two tasks per tool); field values rejected: admin identity 7, not distinctive 14, in too many responses 2, not in the seed inputs 2.
- smoke: passed.
- eval `openai/gpt-oss-120b:groq`: 12/12.
- eval `zai-org/GLM-5.3-Flash:zai-org`: 12/12.
- card and dry publish: 24 episodes, dataset 6.6 MB.
