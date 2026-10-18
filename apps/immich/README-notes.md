# Immich 3.3.3 capture notes (rea showcase, batch 2)

- App: `ghcr.io/immich-app/immich-server:v3.3.3`, digest
  `ghcr.io/immich-app/immich-server@sha256:bae7664ff3aa4c2c1fcbdcdd86b40b105643c5f861f3e6a770fc760089f25862`, version 3.3.3 from
  `GET /api/server/version` (`{"major":3,"minor":3,"patch":3}`), licence AGPL-3.0 (repository LICENSE). Database
  `ghcr.io/immich-app/postgres:14-vectorchord0.4.3-pgvectors0.2.0`
  (`ghcr.io/immich-app/postgres@sha256:bcf63357191b76a916ae5eb93464d65c07511da41e3bf7a8416db519b40b1c23`, the tag and digest the
  v3.3.3 release compose pins) and `docker.io/valkey/valkey:9.1.2-alpine`
  (`valkey/valkey@sha256:48332870af354a799964c0012ae1194a0bf2bf894eb508f945810596dc2d8d11`). Compose project `rea-immich`,
  loopback-only port `127.0.0.1:3207 -> 2283`; postgres and valkey have no host port. Uploads live in a named volume at `/data`.
- No machine-learning container. Immich 3.3 has no environment switch for it, so the seed sets
  `machineLearning.enabled=false` (and `newVersionCheck.enabled=false`, so the server makes no release check) through
  `PUT /api/system-config`. Without ML there is no face detection or smart search; people exist only through manual faces
  (`POST /api/faces`).
- The internal postgres password is generated at run time into `.db.env` (mode 600, deleted at teardown) and read by both
  services through `env_file`; it is not in compose.yml.
- Tooling on the VM: rea 6.6.0, playwright-core 1.58.2, Chromium 155.0.8059.79 (snap, default temp profile worked), node
  v24.22.0, python 3.12.3, Docker 29.9.1, compose 5.6.0, agent-env 0.9.1334.

## Pipeline (all under ~/capture/immich on the VM)
1. `docker compose -p rea-immich -f compose.yml up -d`: postgres and valkey healthy after about 5 s, `/api/server/ping` answered
   200 about 6 s later (the image's own healthcheck is kept).
2. `python3 seed.py` (stdlib only): `POST /api/auth/admin-sign-up` (Rea Admin, rea-admin@example.test, password generated
   into `.admin`, mode 600, password only), a bearer token from `POST /api/auth/login` kept in memory and revoked with
   `POST /api/auth/logout` at the end; system config change above; admin and user onboarding marked done; 2 users through
   `POST /api/admin/users`; 5 PNGs generated with zlib/struct (96x72, a base colour plus a diagonal stripe so each checksum
   differs) uploaded as multipart `POST /api/assets` with fixed `fileCreatedAt`, then `PUT /api/assets/{id}` for description,
   rating and favourite; 3 albums (two shared with users); 4 tags (one nested) assigned with `PUT /api/tags/assets`; 2 people
   with birth dates attached to photos through manual faces; 2 shared links with slugs; 1 album comment
   (`POST /api/activities`); a partner share; an external library with no import paths; 1 notification through
   `POST /api/admin/notifications`. Idempotent: a second run re-uploads as `duplicate` and creates nothing; it also removes
   any `Rea scratch album*` left by an interrupted capture. Writes `seed-ids.json` (ids only).
3. `NODE_PATH=~/capture/node_modules node immich/capture.mjs`: UI login at `/auth/login` (lands on `/photos`), then
   client-side navigation (an injected anchor click that the SvelteKit router intercepts) through `/albums`, the Night Shift
   album, `/sharing`, `/explore`, `/people`, one photo, `/tags`, `/admin/users`, `/user-settings`, `/photos`; then the scripted
   fetch sequence: users/me, users list, 2 users by id, admin users list, 2 admin users by id, albums list, 3 albums by id,
   albums filtered by `assetId`, 5 assets by id, tags list, 4 tags by id, people list, 2 people by id,
   `search/person?name=Mina`, `POST /api/search/metadata` (description "quarry"), shared links list, 2 shared links by id,
   album activities, partners, libraries list and by id, notifications; then a scratch album: POST (201), PATCH, GET,
   DELETE (204), GET (400), albums list again. The web app authenticates with its `immich_access_token` cookie, which the
   in-page `fetch` carries. Full HAR 11.4 MB (deleted after scoping).
   The first attempt used `page.goto` for every page: each full load re-runs about a dozen boot requests
   (`server/config`, `server/features`, `server/media-types`, `server/storage`, `users/me`, ...), which produced 254 API
   records and made scope_har.py's 150-record cap drop the largest bodies, i.e. the album and asset reads. Client-side
   navigation fixed it.
4. `python3 -I ~/capture/scope_har.py immich.full.har immich.scoped.har --origin http://127.0.0.1:3207 --keep-regex '^/api/(?!socket\.io)'`
   -> kept 120 (GET 116, POST 2, PATCH 1, DELETE 1); dropped other-origin 0, path 197, non-json 36 (thumbnails), auth 3
   (the `/auth/login` page, `POST /api/auth/login`, `GET /api/sessions`), big-body 0, over-max 0. The negative lookahead keeps socket.io polling (text/plain)
   out. Credential grep: admin password literal 0 hits, `hf_|ghp_|Bearer ` 0 hits. Scoped HAR sha256
   `a525d5143fb73344d07d44ce129c5d9be7d83ef9a2d5dfc2f453bfa80b0647d0`, 228,076 bytes; statuses 200 x117, 201, 204, 400.
5. `python3 ~/showcase/envbuild.py all immich`: capture Evidence `ev_1a9cf44e9f31412cd6f46b77293c666f4bfa1f6f9afccc430ca3b8d83937590a`
   (120 records, observed); manifest `ev_fda1218791c0c5ced99ef79739463e0a102755b2cdf71df008e93bd52e3ba617` (inferred) and
   no-rules manifest `ev_534b8b25b622007e06bda40b6a5c685a0fe74031d5103908cd8c9139c11e4948`; bundle with 12 retrieval tasks
   from 20 candidates; smoke passed (45 tools listed, replay 200); eval 12/12 for `openai/gpt-oss-120b:groq` and 12/12
   for `zai-org/GLM-5.3-Flash:zai-org`; card and dry publish to `~/showcase/datasets/immich` (6.75 MB).
6. `docker compose -p rea-immich -f compose.yml down -v`; `immich.full.har`, `.admin`, `.db.env`, `req.*.json` removed.

## Manifest facts
- 45 tools (GET 41, POST 2, PATCH 1, DELETE 1), 13 templated groups, 13 path parameters, all `uuid` (Immich ids are
  UUIDs, which REA's unconditional uuid rule templates). The three opt-in rules matched nothing: the no-rules manifest is
  identical in shape (45 tools, 13 `uuid` params). 22 distinct query-parameter names (albumId, assetId, direction, for,
  id, isOwned, isShared, isUpcoming, level, name, order, page, size, timeBucket, type, unread, userId, visibility,
  withDeleted, withHidden, withPartners, withStacked). 3 tools with a body shape (POST albums, PATCH albums/{uuid},
  POST search/metadata). Statuses 200/201/204/400; 0 excluded groups; coverage complete-within-view 45/45; 9 limitations;
  unknowns authorization-model, response-semantics, state-transition.
- The DELETE tool exists here (unlike Ghost): scope_har.py keeps 204 replies, so `delete_albums_by_uuid` is in the manifest.
- Immich answers a read of a missing album with 400, not 404 (`"Not found or no album.read access"`).
- `GET /api/notifications/{id}` returned 400 "Notification not found" for a notification that the list endpoint returns, so
  the capture reads notifications only through the list.
- UI-generated tools besides the scripted ones: server config/features/media-types/storage/about/version-history,
  public config, users/me/preferences, memories and memory statistics, timeline buckets and bucket, activities statistics,
  album map markers, asset OCR, faces by asset, search/explore, system-config and defaults, api-keys, cluster-groups users
  (3.x groups users into clusters). `exclude_tools` keeps these out of the task generator:
  `server|config|timeline|memories|preferences|onboarding|api_keys|cluster_groups|ocr|map_markers|statistics|version|explore`.

## Seeded facts usable for retrieval questions
Photos: lamp room (rating 5, favourite, "the brass lens was polished by Ada Finch"), north quarry (412 blocks, audit
reference GL-2291, face of Mina Okafor), Blue Heron Kitchen pass (36 covers, smoked kelp broth), Copperfield Annex stairwell
(banister colour Quarry Moss), Saltmarsh Depot cart 7 (retired by Tomas Vey, face of Tomas Vey). Albums Lighthouse Rota
Night Shift (shared with Ada Finch as editor; comment "Lens polished and wicks trimmed before the 22:00 hand-over."),
Granite Ledger Field Notes, Blue Heron Kitchen Menus (shared with Rui Castellanos as viewer). Tags Saltmarsh Depot,
Saltmarsh Depot/Cart Inventory, Copperfield Annex, Tide Tables. People Mina Okafor (1987-06-21), Tomas Vey (1979-11-03).
Shared links lighthouse-night-shift ("Night shift photos for the relief crew at Granite Point") and
copperfield-stairwell-repaint. Library Saltmarsh Depot Archive. Notification "Granite Ledger audit due".

## Tasks and results
All 12 generated tasks are fair single-exchange reads (people, users, shared link, asset people, tag, library, admin user,
album users, users list, tags list, users/me, libraries list); both models answered all 12 with one tool call each, so
`episode_notes` is empty.

## Rebuild, 2026-10-18

After review, the shared task generator was tightened: an answer must be a distinctive value that occurs in this app's seed and capture inputs, never the admin account's own identity, in at most 12 recorded responses, and unique across the tasks; each tool gets at most two tasks. Bundle, smoke, eval and card were re-run from the same capture. The bundle and eval numbers earlier in this file describe the first build; these are the published ones.

- bundle: 12 retrieval tasks from 18 recorded reads with an eligible field (up to two tasks per tool); field values rejected: admin identity 10, in too many responses 6, not in the seed inputs 3, not distinctive 1.
- smoke: passed.
- eval `openai/gpt-oss-120b:groq`: 12/12.
- eval `zai-org/GLM-5.3-Flash:zai-org`: 12/12.
- card and dry publish: 24 episodes, dataset 6.8 MB.
