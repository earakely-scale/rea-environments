# Art Institute of Chicago API capture notes (rea showcase, scenario capture)

Replaces The Met Collection API, this VM's first public-API assignment. The Met's API has four live data paths
(`/public/collection/v1/departments`, `/objects`, `/objects/{objectID}`, and `/public/collection/v1.1/search`; the v1 search
was retired on 2026-10-01 and answers 410 with a pointer to v1.1). A scenario with the department list, three v1.1
searches and 16 public-domain object reads (20 transactions) gave a manifest of 3 tools (with and without the opt-in rules:
the built-in numeric rule merges the object ids), below the runner's 8-tool minimum, and adding the two remaining paths
could reach at most 5.

- API: `https://api.artic.edu/api/v1`, no key, no login. Data CC0; the `description` fields of artists and exhibitions are
  CC BY 4.0 and were not requested. The API asks clients to stay under 60 requests per minute; this session made 26.
- Tooling: rea 6.7.0, Chromium 155.0.8059.79 (snap), Ubuntu 24.04 amd64. Captured 2026-10-19 UTC.

## Pipeline (all under ~/capture/artic-collection on the VM)
1. `python3 make_scenario.py` writes `scenario.json` (52 actions, 26 navigations).
2. `rea capture-browser-scenario scenario.json --format json > artic-collection.capture.json` (23.0 s, 26 transactions,
   all 200, 26 bodies captured, 0 dropped events, no omissions, all 53 steps completed).
3. `python3 ~/showcase/envbuild.py all artic-collection`.

## The scenario in prose
`start_url` is `/api/v1/departments?limit=20&fields=id,title,subtype,parent_id`. Then, each followed by a 600 ms pause:
`/artworks/search?q=amphora&limit=5&fields=...`, `/artworks/search?q=field armor&limit=5&fields=...`,
`/artworks?ids=27992,28560,16568,24645&fields=...`, `/artists/search?q=hokusai&limit=3&fields=...`,
`/exhibitions/search?q=monet&limit=4&fields=...`; ten artworks by id with a 21-field `fields=` list (A Sunday on La Grande
Jatte, The Bedroom, Paris Street; Rainy Day, The Assumption of the Virgin, Under the Wave off Kanagawa, Water Lilies, the
Driscoll dragonfly lamp, Field Armor for Man, a Belly-Amphora, Judith); artists 40610 (van Gogh), 40810 (Seurat), 31492
(Hokusai); galleries 240 and 243; artwork types 1 and 18; category terms PC-10 and PC-7; exhibition 9036 (Monet and
Chicago). Settle 1.5 s. Every body is 0.6-1.9 KB.

## Manifest facts
- With rules: 11 GET tools, 6 templated groups; params numeric 5 (artworks, artists, galleries, artwork-types,
  exhibitions by id) and sibling-variance 1 (category-terms/{category_term_id}, from PC-10 and PC-7); 16 query-parameter
  names; nothing excluded; unknowns authorization-model, response-semantics, state-transition; confidence inferred.
- Without the opt-in rules: 12 tools (the two category terms stay literal tools; the numeric rule still applies).
- Retrieval tasks: 12 from 10 candidate tools; with the updated record reader each task carries its recorded query
  arguments (for example the `fields=` list). Eval: gpt-oss-120b 11/12 (missed qa-06, the amphora search), GLM-5.3-Flash
  12/12. Smoke passed.

## Notes
- Visual facts come from the JSON: `color` (h, l, s, percentage, population of the dominant colour), `dimensions`,
  `medium_display`, `style_title`, `classification_title`, `place_of_origin`.
- No request in this session touched another host; images live on the IIIF server and were not fetched.
