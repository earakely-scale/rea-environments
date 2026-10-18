// Drive the showcase Baserow with Chromium via playwright-core and record a HAR with bodies.
// Login through the web UI, visit the main pages (workspace dashboard, the three tables, a row, the extra views, admin
// users), then a scripted read/write/read sequence through fetch from inside the page. Baserow's web UI keeps its JWT
// access token in its Vuex store (refresh token in a cookie); the script reads the access token from the store in the
// page and sends it as the `Authorization: JWT ...` header, exactly like the UI does. Headers are stripped by scoping.
import { chromium } from 'playwright-core';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

const BASE = process.env.BASE_URL || 'http://127.0.0.1:3204';
const DIR = process.env.CAPTURE_DIR || path.join(os.homedir(), 'capture', 'baserow');
const HAR = process.env.HAR_PATH || path.join(DIR, 'baserow.full.har');
const EXE = process.env.CHROMIUM_PATH || '/snap/bin/chromium';
const admin = Object.fromEntries(fs.readFileSync(path.join(DIR, '.admin'), 'utf8').split('\n').filter((l) => l.includes('='))
  .map((l) => { const i = l.indexOf('='); return [l.slice(0, i), l.slice(i + 1)]; }));
const ids = JSON.parse(fs.readFileSync(path.join(DIR, 'seed-ids.json'), 'utf8'));
const log = (m) => console.error(`[capture] ${m}`);

const launchOpts = { executablePath: EXE, headless: true, args: ['--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu'] };
const harOpts = { recordHar: { path: HAR, content: 'embed', mode: 'full' } };
const browser = await chromium.launch(launchOpts);
const context = await browser.newContext({ ...harOpts, viewport: { width: 1440, height: 900 } });
const page = await context.newPage();
page.setDefaultTimeout(45000);

const settle = async (ms = 1500) => { await page.waitForLoadState('networkidle', { timeout: 20000 }).catch(() => {}); await page.waitForTimeout(ms); };
const visit = async (p, ms) => { await page.goto(`${BASE}${p}`, { waitUntil: 'domcontentloaded' }); await settle(ms); log(`visit ${p} -> ${new URL(page.url()).pathname}`); };
const token = async () => page.evaluate(() => window.useNuxtApp().$store.getters['auth/token']);
const api = async (method, p, body) => {
  const tok = await token();
  const res = await page.evaluate(async ({ method, p, body, tok }) => {
    const r = await fetch(p, { method, headers: { 'content-type': 'application/json', accept: 'application/json', authorization: `JWT ${tok}` }, body: body === undefined ? undefined : JSON.stringify(body) });
    return { status: r.status, text: await r.text() };
  }, { method, p, body, tok });
  log(`${method} ${p} -> ${res.status} (${res.text.length} B)`);
  try { return JSON.parse(res.text); } catch { return null; }
};

// --- login through the web UI ---
await visit('/login', 2000);
await page.fill('input[type="email"]', 'rea-admin@example.test');
await page.fill('input[type="password"]', admin.BASEROW_ADMIN_PASSWORD);
await page.click('button:has-text("Login")');
await page.waitForURL((u) => !u.pathname.startsWith('/login'), { timeout: 45000 });
await settle(2500);
log(`logged in, landed on ${new URL(page.url()).pathname}`);

const W = ids.workspace; const D = ids.database; const D2 = ids.database2; const T = ids.tables; const V = ids.views;
const S = T['Stations']; const K = T['Keepers']; const O = T['Supply Orders'];
const R = ids.rows; const F = ids.fields;

// --- main UI pages ---
for (const [p, ms] of [
  [`/workspace/${W}`, 2000],
  [`/database/${D}/table/${K}/${V['Keepers default grid']}`, 2500],
  [`/database/${D}/table/${K}/${V['Certified keepers']}`, 2000],
  [`/database/${D}/table/${O}/${V['Supply Orders default grid']}`, 2500],
  [`/database/${D}/table/${S}/${V['Stations default grid']}`, 2500],
  [`/database/${D}/table/${S}/${V['Station cards']}`, 2000],
  ['/admin/users', 2000],
]) await visit(p, ms);

// --- scripted API sequence from inside the page ---
await api('GET', '/api/workspaces/');
await api('GET', '/api/applications/');
await api('GET', `/api/applications/${D}/`);
await api('GET', `/api/applications/${D2}/`);
await api('GET', `/api/applications/workspace/${W}/`);
await api('GET', `/api/workspaces/users/workspace/${W}/`);
await api('GET', `/api/database/tables/database/${D}/`);
for (const t of [O, K, S]) await api('GET', `/api/database/tables/${t}/`);
await api('GET', `/api/database/fields/table/${K}/`);
await api('GET', `/api/database/fields/${F['Stations']['Lamp']}/`);
await api('GET', `/api/database/fields/${F['Keepers']['Rank']}/`);
await api('GET', `/api/database/fields/${F['Supply Orders']['Supplier']}/`);
await api('GET', `/api/database/fields/${F['Supply Orders']['Supplier']}/unique_row_values/`);
await api('GET', `/api/database/rows/table/${K}/?user_field_names=true`);
for (const [t, rows] of [[O, R['Supply Orders']], [K, R['Keepers']], [S, R['Stations']]]) {
  for (const rid of Object.values(rows)) await api('GET', `/api/database/rows/table/${t}/${rid}/?user_field_names=true`);
}
await api('GET', `/api/database/rows/table/${K}/${R['Keepers']['Ada Finch']}/history/`);
await api('GET', `/api/database/rows/table/${K}/?user_field_names=true&search=heron`);
await api('GET', `/api/database/rows/table/${O}/?user_field_names=true&filter__field_${F['Supply Orders']['Stage']}__single_select_equal=${ids.options['Supply Orders.Stage']['Requested']}`);
await api('GET', `/api/database/rows/table/${K}/?user_field_names=true&order_by=${encodeURIComponent('-Shifts per month')}&size=3`);
await api('GET', `/api/database/rows/names/?table__${S}=${Object.values(R['Stations']).join(',')}`);
await api('GET', `/api/database/views/table/${K}/`);
await api('GET', `/api/database/views/${V['Request supplies']}/`);
await api('GET', `/api/database/views/${V['Certified keepers']}/`);
await api('GET', `/api/database/views/${V['Certified keepers']}/filters/`);
await api('GET', `/api/database/views/${V['Certified keepers']}/sortings/`);
await api('GET', `/api/database/views/filter/${ids.filters['Open orders']}/`);
await api('GET', `/api/database/views/grid/${V['Open orders']}/`);
await api('GET', `/api/database/views/gallery/${V['Station cards']}/`);
await api('GET', '/api/admin/users/');
await api('GET', `/api/search/workspace/${W}/?query=heron`);
await api('GET', '/api/trash/');
// open one row in the UI's row modal (row, its history) after the scripted reads of the same routes
await visit(`/database/${D}/table/${K}/${V['Keepers default grid']}/row/${R['Keepers']['Mina Okafor']}`, 2500);
// write path on a scratch supply order: create, edit, re-read, delete, re-read, list again
const created = await api('POST', `/api/database/rows/table/${O}/?user_field_names=true`, { 'Order code': 'SO-9001', Item: 'Scratch lantern wicks', Quantity: '3', Supplier: 'Copperfield Annex Stores' });
if (created?.id) {
  await api('PATCH', `/api/database/rows/table/${O}/${created.id}/?user_field_names=true`, { Item: 'Scratch lantern wicks (edited)', Quantity: '5' });
  await api('GET', `/api/database/rows/table/${O}/${created.id}/?user_field_names=true`);
  await api('DELETE', `/api/database/rows/table/${O}/${created.id}/`);
  await api('GET', `/api/database/rows/table/${O}/${created.id}/?user_field_names=true`);
}
await api('GET', `/api/database/rows/table/${O}/?user_field_names=true`);
await settle(500);
await context.close(); // flushes the HAR
await browser.close();
log(`HAR written to ${HAR}`);
console.log(HAR);
