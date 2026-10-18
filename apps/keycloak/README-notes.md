# Keycloak 26.8.1 capture notes (rea showcase, batch 2)

- App: `quay.io/keycloak/keycloak:26.8.1` (newest 26.x tag on quay.io on 2026-10-18), digest
  `quay.io/keycloak/keycloak@sha256:79c623a22abacf3fe6c00a5fb30f5b7843d717b234033b80995891c06116d244`, version 26.8.1 from
  `GET /admin/serverinfo` (`systemInfo.version`). Licence Apache-2.0 (`/opt/keycloak/LICENSE.txt` in the image).
  `start-dev` with the embedded H2 file database in the `kc-data` volume (the dev-mode default; no second service),
  `KC_HEALTH_ENABLED=true`, compose project `rea-keycloak`, loopback-only port `127.0.0.1:3210 -> 8080`.
- The image has no curl or wget; the compose healthcheck speaks HTTP over bash `/dev/tcp` to the management port
  (`9000/health/ready`). Healthy after 22 s on a cold volume.
- Tooling on the VM: rea 6.6.0, playwright-core 1.58.2, Chromium (snap) launched headless with `--no-sandbox`, node v24.22.0,
  python 3.12.3, Docker 29.9.1, compose v5.6.0.

## Admin credentials
`up.sh` generates two values into `.admin` (mode 600): a bootstrap password, exported only to the `docker compose up`
invocation as `KC_BOOTSTRAP_ADMIN_PASSWORD` for the temporary admin `rea-bootstrap`, and the password of the permanent admin.
`seed.py` creates the permanent master-realm admin `rea-admin` (realm role `admin`) with the second value, then deletes
`rea-bootstrap`, so the console shows no temporary-admin banner and the value left in the container environment no longer
opens anything. Nothing prints either value; `.admin` was deleted at teardown.

## Pipeline (all under ~/capture/keycloak on the VM)
1. `./up.sh` (writes `.admin` once, `docker compose -p rea-keycloak -f compose.yml up -d`, waits for healthy).
2. `python3 seed.py` (stdlib urllib, tokens from the admin-cli password grant, refreshed before the 60 s master lifespan):
   permanent admin as above, then realm `lighthouse-rota` (display name "Lighthouse Rota Identity", organizations
   enabled), 3 realm roles with descriptions, groups Night Shift / Quarry Crew / Galley Team (each mapped to one realm role,
   each with a description) plus subgroup Lamp Room Crew under Night Shift, users ada.finch, rui.castellanos, mina.okafor,
   tomas.vey (disabled) with group memberships, public clients `granite-ledger-portal` (roles ledger-viewer, ledger-editor)
   and `blue-heron-kitchen-till` (role till-operator) with client-role mappings for Rui and Mina, client scope
   `tide-tables` (optional on the ledger portal), organizations Copperfield Annex and Saltmarsh Depot (domains under
   `example.test`, Mina a member), and a copy of the browser flow named `granite gate browser` with a description.
   Idempotent (lookups by name before every create; leftover `rea-scratch*` users are deleted). Writes `seed-ids.json`.
   Clients are public on purpose: a confidential client's representation would carry a generated secret.
3. `NODE_PATH=~/capture/node_modules node capture.mjs`: UI login at `/admin/master/console/` (master login page, `#username`,
   `#password`, `#kc-login`), then the scripted read sequence from inside the page (39 calls: realm, user list, 4 users by id,
   user search, Ada's groups, Rui's realm role mappings, Mina's client role mappings, group list, 4 groups by id, children,
   members, group search, client search by clientId, 2 clients by id, client roles, one client role by name, realm roles,
   one role by name, one role by id, the groups holding galley-steward, the client scope, organization list, 2 organizations,
   organization members, the copied flow), then 10 console pages of the realm, then the write path: scratch user created
   through `POST partialImport`, `PUT` edit (204), re-read, `DELETE` (204), re-read (404), `users/count`.
   Two things were learned the hard way: a hash-only navigation keeps the console on its current realm (it kept calling
   `/admin/realms/master/...` with the lighthouse-rota user id and got 404s), so every page visit is a `goto` plus a reload;
   and the console's own first read of a user carries `userProfileMetadata=true`, whose profile metadata made a poor task,
   so the scripted reads now run before the UI pages and each tool's first record is a seeded object.
   Full HAR 960 entries, deleted after scoping.
4. `python3 -I ~/capture/scope_har.py keycloak.full.har keycloak.scoped.har --origin http://127.0.0.1:3210
   --keep-regex '^/admin/realms/lighthouse-rota(/|$)'` -> kept 73 (GET 70, POST 1, PUT 1, DELETE 1; statuses 200 x70, 204 x2,
   404 x1); dropped path 843, auth 44, non-json 0, big-body 0, over-max 0. Credential grep on the scoped HAR: `.admin`
   value literals 0, `hf_|ghp_|Bearer ` shapes 0, Keycloak cookie names 0. sha256
   `7c78d99263c9fb922b3fbf714619a3d378f08781b2f677d6a473bd28d5b85b3b`, 197,162 bytes.
5. `python3 ~/showcase/envbuild.py all keycloak`: capture evidence
   `ev_21d8808f42337b36a19f943f7bca1058d9f2c73b660d5bce1f10b05539ca525d` (73 records), manifest
   `ev_b1030270ddcec481e452055bb5db7711cf3539cb97b7d86b9733f1023452fafa` (confidence inferred), no-rules manifest
   `ev_6898940f9e4f1b716c00ced3346e4b1d5f7ba01aadd8269592edf408bf70ac1a`; bundle with 12 retrieval tasks from 29 candidates;
   smoke passed (replay 1, 30 s); eval `openai/gpt-oss-120b:groq` 12/12 and `zai-org/GLM-5.3-Flash:zai-org` 12/12, one tool
   call per episode on average, mean input tokens 11.1k and 14.0k; card and dry publish: 13 tasks, 25 runs,
   `~/showcase/datasets/keycloak` (6.7 MB), scans clean.
6. `./down.sh` (`docker compose -p rea-keycloak -f compose.yml down -v` with a placeholder for the compose file's required
   bootstrap variable, then `keycloak.full.har`, `.admin`, `req.*.json` removed).

## Manifest facts
- 40 tools (GET 39, POST 1) with or without the opt-in rules: every by-id segment is a UUID, which rea's built-in `uuid`
  rule templates in both views (19 templated groups, 18 `uuid` params; `users/{uuid}/role-mappings/clients/{uuid}` has two).
  after-uid-literal, opaque-token and sibling-variance matched nothing. Role names (`roles/tide-keeper`,
  `roles/galley-steward/groups`, `clients/{uuid}/roles/till-operator`) follow fixed segments and stay literal tools.
- 2 excluded groups, both `non-json`: Keycloak answers the scratch user's `PUT` and `DELETE` with 204 and no content type.
  scope_har.py keeps such empty replies, rea's manifest view does not. `POST /users` answers 201 with no body and no content
  type, which scope_har.py itself drops, so the create goes through `POST /admin/realms/{realm}/partialImport` (answers
  `{"added":1,"results":[{"action":"ADDED","resourceType":"USER",...}]}`). That is the manifest's only write tool.
- 25 query-parameter names across tools; statuses 200 and 404; coverage complete-within-view (40/40); unknowns
  authorization-model, response-semantics, state-transition.
- UI-only tools: `ui-ext/{info,brute-force-user,realms/names,authentication-management/flows}`, `users/profile`,
  `users/{uuid}/unmanagedAttributes`, `attack-detection/brute-force/users/{uuid}`, `authentication/required-actions`,
  `default-default-client-scopes`, `default-optional-client-scopes`, `localization/en`, `client-scopes`, a trailing-slash
  `clients/`, `groups/` and `organizations/` variant each (separate tools `_2`). `exclude_tools` keeps the ui-ext, profile,
  count, localization, attack-detection, required-actions, default-scope and unmanaged-attribute tools out of the tasks.
- The console's 306 KB `/admin/serverinfo` read is outside the realm prefix, so it is dropped as path before the body cap.

## Tasks and episodes
12 tasks: Rui's realm role mapping (`default-roles-lighthouse-rota`), the till-operator client role, the Blue Heron
Kitchen Till client name, Mina's client role mapping, Ada's first group (Lamp Room Crew), the ledger-viewer role
description, Rui's email, the quarry-auditor role by id, Night Shift's child group, the Quarry Crew description, the
Quarry Crew member, and the Saltmarsh Depot member. Both models passed all 12 in one tool call each.

## Seeded facts usable for retrieval questions
Realm display name "Lighthouse Rota Identity". Role descriptions: tide-keeper "Keeps the tide tables and signs the night log
at the lamp gallery.", quarry-auditor "Audits the Granite Ledger stone counts every quarter.", galley-steward "Runs the Blue
Heron Kitchen galley rota and orders kelp." Group descriptions: Night Shift "Lamp watch from 22:00 to 06:00; hands over at
the Saltmarsh Depot bell.", Quarry Crew "Counts granite blocks in the north quarry and the tidal yard.", Galley Team "Cooks
and stewards for the Blue Heron Kitchen tide-table menu.", Lamp Room Crew "Trims wicks and polishes the Fresnel lens before
dusk." Clients: "Granite Ledger Portal" ("Stone-count dashboard for the quarry auditors."), "Blue Heron Kitchen Till"
("Point-of-sale app for the tide-table menu sittings."). Client roles: ledger-viewer "Reads the quarterly stone counts.",
ledger-editor "Corrects tallies after an audit.", till-operator "Opens and closes the till for each sitting." Client scope
tide-tables "Grants read access to the published tide tables." Organizations: Copperfield Annex "Contractor crew that
repaints the lamp gallery every spring.", Saltmarsh Depot "Supply depot for lamp oil, rope and dried kelp." Flow
"granite gate browser": "Browser login used by the Granite Ledger kiosks in the quarry office." Tomas Vey is disabled.

## Rebuild, 2026-10-18

After review, the shared task generator was tightened: an answer must be a distinctive value that occurs in this app's seed and capture inputs, never the admin account's own identity, in at most 12 recorded responses, and unique across the tasks; each tool gets at most two tasks. Bundle, smoke, eval and card were re-run from the same capture. The bundle and eval numbers earlier in this file describe the first build; these are the published ones.

The recorded application version was corrected from 26.8 to 26.8.1 (the pinned image tag) and the manifest step re-run.

- bundle: 12 retrieval tasks from 25 recorded reads with an eligible field (up to two tasks per tool); field values rejected: in the tool name or arguments 3, in too many responses 7, not distinctive 22, not in the seed inputs 12.
- smoke: passed.
- eval `openai/gpt-oss-120b:groq`: 12/12.
- eval `zai-org/GLM-5.3-Flash:zai-org`: 12/12.
- card and dry publish: 24 episodes, dataset 6.7 MB.
