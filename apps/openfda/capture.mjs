// Record the public openFDA API (https://api.fda.gov) with Chromium via playwright-core. No key, no login.
// The context declares a descriptive User-Agent; every call is an in-page same-origin GET, one at a time with a 600 ms
// pause (under 2 per second, far below openFDA's 240 per minute without a key), and the session stops well before 150
// requests. Searches are about firms, products, recalls, device classes and regulations; every response is kept small
// with limit=1..3. Individual records are then re-read by their public keys (recall number, NDC, application number,
// product code) taken from the search results.
import { chromium } from 'playwright-core';
import os from 'node:os';
import path from 'node:path';

const ORIGIN = 'https://api.fda.gov';
const DIR = process.env.CAPTURE_DIR || path.join(os.homedir(), 'capture', 'openfda');
const HAR = process.env.HAR_PATH || path.join(DIR, 'openfda.full.har');
const EXE = process.env.CHROMIUM_PATH || '/snap/bin/chromium';
const UA = 'rea-environments showcase (https://github.com/earakely-scale/rea-environments)';
const MAX_REQUESTS = 100; const PAUSE_MS = 600;
const log = (m) => console.error(`[capture] ${m}`);
const eq = (field, value) => `${field}:%22${encodeURIComponent(value)}%22`;
// Range brackets are sent percent-encoded (%5B/%5D): rea's HAR validation requires every request URL to be a strict URI.

const browser = await chromium.launch({ executablePath: EXE, headless: true, args: ['--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu'] });
// openFDA answers every document with `Content-Security-Policy: default-src 'none'`, which blocks in-page fetch even to the same
// origin; bypassCSP lets the opened JSON page call its own origin (requests and responses are unchanged).
const context = await browser.newContext({ userAgent: UA, bypassCSP: true, recordHar: { path: HAR, content: 'embed', mode: 'full' } });
await context.route('**/favicon.ico', (r) => r.abort()); // never sent to the API
const page = await context.newPage();
page.setDefaultTimeout(45000);
page.on('requestfailed', (r) => log(`request failed: ${r.url().slice(0, 120)} ${r.failure()?.errorText}`));
let sent = 0; const sizes = [];
const pause = () => page.waitForTimeout(PAUSE_MS);
const api = async (p) => {
  if (sent >= MAX_REQUESTS) throw new Error('request budget reached');
  sent += 1;
  const once = () => page.evaluate(async (p) => {
    try {
      const r = await fetch(p, { headers: { accept: 'application/json' } });
      return { status: r.status, text: await r.text() };
    } catch (e) { return { status: 0, text: '', error: String(e) }; }
  }, p);
  let res = await once();
  if (res.status === 0) { // a dropped connection; wait and retry once (the retry counts against the budget)
    log(`GET ${p} failed (${res.error}); retrying once`); await page.waitForTimeout(3000); sent += 1; res = await once();
  }
  sizes.push([p, res.status, res.text.length]);
  log(`GET ${p} -> ${res.status} ${res.text.length}B`);
  if (res.status === 403) throw new Error('the API refused the request (403)');
  if (res.status === 429) throw new Error('rate limited (429); stop');
  await pause();
  try { return JSON.parse(res.text); } catch { return null; }
};
const results = (d) => (d && Array.isArray(d.results) ? d.results : []);

// open the API origin (a small JSON search) so in-page fetch is same-origin
sent += 1;
await page.goto(`${ORIGIN}/drug/ndc.json?search=${eq('brand_name', 'Tylenol')}&limit=2`, { waitUntil: 'domcontentloaded' });
await pause();
log('opened the origin');

// --- drug product listings (NDC directory) ---
const ndcA = await api(`/drug/ndc.json?search=${eq('labeler_name', 'Kenvue Brands LLC')}&limit=3`);
const ndcB = await api(`/drug/ndc.json?search=${eq('generic_name', 'ibuprofen')}+AND+${eq('dosage_form', 'TABLET')}&limit=2`);
for (const r of [...results(ndcA).slice(0, 2), ...results(ndcB).slice(0, 2)]) await api(`/drug/ndc.json?search=${eq('product_ndc', r.product_ndc)}&limit=1`);

// --- drug recalls (enforcement reports) ---
const drA = await api(`/drug/enforcement.json?search=${eq('classification', 'Class I')}+AND+${eq('status', 'Ongoing')}&limit=3`);
const drB = await api(`/drug/enforcement.json?search=${eq('classification', 'Class II')}+AND+report_date:%5B20260101+TO+20261231%5D&limit=2`);
for (const r of [...results(drA), ...results(drB)]) await api(`/drug/enforcement.json?search=${eq('recall_number', r.recall_number)}&limit=1`);
await api('/drug/enforcement.json?count=classification.exact');
const firm = results(drA)[0]?.recalling_firm; if (firm) await api(`/drug/enforcement.json?search=${eq('recalling_firm', firm)}&limit=2`);

// --- drug applications and shortages ---
const fdaA = await api(`/drug/drugsfda.json?search=${eq('sponsor_name', 'PFIZER')}&limit=1`);
const fdaB = await api(`/drug/drugsfda.json?search=${eq('products.brand_name', 'LIPITOR')}&limit=1`);
for (const r of [...results(fdaA), ...results(fdaB)]) await api(`/drug/drugsfda.json?search=${eq('application_number', r.application_number)}&limit=1`);
const shA = await api(`/drug/shortages.json?search=${eq('status', 'Current')}&limit=2`);
const shB = await api(`/drug/shortages.json?search=${eq('company_name', 'Hospira')}&limit=2`);
for (const r of [...results(shA), ...results(shB).slice(0, 1)]) await api(`/drug/shortages.json?search=${eq('package_ndc', r.package_ndc)}&limit=1`);

// --- NDC SPL data elements ---
const ns = await api(`/other/nsde.json?search=${eq('proprietary_name', 'Advil')}&limit=2`);
for (const r of results(ns)) await api(`/other/nsde.json?search=${eq('package_ndc', r.package_ndc)}&limit=1`);

// --- food recalls in four inland states ---
for (const st of ['CO', 'KS', 'NE', 'IA']) {
  const fe = await api(`/food/enforcement.json?search=${eq('state', st)}+AND+report_date:%5B20250101+TO+20261231%5D&limit=2`);
  for (const r of results(fe)) await api(`/food/enforcement.json?search=${eq('recall_number', r.recall_number)}&limit=1`);
}
await api('/food/enforcement.json?search=report_date:%5B20260101+TO+20261231%5D&count=state.exact&limit=5');

// --- medical devices: classification, recalls, enforcement ---
const dc = await api(`/device/classification.json?search=${eq('device_name', 'stethoscope')}&limit=2`);
for (const r of results(dc)) await api(`/device/classification.json?search=${eq('product_code', r.product_code)}&limit=1`);
const drc = await api(`/device/recall.json?search=${eq('root_cause_description', 'Software design')}&sort=event_date_initiated:desc&limit=1`);
for (const r of results(drc)) await api(`/device/recall.json?search=${eq('product_res_number', r.product_res_number)}&limit=1`);
await api('/device/recall.json?search=event_date_initiated:%5B2026-01-01+TO+2026-10-01%5D&count=root_cause_description.exact&limit=5');
const de = await api(`/device/enforcement.json?search=${eq('classification', 'Class I')}&sort=report_date:desc&limit=2`);
for (const r of results(de)) await api(`/device/enforcement.json?search=${eq('recall_number', r.recall_number)}&limit=1`);

// --- re-read three records to show stable answers ---
const first = results(drA)[0]; if (first) await api(`/drug/enforcement.json?search=${eq('recall_number', first.recall_number)}&limit=1`);
const n0 = results(ndcA)[0]; if (n0) await api(`/drug/ndc.json?search=${eq('product_ndc', n0.product_ndc)}&limit=1`);
const c0 = results(dc)[0]; if (c0) await api(`/device/classification.json?search=${eq('product_code', c0.product_code)}&limit=1`);

await context.close(); // flushes the HAR
await browser.close();
log(`requests sent ${sent}; largest body ${Math.max(...sizes.map((s) => s[2]))}B; over 60000B: ${sizes.filter((s) => s[2] > 60000).map((s) => s[0]).join(', ') || 'none'}; non-200: ${sizes.filter((s) => s[1] !== 200).length}`);
console.log(HAR);
