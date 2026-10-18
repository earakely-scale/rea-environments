// Drive the showcase BookStack with Chromium via playwright-core and record a HAR with bodies.
// Login through the web UI, visit the main pages, then a scripted sequence of fetch calls from inside the page against the
// REST API. BookStack's own UI is server-rendered and does not call /api; the API accepts the browser session cookie for GET
// requests only ("Only GET requests are allowed when using the API with cookie-based authentication"), so reads ride on the
// session and the three writes send the API token from .admin as an Authorization header with credentials omitted.
// Request headers are stripped from the scoped HAR by scope_har.py.
import { chromium } from 'playwright-core';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

const BASE = process.env.BASE_URL || 'http://127.0.0.1:3219';
const DIR = process.env.CAPTURE_DIR || path.join(os.homedir(), 'capture', 'bookstack');
const HAR = process.env.HAR_PATH || path.join(DIR, 'bookstack.full.har');
const EXE = process.env.CHROMIUM_PATH || '/snap/bin/chromium';
const admin = Object.fromEntries(fs.readFileSync(path.join(DIR, '.admin'), 'utf8').split('\n').filter((l) => l.includes('='))
  .map((l) => { const i = l.indexOf('='); return [l.slice(0, i), l.slice(i + 1)]; }));
const EMAIL = 'rea-admin@example.test'; const PASS = admin.REA_ADMIN_PASSWORD;
const TOKEN = `Token ${admin.BOOKSTACK_TOKEN_ID}:${admin.BOOKSTACK_TOKEN_SECRET}`;
const ids = JSON.parse(fs.readFileSync(path.join(DIR, 'seed-ids.json'), 'utf8'));
const log = (m) => console.error(`[capture] ${m}`);

const launchOpts = { executablePath: EXE, headless: true, args: ['--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu'] };
const harOpts = { recordHar: { path: HAR, content: 'embed', mode: 'full' } };
let browser = null; let context;
if (process.env.USER_DATA_DIR) { // fallback when snap confinement rejects Playwright's temp profile
  context = await chromium.launchPersistentContext(process.env.USER_DATA_DIR, { ...launchOpts, ...harOpts });
} else {
  browser = await chromium.launch(launchOpts);
  context = await browser.newContext(harOpts);
}
const page = context.pages()[0] || await context.newPage();
page.setDefaultTimeout(45000);

const settle = async (ms = 1200) => { await page.waitForLoadState('networkidle', { timeout: 20000 }).catch(() => {}); await page.waitForTimeout(ms); };
const visit = async (p, ms) => { log(`visit ${p}`); await page.goto(`${BASE}${p}`, { waitUntil: 'domcontentloaded' }); await settle(ms); };
const calls = [];
const api = async (method, p, body) => {
  const res = await page.evaluate(async ({ method, p, body, token }) => {
    const write = method !== 'GET';
    const headers = { accept: 'application/json' };
    if (write) { headers['content-type'] = 'application/json'; headers.authorization = token; }
    const r = await fetch(p, { method, headers, credentials: write ? 'omit' : 'same-origin', body: body === undefined ? undefined : JSON.stringify(body) });
    return { status: r.status, text: await r.text() };
  }, { method, p, body, token: method !== 'GET' ? TOKEN : null });
  log(`${method} ${p} -> ${res.status}`); calls.push({ method, path: p, status: res.status });
  try { return JSON.parse(res.text); } catch { return null; }
};

// --- login through the web UI ---
await visit('/login', 500);
await page.fill('#email', EMAIL);
await page.fill('#password', PASS);
await Promise.all([page.waitForURL((u) => !u.pathname.startsWith('/login'), { timeout: 45000 }), page.click('#login-form button.button')]);
await settle(1500);
log(`logged in, landed on ${new URL(page.url()).pathname}`);

// --- main pages (server-rendered UI) ---
for (const p of ['/', '/shelves', '/shelves/lighthouse-rota-handbooks', '/books', '/books/lamp-room-procedures',
  '/books/lamp-room-procedures/chapter/wick-and-lens-care', '/books/lamp-room-procedures/page/trimming-the-wick',
  '/search?term=granite', '/tags', '/settings/users', '/settings/roles', '/settings/audit']) {
  await visit(p);
}

// --- scripted REST sequence from inside the page ---
// Read every seeded object by id; the first read of each collection is an item owned by someone other than the admin.
const order = (m, first) => [m[first], ...Object.values(m).filter((v) => v !== m[first])];
const B = ids.books; const S = ids.shelves; const C = ids.chapters; const P = ids.pages; const U = ids.users; const R = ids.roles;
const sys = await api('GET', '/api/system'); log(`bookstack ${sys?.version}`);
await api('GET', '/api/shelves');
for (const id of order(S, 'Granite Ledger Archive')) await api('GET', `/api/shelves/${id}`);
await api('GET', '/api/books');
for (const id of order(B, 'Tide Table Almanac')) await api('GET', `/api/books/${id}`);
await api('GET', '/api/books?filter%5Bname%3Alike%5D=%25Tide%25');
await api('GET', '/api/chapters');
for (const id of order(C, 'Winter Spring Tides')) await api('GET', `/api/chapters/${id}`);
await api('GET', `/api/chapters?filter%5Bbook_id%5D=${B['Lamp Room Procedures']}`);
await api('GET', '/api/pages');
for (const id of order(P, 'January Tide Readings')) await api('GET', `/api/pages/${id}`);
await api('GET', '/api/pages?sort=%2Bname&count=5');
await api('GET', '/api/attachments');
for (const id of order(ids.attachments, 'Terrace Seven Survey Sheet')) await api('GET', `/api/attachments/${id}`);
await api('GET', '/api/comments');
for (const id of order(ids.comments, 'Smoked Kelp Broth')) await api('GET', `/api/comments/${id}`);
await api('GET', '/api/users');
for (const id of order(U, 'ada.finch')) await api('GET', `/api/users/${id}`);
await api('GET', '/api/roles');
for (const id of [R['Tide Clerks'], R['Quarry Auditors'], 2]) await api('GET', `/api/roles/${id}`);
await api('GET', '/api/tags/names');
await api('GET', '/api/tags/values-for-name?name=site');
await api('GET', '/api/tags/values-for-name?name=auditor');
await api('GET', '/api/search?query=granite&count=5');
await api('GET', '/api/search?query=kelp&count=5');
await api('GET', `/api/search/book/${B['Lamp Room Procedures']}?query=wick`);
await api('GET', `/api/search/chapter/${C['North Quarry Counts']}?query=terrace`);
await api('GET', `/api/content-permissions/book/${B['Quarry Audit Manual']}`);
await api('GET', `/api/content-permissions/page/${P['Smoked Kelp Broth']}`);
await api('GET', '/api/audit-log?count=8&sort=-created_at');
await api('GET', '/api/image-gallery');
await api('GET', '/api/recycle-bin');
// write path on a scratch book (token auth): create, update, add a page, re-read, delete, re-read
const created = await api('POST', '/api/books', { name: 'Rea Scratch Book', description: 'Temporary book written during the capture.', tags: [{ name: 'scratch', value: 'yes' }] });
if (created?.id) {
  await api('PUT', `/api/books/${created.id}`, { name: 'Rea Scratch Book (edited)', description: 'Edited during the capture.' });
  const sp = await api('POST', '/api/pages', { book_id: created.id, name: 'Rea Scratch Page', markdown: 'Scratch page body.' });
  await api('GET', `/api/books/${created.id}`);
  if (sp?.id) await api('GET', `/api/pages/${sp.id}`);
  await api('DELETE', `/api/books/${created.id}`);
  await api('GET', `/api/books/${created.id}`);
}
await api('GET', '/api/recycle-bin');
await api('GET', '/api/books');
await settle(500);
await context.close(); // flushes the HAR
if (browser) await browser.close();
fs.writeFileSync(path.join(DIR, 'capture-calls.json'), JSON.stringify(calls, null, 1));
log(`HAR written to ${HAR}; ${calls.length} scripted calls`);
console.log(HAR);
