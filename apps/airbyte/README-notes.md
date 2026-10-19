# Airbyte 2.4.0 capture notes (rea showcase)

- App: Airbyte community edition 2.4.0 (helm chart V2 `airbyte` 2.4.0), installed by the vendor installer `abctl` v0.30.4
  (release tarball checksum-verified against `abctl_0.30.4_checksums.txt`) into a kind cluster `airbyte-abctl`
  (`kindest/node:v1.32.2@sha256:f226345927d7e348497136874b6d207e0b32cc52154ad8323129352923a3142f`, namespace `airbyte-abctl`,
  ingress-nginx 4.15.1). Pinned images: `airbyte/server:2.4.0@sha256:f3577020d4f3835be66d19da24a78baa9869f55d1a60f492325432b7d238df76`,
  `airbyte/worker:2.4.0@sha256:044022ebec4554c27101377643110772fdd3659ad67a6f7c8c8dc71d96c4d441`, connectors
  `airbyte/source-faker:7.2.1@sha256:358625056eac2fa89f0ae92272e153e598b67c5515536b535f244df20b2ff8eb` (Sample Data) and
  `airbyte/destination-dev-null:0.9.7@sha256:d55727244cc00c1c4eccf3b35ce851a2ceb24c272c8e01dc7ee3237531bd39ed`.
  `GET /api/v1/instance_configuration` reported `edition community`, `version 2.4.0`, auth mode `simple`.
- Licence: the platform's LICENSE is the Elastic License 2.0 (ELv2), read from airbytehq/airbyte-platform; the chart index
  annotates `Elastic-2.0`. Use on our own VM with invented data is within the grant; nothing is offered as a hosted service.
- Install command (`install.sh`): `DO_NOT_TRACK=1 abctl local install --chart-version 2.4.0 --port 3302 --insecure-cookies
  --no-browser --values values.yaml`, where `values.yaml` sets `global.airbyteUrl: http://127.0.0.1:3302`. About 4 minutes
  on the 8 vCPU / 30 GiB VM (image pulls included).
- Binding: abctl has no bind-address option, so kind published `0.0.0.0:3302 -> 80` on the node container. For the whole
  session an iptables rule `DOCKER-USER -i ens5 -p tcp -m conntrack --ctorigdstport 3302 -j DROP` dropped that port on the
  external interface (removed at teardown), and the security group allows only 22; in practice only loopback reached it.
  The generated card's generic line "bound to loopback" is therefore true in effect but not in the literal port mapping.
- Tooling on the VM: rea 6.6.0, playwright-core 1.58.2, Chromium 155.0.8059.79 (snap), node v24.22.0, python 3.12.3,
  Docker 29.9.1, compose v5.6.0, agent-env 0.9.1334, Ubuntu 24.04.5.

## Pipeline (all under ~/capture/airbyte on the VM)
1. `./install.sh` (above); `/api/v1/health` answered `{"available":true}`.
2. `python3 admin.py`: `abctl local credentials --email rea-admin@example.test --password <generated>`; abctl's output went to
   a private temp file that was parsed and removed, so the admin password and the default application's client id/secret
   live only in `.admin` (mode 600, deleted at teardown).
3. `python3 seed.py` (stdlib urllib, public API `/api/public/v1`, bearer token exchanged from the client credentials and
   kept in memory): completes the first-run setup (`/api/v1/instance_configuration/setup`: organization "Lighthouse Rota",
   anonymous data collection off), renames the default workspace to "Lighthouse Rota Pipelines", creates "Saltmarsh Depot
   Sandbox", 4 Sample Data sources, 3 End-to-End Testing (/dev/null) destinations, 3 tags, 3 connections (two tagged), and
   runs one sync of "Granite Ledger census to Quiet Drain" to completion (job 1, succeeded, 900 rows, 306,967 bytes).
   Idempotent; it also deletes any `Rea scratch*` source or tag left by an interrupted capture. Writes `seed-ids.json`.
4. `node capture.mjs`: UI sign-in at `/login` (fields `username`, `password`), then the connections list, one connection's
   status and timeline pages, sources, one source, destinations and settings; then 64 scripted public-API calls from the
   page: organizations, workspaces (list, both by id, includeDeleted), permissions, sources (list, by workspace, two pages,
   all four by id), destinations (list, both workspaces, all three by id), connections (list, by workspace,
   includeDeleted, all three by id), streams for two source/destination pairs, tags (list, by workspace, all three by id),
   jobs (list, by connection, by type+status, by workspace, job 1), the two connector definitions and the destination
   definitions list; then a scratch source POST, PATCH, GET, list, DELETE (204), GET; a scratch tag POST, PATCH, GET,
   DELETE (204), list; `POST /jobs` (manual sync of the Saltmarsh Depot relay) and its job read; re-reads.
   The bearer token for those calls is exchanged in Node (not recorded); every request to another origin (analytics,
   fonts) is aborted in the browser. Full HAR 82.0 MB, 2,856 entries (deleted after scoping).
   Quirk: the server's CORS filter answers 403 with an empty body to PATCH and DELETE that carry a browser `Origin`
   header (GET and POST pass), so `capture.mjs` sends those two methods through `context.request` (same browser context,
   recorded in the same HAR, no Origin header). The first capture attempt recorded the 403s; it was discarded, `seed.py`
   removed its leftovers, and the capture was re-run.
5. `python3 -I scope_har.py airbyte.full.har airbyte.scoped.har --origin http://127.0.0.1:3302 --keep-regex '^/api/public/v1/'`
   -> kept 64 (GET 57, POST 3, PATCH 2, DELETE 2; statuses 200 x62, 204 x2); dropped other-origin 57 (aborted analytics and
   fonts), path 2,679 (the UI's own `/api/v1` RPC traffic and static assets), auth 56, non-json 0, big-body 0, over-max 0.
   Scoped HAR sha256 `1d67ea816437d694c369791740572fbab7d10aa6826ee568c5f98c7608e32016`, 124,694 bytes. The envbuild gate
   found no admin password or client secret literal, no token shapes, no credential-named body fields, no forbidden word.
6. `python3 ~/showcase/envbuild.py all airbyte` (manifest, bundle, smoke, eval, card): all ok.
7. Teardown: `abctl local uninstall --persisted` (the cluster went; root-owned pgdata under `~/.airbyte/abctl/data` needed
   `sudo rm -rf`, then `~/.airbyte` was removed), the leftover empty `kind` docker network removed, the iptables rule
   deleted; `airbyte.full.har` and `.admin` deleted.

## Manifest facts
- Capture Evidence `ev_8e00dfaee9452108d545ea793346d937d5407358ab2ea30d6d614fcfac225307` (64 records). With the opt-in
  rules: `ev_99db62d7bd04e3b25915a76aca88c17ebc8db08578ae869454ebe6babb9cbc5f`, 25 tools (GET 18, POST 3, PATCH 2,
  DELETE 2), 13 templated groups, params uuid 14 and numeric 1 (the built-in format rules did all the templating; the
  opt-in rules matched nothing), 9 distinct query names (connectionId, destinationId, includeDeleted, jobType, limit,
  offset, sourceId, status, workspaceIds), statuses 200/204, 0 excluded, coverage complete-within-view 25/25, unknowns
  authorization-model, response-semantics, state-transition; 9 limitations. Without rules:
  `ev_3c5133ad68cdd567d8e87593cb13a78fb8296f8a8cbe623eac1cb160926a23c3`, the same 25 tools.
- Write tools: `post_public_sources`, `patch_public_sources_by_uuid`, `delete_public_sources_by_uuid`, `post_public_tags`,
  `patch_public_tags_by_uuid`, `delete_public_tags_by_uuid`, `post_public_jobs`.
- After DELETE, `GET /sources/{id}` still answers 200 with the soft-deleted record (Airbyte tombstones sources).
- `exclude_tools` = `definitions|permissions` keeps connector-catalogue names (shipped by Airbyte) and permission rows out
  of the retrieval tasks.

## Results
- 11 retrieval tasks (names of seeded connections, workspaces, destinations, tags, sources and the organization).
- Smoke passed (25 tools listed, replay 200 = recorded 200).
- Eval: `openai/gpt-oss-120b:groq` 11/11, `zai-org/GLM-5.3-Flash:zai-org` 11/11; 22 episodes; dry publish wrote
  `~/showcase/datasets/airbyte` (6.5 MB, 12 tasks, 23 runs).

## Seeded facts usable for retrieval questions
Workspaces "Lighthouse Rota Pipelines" and "Saltmarsh Depot Sandbox"; organization "Lighthouse Rota". Sources (Sample Data):
"Blue Heron Kitchen Orders" (count 250, seed 11), "Granite Ledger Stone Census" (400, 29), "Copperfield Annex Visitor Log"
(120, 5), "Saltmarsh Depot Tide Readings" (60, 3, second workspace). Destinations (/dev/null, SILENT): "Copperfield Annex
Null Sink", "Lighthouse Rota Quiet Drain", "Saltmarsh Depot Dev Null". Connections: "Blue Heron Kitchen nightly orders
feed" (cron `0 30 2 * * ?`, tag Kitchen Night Shift), "Granite Ledger census to Quiet Drain" (manual, tag Quarry Audit,
job 1 succeeded with 900 rows in PT1M16S), "Saltmarsh Depot tide readings relay" (manual). Tags: Quarry Audit #4F7A5B,
Kitchen Night Shift #C2733C, Tide Table Crew #2E6F9E.
