# BookStack capture notes (rea showcase, batch 2)

- App: `lscr.io/linuxserver/bookstack:v26.09.1-ls288` (BookStack **v26.09.1**, from `GET /api/system`), digest
  `lscr.io/linuxserver/bookstack@sha256:0d66f65417fa667085849bf9b32b412ec9a90420773c4f47a95138c4711876b7`; database
  `mariadb:11.8.9` (`mariadb@sha256:f16d7a344413e519dff518f27bdb221388f84b0d274c97c4fb5f2cb0dc1b34fa`) as a second compose
  service with no host port. Compose project `rea-bookstack`, loopback-only `127.0.0.1:3219 -> 80`, `APP_URL=http://127.0.0.1:3219`,
  `MAIL_DRIVER=log`. Licence: MIT ("Copyright (c) 2015-2026, Dan Brown and the BookStack project contributors", LICENSE in the
  BookStack repo); the linuxserver image only packages it.
- Secrets: `up.sh` generates the MariaDB passwords and the Laravel `APP_KEY` into `.admin` (mode 600) and starts compose with
  `--env-file .admin`; `seed.py` appends the admin password and the API token to the same file. compose.yml only holds
  `${VAR:?}` references. `.admin` was deleted at teardown.
- Tooling on the VM: rea 6.6.0, playwright-core 1.58.2, Chromium 155.0.8059.79 (snap; Playwright's default temp profile
  worked, the `USER_DATA_DIR` fallback was not needed), node v24.22.0, python 3.12.3, Docker 29.9.1, Compose 5.6.0.

## Pipeline (all under ~/capture/bookstack on the VM)
1. `./up.sh`: MariaDB healthy, BookStack answering `/login` after ~16 s (the linuxserver init runs the migrations).
2. `python3 seed.py` (stdlib only, idempotent; a second run created nothing):
   - The image boots with the documented default admin `admin@admin.com` / `password`. BookStack issues API tokens only
     through its web UI, so the seed signs in through the login form once with the default admin, creates token
     `rea-seed` through the `/api-tokens/1/create` form (the secret is shown once on the next page and parsed from it),
     then renames the admin through `PUT /api/users/1` to "Rea Admin" <rea-admin@example.test> with a password generated at
     run time. The default credentials stop working at that point (checked: the form rejects them).
   - Then through the REST API with the token: roles "Tide Clerks" and "Quarry Auditors"; users Ada Finch, Rui Castellanos,
     Mina Okafor (`send_invite: false`, throwaway passwords that are never stored); 5 books, 3 shelves, 5 chapters, 8
     markdown pages, all tagged; 2 link attachments (`https://example.test/...`); 2 page comments; then
     `PUT /api/content-permissions/{type}/{id}` hands 9 items to Ada, Rui or Mina as owner and gives 3 of them a role view
     grant, so `owned_by`/`owner` vary per item. Deletes any leftover "Rea Scratch" book. Writes `seed-ids.json`.
3. `node capture.mjs`: UI login at `/login` (the submit button has no `type`, selector `#login-form button.button`), then 12
   UI pages (`/`, shelves, one shelf, books, one book, one chapter, one page, `/search?term=granite`, `/tags`,
   `/settings/users`, `/settings/roles`, `/settings/audit`), then 65 scripted `fetch` calls. Full HAR 7,314,916 bytes
   (deleted after scoping).
   - **BookStack's UI is server-rendered and never calls `/api` itself**: every kept record is a scripted call.
   - **Cookie-session API access is GET-only**: a POST with the session cookie answers 403 "Only GET requests are allowed
     when using the API with cookie-based authentication". Reads therefore ride on the browser session (the auth the UI
     uses), and the three writes send `Authorization: Token <id>:<secret>` from `.admin` with `credentials: 'omit'`.
     Request headers never reach the scoped HAR.
   - Reads: system, every list (shelves, books, chapters, pages, attachments, comments, users, roles, tags/names,
     image-gallery, recycle-bin, audit-log), every seeded object by id (3 shelves, 5 books, 5 chapters, 8 pages,
     2 attachments, 2 comments, 4 users, 3 roles = 32 reads), `filter[name:like]=%Tide%` on books,
     `filter[book_id]=1` on chapters, `sort=+name&count=5` on pages, `tags/values-for-name?name=site|auditor`,
     `search?query=granite|kelp`, `search/book/1?query=wick`, `search/chapter/12?query=terrace`,
     `content-permissions/book/3` and `content-permissions/page/21`. In each collection the first by-id read is an item
     owned by someone other than the admin, so the generated questions are less often "Rea Admin".
   - Writes: `POST /api/books` "Rea Scratch Book", `PUT` it, `POST /api/pages` into it, re-read both, `DELETE` the book
     (204), re-read (404), re-read the recycle bin (now holding the scratch book) and the book list.
4. `python3 -I scope_har.py bookstack.full.har bookstack.scoped.har --origin http://127.0.0.1:3219 --keep-regex '^/api/'`
   -> kept 65 (GET 61, POST 2, PUT 1, DELETE 1; statuses 200 x63, 204 x1, 404 x1); dropped path 86 (pages, `dist/` JS/CSS,
   logos, avatars), auth 2 (the `/login` GET and POST), other-origin 0, non-json 0, big-body 0, over-max 0. The DELETE is kept
   because scope_har keeps empty 204 replies. Scoped HAR 127,666 bytes, sha256
   `1f807d4d2d2ef490cdc5cac50ffcbf573abfc967351038256b92e18f4ebe5366`.
   Credential grep on the scoped HAR: `.admin` values 0 hits, token shapes (`hf_`, `ghp_`, `Bearer `, `Token x:`) 0 hits,
   session cookie names (`bookstack_session`, `XSRF-TOKEN`) 0 hits.
5. `python3 ~/showcase/envbuild.py all bookstack` (steps run one by one): capture evidence
   `ev_07a98c12a171833f8ca00f5f4769a165b358a5e2cca784718af469fc35ee5b77` (65 records, `observed`), manifest with rules
   `ev_47deffa8044f6f1c6835193c59746931187576db6b1c0cc367b7c4380714c322`, without rules
   `ev_294a3fd78d221c90e5246cffd336196604377bca21248664f798c744606815ee`; bundle 12 retrieval tasks from 22 candidates;
   smoke passed in 30.3 s (31 tools listed, `get_attachments` replayed 200); eval **12/12** for
   `openai/gpt-oss-120b:groq` and **12/12** for `zai-org/GLM-5.3-Flash:zai-org` (one tool call per episode, 42-68 s per
   task); card + dry publish to `~/showcase/datasets/bookstack` (24 episodes, 6.5 MB).
6. `docker compose -p rea-bookstack -f compose.yml down -v`; `bookstack.full.har`, `.admin`, `req.*.json` removed on the VM.

## Manifest facts
- With rules: **31 tools** (GET 27, POST 2, PUT 1, DELETE 1), 14 templated groups, all 14 parameters from the default
  `numeric` rule (`/api/{books,shelves,chapters,pages,attachments,comments,users,roles}/{numeric}`, the book PUT/DELETE,
  `search/book/{numeric}`, `search/chapter/{numeric}`, `content-permissions/book/{numeric}`, `content-permissions/page/{numeric}`).
  BookStack ids are plain integers, so none of the three opt-in rules fired: the manifest without rules is identical in tool
  count and names (31). 6 distinct query parameter names (`count`, `filter[book_id]`, `filter[name:like]`, `name`, `query`,
  `sort`); 3 tools with a body shape (POST books, POST pages, PUT books/{numeric}); coverage `complete-within-view` 31/31;
  0 excluded; unknowns authorization-model, response-semantics, state-transition; confidence `inferred`.
- `content-permissions/book/...` and `.../page/...` stay two tools because `book`/`page` are literal segments.
- `exclude_tools` in app.json (`system|image_gallery|recycle_bin|audit_log`) only keeps those four out of the task generator
  (version string, empty lists, a log of the seeding itself); they remain tools in the environment.
- The page export endpoints (`/api/pages/{id}/export/plaintext|markdown`) answer `application/octet-stream`, which scope_har
  would drop as non-JSON, so the capture does not call them.

## Seeded facts usable for retrieval questions
Books: "Lamp Room Procedures" (22:00 lamp check), "Tide Table Almanac" (owner Ada Finch), "Quarry Audit Manual" (owner Rui
Castellanos, tag ledger=GL-2291, Quarry Auditors view grant), "Saltmarsh Depot Inventory", "Blue Heron Kitchen Recipes"
(owner Mina Okafor, tag cook=Marisol Okonkwo-Reyes). Shelves: "Lighthouse Rota Handbooks", "Granite Ledger Archive" (owner
Rui), "Copperfield Annex Stores". Chapters: "Wick and Lens Care" (wicks 4 mm), "Night Watch Handover" (06:00), "Winter Spring
Tides" (5.8 metres off Granite Point), "North Quarry Counts", "Lamp Oil Ledger" (180 litres). Pages include "January Tide
Readings", "Terrace Seven Tally" (58 blocks, cart 7 retired), "Smoked Kelp Broth". Attachments "Wick Gauge Diagram",
"Terrace Seven Survey Sheet". Roles "Tide Clerks" ("Keep the tide tables and the night watch log.") and "Quarry Auditors".

## Episodes
No misses. Four of the twelve generated answers are the admin's own name or slug (`created_by`/`updated_by` fields), which a
model could guess; the episode note on the card says so.

## Rebuild, 2026-10-18

After review, the shared task generator was tightened: an answer must be a distinctive value that occurs in this app's seed and capture inputs, never the admin account's own identity, in at most 12 recorded responses, and unique across the tasks; each tool gets at most two tasks. Bundle, smoke, eval and card were re-run from the same capture. The bundle and eval numbers earlier in this file describe the first build; these are the published ones.

- bundle: 12 retrieval tasks from 18 recorded reads with an eligible field (up to two tasks per tool); field values rejected: admin identity 27, not distinctive 15, not in the seed inputs 1.
- smoke: passed.
- eval `openai/gpt-oss-120b:groq`: 12/12.
- eval `zai-org/GLM-5.3-Flash:zai-org`: 12/12.
- card and dry publish: 24 episodes, dataset 6.5 MB.
