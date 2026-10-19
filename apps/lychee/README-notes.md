# Lychee 6 capture notes (rea showcase, browser scenario capture)

- App: `lycheeorg/lychee:v6.10.4`, digest `lycheeorg/lychee@sha256:4a695e81c0751b1a024cb87384a6cf4cd7c84c96c528d92bcc7effc8ce075a1e`
  (amd64 image `sha256:c2576dcceb37ba9392ebca8bd684a952f6f1ebb60290d53b15c37a51ae6c8d34`), version `6.10.4` from the image's
  `version.md` and `GET /api/v2/Version`. MIT licence (LICENSE: Tobias Reich 2017-2018, LycheeOrg 2018-2025). sqlite at
  `/conf/database.sqlite` (named volume `lychee-conf`), compose project `rea-lychee`, loopback-only port `127.0.0.1:3402 -> 80`,
  `APP_URL=http://127.0.0.1:3402`. Healthy about 10 s after `up -d` (the entrypoint runs all migrations on first start).
- Tooling on the VM: rea 6.7.0, Chromium 155.0.8059.79 (snap), node v24.22.0, python 3.12.3, docker 29.9.1, compose 5.6.0,
  agent-env 0.9.1334.

## Pipeline (all under ~/capture/lychee on the VM)
1. `docker compose -p rea-lychee -f compose.yml up -d`.
2. `python3 seed.py` (stdlib only): generates the admin password into `.admin` (mode 600) and creates `rea-admin` with
   `php artisan lychee:create_user` run as www-data inside the container, the password passed through an environment
   variable. Then over the v2 API with a session cookie and the `X-XSRF-TOKEN` header: 6 albums (4 top level, 2 nested;
   description, copyright and licence each; Lighthouse Rota pinned), 14 generated PNG photos uploaded through the chunked
   `POST /api/v2/Photo` (one chunk each) with title, description, tags, licence and taken-at date set through
   `PATCH /api/v2/Photo`, 3 photos starred, 11 tags (created by tagging), 2 extra users (`ada.finch`, `tomas.vey`, random
   passwords that are thrown away). It blanks the `dropbox_key` setting (see below), keeps its session open and stores
   that session cookie in `.admin` as `session_secret`. Writes `seed-ids.json` (ids only). Idempotent; removes any
   `Rea scratch` album left by an interrupted capture.
3. `scenario.json` is generated from `seed-ids.json` (152 actions). The capture command:
   `APP_PASSWORD=... APP_SESSION=... rea capture-browser-scenario scenario.json --format json > lychee.capture.json`, both
   values read from `.admin` inside the command. 153 steps (start + 152), 50.6 s, all `completed`; 134 transactions
   (GET 129, POST 3, PATCH 1, DELETE 1), statuses 200 x130, 204 x3, 404 x1; 0 dropped events, no omissions.
4. `python3 ~/showcase/envbuild.py all lychee`.

## The scenario in prose
Starts at `/gallery` already signed in: the storage seed sets the `lychee_session` cookie from the declared secret
`session_cookie`. Waits for the album grid, then opens every album by clicking its card (Saltmarsh Depot, its child Signal
Box Nine, Lighthouse Rota, its child Lantern Gallery Repairs, Blue Heron Kitchen, Copperfield Annex), opens one photo in
each nested album (closed with Escape) and walks back with the header back button. Opens Tags from the left menu (closing
the drawer with Escape, otherwise it covers the page and the next click waits forever) and clicks 8 of the 11 tags, going
back to the tag list after each. Opens Timeline, Flow and Sharing from the menu. Returns to the gallery, opens search and
types two terms (`lamp`, `copper`; Lychee sends them base64-encoded as `terms=`). Finally creates `Rea scratch album`
through the + menu, opens its edit panel, changes the title and description and saves (PATCH), deletes it from the danger
zone (DELETE 204) and lands back on the gallery. Ends with the 1.5 s settle wait.

## Manifest facts
- With rules: 15 tools (GET 11, POST 2, PATCH 1, DELETE 1); 66 transactions excluded as `ui-page-or-asset` (HTML, JS,
  CSS, fonts, thumbnails); query parameter names album_id, date, page, tag_id, terms; body shapes on post_album,
  patch_album, post_metrics_photo; unknowns authorization-model, response-semantics, state-transition.
- Without rules: 27 tools. The difference is one rule hit: sibling-variance folds the 13 endpoints whose last path segment
  contains `::` (Auth::user, Auth::rights, Gallery::Init, Gallery::Footer, Gallery::getLayout, Gallery::getUploadLimits,
  Search::init, Sharing::all, Sharing::albums, Timeline::init, Timeline::dates, Flow::init, Users::count) into one
  `get_by_v2_id` tool with a `v2_id` parameter (34 records). These are distinct endpoints with distinct responses, not ids.
- The DELETE (204, no content type) and the photo-view `POST /api/v2/Metrics::photo` (204) are tools too.
- Every object id is a query parameter (`Album?album_id=...`, `Tag?tag_id=...`), so `get_album` holds 7 reads (6 seeded
  albums and the scratch album) and `get_tag` 8.

## Surprises capturing Lychee with a scenario
- Lychee's v2 API rejects any request without `Content-Type: application/json`, GETs included, so a `goto` of a JSON API
  URL is refused (HTTP 406, `UnexpectedContentType`: "Content type \"json\" required"). Every read in this capture comes from the SPA's own requests while navigating.
- The UI login (`POST /api/v2/Auth::login`, 204, no body) is fine for the credential gate now that REA's `[REDACTED:...]`
  marker is accepted, but the login page loads `GET /api/v2/Gallery::Init` anonymously first, and Lychee answers
  anonymous visitors with `"dropbox_api_key": "disabled"` whatever the setting is. That sentinel sits in a field named like
  a credential, so the gate refuses the capture. Starting signed in (storage seed) makes the first Init an admin one, which
  reports the real setting, and seed.py blanks that setting. A capture with the UI login was made; the gate's credential check flags exactly this field in it (`GET /api/v2/Gallery::Init res.dropbox_api_key`) and nothing else.
- The login route is throttled to 10 attempts per 60 minutes; exploration hit it. `php artisan cache:clear` resets it.
- PrimeVue renders duplicate header buttons (one hidden), so locators use `:visible >> nth=0`.
- 3 JavaScript bundles exceed the 256 KiB body limit and are recorded `unavailable` (body-size-limit); they are UI assets.
- Lychee 6 has no single-photo GET; a photo's facts (title, description, tags, licence, size variants with width and
  height, taken_at) arrive inside its album's response, the tag's response, search, timeline and flow.
- Colour palettes are a Supporter Edition feature (`enable_colour_extractions` level 1), so photos carry no palette.

## Seeded facts usable for retrieval questions
Albums: Saltmarsh Depot ("Rail sidings and tide gauges photographed for the Saltmarsh Depot ledger, spring census series.",
copyright Saltmarsh Depot Camera Club, CC-BY-4.0); Signal Box Nine (Tomas Vey's lamp check rota); Lighthouse Rota (pinned,
CC0, filed by Ada Finch); Lantern Gallery Repairs (brass rail polished in week 14); Blue Heron Kitchen (36 covers per
sitting, head cook Mina Okafor, all rights reserved); Copperfield Annex (approved by Rui Castellanos on site visit 3,
CC-BY-SA-4.0). Photos include "Tide gauge at dawn, siding four" (2.35 metres, SD-0412, 640 x 360), "Red aspect, box nine"
(lamp check 23:48), "Fresnel rings, shift three", "Horizon from the gallery rail" (visibility 18 nautical miles),
"Lamp oil swatch, winter budget" (180 litres), "Heron blue charger rings" (order HK-208), "Copper to verdigris swatch"
(paint code CA-31) and "Annex facade bands, option C".
