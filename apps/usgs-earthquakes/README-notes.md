# USGS Earthquake Catalog capture notes (rea showcase)

- API: the U.S. Geological Survey's earthquake catalog at `https://earthquake.usgs.gov` (ComCat): the FDSN event web
  service (`/fdsnws/event/1/`, service version 2.8.1 from `/fdsnws/event/1/version`), event product content files under
  `/product/`, the geoserve region service and the GeoJSON summary feeds. No key, no login, no instance. Data is USGS-authored
  and in the U.S. public domain. GeoNames-derived `places.json` was left out on purpose so every record is USGS data.
- Fair access: the service documents a 20,000-event cap per query and no request rate; the showcase rules were applied:
  User-Agent `rea-environments showcase (https://github.com/earakely-scale/rea-environments)` on the Playwright context,
  one request at a time with 600 ms between calls, every URL appended to `requests.log` on the VM. Whole session: 118 HTTP
  requests (a 7-request pre-flight to size event documents and read the service docs, 3 debugging requests, a first
  capture that stopped after 4 calls, a full capture of 46 calls plus 5 redirect follow-ups, and the final capture of 53).
- Tooling on the VM: rea 6.6.0, playwright-core 1.58.2, Chromium 155.0.8059.79 (snap), node v24.22.0, python 3.12.3.

## Pipeline (all under ~/capture/usgs-earthquakes on the VM)
1. Pre-flight (stdlib urllib, same User-Agent): one February 2024 M5.3+ list and four document sizes, to pick events whose
   detail documents stay under 60 KB (M5.3-5.8 events with at most eight product types are 30-46 KB; events with
   ground-failure or finite-fault products grow past that).
2. `NODE_PATH=~/capture/node_modules node usgs-earthquakes/capture.mjs`: opens `/fdsnws/event/1/version` so in-page fetch is
   same-origin, then 52 in-page GETs: `application.json`; four counts; four event lists for fixed 2024 windows; four
   filtered lists (a Philippines bounding box, 300 km around Vallenar in Chile, PAGER alert level yellow, depth >= 300 km);
   eighteen single events by `eventid` (twelve fixed February ids, then the first six March M4.5-4.9 events from the list
   with at most four product types); PAGER `json/alerts.json` and `json/comments.json`, ShakeMap `download/info.json` and
   Did You Feel It? `dyfi_plot_numresp.json` for the first few of those events that carry each product (URLs taken from the
   event documents); three Flinn-Engdahl region lookups; five small summary feeds (significant_month, significant_week,
   4.5_day, all_hour, 1.0_hour). The first full capture also called the detail feed
   `/earthquakes/feed/v1.0/detail/<id>.geojson`; it answers 302 to `query?eventid=`, so it added no tool and was replaced.
   An earlier attempt with a Playwright route filter made the third in-page fetch fail ("Failed to fetch"); the filter was
   removed.
3. `python3 -I scope_har.py usgs-earthquakes.full.har usgs-earthquakes.scoped.har --origin https://earthquake.usgs.gov
   --keep-regex '^/(fdsnws/event/1/|earthquakes/feed/v1\.0/|product/|ws/geoserve/)'` -> kept 53 (all GET, all 200);
   dropped 0 of every kind. The largest body is 46 KB. Forbidden-word grep on the full HAR 0 hits; no email addresses, no
   token shapes. sha256 in summary.json.
4. `python3 ~/showcase/envbuild.py all usgs-earthquakes` steps (manifest, bundle, smoke, eval for both models, card + dry
   publish).
5. `usgs-earthquakes.full.har` deleted on the VM.

## Manifest facts
- With rules: 10 tools, all GET. REA's always-on numeric rule turns the API version segment into a parameter, so the FDSN
  tools are `/fdsnws/event/{numeric}/query`, `/count`, `/version`, `/application.json`; the product update times are numeric
  parameters too. sibling-variance folds the five summary feeds into `/earthquakes/feed/v1.0/summary/{summary_id}` and the
  event ids of each product file into one parameter (`{losspager_id}`, `{shakemap_id}`, `{dyfi_id}`), giving one tool per
  product file. 17 distinct query parameter names on the query tool, 8 on count, 3 on regions.
- Without rules: 23 tools (the five feeds and every per-event product path stay literal).
- All 26 query records (lists and single events) are one tool; replay picks the record whose query values match best, so
  `eventid=` reads replay the right event and list reads replay the right window.
- 7 retrieval tasks from 4 candidate tools (PAGER comments, the query tool, the summary feeds, DYFI counts); the ShakeMap
  info, PAGER alerts and region documents nest their strings deeper than the task generator reads, and counts are numbers.

## Recorded facts usable for retrieval questions
Feb 2024 events: us7000lwwh M5.4 158 km SW of Merizo Village, Guam; us7000lx12 M5.3 282 km E of Vao, New Caledonia; us7000lx33
and us7000lx2q M5.3/M5.4 Reykjanes Ridge; us7000ly7s M5.4 1 km NNW of Salvacion, Philippines; us7000ly6w M5.8 8 km W of
Esperanza, Philippines; us7000lyiz M5.3 64 km E of Union, Philippines; us7000lxgr M5.4 16 km SW of Claveria, Philippines;
us7000lyi6 M5.4 63 km NW of Vallenar, Chile; us7000lyjh M5.4 central Mid-Atlantic Ridge; us7000lz2v M5.7 South Sandwich
Islands region; us7000lz8a M5.6 Vanuatu region (all PAGER green except us7000lx12, no PAGER). March: Macquarie Island region
(two), South Sandwich Islands region, 54 km SSW of Muborak, Uzbekistan; 29 km NW of Yanglong, China; 104 km SSW of Pagar
Alam, Indonesia. Counts: 17 events M5.3+ on 1-15 Feb 2024, 484 M4.5+ in Feb 2024 (41 in the Philippines box), 13 M6.5+ in
the first half of 2024.
