// Drive the showcase Metabase with Chromium via playwright-core and record a HAR with bodies.
// Login through the UI (/auth/login), visit the main pages, then a scripted read/write/read sequence through fetch from
// inside the page (the metabase.SESSION cookie set by the UI login is carried automatically).
import { chromium } from 'playwright-core';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

const BASE = process.env.BASE_URL || 'http://127.0.0.1:3201';
const DIR = process.env.CAPTURE_DIR || path.join(os.homedir(), 'capture', 'metabase');
const HAR = process.env.HAR_PATH || path.join(DIR, 'metabase.full.har');
const EXE = process.env.CHROMIUM_PATH || '/snap/bin/chromium';
const admin = Object.fromEntries(fs.readFileSync(path.join(DIR, '.admin'), 'utf8').split('\n').filter((l) => l.includes('='))
  .map((l) => { const i = l.indexOf('='); return [l.slice(0, i), l.slice(i + 1)]; }));
const ids = JSON.parse(fs.readFileSync(path.join(DIR, 'seed-ids.json'), 'utf8'));
const log = (m) => console.error(`[capture] ${m}`);

const launchOpts = { executablePath: EXE, headless: true, args: ['--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu'] };
const harOpts = { recordHar: { path: HAR, content: 'embed', mode: 'full' }, viewport: { width: 1440, height: 900 } };
let browser = null; let context;
if (process.env.USER_DATA_DIR) { // fallback when snap confinement rejects Playwright's temp profile
  context = await chromium.launchPersistentContext(process.env.USER_DATA_DIR, { ...launchOpts, ...harOpts });
} else {
  browser = await chromium.launch(launchOpts);
  context = await browser.newContext(harOpts);
}
const page = context.pages()[0] || await context.newPage();
page.setDefaultTimeout(60000);

const settle = async (ms = 2000) => { await page.waitForLoadState('networkidle', { timeout: 30000 }).catch(() => {}); await page.waitForTimeout(ms); };
const visit = async (p, ms) => { log(`visit ${p}`); await page.goto(`${BASE}${p}`, { waitUntil: 'domcontentloaded' }); await settle(ms); };
const api = async (method, p, body) => {
  const res = await page.evaluate(async ({ method, p, body }) => {
    const r = await fetch(p, { method, headers: { 'content-type': 'application/json', accept: 'application/json' }, body: body === undefined ? undefined : JSON.stringify(body) });
    return { status: r.status, text: await r.text() };
  }, { method, p, body });
  log(`${method} ${p} -> ${res.status}`);
  try { return JSON.parse(res.text); } catch { return null; }
};

// --- login through the UI ---
await visit('/auth/login', 1000);
await page.waitForSelector('input[name="username"]');
await page.fill('input[name="username"]', 'rea-admin@example.test'); // fixed, non-secret login email (seed.py EMAIL)
await page.fill('input[name="password"]', admin.MB_ADMIN_PASSWORD);
await page.click('button[type="submit"]');
await page.waitForURL((u) => !u.pathname.startsWith('/auth/'), { timeout: 60000 });
await settle(3000);
log(`logged in, landed on ${new URL(page.url()).pathname}`);

const C = ids.cards; const D = ids.dashboards; const COL = ids.collections; const U = ids.users;

// --- scripted API sequence from inside the page ---
// collections
await api('GET', '/api/collection');
await api('GET', `/api/collection/${COL['granite-ledger']}`);
await api('GET', `/api/collection/${COL['blue-heron-kitchen']}`);
await api('GET', `/api/collection/${COL['saltmarsh-depot']}`);
await api('GET', `/api/collection/${COL['blue-heron-kitchen']}/items`);
await api('GET', `/api/collection/${COL['saltmarsh-depot']}/items?models=card`);
// saved questions and the model
await api('GET', '/api/card?f=all');
for (const k of ['rating-by-category', 'signup-sources', 'widget-reviews', 'ledger-model', 'orders-by-category']) await api('GET', `/api/card/${C[k]}`);
await api('POST', `/api/card/${C['signup-sources']}/query`, {});
await api('POST', `/api/card/${C['rating-by-category']}/query`, {});
// dashboards
await api('GET', '/api/dashboard?f=all');
await api('GET', `/api/dashboard/${D['blue-heron-service-board']}`);
await api('GET', `/api/dashboard/${D['granite-ledger-overview']}`);
// timeline, events, snippet, segment
await api('GET', '/api/timeline?include=events');
await api('GET', `/api/timeline/${ids.timelines['granite-ledger-milestones']}?include=events`);
await api('GET', `/api/timeline-event/${ids.timeline_events['event-1']}`);
await api('GET', `/api/timeline-event/${ids.timeline_events['event-2']}`);
await api('GET', '/api/native-query-snippet');
await api('GET', `/api/native-query-snippet/${ids.snippets['saltmarsh-gizmo-filter']}`);
await api('GET', '/api/segment');
await api('GET', `/api/segment/${ids.segments['granite-large-orders']}`);
// people and groups
await api('GET', '/api/user');
for (const k of ['ada.finch', 'rui.castellanos', 'mina.okafor']) await api('GET', `/api/user/${U[k]}`);
await api('GET', '/api/permissions/group');
await api('GET', `/api/permissions/group/${ids.groups['night-shift-analysts']}`);
// data model of the Sample Database
await api('GET', `/api/database/${ids.database}`);
await api('GET', `/api/table/${ids.tables.products}`);
await api('GET', `/api/field/${ids.fields.products_category}`);
await api('GET', `/api/field/${ids.fields.orders_total}`);
// searches and filters
await api('GET', '/api/search?q=granite');
await api('GET', '/api/search?q=saltmarsh&models=card');
await api('GET', '/api/user?query=okafor');
// --- main UI pages (after the scripted reads, so each tool's first record is a plain scripted read) ---
for (const p of [`/collection/${COL['granite-ledger']}`, `/dashboard/${D['granite-ledger-overview']}`,
  `/question/${C['orders-by-category']}`, `/collection/${COL['saltmarsh-depot']}`, '/admin/people']) {
  await visit(p, 2500);
}

// write path on a scratch saved question: create, rename, re-read, delete, re-read
const created = await api('POST', '/api/card', {
  name: 'Rea scratch tally', description: 'Scratch question written during the capture.', display: 'scalar', type: 'question',
  collection_id: COL['saltmarsh-depot'], visualization_settings: {},
  dataset_query: { database: ids.database, type: 'native', native: { query: 'SELECT COUNT(*) AS PICKS FROM PRODUCTS', 'template-tags': {} } },
});
if (created?.id) {
  const upd = await api('PUT', `/api/card/${created.id}`, { name: 'Rea scratch tally (edited)', description: 'Edited scratch question.' });
  log(`scratch card renamed -> ${upd?.name}`);
  await api('GET', `/api/card/${created.id}`);
  await api('DELETE', `/api/card/${created.id}`);
  await api('GET', `/api/card/${created.id}`);
}
await api('GET', `/api/collection/${COL['saltmarsh-depot']}/items?models=card`);
await settle(500);
await context.close(); // flushes the HAR
if (browser) await browser.close();
log(`HAR written to ${HAR}`);
console.log(HAR);
