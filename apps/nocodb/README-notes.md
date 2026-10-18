# NocoDB capture notes

App: NocoDB community edition, image `nocodb/nocodb:latest` resolved to
`sha256:27d2fd14670db892ac721849d4f071edce47e386a1e74c921a0162644b9c213d`, version string `2026.09.1`
(from `GET /api/v1/version`: `{"currentVersion":"2026.09.1","releaseVersion":"2026.09.1"}`; the same value is in
`GET /api/v2/meta/nocodb/info`). SQLite storage (the image default, volume `nocodb_data` at `/usr/app/data`).
Compose project `rea-nocodb`, host binding `127.0.0.1:3103 -> 8080`, telemetry disabled (`NC_DISABLE_TELE=true`),
`NC_PUBLIC_URL=http://127.0.0.1:3103`. Readiness: `GET /api/v1/health` -> `{"message":"OK",...}`.

Tooling on the VM: Ubuntu 24.04, node v24.22.0, playwright-core 1.58.2, snap Chromium 155.0.8059.79
(`chromium.launchPersistentContext` with `executablePath=/snap/bin/chromium`, `--no-sandbox --disable-gpu`, a profile
dir under `/home/ubuntu/capture/nocodb/profile`; a plain `chromium.launch` was not needed), docker 29.9.1 / compose
v5.6.0, rea 6.6.0, python 3.12.3.

## Seeding (seed.py, v2 meta/data API, idempotent)

1. `POST /api/v1/auth/user/signup` with `rea-admin@example.test` and a password generated at run time
   (`secrets.token_urlsafe(18) + "Aa1!"`), stored only in `.admin` (mode 600, deleted at the end). The first signup
   creates the super admin. On re-runs signup returns 400 and the script falls back to `POST /api/v1/auth/user/signin`.
   The JWT is kept in process memory and sent only as the `xc-auth` header.
2. `POST /api/v2/meta/bases` -> base "Lighthouse Rota" (`p6xibd8cmh0sl25`).
3. `POST /api/v2/meta/bases/{baseId}/tables` x2:
   - "Vessels" (`m4eijvqyydf5ont`): `name` SingleLineText (display value), `flag` SingleLineText, `length_m` Number,
     `status` SingleSelect with options Active / In Port / Laid Up (passed as both `dtxp` and `colOptions.options`;
     the options came out as expected). Default grid view `vwde0b34abk8eh18`.
   - "Port Calls" (`mpdpidv9yj7jesi`): `vessel` SingleLineText (display value; a plain text reference, not a Links
     column), `berth` SingleLineText, `eta` Date, `cranes` Number. Default grid view `vw8656n6h6p3yell`.
   NocoDB adds its system fields (Id, CreatedAt, UpdatedAt, nc_created_by, nc_updated_by, nc_order, __nc_deleted).
4. `POST /api/v2/tables/{tableId}/records` with 8 rows each (vessels: Granite Ledger, Blue Heron, Saffron Tide,
   Copper Lantern, Northern Quill, Pale Meridian, Ember Compass, Silver Anvil; port calls: one per vessel, berths
   A1/B4/A3/C2/B1/A2/C1/B3, ETAs 2026-10-20..27, 1-4 cranes). Verified afterwards: `totalRows` 8 in both tables,
   `where=(status,eq,Active)` -> 4 rows.

## Capture (capture.mjs)

Playwright HAR with `recordHar: {content: "embed", mode: "full"}`. Flow:

1. `GET /` redirects to the signin form (`#form_item_email`, `#form_item_password`, `button[type=submit]`); login
   through the UI; the dashboard is served at `/` in this version (`dashboardPath: "/"`, history-mode routes).
2. `GET /nc/{baseId}` (base overview, full page load).
3. Sidebar click on "Vessels" and then "Port Calls" (client-side navigation to
   `/nc/{baseId}/{tableId}/{viewId}/{slug}`; the click is verified by `waitForURL` on the table id, with a direct
   visit as fallback). The first attempt of this run used the draggable handle alone and did not navigate; the
   script now tries the handle, its parent and the tree-item ancestor in turn. In this run the third target
   navigated for both tables.
4. `...?page=field` on the Port Calls view URL = the table details (fields) page (a full page load).
5. Scripted `fetch` sequence from inside the page (37 calls, `xc-auth` read from the UI's `localStorage`
   `nocodb-gui-v2` entry): version, nocodb info, bases list, base by id, base info, base tables, table meta x2,
   table views x2, records lists (`limit=25`), `where=` filters on status / flag / cranes+sort / berth like+fields,
   `limit=3&offset=3&sort=-length_m`, record counts (plain and with `where`), single records (vessels 1, 3, 8; port
   calls 2, 5), then a scratch vessel "Scratch Pilot": POST (Id 9), PATCH, GET, `where=(name,eq,Scratch Pilot)`,
   DELETE, GET again (404), and a final count.

117 same-origin `/api/` requests were seen by the page; the raw HAR had 2,676 entries (64.9 MB, mostly the SPA
bundles) and was deleted after scoping.

## Scoping and scrubbing

`scope_har.py nocodb.har nocodb.scoped.har --origin http://127.0.0.1:3103 --keep-regex '^/api/'
--drop-regex 'login|logout|signin|signup|password|session|token|oauth|csrf|/auth/' --max-records 150`
(default `--max-body 60000`). The default drop regex does not match NocoDB's `/api/v1/auth/user/signin` (whose
response body carries the JWT) or `/api/v1/auth/user/me`, hence the added `signin` and `/auth/` terms.

Result: kept 105 (GET 80, POST 23, PATCH 1, DELETE 1), 324,797 bytes,
sha256 `fe7e31fddd225d7bd00ecd8739fd0a2a474ef7a36aa79398900bc81499093f65`. Dropped: 2,534 same-origin non-`/api/`
(SPA shell, bundles, fonts), 24 other-origin (6 to `app.chatwoot.com`: the support widget the NocoDB UI loads,
`GET /packs/js/sdk.js` 200 and `GET /widget` 404, no data of ours; 18 `blob:` URLs), 11 auth
(`POST /auth/token/refresh` x1, `POST /api/v1/auth/user/signin` x1, `GET /api/v1/auth/user/me` x9), 2 big-body
(`GET /api/v2/internal/nc/{baseId}?operation=workflowNodes`, 262,203 bytes each: the workflow node catalog).

Credential grep on the scoped HAR (counts only): admin password literal 0, `hf_` 0, `ghp_` 0, `Bearer ` 0,
`eyJ` (JWT prefix) 0, `xc-auth` 0, `refresh_token` 0. Headers other than content-type/accept and all cookies are
removed by the scoping tool; NocoDB sends the JWT only as the `xc-auth` header and the refresh token only as a
cookie, so nothing auth-shaped remained in bodies or query strings.

## rea

- `rea inspect-web-network-capture /home/ubuntu/capture/nocodb/nocodb.scoped.har har --format json`
  -> `nocodb.capture.json`, evidence `ev_c2296ec7318f8978720a75499d6fb34a6c5f5f8943f2da32acc1eaaad450e08e`,
  105 records, confidence `observed`.
- `rea inspect-analysis-view req.json --format json` with
  `{"source":{"kind":"inline","evidence":<capture.json>},"view":{"kind":"environment-manifest","template_rules":["after-uid-literal","opaque-token","sibling-variance"]}}`
  -> `nocodb.manifest.json`, evidence `ev_12b6ec59bee2946b7b74a675d71335b5c56a2c026712583c6342ca0a752d8616`,
  coverage `complete-within-view` 28/28 (no resource_constraint; the default scope sizes were enough),
  confidence `inferred`, authority `historical-reference`.
  - 28 tools: GET 23, POST 3, PATCH 1, DELETE 1. 20 templated groups, 0 excluded groups.
  - 25 path parameters: 24 from `opaque-token` (base, table and view ids such as `p6xibd8cmh0sl25` are 15-char
    lowercase alphanumerics), 1 `numeric` (rea's built-in rule, the record id). `after-uid-literal` and
    `sibling-variance` contributed none here.
  - 13 distinct query parameter names: fields, includeM2M, includeSortAndFilterColumns,
    include_button_filter_columns, include_row_color, is_read, limit, offset, operation, parent_id, sort, tableId,
    where.
  - Statuses observed: 200 and 404 (`GET /api/v2/tables/{uid}/records/{numeric}` after the delete, and
    `GET /api/v2/meta/workspaces/nc/integrations`, which 404s in the community edition).
  - Body shapes inferred for the two POST internal batch tools (`{operations: array}`) and the record create
    (`{flag, length_m, name, status}`).
  - Unknowns stated by the view: authorization-model, response-semantics, state-transition.
- Same view without `template_rules` -> `nocodb.manifest.norules.json`, evidence
  `ev_98629f8a878998eb1e29ca6a1800dc5fa0f2e1ef92db8f87bbc90e56dbb7b961`: 35 tools (GET 30, POST 3, PATCH 1,
  DELETE 1), 2 templated groups, 2 parameters (both the built-in numeric record id). Without the rules every
  base/table/view id stays a literal path segment, so the two tables produce separate tools for the same route
  (e.g. `/api/v2/tables/m4eijvqyydf5ont/records` and `/api/v2/tables/mpdpidv9yj7jesi/records`).

## Observations

- The UI mixes three API generations: `/api/v1/db/meta/projects/...` and `/api/v1/db/data/noco/{base}/{table}/views/{view}`
  for the grid, `/api/v2/meta/...` and `/api/v2/tables/{id}/records` (what the scripted sequence used), and a
  `/api/v2/internal/{workspace}/{base}?operation=...` RPC-style endpoint (GET operations `baseSchema`,
  `documentList`, `workflowNodes`, `baseSectionList`, `viewList`, `tableGet`; POST `operation=batch`).
- Two workspace literals were not templated: `wqsswtut` in `/api/v2/internal/wqsswtut/{uid}` and `nc` in
  `/api/v2/internal/nc/{uid}` and `/api/v2/meta/workspaces/nc/integrations` (single observed value each and not
  opaque-token shaped), so the internal endpoint appears as two POST tools.
- Polling noise kept on purpose (it is real app traffic and small): `GET /api/v1/notifications` (6 records,
  `is_read=true|false`), `GET /api/v1/license/status`, `GET /api/v1/workspaces`.
- The grid in this version is canvas-rendered (no DOM rows), so the "expand record" UI action was not scripted;
  single-record reads come from the scripted `GET .../records/{id}` calls.

## Teardown

`docker compose -p rea-nocodb -f compose.yml down -v`; the raw HAR with bundles, `.admin`, `ids.json`, the probe
scripts and the Playwright profile dirs were removed from the VM. Only the scoped HAR and the rea outputs were copied
back. Deliverables total well under 1 MB.
