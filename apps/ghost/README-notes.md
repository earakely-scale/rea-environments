# Ghost 5 capture notes (rea showcase)

- App: `ghost:5-alpine`, digest `ghost@sha256:a0506f3f05f5bdc6c950c5113cdcdb1e1f96fbf15f6dc0a39fc093c25348bdb5`,
  version `5.130` from `GET /ghost/api/admin/site/` (installed build `5.130.6`), sqlite3 at
  `/var/lib/ghost/content/data/ghost.db`, `url=http://127.0.0.1:3105`, compose project `rea-ghost`, loopback-only port
  `127.0.0.1:3105 -> 2368`. `NODE_ENV` left at the image default (production); Ghost started cleanly with sqlite3.
  `security__staffDeviceVerification=false` so sign-in does not wait for an emailed device code.
- Tooling on the VM: rea 6.6.0, playwright-core 1.58.2, Chromium 155.0.8059.79 (snap, launched with
  `chromium.launch({ executablePath: '/snap/bin/chromium', args: ['--no-sandbox', ...] })`; the default temp profile worked, the
  `USER_DATA_DIR` persistent-context fallback in capture.mjs was not needed), node v24.22.0, python 3.12.3.

## Pipeline (all under ~/capture/ghost on the VM)
1. `docker compose -p rea-ghost -f compose.yml up -d` (healthcheck on `/ghost/api/admin/site/`, healthy after 8 s).
2. `python3 seed.py`: owner through `POST /ghost/api/admin/authentication/setup` (name "Rea Admin", rea-admin@example.test,
   blog "Lighthouse Rota", password generated at run time into `.admin`, mode 600), a session cookie for the seed only
   (destroyed at the end), then idempotent creation of 2 tags, 2 published posts (html source, tagged), 1 draft, 1 page,
   1 member "Ada Finch" (label "Rota Crew"), owner bio/location update; newsletter left at default. Every request sends
   `Origin: http://127.0.0.1:3105` because Ghost's session CSRF check compares Origin/Referer on every call.
   It also deletes any `rea-scratch-post*` left by an interrupted capture. Writes `seed-ids.json` (ids/slugs only).
3. `NODE_PATH=~/capture/node_modules node ghost/capture.mjs`: UI login at `/ghost/#/signin`, visits posts, the editor of the
   first published post, pages, tags, members, settings; then the scripted fetch sequence from inside the page (site,
   posts list with include, post by id, post by slug, pages, tags with count.posts, tag by id, members list, member by id,
   users with roles, settings, `filter=tag:granite-ledger`, `filter=status:draft`), then POST a scratch post, PUT it, GET it,
   DELETE it (204), GET it again (404), re-read the posts list. Full HAR 19.2 MB (deleted on the VM after scoping).
4. `python3 -I scope_har.py ghost.full.har ghost.scoped.har --origin http://127.0.0.1:3105 --keep-regex '^/ghost/api/'`
   -> kept 76 (GET 72, POST 3, PUT 1); dropped other-origin 35, path 27, non-json 1, auth 1, big-body 0, over-max 0.
   Credential grep on the scoped HAR: admin password literal 0 hits, `hf_|ghp_|Bearer ` 0 hits, session cookie name 0 hits.
   sha256 `cf7eb90b391c2b83b4863f7c61be70b78f7aaa398bc182b15acafaa423a497ad`, 356,170 bytes.
5. `rea inspect-web-network-capture /home/ubuntu/capture/ghost/ghost.scoped.har har --format json > ghost.capture.json`
   (evidence `ev_f2f21b681f5ab8a313f4bff3cd2d36d1b5e864451d881cc8052a76d4c892e69a`, 76 records, confidence observed), then
   `rea inspect-analysis-view req.json --format json` with template_rules [after-uid-literal, opaque-token, sibling-variance]
   -> `ghost.manifest.json` (evidence `ev_9f7b1b2e995efe7a7d513eb662d9f12d005183bbd5e464e6fa407b1e3a4aa320`, confidence
   inferred) and the same view without template_rules -> `ghost.manifest.norules.json` (evidence
   `ev_cbe80916a0b9871d6b92e80de3e064df23e7c5a6b2ad7e2f31b7dd8d41d48788`, confidence derived). No resource_constraint;
   coverage `complete-within-view`, 36/36 examined, exhausted.
6. `summary.json` generated from the manifests, the scoped HAR, the site API and the image metadata.
7. `docker compose -p rea-ghost -f compose.yml down -v`; `ghost.full.har`, `.admin`, `req*.json` removed on the VM.

## Manifest facts
- With rules: 36 tools (GET 33, POST 2, PUT 1), 4 templated groups, params by rule opaque-token 4 (members/{uid},
  posts/{uid} GET and PUT, tags/{uid}), after-uid-literal 0, sibling-variance 0; 54 query-parameter names across tools
  (11 distinct: allFilter, fields, filter, formats, group, include, limit, order, page, source, status); 3 tools with a
  body shape (POST posts, PUT posts/{uid}, POST stats/posts-member-counts); statuses 200/201/403/404; 0 excluded groups;
  unknowns: authorization-model, response-semantics, state-transition; 9 limitations.
- Without rules: 37 tools (GET 34, POST 2, PUT 1), 0 params, 0 templated groups; the two posts ids and the member/tag ids
  stay as literal tools. The rules collapse 37 -> 36 because the two `/posts/<id>/` GET literals merge into one `{uid}` tool.
- The literal `GET /ghost/api/admin/posts/slug/blue-heron-kitchen-tide-table-menu/` stays a literal tool in both variants
  (the slug follows a fixed `slug` segment, not a uid, so after-uid-literal does not apply; only one slug was recorded, so
  sibling-variance has nothing to merge).
- No DELETE tool: Ghost answers `DELETE /ghost/api/admin/posts/{id}/` with 204 and no content type, which scope_har.py
  drops as non-JSON. The POST (201) and PUT (200) of the scratch post are in the manifest.
- The 403 record is the admin UI probing `/ghost/api/admin/users/me/` before sign-in; the 404 is the re-read after delete.
- UI-generated tools present besides the scripted ones: config, users/me, newsletters, tiers, labels, roles, invites,
  integrations, offers, snippets, themes, themes/active, notifications, recommendations, incoming_recommendations,
  search-index/{posts,pages,tags,users}, stats/member_count, stats/referrers, stats/posts-member-counts (POST), the
  `authentication/setup` status probe.

## Seeded facts usable for retrieval questions
Granite Ledger post: 412 blocks north quarry, 97 tidal yard, audited by Rui Castellanos on the fourteenth, reference
GL-2291, featured. Blue Heron Kitchen post: 36 covers per sitting, head cook Marisol Okonkwo-Reyes, night shift 22:00.
Draft: shift three 22:00-06:00, Ada Finch keeps the tide tables for January, lamp oil 180 litres. Page "About the
Lighthouse Rota" (editor Rea Admin). Member Ada Finch, label "Rota Crew", note "Keeps the tide tables for the winter rota."
Owner bio "Keeper of the Lighthouse Rota since the spring census; counts granite by lamplight.", location "Granite Point".
Tag descriptions: "Stone counts and quarry audits for the rota." / "Menus that follow the tides."
