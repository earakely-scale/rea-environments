# Sonarr capture notes (rea showcase, batch 2)

- App: `lscr.io/linuxserver/sonarr:4.0.20.3014-ls329` (Sonarr **4.0.20.3014**, from `GET /api/v3/system/status` and the
  start-up log), digest `lscr.io/linuxserver/sonarr@sha256:44b06045a98bc1f237b9ffefc4b28dab64cb29305e4a2a94875ae93b5224e4cc`.
  Licence GPL-3.0 (`LICENSE.md` in the Sonarr repo); the linuxserver image only packages it. Built-in SQLite
  (`/config/sonarr.db`), no second service. Compose project `rea-sonarr`, loopback-only `127.0.0.1:3221 -> 8989`; named volumes
  for `/config` and `/data` (root folders and two no-op connection scripts live under `/data`).
- Config overrides through Sonarr's double-underscore environment variables: `SONARR__AUTH__METHOD=Forms`,
  `SONARR__AUTH__REQUIRED=Enabled`, `SONARR__LOG__ANALYTICSENABLED=False`.
- Credentials: the API key is the one Sonarr generated on first start; `seed.py` reads `/config/config.xml` through
  `docker compose exec` and parses `<ApiKey>` in memory. It and the generated admin password live only in `.admin` (mode 600,
  deleted at teardown).
- Tooling on the VM: rea 6.6.0, playwright-core 1.58.2, Chromium 155.0.8059.79 (snap, default temp profile worked),
  node v24.22.0, python 3.12.3, Docker 29.9.1, Compose 5.6.0.

## Pipeline (all under ~/capture/sonarr on the VM)
1. `./up.sh`: `/ping` answered after ~8 s on the first start; it then creates `/data/lighthouse-rota-archive`,
   `/data/granite-ledger-films` and `/data/scripts/{copperfield-annex,night-shift-pager}.sh` (`exit 0`).
2. `python3 seed.py` (stdlib, idempotent; a second run created nothing), all with `X-Api-Key`:
   - `PUT /api/v3/config/host/1`: forms login for user `rea-admin` with the generated password.
   - 4 tags (`lighthouse-rota`, `granite-ledger`, `blue-heron-kitchen`, `saltmarsh-depot`), 2 root folders, 3 custom formats
     ("Granite Ledger Remux", "Blue Heron Kitchen Subtitles", "Saltmarsh Depot x265", each one release-title regex), 2 quality
     profiles built from `qualityprofile/schema` ("Lighthouse Rota HD", cutoff HDTV-1080p, Remux +40, x265 -10; "Granite
     Ledger Archive SD", cutoff DVD, Subtitles +25), 2 release profiles ("Copperfield Annex Preferred", "Tide Table Filter"),
     1 delay profile (usenet 90 min, torrent 30 min, tag granite-ledger), 2 Custom Script connections ("Copperfield Annex
     Script", "Night Shift Pager"), 3 import-list exclusions with invented titles ("Granite Ledger Chronicles", "The
     Saltmarsh Depot Hour", "Blue Heron Kitchen Nights") and 1 auto-tagging rule ("Night Shift Dramas", genre Drama).
   - **Connections**: Sonarr test-fires a connection on save, and `?forceSave=true` does not skip a failing test. A Webhook to
     `hooks.example.test` failed with 500 "Name does not resolve", so both connections are Custom Script connections pointing
     at the no-op scripts.
   - **No series**: adding a series needs a lookup against Sonarr's online metadata service, which returns real shows; that
     is excluded by the synthetic-data rule, so the library, calendar, queue and wanted lists are empty.
3. `node capture.mjs`: forms login at `/login` (`input[name=username|password]`, `button[type=submit]`), lands on `/`, then
   navigates **inside the single-page app** (`history.pushState` + `popstate`) to `/calendar`, `/activity/queue`,
   `/wanted/missing`, `/settings/profiles`, `/settings/customformats`, `/settings/tags`, `/settings/connect`,
   `/system/status`, so the UI bootstraps once instead of once per page. It never opens Settings > General: the UI reads
   `/api/v3/config/host` there, whose response carries the API key and password (the scope drop regex also lists
   `config/host` as a guard). Then 59 scripted `fetch` calls with `X-Api-Key: window.Sonarr.apiKey`, the header the UI itself
   sends: every list, every seeded object by id (first by-id read in each collection is not the first-created item),
   `tag/detail`, `importlistexclusion/paged?...`, quality definitions (HDTV-1080p, DVD), `language/1`, naming / media
   management / ui config, health, disk space, system tasks, `calendar?start&end`, `wanted/missing?...`, series; writes:
   POST tag `rea-scratch`, PUT it, GET, DELETE, GET (404), POST release profile "Rea Scratch Profile", PUT, DELETE, re-read
   both lists. `rootFolder` and `autoTagging` are spelled the way the UI spells them; with lowercase paths the manifest had
   two tools each. Full HAR 4,135,150 bytes (deleted).
4. `python3 -I scope_har.py sonarr.full.har sonarr.scoped.har --origin http://127.0.0.1:3221 --keep-regex '^/api/v3/'
   --drop-regex 'login|logout|signup|password|session|token|oauth|csrf|config/host'` -> kept 98 (GET 94, POST 2, PUT 2;
   200 x93, 201 x2, 202 x2, 404 x1), 41 of them the UI's own calls; dropped path 18 (pages, `/initialize.json`, signalr
   negotiate, static), auth 3 (`/login`), big-body 1 (`/api/v3/localization`, 153 KB), non-json 2, other-origin 0,
   over-max 0. Scoped HAR 333,903 bytes, sha256 `25abe37ab890a22325bc85ae5852ba96517238117328fe8c818656386883654e`.
   Credential grep: `.admin` values 0, token shapes 0, `SonarrAuth` cookie name 0.
   - The 2 non-json drops are the DELETEs: Sonarr answers `DELETE /api/v3/tag/{id}` and `/api/v3/releaseprofile/{id}` with
     200, an empty body and no content type, which the HAR records as mimeType `x-unknown`; scope_har keeps empty replies only
     for 202/204 or a blank mimeType, so the manifest has no DELETE tool.
5. `python3 ~/showcase/envbuild.py all sonarr` (steps one by one): capture evidence
   `ev_c572a89136acc993cc0d84090da837a73206dc0d45291613dbd7a616120c4850` (98 records, `observed`); manifest with rules
   `ev_1ca510bb7f5f8a7e2d424e9f69d110dd4d569368cdeabe28ea2f7594add08a0d`, without rules
   `ev_41d25acb3dd4817028221edb513c0f356fe773c16bdc43d1f96873bac0c574ae`; 12 retrieval tasks from 24 candidates; smoke passed
   in 26.4 s; eval **12/12** for `openai/gpt-oss-120b:groq` and **12/12** for `zai-org/GLM-5.3-Flash:zai-org`; card + dry
   publish to `~/showcase/datasets/sonarr` (24 episodes, 6.8 MB).
6. `docker compose -p rea-sonarr -f compose.yml down -v`; `sonarr.full.har`, `.admin`, `req.*.json` removed.

## Manifest facts
- With rules: **48 tools** (GET 44, POST 2, PUT 2), 14 templated groups, all from the default `numeric` rule
  (`{autoTagging,customformat,delayprofile,importlistexclusion,language,notification,qualitydefinition,qualityprofile,
  releaseprofile,rootFolder,tag,tag/detail}/{numeric}` plus PUT tag and PUT releaseprofile). Sonarr ids are integers, so the
  three opt-in rules changed nothing: the view without them also has 48 tools. 9 distinct query names (`all`, `end`,
  `includeUnknownSeriesItems`, `monitored`, `page`, `pageSize`, `sortDirection`, `sortKey`, `start`); 4 tools with a body
  shape; coverage `complete-within-view` 48/48; 0 excluded; unknowns authorization-model, response-semantics,
  state-transition.
- UI-only tools (the scripts never call them): `customFilter`, `downloadclient`, `importlist`, `indexer`, `indexerFlag`,
  `localization/language`, `queue/status`, `queue/details`, `queue`.
- `exclude_tools` keeps instance-level or empty tools (status, tasks, health, disk space, ui/naming/media-management config,
  custom filters, queue, calendar, wanted, localization) out of the task generator; they stay in the environment.

## Episodes
No misses. Three of the twelve answers are values Sonarr ships rather than seeded ones (`English`, `DVD`, the custom-format
field label `Regular Expression`).

## Rebuild, 2026-10-18

After review, the shared task generator was tightened: an answer must be a distinctive value that occurs in this app's seed and capture inputs, never the admin account's own identity, in at most 12 recorded responses, and unique across the tasks; each tool gets at most two tasks. Bundle, smoke, eval and card were re-run from the same capture. The bundle and eval numbers earlier in this file describe the first build; these are the published ones.

- bundle: 12 retrieval tasks from 13 recorded reads with an eligible field (up to two tasks per tool); field values rejected: not distinctive 49, not in the seed inputs 4, in too many responses 4.
- smoke: passed.
- eval `openai/gpt-oss-120b:groq`: 12/12.
- eval `zai-org/GLM-5.3-Flash:zai-org`: 12/12.
- card and dry publish: 24 episodes, dataset 6.9 MB.
