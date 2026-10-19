// Record a HAR of NOAA CO-OPS public API reads (metadata, data and derived-product APIs) with Chromium via playwright-core.
// Opens one JSON document on the API origin, then makes a scripted sequence of same-origin in-page fetch GETs, one at a
// time with a 600 ms pause between calls (well under 2 requests per second), with a declared User-Agent. No keys, no login.
import { chromium } from 'playwright-core';
import os from 'node:os';
import path from 'node:path';

const ORIGIN = 'https://api.tidesandcurrents.noaa.gov';
const DIR = process.env.CAPTURE_DIR || path.join(os.homedir(), 'capture', 'noaa-tides');
const HAR = process.env.HAR_PATH || path.join(DIR, 'noaa-tides.full.har');
const EXE = process.env.CHROMIUM_PATH || '/snap/bin/chromium';
const UA = 'rea-environments showcase (https://github.com/earakely-scale/rea-environments)';
const APP = 'rea-environments_showcase';
const log = (m) => console.error(`[capture] ${m}`);

const browser = await chromium.launch({ executablePath: EXE, headless: true, args: ['--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu'] });
const context = await browser.newContext({ userAgent: UA, recordHar: { path: HAR, content: 'embed', mode: 'full' } });
const page = await context.newPage();
page.setDefaultTimeout(45000);
const pause = (ms = 600) => page.waitForTimeout(ms);
let calls = 0;
const get = async (p, attempt = 1) => {
  calls += 1;
  const res = await page.evaluate(async (p) => {
    try {
      const r = await fetch(p, { headers: { accept: 'application/json' } });
      const text = await r.text();
      return { status: r.status, bytes: text.length, type: r.headers.get('content-type') };
    } catch (e) { return { error: String(e) }; }
  }, p);
  if (res.error) {
    log(`#${calls} GET ${p} -> network error (${res.error})`);
    await pause(2500);
    return attempt < 2 ? get(p, attempt + 1) : res; // one retry after a transient connection failure
  }
  log(`#${calls} GET ${p} -> ${res.status} ${res.bytes}B ${res.type}`);
  await pause();
  return res;
};

const MD = '/mdapi/prod/webapi';
const DATA = '/api/prod/datagetter';
const DP = '/dpapi/prod/webapi';
const dq = (q) => `${DATA}?${q}&application=${APP}&format=json`;

try {
// landing: one station document on the origin (so every later fetch is same-origin)
log('open landing document');
const landing = await page.goto(`${ORIGIN}${MD}/stations/9414290.json`, { waitUntil: 'domcontentloaded' });
calls += 1; log(`#${calls} landing -> ${landing.status()}`);
await pause(1200);

// a small collection: stations with air-gap (bridge clearance) sensors
await get(`${MD}/stations.json?type=airgap`);

// station records by id
for (const id of ['8724580', '9447130', '8771450', '8638610', '9410170', '8410140', '9455920', '8761724', '1617760']) {
  await get(`${MD}/stations/${id}.json`);
}
// station sub-resources by id
for (const id of ['8724580', '9447130', '8771450', '8410140', '1617760']) await get(`${MD}/stations/${id}/details.json`);
for (const id of ['9414290', '8724580', '9455920', '8638610', '9410170']) await get(`${MD}/stations/${id}/datums.json?units=english`);
for (const id of ['9414290', '8771450', '9447130']) await get(`${MD}/stations/${id}/harcon.json?units=metric`);
for (const id of ['9414290', '8638610', '8761724', '9410170']) await get(`${MD}/stations/${id}/sensors.json`);
for (const id of ['8638610', '8771450', '8724580', '9447130']) await get(`${MD}/stations/${id}/floodlevels.json?units=english`);
for (const id of ['9414290', '8771450']) await get(`${MD}/stations/${id}/notices.json`);
await get(`${MD}/stations/9447130/products.json`);
for (const id of ['8410140', '1617760']) await get(`${MD}/stations/${id}/benchmarks.json`);

// data API: filtered queries over short ranges
for (const id of ['9414290', '8724580', '9447130', '8771450', '1617760', '9455920']) {
  await get(dq(`product=predictions&station=${id}&begin_date=20261019&end_date=20261020&datum=MLLW&interval=hilo&units=english&time_zone=lst_ldt`));
}
for (const id of ['9414290', '8638610', '8452660']) {
  await get(dq(`product=water_level&station=${id}&begin_date=20261017&range=3&datum=MLLW&units=english&time_zone=gmt`));
}
for (const id of ['8724580', '9447130']) {
  await get(dq(`product=monthly_mean&station=${id}&begin_date=20240101&end_date=20241231&datum=MSL&units=metric&time_zone=gmt`));
}
await get(dq('product=high_low&station=8771450&begin_date=20260901&end_date=20260905&datum=MLLW&units=english&time_zone=gmt'));
await get(dq('product=wind&station=9414290&begin_date=20261017&range=2&units=english&time_zone=gmt'));
await get(dq('product=air_temperature&station=8724580&begin_date=20261017&range=2&units=english&time_zone=gmt'));
await get(dq('product=water_temperature&station=9447130&begin_date=20261017&range=2&units=english&time_zone=gmt'));
await get(dq('product=air_pressure&station=9447130&begin_date=20261017&range=2&units=metric&time_zone=gmt'));
await get(dq('product=datums&station=8410140&units=english'));

// derived-product API: sea level trends and annual high-tide flooding counts
for (const id of ['9414290', '8724580', '8638610']) await get(`${DP}/product/sealvltrends.json?station=${id}&affil=US`);
for (const id of ['8638610', '8771450']) await get(`${DP}/htf/htf_annual.json?station=${id}&year=2024`);

} finally {
  await context.close(); // flushes the HAR, also after an error
  await browser.close();
}
log(`requests issued: ${calls} (plus any browser favicon probe); HAR written to ${HAR}`);
console.log(HAR);
