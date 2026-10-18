# Homebox 0.27.0 capture notes (rea showcase, batch 2)

- App: `ghcr.io/sysadminsmedia/homebox:0.27.0`, digest
  `ghcr.io/sysadminsmedia/homebox@sha256:d49f12caf25ce3fa7f44102bb74953f3dff2dfdad38d87bd9057f3f611e797bb`, version v0.27.0 from
  `GET /api/v1/status` (`build.version`, commit `bae3fb4e9b84672e4e64da15e57a14217aea7c13`), released 2026-10-17 and chosen
  over 0.26.2 because it patches 15 published security advisories. Licence AGPL-3.0 (repository LICENSE). sqlite3 at
  `/data/homebox.db` (the default driver) in the named volume `homebox-data`. Compose project `rea-homebox`, loopback-only
  port `127.0.0.1:3208 -> 7745`; healthcheck `wget -qO- http://127.0.0.1:7745/api/v1/status`, healthy within 3 s.
- 0.27.0 panics at start without `HBOX_AUTH_API_KEY_PEPPER` ("must be set to at least 32 bytes"). The pepper is generated at
  run time into `.hb.env` (48 random bytes, base64, mode 600, deleted at teardown) and read through `env_file`; it is not in
  compose.yml. Registration on, analytics off, GitHub release check off.
- The data model changed in the 0.26 line: items and locations are both **entities**, distinguished by an **entity type**
  (`isLocation`), and labels are now **tags**. The hint's "locations, labels, items with fields" maps to
  `/api/v1/entities` (location types and item types), `/api/v1/tags`, and `fields` on the entity.
  Registration creates default tags (Appliances, Electronics, ...) and default locations (Attic, Basement, Garage, ...);
  the seed deletes them so every name in the capture is invented.
- `PUT /api/v1/entities/{id}` replaces the whole entity: a partial body blanks description, quantity and the rest, so the
  seed always sends every field.
- The web app's API calls ride on the cookies set at login (no Authorization header in the browser), so the in-page
  `fetch` needs no header; the seed uses the bearer token from the login reply instead.
- Tooling on the VM: rea 6.6.0, playwright-core 1.58.2, Chromium 155.0.8059.79 (snap, default temp profile), node v24.22.0,
  python 3.12.3, Docker 29.9.1, compose 5.6.0, agent-env 0.9.1334.

## Pipeline (all under ~/capture/homebox on the VM)
1. `docker compose -p rea-homebox -f compose.yml up -d` (after generating `.hb.env`).
2. `python3 seed.py` (stdlib only): `POST /api/v1/users/register` (Rea Admin, rea-admin@example.test, password generated into
   `.admin`, mode 600, password only), a bearer token from `POST /api/v1/users/login` kept in memory and revoked with
   `POST /api/v1/users/logout` at the end; collection renamed to "Copperfield Annex Stores" in EUR (`PUT /api/v1/groups`);
   default tags and locations deleted; 2 entity types (Storage Room as a location type, Spare Part as an item type);
   5 tags with colours and descriptions (Lens Spares nested under Spare Parts); 4 locations (Granite Ledger Vault nested in
   Saltmarsh Depot); 6 items created with `POST /api/v1/entities` and completed with a full `PUT` (manufacturer, model,
   serial, purchase place, price and date, notes, warranty, insured flag, tags, text/number/boolean custom fields);
   3 maintenance entries (2 scheduled, 1 completed); 1 item template with a default location, tag and field.
   Idempotent by name; also removes any `Rea scratch*` entity left by an interrupted capture. Writes `seed-ids.json`.
3. `NODE_PATH=~/capture/node_modules node homebox/capture.mjs`: UI login at `/` (lands on `/home`), then client-side
   navigation through the Nuxt app's own router (`#__nuxt.__vue_app__...$router.push`) to `/locations`, the Saltmarsh Depot
   location, `/items`, the Fresnel kit item, the Tide Gauge maintenance tab, `/tags`, the Calibration Due tag,
   `/maintenance`, `/templates`, `/collection`, `/profile`, `/home`; then the scripted fetch sequence: users/self, groups,
   group statistics (totals, by location, by tag), entity types, tags list, 5 tags by id, entities list, 4 locations and
   6 items by id, 2 entity paths, 2 maintenance lists (`status=both`), all maintenance, the entity tree, `entities?q=lens`,
   `entities?tags=<Calibration Due>`, custom field names and values, templates list and template by id; then a scratch item:
   POST (201), PUT, GET, DELETE (204), GET (404), entities list again. Full HAR 5.8 MB (deleted after scoping).
   The asset-id lookup (`/api/v1/assets/{assetId}`) was planned but skipped: items get no asset id until the
   "ensure asset ids" action runs, and the capture does not run maintenance actions.
4. `python3 -I ~/capture/scope_har.py homebox.full.har homebox.scoped.har --origin http://127.0.0.1:3208 --keep-regex '^/api/v1/'`
   -> kept 91 (GET 87, PUT 2, POST 1, DELETE 1); dropped other-origin 0, path 209 (Nuxt assets and pages), non-json 0,
   auth 1 (`POST /api/v1/users/login`), big-body 0, over-max 0. Credential grep: admin password literal 0 hits,
   `hf_|ghp_|Bearer ` 0 hits. Scoped HAR sha256 `249dbf323faaf79dc6a91d856dc6e7ebc494f2e8bfa3b15af85de7af0bcbf2cf`,
   256,047 bytes; statuses 200 x88, 201, 204, 404.
5. `python3 ~/showcase/envbuild.py all homebox`: capture Evidence `ev_cb9cef1bb6902484524658e34cfb3aa220e1f06dd807e8da93c2089899872e1c`
   (91 records, observed); manifest `ev_12cd79fbad0e4c228684699815fdee9521ba2b9ede6c2b891c504603d1e4e457` (inferred) and
   no-rules manifest `ev_c3747d67e4a51ef2a5688ddc2829ae5649a7ac4234b61a555ad07d785b2e2e90`; bundle with 12 retrieval tasks
   from 15 candidates; smoke passed (28 tools listed, replay 200); eval 12/12 for `openai/gpt-oss-120b:groq` and 12/12
   for `zai-org/GLM-5.3-Flash:zai-org`; card and dry publish to `~/showcase/datasets/homebox` (6.7 MB).
6. `docker compose -p rea-homebox -f compose.yml down -v`; `homebox.full.har`, `.admin`, `.hb.env`, `req.*.json` removed.

## Manifest facts
- 28 tools (GET 24, PUT 2, POST 1, DELETE 1), 7 templated groups, 7 path parameters, all `uuid`; the opt-in rules matched
  nothing, so the no-rules manifest has the same 28 tools. 18 distinct query-parameter names (entityTypeIds, field,
  filterChildren, includeArchived, isLocation, matchAllTags, negateTags, onlyWithPhoto, onlyWithoutPhoto, orderBy,
  orderDirection, page, pageSize, parentIds, q, status, tags, withItems), most of them from the UI's own list calls.
  3 tools with a body shape (POST entities, PUT entities/{uuid}, PUT users/self/settings). Statuses 200/201/204/404;
  0 excluded groups; coverage complete-within-view 28/28; 9 limitations; unknowns authorization-model, response-semantics,
  state-transition.
- The second write tool is UI-generated: the web app writes the user's view settings (`PUT /api/v1/users/self/settings`)
  on first load.
- `GET /api/v1/entities/{uuid}` covers locations and items alike (one tool, 200 and 404), which is how the 0.27 API is
  shaped. `GET /api/v1/entities/{uuid}/path` reports `type: "location"` for an item at the end of the path.
- UI-generated tools besides the scripted ones: status, currencies (a 14 KB catalogue), groups/all, groups/members,
  users/self/settings, users/self/api-keys, entities with UI filters. `exclude_tools`
  (`status|currencies|settings|api_keys|members|groups_all|fields$|fields_values`) keeps those and the string-array field
  endpoints out of the task generator.

## Seeded facts usable for retrieval questions
Collection Copperfield Annex Stores (EUR). Locations Saltmarsh Depot ("the key is held by Tomas Vey"), Granite Ledger Vault
(inside the depot), Copperfield Annex Workshop ("run by Mina Okafor"), Blue Heron Kitchen Pantry. Items: Fresnel Lens
Polishing Kit (Finch and Vey Optics FLK-412, serial LR-0097-SD, 184.50, Lens Grade Second-order), Tide Gauge Logger
(Saltmarsh Instrument Works TGL-7, TG-2291-GL, Datum "Granite Point Chart Datum"), Copper Stockpot 40 L (Heron Forge,
quantity 2, lining Tin), Quarry Tally Counter (quantity 3, assigned to Rui Castellanos), Brass Lamp Wick Trimmer
(Heron Forge WT-22, blade Carbon), Spare Lamp Mantle Pack (24, Number 3 silk). Maintenance: Recalibrate tide gauge
(scheduled 2026-11-14), Re-tin the lining (completed 2026-08-20), Replace chamois cloths (scheduled 2026-12-01).
Template Lighthouse Spare Part. Tag descriptions such as "Needs recalibration before the spring census."

## Tasks and results
The 12 generated tasks read a maintenance description, a tag description, an entity path, a template, a location,
the templates list, users/self, the per-location and per-tag statistics, scheduled maintenance, the entity tree and the
UI's location list (`filterChildren=false&isLocation=true`). Both models answered all 12, so `episode_notes` is empty.

## Rebuild, 2026-10-18

After review, the shared task generator was tightened: an answer must be a distinctive value that occurs in this app's seed and capture inputs, never the admin account's own identity, in at most 16 recorded responses, and unique across the tasks; each tool gets at most two tasks. Bundle, smoke, eval and card were re-run from the same capture. The bundle and eval numbers earlier in this file describe the first build; these are the published ones.

- bundle: 10 retrieval tasks from 7 recorded reads with an eligible field (up to two tasks per tool); field values rejected: in too many responses 13, not distinctive 4, admin identity 2.
- smoke: passed.
- eval `openai/gpt-oss-120b:groq`: 10/10.
- eval `zai-org/GLM-5.3-Flash:zai-org`: 10/10.
- card and dry publish: 20 episodes, dataset 6.7 MB.
