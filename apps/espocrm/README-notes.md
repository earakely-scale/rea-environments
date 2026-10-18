# EspoCRM 10 capture notes (rea showcase)

- App: `espocrm/espocrm:10.0.10-apache`, digest
  `espocrm/espocrm@sha256:debf48652fed511424825839185fd67e773081ee0d665ab62cbce985acb32636` (PHP 8.4.26, Apache 2.4.68,
  Debian trixie base), version `10.0.10` (from the sign-in reply's `settings.version`). Licence AGPL-3.0 (`LICENSE.txt` in
  the image). Database `mariadb:11.8.9`, digest `mariadb@sha256:f16d7a344413e519dff518f27bdb221388f84b0d274c97c4fb5f2cb0dc1b34fa`,
  as a second compose service with no host port and a random root password. Compose project `rea-espocrm`, loopback-only
  port `127.0.0.1:3216 -> 80`, `ESPOCRM_SITE_URL=http://127.0.0.1:3216`, time zone UTC, default currency left at USD.
- Tooling on the VM: rea 6.6.0, playwright-core 1.58.2, snap Chromium 155 (`chromium.launch` with `--no-sandbox`; the
  persistent-context fallback was not needed), node v24, python 3.12, docker 29.9.1.

## Surprises
- **Volume layout.** EspoCRM 10 images refuse to install when `/var/www/html` is mounted whole ("LEGACY INSTALLATION
  METHOD DETECTED", the container serves a redirect and never installs). The compose file mounts the three directories the
  image expects instead: `/var/www/html/data`, `/var/www/html/custom`, `/var/www/html/client/custom`.
- **Admin user name.** The 10.0.10 entrypoint runs `create-admin-user "$ESPOCRM_ADMIN_USERNAME"` and then
  `set-password admin` with a hard-coded `admin`; with any other user name the second command fails, and because the
  script runs under `set -e` with output sent to /dev/null the container restarts in an install loop with no error
  message. Compose therefore lets the image create `admin`, and seed.py renames that user to `rea-admin` (first name Rea,
  last name Admin, rea-admin@example.test, title "CRM Administrator") through `PUT /api/v1/User/{id}` on the first run.
- **Currency.** `ESPOCRM_DEFAULT_CURRENCY=EUR` sets the default currency but not the currency list, so creating an
  opportunity in EUR fails with `validCurrency`; the seed uses USD and compose leaves the currency alone.
- Tasks, meetings, calls and cases require an assigned user (`assignedUser` required), so the seed assigns them to rea-admin.
- `DELETE /api/v1/Task/{id}` answers 200 with the JSON literal `true`, and the admin can still read the deleted record:
  the re-read after delete is 200 with `"deleted": true` (soft delete), not 404.
- Related-record lists (`/api/v1/Account/{id}/contacts` etc.) return ids only unless the request names attributes with
  `select=`; the scripted calls pass `select`, the web client passes `attributeSelect`.
- A raw `[` in a query string (`where[0][type]=...`) makes the HAR URL fail rea's `uri` format check
  (`inspect-web-network-capture` rejects the whole capture); capture.mjs percent-encodes the brackets as the web client does.
- envbuild's credential grep flags every value in `.admin` that appears in the HAR, including the user name (`rea-admin`
  is the `userName` of every record's creator), so `.admin` holds only the two passwords and the user name is a constant.

## Pipeline (all under ~/capture/espocrm on the VM)
1. `python3 seed.py init` writes `.admin` (mode 600: admin password and database password, generated at run time).
   `docker compose -p rea-espocrm -f compose.yml --env-file .admin up -d`; MariaDB healthy after about 10 s, EspoCRM's
   first-start install (config, rebuild, admin, scheduled jobs) about a minute; healthcheck `curl` on `/`.
2. `python3 seed.py`: waits for `/` and `GET /api/v1/App/user`, renames the bootstrap admin, then creates through the
   REST API (header `Espo-Authorization: base64(user:password)`, the web client's password sign-in): 2 teams, 4 accounts,
   4 contacts (linked to the accounts), 3 leads, 4 opportunities (USD), 3 cases (with contacts), 3 tasks, 2 meetings,
   2 calls, 2 knowledge-base articles, 1 campaign, 1 target list and a stream post on Granite Ledger Holdings. Idempotent
   (each object is looked up by name or email with a `where` filter before creation) and it removes `Rea scratch*` tasks
   left by an interrupted capture. Writes `seed-ids.json` (ids only).
3. `NODE_PATH=~/capture/node_modules node capture.mjs`: UI sign-in (`#field-userName`, `#field-password`, `#btn-login`;
   the 1440x900 viewport; `#navbar` is attached but hidden in headless mode, so the script waits for it attached), visits
   `#Account`, the Granite Ledger Holdings detail view, `#Contact`, the Ada Finch detail view, `#Lead`, `#Opportunity`,
   one opportunity detail view, `#Case`, `#Task`, `#KnowledgeBaseArticle`. The script copies the web client's own
   `Espo-Authorization` / `Espo-Authorization-By-Token` header values from its first token-authenticated request (in
   memory only) and runs 58 scripted fetch calls: 12 collection lists, every seeded object by id (32 reads over 13 entity
   types, including the user and both teams), 3 related lists with `select`, the account stream, 4 filters
   (`where` industry = Shipping, `textFilter=Okafor`, amount > 10000 ordered by amount, priority = Urgent), then a scratch
   task POST, PUT, GET, DELETE, GET and a final task list. Full HAR 6.8 MB, 161 entries (deleted after scoping).
4. `python3 -I ~/capture/scope_har.py espocrm.full.har espocrm.scoped.har --origin http://127.0.0.1:3216 --keep-regex '^/api/v1/'
   --drop-regex 'login|logout|signup|password|session|token|oauth|csrf|/App/user|/I18n|/Metadata'`
   -> kept 131 (GET 128, POST 1, PUT 1, DELETE 1), all 200; dropped path 26 (SPA shell, bundles, templates, images),
   auth 4 (`/App/user` = the sign-in reply carrying the session token; `/I18n` 36 KB of UI strings; `/Metadata` x2, over
   60 KB each), non-json 0, big-body 0, other-origin 0. 260,567 bytes, sha256
   `b5fdf1ec365990047149655278e9a74f26b4fbbad53d75113ddb65ed89357b26`.
   Credential check (counts only): admin and database passwords 0, the session token and both auth header values taken
   from the full HAR 0, `Bearer `/`hf_`/`ghp_` 0, password/secret/apiKey keys in bodies 0.
5. `python3 ~/showcase/envbuild.py all espocrm`: capture evidence
   `ev_f3ad613cd68560f8796fa77cc136de88152b4ab1158158d7b74a873455ec3fe9` (131 records, observed); manifest
   `ev_318ff198f98931b6b5d15f468d8ba767e95abbeb05ed8eb65cd742f138117f34` (inferred, view digest
   `5248cf49d4edd4de1d8b7e0bbd0fa5ddae137c74b977c3657adf1c062122e1fb`); no-rules manifest
   `ev_447a95c40dcdd9523cc24f7bc9c41ec47f387ab792deabbe55a3b62c91fc3556`. Bundle: 12 retrieval tasks from 29
   candidates. Smoke passed (88 tools listed, 29.8 s). Eval: `openai/gpt-oss-120b:groq` 12/12,
   `zai-org/GLM-5.3-Flash:zai-org` 12/12, one tool call per task on average. Card and dry publish:
   `~/showcase/datasets/espocrm` (24 episodes, 6.9 MB).
6. `docker compose -p rea-espocrm -f compose.yml down -v`; `espocrm.full.har`, `.admin`, `req.*.json` removed.

## Manifest facts
- With rules: 88 tools (GET 85, POST 1, PUT 1, DELETE 1), 35 templated groups, all 35 parameters by `opaque-token`
  (EspoCRM ids are 17-character hex strings such as `6ad52f2e4cd6dba37`); `after-uid-literal` and `sibling-variance`
  matched nothing. 196 query-parameter names across tools, 18 distinct (attributeSelect, checkIfEmpty, entityType,
  entityTypeList[], filter, futureDays, maxSize, offset, order, orderBy, primaryFilter, select, textFilter,
  whereGroup[0][attribute], whereGroup[0][type], where[0][attribute], where[0][type], where[0][value]); 2 tools with a
  body shape (POST /Task, PUT /Task/{uid}); statuses 200 only; 0 excluded; coverage complete-within-view 88/88;
  unknowns authorization-model, response-semantics, state-transition; 9 limitations.
- Without rules: 110 tools (GET 107, POST 1, PUT 1, DELETE 1), every by-id read a literal tool.
- 55 of the 88 tools match `exclude_tools` and are kept out of task generation (they stay in the manifest): web-client
  plumbing (`{Entity}/layout/*`, notification counters, `Activities/*`, streams, `Settings`,
  `KnowledgeBaseCategory/action/listTree`, the API root) and detail-view side panels that are empty or carry only
  metadata (documents, target lists, task panels).
- Tool names are lower-cased entity names (`get_knowledgebasearticle_by_uid`, `get_account_contacts_by_uid`).

## Tasks and episodes
12 tasks over user (title), target list (description), team, campaign, task, opportunity, knowledge-base article,
meeting, call (names), contact cases and account contacts (first list entry's name), lead (description). Both models
passed all 12; no episode notes needed.

## Rebuild, 2026-10-18

After review, the shared task generator was tightened: an answer must be a distinctive value that occurs in this app's seed and capture inputs, never the admin account's own identity, in at most 12 recorded responses, and unique across the tasks; each tool gets at most two tasks. Bundle, smoke, eval and card were re-run from the same capture. The bundle and eval numbers earlier in this file describe the first build; these are the published ones.

- bundle: 12 retrieval tasks from 29 recorded reads with an eligible field (up to two tasks per tool); field values rejected: in too many responses 25, not distinctive 30, admin identity 17.
- smoke: passed.
- eval `openai/gpt-oss-120b:groq`: 12/12.
- eval `zai-org/GLM-5.3-Flash:zai-org`: 12/12.
- card and dry publish: 24 episodes, dataset 6.9 MB.
