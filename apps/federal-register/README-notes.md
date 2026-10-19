# Federal Register API capture notes (rea showcase)

- API: `https://www.federalregister.gov/api/v1` (version v1), published by the Office of the Federal Register. No key, no
  login, no instance, no seed. Records are U.S. public-domain works (agencies, rules, proposed rules, presidential
  documents). Captured on 2026-10-19 (UTC), so every answer is about that snapshot.
- Fair access followed: User-Agent `rea-environments showcase (https://github.com/earakely-scale/rea-environments)` on the
  Playwright context (and on the research curls), one request at a time, 600 ms pause between calls (under 2 per second),
  small bodies (`per_page=5`, `fields[]` on every document read; largest recorded body 13,449 bytes). Requests in the whole
  session: 69 of the 150 allowed (11 research curls, 6 in an aborted first capture run and one diagnosis run, 52 in the
  recorded capture). The publisher's HTML site redirects automated clients to a CAPTCHA page and points them to the
  developer API; the API itself accepted the declared User-Agent.
- Tooling on the VM: rea 6.6.0, playwright-core 1.58.2, Chromium 155.0.8059.79 (snap), node v24.22.0, python 3.12.3.

## Pipeline (all under ~/capture/federal-register on the VM)
1. Research with curl (11 requests): one agency record; three wide searches (`per_page=20`, all planned fields) over FAA
   final rules published in September 2026, Energy Department proposed rules in 2026 and executive orders signed in 2026;
   the full agency list once (695 KB, research only); one multi-number public-inspection read; one term search; one
   suggested-search list; one public-inspection list for a date (234 KB, research only). Every candidate was screened for
   the forbidden word: 2 of 473 agencies carry it in their descriptions and the FAA public-inspection list for 2026-10-16
   carried it in titles, so neither is in the capture; the CFR topic vocabulary also contains it, so no `topics` field or
   topic facet is requested.
2. `NODE_PATH=~/capture/node_modules node federal-register/capture.mjs`: navigates to
   `/api/v1/agencies/federal-aviation-administration.json` (so in-page `fetch` is same-origin), then 51 GETs: 6 more agency
   records (DOT, DOE, FERC, DHS, FEMA, EOP); 7 document searches (FAA final rules 2026-09-01..30 pages 1 and 2, Energy
   proposed rules 2026-01-01..09-30, executive orders signed 2026-01-01..03-31, term `distribution transformers` in 2026,
   docket `EERE-2026-BT-STD-0133`, RIN `1904-AF51`), all with fixed past date ranges and `order=oldest` so results are
   stable; 3 facet counts (`type`, `monthly`, `agency`); 23 documents by number with a fixed `fields[]` list (10 FAA final
   rules, 8 Energy/FERC/CBP proposed rules, executive orders 14374, 14378, 14381, 14387, 14391), one two-number read and
   one default-field read; 6 public-inspection records and one two-number public-inspection read; the suggested-search
   list for `business-and-industry` and two suggested searches (`pipeline-safety`, `air-travel`). Full HAR 411 KB (deleted
   on the VM after scoping).
   The first capture attempt was aborted after 4 calls with `TypeError: Failed to fetch`; Chromium reported
   `net::ERR_NETWORK_CHANGED` because the concurrent Nomad eval was creating and removing Docker networks on the same VM.
   The recorded capture ran with no Docker activity.
   During the run each response was also checked in-page for the forbidden word (0 hits, log only); that log-only check
   was removed from the copied capture.mjs so the script does not spell the word.
3. `python3 -I scope_har.py federal-register.full.har federal-register.scoped.har --origin https://www.federalregister.gov --keep-regex '^/api/v1/'`
   -> kept 52 (GET 52, all 200); dropped 0 in every class; 0 bodies scrubbed. sha256
   `92b61ba4a50cd9beeb3af0913704c5a80536a2198a62c86f5e99d2eb56d7f5bf`, 198,774 bytes. Forbidden-word grep: 0 hits.
4. `python3 ~/showcase/envbuild.py all federal-register` step by step (manifest, bundle, smoke, eval, card).

## Manifest facts
- With rules: 10 GET tools, 3 templated groups, all `sibling-variance`: `/api/v1/agencies/{agency_id}` (7 records),
  `/api/v1/documents/{document_id}` (25 records, includes the comma-joined two-number read) and
  `/api/v1/public-inspection-documents/{public_inspection_document_id}` (7 records). The `.json` suffix is part of the
  parameter value (`2026-18126.json`, `energy-department.json`). The three facets and the two suggested searches stay
  literal tools. 16 distinct query-parameter names (`conditions[...]` filters, `fields[]`, `order`, `page`, `per_page`);
  status 200 only; 0 excluded; unknowns authorization-model, response-semantics, state-transition; coverage
  complete-within-view 10/10. Capture `ev_e824e8d53e2ce40fe1173e27f7002aa1e3e7f80707e999d864745bac26d86575`, manifest
  `ev_23d1066c3bc138a90ac041fe3012494bc348237ced0daac373a9dc2845357f19` (inferred, historical-reference), norules
  `ev_48bd2582653a2e2e8d30501448986264e01c2c4eeccc9cbb9a8e722aa6af3803`.
- Without rules: 45 tools (every agency, document and public-inspection number is a literal tool).

## Build results
- bundle: 10 retrieval tasks from 8 candidate tools (rejected fields: common 7, in-call 7, shape 3).
- smoke: passed (replay listed 10 tools, expected 10).
- eval: `openai/gpt-oss-120b:groq` 9/10, `zai-org/GLM-5.3-Flash:zai-org` 9/10. Both missed only
  `qa-01-get_public_inspection_documents_by_publi`, and both answered it correctly: the public-inspection `title` field
  ends with a trailing space (`...Point Pleasant, WV `), `gen_tasks.py` kept the space in the needle, and the models'
  trimmed answer `Airspace Designations and Reporting Points: Point Pleasant, WV` does not contain it. The card attributes
  the miss to the models; it is a grading artefact.
- card + dry publish: 20 episodes, dataset at `~/showcase/datasets/federal-register` (6.6 MB), scans clean.
- Several generated answers are low-information (`January 2026`, `May 2026`, `business-and-industry`,
  `Executive Office of the President`); `qa-02` and `qa-08` list `fields[]=signing_date` as the only argument because
  `gen_tasks.py` keeps one value per repeated query name, although the recorded call carried 21 `fields[]` values.
