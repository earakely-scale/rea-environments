# Treasury Fiscal Data API capture notes (rea showcase)

- API: the U.S. Treasury Fiscal Data API, published by the Bureau of the Fiscal Service, base
  `https://api.fiscaldata.treasury.gov/services/api/fiscal_service/`. Endpoints are versioned per dataset (`v1/...` and
  `v2/...`); every response is `{data: [...], meta: {count, labels, dataTypes, dataFormats, total-count, total-pages},
  links: {self, first, prev, next, last}}`. Query parameters: `filter=field:op:value,...` (ops eq, in:(..), gte, lte),
  `fields=`, `sort=` (prefix `-` for descending), `page[size]`, `page[number]`.
- Licence: U.S. public domain (works of the U.S. Government). No key, no login, no account. The API answers CORS `*` and
  sets load-balancer cookies, which `scope_har.py` removes with every other header except content-type/accept.
- Fair access: Fiscal Data publishes no numeric rate limit; we followed the showcase rules: a declared User-Agent
  `rea-environments showcase (https://github.com/earakely-scale/rea-environments)` set on the Playwright context (the API
  accepted it), one request at a time, a 600 ms pause after every call (under 2 requests per second), and a hard stop at
  140 requests. Totals: 25 research requests (curl, one small request per endpoint, 1.2 s apart) plus 52 capture
  requests = 77 of the 150-request budget. Every capture query is narrowed with `filter`, often `fields`, and
  `page[size]=5`; the largest recorded body is 4,307 bytes.
- No image, no seed: the data is the live public API on the capture date (2026-10-19 UTC; latest record dates 2026-10-15
  for daily datasets, 2026-09-30 for monthly and quarterly ones). Records are about agencies, currencies, securities and
  states; no query names a private individual. The forbidden word does not occur in the scoped HAR (0 hits).
- Tooling on the VM: rea 6.6.0, playwright-core 1.58.2, Chromium 155.0.8059.79 (snap), node v24.22.0, python 3.12.3.

## Pipeline (all under ~/capture/treasury-fiscal-data on the VM)
1. `NODE_PATH=~/capture/node_modules node treasury-fiscal-data/capture.mjs`: opens
   `/v2/accounting/od/debt_outstanding?filter=record_date:gte:2022-09-30&page[size]=5` (a JSON document, so in-page fetch is
   same-origin), then 51 in-page GETs over 16 datasets: rates_of_exchange (three countries on one date, then 8 currencies by
   key), avg_interest_rates (4), gold_reserve (3 facilities), interest_expense (3), title_xii (one date, then the two states
   it returned), statement_net_cost (one year, then two agencies it returned), DTS operating_cash_balance (2 days) and
   deposits_withdrawals_operating_cash (5, four by agency category), auctions_query (one auction date, the first CUSIP it
   returned, 10-, 30- and 2-year terms since June), revenue rcm (2 days), MTS table 5 (first lines; three departments'
   totals), securities_sales (2), federal_maturity_rates, debt_to_penny (a week, two quarter-ends), debt_outstanding,
   Treasury Report on Receivables for two departments (with `fields`). 52 requests to the host; full HAR 361 KB, deleted
   on the VM after scoping.
2. `python3 -I scope_har.py treasury-fiscal-data.full.har treasury-fiscal-data.scoped.har --origin https://api.fiscaldata.treasury.gov --keep-regex '^/services/api/fiscal_service/'`
   -> kept 52 (GET 52, all 200); dropped other-origin 0, path 0, non-json 0, auth 0, big-body 0, over-max 0. sha256
   `3e41c0dfb7af43dcc87399c0976cc7bbc3ed6111e22f02e4f610cfee0f8b1413`, 211,445 bytes.
3. `python3 ~/showcase/envbuild.py all treasury-fiscal-data` (run as manifest, bundle, then smoke/eval/card).
4. `treasury-fiscal-data.full.har` removed.

## Manifest facts
- 16 tools, all GET, one per dataset path; no templated groups and no path parameters with or without the opt-in rules
  (dataset names are not identifier-like, and only one MTS table was recorded); 44 query-parameter names across tools
  (filter, fields, sort, page[size]). 0 excluded.
- Retrieval tasks: 12 from 16 candidates. Four ask for record values (a receivable type, a security, a currency, a DTS
  deposit category); eight ask for a `meta.labels` column label (for example `Debt Held by the Public`), because many
  datasets' first records carry only numbers and dates, and the label strings appear in at most the 2-10 responses of
  their own endpoint. Kept as generated (see tool_issues).
- Eval: GLM-5.3-Flash 12/12; gpt-oss-120b 8/12. Its four misses are all label questions (`meta.labels.state_nm`,
  `month_expense_amt`, `agency_nm`, `debt_outstanding_amt`), where it answered the first record's value instead of the
  column label (for example `California` for `State Name`).
