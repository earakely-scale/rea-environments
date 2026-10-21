// Drive the showcase Komga web UI with Chromium via playwright-core and record a HAR with bodies.
// Login through the UI (/login: the UI sends basic auth once to /api/v2/users/me and then rides the session cookie),
// a scripted read sequence through fetch from inside the page, the main UI pages, then writes on two scratch collections and
// two scratch read lists, each write read back at once (record_writes.mjs).
import { chromium } from 'playwright-core';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { recordWrites } from '../record_writes.mjs'; // shipped to ~/capture/ next to scope_har.py

const BASE = process.env.BASE_URL || 'http://127.0.0.1:3231';
const DIR = process.env.CAPTURE_DIR || path.join(os.homedir(), 'capture', 'komga');
const HAR = process.env.HAR_PATH || path.join(DIR, 'komga.full.har');
const EXE = process.env.CHROMIUM_PATH || '/snap/bin/chromium';
const admin = Object.fromEntries(fs.readFileSync(path.join(DIR, '.admin'), 'utf8').split('\n').filter((l) => l.includes('='))
  .map((l) => { const i = l.indexOf('='); return [l.slice(0, i), l.slice(i + 1)]; }));
const ids = JSON.parse(fs.readFileSync(path.join(DIR, 'seed-ids.json'), 'utf8'));
const log = (m) => console.error(`[capture] ${m}`);

const launchOpts = { executablePath: EXE, headless: true, args: ['--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu'] };
const harOpts = { recordHar: { path: HAR, content: 'embed', mode: 'full' }, viewport: { width: 1440, height: 900 } };
let browser = null; let context;
if (process.env.USER_DATA_DIR) {
  context = await chromium.launchPersistentContext(process.env.USER_DATA_DIR, { ...launchOpts, ...harOpts });
} else {
  browser = await chromium.launch(launchOpts);
  context = await browser.newContext(harOpts);
}
const page = context.pages()[0] || await context.newPage();
page.setDefaultTimeout(45000);

const settle = async (ms = 1500) => { await page.waitForLoadState('networkidle', { timeout: 20000 }).catch(() => {}); await page.waitForTimeout(ms); };
const visit = async (p, ms) => { log(`visit ${p}`); await page.goto(`${BASE}${p}`, { waitUntil: 'domcontentloaded' }); await settle(ms); };
const api = async (method, p, body) => {
  const res = await page.evaluate(async ({ method, p, body }) => {
    const r = await fetch(p, { method, credentials: 'same-origin', headers: { accept: 'application/json', 'X-Requested-With': 'XMLHttpRequest', ...(body === undefined ? {} : { 'content-type': 'application/json' }) }, body: body === undefined ? undefined : JSON.stringify(body) });
    return { status: r.status, text: await r.text() };
  }, { method, p, body });
  log(`${method} ${p} -> ${res.status}`);
  try { return JSON.parse(res.text); } catch { return null; }
};

// --- login through the UI ---
// land on the account page, not the dashboard, so the scripted reads below are the first records of each route
await visit('/login?redirect=%2Faccount%2Fme', 1500);
await page.fill('input[autocomplete="username"]', 'rea-admin@example.test'); // fixed, non-secret login email (seed.py EMAIL)
await page.fill('input[autocomplete="current-password"]', admin.KOMGA_ADMIN_PASSWORD);
await page.click('button[type="submit"]');
await page.waitForURL((u) => !u.pathname.startsWith('/login'), { timeout: 45000 });
await settle(2500);
log(`logged in, landed on ${new URL(page.url()).pathname}`);

const S = ids.series; const B = ids.books; const C = ids.collections; const R = ids.readlists; const U = ids.users; const L = ids.library;
// --- scripted reads ---
await api('GET', '/api/v1/libraries');
await api('GET', `/api/v1/libraries/${L}`);
await api('GET', '/api/v1/series?size=20');
await api('GET', `/api/v1/series/${S['granite-ledger']}`);
await api('GET', `/api/v1/series/${S['lighthouse-rota']}`);
await api('GET', `/api/v1/series/${S['blue-heron-kitchen']}`);
for (const k of ['lighthouse-rota', 'granite-ledger']) await api('GET', `/api/v1/series/${S[k]}/books`);
for (const k of ['granite-ledger', 'blue-heron-kitchen']) await api('GET', `/api/v1/series/${S[k]}/collections`);
await api('GET', '/api/v1/books?size=20');
for (const k of ['blue-heron-kitchen-02', 'granite-ledger-01', 'lighthouse-rota-03', 'lighthouse-rota-01']) await api('GET', `/api/v1/books/${B[k]}`);
await api('GET', `/api/v1/books/${B['lighthouse-rota-02']}/next`);
await api('GET', `/api/v1/books/${B['blue-heron-kitchen-01']}/next`);
await api('GET', `/api/v1/books/${B['granite-ledger-02']}/previous`);
await api('GET', `/api/v1/books/${B['lighthouse-rota-03']}/previous`);
for (const k of ['granite-ledger-01', 'lighthouse-rota-03']) await api('GET', `/api/v1/books/${B[k]}/readlists`);
await api('GET', `/api/v1/books/${B['blue-heron-kitchen-01']}/pages`);
await api('GET', '/api/v1/collections');
await api('GET', `/api/v1/collections/${C['quarry-and-depot-files']}`);
await api('GET', `/api/v1/collections/${C['night-shift-reading']}`);
for (const k of ['night-shift-reading', 'quarry-and-depot-files']) await api('GET', `/api/v1/collections/${C[k]}/series`);
await api('GET', '/api/v1/readlists');
for (const k of ['granite-ledger-audit-order', 'blue-heron-tasting-order']) {
  await api('GET', `/api/v1/readlists/${R[k]}`);
  await api('GET', `/api/v1/readlists/${R[k]}/books`);
}
await api('GET', `/api/v1/readlists/${R['granite-ledger-audit-order']}/books/${B['granite-ledger-02']}/next`);
await api('GET', `/api/v1/readlists/${R['blue-heron-tasting-order']}/books/${B['blue-heron-kitchen-01']}/next`);
await api('GET', '/api/v2/users/me');
await api('GET', '/api/v2/users');
await api('GET', `/api/v2/users/${U['rea-admin']}/authentication-activity/latest`); // only rea-admin has signed in
await api('GET', '/api/v1/genres');
await api('GET', '/api/v1/tags/series');
await api('GET', '/api/v1/publishers');
await api('GET', '/api/v1/age-ratings');
await api('GET', '/api/v2/authors?role=writer');
// searches and filters
await api('GET', '/api/v1/series?search=granite');
await api('GET', '/api/v1/books?search=kelp');
await api('GET', '/api/v1/series?status=ONGOING');
await api('GET', '/api/v1/books?tag=audit');
await api('GET', '/api/v1/books/ondeck');

// --- main UI pages ---
for (const p of ['/dashboard', `/libraries/${L}/series`, `/series/${S['lighthouse-rota']}`, `/book/${B['granite-ledger-01']}`,
  `/collections/${C['night-shift-reading']}`, `/readlists/${R['granite-ledger-audit-order']}`]) await visit(p, 2000);

// --- writes on scratch objects ---
await recordWrites(api, {
  collection: '/api/v1/collections', list: '/api/v1/collections', item: (id) => `/api/v1/collections/${id}`, id: (c) => c?.id,
  create: (n) => ({ name: `Rea scratch collection ${n}`, ordered: false, seriesIds: [S['blue-heron-kitchen']] }),
  update: (n) => ({ name: `Rea scratch collection ${n} (edited)`, ordered: true }),
});
await recordWrites(api, {
  collection: '/api/v1/readlists', list: '/api/v1/readlists', item: (id) => `/api/v1/readlists/${id}`, id: (r) => r?.id,
  create: (n) => ({ name: `Rea scratch read list ${n}`, summary: `Scratch read list ${n} written during the capture.`, ordered: true,
    bookIds: [B['blue-heron-kitchen-01']] }),
  update: (n) => ({ summary: `Edited scratch read list ${n}.` }),
});
await settle(500);
await context.close();
if (browser) await browser.close();
log(`HAR written to ${HAR}`);
console.log(HAR);
