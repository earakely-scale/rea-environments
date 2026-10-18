# Navidrome 0.64.2 capture notes (rea showcase, batch 2)

Navidrome is vm3's assigned alternate. It replaces Healthchecks (see the last section): that app's web UI renders HTML on
the server, and its REST API has too few JSON reads with string fields to reach 10 retrieval tasks.

- App: `deluan/navidrome:0.64.2`, digest
  `deluan/navidrome@sha256:38dc2727bfcfd5ede290f8ada114fc90368146f265ae4701ddddbcbe2a44ee52`, version 0.64.2 (release
  2026-09-24), licence GPL-3.0 (repository LICENSE). sqlite in `/data` (named volume `nd-data`). Compose project
  `rea-navidrome`, loopback-only port `127.0.0.1:3233 -> 4533`; healthcheck `wget -qO- http://127.0.0.1:4533/ping`.
  External services, Last.fm, ListenBrainz, Deezer and the insights collector are off; sharing and star ratings are on;
  periodic scans are off (`ND_SCANNER_SCHEDULE=0`), the seed starts the one scan it needs.
- The library is generated, not downloaded: `seed.py music` writes 10 MP3 files under `./music` (mounted read-only at
  `/music`) before the first start. Each file is an ID3v2.3 tag (title, artist, album artist, album, track n/N, year,
  genre, composer, comment; latin-1 text frames) followed by 5-14 seconds of silent MPEG-1 Layer III frames (128 kbit/s,
  44.1 kHz, 417-byte frames with all-zero side information), built with `struct` only. Navidrome's TagLib scanner reads
  them as 128 kbit/s stereo MP3s with the right durations. 1.0 MB for the whole library.
- Auth: the web app keeps a JWT in `localStorage.token` and sends it as `x-nd-authorization: Bearer ...`; the capture
  reads it in the page and does the same (request headers are stripped by scope_har.py). The Subsonic API under `/rest`
  authenticates with `u`, `t` (md5 of password + salt) and `s` in the **query string**, which a HAR keeps, so `/rest` is
  outside `keep_regex` (`^/api/`); the UI's own `/rest` calls (cover art, album/artist info, scan status, now playing) are
  dropped as `path`.
- Tooling on the VM: rea 6.6.0, playwright-core 1.58.2, Chromium 155.0.8059.79 (snap, default temp profile), node v24.22.0,
  python 3.12.3, Docker 29.9.1, compose 5.6.0, agent-env 0.9.1334.

## Pipeline (all under ~/capture/navidrome on the VM)
1. `python3 seed.py music`, then `docker compose -p rea-navidrome -f compose.yml up -d`.
2. `python3 seed.py`: `POST /auth/createAdmin` (user `rea-admin`, password generated into `.admin`, mode 600, password only;
   a second run gets 403 and logs in), `POST /auth/login` for a JWT kept in memory; Subsonic `startScan` and
   `getScanStatus` until 10 tracks are in; then through the native API: the admin's display name and email
   (`PUT /api/user/{id}`), the library renamed to "Saltmarsh Depot Archive" (`PUT /api/library/1`), user `mina.okafor`,
   2 playlists (`POST /api/playlist`, `POST /api/playlist/{id}/tracks`), 2 internet radio stations on `example.test` URLs,
   2 shares (an album and a playlist); stars and ratings through Subsonic `star` and `setRating`. Idempotent by name.
   Writes `seed-ids.json` (ids only). The seed's Subsonic calls register a player "rea-seed [Python-urllib]", which shows
   up in `/api/player`.
3. `NODE_PATH=~/capture/node_modules node navidrome/capture.mjs`: UI login at `/app/` (lands on `#/album/recentlyAdded`),
   then hash-route views (no reloads): albums, the Tide Tables album, artists, the Ada Finch Quartet artist, songs,
   playlists, the Night Mix playlist, radios, shares, users, players, libraries, albums; then the scripted fetch sequence:
   album list and 3 albums by id, artist list and 5 artists by id (album artists and composers), composer filter
   (`role=composer`), song list and all 10 songs by id, songs of one album (`album_id`), a title filter (`title=lamp`),
   the playlists of one song, genres, an album name filter (`name=tide`), genre tags (`/api/tag?tag_name=genre`), playlist
   list, 2 playlists and their tracks, radio list and 2 radios, share list and 2 shares, user list and 2 users, library
   list and library 1; then a scratch playlist: POST (200, `{"id": ...}`), PUT, GET, DELETE (200), GET (404), playlist
   list again. Full HAR 7.3 MB (deleted after scoping).
4. `python3 -I ~/capture/scope_har.py navidrome.full.har navidrome.scoped.har --origin http://127.0.0.1:3233 --keep-regex '^/api/'`
   -> kept 71 (GET 68, POST 1, PUT 1, DELETE 1); dropped other-origin 12 (`blob:` cover images), path 60 (`/app` assets,
   `/rest`), non-json 1 (`/api/events`, a server-sent event stream), auth 1 (`POST /auth/login`), big-body 0, over-max 0.
   Credential grep: admin password literal 0 hits, `hf_|ghp_|Bearer ` 0 hits. Scoped HAR sha256
   `b516aa95b4651db7489d229659785af72dc85c906793b52919cd759f191dedf5`, 222,808 bytes; statuses 200 x70, 404.
5. `python3 ~/showcase/envbuild.py all navidrome`: capture Evidence
   `ev_3995896845c068943afaf1c5bb032f2e6f303a279f4c24c26fae001311ec22b7` (71 records, observed); manifest
   `ev_e37526a3edbe955837e258ccc596d67628ca77f09f9b2a6eb2b27a967ab57f67` (inferred) and no-rules manifest
   `ev_475574445675330cc4afb2c4bd7951e3438bad141740bcba49b1b89248329bf9`; bundle with 12 retrieval tasks from 19 candidates;
   smoke passed (25 tools listed, replay 200); eval 12/12 for `openai/gpt-oss-120b:groq` and 12/12 for
   `zai-org/GLM-5.3-Flash:zai-org`; card and dry publish to `~/showcase/datasets/navidrome` (6.66 MB).
6. `docker compose -p rea-navidrome -f compose.yml down -v`; `navidrome.full.har`, `.admin`, `req.*.json` and the generated
   `music/` removed.

## Manifest facts
- This is the batch's clearest case for the opt-in rules. Navidrome ids are 22-character mixed-case base62 strings, which
  none of REA's four format rules match and which `opaque-token` rejects (it wants lowercase). Without rules every id read
  is its own literal tool: **46 tools** (GET 43), 1 parameter (`library/{numeric}`). With `sibling-variance` the literal
  siblings collapse into 8 templated parameters (album, artist, playlist, playlist tracks, radio, share, song, user):
  **25 tools** (GET 22, POST 1, PUT 1, DELETE 1), 9 templated groups, params sibling-variance 8 and numeric 1.
- The scratch playlist's `PUT` and `DELETE` stay literal tools (`put_playlist_5t7xnti2owmqvpny2o4bvf`,
  `delete_playlist_5t7xnti2owmqvpny2o4bvf`): each method saw one id, so there is no sibling to vary against; its GET merged
  into `get_playlist_by_playlist_id`. `GET /api/song/{id}/playlists` also stays literal (one value) and answers with
  `text/plain`, so the task generator skips it.
- 12 distinct query-parameter names (`_end`, `_order`, `_sort`, `_start`, `album_id`, `artist_id`, `name`, `playlist_id`,
  `role`, `seed`, `tag_name`, `title`), the react-admin list convention. 2 tools with a body shape (POST playlist, PUT
  playlist). Statuses 200/404; 0 excluded groups; coverage complete-within-view 25/25; 9 limitations; unknowns
  authorization-model, response-semantics, state-transition.
- Composers become artists: the library has 3 album artists and 3 composer artists (Mina Okafor, Ada Finch, Rui
  Castellanos), and the UI's artist list filters `role=albumartist`.
- `exclude_tools` = `transcoding|player|keepalive|translation|insights|config` keeps the transcoding catalogue and the
  player list (user agents and a bridge IP) out of the task generator.

## Seeded facts usable for retrieval questions
Albums Tide Tables (The Saltmarsh Lanterns, 2024, Coastal Folk), Night Shift at the Lamp Room (Ada Finch Quartet, 2025,
Chamber Jazz), Quarry Hymns (Granite Ledger Choir, 2023, Choral). Ten track titles such as Lamp Oil Waltz (rated 5),
Audit on the Fourteenth (rated 3), Spring Tide at Granite Point (starred), each with an ID3 comment. Playlists Lighthouse
Rota Night Mix ("For the 22:00 to 06:00 shift; keep the volume under the foghorn.") and Blue Heron Kitchen Prep. Radios
Copperfield Annex Radio and Granite Point Shipping Forecast. Shares "Quarry Hymns for the Granite Ledger auditors" and
"Night Mix for the relief crew at Granite Point". Users Rea Admin and Mina Okafor. Library Saltmarsh Depot Archive.

## Tasks and results
The 12 generated tasks read a radio, a user's library, the library, an artist, a playlist's tracks, a playlist, a share,
a song, an album's genre, the album-artist list, the user list and the playlist list (the last two with the UI's own
react-admin query, e.g. `_end=0&_sort=name&_start=-100`). Both models answered all 12, so `episode_notes` is empty.

## Why Healthchecks was replaced
Serious attempt on `healthchecks/healthchecks:v4.4` (BSD-3-Clause, digest
`healthchecks/healthchecks@sha256:aa08a61b0dcfd83f1332eab195d5cec1b595ae076eb8388cadf8a3d597114f9b`, sqlite, port 3209):
superuser, project, read-write API key and 2 email integrations through `manage.py shell` on stdin, 5 checks through
`POST /api/v3/checks/`, pings with distinctive user agents and bodies, one check paused; UI login and 9 pages, then every
JSON read the API has. The web UI is server-rendered HTML; its only JSON traffic is the status polling of the checks list
and details pages. The REST API (`/api/v1|v2|v3/`, the same routes three times, which sibling-variance would fold back
together) has 12 routes, of which only checks list, single check, pings and channels carry readable strings (flips are
timestamps and booleans, badges are URLs, ping bodies are `text/plain`, `status/` is the text `OK`, a check by unique key
needs a read-only key). The scoped HAR had 27 records (the manifest step requires 40) and the manifest view built from it
had 12 tools; `gen_tasks.py` found **5 task candidates**, against a bar of at least 10 retrieval tasks. Torn down with
`down -v`; secrets and the full HAR deleted.

## Rebuild, 2026-10-18

After review, the shared task generator was tightened: an answer must be a distinctive value that occurs in this app's seed and capture inputs, never the admin account's own identity, in at most 12 recorded responses, and unique across the tasks; each tool gets at most two tasks. Bundle, smoke, eval and card were re-run from the same capture. The bundle and eval numbers earlier in this file describe the first build; these are the published ones.

- bundle: 12 retrieval tasks from 11 recorded reads with an eligible field (up to two tasks per tool); field values rejected: in too many responses 63, not distinctive 5, admin identity 7.
- smoke: passed.
- eval `openai/gpt-oss-120b:groq`: 12/12.
- eval `zai-org/GLM-5.3-Flash:zai-org`: 12/12.
- card and dry publish: 24 episodes, dataset 6.7 MB.
