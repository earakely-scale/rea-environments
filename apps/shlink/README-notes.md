# Shlink 5.1.7 capture notes (rea showcase, batch 2)

- App: `shlinkio/shlink:5.1.7` (the default, non `-roadrunner`-suffixed tag; it runs RoadRunner too), digest
  `shlinkio/shlink@sha256:844e1f2b6455331c5b49207bad3a2455ccd65e62bb9daa09a6c57afff26bd9c8`; `GET /rest/health` reports
  `{"status":"pass","version":"5.1.7"}`. Licence MIT (LICENSE at v5.1.7: "The MIT License (MIT), Copyright (c) 2016-2024
  Alejandro Celaya").
- Compose project `rea-shlink`, loopback-only `127.0.0.1:3206 -> 8080`, `DEFAULT_DOMAIN=127.0.0.1:3206`,
  `IS_HTTPS_ENABLED=false`, `DB_DRIVER=sqlite` (`/etc/shlink/data/database.sqlite` on volume `shlink-data`),
  `SKIP_INITIAL_GEOLITE_DOWNLOAD=true` (no GeoLite licence key, so visits carry no location), `WEB_WORKER_NUM=1`,
  `TASK_WORKER_NUM=1`. Healthcheck `wget /rest/health`; healthy within seconds.
- Tooling on the VM: rea 6.6.0, playwright-core 1.58.2, Chromium 155.0.8059.79 (snap, plain `chromium.launch`), node v24.22.0,
  python 3.12.3, docker 29.9.1, compose 5.6.0.

## No bundled UI
Shlink is API-only; its web client (shlink-web-client) is a separate project and is not in this image. As the brief
prescribes, `capture.mjs` opens a page on the app origin (`GET /rest/health`, the public health document, rendered as
JSON text) and runs every API call with `fetch` from that page. Shlink's REST API authenticates with an API key in the
`X-Api-Key` header; the key comes from `.admin` and the header is stripped by scoping. So the raw HAR is tiny (66 entries,
229,561 bytes): the page load plus 65 scripted calls, and nothing is dropped by scoping.

## Something surprising: sqlite and the default worker pool
With the image defaults (a pool of RoadRunner web workers plus task workers), the first capture hung on
`PATCH /rest/v3/short-urls/rea-scratch` with a body that also rewrote `tags`; the request never answered, and afterwards every
write failed with `SQLSTATE[HY000]: General error: 5 database is locked` (Doctrine `LockWaitTimeoutException`) until the
container was recreated. With `WEB_WORKER_NUM=1` and `TASK_WORKER_NUM=1` the same PATCH answers in 20 ms, so the compose
file pins one worker of each kind. Reads were never affected.

## Pipeline (all under ~/capture/shlink on the VM)
1. `docker compose -p rea-shlink -f compose.yml up -d`.
2. `python3 seed.py` (stdlib urllib, idempotent): generates one API key named `rea-capture` with
   `docker compose exec -T shlink shlink api-key:generate --name=rea-capture` and stores only the key in `.admin`
   (mode 600; never printed); removes leftover scratch links and the orphan `scratch` tag; creates 8 short URLs through
   `POST /rest/v3/short-urls` (7 custom slugs, one on the custom domain `links.saltmarsh.example.test`, which Shlink
   registers on first use, and one generated 6-character code via `findIfExists`), with titles, tags, `maxVisits`,
   `validSince`/`validUntil`, `crawlable` and `forwardQuery`; sets two redirect rules on `tide-tables`
   (`device = android`, query `shift = night`); then simulates visits by requesting the short URLs with redirects disabled
   and synthetic `User-Agent`/`Referer` headers (the custom-domain link with a `Host: links.saltmarsh.example.test`
   header), one second apart so newest-first lists start with different visitors, plus two orphan visits (`/` and
   `/no-such-rota`). Shlink classified `TideTableReader/3.2 (Copperfield Annex)` as a potential bot, which makes the
   `excludeBots` filters meaningful. All long URLs and referers use `.test` hosts. Writes `seed-ids.json`.
3. `NODE_PATH=~/capture/node_modules node capture.mjs`: opens `/rest/health`, then 65 `fetch` calls: health; short-URL
   lists (`orderBy=title-ASC`, `searchTerm=heron`, `tags[]=granite-ledger`, `orderBy=visits-DESC&itemsPerPage=3`, page 2,
   `domain=`, `tagsMode=all` with two tags, `excludeMaxVisitsReached`+`excludePastValidUntil`, `searchTerm=granite` with
   `orderBy=dateCreated-DESC`); all 8 short URLs by code (the custom-domain one with `?domain=`) and the custom-domain code
   without it (404); visits of all 8 plus `excludeBots` and `startDate` variants; redirect rules of all 8; tags, tags with
   `searchTerm`, tag stats (plain, `orderBy=visits-DESC`, `searchTerm=rota`); visits of all 5 tags plus an `excludeBots`
   variant; domains; visits of the custom domain and of `DEFAULT` (plus `excludeBots`); the global visits summary;
   non-orphan visits (plain, `excludeBots`, `startDate` page 2); orphan visits (plain, `type=invalid_short_url`);
   `mercure-info` (501, not configured). Write path: POST `rea-scratch` (200), PATCH title and tags (200), GET, DELETE
   (204), GET (404), then the title-ordered list again.
4. `python3 -I ~/capture/scope_har.py shlink.full.har shlink.scoped.har --origin http://127.0.0.1:3206 --keep-regex '^/rest/'`
   -> kept 66 (GET 63, POST 1, PATCH 1, DELETE 1), dropped nothing. Statuses 200 x62, 204 x1, 404 x2, 501 x1. Scoped
   HAR 117,350 bytes, sha256 `97a0390d535b7d6f2555d14a7402f5785ac85825b7077236bcfcc8ccbbc1714c`. Credential grep: API key
   literal 0, `X-Api-Key` 0, `apiKey` 0, `Bearer `/`JWT `/`eyJ` 0, cookies 0; only content-type/accept headers remain.
5. `python3 ~/showcase/envbuild.py all shlink` (manifest, bundle, smoke, eval, card).

## Manifest facts
- Capture Evidence `ev_4779d529d62305de670c032f0cdd9188c95cf86f0b549b9a0fac8554db69142b` (66 records, observed).
- With the opt-in rules: `ev_a3d72b74e5d37d9c974dd35a57591dbbe52e160452a2cc3b63a4d2576e852336`, confidence `inferred`,
  17 tools (GET 15, POST 1, PATCH 1), 4 templated groups, 4 path parameters, all `sibling-variance`:
  `short-urls/{short_url_id}` (9 observed codes including the scratch one), its `/visits` and `/redirect-rules`
  (8 codes each), and `tags/{tag_id}/visits` (5 tags). Coverage complete-within-view, 1 excluded group, 9 limitations.
  12 distinct query parameter names (domain, excludeBots, excludeMaxVisitsReached, excludePastValidUntil, itemsPerPage,
  orderBy, page, searchTerm, startDate, tagsMode, tags[], type). Body shapes on the POST and the PATCH.
- Without the rules: `ev_2bb6ae3d85e4109d51fbed6349c7c371dfd2c38596412c83e649052b90f906b4`, confidence `derived`, 43 tools
  (GET 41), one literal tool per short code and per tag.
- The excluded group is the scratch `DELETE /rest/v3/short-urls/rea-scratch`: Shlink answers 204 with no content type
  (HAR `x-unknown`), which REA excludes as non-json, so the manifest has no DELETE tool.
- `domains/DEFAULT/visits` and `domains/links.saltmarsh.example.test/visits` stay two literal tools (two observed values
  are not enough for `sibling-variance`); the scratch PATCH stays literal (`patch_rest_short_urls_rea_scratch`).

## Tasks and eval
- `exclude_tools` = `health|mercure`. Exactly 10 candidates, 10 tasks: Shlink objects carry few readable string fields
  (short-URL `title`; everything else is URLs, dates, counters or enums), so the generator falls back to visit
  `userAgent` strings, the redirect-rule `matchValue` and the tag name in tag stats; the tag list (bare strings), the
  domain list (the default domain `127.0.0.1:3206` has no letters), the visits summary (numbers) and health yield no
  candidate.
- Two tasks share an answer by construction: the newest non-orphan visit is also the newest visit on the default domain
  (`TideTableReader/3.2 (Copperfield Annex)`).
- Smoke passed (17 tools listed, `get_rest_health` replayed 200). gpt-oss-120b 9/10, GLM-5.3-Flash 10/10. The gpt-oss
  miss (`qa-09`, tag stats) is a provider 400: the model sent `null` for the optional `searchTerm` and `orderBy` string
  parameters and the router's tool-call validation rejected the call before it reached the environment; recorded in
  `episode_notes`.

## Seeded facts usable for retrieval questions
Short URLs: granite-ledger "Granite Ledger quarterly stone count" (max 500 visits), tide-tables "January tide tables for
Granite Point" (crawlable, rules android -> compact view, shift=night -> night-shift page), blue-heron-menu "Blue Heron Kitchen
spring-tide menu", depot-manifest on links.saltmarsh.example.test "Saltmarsh Depot lamp-oil manifest SO-4471", annex-rebuild
"Copperfield Annex beacon rebuild notes" (valid until 2027-03-31), rota-binder "Lighthouse Rota binder index", kelp-broth
"Smoked kelp broth recipe card", 4eceeU "Night shift handover checklist". Tag stats: lighthouse-rota 4 short URLs / 5
visits (1 bot), blue-heron-kitchen 2 / 2, granite-ledger 1 / 2, copperfield-annex 1 / 1, saltmarsh-depot 1 / 1. Visitors,
newest first: TideTableReader/3.2 (Copperfield Annex, bot), KeeperConsole/2.1 (Granite Point Light), DepotScanner/0.9
(Saltmarsh Depot quay), GalleyTablet/1.4 (Blue Heron Kitchen), KeeperConsole/2.0 (Saltmarsh Depot Tower) x2, QuarryClipboard/5.0
(north quarry), LampWright/0.7 (Copperfield Annex workshop), GalleyTablet/1.2 (Blue Heron Kitchen pass); orphans
LostLantern/1.1 (mistyped short code), LostLantern/1.0 (base URL).

## Teardown
`docker compose -p rea-shlink -f compose.yml down -v` (the volume holds the sqlite database and the hashed API key);
`shlink.full.har`, `.admin`, `req.*.json` and the probe script removed on the VM.

## Rebuild, 2026-10-18

After review, the shared task generator was tightened: an answer must be a distinctive value that occurs in this app's seed and capture inputs, never the admin account's own identity, in at most 12 recorded responses, and unique across the tasks; each tool gets at most two tasks. Bundle, smoke, eval and card were re-run from the same capture. The bundle and eval numbers earlier in this file describe the first build; these are the published ones.

- bundle: 7 retrieval tasks from 8 recorded reads with an eligible field (up to two tasks per tool); field values rejected: not distinctive 1, in too many responses 1.
- smoke: passed.
- eval `openai/gpt-oss-120b:groq`: 7/7.
- eval `zai-org/GLM-5.3-Flash:zai-org`: 7/7.
- card and dry publish: 14 episodes, dataset 6.5 MB.
