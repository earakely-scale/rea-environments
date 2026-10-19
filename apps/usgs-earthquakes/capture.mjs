// Capture the public USGS Earthquake Catalog API with Chromium via playwright-core and record a HAR with bodies.
// No key, no login. Fair access: a declared User-Agent on the context, one request at a time, 600 ms between calls,
// every URL appended to requests.log so the session total stays auditable (well under 150).
// Opens one URL on the API origin, then makes in-page same-origin fetch GETs: catalog metadata, counts, event lists for
// fixed past windows (values are stable), filtered queries, single events by id, small product content files linked from
// those events (PAGER, ShakeMap, Did You Feel It?), Flinn-Engdahl region lookups and a few small real-time summary feeds.
import { chromium } from 'playwright-core';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

const ORIGIN = 'https://earthquake.usgs.gov';
const UA = 'rea-environments showcase (https://github.com/earakely-scale/rea-environments)';
const DIR = process.env.CAPTURE_DIR || path.join(os.homedir(), 'capture', 'usgs-earthquakes');
const HAR = process.env.HAR_PATH || path.join(DIR, 'usgs-earthquakes.full.har');
const REQLOG = path.join(DIR, 'requests.log');
const EXE = process.env.CHROMIUM_PATH || '/snap/bin/chromium';
const MAX_CALLS = 60;
const log = (m) => console.error(`[capture] ${m}`);
let calls = 0;
const note = (u) => { calls += 1; fs.appendFileSync(REQLOG, `${new Date().toISOString()} capture ${u}\n`); if (calls > MAX_CALLS) throw new Error('request budget exceeded'); };

const browser = await chromium.launch({ executablePath: EXE, headless: true, args: ['--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu'] });
const context = await browser.newContext({ userAgent: UA, recordHar: { path: HAR, content: 'embed', mode: 'full' } });
const page = await context.newPage();
page.setDefaultTimeout(60000);
const pause = () => page.waitForTimeout(600);

const get = async (p) => {
  await pause(); note(ORIGIN + p);
  const res = await page.evaluate(async (p) => {
    const r = await fetch(p, { headers: { accept: 'application/json' } });
    return { status: r.status, type: r.headers.get('content-type'), text: await r.text() };
  }, p);
  log(`GET ${p} -> ${res.status} ${res.text.length}B`);
  try { return JSON.parse(res.text); } catch { return null; }
};

// --- open the API origin (the service version, a 5-byte text document), so in-page fetch is same-origin ---
note(`${ORIGIN}/fdsnws/event/1/version`);
await page.goto(`${ORIGIN}/fdsnws/event/1/version`, { waitUntil: 'load' });
log(`opened ${page.url()}`);

// --- service metadata ---
await get('/fdsnws/event/1/application.json');

// --- counts for fixed past windows ---
await get('/fdsnws/event/1/count?format=geojson&starttime=2024-02-01&endtime=2024-02-15&minmagnitude=5.3');
await get('/fdsnws/event/1/count?format=geojson&starttime=2024-02-01&endtime=2024-02-29&minmagnitude=4.5');
await get('/fdsnws/event/1/count?format=geojson&starttime=2024-01-01&endtime=2024-06-30&minmagnitude=6.5');
await get('/fdsnws/event/1/count?format=geojson&starttime=2024-02-01&endtime=2024-02-29&minmagnitude=4.5&minlatitude=4&maxlatitude=21&minlongitude=116&maxlongitude=127');

// --- event lists (collections) for fixed past windows ---
await get('/fdsnws/event/1/query?format=geojson&starttime=2024-02-01&endtime=2024-02-15&minmagnitude=5.3&orderby=time-asc&limit=20');
const small = await get('/fdsnws/event/1/query?format=geojson&starttime=2024-03-04&endtime=2024-03-06&minmagnitude=4.5&maxmagnitude=4.9&orderby=time-asc&limit=20');
await get('/fdsnws/event/1/query?format=geojson&starttime=2024-03-01&endtime=2024-03-31&minmagnitude=6&orderby=magnitude&limit=10');
await get('/fdsnws/event/1/query?format=geojson&starttime=2024-05-01&endtime=2024-05-08&minmagnitude=5.5&orderby=time-asc&limit=12');

// --- filtered queries ---
await get('/fdsnws/event/1/query?format=geojson&starttime=2024-02-01&endtime=2024-02-29&minmagnitude=4.5&minlatitude=4&maxlatitude=21&minlongitude=116&maxlongitude=127&orderby=magnitude&limit=12');
await get('/fdsnws/event/1/query?format=geojson&latitude=-28.6&longitude=-70.8&maxradiuskm=300&starttime=2024-01-01&endtime=2024-03-31&minmagnitude=4.8&limit=12');
await get('/fdsnws/event/1/query?format=geojson&starttime=2024-01-01&endtime=2024-06-30&alertlevel=yellow&limit=10');
await get('/fdsnws/event/1/query?format=geojson&starttime=2024-02-01&endtime=2024-02-29&minmagnitude=5&mindepth=300&orderby=magnitude&limit=10');

// --- single events by id (fixed list chosen from the February 2024 M5.3+ window, small detail documents) ---
const FEB = ['us7000lx12', 'us7000lx33', 'us7000ly7s', 'us7000lx2q', 'us7000lyjh', 'us7000lyiz', 'us7000lyi6', 'us7000lxgr',
  'us7000lz2v', 'us7000lz8a', 'us7000lwwh', 'us7000ly6w'];
// product content files (small JSON documents) linked from those events: PAGER alerts and comments, ShakeMap run info,
// Did You Feel It? response counts; the first few events that carry each product
const products = { 'losspager:json/alerts.json': 3, 'losspager:json/comments.json': 3, 'shakemap:download/info.json': 4, 'dyfi:dyfi_plot_numresp.json': 3 };
const picked = Object.fromEntries(Object.keys(products).map((k) => [k, []]));
for (const id of FEB) {
  const ev = await get(`/fdsnws/event/1/query?eventid=${id}&format=geojson`);
  for (const [k, n] of Object.entries(products)) {
    const [type, file] = k.split(':');
    const url = ev?.properties?.products?.[type]?.[0]?.contents?.[file]?.url;
    if (url && url.startsWith(ORIGIN) && picked[k].length < n) picked[k].push(url.slice(ORIGIN.length));
  }
}
// smaller M4.5-4.9 events from the March 2024 list (origin and phase data only), six by eventid
const smallIds = (small?.features || []).filter((f) => f.properties.types.split(',').filter(Boolean).length <= 4).map((f) => f.id);
for (const id of smallIds.slice(0, 6)) await get(`/fdsnws/event/1/query?eventid=${id}&format=geojson`);

// --- the product content files picked above ---
for (const list of Object.values(picked)) for (const p of list) await get(p);

// --- Flinn-Engdahl region names for three epicentres ---
await get('/ws/geoserve/regions.json?latitude=-22.53&longitude=171.36&type=fe');
await get('/ws/geoserve/regions.json?latitude=63.0&longitude=-23.5&type=fe');
await get('/ws/geoserve/regions.json?latitude=-28.3&longitude=-71.6&type=fe');

// --- small real-time summary feeds (snapshot of the capture day) ---
for (const f of ['significant_month', 'significant_week', '4.5_day', 'all_hour', '1.0_hour']) await get(`/earthquakes/feed/v1.0/summary/${f}.geojson`);

await page.waitForTimeout(500);
await context.close(); // flushes the HAR
await browser.close();
log(`HAR written to ${HAR}; ${calls} requests this run`);
console.log(HAR);
