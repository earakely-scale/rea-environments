# Memos 0.31.0 capture notes (rea showcase, batch 2)

- App: `neosmemo/memos:0.31.0` (the tag `stable` pointed at the same digest on the capture day), digest
  `neosmemo/memos@sha256:24c2707ddd8fbd2ceaa7a61ecab86a53cdcde640b24ce572b73da14b00b5785f`. `GET /api/v1/instance/profile`
  reports version 0.31.0, commit `2b2192d4e153bd04f1d325b60fd880cf00d68b01`; the container log shows a fresh sqlite schema
  0.31.8. Licence MIT (LICENSE at the v0.31.0 tag: "MIT License, Copyright (c) 2025 Memos").
- Compose project `rea-memos`, loopback-only `127.0.0.1:3205 -> 5230`, `MEMOS_MODE=prod`, `MEMOS_DRIVER=sqlite`,
  `MEMOS_INSTANCE_URL=http://127.0.0.1:3205`, volume `memos-data:/var/opt/memos`; healthcheck `wget /api/v1/instance/profile`,
  healthy within seconds.
- Tooling on the VM: rea 6.6.0, playwright-core 1.58.2, Chromium 155.0.8059.79 (snap, plain `chromium.launch`), node v24.22.0,
  python 3.12.3, docker 29.9.1, compose 5.6.0.

## The surprising part: the web UI does not speak JSON
The Memos 0.31 web UI calls its backend over Connect RPC with **binary protobuf**: every UI request is
`POST /memos.api.v1.<Service>/<Method>` with `application/proto` bodies (103 such calls in this session, 102 protobuf plus
the pre-login RefreshToken 401 answered as JSON: SignIn,
GetCurrentUser, ListMemos, ListSpaces, ListUserSettings, GetUserStats, ...). Nothing in that traffic is JSON, so
`scope_har.py` cannot keep it and REA could not read it anyway. The same services are also published as a JSON REST
mapping under `/api/v1` (grpc-gateway style, AIP resource names such as `memos/<id>`, `users/<username>`,
`spaces/<uuid>`), which is what the scripted part of the capture uses. The UI keeps its short-lived access token in
`localStorage.memos_access_token` (refresh token in the HttpOnly cookie `memos_refresh`); the script reads the access
token in the page and sends it as `Authorization: Bearer ...`. So every record in the scoped HAR comes from the scripted
`fetch` sequence; the UI page visits are real but leave no JSON trace.

## Pipeline (all under ~/capture/memos on the VM)
1. `docker compose -p rea-memos -f compose.yml up -d` (instance profile reports `needsSetup: true` on a fresh volume).
2. `python3 seed.py` (stdlib urllib, idempotent): `POST /api/v1/users` creates `rea-admin` as the first account (role
   ADMIN, Rea Admin, rea-admin@example.test); the admin then creates ada-finch, rui-castellanos and mina-okafor. All four
   passwords are generated at run time into `.admin` (mode 600); `POST /api/v1/auth/signin` tokens stay in process memory.
   Seeds bios, 9 memos (tags inline as `#tag`; one pinned through `PATCH ?updateMask=pinned` because the pinned flag is
   ignored on create; one archived through `PATCH ?updateMask=state`; one with a task list; one with a location; one with
   SPACE visibility), 3 comments, 3 reactions, a REFERENCE relation, space "Saltmarsh Depot Crew" (ada-finch accepted,
   mina-okafor pending), space "Blue Heron Kitchen Rota" owned by mina-okafor with a pending invitation for rea-admin, the
   saved memo view "Granite Ledger notes" and the admin's GENERAL settings. Single-line memo contents are kept under 80
   characters so they can serve as answers. A webhook was not seeded: Memos rejects webhook targets that resolve to private
   or reserved addresses ("webhook URL must not resolve to a reserved or private IP address"), including `.test` hosts.
3. `NODE_PATH=~/capture/node_modules node capture.mjs`: UI login at `/auth` (`#signin-username`, `#signin-password`),
   then `/`, `/explore`, `/archived`, the stone-count memo page `/memos/<id>`, `/u/ada-finch`, `/inbox`, `/setting`; then 67
   scripted `fetch` calls: instance profile; users list, a `filter=username == 'mina-okafor'` list and the four users by
   name; memos lists (default, `state=ARCHIVED`, CEL filters `"granite-ledger" in tags`, `content.contains("tide")`,
   `pinned == true`, `creator == "users/ada-finch"`, `visibility == "PUBLIC"` with `orderBy=update_time asc`,
   `has_task_list == true`, `"lighthouse-rota" in tags`); all 9 memos and the 3 comments by name; comments of 8 memos,
   reactions of 6, relations of 4, attachments of 1; spaces list, the crew space, its members, invitations, mina-okafor's
   invitation and ada-finch's membership by name; the admin's own space invitations and the invitation to the kitchen
   space by name; saved views list and by name; user settings list and GENERAL; instance stats; notifications. Write path:
   a scratch memo POST, PATCH (`updateMask=content`), GET, DELETE, GET (404), then the memo list again.
   Raw HAR 484 entries, 20.9 MB, deleted after scoping.
   Reads of the custom methods `users/<u>:getStats`, `users:stats` and of `/api/v1/identity-providers` were tried in an
   earlier pass and removed: with them, REA's opt-in `sibling-variance` rule merged `/api/v1/{memos,users,spaces,...}`
   into one `get_by_v1_id` tool and folded `users/<u>:getStats` into `users/{user_id}`.
4. `python3 -I ~/capture/scope_har.py memos.full.har memos.scoped.har --origin http://127.0.0.1:3205 --keep-regex '^/api/v1/'
   --drop-regex 'login|logout|signin|signup|password|session|token|oauth|csrf|/auth/|/sse'` -> kept 67 (GET 64, POST 1,
   PATCH 1, DELETE 1); dropped path 405 (UI shell, assets, the 103 Connect/protobuf calls), auth 12 (Connect SignIn and
   RefreshToken, two sign-in JS chunks, 8 `GET /api/v1/sse` event streams), other-origin 0, non-json 0, big-body 0.
   Statuses 200 x66, 404 x1. Scoped HAR 113,900 bytes, sha256
   `88d94da05d999e68d6b7b3692e0c3bab48b02390921bc66ea2352f39df4cf2de`. Credential grep: every `.admin` value 0, `eyJ` 0,
   `Bearer ` 0, `accessToken` 0, `memos_refresh`/`memos_access_token` 0, cookies 0; only content-type/accept headers remain.
5. `python3 ~/showcase/envbuild.py all memos` (manifest, bundle, smoke, eval, card).

## Manifest facts
- Capture Evidence `ev_c312b72e2468894d9dfbe7bffe1b38ab8a60dfad82d049e36ffd9c199420c31e` (67 records, observed).
- With the opt-in rules: `ev_9535f9c5f689cd44d904d5b6e3b3462b1bc522be7ae1397e1a2a0eca35296955`, confidence `inferred`,
  26 tools (GET 23, POST 1, PATCH 1, DELETE 1), 12 templated groups, 12 path parameters: 7 from the built-in `uuid` rule
  (space and view ids) and 5 from `sibling-variance` (`memos/{memo_id}` and its `/comments`, `/reactions`, `/relations`,
  and `users/{user_id}`); `opaque-token` and `after-uid-literal` matched nothing (Memos ids are 22-character mixed-case
  base-57 strings). Coverage complete-within-view, 0 excluded groups, 9 limitations (one of them states that merged
  parameters may conflate distinct resources). Query parameter names: filter, orderBy, pageSize, state, updateMask.
  Body shapes on `post_memos` and the scratch PATCH.
- Without the rules: `ev_d78af12ffd40cd37e54d3867dbfa97a6a8d6c7045ecbcd4c822862756519ab54`, 56 tools (GET 53): every memo
  id, comments/reactions/relations path and user name stays a literal tool.
- The scratch memo's PATCH, DELETE and its post-delete GET stay literal tools (`patch_memos_fdsic6f6xuhk3yamkb5ohn`,
  ...): one sample each is not enough for `sibling-variance`, and the id shape is not `opaque-token`. The 404 re-read
  is folded into `get_memos_by_memo_id` (statuses 200 and 404). Memos answers DELETE with `{}` and 200.
- Members/invitations under two different space uuids stay as separate literal-suffix tools
  (`get_spaces_invitations_mina_okafor_by_uuid`, `get_spaces_invitations_rea_admin_by_uuid`,
  `get_spaces_members_ada_finch_by_uuid`).

## Tasks and eval
- `exclude_tools` = `settings|notifications|stats|members|reactions|relations|attachments|invitations_mina|invitations_rea`:
  settings/notifications/stats carry no readable answer, and members/reactions/relations/single-invitation tools only
  offer resource names (`spaces/<uuid>/members/<user>`, `memos/<id>/reactions/1`). 12 candidates, 12 tasks.
- Because every Memos object has an AIP `name`, the generator still picks a `name` field in 6 of 12 tasks
  (`memos/<id>`, `spaces/<uuid>`, `users/mina-okafor`, an invitation name, a view name); the others ask for a description,
  a comment, a memo's content, a space title, a view title and the admin bio from the instance profile.
- Smoke passed (26 tools). gpt-oss-120b 11/12, GLM-5.3-Flash 12/12, no provider errors. The miss (`qa-03`, the view's
  `name`): gpt-oss answered the view's title "Granite Ledger notes" instead of `users/rea-admin/views/<uuid>`, a model
  error on a question that is fair but easy to misread; recorded in `episode_notes`.

## Seeded facts usable for retrieval questions
Bios: rea-admin "Keeper of the Lighthouse Rota since the spring census.", ada-finch "Keeps the tide tables for the winter
rota.", rui-castellanos "Audits the Granite Ledger stone counts.", mina-okafor "Relief keeper on Blue Heron Spit."
Memos: "#lighthouse-rota Shift three at Granite Point Light runs 22:00 to 06:00." (pinned), "#granite-ledger Stone count
GL-2291: 412 blocks in the north quarry.", "#blue-heron-kitchen Blue Heron Kitchen serves 36 covers per sitting." (location
"Blue Heron Spit boathouse"), "#saltmarsh-depot Order SO-4471: 180 litres of lamp oil delivered." (private), the Granite
Ledger checklist, "#copperfield-annex Copperfield Annex beacon converted to an LED cluster." (archived), Ada's "January low
water at Granite Point: 04:12 on the third.", Rui's "Cart number 7 retired; wheels sent to the annex workshop.", the crew
meeting at the Copperfield Annex boathouse at 18:30. Comments: "I will bring the January tide tables to the handover.",
"Count confirmed at the tidal yard; two blocks are cracked.", "Thanks Ada, copied into the rota binder." Spaces: "Saltmarsh
Depot Crew" ("Keepers and quartermasters of the Saltmarsh Depot."), "Blue Heron Kitchen Rota" ("Night-shift supper rota for
the Heron Flats keepers."). View "Granite Ledger notes".

## Teardown
`docker compose -p rea-memos -f compose.yml down -v`; `memos.full.har`, `.admin`, `req.*.json` and the probe/explore
scripts removed on the VM.

## Rebuild, 2026-10-18

After review, the shared task generator was tightened: an answer must be a distinctive value that occurs in this app's seed and capture inputs, never the admin account's own identity, in at most 12 recorded responses, and unique across the tasks; each tool gets at most two tasks. Bundle, smoke, eval and card were re-run from the same capture. The bundle and eval numbers earlier in this file describe the first build; these are the published ones.

- bundle: 12 retrieval tasks from 12 recorded reads with an eligible field (up to two tasks per tool); field values rejected: admin identity 3, not distinctive 2, in the tool name or arguments 1.
- smoke: passed.
- eval `openai/gpt-oss-120b:groq`: 12/12.
- eval `zai-org/GLM-5.3-Flash:zai-org`: 12/12.
- card and dry publish: 24 episodes, dataset 6.5 MB.

## v0.2.0 capture

Re-recorded on a fresh instance seeded by the same script, with the steps above unless stated: 80 scoped records (GET 74, POST 2, PATCH 2, DELETE 2), scoped HAR sha256 `82239f71…`, 176,934 bytes; capture `ev_9a022f8f…`. The write block records two scratch memos with `record_writes.mjs`: each created, edited by PATCH with `updateMask=content` and deleted, every write read back by name and in the memo list. 26 tools, with the update and delete now templated on the memo id; no write is served: Memos names a memo `memos/<id>` while its paths carry only `<id>`, so the memo type's identity is never proven.
