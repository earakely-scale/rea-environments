// Drive the showcase Miniflux with Chromium via playwright-core and record a HAR with bodies.
// Miniflux's web UI is server-rendered HTML (its own JavaScript only posts to a few non-/v1 form endpoints), so the JSON
// surface is the documented REST API under /v1. The script signs in through the UI form, browses the main pages, then
// runs a scripted read/write/read sequence with fetch from inside the signed-in page against /v1, authenticating with an
// HTTP Basic header (the /v1 API does not accept the UI session cookie). Headers are stripped by the scoping step.
import { chromium } from 'playwright-core';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

const BASE = process.env.BASE_URL || 'http://127.0.0.1:3217';
const DIR = process.env.CAPTURE_DIR || path.join(os.homedir(), 'capture', 'miniflux');
const HAR = process.env.HAR_PATH || path.join(DIR, 'miniflux.full.har');
const EXE = process.env.CHROMIUM_PATH || '/snap/bin/chromium';
const admin = Object.fromEntries(fs.readFileSync(path.join(DIR, '.admin'), 'utf8').split('\n').filter((l) => l.includes('='))
  .map((l) => { const i = l.indexOf('='); return [l.slice(0, i), l.slice(i + 1)]; }));
const USER = 'rea-admin'; const PASS = admin.MINIFLUX_ADMIN_PASSWORD;
const AUTH = { authorization: `Basic ${Buffer.from(`${USER}:${PASS}`).toString('base64')}` };
const ids = JSON.parse(fs.readFileSync(path.join(DIR, 'seed-ids.json'), 'utf8'));
const log = (m) => console.error(`[capture] ${m}`);

const launchOpts = { executablePath: EXE, headless: true, args: ['--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu'] };
const harOpts = { recordHar: { path: HAR, content: 'embed', mode: 'full' } };
let browser = null; let context;
if (process.env.USER_DATA_DIR) {
  context = await chromium.launchPersistentContext(process.env.USER_DATA_DIR, { ...launchOpts, ...harOpts });
} else {
  browser = await chromium.launch(launchOpts);
  context = await browser.newContext({ ...harOpts, viewport: { width: 1440, height: 900 } });
}
const page = context.pages()[0] || await context.newPage();
page.setDefaultTimeout(45000);

const settle = async (ms = 1000) => { await page.waitForLoadState('networkidle', { timeout: 20000 }).catch(() => {}); await page.waitForTimeout(ms); };
const visit = async (p, ms) => { log(`visit ${p}`); await page.goto(`${BASE}${p}`, { waitUntil: 'domcontentloaded' }); await settle(ms); };
let calls = 0;
const api = async (method, p, body) => {
  const res = await page.evaluate(async ({ method, p, body, headers }) => {
    const r = await fetch(`/v1/${p}`, { method, headers: { ...headers, 'content-type': 'application/json', accept: 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body) });
    return { status: r.status, text: await r.text() };
  }, { method, p, body, headers: AUTH });
  calls += 1; log(`${method} /v1/${p} -> ${res.status}`);
  try { return JSON.parse(res.text); } catch { return null; }
};

// --- sign in through the UI form ---
await visit('/', 300);
await page.fill('input[name="username"]', USER);
await page.fill('input[name="password"]', PASS);
await Promise.all([page.waitForNavigation({ waitUntil: 'domcontentloaded' }), page.click('button[type="submit"]')]);
await settle(800);
if (new URL(page.url()).pathname.startsWith('/login')) throw new Error('UI sign-in failed');
log(`signed in, landed on ${new URL(page.url()).pathname}`);

const F = ids.feeds; const C = ids.categories; const E = ids.entries; const U = ids.users;
const feedIds = Object.values(F); const catIds = Object.values(C); const entryIds = Object.values(E);

// --- main pages (server-rendered HTML; not part of the JSON scope) ---
for (const p of ['/unread', '/starred', '/history', '/feeds', `/feed/${F['Granite Ledger Quarry Notes']}/entries`,
  `/feed/${F['Granite Ledger Quarry Notes']}/entry/${E['Quarterly stone count: 412 blocks']}`, '/categories',
  `/category/${C['Coastal Operations']}/entries`, '/search?q=kelp', '/settings', '/users']) {
  await visit(p, 600);
}

// --- scripted API sequence from inside the page ---
await api('GET', 'version');
await api('GET', 'me');
await api('GET', 'users');
for (const id of Object.values(U)) await api('GET', `users/${id}`);
await api('GET', 'categories');
await api('GET', 'categories?counts=true');
for (const id of catIds) await api('GET', `categories/${id}/feeds`);
for (const id of catIds) await api('GET', `categories/${id}/entries?limit=5&order=published_at&direction=desc`);
// each entry through its category, as the category view links it
const FEED_CAT = { 'Lighthouse Rota Bulletin': 'Coastal Operations', 'Granite Ledger Quarry Notes': 'Quarry and Stone',
  'Blue Heron Kitchen Specials': 'Kitchens and Supplies', 'Saltmarsh Depot Tide Log': 'Coastal Operations' };
const entryFeed = {};
for (const [feedTitle, fid] of Object.entries(F)) {
  const list = await api('GET', `feeds/${fid}/entries?limit=5&order=published_at&direction=asc`);
  for (const e of list?.entries || []) entryFeed[e.id] = feedTitle;
}
for (const [title, id] of Object.entries(E)) await api('GET', `categories/${C[FEED_CAT[entryFeed[id]]]}/entries/${id}`);
await api('GET', 'feeds');
await api('GET', 'feeds/counters');
for (const id of feedIds) await api('GET', `feeds/${id}`);
// each entry through its feed, as the feed view links it
for (const [title, id] of Object.entries(E)) await api('GET', `feeds/${F[entryFeed[id]]}/entries/${id}`);
await api('GET', `feeds/${F['Blue Heron Kitchen Specials']}/icon`);
// every entry by id
for (const id of entryIds) await api('GET', `entries/${id}`);
// searches and filters
await api('GET', 'entries?status=unread&limit=10&order=published_at&direction=desc');
await api('GET', 'entries?starred=true&limit=10');
await api('GET', 'entries?search=kelp&limit=10');
await api('GET', 'entries?status=read&limit=10');
await api('GET', `entries?category_id=${C['Quarry and Stone']}&limit=10&order=published_at&direction=asc`);
await api('GET', `entries?before_entry_id=${E['Quarterly stone count: 412 blocks']}&limit=3&order=id&direction=desc`);
await api('GET', 'entries?published_after=1791590400&limit=10&order=published_at&direction=asc');
await api('GET', 'users/mina-okafor');
await api('GET', 'integrations/status');
// a no-op feed update and a refresh (the feed host serves the same file, so nothing changes)
await api('PUT', `feeds/${F['Saltmarsh Depot Tide Log']}`, { title: 'Saltmarsh Depot Tide Log', category_id: C['Coastal Operations'] });
await api('PUT', `feeds/${F['Saltmarsh Depot Tide Log']}/refresh`);
await api('GET', `feeds/${F['Saltmarsh Depot Tide Log']}`);
await api('POST', 'discover', { url: 'http://feeds/saltmarsh-depot-tide-log.atom' });
// write path: a scratch category (create, rename, read, delete, re-read) and entry state changes
const created = await api('POST', 'categories', { title: 'Rea scratch category' });
if (created?.id) {
  const upd = await api('PUT', `categories/${created.id}`, { title: 'Rea scratch category (edited)' });
  log(`scratch category renamed -> ${upd?.title}`);
  await api('GET', 'categories');
  await api('DELETE', `categories/${created.id}`);
  await api('GET', `categories/${created.id}/feeds`);
}
const glance = E['Seaward stack re-measured at 31 metres'];
await api('PUT', 'entries', { entry_ids: [glance], status: 'read' });
await api('GET', `entries/${glance}`);
await api('PUT', 'entries', { entry_ids: [glance], status: 'unread' });
await api('PUT', `entries/${E['Copperfield Annex collects 12 drums']}/bookmark`);
await api('GET', `entries/${E['Copperfield Annex collects 12 drums']}`);
await api('PUT', `entries/${E['Copperfield Annex collects 12 drums']}/bookmark`);
await api('GET', 'entries?starred=true&limit=10');
await api('GET', 'feeds/counters');
await settle(300);
await context.close(); // flushes the HAR
if (browser) await browser.close();
log(`${calls} scripted calls; HAR written to ${HAR}`);
console.log(HAR);
