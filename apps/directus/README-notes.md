# Directus 11.17.4 capture notes (rea showcase)

- App: `directus/directus:11.17.4` (the hint asked for 11.x; 12.5.0 is the newest tag), digest
  `directus/directus@sha256:eb326f679ae847c0a776f93b972761dc2ebe84980e0b9d274a6bc31cd62809f7`, version `11.17.4`
  (image `package.json`, same in `GET /server/info`), sqlite3 at `/directus/database/data.db` (volume `directus-db`),
  uploads in volume `directus-uploads`. Compose project `rea-directus`, loopback-only `127.0.0.1:3223 -> 8055`,
  `PUBLIC_URL=http://127.0.0.1:3223`, `TELEMETRY=false`, `WEBSOCKETS_ENABLED=false`, `MARKETPLACE_TRUST=sandbox`.
- Licence: Business Source License 1.1 (`/directus/license` in the image): Licensor Monospace, Inc.; additional use grant
  for production use by entities under US $5M total finances; non-production use (evaluation, testing) is granted;
  change license GPL v3 three years after each release. `app.json` says `BSL-1.1`; only Directus's JSON responses over
  synthetic data are in the dataset.
- Tooling on the VM: rea 6.6.0, playwright-core 1.58.2, Chromium 155.0.8059.79 (snap, plain `chromium.launch`),
  node v24.22.0, python 3.12.3, docker 29.9.1, compose 5.6.0, Ubuntu 24.04 amd64.

## Pipeline (all under ~/capture/directus on the VM)
1. `python3 seed.py` writes `.admin` (mode 600) with `KEY`, `SECRET` and `ADMIN_PASSWORD` generated at run time, then
   starts `docker compose -p rea-directus -f compose.yml up -d` itself, because compose.yml reads `.admin` as its
   `env_file` (so the secrets never sit in compose.yml). `ADMIN_EMAIL` is a constant in compose.yml. Directus bootstraps
   the schema and the admin on first start; the script waits on `/server/health` before signing in.
   Surprise: Directus validates emails against the IANA TLD list, so `rea-admin@example.test` was created by the
   bootstrap but `POST /auth/login` then rejected it (`"email" must be a valid email`). The env uses the reserved
   documentation domain `example.com` instead (admin `rea-admin@example.com`, users `ada.finch@example.com`,
   `rui.castellanos@example.com`).
2. Seeding (same script, `POST /auth/login` in JSON mode; the token stays in process memory and the refresh token is
   logged out at the end): collections `crew_rota` (note "Who keeps which watch for the Lighthouse Rota.", fields name,
   role_title, shift dropdown, watch_station, notes, each with a field note) and `provisions` (note "Stores held at the
   Saltmarsh Depot for the rota.", fields title, category, quantity, unit, storage_bay, supplier_note), 5 items each;
   folders Lighthouse Rota Archive > Granite Ledger Scans; a multipart upload of `granite-ledger-gl-2291.txt` (title
   "Granite Ledger tally GL-2291"); policy Rota Editing (4 permissions) attached to role Rota Editors via `/access`;
   role Depot Viewers; users Ada Finch and Rui Castellanos (titles, locations, descriptions); the admin profile (Rea
   Admin, Rota Archivist, Granite Point, `last_page` reset to `/content/crew_rota` so every capture lands on the same
   page); bookmark Night shift crew; Insights dashboard Depot Overview with metric panel Provisions on hand; manual
   inactive flow Announce new provisions; a comment on Ada Finch's rota item. Idempotent (lookup by name/email/title
   first) and removes `Rea Scratch*` provisions left by an interrupted capture. Writes `seed-ids.json`.
3. `NODE_PATH=~/capture/node_modules node directus/capture.mjs`: sign-in at `/admin/login`. The Data Studio uses
   session mode (an httpOnly `directus_session_token` cookie; nothing in localStorage), so scripted `fetch` calls carry
   the cookie. Directus 11 then opens a "You have not set a project owner" dialog (BSL compliance); setting an owner
   would call out to directus.io, so the capture clicks "Remind Later". The first capture loaded every module with
   `page.goto`, and each full load re-ran the ~22-request Data Studio bootstrap (over 200 API records, a 326 KB `/fields`
   each time); the final capture navigates client-side by clicking the module links (content > provisions > a row,
   users, files, insights > Depot Overview, settings > data model, flows), so the bootstrap appears once. Then 35
   scripted calls: server info, users/me, both collections, the crew_rota fields and one provisions field, both item
   lists, 4 items by id, a JSON `filter` (category = Lamp), a `search` (Blue Heron), a sort/limit read, folders and a
   folder by id, the file, roles and a role, the policy, its permissions, users and a user, the bookmark, the dashboard,
   the panel, the flow, the comment; then POST a scratch provision (200), PATCH it (200), GET it, DELETE it (204), GET it
   again (403: Directus answers 403, not 404, for a missing item) and an `aggregate` count. JSON query values are sent
   with `encodeURIComponent`. Full HAR 10.4 MB, 130 entries (deleted after scoping).
4. `python3 -I ~/capture/scope_har.py directus.full.har directus.scoped.har --origin http://127.0.0.1:3223 --keep-regex
   '^/(items|collections|fields|users|roles|policies|permissions|folders|files|presets|dashboards|panels|flows|operations|comments|activity|revisions|relations|settings|server|translations|notifications|shares|versions)(/|$)'`
   (default drop regex) -> kept 90 (GET 77, PATCH 11, POST 1, DELETE 1); dropped path 37 (33 Data Studio assets,
   `GET /auth?sessionOnly` x2, `POST /auth/refresh`, `GET /extensions/sources/index.js`, `POST /graphql` from the Insights
   panel), auth 2 (`GET /admin/login`, `POST /auth/login`), big-body 1 (`GET /fields`, 326,054 bytes), non-json 0,
   other-origin 0. Credential grep on the scoped HAR: admin password 0, KEY 0, SECRET 0, `hf_|ghp_|Bearer ` 0,
   `directus_session_token` 0, `eyJ` 0. sha256 `1667a554741c257c7831f80302833dfff820050f35866ac9f0fd6bc1d6e5a8c9`,
   219,187 bytes.
5. `python3 ~/showcase/envbuild.py all directus`:
   - manifest: capture evidence `ev_726c10bf55a915e584548f44ddfcacfabb7b72780f9ce24a1a1d18d093836af2` (90 records,
     confidence observed); manifest with rules `ev_df3fc9049d7dd8e54cbefab23250d29be75af6e6ba7bbc9c3cc092e64c134c58`
     (inferred, historical-reference); without rules `ev_2457c64e65ef78f193b7d85c778320f714e3e568b924b107e0b9a83bbcf227a2`.
   - bundle: 12 retrieval tasks (`exclude_tools`: `server|settings|track|config$|version$`).
   - smoke: passed in 26.6 s (`listed 43 tools, expected 43`).
   - eval: `openai/gpt-oss-120b:groq` 12/12, `zai-org/GLM-5.3-Flash:zai-org` 12/12, no provider errors.
   - card + dry publish: 24 episodes, `~/showcase/datasets/directus` (6.7 MB).
6. `docker compose -p rea-directus -f compose.yml down -v`; `directus.full.har`, `.admin` and the probe script removed.

## Manifest facts
- 43 tools (GET 41, POST 1, PATCH 1), 14 templated groups, 13 parameters: 9 `uuid` (users, roles, policies, folders,
  files, dashboards, panels, flows, comments) and 4 `numeric` (items of both collections, presets). These are rea's
  built-in rules; the opt-in rules match nothing, so the no-rules manifest is also 43 tools. Collection names are plain
  words and stay literal: `get_items_crew_rota_by_id`, `get_items_provisions_by_id`, `get_collections_crew_rota`,
  `get_fields_provisions_storage_bay`, and so on.
- 2 groups excluded as non-json: `DELETE /items/provisions/{numeric}` and `PATCH /users/me/track/page` (both 204 with
  mime type `x-unknown`; the scoping tool keeps empty replies, rea's manifest then drops them). So there is no DELETE
  tool; the POST and PATCH of the scratch provision are tools with body shapes.
- 73 query-parameter name slots; the Data Studio's own reads use bracketed names (`fields[]`, `sort[]`,
  `filter[_and][0][collection][_eq]`, `aggregate[countDistinct]`, ...), the scripted ones use JSON-valued `filter` and
  `aggregate` plus `fields`, `search`, `sort`, `limit`. Statuses 200 and 403; unknowns authorization-model,
  response-semantics, state-transition.
- UI-generated tools besides the scripted ones: users/me (11 records), roles/me, policies/me/globals, permissions/me,
  collections, relations, settings, presets (3 filter variants), translations, notifications, dashboards, panels,
  flows, files (3), revisions, comments, shares, versions (the item page's side panels).

## Tasks and episodes
- 12 tasks, all on by-id tools: dashboard name, file title, crew_rota item name, user first name, role name, bookmark
  collection, provision title, panel name, comment collection, policy description, folder name, flow name. Every value
  sits under `data` (Directus wraps responses as `{"data": ...}`), so fields read `data.name`, `data.title`.
- Both models passed 12/12; no `episode_notes` needed.

## Seeded facts usable for retrieval questions
Crew: Ada Finch (Tide Table Keeper, Night, North Lamp Gallery, "Keeps the January tide tables."), Rui Castellanos
(Quarry Auditor, Day, Granite Ledger Office, audited GL-2291), Mina Okafor (Market Liaison, Blue Heron Kitchen), Tomas
Vey (Cracker Baker, Dawn, Copperfield Annex), Marisol Okonkwo-Reyes (Head Cook, Evening). Provisions: Saffron Tide
Biscuits 48 tins Bay C2, Pale Meridian Tea 12 bricks Bay A1, Ember Compass Matches 300 boxes Bay B4, Silver Anvil Rivets
900 pieces Bay D1, Northern Quill Ink 6 bottles Bay A3. Policy Rota Editing: "Create and update crew rota entries and read
provisions." Comment: "Ada swaps the January night watch with Tomas Vey."

## Rebuild, 2026-10-18

After review, the shared task generator was tightened: an answer must be a distinctive value that occurs in this app's seed and capture inputs, never the admin account's own identity, in at most 12 recorded responses, and unique across the tasks; each tool gets at most two tasks. Bundle, smoke, eval and card were re-run from the same capture. The bundle and eval numbers earlier in this file describe the first build; these are the published ones.

- bundle: 12 retrieval tasks from 25 recorded reads with an eligible field (up to two tasks per tool); field values rejected: not distinctive 68, not in the seed inputs 3, admin identity 1.
- smoke: passed.
- eval `openai/gpt-oss-120b:groq`: 12/12.
- eval `zai-org/GLM-5.3-Flash:zai-org`: 12/12.
- card and dry publish: 24 episodes, dataset 6.7 MB.
