# HashiCorp Vault 1.21.4 capture notes (rea showcase)

- App: `hashicorp/vault:1.21.4`, digest `hashicorp/vault@sha256:4e33b126a59c0c333b76fb4e894722462659a6bec7c48c9ee8cea56fccfd2569`
  (amd64), `Vault v1.21.4 (ffe7023c481dc1ea2d8550bbaca8d85f8e611e0b), built 2026-03-04T17:40:05Z`. Licence: Business Source
  License 1.1 (Licensor HashiCorp, Inc.; Licensed Work "Vault Version 1.15.0 or later"), read from
  `/usr/share/doc/vault/LICENSE.txt` inside the image. The 1.21 line was chosen as the newest 1.2x release; 2.x tags exist.
- Server mode (not dev mode): `vault.hcl` with `storage "file"` on a named volume, a plain-HTTP TCP listener inside the
  container, `ui = true`, `disable_mlock = true` (with `SKIP_SETCAP=true`, so the container needs no IPC_LOCK capability).
  Compose project `rea-vault`, loopback-only port `127.0.0.1:3303 -> 8200`, healthcheck on
  `sys/health?uninitcode=200&sealedcode=200` (healthy after about 6 s).
- Tooling on the VM: rea 6.6.0, playwright-core 1.58.2, Chromium 155.0.8059.79 (snap), node v24.22.0, python 3.12.3,
  Docker 29.9.1, Compose v5.6.0.

## Pipeline (all under ~/capture/vault on the VM)
1. `docker compose -p rea-vault -f compose.yml up -d`.
2. `python3 seed.py` (stdlib urllib, idempotent): `PUT /v1/sys/init` with one key share and threshold one; the unseal key and
   root token go straight into `.admin` (mode 600) with a generated password for the UI admin, then `PUT /v1/sys/unseal`.
   With the root token (seed only) it enables two KV v2 mounts (`rota-config`, `ledger-config`), two auth methods
   (`userpass`, `approle` with no roles), writes four ACL policies plus a `rea-admin` policy, the userpass user `rea-admin`,
   six KV entries with configuration-like keys (owner, region, rotation_days, tier, ...) and custom metadata on four of them,
   four identity entities with metadata (display_name, team, desk, `@example.test` email), one userpass entity alias each,
   and three internal groups with members and policies. It removes scratch objects left by an interrupted capture and
   writes `seed-ids.json` (ids, names and accessors only).
3. `NODE_PATH=~/capture/node_modules node vault/capture.mjs`: UI sign-in at `/ui/vault/auth?with=userpass` as `rea-admin`,
   then the dashboard, secrets engines, both KV lists, the shift-plan entry, ACL policies, one policy, auth methods,
   identity entities and groups. The scripted sequence runs in the page: the helper reads the UI's client token from browser
   storage and sends it as `X-Vault-Token`, so the token never reaches the script. Reads: sys/health, sys/mounts,
   sys/mounts/rota-config/tune, sys/auth, the ACL policy list and four policies, KV metadata lists, five rota-config entries,
   two KV metadata records, the ledger-config list, entry and metadata, `?version=1` of the shift plan, the entity list,
   four entities by id, one entity by name, the alias list and two aliases, the group list, three groups by id, one group by
   name, the userpass user list. Writes on scratch objects: a KV entry written twice (v1, v2), read, metadata deleted (204),
   re-read (404); an ACL policy put (204), read, deleted (204), re-read (404); an identity entity created (200), updated
   (204), read, deleted (204), re-read (404). Re-reads of the rota-config list and the entity list. Full HAR 139.8 MB
   (deleted on the VM after scoping).
4. `python3 -I scope_har.py vault.full.har vault.scoped.har --origin http://127.0.0.1:3303 --keep-regex
   '^/v1/(?!sys/(health|seal-status|capabilities-self|internal/ui/feature-flags)$)'` -> kept 85 (GET 77, POST 4, DELETE 3,
   PUT 1; statuses 200 x77, 204 x5, 404 x3); dropped path 196, auth 1 (the userpass login), other-origin 0, non-json 0,
   big-body 0, over-max 0. The negative lookahead leaves out the UI's background polling (sys/health 24, sys/seal-status 23,
   sys/capabilities-self 26 POSTs, feature-flags 11): with `^/v1/` alone the 150-record cap dropped the largest scripted reads
   (sys/mounts, sys/auth). The scripted `sys/health` read went with it. `token/*` paths never survive scoping (the default
   drop regex matches `token`), and 9 bodies had the mount option `token_type` scrubbed by the scope tool's key filter.
   Credential grep on the scoped HAR: `.admin` values 0 hits, `hvs.`/`hf_`/`ghp_`/`Bearer ` shapes 0 hits, `X-Vault-Token`
   0 hits. sha256 `02038b8412236a14ef63eaa9155a49ab89c2ad927d2c2d9fb2ab73b39430e6ea`, 176,735 bytes.
5. `python3 ~/showcase/envbuild.py all vault` (manifest, bundle, smoke, eval for both models, card + dry publish).
6. `docker compose -p rea-vault -f compose.yml down -v`; `vault.full.har`, `.admin`, `req.*.json` removed on the VM.

## Manifest facts
- With rules: 43 tools (GET 36, POST 3, DELETE 3, PUT 1), 6 templated groups: the built-in uuid rule templates
  `identity/entity/id/{uuid}` (GET, POST, DELETE), `identity/entity-alias/id/{uuid}` and `identity/group/id/{uuid}`;
  sibling-variance folds the rota-config metadata list root and the UI's `lighthouse-rota%2Fshift-plan` metadata read into
  `rota-config/metadata/{metadata_id}`. after-uid-literal and opaque-token matched nothing. Query parameter names: `list`,
  `version`. Without rules: 44 tools (the uuid templates stay; the two metadata literals stay apart).
- Vault answers LIST as `GET ...?list=true`, so every list is a GET tool with a `list` query parameter.
- Policy, KV path and group/entity names are literal path segments, so each read of a named object is its own literal tool
  (for example `get_sys_policies_acl_granite_ledger_ops`, `get_identity_entity_name_rui_castellanos`).
- UI-generated tools besides the scripted ones: `sys/internal/ui/mounts` (+ per mount), `sys/internal/ui/resultant-acl`,
  `sys/config/state/sanitized`, the UI's KV metadata read.
- Writes in the manifest: POST KV data (create and update are the same call in KV v2), DELETE KV metadata, PUT/DELETE ACL
  policy, POST identity/entity, POST/DELETE identity/entity/id/{uuid}. Vault's 204 replies are kept by the scope tool.

## Seeded facts usable for retrieval questions
Shift plan (rota-config/lighthouse-rota/shift-plan): owner Ada Finch, region Granite Point North, tier "night watch tier",
shift 22:00 to 06:00, 180 litres lamp oil, handover at the Tide Table Desk, review board Lighthouse Rota Council. Tide tables:
owner Tomas Vey, January tide almanac, chart LR-TIDE-0117. Blue Heron Kitchen menu cycle: owner Mina Okafor, Tidewater Quay,
"galley standard", 36 covers, head cook Marisol Okonkwo-Reyes, Blue Heron Tasting Panel. Saltmarsh Depot inventory: Tomas
Vey, Saltmarsh Flats East, "bulk storage tier", 12 covered bays, three electric forklifts, Saltmarsh Depot Yard Committee.
Copperfield Annex archive: Rui Castellanos, Copperfield Hill, "cold archive tier", shelf CA-ROW-0417. Granite Ledger quarry
audit: Rui Castellanos, North Quarry Terrace, reference GL-2291, 412 blocks north quarry, 97 blocks tidal yard, Granite
Ledger Audit Circle. Entities: Ada Finch (Tide Table Desk), Rui Castellanos (North Quarry Audit Desk), Mina Okafor (Galley
Planning Desk), Tomas Vey (Bulk Store Ledger Desk). Groups: granite-ledger-crew ("Quarry audits and stone counts", first
Monday at the north quarry), blue-heron-kitchen-staff ("Menus that follow the tides"), copperfield-annex-reviewers.
Mount descriptions: "Shift and station settings for the Lighthouse Rota", "Quarry audit settings kept by the Granite Ledger
crew"; auth descriptions: "Crew sign-in for the Lighthouse Rota console", "Machine sign-in reserved for the Saltmarsh Depot
scanners".
