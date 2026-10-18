// Drive the showcase Paperless-ngx UI with Chromium via playwright-core and record a HAR with bodies.
// Login through the Django/allauth form, visit the main Angular pages, then a scripted read/write/read sequence through
// fetch from inside the page: the session cookie is carried automatically, writes send the csrftoken cookie as X-CSRFToken,
// and every call sends the same versioned Accept header the UI uses (application/json; version=9).
import { chromium } from 'playwright-core';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

const BASE = process.env.BASE_URL || 'http://127.0.0.1:3213';
const DIR = process.env.CAPTURE_DIR || path.join(os.homedir(), 'capture', 'paperless');
const HAR = process.env.HAR_PATH || path.join(DIR, 'paperless.full.har');
const EXE = process.env.CHROMIUM_PATH || '/snap/bin/chromium';
const admin = Object.fromEntries(fs.readFileSync(path.join(DIR, '.admin'), 'utf8').split('\n').filter((l) => l.includes('='))
  .map((l) => { const i = l.indexOf('='); return [l.slice(0, i), l.slice(i + 1)]; }));
const USER = 'rea-admin'; const PASS = admin.PAPERLESS_ADMIN_PASSWORD;
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
    const csrf = (document.cookie.split('; ').find((c) => c.startsWith('csrftoken=')) || '').split('=')[1] || '';
    const headers = { accept: 'application/json; version=9' };
    if (body !== undefined) headers['content-type'] = 'application/json';
    if (method !== 'GET') headers['X-CSRFToken'] = csrf;
    const r = await fetch(p, { method, headers, body: body === undefined ? undefined : JSON.stringify(body), credentials: 'same-origin' });
    return { status: r.status, text: await r.text() };
  }, { method, p, body });
  log(`${method} ${p} -> ${res.status}`);
  try { return JSON.parse(res.text); } catch { return null; }
};

// --- login through the UI form ---
await visit('/accounts/login/', 500);
await page.fill('input[name="login"]', USER);
await page.fill('input[name="password"]', PASS);
await Promise.all([page.waitForURL((u) => !u.pathname.startsWith('/accounts/login'), { timeout: 45000 }), page.click('button[type="submit"]')]);
await settle(3000);
log(`logged in, landed on ${new URL(page.url()).pathname}`);

const D = ids.documents; const docId = (t) => D[t];
const firstDoc = docId('Granite Ledger Quarterly Stone Count');

// --- main UI pages: navigate inside the single-page app (sidebar links) so the app shell does not reload on every page ---
const nav = async (href) => {
  const link = page.locator(`a[href="${href}"]`).first();
  if (await link.count() && await link.isVisible().catch(() => false)) { log(`click ${href}`); await link.click(); await settle(1500); }
  else await visit(href, 1500);
};
for (const p of ['/documents', `/documents/${firstDoc}/details`, '/tags', '/correspondents', '/documenttypes', '/storagepaths',
  '/customfields', '/workflows', '/mail', '/usersgroups']) {
  await nav(p);
}

// --- scripted API sequence from inside the page: collections, then every seeded object by id ---
await api('GET', '/api/documents/?page=1&page_size=25&ordering=-created&truncate_content=true');
for (const id of Object.values(D)) await api('GET', `/api/documents/${id}/`);
await api('GET', `/api/documents/${firstDoc}/notes/`);
await api('GET', `/api/documents/${docId('Lighthouse Rota Winter Handover')}/notes/`);
await api('GET', `/api/documents/${docId('Saltmarsh Depot Lamp Oil Delivery')}/notes/`);
await api('GET', `/api/documents/${docId('Blue Heron Kitchen Kelp Broth Invoice')}/metadata/`);
await api('GET', `/api/documents/${docId('Copperfield Annex Lease Renewal')}/history/`);
for (const [coll, key] of [['tags', 'tags'], ['correspondents', 'correspondents'], ['document_types', 'document_types'], ['storage_paths', 'storage_paths'],
  ['custom_fields', 'custom_fields'], ['saved_views', 'saved_views'], ['groups', 'groups'], ['users', 'users'], ['mail_accounts', 'mail_accounts'],
  ['mail_rules', 'mail_rules'], ['workflows', 'workflows']]) {
  await api('GET', `/api/${coll}/?page=1&page_size=50`);
  for (const id of Object.values(ids[key])) await api('GET', `/api/${coll}/${id}/`);
}
await api('GET', '/api/config/');
await api('GET', '/api/profile/');
await api('GET', '/api/statistics/');
// searches and filters
await api('GET', '/api/documents/?query=lamp%20oil&page_size=10&truncate_content=true');
await api('GET', `/api/documents/?tags__id__all=${ids.tags['Winter Rota']}&page_size=10&truncate_content=true`);
await api('GET', `/api/documents/?correspondent__id__in=${ids.correspondents['Saltmarsh Depot Stores']}&ordering=title&truncate_content=true`);
await api('GET', '/api/search/?query=heron');
// write path on a scratch tag: create, edit, re-read, delete, re-read; and a scratch note on one document
const created = await api('POST', '/api/tags/', { name: 'Rea scratch tag', color: '#a0a0a0', match: '', matching_algorithm: 0, is_inbox_tag: false });
if (created?.id) {
  const upd = await api('PATCH', `/api/tags/${created.id}/`, { name: 'Rea scratch tag (edited)', color: '#5a5a5a' });
  log(`scratch tag edited -> ${upd?.name}`);
  await api('GET', `/api/tags/${created.id}/`);
  await api('DELETE', `/api/tags/${created.id}/`);
  await api('GET', `/api/tags/${created.id}/`);
}
const annex = docId('Copperfield Annex Lease Renewal');
const notes = await api('POST', `/api/documents/${annex}/notes/`, { note: 'Scratch note written during the capture.' });
const scratch = Array.isArray(notes) ? notes.find((n) => n.note?.startsWith('Scratch note')) : null;
if (scratch) await api('DELETE', `/api/documents/${annex}/notes/?id=${scratch.id}`);
await api('GET', '/api/tags/?page=1&page_size=50');
await settle(500);
await context.close(); // flushes the HAR
if (browser) await browser.close();
log(`HAR written to ${HAR}`);
console.log(HAR);
