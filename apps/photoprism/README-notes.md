# PhotoPrism capture notes (rea showcase, scenario capture)

- App: `photoprism/photoprism:261007`, digest `photoprism/photoprism@sha256:0f85369636ad99ca9a1c33f2d04df6c590802d16b7c33b4a1ea026b595be06d1`,
  build `261007-65faaae5d-Linux-AMD64-Plus`, AGPL-3.0 (LICENSE read from the repository). sqlite
  (`PHOTOPRISM_DATABASE_DRIVER=sqlite`), TensorFlow, faces, classification, places lookups, WebDAV and backups disabled,
  `PHOTOPRISM_HTTP_COMPRESSION=none`. Compose project `rea-photoprism`, loopback only `127.0.0.1:3401 -> 2342`, healthcheck
  `curl -sf /api/v1/status` (the image's own `photoprism status` probe could not reach `0.0.0.0:2342` and stayed unhealthy).
- Auth: `PHOTOPRISM_AUTH_MODE=public`. There is no login and the API answers the browser without credentials; the initial
  admin `rea-admin` still gets a generated password (from `.admin`, passed to compose through `PP_ADMIN_PASSWORD`) because
  the image requires one.
- Tooling: rea 6.7.0, Chromium 155.0.8059.79 (snap), python 3.12.3, Docker 29.9.1, Compose v5.6.0, Ubuntu 24.04 amd64.

## Pipeline (all under ~/capture/photoprism on the VM)
1. `python3 seed.py admin` writes `.admin` (mode 600: user, generated password).
2. `PP_ADMIN_PASSWORD="$(sed -n 's/^password=//p' .admin)" docker compose -p rea-photoprism -f compose.yml up -d` (healthy in ~10 s).
3. `python3 seed.py`: generates 12 PNGs with zlib + struct (gradients, stripes, rings, checks, discs; 200x160 to 640x427,
   0.7-6 KB), `docker cp`s them into the originals volume in three folders, `POST /api/v1/index`, then per photo
   `PUT /api/v1/photos/{uid}` (title, caption, taken date, coordinates, keywords, notes, subject, artist, copyright, licence),
   `POST /api/v1/photos/{uid}/label`, `POST /api/v1/photos/{uid}/like`; four albums through `POST /api/v1/albums`,
   `PUT /api/v1/albums/{uid}` and `POST /api/v1/albums/{uid}/photos`. Deletes any other album first. Stores the public
   session id and access token (`POST /api/v1/session`) in `.admin` as `public_session_token` and `public_access_token`.
   Writes `seed-ids.json`.
4. `python3 make_scenario.py` writes `scenario.json` from `seed-ids.json` (55 actions).
5. `PP_PUBLIC_SESSION="$(sed -n 's/^public_session_token=//p' .admin)" PP_PUBLIC_TOKEN="$(sed -n 's/^public_access_token=//p' .admin)" rea capture-browser-scenario scenario.json --format json > photoprism.capture.json`
   (9.5 s, 277 transactions, 0 dropped events, no omissions, all 56 steps completed).
6. `python3 ~/showcase/envbuild.py all photoprism`.

## The scenario in prose
Start on `/library/browse` and wait for the photo grid. `goto` the JSON of each of the 12 seeded photos
(`/api/v1/photos/{uid}`). Open `/library/albums`, then each seeded album's view `/library/albums/{uid}/view` (the UI fetches
`/api/v1/albums/{uid}` and `/api/v1/photos?s={uid}&...`). Visit `/library/labels`, `/library/folders`, `/library/favorites`
and a UI search `/library/browse?q=copper`. `goto` JSON searches: `/api/v1/photos?count=6&order=newest`, `q=heron`,
`label=tide-gauge`, `color=gold`, and `/api/v1/albums?type=folder`. Scratch album through the UI: on `/library/albums` click
Add Album (`POST /api/v1/albums`; PhotoPrism names it after the current month, "October 2026"), click its title to open the
edit dialog, fill title "Rea Scratch Album", location "Copperfield Annex" and a description, Save (`PUT /api/v1/albums/{uid}`),
open the album view by its preview, menu, Delete Album, confirm (`DELETE /api/v1/albums/{uid}`, 200 with the album JSON).
Re-open `/library/albums`, settle 1.5 s.

## Surprises with a scenario capture of this app
- Public mode still has a session: the UI's boot call `GET /api/v1/session` answers `access_token`, `id` (the same value)
  and `token_type: Bearer`, echoing the `X-Auth-Token` the UI sends (curl with a random header gets that random value
  back), plus a stable 64-hex `session_id`. Both are fixed values of public mode (identical after a full redeploy with
  fresh volumes). seed.py reads them through `POST /api/v1/session` into `.admin`; the scenario declares them as secrets
  `public_session` and `public_access_token`, and REA replaced them in every recorded body (12 session replies) with
  `[REDACTED:public_session]` / `[REDACTED:public_access_token]`. A grep of the capture for either value finds nothing.
- First attempt (before the runner accepted redaction markers): the credential gate refused
  `GET /api/v1/session res.access_token`, so that build used `max_network_body_bytes: 12288` to keep the session body out
  (and with it the config and the 12-photo browse list). It was rebuilt from a fresh deployment once the runner learned
  `[REDACTED:...]`; this capture keeps every JSON body and uses `max_network_body_bytes: 65536` only to drop the 1.9 MB app
  bundle, CSS and fonts.
- With the default `max_total_event_allocation_bytes` (16 MiB) an early run dropped 282 events (the last 68 transactions,
  including all three writes) because every full page load re-records the app bundle and assets; 64 MiB gives 0 dropped.
- A click whose locator never matches hangs the capture with no timeout: the album view's menu button shares its class
  with the album list's, the `wait_for` matched the list's button before the SPA navigated, the menu that opened had no
  Delete item, and the `click` on `.action-delete` waited 7.5 minutes until I killed REA (it then reported `cancelled`
  with a partial observation). Every click, fill and wait now carries `timeout_ms: 20000`, and the scenario waits for the
  album view's layout toggle (`button.action-view-list`) instead.
- Album cards hide their selection checkbox until hover (`visibility: hidden`) and the scenario has no hover action, so
  the list-page delete path is unreachable; the album view menu's Delete Album is what the scenario uses. A favourite click
  on the freshly renamed card did not fire reliably and was dropped.
- `PUT /api/v1/photos/{uid}` silently ignores `Details` (keywords, notes, artist) unless `Details.PhotoID` is set, and rejects
  `TakenAtLocal` without a zone with a generic 400 "Unable to do that".
- `goto` destinations take query entries as `{"name": ..., "value": {"source": "literal", "value": ...}}`; a bare string
  value fails validation with `expected: object`.
- 5 thumbnail requests end `net::ERR_ABORTED` because the next `goto` leaves the page while the grid is still loading;
  they are recorded without a response and excluded from the manifest.

## Manifest facts
- With rules: 13 tools (GET 10, POST 1, PUT 1, DELETE 1), 6 templated groups; params opaque-token 5 (albums/{uid} GET, PUT,
  DELETE and its thumbnail, photos/{uid}) and hex 1 (thumbnail hash); 33 query-parameter names; 2 tools with a body shape
  (POST albums, PUT albums/{uid}); 21 groups excluded as UI pages or assets; unknowns authorization-model,
  response-semantics, state-transition; confidence inferred, authority controlled-replay.
- Without the opt-in rules: 28 tools (each photo and album id stays a literal tool).
- `get_config`, `get_session` (bodies with the two redaction markers) and `get_manifest` are tools; `exclude_tools` keeps
  them out of task generation. Images (`/api/v1/t/{hash}/public/tile_500`) are tools too, but carry no JSON.
- Retrieval tasks: 10 from 5 candidate tools (photos/{uid}, albums/{uid}, albums, photos, labels), each with its recorded
  query arguments. Eval: gpt-oss-120b 10/10, GLM-5.3-Flash 10/10. Smoke passed.

## Seeded facts usable for retrieval questions
Site "Saltmarsh Depot Archive". Photos (title / artist / main colour PhotoPrism derived): "Saltmarsh Depot dawn sky gradient"
(Ada Finch, notes "Frame SD-0312 from the depot roof camera"), "Depot tide board stripes", "Teal ripple rings on the slipway"
(Rui Castellanos), "Gold and slate crate checks" (gold, notes "Crate lot SD-77 counted by Rui Castellanos"), "Copperfield
Annex kiln glow" (Mina Okafor), "Copper disc on cream", "Annex diagonal awning" (Tomas Vey), "Green ledger spines" (green),
"Blue Heron Kitchen plate rings", "Heron saffron broth gradient" (notes "Broth batch BH-12 for the tide-table menu"), "Teal
tablecloth checks", "Lantern moon over the heron pier" (blue). Albums: Saltmarsh Depot Survey (Survey, favourite), Copperfield
Annex Workshop (Workshop), Blue Heron Kitchen Tasting Night (Kitchen), Granite Ledger Colour Study (Study, location Lighthouse
Rota, favourite, 5 photos). Labels: Tide Gauge, Signal Paint, Water Pattern, Crate Lot, Kiln Light.
