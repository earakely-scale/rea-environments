// Drive the showcase Grocy with Chromium via playwright-core and record a HAR with bodies.
// Login through the web form, visit the main pages, then a scripted read/write/read sequence through fetch from inside
// the page. Grocy's web UI calls /api with its session cookie, so no API key is involved. Query brackets are sent
// percent-encoded (query%5B%5D) because the HAR schema requires RFC 3986 URIs.
import { chromium } from 'playwright-core';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

const BASE = process.env.BASE_URL || 'http://127.0.0.1:3222';
const DIR = process.env.CAPTURE_DIR || path.join(os.homedir(), 'capture', 'grocy');
const HAR = process.env.HAR_PATH || path.join(DIR, 'grocy.full.har');
const EXE = process.env.CHROMIUM_PATH || '/snap/bin/chromium';
const admin = Object.fromEntries(fs.readFileSync(path.join(DIR, '.admin'), 'utf8').split('\n').filter((l) => l.includes('='))
  .map((l) => { const i = l.indexOf('='); return [l.slice(0, i), l.slice(i + 1)]; }));
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

const settle = async (ms = 1200) => { await page.waitForLoadState('networkidle', { timeout: 20000 }).catch(() => {}); await page.waitForTimeout(ms); };
const visit = async (p, ms) => { log(`visit ${p}`); await page.goto(`${BASE}${p}`, { waitUntil: 'domcontentloaded' }); await settle(ms); };
const api = async (method, p, body) => {
  const res = await page.evaluate(async ({ method, p, body }) => {
    const r = await fetch(p, { method, headers: { 'content-type': 'application/json', accept: 'application/json' }, body: body === undefined ? undefined : JSON.stringify(body) });
    return { status: r.status, text: await r.text() };
  }, { method, p: `/api${p}`, body });
  log(`${method} /api${p} -> ${res.status}`);
  try { return JSON.parse(res.text); } catch { return null; }
};

// --- login through the web form (the page base64-encodes the password into a hidden field) ---
await visit('/login', 500);
await page.fill('#username', 'rea-admin');
await page.fill('#password_input', admin.GROCY_ADMIN_PASSWORD);
await Promise.all([page.waitForURL((u) => !u.pathname.startsWith('/login'), { timeout: 45000 }), page.click('#login-button')]);
await settle(1500);
log(`logged in, landed on ${new URL(page.url()).pathname}`);

const P = ids.products; const L = ids.locations; const Q = ids.quantity_units; const C = ids.chores; const B = ids.batteries;
// --- main pages (UI traffic) ---
for (const p of ['/stockoverview', '/products', `/product/${P['Heron Rye Crackers']}`, '/locations', '/quantityunits', '/shoppinglist',
  '/choresoverview', '/batteriesoverview', '/tasks', '/recipes', '/equipment', '/stockjournal']) {
  await visit(p, 1200);
}

// --- scripted API sequence from inside the page ---
await api('GET', '/system/info');
await api('GET', '/objects/products');
await api('GET', `/objects/products/${P['Smoked Kelp Broth']}`);
await api('GET', `/objects/products/${P['Lamp Wick Bundle']}`);
await api('GET', `/stock/products/${P['Copperfield Lamp Oil']}`);
await api('GET', `/stock/products/${P['Smoked Kelp Broth']}`);
await api('GET', `/stock/products/${P['Granite Salt Flakes']}/entries`);
await api('GET', `/stock/products/${P['Heron Rye Crackers']}/locations`);
await api('GET', '/stock');
await api('GET', `/stock/locations/${L['Copperfield Annex Larder']}/entries`);
await api('GET', '/objects/locations');
await api('GET', `/objects/locations/${L['Granite Ledger Lockers']}`);
await api('GET', '/objects/quantity_units');
await api('GET', `/objects/quantity_units/${Q.Crate}`);
await api('GET', '/objects/product_groups');
await api('GET', `/objects/product_groups/${ids.product_groups['Lamp Supplies']}`);
await api('GET', '/objects/shopping_locations');
await api('GET', `/objects/shopping_locations/${ids.shopping_locations['Blue Heron Kitchen Market']}`);
await api('GET', '/objects/shopping_lists');
await api('GET', `/objects/shopping_lists/${ids.shopping_lists['Lighthouse Rota Night Shift']}`);
await api('GET', `/objects/shopping_list?query%5B%5D=shopping_list_id=${ids.shopping_lists['Saltmarsh Depot Restock']}`);
await api('GET', `/objects/shopping_list/${ids.shopping_list['Two crates before the winter shift plan starts']}`);
await api('GET', '/chores');
await api('GET', `/chores/${C['Polish the Lighthouse Lens']}`);
await api('GET', `/objects/chores/${C['Rotate the Kelp Barrels']}`);
await api('GET', '/batteries');
await api('GET', `/batteries/${B['Foghorn Remote Cell']}`);
await api('GET', `/objects/batteries/${B['Tide Gauge Pack']}`);
await api('GET', '/tasks');
await api('GET', `/objects/tasks/${ids.tasks['Recount the Granite Ledger crates']}`);
await api('GET', `/objects/task_categories/${ids.task_categories['Lamp Watch']}`);
await api('GET', '/objects/equipment');
await api('GET', `/objects/equipment/${ids.equipment['Copperfield Annex Dehydrator']}`);
await api('GET', `/objects/recipes/${ids.recipes['Tide-Table Kelp Stew']}`);
await api('GET', `/objects/recipes_pos?query%5B%5D=recipe_id=${ids.recipes['Tide-Table Kelp Stew']}`);
await api('GET', `/recipes/${ids.recipes['Tide-Table Kelp Stew']}/fulfillment`);
await api('GET', '/users');
await api('GET', '/user');
// searches and filters
await api('GET', `/objects/products?query%5B%5D=product_group_id=${ids.product_groups['Tide Rations']}&order=name:asc`);
await api('GET', '/objects/chores?query%5B%5D=name~Kelp');
await api('GET', '/objects/tasks?query%5B%5D=done=0&order=due_date:asc&limit=5');
// write path on a scratch product: create, edit, re-read, delete, re-read, list again
const created = await api('POST', '/objects/products', { name: 'Rea Scratch Product', description: 'Scratch product written during the capture.',
  location_id: L['Copperfield Annex Larder'], qu_id_purchase: Q.Piece, qu_id_stock: Q.Piece, qu_id_consume: Q.Piece, qu_id_price: Q.Piece });
const sid = created?.created_object_id;
if (sid) {
  await api('PUT', `/objects/products/${sid}`, { description: 'Edited scratch product description.' });
  await api('GET', `/objects/products/${sid}`);
  await api('DELETE', `/objects/products/${sid}`);
  await api('GET', `/objects/products/${sid}`);
}
await api('GET', '/objects/products');
await settle(500);
await context.close(); // flushes the HAR
if (browser) await browser.close();
log(`HAR written to ${HAR}`);
console.log(HAR);
