# Pinry 2.1.13 scenario capture notes (rea showcase, batch 4)

- App: `getpinry/pinry:2.1.13`, digest `getpinry/pinry@sha256:9a619749ec5246e04694adc479a135e654a7ac5f34c15d6d134d917a62b4889b`
  (amd64 only; Django 2.2.28, Django REST framework 3.13.1, Python 3.9.12; the image's pyproject.toml still reads 2.1.9).
  Licence: Simplified BSD (BSD-2-Clause), `docker/LICENSE.rst` in the image, "Copyright (c) Pinry Contributors".
  sqlite at `/data/production.db` (the image's generated local_settings), compose project `rea-pinry`, loopback-only port
  `127.0.0.1:3403 -> 80` (nginx in front of gunicorn). The bundled nginx site forwards `Host $host`, which drops the port, so
  every absolute link in the API read `http://127.0.0.1/...`; compose mounts the same site file with `Host $http_host` so links
  read `http://127.0.0.1:3403/...`. Healthy 8 s after `up`.
- Tooling on the VM: rea 6.7.0, Chromium 155.0.8059.79 (snap, launched headless by rea), node v24.22.0, python 3.12.3,
  docker 29.9.1, compose v5.6.0.

## Pipeline (all under ~/capture/pinry on the VM)
1. `docker compose -p rea-pinry -f compose.yml up -d`.
2. `python3 seed.py` (stdlib only, idempotent, about 4 s): five accounts through the sign-up API
   (`POST /api/v2/profile/users/`): pinners ada-finch, rui-castellanos, mina-okafor, tomas-vey, and the capture account
   rea-admin, which owns nothing seeded. Passwords generated at run time into `.admin` (mode 600). Each pinner's API token
   is used in memory only. 14 generated PNGs (stripes, gradients, rings, checks, diagonal seams, nested squares, dots,
   chevrons, a diamond, a sawtooth chart, window panes, an arch; 300x300 to 640x400 px plus one 320x560 portrait; 959 to
   3,805 bytes) uploaded through `POST /api/v2/images/` (multipart), pinned with a description naming the colours and
   pattern, tags and a source link (`POST /api/v2/pins/` with `image_by_id`), and collected into 5 boards
   (`POST /api/v2/boards/`, `PATCH ... pins_to_add`). 8 tags. Then rea-admin signs in with its own cookie jar; its
   `sessionid`, `csrftoken` and API token go to `.admin`. Writes `seed-ids.json` and generates `scenario.json` from the ids.
3. `rea capture-browser-scenario scenario.json --format json > pinry.capture.json`, with `APP_SESSION`, `APP_CSRF`,
   `APP_API_TOKEN` read from `.admin` inside the command and `APP_MARKER_GUARD=REDACTED` (see below). 38 s.
4. `python3 ~/showcase/envbuild.py all pinry`.

## The scenario in prose
Starts signed in: cookies `sessionid` (http-only) and `csrftoken` (readable, the SPA copies it into `X-CSRFToken`) from
declared secrets, and local storage `pinry.user` holding a cached profile (username, email, gravatar hash, link; no token,
expiry in 2100) so the SPA never calls `GET /api/v2/profile/users/`, whose body carries the API token. Then: home grid;
each of the 14 pin pages `/pins/{id}`; each of the 5 board pages `/pins/boards/{id}` followed by a direct `goto` of
`/api/v2/boards/{id}/`; the board lists of the four pinners `/boards/users/{name}`; mina-okafor's pins; three tag pages
(tile-glaze, core-sample, window-study); direct JSON gotos of 5 pins, the tag list, ada-finch's board autocomplete,
tomas-vey's public profile, `pins?tags__name=tide-gauge&limit=5` and `pins?submitter__username=rui-castellanos&limit=5`;
the search page with the Board filter and the text "Granite"; then the scratch board: header Create > Board, name
"Copperfield Annex scratch board", Create Board (POST 201); My boards page, hover the card (a click on its title), pencil,
rename to "... (renamed)", Save Changes (PATCH 200); hover, bin icon, OK in the confirm dialog (DELETE 204); the list
re-reads empty; home again; settle 1.5 s. 600 ms pause after every navigation. 148 actions (52 waits, 46 gotos, 36
wait_for, 10 clicks, 3 fills, 1 select_option), 149 steps completed, 0 failed.

## Capture numbers
568 transactions (GET 565, POST 1, PATCH 1, DELETE 1), every one with a response; 0 dropped events, no omissions.
78 hit `/api/` (63 with a JSON body; 14 are 301 redirects from `/api/v2/pins/{id}` to `/api/v2/pins/{id}/`).
Other origins: cdn.jsdelivr.net 64 (icon CSS and font) and gravatar.com 80 (avatar redirects and images for the
md5 of the `@example.test` addresses). Evidence 2,303,521 bytes, sha256 `921645f3...f42951`, evidence id
`ev_0878c47a60e7fec405c266932194cb3b41b645d635c765b4593c2c6e5d382ac5`. Body limit 20,000 bytes: 251 transactions keep no
response body (redirects, the 204, bodies over the limit).

## Manifest facts
12 tools (GET 9, POST 1, PATCH 1, DELETE 1), confidence inferred, authority controlled-replay, 23 templated groups, 5
`numeric` id parameters, 13 query-parameter names, 2 tools with a body shape (POST and PATCH boards), excluded groups:
34 ui-page-or-asset (SPA routes, JS, CSS, media renditions) and 4 other-origin. Without the opt-in rules the manifest is
identical (12 tools): the built-in numeric rule does all the templating. Tools: get_boards_auto_complete, get_boards,
post_boards, delete_boards_by_id, get_boards_by_id, patch_boards_by_id, get_pins, get_pins_by_id (the slashless URL, 301
only), get_pins_by_id_2 (the slashed URL with the JSON), get_profile_public_users, get_tags_auto_complete, and
get_manifest (the SPA's web app manifest `/manifest.json`, 32 records, excluded from task generation in app.json).
Unknowns: authorization-model, response-semantics, state-transition; 17 limitations.

## What was surprising about capturing this app with a scenario
- Pinry's user serializer returns the signed-in user's own API token wherever that user's object is serialized: the
  sign-in response, `GET /api/v2/profile/users/`, the `submitter` of every board and pin the user owns, and even
  `GET /api/v2/profile/public-users/?username=<self>` (the public view reuses the private serializer). So every UI write
  (POST/PATCH board) returns the token in its body. Seeding all content under other accounts keeps it out of the reads; the
  writes still carry it. Declaring the token as a secret makes REA replace it in the bodies, but REA's marker
  `[REDACTED:api_token]` is refused by the build runner's credential gate (it accepts only `*` masks or markers starting
  with `<`). Declaring the literal word REDACTED as one more secret makes REA fall back to its one-character marker `…`,
  which the gate accepts; the capture has `"token":"…"` in 5 bodies and `"token":null` for other users.
- The first capture used the brief's 262 kB body limit: 12.5 MB of Evidence, mostly icon CSS (3.6 MB, re-fetched on each
  of 33 page loads) and JavaScript (2.7 MB); the environment-manifest view then failed with `resource_constraint`
  ("retained state and temporary work exceed the projection representation budget", output_bytes 100663296). A 20 kB
  limit kept every JSON body (largest 13.8 kB) and passed.
- `wait_for` is strict: `.pin-card` matched 14 elements and failed the step; `>> nth=0` (Playwright selector chaining
  works in the css locator) fixed it. A failed step cancels the remaining 147 steps but still writes Evidence with exit 0.
- Navigating to `/` right after the start URL cancelled the home grid's first pins request; its record (no response)
  became the first record of `get_pins`, so the task generator skipped that tool. Waiting on the start page instead fixed it.
- Duplicate `step_id`s are refused up front with a precise path (`actions`, "Action step IDs must be unique").

## Seeded facts usable for retrieval questions
Pin descriptions (codes LR-, GL-, BH-, SD-, CA-) name colours and patterns, e.g. "Signal card LR-0417: amber over teal,
eleven horizontal stripes" (480x320, thumbnail 240x160), "Core sample GL-2291: banded granite with pink feldspar layers"
(320x560), "Tile glaze BH-118: cobalt blue fading to cream, kiln batch Kestrel", "Crate stencil SD-12: white diamond on
navy, marked for cold store", "Window study CA-09: arched pane, peach sky fading to lemon". Boards: Lighthouse Rota Signal
Colours, Granite Ledger Core Samples, Blue Heron Kitchen Tile Glazes, Saltmarsh Depot Crate Stencils, Copperfield Annex
Window Studies (3 pins each; LR-0431 is on two boards). Owners and emails `<name>@example.test`; tags as listed.
