// Record a HAR of the public Federal Register API (https://www.federalregister.gov/api/v1) with Chromium via playwright-core.
// No key, no login. Fair access: a declared User-Agent on the browser context, one request at a time, a 600 ms pause
// between calls, about 55 requests in total, small bodies (per_page <= 5 and fields[] on every document read).
// Opens one API URL (an agency record) so that every later in-page fetch is same-origin, then: agency reads, document
// searches and filters, facet counts, document reads by number, public-inspection reads, suggested searches.
import { chromium } from 'playwright-core';
import os from 'node:os';
import path from 'node:path';

const ORIGIN = 'https://www.federalregister.gov';
const API = '/api/v1';
const DIR = process.env.CAPTURE_DIR || path.join(os.homedir(), 'capture', 'federal-register');
const HAR = process.env.HAR_PATH || path.join(DIR, 'federal-register.full.har');
const EXE = process.env.CHROMIUM_PATH || '/snap/bin/chromium';
const UA = 'rea-environments showcase (https://github.com/earakely-scale/rea-environments)';
const PAUSE_MS = 600;
const log = (m) => console.error(`[capture] ${m}`);

const browser = await chromium.launch({ executablePath: EXE, headless: true, args: ['--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu'] });
const context = await browser.newContext({ userAgent: UA, recordHar: { path: HAR, content: 'embed', mode: 'full' } });
const page = await context.newPage();
page.setDefaultTimeout(45000);
let calls = 0;

const get = async (p) => {
  await page.waitForTimeout(PAUSE_MS);
  calls += 1;
  const res = await page.evaluate(async (p) => {
    const r = await fetch(p, { headers: { accept: 'application/json' } });
    return { status: r.status, text: await r.text() };
  }, p);
  log(`#${calls} GET ${p} -> ${res.status} (${res.text.length} bytes)`);
  try { return JSON.parse(res.text); } catch { return null; }
};
const qs = (pairs) => pairs.map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v)}`).join('&');
const fields = (names) => names.map((n) => ['fields[]', n]);
const DOC_FIELDS = ['document_number', 'title', 'type', 'subtype', 'action', 'abstract', 'agencies', 'publication_date', 'citation',
  'start_page', 'end_page', 'page_length', 'docket_ids', 'regulation_id_numbers', 'effective_on', 'comments_close_on', 'dates',
  'significant', 'cfr_references', 'executive_order_number', 'signing_date'];
const LIST_FIELDS = ['document_number', 'title', 'type', 'action', 'publication_date'];

// --- open the API origin on one agency record (navigation), then same-origin fetches ---
calls += 1;
const first = await page.goto(`${ORIGIN}${API}/agencies/federal-aviation-administration.json`, { waitUntil: 'domcontentloaded' });
log(`#${calls} NAV agencies/federal-aviation-administration.json -> ${first.status()} ${page.url()}`);
if (!page.url().startsWith(`${ORIGIN}${API}/`)) throw new Error(`redirected away from the API: ${page.url()}`);

// agencies by slug
for (const slug of ['transportation-department', 'energy-department', 'federal-energy-regulatory-commission',
  'homeland-security-department', 'federal-emergency-management-agency', 'executive-office-of-the-president']) {
  await get(`${API}/agencies/${slug}.json`);
}

// document searches and filters (fixed past date ranges, oldest first, so results are stable)
const faaSept = [['conditions[agencies][]', 'federal-aviation-administration'], ['conditions[type][]', 'RULE'],
  ['conditions[publication_date][gte]', '2026-09-01'], ['conditions[publication_date][lte]', '2026-09-30']];
await get(`${API}/documents.json?${qs([['per_page', '5'], ['order', 'oldest'], ...faaSept, ...fields(LIST_FIELDS)])}`);
await get(`${API}/documents.json?${qs([['per_page', '5'], ['page', '2'], ['order', 'oldest'], ...faaSept, ...fields(LIST_FIELDS)])}`);
await get(`${API}/documents.json?${qs([['per_page', '5'], ['order', 'oldest'], ['conditions[agencies][]', 'energy-department'],
  ['conditions[type][]', 'PRORULE'], ['conditions[publication_date][gte]', '2026-01-01'], ['conditions[publication_date][lte]', '2026-09-30'], ...fields(LIST_FIELDS)])}`);
await get(`${API}/documents.json?${qs([['per_page', '5'], ['order', 'oldest'], ['conditions[type][]', 'PRESDOCU'],
  ['conditions[presidential_document_type][]', 'executive_order'], ['conditions[signing_date][gte]', '2026-01-01'],
  ['conditions[signing_date][lte]', '2026-03-31'], ...fields(['document_number', 'title', 'executive_order_number', 'signing_date', 'publication_date'])])}`);
await get(`${API}/documents.json?${qs([['per_page', '5'], ['conditions[term]', 'distribution transformers'],
  ['conditions[publication_date][year]', '2026'], ...fields(['document_number', 'title', 'type', 'publication_date', 'agencies'])])}`);
await get(`${API}/documents.json?${qs([['per_page', '5'], ['conditions[docket_id]', 'EERE-2026-BT-STD-0133'], ...fields(LIST_FIELDS)])}`);
await get(`${API}/documents.json?${qs([['per_page', '5'], ['order', 'oldest'], ['conditions[regulation_id_number]', '1904-AF51'], ...fields(LIST_FIELDS)])}`);

// facet counts
await get(`${API}/documents/facets/type?${qs(faaSept.filter(([k]) => k !== 'conditions[type][]'))}`);
await get(`${API}/documents/facets/monthly?${qs([['conditions[agencies][]', 'energy-department'], ['conditions[publication_date][year]', '2026']])}`);
await get(`${API}/documents/facets/agency?${qs([['conditions[type][]', 'PRESDOCU'], ['conditions[publication_date][gte]', '2026-09-01'], ['conditions[publication_date][lte]', '2026-09-30']])}`);

// documents by number (FAA rules, Energy and FERC proposals, a CBP proposal, executive orders)
const DOCS = ['2026-18019', '2026-18032', '2026-18126', '2026-18437', '2026-18559', '2026-18601', '2026-18776', '2026-18848',
  '2026-18902', '2026-19082', '2026-01066', '2026-03159', '2026-06177', '2026-10498', '2026-11971', '2026-13673', '2026-17108',
  '2026-19332', '2026-01061', '2026-01872', '2026-02292', '2026-03628', '2026-05382'];
for (const n of DOCS) await get(`${API}/documents/${n}.json?${qs(fields(DOC_FIELDS))}`);
await get(`${API}/documents/2026-18126,2026-18902.json?${qs(fields(['document_number', 'title', 'publication_date', 'docket_ids']))}`);
await get(`${API}/documents/2026-18776.json`);  // default field set, once

// public inspection (documents filed for inspection before publication)
for (const n of ['2026-18126', '2026-18902', '2026-18776', '2026-19332', '2026-11971', '2026-02292']) {
  await get(`${API}/public-inspection-documents/${n}.json`);
}
await get(`${API}/public-inspection-documents/2026-18126,2026-19332.json`);

// suggested searches
await get(`${API}/suggested_searches.json?${qs([['conditions[sections]', 'business-and-industry']])}`);
await get(`${API}/suggested_searches/pipeline-safety.json`);
await get(`${API}/suggested_searches/air-travel.json`);

await page.waitForTimeout(500);
await context.close(); // flushes the HAR
await browser.close();
log(`${calls} requests; HAR written to ${HAR}`);
console.log(HAR);
