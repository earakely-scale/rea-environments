// Drive the showcase listmonk admin with Chromium via playwright-core and record a HAR with bodies.
// Login through the admin login form, visit the main admin pages by clicking the Vue router links, then a scripted
// read/write/read sequence through fetch from inside the page (the session cookie is carried automatically). Nothing is sent:
// no campaign is started and no test message is requested.
import { chromium } from 'playwright-core';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

const BASE = process.env.BASE_URL || 'http://127.0.0.1:3214';
const DIR = process.env.CAPTURE_DIR || path.join(os.homedir(), 'capture', 'listmonk');
const HAR = process.env.HAR_PATH || path.join(DIR, 'listmonk.full.har');
const EXE = process.env.CHROMIUM_PATH || '/snap/bin/chromium';
const admin = Object.fromEntries(fs.readFileSync(path.join(DIR, '.admin'), 'utf8').split('\n').filter((l) => l.includes('='))
  .map((l) => { const i = l.indexOf('='); return [l.slice(0, i), l.slice(i + 1)]; }));
const USER = 'rea-admin'; const PASS = admin.LISTMONK_ADMIN_PASSWORD;
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
// In-app navigation: a visible router link if there is one, else the app's own Vue router, else a page load.
const nav = async (href) => {
  const link = page.locator(`a[href="${href}"]`).first();
  if (await link.count() && await link.isVisible().catch(() => false)) { log(`click ${href}`); await link.click(); await settle(1500); return; }
  const pushed = await page.evaluate(async (href) => {
    const el = [document.querySelector('#app'), ...document.querySelectorAll('body *')].find((e) => e && (e.__vue__ || e.__vue_app__));
    const router = el?.__vue_app__?.config?.globalProperties?.$router || el?.__vue__?.$router;
    if (!router) return false;
    await router.push(href.replace(/^\/admin/, '') || '/').catch(() => {});
    return true;
  }, href);
  if (pushed) { log(`router ${href}`); await settle(1500); } else await visit(href, 1500);
};
const api = async (method, p, body) => {
  const res = await page.evaluate(async ({ method, p, body }) => {
    const headers = { accept: 'application/json' };
    if (body !== undefined) headers['content-type'] = 'application/json';
    const r = await fetch(p, { method, headers, body: body === undefined ? undefined : JSON.stringify(body), credentials: 'same-origin' });
    return { status: r.status, text: await r.text() };
  }, { method, p, body });
  log(`${method} ${p} -> ${res.status}`);
  try { return JSON.parse(res.text); } catch { return null; }
};
const q = (s) => encodeURIComponent(s);

// --- login through the admin form ---
await visit('/admin/login', 500);
await page.fill('input[name="username"]', USER);
await page.fill('input[name="password"]', PASS);
await Promise.all([page.waitForURL((u) => !u.pathname.startsWith('/admin/login'), { timeout: 45000 }), page.click('button[type="submit"]')]);
await settle(2500);
log(`logged in, landed on ${new URL(page.url()).pathname}`);

const L = ids.lists; const S = ids.subscribers; const C = ids.campaigns; const T = ids.templates;

// --- main admin pages, inside the single-page app ---
for (const p of ['/admin/lists', '/admin/subscribers', `/admin/subscribers/${S['Ada Finch']}`, '/admin/campaigns',
  `/admin/campaigns/${C['Winter Rota Briefing']}`, '/admin/campaigns/templates', '/admin/campaigns/media', '/admin/users',
  '/admin/users/roles/users', '/admin/users/roles/lists']) {
  await nav(p);
}

// --- scripted API sequence from inside the page: collections, then every seeded object by id ---
await api('GET', '/api/lists?page=1&per_page=20');
for (const id of Object.values(L)) await api('GET', `/api/lists/${id}`);
await api('GET', '/api/subscribers?page=1&per_page=20');
for (const id of Object.values(S)) await api('GET', `/api/subscribers/${id}`);
await api('GET', `/api/subscribers/${S['Ada Finch']}/export`);
await api('GET', `/api/subscribers/${S['Rui Castellanos']}/export`);
await api('GET', `/api/subscribers/${S['Tomas Vey']}/activity`);
await api('GET', `/api/subscribers/${S['Marisol Okonkwo-Reyes']}/activity`);
await api('GET', `/api/subscribers/${S['Mina Okafor']}/bounces`);
await api('GET', `/api/campaigns?page=1&per_page=20&no_body=true`);
for (const id of Object.values(C)) await api('GET', `/api/campaigns/${id}`);
await api('GET', '/api/templates?no_body=true');
for (const id of Object.values(T)) await api('GET', `/api/templates/${id}`);
await api('GET', '/api/users');
for (const id of [...Object.values(ids.users), 1]) await api('GET', `/api/users/${id}`);
await api('GET', '/api/roles/users');
await api('GET', '/api/roles/lists');
await api('GET', '/api/media');
for (const id of Object.values(ids.media)) await api('GET', `/api/media/${id}`);
await api('GET', '/api/bounces?page=1&per_page=20');
await api('GET', '/api/public/lists');
await api('GET', '/api/dashboard/counts');
await api('GET', '/api/about');
await api('GET', '/api/import/subscribers');
// searches and filters
await api('GET', `/api/subscribers?page=1&per_page=20&query=${q("subscribers.attribs->>'city' = 'Granite Point'")}`);
await api('GET', `/api/subscribers?page=1&per_page=20&list_id=${L['Blue Heron Kitchen Regulars']}`);
await api('GET', `/api/subscribers?page=1&per_page=20&query=${q("subscribers.status = 'blocklisted'")}`);
await api('GET', `/api/campaigns?page=1&per_page=20&no_body=true&query=${q('granite')}`);
await api('GET', `/api/lists?page=1&per_page=20&query=${q('depot')}`);
// write path on a scratch list: create, edit, re-read, delete, re-read
const created = await api('POST', '/api/lists', { name: 'Rea scratch list', type: 'private', optin: 'single', tags: ['scratch'], description: 'Scratch list written during the capture.' });
const sl = created?.data;
if (sl?.id) {
  const upd = await api('PUT', `/api/lists/${sl.id}`, { name: 'Rea scratch list (edited)', type: 'private', optin: 'single', tags: ['scratch', 'edited'], description: 'Edited scratch list.' });
  log(`scratch list edited -> ${upd?.data?.name}`);
  await api('GET', `/api/lists/${sl.id}`);
  await api('DELETE', `/api/lists/${sl.id}`);
  await api('GET', `/api/lists/${sl.id}`);
}
await api('GET', '/api/lists?page=1&per_page=20');
await settle(500);
await context.close(); // flushes the HAR
if (browser) await browser.close();
log(`HAR written to ${HAR}`);
console.log(HAR);
