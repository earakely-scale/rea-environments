# Umami 3.4 capture notes (rea showcase, batch 2)

- App: `ghcr.io/umami-software/umami:3.4.0`, digest
  `ghcr.io/umami-software/umami@sha256:85909afc45bdcda1917394594a087421fdbb05610fded0fa9f6fb861abb2f367` (package.json
  `3.4.0`, Next.js 16.3.4; the image has no OCI licence label, the project LICENSE is MIT, Umami Software, Inc.). Umami 3
  is PostgreSQL-only, so the `postgresql-` tag prefix of the 2.x line is gone; `3.4.0` is the PostgreSQL image. Database
  `postgres:17.9-alpine` (`postgres@sha256:c7526c0f6c3f30260a563d7bcf8ad778effac59a44f8ffa86678c35418338609`), second
  service, no host port; Prisma migrations run at container start. Compose project `rea-umami`, loopback-only
  `127.0.0.1:3215 -> 3000`, `DISABLE_TELEMETRY=1`, `DISABLE_UPDATES=1`.
- Secrets: `DATABASE_URL`, `POSTGRES_PASSWORD`, `APP_SECRET` and the rea-admin password live in `.admin` (mode 600) written
  by `python3 seed.py init`, read by both services through `env_file`.
- Admin: the image creates `admin` / `umami`. The seed signs in with that default once and renames the account to
  `rea-admin` with the generated password (`POST /api/users/{id}`), so the default credential is gone before anything
  else happens.
- Tooling on the VM: rea 6.6.0, playwright-core 1.58.2, Chromium 155.0.8059.79 (snap), node v24.22.0, python 3.12.3,
  Docker 29.9.1, compose 5.6.0.

## Pipeline (all under ~/capture/umami on the VM)
1. `python3 seed.py init`, then `docker compose -p rea-umami -f compose.yml up -d`; healthy within the first
   minute (healthcheck `curl /api/heartbeat`).
2. `python3 seed.py`: bearer-token API (`POST /api/auth/login` -> token), idempotent by name: 2 teams, 3 websites (one
   per team plus one owned by rea-admin), 2 users (`user`, `view-only`) added to the teams, a short link, a pixel, a
   website board, 2 annotations, a segment, a goal and a funnel. Then, only if a website has no pageviews yet, synthetic
   traffic through the public collector `POST /api/send`: 8 visitors per website, each with an explicit `userAgent`
   (Chrome/Linux, Firefox/Windows, Safari/macOS, Safari/iOS), an `ip` from the 198.51.100.0/24 documentation range and
   `timestamp`s spread from six days ago; 68 pageviews with titles and referrers, 12 custom events with data
   (rota-signup, tide-table-download, download-ledger-pdf, book-sitting) and 6 identify calls with session data
   (crew, home_station). 86 collector calls in all; stats afterwards: 28, 20 and 20 pageviews. Writes `seed-ids.json`.
   Two API shapes needed care: `POST /api/teams` answers a two-element array (the team and the owner membership), and
   `GET /api/websites/{id}/segments` requires `?type=segment`.
3. `NODE_PATH=~/capture/node_modules node umami/capture.mjs`: login through the UI form at `/login`; the UI keeps its bearer
   token in localStorage (`umami.auth`), so the scripted fetch calls read it there and send it as `Authorization`, which
   scope_har.py strips. The browser context aborts every request that is not to the app origin: the UI fetches website and
   referrer favicons from a third-party icon service, and those 5 requests end as `net::ERR_FAILED` in the HAR (dropped as
   other-origin). Pages: websites list, the Granite Ledger Docs overview, the events view of Lighthouse Rota Portal, the
   sessions view of Blue Heron Kitchen, links, pixels, boards, teams, admin users (5 by link click, 5 by page load). Scripted
   sequence: me; websites + each of the 3 by id; teams + each by id + their users; one team's websites; admin users + each
   of the 3 users by id + one user's teams; links, pixels, boards and one of each by id; annotations, segments, goals,
   funnels (list + one by id each); stats, metrics (`type=title`, `referrer`, `browser`, `event`), pageviews by day,
   event-data properties and values, session-data properties and values (`propertyName=crew`), sessions list, one session
   with its activity and properties, events list, daterange, all over a seven-day window; a search
   `?search=heron`; then POST a scratch website, rename it (`POST /api/websites/{id}`), GET it, DELETE it (200
   `{"ok":true}`), GET it again (still 200: websites are soft-deleted), re-read the list. Full HAR 30.3 MB (Next.js chunks;
   deleted after scoping).
4. `python3 ~/capture/scope_har.py umami.full.har umami.scoped.har --origin http://127.0.0.1:3215 --keep-regex '^/api/' --drop-regex 'login|logout|signup|password|token|oauth|csrf|^/api/auth/'`
   The default drop pattern contains `session`, which would drop Umami's visitor-analytics routes
   (`/api/websites/{id}/sessions*`, `/session-data/*`; 8 records in this capture); the narrowed pattern still drops
   `POST /api/auth/login` (the token reply) and all 7 `POST /api/auth/verify`. -> kept 101 (GET 98, POST 2, DELETE 1;
   all 200); dropped path 342, other-origin 5, auth 11 (3 `/login` page loads, login, 7 verify), non-json 0, big-body 0,
   over-max 0. 153,212 bytes, sha256 `85400fd70ec0df831f86c350417c4aef021dd3e9faf5581aa00e58df379cd35a`. Credential grep at
   the time: admin, database and app secrets 0 hits, token shapes 0, `umami.auth` 0. That grep did not look at keys inside
   response bodies, which is how the session token returned by `GET /api/me` got through; see the rebuild section. URLs in the scoped HAR: the app origin and
   the synthetic `https://lighthouse-rota.example.test` (the short link's target).
5. `python3 ~/showcase/envbuild.py all umami` with `exclude_tools` `config$|2fa|charts$|daterange|active$|me$`.
   - capture Evidence `ev_dcfbfac54f2924c001dbf7cb902251fae953a583a02b6d119bcf091066fac078` (101 records, observed);
     manifest `ev_4d0998b2ac5275c8de0fbf914694d19f4032770678f30df45c7dc53587db65e1` (inferred, view digest
     `489706631c3b16225e3793643784aedb3c9cefb71cee9142b644b019f5776e98`); no-rules manifest
     `ev_04ea8c05b0869fc17efb024d29babe8b623cc1837d72faa44d47ce5720d8142e`.
   - bundle: 12 retrieval tasks from 30 candidates; smoke passed (50 tools listed, `get_2fa_status` replayed 200) in 26 s.
   - eval: `openai/gpt-oss-120b:groq` 12/12, `zai-org/GLM-5.3-Flash:zai-org` 12/12, one tool call per episode on average,
     mean input tokens 15,566 and 20,637 (50 tool schemas). Card + dry publish: 24 episodes, dataset 6.7 MB at
     `~/showcase/datasets/umami`.
6. `docker compose -p rea-umami -f compose.yml down -v`; `umami.full.har`, `.admin`, `req.*.json` removed on the VM.

## Manifest facts
- 50 tools (GET 47, POST 2, DELETE 1), 37 templated groups, 44 parameters, all from the built-in `uuid` rule (every Umami
  id is a UUID; routes with two ids get `uuid` and `uuid_2`, e.g. `get_websites_sessions_activity_by_uuid_uuid_2`). The
  opt-in rules matched nothing; the no-rules manifest has the same 50 tools and 44 uuid parameters (8 limitations
  instead of 9).
- 70 query-parameter names across tools, 14 distinct (endAt, event, ids, includeTeams, limit, maxResults, page, pageSize,
  propertyName, search, startAt, timezone, type, unit); 2 tools with a body shape (POST websites, POST websites/{uuid});
  statuses 200 only; 0 excluded groups; coverage complete-within-view 50/50; unknowns authorization-model,
  response-semantics, state-transition.
- Umami updates with POST, not PUT/PATCH: `post_websites_by_uuid` is the rename. `delete_websites_by_uuid` answers 200.
- `get_websites_metrics_by_uuid` folds 10 records (UI and scripted, `type=title|referrer|browser|event|path|country`) into
  one tool; the replay picks the record by the `type` value.
- UI-only tools besides the scripted ones: config, 2fa status, websites/links/pixels charts, website active, events
  series and stats, sessions weekly, the user's websites, and the overview page's metrics.

## Seeded facts usable for retrieval questions
Websites "Lighthouse Rota Portal" (lighthouse-rota.example.test, team Saltmarsh Depot Analytics), "Granite Ledger Docs"
(granite-ledger.example.test), "Blue Heron Kitchen" (blue-heron-kitchen.example.test, team Copperfield Annex Web). Teams
"Saltmarsh Depot Analytics" (ada.finch team-member), "Copperfield Annex Web" (tomas.vey team-view-only). Link "Tide Table
Signup", pixel "Granite Ledger Newsletter Pixel", board "Night Shift Overview" ("Pageviews of the Lighthouse Rota night
shift pages."). Annotations "Quarterly stone count published; audited by Rui Castellanos." and "Spring tide menu launched
with smoked kelp broth." Segment "Kelp Broth Readers", goal "Ledger PDF Downloads" ("Visitors who download the quarterly
ledger PDF."), funnel "Rota Signup Funnel". Page titles "Winter Shift Plan", "Tide Tables for January", "Quarterly Stone
Count", "Spring Tide Menu", "Smoked Kelp Broth"; referrers saltmarsh-depot.example.test, copperfield-annex.example.test;
session data crew = night shift / day shift, home_station = Saltmarsh Depot.

## Surprises
- The default scope drop pattern treats any path containing `session` as an auth exchange; for an analytics app that
  is the visitor-session API, so the scope command narrows the pattern (reported as a tool issue).
- The collector accepts explicit `ip`, `userAgent` and `timestamp`, which makes backdated, multi-visitor synthetic traffic
  possible without a browser; bot user agents are ignored, so the seed sends realistic ones.
- Deleted websites stay readable by id (soft delete).

## Rebuild, 2026-10-18

After review, the shared task generator was tightened: an answer must be a distinctive value that occurs in this app's seed and capture inputs, never the admin account's own identity, in at most 12 recorded responses, and unique across the tasks; each tool gets at most two tasks. Bundle, smoke, eval and card were re-run from the same capture. The bundle and eval numbers earlier in this file describe the first build; these are the published ones.

Before the rebuild the scoped HAR was re-scoped from itself with `^/api/me$` added to the drop pattern: that exchange returned the session's bearer token in its response body, which the first scope did not scrub. The manifest step was re-run, so the capture and manifest Evidence ids in the published card supersede the ones above.

- bundle: 12 retrieval tasks from 26 recorded reads with an eligible field (up to two tasks per tool); field values rejected: not distinctive 15, admin identity 3, in too many responses 2.
- smoke: passed.
- eval `openai/gpt-oss-120b:groq`: 11/12 (misses: `qa-06-get_websites_funnels_by_uuid_uuid_2`: the model's answer did not contain the expected value).
- eval `zai-org/GLM-5.3-Flash:zai-org`: 12/12.
- card and dry publish: 24 episodes, dataset 6.7 MB.
