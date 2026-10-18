# Jellyfin 10.10.7 capture notes (rea showcase)

- App: `jellyfin/jellyfin:10.10.7` (the newest 10.10 tag, as the hint asked), digest
  `jellyfin/jellyfin@sha256:7ae36aab93ef9b6aaff02b37f8bb23df84bb2d7a3f6054ec8fc466072a648ce2`, version `10.10.7`
  (`GET /System/Info/Public`). Library database in the `jellyfin-config` volume, cache in `jellyfin-cache`, the generated
  media bind-mounted read-only at `/media`. Compose project `rea-jellyfin`, loopback-only `127.0.0.1:3224 -> 8096`,
  `JELLYFIN_PublishedServerUrl=http://127.0.0.1:3224`, the image's default user (root) so it can write its volumes.
- Licence: GPL-2.0 (`LICENSE` of jellyfin/jellyfin and jellyfin/jellyfin-web at tag v10.10.7; the image itself ships
  only the jellyfin-ffmpeg copyright file). Only Jellyfin's JSON responses over synthetic files are in the dataset.
- Tooling on the VM: rea 6.6.0, playwright-core 1.58.2, Chromium 155.0.8059.79 (snap, plain `chromium.launch`),
  node v24.22.0, python 3.12.3, docker 29.9.1, compose 5.6.0, Ubuntu 24.04 amd64.

## Pipeline (all under ~/capture/jellyfin on the VM)
1. `python3 seed.py` first writes `media/` with the Python stdlib only (about 45 KB): five one-second silent WAV tracks
   (8 kHz, 8-bit) carrying RIFF INFO tags (INAM title, IART artist, IPRD album, IGNR genre, ICRD year, ITRK track,
   ICMT comment) under `music/<artist>/<album>/`, three 64x48 PNG pictures (zlib + struct) under
   `photos/Saltmarsh Depot Survey/`, and two minimal EPUBs (zipfile; OPF title, creator, description, publisher,
   subject). It then starts the compose project (the media folder must exist before the bind mount, or Docker creates
   it as root) and waits on `/System/Info/Public`.
2. Startup wizard through the API, unauthenticated as Jellyfin allows before completion: `POST /Startup/Configuration`
   (en-US), `GET` + `POST /Startup/User` (renames the initial user to `rea-admin` with a password generated at run time
   into `.admin`, mode 600, password only), `POST /Startup/RemoteAccess`, `POST /Startup/Complete`.
3. Seeding with `POST /Users/AuthenticateByName` (header `Authorization: MediaBrowser Client=..., Token=...`; the token
   stays in process memory and the session is logged out at the end): libraries Lighthouse Rota Music (music),
   Saltmarsh Depot Photos (homevideos) and Copperfield Annex Reading Room (books) via `POST /Library/VirtualFolders`,
   `POST /Library/Refresh` and a poll until the 10 files are items. Jellyfin read the WAV INFO tags (artists Ada Finch
   Quartet and Blue Heron Kitchen Band, albums Lighthouse Rota Suite and Saltmarsh Depot Sessions, genres Coastal Folk and
   Kitchen Jazz, track titles), but not the EPUB OPF metadata (no year, publisher or author on the books), so overviews
   and tags on albums, artists, photos, books, the playlist and the collection are set the way the web client's metadata
   editor does it: read the item, change the fields, `POST /Items/{id}` with the whole DTO. Also: users Ada Finch and
   Rui Castellanos (`POST /Users/New`), playlist Night Watch Mix (3 tracks), collection Granite Ledger Sessions (both
   albums; Jellyfin then adds a "Collections" library of its own), two favourite tracks. Idempotent; removes
   `Rea Scratch*` playlists. Writes `seed-ids.json`.
4. `NODE_PATH=~/capture/node_modules node jellyfin/capture.mjs`: the web client's manual login form at
   `/web/#/login.html` (`#txtManualName`, `#txtManualPassword`; the script clicks "Manual Login" only if the form is
   hidden behind user cards), landing on `#/home.html`; then hash-route visits
   (music library, album details, photos library, books library, playlist details, dashboard, dashboard users, dashboard
   libraries; hash changes do not reload the client). The web client keeps its access token in localStorage
   (`jellyfin_credentials`), not in a cookie, so the 40 scripted calls read it there and send it in the `Authorization`
   header (stripped by the scoping tool): system info, users, a user by id, users/Me, virtual and media folders, user
   views, an album and a track by id, an album through the legacy `/Users/{id}/Items/{id}` route, the album's tracks,
   a track's ancestors, artists and both artists by name, music genres and one by name, similar albums, the playlist's
   items, the playlist and the collection, a photo by id, the books, similar books, a track's user data, latest items,
   filters, counts, `Search/Hints?searchTerm=Granite`, `searchTerm=Kelp`, `isFavorite=true`; then the write path on a
   scratch playlist: `POST /Playlists` (200), `POST /Playlists/{id}/Items` (204), `GET`, `POST /Items/{id}` metadata
   edit (204), `POST /UserFavoriteItems/{id}` (200), `GET` its items, `DELETE /Items/{id}` (204), `GET` (404), and the
   playlist list. Full HAR 14.8 MB, 256 entries (deleted after scoping).
5. `python3 -I ~/capture/scope_har.py jellyfin.full.har jellyfin.scoped.har --origin http://127.0.0.1:3224 --keep-regex
   '^/(Users|Items|UserItems|UserViews|UserFavoriteItems|Library|Playlists|Artists|MusicGenres|Genres|Albums|Search|Shows|DisplayPreferences|Branding/Configuration|System/Info)(/|$)'
   --drop-regex 'login|logout|signup|password|session|token|oauth|csrf|authenticate'` -> kept 72 (GET 66, POST 5,
   DELETE 1; statuses 200 x67, 204 x4, 404 x1). `authenticate` is in the drop regex on purpose: the sign-in request
   body carries the password in a field named `Pw`, which the scrubber's key list (password, secret, token, ...) would
   not catch, and the reply carries the access token. Dropped: path 173 (159 web-client assets, `/Branding/Css`,
   `/LiveTv/*` x2, `/Playback/BitrateTest` x3, `/QuickConnect/Enabled` x2, `/ScheduledTasks` x3,
   `/System/ActivityLog/Entries` x2, `/System/Endpoint`, and the login page's lower-case `/system/info/public`, `/users`,
   `/users/public`), auth 7 (`POST /Users/authenticatebyname`, `GET /Sessions`, `POST /Sessions/Capabilities/Full` x2 and
   three web-client assets with "session" in their file names), non-json 2 (`/Items/{id}/Images/Primary`, image/webp),
   other-origin 2 (a connectivity probe the browser sent to a third-party origin), big-body 0. Credential grep on the
   scoped HAR: admin password 0, the access token 0, `"Pw"` 0, `MediaBrowser ` 0, `hf_|ghp_|Bearer ` 0.
   sha256 `eb1bf56ca3ad61fccf0c9aec11fc580ae2929cf9703d8de26ff40f7fa7f602cc`, 196,660 bytes.
6. `python3 ~/showcase/envbuild.py all jellyfin`:
   - manifest: capture evidence `ev_e0e8efc19b07b4df61b2a5753a06282b27892bc8404746372201bfdd27662ba9` (72 records,
     confidence observed); manifest with rules `ev_e0005f7fdf6adba22caf1ff60dd317660ec3e9e5fbf91991a6bfdfd803d9feea`
     (inferred, historical-reference); without rules `ev_a90058b46ccbbaf0ad5ec5625ce1a90bc7f9fef1365336ab8b8ea8248f02a946`.
   - bundle: 12 retrieval tasks from 20 candidates (`exclude_tools`:
     `system|branding|displaypreferences|userdata|settings|config$|version$`; `userdata` because the only string in a
     track's user data is Jellyfin's internal composite key, "Ada Finch Quartet-Lighthouse Rota Suite-0003Lamp Oil Reel").
   - smoke: passed in 26.6 s (`listed 34 tools, expected 34`).
   - eval: `openai/gpt-oss-120b:groq` 12/12, `zai-org/GLM-5.3-Flash:zai-org` 12/12, no provider errors.
   - card + dry publish: 24 episodes, `~/showcase/datasets/jellyfin` (6.7 MB).
7. `docker compose -p rea-jellyfin -f compose.yml down -v`; `jellyfin.full.har`, `.admin` and the generated `media/`
   removed on the VM (seed.py regenerates the media byte-for-byte).

## Manifest facts
- 34 tools (GET 32, POST 2), 16 templated groups, 15 parameters, all from rea's built-in `hex` rule (Jellyfin ids are
  32-character lower-case hex GUIDs, named `{hash}`, `{hash_2}`); the opt-in rules match nothing, so the no-rules
  manifest is also 34 tools. `/Artists/Ada%20Finch%20Quartet`, `/Artists/Blue%20Heron%20Kitchen%20Band` and
  `/MusicGenres/Kitchen%20Jazz` stay literal tools (`get_artists_ada_20finch_20quartet`, ...): the name sits at path index
  1, and sibling-variance only compares segments from index 2 on.
- 4 groups excluded as non-json, all 204 replies with mime type `x-unknown`: `POST /Items/{hex}` (metadata edit),
  `POST /Playlists/{hex}/Items`, `DELETE /Items/{hex}` and the client's `POST /DisplayPreferences/usersettings`. The write
  tools left are `post_playlists` (with a body shape) and `post_userfavoriteitems_by_hash`.
- 31 distinct query parameter names over 75 slots; the web client's own reads carry long, PascalCase parameter sets
  (`EnableImageTypes`, `Fields`, `ImageTypeLimit`, `ParentId`, `SortBy`, ...) while the scripted ones are camelCase, and
  `get_playlists_items_by_hash` lists both `UserId` and `userId`. Statuses 200 and 404; 9 limitations; unknowns
  authorization-model, response-semantics, state-transition.
- UI-generated tools besides the scripted ones: `Users/{id}/Items` (album grid), `Users/{id}/Items/Latest`,
  `Users/{id}/Items/Resume`, `Users/{id}/Items/{id}` (details pages), `Playlists/{id}/Users/{id}`, `Shows/NextUp`,
  `UserViews`, `DisplayPreferences/usersettings`, `Branding/Configuration`, `Items/{id}/Similar` (details pages).

## Tasks and episodes
- 12 tasks: album grid of the music library (`Items[0].Name`), playlist items (`Items[0].AlbumArtists[0].Name`), latest
  items of the books library, a track's ancestors, the music library through the legacy user route, an album's
  `GenreItems[0].Name`, the admin user by id and `Users/Me` (both `rea-admin`), media folders and their first entry
  ("Collections"), the album's tracks, the user list (`Ada Finch`), artists (`Ada Finch Quartet`). Several prompts
  list every recorded query parameter of the web client's request (up to ten), which both models handled.
- Both models passed 12/12; no `episode_notes` needed.

## Seeded facts usable for retrieval questions
Album Lighthouse Rota Suite (Ada Finch Quartet, 2026, Coastal Folk; "Three tunes the Ada Finch Quartet plays for the
winter rota."; tracks Granite Ledger, Tide Table Waltz, Lamp Oil Reel). Album Saltmarsh Depot Sessions (Blue Heron Kitchen
Band, 2025, Kitchen Jazz; "Kitchen jazz taped between sittings at Blue Heron Kitchen."). Artist overviews: "Lamp-room
quartet led by Ada Finch, keeper of the tide tables." / "House band of Blue Heron Kitchen, fronted by Marisol
Okonkwo-Reyes." Photos: north-quay-bollards ("Bollards 1 to 6 on the north quay, surveyed by Rui Castellanos."),
granite-ledger-cart-seven, copperfield-annex-roof. Books: The Rye Cracker Almanac (Baking), Quayside Market Ledger
(Accounts). Playlist Night Watch Mix ("Three tracks for the 22:00 to 06:00 watch."); collection Granite Ledger Sessions.

## Rebuild, 2026-10-18

After review, the shared task generator was tightened: an answer must be a distinctive value that occurs in this app's seed and capture inputs, never the admin account's own identity, in at most 12 recorded responses, and unique across the tasks; each tool gets at most two tasks. Bundle, smoke, eval and card were re-run from the same capture. The bundle and eval numbers earlier in this file describe the first build; these are the published ones.

- bundle: 12 retrieval tasks from 15 recorded reads with an eligible field (up to two tasks per tool); field values rejected: in too many responses 29, not distinctive 18, admin identity 2.
- smoke: passed.
- eval `openai/gpt-oss-120b:groq`: 12/12.
- eval `zai-org/GLM-5.3-Flash:zai-org`: 12/12.
- card and dry publish: 24 episodes, dataset 6.7 MB.
