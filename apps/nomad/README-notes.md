# HashiCorp Nomad 1.11.3 capture notes (rea showcase)

- App: `hashicorp/nomad:1.11.3`, digest `hashicorp/nomad@sha256:996069720c5dbb48c644bf5ac61f14593fb362408921b7d4c6086fb2cfc9f2c4`,
  version `1.11.3` (revision `173ab08a`, from `GET /v1/agent/self` and the image labels). Licence BUSL-1.1 (read from
  `/usr/share/doc/nomad/LICENSE.txt` in the image; the Additional Use Grant allows production use except a competitive hosted
  or embedded offering). Compose project `rea-nomad`, loopback-only port `127.0.0.1:3304 -> 4646`.
- Mode: `nomad agent -dev` (server and client in one process, in-memory state, ACLs off), region `saltmarsh`, datacenter
  `granite-point`, node name `copperfield-annex-01`. With ACLs off there is no sign-in, no admin account and no `.admin` file:
  the UI and the API are anonymous on loopback.
- Running a Nomad client inside Docker is unsupported upstream. To let the dev client run tasks the compose file uses
  `cgroup: host`, a read-write bind of `/sys/fs/cgroup` (the client creates its own `nomad.slice` cgroup) and
  `cap_add: SYS_ADMIN` with `apparmor:unconfined` (each task directory gets a tmpfs secrets mount). Without these the agent
  exits (`/sys/fs/cgroup/cgroup.subtree_control: read-only file system`) or every task fails (`task_dir: mount: operation not
  permitted`). Tasks use the `raw_exec` driver (enabled in dev mode) and only run `/bin/sleep` or a one-line `echo` inside the
  agent container. The `docker` driver is undetected (no socket), which is fine.
- Tooling on the VM: rea 6.6.0, playwright-core 1.58.2, Chromium 155.0.8059.79 (snap), node v24.22.0, python 3.12.3,
  Docker 29.9.1, compose v5.6.0.

## Pipeline (all under ~/capture/nomad on the VM)
1. `docker compose -p rea-nomad -f compose.yml up -d --wait` (healthcheck on `/v1/status/leader`).
2. `python3 seed.py` (stdlib urllib, anonymous): purges leftover `rea-scratch*` jobs, then upserts namespaces
   `lighthouse-rota` and `granite-ledger` (descriptions and meta), node pool `saltmarsh-depot` (no nodes), dynamic node
   metadata on the dev node, and registers 6 jobs: service `blue-heron-kitchen-orders` (groups `tide-table-counter` x2 and
   `kelp-smoker` with two tasks), service `lighthouse-rota-night-watch`, batch `granite-ledger-stone-count` (finishes),
   periodic batch `granite-ledger-seaward-remeasure` (cron `0 6 * * 1`), parameterized batch `copperfield-annex-ledger-sync`
   (one dispatched child, meta `ledger_ref=GL-2291`), and service `saltmarsh-depot-cold-store` on the empty node pool (stays
   pending with a blocked evaluation). After the first deployment settles it registers version 1 of the kitchen job (menu
   meta change), so the job has two versions and two deployments. Writes `seed-ids.json` (job, node, allocation, evaluation
   and deployment ids only).
3. `NODE_PATH=~/capture/node_modules node nomad/capture.mjs`: visits 11 UI pages (jobs list, kitchen job overview,
   versions, deployments, stone-count allocations, one allocation, clients, the dev client, topology, evaluations, servers),
   then opens `/v1/status/leader` (a JSON page, so no UI scripts run) and makes the scripted fetch sequence: regions,
   namespaces list and both namespaces, node pools list, the pool and its jobs, nodes list and the node, the jobs list, all
   6 jobs plus the dispatched child (its id carries an encoded slash), kitchen versions/allocations/deployments/summary,
   evaluations of two jobs, three allocations, the blocked evaluation, the deployments list and the kitchen v1 deployment,
   the evaluations list, `prefix=granite`, `filter=Status == "pending"`, `POST /v1/search/fuzzy` for `kelp`; then registers
   a scratch batch job, reads it, re-registers it (version 1), reads its versions, purges it (`DELETE ...?purge=true`, JSON
   reply) and re-reads it (404, text `job not found`), then re-reads the namespace's job list.
   `recordHar.urlFilter` keeps the UI's blocking watch queries (`index=N` long polls) out of the HAR. Full HAR 75.6 MB
   (deleted on the VM after scoping).
4. `python3 -I scope_har.py nomad.full.har nomad.scoped.har --origin http://127.0.0.1:3304 --keep-regex '^/v1/(?!agent/|acl/|vars?(/|$)|operator/)'`
   -> kept 131 (GET 115, POST 15, DELETE 1; 130 x 200, 1 x 404); dropped path 134 (UI assets and `/v1/agent/*`), auth 11
   (`/v1/acl/token/self` probes), big-body 2 (`/v1/node/<id>/allocations`, 88 KB), other-origin 0, non-json 0, over-max 0;
   48 bodies scrubbed. sha256 `61df40951c6ee1872176416df0d5b0a6c2f8eaea91230c7f01b16ea47343df83`, 615,790 bytes.
5. `python3 ~/showcase/envbuild.py all nomad` (manifest, bundle, smoke, eval for both models, card + dry publish).
6. `docker compose -p rea-nomad -f compose.yml down -v`; `nomad.full.har` removed; the empty `nomad.slice` cgroups the dev
   client left on the host removed.

## Manifest facts
- With rules: 39 tools (GET 34, POST 4, DELETE 1), 6 templated groups: `uuid` 5 (allocation, client allocation stats,
  deployment, evaluation, node) and `sibling-variance` 1 (`/v1/job/{job_id}`, 8 observed job ids including the scratch job
  and the slash-encoded dispatched child); 12 distinct query-parameter names (diffs, filter, namespace, next_token, node_id,
  per_page, prefix, purge, region, resources, reverse, task_states); statuses 200/404; 0 excluded; unknowns
  authorization-model, response-semantics, state-transition; coverage complete-within-view 39/39.
- Without rules: 46 tools, 0 templated groups (each job id, allocation id and node id stays a literal tool).
- Job sub-resources (`/v1/job/<id>/allocations`, `/evaluations`, `/versions`, ...) stay literal per job even with rules,
  because each was recorded for one job only; the write tools are `post_jobs` (register), `post_job_rea_scratch_tide_probe`
  (update), `delete_job_rea_scratch_tide_probe` (purge), plus the UI's `POST /v1/jobs/statuses` and `POST /v1/search/fuzzy`.
- rea names the `GET /v1/namespaces` tool plain `get` (the `namespaces` segment is dropped from the name, as for Kubernetes
  paths); `GET /v1/namespace/<name>` stays two literal tools (`get_namespace_lighthouse_rota`, `get_namespace_granite_ledger`).

## Seeded facts usable for retrieval questions
Namespace `lighthouse-rota`: "Night shifts, lamp oil and tide tables for the Lighthouse Rota", steward Ada Finch, shift
pattern "three shifts from 22:00 to 06:00". Namespace `granite-ledger`: "Quarry audits and stone counts for the Granite
Ledger", steward Rui Castellanos, ledger series "GL-2291 quarterly series". Node pool `saltmarsh-depot`: "Cold-store hosts at
the Saltmarsh Depot (no hosts enrolled yet)", steward Tomas Vey, loading bay "bay 4 beside the eel smokehouse". Node meta:
cabinet "Copperfield Annex cabinet 7", caretaker Mina Okafor. Kitchen job meta: steward Mina Okafor, menu "smoked kelp broth
with tide-table bread" (v0) then "neap tide menu with oat crackers" (v1), "36 covers per sitting"; group `tide-table-counter`
lead Marisol Okonkwo-Reyes, "second sitting at 21:30"; group `kelp-smoker` batch "kelp batch K-17 from the north cove".
Night watch: "lamp checked every forty minutes", "180 litres for the winter", keeper Tomas Vey, "second-order Fresnel lens".
Stone count: auditor Rui Castellanos, ledger_ref GL-2291, "412 blocks in the north quarry", yard "97 blocks in the tidal yard".
Seaward remeasure: "Monday dawn remeasure of the seaward stack", "seaward stack of 58 blocks". Cold store: "eel smokehouse
cold room at 3 degrees", "twelve shelves of smoked eel". Ledger sync: clerk Mina Okafor, archive "Copperfield Annex archive
shelf 3".

## Build results (`envbuild.py all nomad`, step by step)
- manifest: 39 tools (norules 46), 131 scoped records, capture `ev_09880f9a941052d3335d98097843a3ad3774778266aabd85fbe9093de61b6ad1`,
  manifest `ev_12982eae5eeb6c118ce31026d3377f17232a0b872b74ef36620d7c418752688d` (inferred, historical-reference), norules
  `ev_5300af8f30144a61e33ba661313b6f3267682d5abe3a80838ec0b091b73eca5c`; credential, forbidden-word and record-count gates passed.
- bundle: 12 retrieval tasks from 15 candidates (`exclude_tools` = `stats|status_leader|regions|search`).
- smoke: passed (replay listed 39 tools, expected 39).
- eval: `openai/gpt-oss-120b:groq` 12/12, `zai-org/GLM-5.3-Flash:zai-org` 12/12, one tool call per episode on average.
- card + dry publish: 24 episodes, dataset at `~/showcase/datasets/nomad` (7.3 MB), scans clean.
- Two answers are Nomad's own wording rather than seed text (`Node registered`, `job-register`); they pass the seed-word
  check because those words also occur in seed.py's log lines. The card template's "drove a login" line does not apply
  here (no sign-in with ACLs off).
