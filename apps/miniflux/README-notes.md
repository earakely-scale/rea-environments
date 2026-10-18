# Miniflux 2.3 capture notes (rea showcase)

- App: `miniflux/miniflux:2.3.3`, digest `miniflux/miniflux@sha256:49d7b60987616387c306a8023087b31f2c9b7b21288b523026cb04058e8b6dbb`
  (`miniflux -i`: version 2.3.3, commit c4d54f87, built 2026-07-23, go1.26.5, linux/amd64). Licence Apache-2.0 (image label
  `org.opencontainers.image.licenses` and the upstream LICENSE). Database `postgres:17.11`
  (`postgres@sha256:2d2b8998d31037bf721cfdf764d76ba74171b4fab3431b7f72c27c56ddbdf9e3`), no host port, schema version 132
  after `RUN_MIGRATIONS=1`. Feed host `nginx:1.30.6-alpine` (`nginx@sha256:970364228b1e4f932abc22d321932816782cca8a20b85a77552a7cfe9acfb3b5`)
  serving `./feeds` read-only as `http://feeds/<file>` on the compose network, no host port. Compose project `rea-miniflux`,
  loopback-only port `127.0.0.1:3217 -> 8080`, `BASE_URL=http://127.0.0.1:3217`, admin `rea-admin` created by
  `CREATE_ADMIN=1` from the run-time env file.
- Tooling on the VM: rea 6.6.0, playwright-core 1.58.2, snap Chromium 155 (`chromium.launch`, `--no-sandbox`), node v24,
  python 3.12, docker 29.9.1.

## Surprises
- **Private networks.** Miniflux refuses to fetch feeds from private addresses by default; the compose feed host is one, so
  compose sets `FETCHER_ALLOW_PRIVATE_NETWORKS=1` (option name found in the 2.3.3 binary). `DISABLE_SCHEDULER_SERVICES=1`
  stops background polling, so entries change only through the explicit calls in seed.py and capture.mjs.
- **The web UI is not a JSON client.** Miniflux renders HTML on the server; its pages make no `/v1` calls, and the `/v1`
  API does not accept the UI session cookie (Basic auth or `X-Auth-Token` only). capture.mjs signs in through the UI form,
  browses 11 pages, then calls `/v1` from inside the signed-in page with a Basic header; scoping removes all headers.
- **Bodiless writes are not tools.** `DELETE /v1/categories/{id}`, `PUT /v1/entries` (mark read/unread),
  `PUT /v1/entries/{id}/bookmark` and `PUT /v1/feeds/{id}/refresh` answer 204 with no body. scope_har.py keeps them, but
  rea excludes the four groups as `non-json`, so the manifest's write tools are `POST /v1/categories`,
  `PUT /v1/categories/{id}`, `PUT /v1/feeds/{id}` and `POST /v1/discover`.
- **Ids are integers**, so REA's unconditional `numeric` rule templates them; the opt-in rules matched nothing and the
  manifest is identical with and without them (22 tools). Two-id routes get names like `get_feeds_entries_by_id_id_2`.
- `GET /v1/users/{identifier}` accepts a user name as well as an id; the recorded `/v1/users/mina-okafor` stays a literal
  tool (excluded from task generation, its only string field is the name in its own path).
- The first capture gave three tasks whose answer was the same channel description, so the feeds carry no channel
  description and the stack was rebuilt from scratch before the final capture.
- A new user gets its own default category "All"; the scratch category therefore had id 7, not 5.

## Pipeline (all under ~/capture/miniflux on the VM)
1. `python3 seed.py init` writes `.admin` (mode 600: admin and database passwords generated at run time) and the four feed
   files. `docker compose -p rea-miniflux -f compose.yml --env-file .admin up -d`; healthy (`miniflux -healthcheck auto`)
   within about 10 s.
2. `python3 seed.py` (Basic auth as rea-admin): 3 categories, 4 subscriptions (`POST /v1/feeds`, Miniflux fetches each
   feed on creation: 12 entries), a second, non-admin user `mina-okafor` (random password, discarded), 2 entries marked
   read, 2 starred, user time zone UTC. Idempotent (looks up categories, feed URLs, users and starred state first) and
   removes `Rea scratch*` categories left by an interrupted capture. Writes `seed-ids.json` (ids only).
3. `NODE_PATH=~/capture/node_modules node capture.mjs`: UI sign-in at `/login`, visits `/unread`, `/starred`, `/history`,
   `/feeds`, one feed's entries, one entry, `/categories`, one category's entries, `/search?q=kelp`, `/settings`, `/users`;
   then 86 scripted `/v1` calls: version, me, users (list, by id x2, by name), categories (list, with counts, feeds and
   entries per category, every entry through its category), feeds (list, counters, by id x4, entries per feed, every entry
   through its feed, one icon 404), every entry by id (12), 7 entry filters (unread, starred, `search=kelp`, read,
   `category_id`, `before_entry_id`, `published_after`), integrations status, `POST /v1/discover` on a feed-host URL, a
   no-op feed update and refresh, then a scratch category POST, PUT, list, DELETE, re-read (404), and entry state changes
   (read then unread, star then unstar) with re-reads. Full HAR 1.8 MB, 154 entries (deleted after scoping).
4. `python3 -I ~/capture/scope_har.py miniflux.full.har miniflux.scoped.har --origin http://127.0.0.1:3217 --keep-regex '^/v1/'`
   (default drop regex) -> kept 86 (GET 76, PUT 7, POST 2, DELETE 1; statuses 200 x75, 201 x3, 204 x6, 404 x2); dropped
   path 67 (15 HTML pages, 13 stylesheets, 14 scripts, 26 SVG icons), auth 1 (`POST /login`), non-json 0, big-body 0.
   278,479 bytes in the scope summary; 279,002 bytes on disk, sha256
   `da65467c3008cfc9b99d9b69cadc9c63bf8b1d66d377e0ea4b65504982c42072`. Credential check (counts only): both passwords 0,
   the Basic header value 0, session cookie values 0, `Bearer `/`hf_`/`ghp_` 0. Feed objects carry empty `password`,
   `cookie` and `user_agent` fields (per-feed fetch settings, unused here).
5. `python3 ~/showcase/envbuild.py all miniflux`: capture evidence
   `ev_d65576c62c9473341453db9efd48b5124980707e66c363e2c210dd404a877235` (86 records, observed); manifest
   `ev_87cdbc359ae8ac5356656a9666026abc94623345fffe2f620f3a1c8eee2ff841` (inferred, view digest
   `c0e8757f6beec6a85ea7773d26c8210513165fab4144143cf616e6beddd3da13`); no-rules manifest
   `ev_88757ead75bfeaaba2ef67de37877306d98c7d7bf88531692023493ad8fd82a3`. Bundle: 12 retrieval tasks from 12 candidates.
   Smoke passed (22 tools listed, 26.6 s). Eval: `openai/gpt-oss-120b:groq` 11/12, `zai-org/GLM-5.3-Flash:zai-org` 8/12.
   Card and dry publish: `~/showcase/datasets/miniflux` (24 episodes, 6.9 MB).
6. `docker compose -p rea-miniflux -f compose.yml down -v`; `miniflux.full.har`, `.admin`, `req.*.json` and the feed
   files removed.

## Manifest facts
- 22 tools (GET 18, POST 2, PUT 2), 14 templated groups, 13 `numeric` parameters; same 22 tools without the opt-in rules.
  16 query-parameter names across tools, 10 distinct (before_entry_id, category_id, counts, direction, limit, order,
  published_after, search, starred, status); 4 tools with a body shape (POST categories, PUT categories/{id},
  PUT feeds/{id}, POST discover); statuses 200/201/404; 4 groups excluded as non-json (the 204 writes above); coverage
  complete-within-view 22/22; unknowns authorization-model, response-semantics, state-transition; 9 limitations.
- `exclude_tools` keeps version, me, integrations status, feed counters, the icon 404, discover and the literal
  `users/mina-okafor` out of task generation, which leaves exactly 12 candidates.

## Tasks and episodes
Tasks cover feeds by id (category title), users by id, a category's feeds (first feed title), a feed's entries, entries
by feed and by category, entries by id (content), the unread entry list (feed title of the newest), users, categories
and feeds lists. gpt-oss-120b 11/12, GLM-5.3-Flash 8/12. All five misses come from the generator's wording for plain
lists (a field "of the first entry"): in Miniflux an entry is an article, and the models went on to read entries
(see `episode_notes`). Excluding those list tools would leave 8 candidates, below the 10-task bar, so they stay and the
collision is documented.

## Rebuild, 2026-10-18

After review, the shared task generator was tightened: an answer must be a distinctive value that occurs in this app's seed and capture inputs, never the admin account's own identity, in at most 16 recorded responses, and unique across the tasks; each tool gets at most two tasks. Bundle, smoke, eval and card were re-run from the same capture. The bundle and eval numbers earlier in this file describe the first build; these are the published ones.

- bundle: 7 retrieval tasks from 7 recorded reads with an eligible field (up to two tasks per tool); field values rejected: not distinctive 7, in too many responses 15, not in the seed inputs 3, admin identity 1.
- smoke: passed.
- eval `openai/gpt-oss-120b:groq`: 7/7.
- eval `zai-org/GLM-5.3-Flash:zai-org`: 7/7.
- card and dry publish: 14 episodes, dataset 6.7 MB.
