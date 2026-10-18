// Drive the showcase Navidrome web app with Chromium via playwright-core and record a HAR with bodies.
// Login through the web UI, visit the main views (hash routes, so the app does not reload), then a scripted
// read/write/read sequence against the native API /api through fetch from inside the page. The web app keeps its JWT in
// localStorage and sends it as x-nd-authorization; the script reads it in the page and does the same (request headers are
// stripped by scope_har.py). The Subsonic API under /rest carries password-derived tokens in its query string and is
// kept out of the scope.
import { chromium } from 'playwright-core';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

const BASE = process.env.BASE_URL || 'http://127.0.0.1:3233';
const DIR = process.env.CAPTURE_DIR || path.join(os.homedir(), 'capture', 'navidrome');
const HAR = process.env.HAR_PATH || path.join(DIR, 'navidrome.full.har');
const EXE = process.env.CHROMIUM_PATH || '/snap/bin/chromium';
const admin = Object.fromEntries(fs.readFileSync(path.join(DIR, '.admin'), 'utf8').split('\n').filter((l) => l.includes('='))
  .map((l) => { const i = l.indexOf('='); return [l.slice(0, i), l.slice(i + 1)]; }));
const USER = 'rea-admin'; const PASS = admin.NAVIDROME_ADMIN_PASSWORD;
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

const settle = async (ms = 1500) => { await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => {}); await page.waitForTimeout(ms); };
const visit = async (p, ms) => { log(`visit ${p}`); await page.goto(`${BASE}${p}`, { waitUntil: 'domcontentloaded' }); await settle(ms); };
const hash = async (h, ms) => { log(`view ${h}`); await page.evaluate((h) => { window.location.hash = h; }, h); await settle(ms); };
const api = async (method, p, body) => {
  const res = await page.evaluate(async ({ method, p, body }) => {
    const headers = { 'content-type': 'application/json', accept: 'application/json', 'x-nd-authorization': `Bearer ${localStorage.getItem('token')}` };
    const r = await fetch(p, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });
    return { status: r.status, text: await r.text() };
  }, { method, p, body });
  log(`${method} ${p} -> ${res.status}`);
  try { return JSON.parse(res.text); } catch { return null; }
};

// --- login through the web UI ---
await visit('/app/', 1000);
await page.waitForSelector('input[name="username"]');
await page.fill('input[name="username"]', USER);
await page.fill('input[name="password"]', PASS);
await page.click('button[type="submit"]');
await page.waitForFunction(() => !!localStorage.getItem('token'), null, { timeout: 45000 });
await settle(2500);
log(`logged in, view ${new URL(page.url()).hash}`);

const AL = ids.albums; const AR = ids.artists; const S = ids.songs; const PL = ids.playlists;
// --- main views (UI traffic) ---
for (const h of ['#/album/all', `#/album/${AL['Tide Tables']}/show`, '#/artist', `#/artist/${AR['Ada Finch Quartet']}/show`, '#/song',
  '#/playlist', `#/playlist/${PL['Lighthouse Rota Night Mix']}/show`, '#/radio', '#/share', '#/user', '#/player', '#/library', '#/album/all']) {
  await hash(h, 1500);
}

// --- scripted API sequence from inside the page ---
await api('GET', '/api/album?_start=0&_end=15&_sort=name&_order=ASC');
for (const id of Object.values(AL)) await api('GET', `/api/album/${id}`);
await api('GET', '/api/artist?_start=0&_end=15&_sort=name&_order=ASC');
for (const n of ['The Saltmarsh Lanterns', 'Ada Finch Quartet', 'Granite Ledger Choir', 'Mina Okafor', 'Rui Castellanos']) await api('GET', `/api/artist/${AR[n]}`);
await api('GET', '/api/artist?_start=0&_end=15&_sort=name&_order=ASC&role=composer');
await api('GET', '/api/song?_start=0&_end=20&_sort=title&_order=ASC');
for (const t of Object.keys(S).sort()) {
  await api('GET', `/api/song/${S[t]}`);
}
await api('GET', `/api/song?_start=0&_end=20&album_id=${AL['Quarry Hymns']}`);
await api('GET', '/api/song?_start=0&_end=10&title=lamp');
await api('GET', `/api/song/${S['Lamp Oil Waltz']}/playlists`);
await api('GET', '/api/genre?_start=0&_end=10');
await api('GET', '/api/album?_start=0&_end=10&name=tide');
await api('GET', '/api/tag?_start=0&_end=20&tag_name=genre');
await api('GET', '/api/playlist?_start=0&_end=10');
for (const id of Object.values(PL)) { await api('GET', `/api/playlist/${id}`); await api('GET', `/api/playlist/${id}/tracks?_start=0&_end=10`); }
await api('GET', '/api/radio');
for (const id of Object.values(ids.radios)) await api('GET', `/api/radio/${id}`);
await api('GET', '/api/share');
for (const id of Object.values(ids.shares)) await api('GET', `/api/share/${id}`);
await api('GET', '/api/user');
await api('GET', `/api/user/${ids.users['mina.okafor']}`);
await api('GET', `/api/user/${ids.admin}`);
await api('GET', '/api/library');
for (const id of Object.values(ids.libraries)) await api('GET', `/api/library/${id}`);

// write path on a scratch playlist: create, update, re-read, delete, re-read
const created = await api('POST', '/api/playlist', { name: 'Rea scratch playlist', comment: 'Scratch playlist written during the capture.', public: false });
if (created?.id) {
  await api('PUT', `/api/playlist/${created.id}`, { id: created.id, name: 'Rea scratch playlist (edited)', comment: 'Edited scratch playlist.', public: false });
  await api('GET', `/api/playlist/${created.id}`);
  await api('DELETE', `/api/playlist/${created.id}`);
  await api('GET', `/api/playlist/${created.id}`);
}
await api('GET', '/api/playlist?_start=0&_end=10');
await settle(500);
await context.close(); // flushes the HAR
if (browser) await browser.close();
log(`HAR written to ${HAR}`);
console.log(HAR);
