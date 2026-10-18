# Grocy 4.7.1 capture notes (rea showcase)

- App: `lscr.io/linuxserver/grocy:v4.7.1-ls345` (linuxserver.io packaging, nginx + php-fpm 8.5.6), digest
  `lscr.io/linuxserver/grocy@sha256:cae63f6c731f6ad8a3596eef097c136934a3a076e6ae533f933182187fe85a12`, Grocy `4.7.1`
  (release date 2026-09-04, `db_version` 257, from `GET /api/system/info`), sqlite 3.53.4 at `/config/data/grocy.db` in the
  `grocy-config` volume. Compose project `rea-grocy`, loopback-only port `127.0.0.1:3222 -> 80`, `GROCY_CURRENCY=EUR`.
- Licence: Grocy is MIT (`/app/www/LICENSE.md`, Copyright (c) 2017-2026 Bernd Bestel). The linuxserver.io image packaging
  is labelled GPL-3.0-only (`org.opencontainers.image.licenses`); only Grocy's JSON responses are in the dataset.
- Tooling on the VM: rea 6.6.0, playwright-core 1.58.2, Chromium 155.0.8059.79 (snap; the plain `chromium.launch` temp
  profile worked), node v24.22.0, python 3.12.3, docker 29.9.1, compose 5.6.0, Ubuntu 24.04 amd64.

## Pipeline (all under ~/capture/grocy on the VM)
1. `docker compose -p rea-grocy -f compose.yml up -d`; healthcheck `curl -fsS http://127.0.0.1:80/login`, healthy after ~15 s.
   Surprise: the database is created by the first `GET /` (Grocy runs its schema migrations there). Before that the login
   form answers 500 (`no such table: migrations`) even though `/login` itself renders 200, so seed.py requests `/` first.
2. `python3 seed.py`: signs in through the web form with Grocy's built-in default `admin`/`admin` (the form posts
   `username` and `password_base64`; the page base64-encodes the password in JS), renames that user with
   `PUT /api/users/1` to `rea-admin` (Rea Admin) with a password generated at run time into `.admin` (mode 600, holding
   only `GROCY_ADMIN_PASSWORD`; the user name is a constant because envbuild's credential check flags any `.admin`
   value that appears in the HAR, and `/api/users` returns the user name), checks that `admin/admin` no longer signs in,
   signs in again as rea-admin and seeds through `/api` with the session cookie the web UI uses (no API key needed).
   Grocy ships a location "Fridge", quantity units "Piece"/"Pack" and a shopping list "Shopping list"; the first and last
   are renamed to synthetic names. Seeded: users afinch (Ada Finch) and rcastellanos (Rui Castellanos); locations
   Saltmarsh Depot Cold Room, Copperfield Annex Larder, Granite Ledger Lockers; quantity units Crate/Crates and Tin/Tins;
   product groups Tide Rations and Lamp Supplies; stores Blue Heron Kitchen Market and Lighthouse Rota Co-op; 5 products
   (Smoked Kelp Broth, Granite Salt Flakes, Heron Rye Crackers, Lamp Wick Bundle, Copperfield Lamp Oil) each with one
   purchase (`POST /api/stock/products/{id}/add` with price, due date, store and a note); shopping lists Saltmarsh Depot
   Restock and Lighthouse Rota Night Shift with 4 items; chores Polish the Lighthouse Lens (one execution by Ada Finch),
   Rotate the Kelp Barrels, Sweep the Copperfield Annex; batteries Foghorn Remote Cell (one charge) and Tide Gauge Pack;
   task categories Depot Rounds and Lamp Watch; tasks Recount the Granite Ledger crates and Order winter lamp mantles;
   equipment Copperfield Annex Dehydrator and Saltmarsh Depot Chest Scale; recipe Tide-Table Kelp Stew with 2 ingredients.
   Idempotent (lookup by name before create); removes `Rea Scratch*` products left by an interrupted capture.
   `POST /api/objects/{entity}` answers `{"created_object_id": "<n>"}` with the id as a string. Writes `seed-ids.json`.
3. `NODE_PATH=~/capture/node_modules node grocy/capture.mjs`: UI sign-in at `/login` (`#username`, `#password_input`,
   `#login-button`), visits /stockoverview, /products, /product/3 (edit form), /locations, /quantityunits, /shoppinglist,
   /choresoverview, /batteriesoverview, /tasks, /recipes, /equipment, /stockjournal, then 47 scripted `fetch` calls from the
   page: system info, every collection list, 22 reads of single seeded objects (generic `/api/objects/{entity}/{id}` for
   products x2, locations, quantity units, product groups, stores, shopping lists, shopping-list items, chores, batteries,
   tasks, task categories, equipment, recipes; plus `/api/stock/products/{id}` x2, `.../entries`, `.../locations`,
   `/api/stock/locations/{id}/entries`, `/api/chores/{id}`, `/api/batteries/{id}`, `/api/recipes/{id}/fulfillment`), 5
   filtered reads (`query[]=product_group_id=1&order=name:asc`, `query[]=name~Kelp`, `query[]=done=0&order=due_date:asc&limit=5`,
   shopping-list items by list, recipe positions by recipe), then POST a scratch product (200), PUT it (204), GET it, DELETE it (204), GET it again (404),
   and the product list again. The query brackets are sent as `query%5B%5D`: with raw brackets rea rejects the HAR
   (`HAR schema validation failed: format (must match format "uri")`). Full HAR 18.7 MB, 802 entries (deleted after scoping).
4. `python3 -I ~/capture/scope_har.py grocy.full.har grocy.scoped.har --origin http://127.0.0.1:3222 --keep-regex '^/api/'
   --drop-regex 'login|logout|signup|password|session|token|oauth|csrf|uihelper'` -> kept 75 (GET 65, PUT 8, POST 1,
   DELETE 1; statuses 200 x65, 204 x9, 404 x1); dropped path 723 (server-rendered pages and assets), auth 4 (GET /login,
   GET /viewjs/login.js, POST /login, and the shopping-list page's own `GET /api/objects/uihelper_shopping_list??query[]=...`,
   whose doubled `?` and raw brackets would fail the same URI check, hence `uihelper` in the drop regex), non-json 0,
   big-body 0, other-origin 0. Credential grep on the scoped HAR: admin password literal 0, its base64 0, `hf_|ghp_|Bearer `
   0, `grocy_session` 0, `GROCY-API-KEY` 0. sha256 `4e673f0a954204d036082a7901bc0bdf4b116cea8b849a92ceaa88a87174662a`,
   144,824 bytes.
5. `python3 ~/showcase/envbuild.py all grocy`:
   - manifest: capture evidence `ev_853ed4f6409f2a62f73da27f0a83010aff0ba3f0365d71788c364cfade127838` (75 records,
     confidence observed); manifest with rules `ev_cd77ac50b20a04df27506d51dc91c8e252065c659fbbde30e497181ddbd95b1a`
     (confidence inferred, authority historical-reference), without rules
     `ev_e138d49a40b50d7af0cee950fe93ff3ce350cd4d244c71c2f2a68f4d4d19ba99`. Coverage complete-within-view 45/45.
   - bundle: 12 retrieval tasks from 38 candidates (`exclude_tools`: `system|user_settings|settings|config$|version$`).
   - smoke: passed in 28.3 s (`listed 45 tools, expected 45`).
   - eval: `openai/gpt-oss-120b:groq` 10/12, `zai-org/GLM-5.3-Flash:zai-org` 12/12, no provider errors.
   - card + dry publish: 24 episodes, `~/showcase/datasets/grocy` (README.md, bundles/, episodes/, raw/, tasks/; 6.6 MB).
6. `docker compose -p rea-grocy -f compose.yml down -v`; `grocy.full.har`, `.admin` and the probe files removed on the VM.

## Manifest facts
- 45 tools (GET 40, PUT 3, POST 1, DELETE 1), 22 templated groups, all 22 parameters from rea's built-in `numeric` rule;
  `after-uid-literal`, `opaque-token` and `sibling-variance` match nothing, so the no-rules manifest is also 45 tools.
  Grocy ids are small integers, and the entity names under `/api/objects/` are plain words (no digits, no hyphens), so
  sibling-variance does not fold `products`, `locations`, `chores` and the rest into one `{entity}` parameter: each
  entity keeps its own list and by-id tool, which is what gives 38 task candidates.
- 4 distinct query parameter names (`due_soon_days`, `limit`, `order`, `query[]`); 4 tools with a body shape
  (POST/PUT objects/products, two PUT user/settings tools); statuses 200, 204, 404; 0 excluded groups; unknowns
  authorization-model, response-semantics, state-transition; 9 limitations.
- UI-generated traffic that became tools: `GET /api/system/db-changed-time` (13 records: every page polls it),
  `GET /api/stock` and `/api/stock/volatile?due_soon_days=5` (stock overview), `/api/chores`, `/api/batteries`,
  `/api/tasks` (their overview pages), `/api/objects/equipment/1` (equipment page), and two
  `PUT /api/user/settings/datatables_state_<table>` tools (the pages save their table state; only two distinct keys
  were written in the final capture because the state of the other tables was already saved during the first run).
  With three or more such keys sibling-variance would merge them (hyphenated values under the plural `settings`).
- Replay detail visible in the episodes: asking a by-id tool for an id that was never recorded returns the closest
  record with `replay.exact_match: false` (location 3 came back as location 4 in gpt-oss's qa-03 episode).

## Tasks and episodes
- 12 tasks, all on by-id tools: recipe fulfillment (`product_names_comma_separated`), equipment, product locations,
  task, location entries (`[0].note`), product group, product (`description`), location, product stock details
  (`quantity_unit_price.name`), recipe, shopping list, store.
- gpt-oss-120b missed qa-03 (the generated wording "products locations with id 3" does not say the id is a product id; it
  went to the location routes) and qa-05 (right tool and data, answered with the second entry's note). GLM-5.3-Flash
  passed all 12. Both noted in `episode_notes`.

## Seeded facts usable for retrieval questions
Smoked Kelp Broth: "Jarred broth from Blue Heron Kitchen for the 22:00 shift change.", 8 tins at 3.40 EUR, due
2026-11-30, note "Delivered by Mina Okafor in a cool box". Granite Salt Flakes: batch SD-118, note "Batch SD-118 from the
east pans". Heron Rye Crackers: "packed by Tomas Vey". Copperfield Lamp Oil: winter budget 180 litres, 2 crates at 38.00.
Lamp Wick Bundle: 24 wicks cut to 14 cm. Chore Polish the Lighthouse Lens done 2026-10-14 by Ada Finch. Battery Foghorn
Remote Cell charged 2026-10-09, used in "Foghorn remote, gallery level". Task Recount the Granite Ledger crates (ledger
reference GL-2291, due 2026-11-02, Ada Finch). Recipe Tide-Table Kelp Stew uses Smoked Kelp Broth and Granite Salt Flakes.

## Rebuild, 2026-10-18

After review, the shared task generator was tightened: an answer must be a distinctive value that occurs in this app's seed and capture inputs, never the admin account's own identity, in at most 12 recorded responses, and unique across the tasks; each tool gets at most two tasks. Bundle, smoke, eval and card were re-run from the same capture. The bundle and eval numbers earlier in this file describe the first build; these are the published ones.

- bundle: 12 retrieval tasks from 35 recorded reads with an eligible field (up to two tasks per tool); field values rejected: not distinctive 20, admin identity 4.
- smoke: passed.
- eval `openai/gpt-oss-120b:groq`: 11/12 (misses: `qa-03-get_stock_locations_entries_by_id`: the model's answer did not contain the expected value).
- eval `zai-org/GLM-5.3-Flash:zai-org`: 12/12.
- card and dry publish: 24 episodes, dataset 6.6 MB.
