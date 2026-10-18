# Mealie 3.28 capture notes (rea showcase, batch 2)

- App: `ghcr.io/mealie-recipes/mealie:v3.28.0`, digest
  `ghcr.io/mealie-recipes/mealie@sha256:8b02290f4d1806f02acac6f25f6d48a3c965612fda1f8e914d5af533276f8688`, version `v3.28.0`
  from `GET /api/app/about`. v3.29.0 had been out for one day on 2026-10-18; the month-old v3.28.0 was pinned instead.
  Licence AGPL-3.0 (LICENSE at the v3.28.0 tag). sqlite in the `mealie-data` volume, compose project `rea-mealie`,
  loopback-only port `127.0.0.1:3212 -> 9000`, `BASE_URL=http://127.0.0.1:3212`, sign-up off, no AI key. The healthcheck uses
  the image's python against `/api/app/about`; healthy after 14 s.
- Tooling on the VM: rea 6.6.0, playwright-core 1.58.2, Chromium (snap) headless with `--no-sandbox`, node v24.22.0,
  python 3.12.3, Docker 29.9.1, compose v5.6.0.

## Admin credentials
Mealie starts with its documented first-run admin `changeme@example.com` / `MyPassword`. `up.sh` generates the real admin
password and a crew password into `.admin` (mode 600); the first thing `seed.py` does is `PUT /api/users/password` from the
default to the generated value (the change revokes the old token, so it logs in again), then renames the account to
rea-admin (Rea Admin, rea-admin@example.test). The login chain handles every intermediate state (default, password changed
but not renamed, done). The scoped HAR has no hit for the default email, the default password, the `.admin` values or the
cookie name.

## Pipeline (all under ~/capture/mealie on the VM)
1. `./up.sh` (writes `.admin` once, `docker compose -p rea-mealie -f compose.yml up -d`, waits for healthy).
2. `python3 seed.py` (stdlib urllib, bearer tokens from `POST /api/auth/token`): admin as above; group renamed to
   "Lighthouse Rota" and household to "Blue Heron Kitchen" (admin endpoints); crew account mina-okafor; 3 categories,
   4 tags, 2 tools, 3 foods with descriptions, 2 units; 5 recipes written from JSON: `POST /api/recipes {"name"}` answers the
   slug, then the full recipe is read and `PUT` back with description, yield, servings, prep/cook/total time, ingredient
   notes, instruction steps, a note, categories, tags and tools (no URL scraping, no images); 2 cookbooks whose
   `queryFilterString` selects a category; 2 shopping lists with 4 items (one linked to a food and the crate unit); 3 meal-plan
   entries (two recipes, one side note); Mina comments on two recipes. Idempotent (list-and-match before every create; a
   rerun creates nothing; leftover `rea-scratch*` recipes are deleted). Writes `seed-ids.json`.
   `GET /api/organizers/tags/slug/<missing>` answers 500 instead of 404 in this version, so organizer lookups list and match.
3. `NODE_PATH=~/capture/node_modules node capture.mjs`: browser context with service workers blocked; UI login at `/login`
   (`#username`, `#password`, Enter), landing on `/g/lighthouse-rota`. The UI keeps its JWT in the non-httpOnly cookie
   `mealie.access_token` and sends it as a bearer header; the scripted calls read the cookie and do the same. 37 scripted
   reads first: about, users/self, groups/self, households/self, recipe list, 5 recipes by slug, a recipe's comments, one
   comment by id, a text search (`search=kelp`), a category filter, category list, 2 categories by id, one by slug, tag list,
   one tag, one tool, 2 foods, one unit, cookbook list, 2 cookbooks, shopping-list list, 2 lists, one item, meal plans for
   2026-11-14..16 and 3 entries by id. Then 8 UI pages (home, a recipe, a cookbook, categories, tags, meal planner, shopping
   lists, one list). Then the write path: `POST /api/recipes` (201, answers the slug as a JSON string), `PATCH` (200),
   re-read, `DELETE` (200, answers the deleted recipe), re-read (404), list re-read. Full HAR 2,174 entries (27 MB), deleted
   after scoping.
4. `python3 -I ~/capture/scope_har.py mealie.full.har mealie.scoped.har --origin http://127.0.0.1:3212 --keep-regex '^/api/'`
   -> kept 139 (GET 136, POST 1, PATCH 1, DELETE 1; statuses 200 x137, 201, 404); dropped path 2,022, non-json 9 (the
   profile image, image/webp), auth 4 (the token request and `/login` page loads), big-body 0, over-max 0. 139 is just under
   the 140 ceiling: every UI page load refetches the group, household, cookbooks, organizers, foods and units. Credential
   grep clean. sha256 `069d5a884bd4ab155e0e7b8c751891e08718d18a50b006f2a9a25f4d2f2350d6`, 288,867 bytes.
5. `python3 ~/showcase/envbuild.py all mealie` (steps one at a time): capture evidence
   `ev_b23b02ad2cf3e1cf793dae77441e7867b7043564dbe0ed4d18d89776611239be` (139 records, observed), manifest
   `ev_6976682a576ab89896833d0e89eb2f1fa4d48b9e3cef4c8449ee4f4a87979d5c` (inferred), no-rules manifest
   `ev_7adf8020f1e1ec7f1876aa037463173f4bbe9cfbee6da9c890bda79b7bcebb77`; bundle 12 retrieval tasks from 23 candidates;
   smoke passed (replay 1, 26.5 s); eval `openai/gpt-oss-120b:groq` 12/12 and `zai-org/GLM-5.3-Flash:zai-org` 12/12, one
   tool call per episode on average, mean input tokens 11.2k and 14.4k; card and dry publish: 13 tasks, 25 runs,
   `~/showcase/datasets/mealie` (6.9 MB), scans clean.
6. `./down.sh` (`docker compose -p rea-mealie -f compose.yml down -v`, then `mealie.full.har`, `.admin`, `req.*.json` removed).

## Manifest facts
- With rules: 39 tools (GET 36, POST 1, PATCH 1, DELETE 1), 12 templated groups; params uuid 10, numeric 1 (meal-plan ids
  are integers), sibling-variance 1: the five recipe slugs (plus the scratch recipe's reads) fold into one
  `get_recipes_by_recipe_id` tool. Without the opt-in rules: 44 tools, each recipe slug its own literal tool. The scratch
  recipe's PATCH and DELETE stay literal (`patch_recipes_rea_scratch_recipe`, `delete_recipes_rea_scratch_recipe`), since
  only one slug was written. `get_households_cookbooks_spring_tide_menu` and
  `get_organizers_categories_slug_quarry_lunches` are literal slug tools too.
- 60 query-parameter names across tools; statuses 200, 201, 404; 2 tools with a body shape (POST, PATCH); 0 excluded groups;
  coverage complete-within-view (39/39); 9 limitations; unknowns authorization-model, response-semantics, state-transition.
- UI-only tools: app about/theme/startup-info, users/self/ratings, groups/members, groups/households (+ by id), groups/labels,
  households/self/recipes/<slug>, mealplans/rules, and the list reads with `perPage=-1`. `exclude_tools` keeps the
  about/startup/theme, ratings, members, households and `*_self` reads out of the tasks.

## Tasks and episodes
12 tasks: the Quarry Packs cookbook description, the foraged tag, the kelp-delivery meal-plan note, the crate unit, the oat
bars' category, the Night-Shift Snacks category slug, a shopping item note, a comment's author, the kelp smoker tool slug,
the samphire food, the first item's food description on the Saltmarsh Depot list, and the first recipe of the UI's recipe
list (whose recorded request carries the UI's twelve query parameters). Four of the recorded unfiltered list reads start with
Copperfield Ginger Tea (newest first and name order agree); the cookbook page's read (`cookbook=spring-tide-menu`) starts
with Lamp-Watch Barley Stew and the search and category reads differ too, so the agent has to pass enough of the query for
the replay to pick an unfiltered record. Both models passed all 12 in one tool call each.

## Seeded facts usable for retrieval questions
Recipes: Smoked Kelp Broth ("Blue Heron Kitchen's spring-tide starter, ladled from one cast-iron kettle."; 36 bowls; 20 min
prep, 1 h 30 min cook; note "Serve to the Lighthouse Rota night shift at 22:00."), Granite Ledger Oat Bars ("Dense oat bars
packed for the north quarry count."; 24 bars), Lamp-Watch Barley Stew ("Kept warm on the gallery stove from 22:00 to
06:00."; 12 bowls), Saltmarsh Samphire Hash ("Samphire and potato hash from the Saltmarsh Depot garden."; 6 plates; "add no
salt"), Copperfield Ginger Tea ("Ginger and honey tea brewed for the Copperfield Annex painters."; 1 flask). Foods: dried kelp
"Bladderwrack dried on the Saltmarsh Depot racks.", pearl barley, samphire. Units crate ("A Saltmarsh Depot supply crate."),
ladle. Cookbooks Spring Tide Menu, Quarry Packs. Lists: Saltmarsh Depot order (twelve crates of dried kelp, four sacks of
pearl barley), Granite Ledger pantry (rolled oats, two jars of heather honey). Meal plan 2026-11-16 side "Kelp delivery day":
"Twelve crates arrive from the Saltmarsh Depot before noon." Mina's comments: "Halve the pepper when the day shift eats it.",
"These held together through the whole tidal-yard count."

## Rebuild, 2026-10-18

After review, the shared task generator was tightened: an answer must be a distinctive value that occurs in this app's seed and capture inputs, never the admin account's own identity, in at most 12 recorded responses, and unique across the tasks; each tool gets at most two tasks. Bundle, smoke, eval and card were re-run from the same capture. The bundle and eval numbers earlier in this file describe the first build; these are the published ones.

- bundle: 12 retrieval tasks from 19 recorded reads with an eligible field (up to two tasks per tool); field values rejected: in too many responses 19, not distinctive 13, not in the seed inputs 2, in the tool name or arguments 7.
- smoke: passed.
- eval `openai/gpt-oss-120b:groq`: 12/12.
- eval `zai-org/GLM-5.3-Flash:zai-org`: 12/12.
- card and dry publish: 24 episodes, dataset 6.9 MB.
