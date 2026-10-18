# Mattermost Team Edition capture notes

## What ran
- App: Mattermost Team Edition **12.0.0** (build 38519854955, build hash 1f5e0e9ba40da7ba0741659346e0a385a623d6a4, build date
  2026-10-14; `X-Version-Id: 12.0.0.38519854955.1075cfe2b49072f29d81aa34ec1eacddd79e439aa930a34a6835d60c6c8579a8.false`).
  Image `mattermost/mattermost-team-edition@sha256:c213d4eb01c2973a3814f57dab4e0629287b92896cb2f98d27134aa62ee5c3cc` (amd64) with
  `postgres@sha256:721873c34ceb9f8d8fc265984940dc982404c105f19ad51be9fdc5970a6080ea` (16-alpine).
- Compose project `rea-mattermost`, host port `127.0.0.1:3104` -> 8065, `.admin` (600) supplied the generated DB and user passwords
  through `--env-file`. Besides the required env (postgres driver + datasource, site URL, open server, developer mode off) the
  compose sets capture hygiene: onboarding flow off, plugins off (no prepackaged plugin bundles), diagnostics/telemetry off,
  security-fix alert off, email off.
- Toolchain on the VM: Ubuntu 24.04 amd64, Docker 29.9.1 + Compose v5.6.0, Node v24.22.0, playwright-core 1.58.2 driving snap
  Chromium 155.0.8059.79 with `executablePath: /snap/bin/chromium`, `--no-sandbox` and `TMPDIR` under the app directory
  (snap confinement was not a problem with that), python3.12, rea 6.6.0.

## Seed (seed.py, idempotent, stdlib only; re-run produced the same ids and no duplicates)
- First `POST /api/v4/users` on the empty server created `rea-admin` (system admin). One login per seeded user minted a session
  for seeding only; those sessions were revoked (`sessions/revoke/all`) / logged out at the end of the script.
- Team `lighthouse-rota` ("Lighthouse Rota"); channels `granite-ledger`, `blue-heron-kitchen`, `night-shift` (public) and
  `keel-room` (private); users `ada.finch`, `rui.castellanos` added to the team and all four channels.
- 12 root posts (3 per channel, by all three authors) + 1 thread in granite-ledger with 3 replies; 1 reaction (`+1` by ada.finch on
  the allergen-cards post); 1 pinned post (the granite-ledger welcome). Custom emoji (optional) was skipped. Post text is synthetic
  rota/kitchen/watch content with made-up labels (NS-204, KR-77, GL-10-09, 8841-B) for retrieval questions.
- `seed-ids.json` (ids, names, version fields; no secrets) feeds capture.mjs.

## Capture (capture.mjs)
- `__landingPageSeen__` init script skips the "open in desktop app" landing page; login through the `/login` form; visits:
  the four channels, a permalink to a thread reply (opens the thread in the RHS), `/threads`, `/threads/<root>`, then the channel
  members RHS (`#member_rhs`), pinned messages RHS, channel info RHS and the Settings modal.
- Scripted in-page `fetch` sequence (CSRF header taken from the `MMCSRF` cookie for writes): users/me, users/me/teams, team by id
  and by name, team channels, channel by name, team stats/members, each channel + its posts (`per_page=30`), channel stats/members/
  member-by-id/pinned, pinned post, thread root, `/thread`, a reply, reactions, users `in_team` / `in_channel`, two users by id and
  by username, a user's teams and team channels, two post searches (POST), user search (POST), channel search (POST); then the
  scratch lifecycle: POST post -> GET -> PUT (edit) -> POST reaction -> GET -> GET reactions -> DELETE -> GET (404); re-read of
  the channel posts and `system/ping`.
- Full HAR: 440 `/api/v4/` entries, 120 MB with bodies (deleted at teardown).

## Scope (scope_har.py) and scrub
- `--origin http://127.0.0.1:3104 --keep-regex '^/api/v4/' --max-body 60000 --max-records 140`; drop regex = the tool's auth defaults
  plus UI polling/bootstrap noise: `roles/names|/image|limits|/agents|properties/groups|status/ids|users/ids|config/client|
  license/client|trial-license|users/stats|analytics|system/notices|client_perf|access_control|drafts|/unread|members/me/view|
  channel_members|categories|preferences|threads$` (the websocket and `users/ids`-style polling are left out by design).
- Result: **kept 129**; dropped path 796, drop-regex 323 (reported under the tool's `auth` key, which counts every drop-regex match,
  not only the login exchange), non-json 0, big-body 0, over-max 0. Methods GET 119 / POST 7 / PUT 2 / DELETE 1; statuses
  200 x127, 201 x1, 404 x1 (the re-read after delete). Scoped HAR 322,821 bytes,
  sha256 `e5874c112d0ab28d94c68595073b1e0512f0cadc8a47b5bf40914ef8d4cf470f`.
- Credential grep on the scoped HAR (occurrence counts): admin password 0, seeded-user password 0, DB password 0, `hf_` 0, `ghp_` 0,
  `Bearer ` 0, `MMAUTHTOKEN` 0, `MMCSRF` 0. Case-insensitive scan of every artefact for the forbidden project word: 0 hits.

## rea 6.6.0
- `inspect-web-network-capture ... har`: evidence `ev_7cc07ebe56003462bbd033d9c12c3a92d92badddff6f9199083c68e9a60357ba`,
  `sensitive_value_count` 0, 129 retained records. No `resource_constraint` from the capture or either view; both views ran in ~3 s.
- `inspect-analysis-view` environment-manifest with `after-uid-literal, opaque-token, sibling-variance`: evidence
  `ev_97f3c9f89c92adf208d73e8e8e5de3dcb34c5a19fac09fbb29280d423f3f5342`, confidence `inferred`, authority `historical-reference`,
  **37 tools** (GET 28, POST 6, PUT 2, DELETE 1), 33 params (opaque-token 32, numeric 1), 16 observed query names, 26 templated
  groups, 0 excluded groups, the three fixed unknowns (authorization-model, response-semantics, state-transition).
- No-rules variant: evidence `ev_520a920a6a48370899829dcef7b21b4fdb812eb8f8b9abda7c5784cb1d1dfdaf`, 58 tools, 1 templated group
  (only the format rule `{numeric}` on the thread-read timestamp), confidence `inferred`.
- Observations on the rules: every 26-char Mattermost id became `{uid}` / `{uid_2}` / `{uid_3}` (opaque-token). sibling-variance
  folded the `me` alias into `GET /api/v4/users/{uid}` (12 records = 2 by id + 10 `users/me`) and `GET /api/v4/users/{uid}/teams`
  (11 = 1 + 10 `users/me/teams`), because `me` is a literal sibling of an opaque-token parameter; `users/me/channels` and
  `users/me/teams/members` stayed literal (no templated sibling). The by-name lookups (`teams/name/lighthouse-rota`,
  `channels/name/granite-ledger`, `users/username/ada.finch`, `users/username/rui.castellanos`) stayed literal tools: the rules
  only fold literals into parameters produced by an opt-in rule, and the name segments are not opaque tokens, so the manifest has
  two username tools instead of one `{username}` tool. Repeated UI reads (users/me x10, users/me/teams x10, teams x9,
  users/me/channels x9, users/me/teams/members x9, channels/{id}/stats x9, GET /users x13) inflate the record count without adding
  tools.

## Teardown
`docker compose -p rea-mattermost down -v`; full HAR with bodies, `.admin`, Chromium temp dir removed. Only the scoped HAR left the VM.

## Files
compose.yml, seed.py, run.sh (staged runner: up|seed|capture|scope|check|rea|summary|down|all), summarize.py, capture.mjs,
seed-ids.json, scope-summary.json, mattermost.scoped.har, mattermost.capture.json, mattermost.manifest.json,
mattermost.manifest.norules.json, summary.json, README-notes.md.
