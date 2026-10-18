// Drive the showcase Directus Data Studio with Chromium via playwright-core and record a HAR with bodies.
// Login through /admin/login (the Data Studio uses session mode: an httpOnly session cookie, no token in page storage),
// visit the main modules, then a scripted read/write/read sequence through fetch from inside the page against the REST
// API at the root. JSON filters are sent percent-encoded so every recorded URL is a valid RFC 3986 URI.
import { chromium } from 'playwright-core';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

const BASE = process.env.BASE_URL || 'http://127.0.0.1:3223';
const DIR = process.env.CAPTURE_DIR || path.join(os.homedir(), 'capture', 'directus');
const HAR = process.env.HAR_PATH || path.join(DIR, 'directus.full.har');
const EXE = process.env.CHROMIUM_PATH || '/snap/bin/chromium';
const EMAIL = 'rea-admin@example.com';
const admin = Object.fromEntries(fs.readFileSync(path.join(DIR, '.admin'), 'utf8').split('\n').filter((l) => l.includes('='))
  .map((l) => { const i = l.indexOf('='); return [l.slice(0, i), l.slice(i + 1)]; }));
const ids = JSON.parse(fs.readFileSync(path.join(DIR, 'seed-ids.json'), 'utf8'));
const log = (m) => console.error(`[capture] ${m}`);
const enc = (o) => encodeURIComponent(JSON.stringify(o));

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
const api = async (method, p, body) => {
  const res = await page.evaluate(async ({ method, p, body }) => {
    const r = await fetch(p, { method, credentials: 'same-origin', headers: { 'content-type': 'application/json', accept: 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body) });
    return { status: r.status, text: await r.text() };
  }, { method, p, body });
  log(`${method} ${p.split('?')[0]} -> ${res.status}`);
  try { return JSON.parse(res.text); } catch { return null; }
};

// --- login through the Data Studio ---
await visit('/admin/login', 1000);
await page.fill('input[type="email"]', EMAIL);
await page.fill('input[type="password"]', admin.ADMIN_PASSWORD);
await Promise.all([page.waitForURL((u) => !u.pathname.startsWith('/admin/login'), { timeout: 45000 }), page.click('button[type="submit"]')]);
await settle(2000);
log(`logged in, landed on ${new URL(page.url()).pathname}`);
// Directus 11 asks an admin to register a project owner (BSL 1.1 compliance); registering would call out to directus.io,
// so the capture answers "Remind Later", as a person evaluating the instance would.
const dismissOwner = async () => {
  const later = page.getByRole('button', { name: 'Remind Later' });
  if (await later.count() && await later.first().isVisible()) { await later.first().click(); await settle(800); log('owner dialog: Remind Later'); }
};
await dismissOwner();

const crew = ids.crew_rota; const prov = ids.provisions;
// --- main modules (UI traffic), navigated client-side so the Data Studio bootstraps once instead of on every page ---
const nav = async (href, ms = 1500) => {
  log(`nav ${href}`);
  const link = page.locator(`a[href="${href}"]`).first();
  if (await link.count()) {
    await link.click();
    await page.waitForURL((u) => u.pathname.startsWith(href), { timeout: 15000 }).catch(() => {});
  }
  if (!new URL(page.url()).pathname.startsWith(href)) {
    log(`  no link for ${href}, loading it`); await page.goto(`${BASE}${href}`, { waitUntil: 'domcontentloaded' }); await settle(ms); await dismissOwner();
  }
  await settle(ms);
};
await nav('/admin/content/provisions');
const row = page.locator('tbody tr').nth(1);
if (await row.count()) { await row.click(); await page.waitForURL(/\/admin\/content\/provisions\/\d+/, { timeout: 15000 }).catch(() => {}); await settle(1500); log(`opened ${new URL(page.url()).pathname}`); }
await nav('/admin/users');
await nav('/admin/files');
await nav('/admin/insights');
await nav(`/admin/insights/${ids.dashboards['Depot Overview']}`);
await nav('/admin/settings');
await nav('/admin/settings/data-model');
await nav('/admin/settings/flows');

// --- scripted API sequence from inside the page ---
await api('GET', '/server/info');
await api('GET', '/users/me?fields=id,first_name,last_name,email,title,location');
await api('GET', '/collections/crew_rota');
await api('GET', '/collections/provisions');
await api('GET', '/fields/crew_rota');
await api('GET', '/fields/provisions/storage_bay');
await api('GET', '/items/crew_rota?fields=*&sort=id');
await api('GET', `/items/crew_rota/${crew['Ada Finch']}`);
await api('GET', `/items/crew_rota/${crew['Marisol Okonkwo-Reyes']}`);
await api('GET', '/items/provisions?fields=*&sort=id');
await api('GET', `/items/provisions/${prov['Pale Meridian Tea']}`);
await api('GET', `/items/provisions/${prov['Northern Quill Ink']}`);
await api('GET', `/items/provisions?filter=${enc({ category: { _eq: 'Lamp' } })}`);
await api('GET', '/items/crew_rota?search=Blue%20Heron&fields=name,role_title,watch_station');
await api('GET', '/items/provisions?sort=-quantity&limit=2&fields=title,quantity,storage_bay');
await api('GET', '/folders');
await api('GET', `/folders/${ids.folders['Granite Ledger Scans']}`);
await api('GET', `/files/${ids.files['Granite Ledger tally GL-2291']}`);
await api('GET', '/roles?fields=id,name,description');
await api('GET', `/roles/${ids.roles['Rota Editors']}`);
await api('GET', `/policies/${ids.policies['Rota Editing']}`);
await api('GET', `/permissions?filter=${enc({ policy: { _eq: ids.policies['Rota Editing'] } })}&fields=collection,action`);
await api('GET', '/users?fields=id,first_name,last_name,email,title,location');
await api('GET', `/users/${ids.users['ada.finch@example.com']}`);
await api('GET', `/presets/${ids.presets['Night shift crew']}`);
await api('GET', `/dashboards/${ids.dashboards['Depot Overview']}`);
await api('GET', `/panels/${ids.panels['Provisions on hand']}`);
await api('GET', `/flows/${ids.flows['Announce new provisions']}`);
await api('GET', `/comments/${ids.comments['night watch swap']}`);
// write path on a scratch provision: create, edit, re-read, delete, re-read, count
const created = await api('POST', '/items/provisions', { title: 'Rea Scratch Provision', category: 'Food', quantity: 1, unit: 'crate',
  storage_bay: 'Bay Z9', supplier_note: 'Written during the capture.' });
const sid = created?.data?.id;
if (sid) {
  await api('PATCH', `/items/provisions/${sid}`, { quantity: 2, supplier_note: 'Edited during the capture.' });
  await api('GET', `/items/provisions/${sid}`);
  await api('DELETE', `/items/provisions/${sid}`);
  await api('GET', `/items/provisions/${sid}`);
}
await api('GET', `/items/provisions?aggregate=${enc({ count: '*' })}`);
await settle(500);
await context.close(); // flushes the HAR
if (browser) await browser.close();
log(`HAR written to ${HAR}`);
console.log(HAR);
