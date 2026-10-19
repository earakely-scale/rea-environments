# openFDA capture notes (rea showcase)

- API: openFDA, `https://api.fda.gov`, published by the U.S. Food and Drug Administration. No key, no login. The data is
  U.S. public domain (U.S. government work; every response links `meta.license` https://open.fda.gov/license/ and
  `meta.terms`). openFDA has no API version string; app.json
  uses `v1`. Each endpoint reports its own `meta.last_updated` (2026-10-05 to 2026-10-16 in this capture).
- Why this app: it is the assigned alternate for the National Weather Service API. NWS was captured cleanly (62 records,
  manifest 57 tools) but the shared task generator only reads response bodies whose MIME type starts with
  `application/json`, and every NWS endpoint answers `application/geo+json` or `application/ld+json` (the OpenAPI spec
  lists no plain-JSON representation; `Accept: application/json` still returns geo/ld+json), so the bundle step produced 0
  retrieval tasks. See `../nws/README-notes.md`.
- Fair access followed: openFDA allows 240 requests per minute and 1,000 per day per IP without a key. The Playwright
  context declared `User-Agent: rea-environments showcase (https://github.com/earakely-scale/rea-environments)`; calls ran
  one at a time with a 600 ms pause (under 2 per second); every query used `limit=1..3` or a `count=` aggregation.
  The final capture made 53 requests; the whole session made 138 requests to api.fda.gov (11 curl probes for syntax,
  sizes and response headers, plus three discarded attempts: 1 request, 20 requests and 53 requests; reasons below).
- Tooling on the VM: rea 6.6.0, playwright-core 1.58.2, Chromium 155.0.8059.79 (snap), node v24.22.0, python 3.12.3,
  agent-env 0.9.1334, Ubuntu 24.04.5.

## Pipeline (all under ~/capture/openfda on the VM)
1. `node capture.mjs` opens `https://api.fda.gov/drug/ndc.json?search=brand_name:"Tylenol"&limit=2` (a small JSON search, so
   in-page fetch is same-origin), then 52 in-page GETs:
   - drug NDC directory: searches by labeler (Kenvue Brands LLC) and by generic name + dosage form (ibuprofen tablets),
     then four listings re-read by `product_ndc`;
   - drug enforcement (recalls): Class I ongoing and Class II 2026 searches, all five recalls re-read by `recall_number`,
     a `count=classification.exact` aggregation and a search by recalling firm;
   - drugs@FDA applications: sponsor PFIZER and brand LIPITOR searches, both applications re-read by `application_number`;
   - drug shortages: current shortages and a company search, three re-read by `package_ndc`;
   - NDC SPL data elements: proprietary name Advil, both packages re-read by `package_ndc`;
   - food enforcement: 2025-2026 recalls reported by firms in Colorado, Kansas, Nebraska and Iowa (two each, each re-read
     by `recall_number`) and a `count=state.exact` aggregation for 2026;
   - devices: stethoscope classifications (re-read by `product_code`), the latest software-design device recall (re-read
     by `product_res_number`) with a 2026 root-cause count, the two latest Class I device enforcement reports (re-read by
     `recall_number`);
   - three re-reads (a drug recall, an NDC listing, a device class) to show stable answers.
   Every response 200 and `application/json`; largest body 44,826 bytes. Full HAR 479,475 bytes (deleted after scoping).
2. `python3 -I scope_har.py openfda.full.har openfda.scoped.har --origin https://api.fda.gov --keep-regex '^/(drug|device|food|other)/[a-z0-9]+\.json$'`
   -> kept 53 (GET 53, all 200), dropped nothing. No forbidden word, no token shapes, no credential-named fields.
3. `python3 ~/showcase/envbuild.py all openfda` (manifest, bundle, smoke, eval, card).
4. Teardown: `openfda.full.har` deleted.

## Discarded attempts (why the session made more than 53 requests)
1. openFDA sends `Content-Security-Policy: default-src 'none'` on every response, which blocks in-page `fetch` even to the
   same origin ("Failed to fetch"). Fixed with `bypassCSP: true` on the Playwright context; requests and responses are
   unchanged.
2. One in-page fetch failed transiently ("Failed to fetch" on a request that curl then answered normally); `capture.mjs`
   now retries a dropped request once after 3 s (counted against the budget) and logs `requestfailed`. Not needed in the
   final run.
3. A complete capture was rejected by `rea inspect-web-network-capture`: HAR schema validation requires every request
   URL to be a strict URI, and the range queries carried raw `[` `]`. The final capture sends them as `%5B`/`%5D`.

## Manifest facts
- Capture Evidence `ev_831755436c6fab21a1196cc47650cc102eb756bc8286b8c8528cda928dcfaf90` (53 records). Manifest with the
  opt-in rules `ev_4acb8641e2a8042c00762d967a519ccba688eff4255b13a44cc01ce5c6efa924`: 9 tools, all GET, one per endpoint
  path (`get_drug_ndc`, `get_drug_enforcement`, `get_drug_drugsfda`, `get_drug_shortages`, `get_other_nsde`,
  `get_food_enforcement`, `get_device_classification`, `get_device_recall`, `get_device_enforcement`), no path parameters
  (openFDA keys records by `search=` query values, not by path), query names search, limit, count, sort; 0 excluded;
  coverage complete-within-view 9/9; confidence derived; unknowns authorization-model, response-semantics,
  state-transition; 8 limitations. Without rules: `ev_4a38afdce6788df7b8aa53c1b2146458f7575a476f2fdf149517c96e17423c02`,
  the same 9 tools.
- Because each tool is one path with many recorded queries, replay picks the recorded record whose `search` value best
  matches the arguments; a query the session never made falls back to the closest record.
- No write tools: the API is read-only.

## Recorded facts usable for retrieval questions
Kenvue Brands LLC labels TYLENOL 8 HR ARTHRITIS PAIN (NDC 50580-575); McKesson's Class I ongoing drug recall D-0353-2026
(6555 State Highway 161, Irving TX); Pfizer application NDA019617; Hospira (a Pfizer company) lidocaine shortage; Advil
SPL elements under NDA018989; stethoscope device classes (product code BZW, regulation 868.1910); Colorado, Kansas,
Nebraska and Iowa food recalls with their recall numbers and reasons; the latest Class I device enforcement reports
(Medline Industries, LP).
