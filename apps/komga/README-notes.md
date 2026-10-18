# Komga capture notes (rea showcase, batch 2, vm1; alternate that replaced Gotify)

- App: `gotson/komga:1.29.1`, digest `gotson/komga@sha256:9fa656e8259bbd75c0f654bdfa91abf2b4813cbf4f40e80eb292495446ffdf1f`,
  `GET /actuator/info` build version 1.29.1 (Java 25.0.4.1 in the image). MIT licence (`LICENSE` at the tag, copyright
  Gauthier Roebroeck).
- Compose project `rea-komga`, loopback-only `127.0.0.1:3231 -> 25600`, embedded sqlite under `/config` on the `komga-config`
  volume, `JAVA_TOOL_OPTIONS=-Xmx1g`, the generated library bind-mounted read-only at `/data`. Healthcheck is a bash
  `/dev/tcp` probe (the image has no curl); Spring Boot started in 7.5 s, healthy after 15 s.
- Tooling on the VM: rea 6.6.0, playwright-core 1.58.2, Chromium 155.0.8059.79 snap (default temp profile worked),
  node v24.22.0, python 3.12.3, Docker 29.9.1 / Compose v5.6.0, agent-env 0.9.1334.

## Pipeline (all under ~/capture/komga on the VM)
1. `python3 make_library.py` (stdlib zipfile + a 15-line PNG writer): `library/annex/<Series>/<Series> NNN.cbz`, 3 series
   and 7 issues, each with 3 generated 160x240 PNG pages and a `ComicInfo.xml` (title, number, count, summary, date,
   writer/penciller/colorist/editor, publisher, genre, tags, language). Deterministic bytes (fixed zip timestamps), 48 KB.
   Series "Lighthouse Rota" (The First Watch, Lamp Oil Winter, Shift Three), "Granite Ledger" (Quarry Count, The Seaward
   Stack), "Blue Heron Kitchen" (Tide-Table Menu, Kelp Broth Night); publishers "Saltmarsh Depot Press" and "Copperfield
   Annex Comics"; people Ada Finch, Rui Castellanos, Mina Okafor, Tomas Vey, Marisol Okonkwo-Reyes. All invented.
2. `docker compose -p rea-komga -f compose.yml up -d`.
3. `python3 seed.py` (stdlib, idempotent by name; re-run before every capture, the last re-run only added the second read list): `POST /api/v1/claim` with
   `X-Komga-Email: rea-admin@example.test` and a password generated into `.admin` (mode 600; only the password is stored,
   the email is a fixed constant), then basic auth: library "Copperfield Annex Shelf" on `/data/annex` (scan starts on
   creation; the seed waits until 7 books are READY with ComicInfo titles), series metadata patched (summaries, statuses
   ONGOING / ENDED / HIATUS, age ratings, extra tags), collections "Night Shift Reading" and "Quarry and Depot Files"
   (ordered), read lists "Granite Ledger audit order" and "Blue Heron tasting order", users ada.finch@example.test and
   rui.castellanos@example.test, read progress on 2 books. Writes `seed-ids.json` (ids only).
4. `NODE_PATH=~/capture/node_modules node komga/capture.mjs`: UI login at `/login?redirect=/account/me` (the UI sends basic
   auth once to `/api/v2/users/me?remember-me=false`, then rides the session cookie), then 47 scripted in-page reads, the UI
   pages `/dashboard`, the library's series, a series, a book, a collection, a read list, then the write path: scratch
   collection POST, PATCH (204), GET, DELETE (204), GET (404); scratch read list POST, PATCH, DELETE; collections again.
   The scripted reads run before the dashboard on purpose: with `sibling-variance`, `/api/v1/series/new|updated` and
   `/api/v1/books/ondeck` merge into the `{id}` tools, and when the dashboard loaded first those literals became the
   first record of `get_series_by_sery_id` / `get_books_by_book_id`, which the task generator then skipped.
   Every by-id route is read for at least two ids so that the opt-in rule templates it with a named parameter
   (`collection_id`, `readlist_id`, `book_id`, `sery_id`).
5. `python3 -I ~/capture/scope_har.py komga.full.har komga.scoped.har --origin http://127.0.0.1:3231 --keep-regex '^/api/'
   --drop-regex 'login|logout|signup|password|session|token|oauth|csrf|^/api/v1/announcements|^/api/v1/client-settings/|^/api/v1/releases'`
   -> kept 116 (GET 95, POST 17, PATCH 2, DELETE 2); dropped path 289 (pages, assets, thumbnails), non-json 23 (page
   images and bodyless answers), auth/noise 33, big-body 0, over-max 0. Statuses 200 x110, 204 x4, 404 x2 (the UI asking
   for the previous book of issue 1, and the re-read of the deleted scratch collection). 254,388 bytes, sha256
   `4486c491d956d4a28b83a739ed6dd788f6bbb8f3790f73186583a35075870d9e`. Credential grep: admin password 0, token shapes 0,
   no secret-looking keys in any response body, no URL outside the app origin.
   `/api/v1/announcements` and `/api/v1/releases` are the Komga project's own news feed and release notes, which the server
   fetches from upstream on each page load: real-world content, so they are dropped by name (releases were also over the
   60 KB body cap). `client-settings` lists were empty UI noise.
6. `python3 ~/showcase/envbuild.py all komga` (first round), then after the input fix below `manifest`, `bundle`, `smoke`,
   `eval`, `card` again.

## Manifest facts
- Capture Evidence `ev_5d1edee16d3181a6cb765a258edf8a455e0f669980a1b3943b5a465d859db5a8` (116 records, observed).
- With rules: `ev_2400fc90acfee4c519b06085c63026c94599134757eb02bfa872af0b32bbdc10`, confidence inferred, **42 tools**
  (GET 33, POST 5, PATCH 2, DELETE 2), 11 templated groups, 11 path parameters, all from `sibling-variance`: Komga ids
  are 13-character Crockford base32 strings (`0RZ51K8GFA1KB`) that neither the four unconditional format rules nor
  `opaque-token` recognise, so only routes read with two or more ids become templates. 42 query-parameter names across
  tools (14 distinct: collection_id, library_id, oneshot, page, readlist_id, remember-me, role, search, series_id, size,
  sort, status, tag, unpaged); 7 tools with a body shape (the UI's `POST /api/v1/books/list` and `/series/list` searches,
  the scratch creates and patches); coverage complete-within-view 42/42; 9 limitations.
- Without rules: `ev_4ddd7bd03e09d9e76f523b38d91aad40acb6ed3b176dd95a1220c4efbc51b94e`, **64 tools**, no templates: every
  id read is its own literal tool. This is the largest rules-vs-norules gap of the three apps on this VM.
- Single-id routes stay literal with the id in the tool name (`get_libraries_0rz51k8bfa8nx`,
  `get_users_0rz51k69fa5zh_authentication_activity_latest`, the scratch `patch_/delete_collections_<id>`); the read-list
  "next book" route varies in two positions at once and stays as two literal tools.
- `sibling-variance` also folds the literal siblings `/series/new`, `/series/updated`, `/series/release-dates` into
  `get_series_by_sery_id` and `/books/ondeck` into `get_books_by_book_id`, the conflation the manifest's limitations warn about.

## Build results
- First round (dashboard before the reads, one id per sub-route): 12 tasks, `gpt-oss` 10/12, `GLM` 11/12. Both models
  missed a task whose literal tool `/api/v1/collections/<id>/series` was phrased "look up the <id> series": they called
  `get_series_by_sery_id` with the collection id and the replay fell back to a different record. That was a task
  limitation, so the capture was changed (step 4) rather than accepted.
- Final: 12 retrieval tasks from 23 candidates, 11 of them on templated by-id tools with named parameters, 1 on the
  collections list. `exclude_tools` drops the UI plumbing and the non-informative lists (announcements, client settings,
  claim, thumbnails, files, release dates, age ratings, languages, sharing labels, alphabetical groups, pages).
- Smoke passed (27 s; the replay listed 42 tools, as expected).
- Eval: `openai/gpt-oss-120b:groq` **11/12**, `zai-org/GLM-5.3-Flash:zai-org` **12/12**; mean input tokens 11,796 and
  15,004. The miss (`qa-11`, the read lists that contain one book) was a provider rejection: gpt-oss called the
  all-read-lists tool `get_readlists` with its optional query parameters set to `null` and the provider's schema
  validation answered 400. Same miss, same cause, in two separate runs; written into `episode_notes`.
- Because the first round's smoke run (against the 41-tool bundle) would otherwise stay in the dataset next to the new
  one (`eval` purges per model, not smoke), all komga runs were purged with `envbuild.py purge komga` and smoke, eval
  and card re-run. Dry publish: 13 tasks, 25 runs (24 eval episodes + smoke) in `~/showcase/datasets/komga`, 6.8 MB;
  scans clean.

## Teardown
`docker compose -p rea-komga -f compose.yml down -v`; `komga.full.har`, `.admin`, `req.*` deleted; the generated `library/`
removed (re-creatable with make_library.py).

## Rebuild, 2026-10-18

After review, the shared task generator was tightened: an answer must be a distinctive value that occurs in this app's seed and capture inputs, never the admin account's own identity, in at most 12 recorded responses, and unique across the tasks; each tool gets at most two tasks. Bundle, smoke, eval and card were re-run from the same capture. The bundle and eval numbers earlier in this file describe the first build; these are the published ones.

- bundle: 12 retrieval tasks from 19 recorded reads with an eligible field (up to two tasks per tool); field values rejected: in too many responses 30, not distinctive 16, admin identity 3.
- smoke: passed.
- eval `openai/gpt-oss-120b:groq`: 11/12 (misses: `qa-11-get_readlists_0rz51kszka53j_books_0rz51k`: the model's answer did not contain the expected value).
- eval `zai-org/GLM-5.3-Flash:zai-org`: 11/12 (misses: `qa-11-get_readlists_0rz51kszka53j_books_0rz51k`: the model's answer did not contain the expected value).
- card and dry publish: 24 episodes, dataset 6.8 MB.
