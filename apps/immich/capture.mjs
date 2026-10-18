// Drive the showcase Immich web app with Chromium via playwright-core and record a HAR with bodies.
// Login through the web UI, visit the main pages, then a scripted read/write/read sequence through fetch from inside the
// page (the web app authenticates with its immich_access_token cookie, which fetch carries automatically).
import { chromium } from 'playwright-core';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

const BASE = process.env.BASE_URL || 'http://127.0.0.1:3207';
const DIR = process.env.CAPTURE_DIR || path.join(os.homedir(), 'capture', 'immich');
const HAR = process.env.HAR_PATH || path.join(DIR, 'immich.full.har');
const EXE = process.env.CHROMIUM_PATH || '/snap/bin/chromium';
const admin = Object.fromEntries(fs.readFileSync(path.join(DIR, '.admin'), 'utf8').split('\n').filter((l) => l.includes('='))
  .map((l) => { const i = l.indexOf('='); return [l.slice(0, i), l.slice(i + 1)]; }));
const EMAIL = 'rea-admin@example.test'; const PASS = admin.IMMICH_ADMIN_PASSWORD;
const ids = JSON.parse(fs.readFileSync(path.join(DIR, 'seed-ids.json'), 'utf8'));
const log = (m) => console.error(`[capture] ${m}`);

const launchOpts = { executablePath: EXE, headless: true, args: ['--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu'] };
const harOpts = { recordHar: { path: HAR, content: 'embed', mode: 'full' } };
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
// Client-side navigation: the SvelteKit router intercepts anchor clicks, so the app does not re-run its boot requests.
const nav = async (p, ms) => {
  log(`nav ${p}`);
  await page.evaluate((href) => { const a = document.createElement('a'); a.href = href; document.body.appendChild(a); a.click(); a.remove(); }, p);
  await page.waitForURL((u) => u.pathname === p.split('?')[0], { timeout: 20000 }).catch(() => log(`  (url is ${new URL(page.url()).pathname})`));
  await settle(ms);
};
const api = async (method, p, body) => {
  const res = await page.evaluate(async ({ method, p, body }) => {
    const r = await fetch(p, { method, headers: { 'content-type': 'application/json', accept: 'application/json' }, body: body === undefined ? undefined : JSON.stringify(body) });
    return { status: r.status, text: await r.text() };
  }, { method, p, body });
  log(`${method} ${p} -> ${res.status}`);
  try { return JSON.parse(res.text); } catch { return null; }
};

// --- login through the web UI ---
await visit('/auth/login', 1000);
await page.waitForSelector('input[type="email"], input#email');
await page.fill('input[type="email"], input#email', EMAIL);
await page.fill('input[type="password"]', PASS);
await page.click('button[type="submit"]');
await page.waitForURL((u) => !u.pathname.startsWith('/auth/login'), { timeout: 45000 });
await settle(2500);
log(`logged in, landed on ${new URL(page.url()).pathname}`);

const A = ids.assets; const AL = ids.albums; const T = ids.tags; const P = ids.people; const U = ids.users;
const night = AL['Lighthouse Rota Night Shift'];

// --- main pages (UI traffic, client-side navigation after the first load) ---
for (const p of ['/albums', `/albums/${night}`, '/sharing', '/explore', '/people', `/photos/${A['granite-ledger-north-quarry']}`,
  '/tags', '/admin/users', '/user-settings', '/photos']) {
  await nav(p, 1500);
}

// --- scripted API sequence from inside the page ---
await api('GET', '/api/users/me');
await api('GET', '/api/users');
await api('GET', `/api/users/${U['ada-finch']}`);
await api('GET', `/api/users/${U['rui-castellanos']}`);
await api('GET', '/api/admin/users');
await api('GET', `/api/admin/users/${U['ada-finch']}`);
await api('GET', `/api/admin/users/${U['rui-castellanos']}`);
await api('GET', '/api/albums');
for (const id of Object.values(AL)) await api('GET', `/api/albums/${id}`);
await api('GET', `/api/albums?assetId=${A['saltmarsh-depot-cart-7']}`);
for (const id of Object.values(A)) await api('GET', `/api/assets/${id}`);
await api('GET', '/api/tags');
for (const id of Object.values(T)) await api('GET', `/api/tags/${id}`);
await api('GET', '/api/people?withHidden=true');
for (const id of Object.values(P)) await api('GET', `/api/people/${id}`);
await api('GET', '/api/search/person?name=Mina');
await api('POST', '/api/search/metadata', { description: 'quarry', size: 10 });
await api('GET', '/api/shared-links');
for (const id of Object.values(ids.shared_links)) await api('GET', `/api/shared-links/${id}`);
await api('GET', `/api/activities?albumId=${night}`);
await api('GET', '/api/partners?direction=shared-by');
await api('GET', '/api/libraries');
await api('GET', `/api/libraries/${ids.libraries['Saltmarsh Depot Archive']}`);
await api('GET', '/api/notifications');

// write path on a scratch album: create, edit, re-read, delete, re-read
const created = await api('POST', '/api/albums', { albumName: 'Rea scratch album', description: 'Scratch album written during the capture.', assetIds: [A['blue-heron-kitchen-pass']] });
if (created?.id) {
  const upd = await api('PATCH', `/api/albums/${created.id}`, { albumName: 'Rea scratch album (edited)', description: 'Edited scratch album.' });
  log(`scratch album edited -> ${upd?.albumName}`);
  await api('GET', `/api/albums/${created.id}`);
  await api('DELETE', `/api/albums/${created.id}`);
  await api('GET', `/api/albums/${created.id}`);
}
await api('GET', '/api/albums');
await settle(500);
await context.close(); // flushes the HAR
if (browser) await browser.close();
log(`HAR written to ${HAR}`);
console.log(HAR);
