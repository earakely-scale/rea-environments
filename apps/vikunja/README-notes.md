# Vikunja 2.7 capture notes (rea showcase, batch 2)

- App: `vikunja/vikunja:2.7.0` (API and bundled web UI in one image; newest release on Docker Hub on 2026-10-18), digest
  `vikunja/vikunja@sha256:e2204a1c1c6a81e833c2b3a5442be182ca2335b54c2e7e37578cc3fe12a27cfc`, version `v2.7.0` from
  `GET /api/v2/info`. Licence AGPL-3.0-or-later (LICENSE at the v2.7.0 tag; the binary's help text says the same).
  sqlite, compose project `rea-vikunja`, loopback-only port `127.0.0.1:3211 -> 3456`, registration enabled, mailer off,
  `VIKUNJA_SERVICE_PUBLICURL=http://127.0.0.1:3211/`. Healthcheck is the binary's own `vikunja healthcheck`; healthy after 8 s.
- The image is a scratch image running as uid 1000 whose only uid-1000-writable directory is `/tmp`; a named volume mounted
  at a path the image lacks would be root-owned, so `vikunja-data` is mounted on `/tmp` (a fresh named volume inherits the
  image directory's ownership) and holds `vikunja.db` and `files/`.
- Register and login are rate-limited per IP (10 a minute by default); the seed's reruns hit 429, so
  `VIKUNJA_RATELIMIT_NOAUTHLIMIT=200` is set, and the seed tries to log in before it registers.
- Tooling on the VM: rea 6.6.0, playwright-core 1.58.2, Chromium (snap) headless with `--no-sandbox`, node v24.22.0,
  python 3.12.3, Docker 29.9.1, compose v5.6.0.

## The web UI talks to /api/v2
Vikunja 2.x serves two REST APIs. The legacy `/api/v1` keeps the old verbs (PUT creates, POST updates) and still works;
the 2.x web UI only calls the RESTful `/api/v2` (POST creates, PATCH/PUT update, DELETE answers 204), documented at
`/api/v2/openapi.json` (136 paths). The first capture used v1 for the scripted calls and was redone: the scoped HAR and
manifest are v2 only (`keep_regex ^/api/v2/`). The seed still uses v1, which is fine for seeding. v2 list endpoints wrap
results in `{"items": [...]}`, which is why list-task fields read `items[0].<field>`.

## Pipeline (all under ~/capture/vikunja on the VM)
1. `./up.sh`: generates the service secret, the rea-admin password and one password shared by the three crew accounts into
   `.admin` (mode 600) once, exports only the secret to `docker compose -p rea-vikunja -f compose.yml up -d`, waits for healthy.
2. `python3 seed.py` (stdlib urllib, /api/v1, bearer tokens from `/login`): registers rea-admin, ada-finch, rui-castellanos
   and mina-okafor (usernames may not contain dots, so they are hyphenated; emails are `first.last@example.test`) and sets
   their display names. Content is created by the account that would own it, so creator fields differ (the first draft
   created everything as rea-admin, and half of the generated questions answered "Rea Admin"): rea-admin creates 5
   projects (Lamp Room Upkeep is a child of Lighthouse Rota, Copperfield Annex Repaint is archived), 3 labels, the shares and
   the saved filter; Ada creates team Night Watch and Rui team Quarry Auditors (each adds rea-admin); rea-admin shares
   Lighthouse Rota and Granite Ledger with those teams (read/write) and Blue Heron Kitchen with mina-okafor; Ada, Rui and
   Mina create the tasks in their projects (rea-admin the Lamp Room one) and Rui and Mina comment; rea-admin applies labels,
   assignees (an assignee must already have project access, hence shares before tasks) and one `related` relation.
   Idempotent (log in first, look up by title/name before creating, delete leftover `Rea scratch*` tasks); a rerun creates
   nothing. Writes `seed-ids.json`. Registration answers 412 for invalid usernames, user settings need the full settings
   object (a partial body answers 412 `overdue_tasks_reminders_time: non zero value required`).
3. `NODE_PATH=~/capture/node_modules node capture.mjs`: browser context with `serviceWorkers: 'block'` (the PWA worker
   otherwise recorded every page fetch twice, once from the page and once from the worker); UI login at `/login`
   (`#username`, `#password`, Enter); the JWT is in `localStorage.token`. Then 40 scripted reads through `fetch('/api/v2/...')`
   with that bearer: info, user, project list, 5 projects, Lighthouse Rota views, Granite Ledger list-view tasks, Blue Heron
   Kitchen kanban buckets, project teams, project users, a task by project index, 7 tasks by id, comments of the tidal-yard
   count, one comment by id, task labels, task assignees, label list, 3 labels, team list, 2 teams, the saved filter, a text
   search (`tasks?s=kelp`), a filter query (`tasks?filter=priority >= 3`), `labels?s=quarry`, `users?s=okafor`. Then 8 UI pages
   (home, projects, a list view, a kanban view, a task, labels, teams, team edit), then the write path on a scratch task:
   `POST /projects/{id}/tasks` (201), `PATCH /tasks/{id}` (200), re-read, `DELETE` (204), re-read (404), list re-read.
   The task page visit also makes the UI mark the task read (`PUT /tasks/{id}/read`). Full HAR 775 entries, deleted after scoping.
4. `python3 -I ~/capture/scope_har.py vikunja.full.har vikunja.scoped.har --origin http://127.0.0.1:3211 --keep-regex '^/api/v2/'`
   -> kept 102 (GET 98, POST 1, PATCH 1, PUT 1, DELETE 1; statuses 200 x99, 201, 204, 404); dropped path 621, non-json 23
   (avatar SVGs), auth 29 (login and the UI's token refresh on every page load), big-body 0, over-max 0. Credential grep:
   `.admin` value literals 0, `hf_|ghp_|Bearer ` shapes 0. sha256
   `10843162cbd00ebf87245969fcda682fa750ff07d0640cae18c1f9985883b314`, 378,047 bytes.
5. `python3 ~/showcase/envbuild.py all vikunja` (steps run one at a time while iterating): capture evidence
   `ev_6172766db5dacc12fa38511878e7a2db573f50122947cad181f09d52b850cceb` (102 records, observed), manifest
   `ev_19917e26dc88ca87887cb83f10d96d4f922051f312fa420ffdcd27d57f25b7e4` (inferred), no-rules manifest
   `ev_512a333bb058854675add5c92a5fb4299feb66a47526f5660a605e105aa31e4d`; bundle 12 retrieval tasks from 18 candidates;
   smoke passed (replay 1, 26.7 s); eval `openai/gpt-oss-120b:groq` 12/12 and `zai-org/GLM-5.3-Flash:zai-org`
   12/12, one tool call per episode on average, mean input tokens 8.1k and 10.7k; card and dry publish: 13 tasks, 25 runs,
   `~/showcase/datasets/vikunja` (6.9 MB), scans clean.
6. `./down.sh` (`docker compose -p rea-vikunja -f compose.yml down -v` with a placeholder for the compose file's required
   secret variable, then `vikunja.full.har`, `.admin`, `req.*.json` removed).

## Manifest facts
- 28 tools (GET 24, POST 1, PATCH 1, PUT 1, DELETE 1) with or without the opt-in rules: every id is an integer, which rea's
  built-in `numeric` rule templates in both views (19 templated groups, 25 numeric params; two-id routes get `id` and
  `id_2`). Tool names drop the `/api/v2` prefix (`get_tasks_by_id`, `get_projects_views_tasks_by_id_id_2`).
- Write tools: `post_projects_tasks_by_id` and `patch_tasks_by_id` (with body shapes), `delete_tasks_by_id` (204, kept by
  both scope_har.py and rea), and the UI's `put_tasks_read_by_id`. 0 excluded groups.
- 39 query-parameter names across tools; statuses 200, 201, 204, 404; coverage complete-within-view (28/28); 9 limitations;
  unknowns authorization-model, response-semantics, state-transition.
- UI-only tools: notifications, the kanban `views/{id}/buckets/tasks` read (with the UI's filter parameters), and the read
  marker. `exclude_tools` keeps info, user, notifications, the default view list (`get_projects_views_by_id`, whose first
  entry is always the default "List" view) and the default kanban buckets (created by the project owner) out of the tasks.

## Tasks and episodes
12 tasks: Mina's comment author, the kelp-order label's creator, the first task of Granite Ledger's list view, Blue Heron
Kitchen's shared user, Lighthouse Rota's team description, the tidal-yard task's creator, the tidal-yard comment author,
the related task's description through `tasks/by-index`, the kelp task's first label creator, the first card of the Blue
Heron Kitchen kanban, the saved filter's description and team 2's name. Both models passed all 12 in one tool call each, including the kanban question whose recorded
request carries the UI's seven filter parameters; that tool retains a single record (69), so the replay answers with it
whichever query values the agent sends.

## Seeded facts usable for retrieval questions
Projects: Lighthouse Rota "Night-watch planning for the lamp gallery and the tide tables."; Granite Ledger "Quarterly stone
counts for the north quarry and the tidal yard."; Blue Heron Kitchen "Menu planning that follows the spring tides, 36 covers
a sitting."; Lamp Room Upkeep "Wicks, lens cloths and brass polish for the Fresnel lens."; Copperfield Annex Repaint
(archived) "Repainting the lamp gallery railings; finished in the spring." Tasks: "Count the blocks in the tidal yard" (97
blocks expected after the October storm; ledger page 2291; priority 4; due 2026-11-14; Rui), "Draft the January night-shift
rota" (shift three 22:00 to 06:00; due 2027-01-05; Ada), "Log the lamp oil budget" (180 litres), "Order smoked kelp from the
Saltmarsh Depot" (twelve crates; Mina), "Print the tide-table menu cards" (thirty-six cards on heron-grey stock; 50 %),
"Retire cart number 7" (axle bent, load to cart 9; done), "Trim the wicks before dusk" (done). Labels tide-critical,
quarry-audit, kelp-order with descriptions. Teams Night Watch "Keepers of the lamp from 22:00 to 06:00." and Quarry Auditors
"Stone counters for the Granite Ledger." Saved filter "Tide-critical open work".

## Rebuild, 2026-10-18

After review, the shared task generator was tightened: an answer must be a distinctive value that occurs in this app's seed and capture inputs, never the admin account's own identity, in at most 12 recorded responses, and unique across the tasks; each tool gets at most two tasks. Bundle, smoke, eval and card were re-run from the same capture. The bundle and eval numbers earlier in this file describe the first build; these are the published ones.

- bundle: 12 retrieval tasks from 11 recorded reads with an eligible field (up to two tasks per tool); field values rejected: admin identity 24, in too many responses 46, not distinctive 3.
- smoke: passed.
- eval `openai/gpt-oss-120b:groq`: 12/12.
- eval `zai-org/GLM-5.3-Flash:zai-org`: 12/12.
- card and dry publish: 24 episodes, dataset 6.9 MB.
