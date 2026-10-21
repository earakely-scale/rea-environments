// Drive the showcase Homebox web app with Chromium via playwright-core and record a HAR with bodies.
// Login through the web UI, visit the main pages, then a scripted read sequence through fetch from inside the page and writes
// on two scratch items, each read back at once (record_writes.mjs); the web app authenticates with an httpOnly session cookie,
// which fetch carries automatically.
import { chromium } from 'playwright-core';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { recordWrites } from '../record_writes.mjs'; // shipped to ~/capture/ next to scope_har.py

const BASE = process.env.BASE_URL || 'http://127.0.0.1:3208';
const DIR = process.env.CAPTURE_DIR || path.join(os.homedir(), 'capture', 'homebox');
const HAR = process.env.HAR_PATH || path.join(DIR, 'homebox.full.har');
const EXE = process.env.CHROMIUM_PATH || '/snap/bin/chromium';
const admin = Object.fromEntries(fs.readFileSync(path.join(DIR, '.admin'), 'utf8').split('\n').filter((l) => l.includes('='))
  .map((l) => { const i = l.indexOf('='); return [l.slice(0, i), l.slice(i + 1)]; }));
const EMAIL = 'rea-admin@example.test'; const PASS = admin.HOMEBOX_ADMIN_PASSWORD;
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
// Client-side navigation through the Nuxt app's own router, so the app does not re-run its boot requests.
const nav = async (p, ms) => {
  const ok = await page.evaluate(async (href) => {
    const app = document.querySelector('#__nuxt')?.__vue_app__;
    const router = app?.config?.globalProperties?.$router;
    if (!router) return false;
    await router.push(href); return true;
  }, p).catch(() => false);
  log(`nav ${p}${ok ? '' : ' (router not found, full load)'}`);
  if (!ok) await page.goto(`${BASE}${p}`, { waitUntil: 'domcontentloaded' });
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
await visit('/', 1000);
await page.waitForSelector('input[type="password"]');
const emailBox = page.locator('input[type="email"], input[name="email"], input[autocomplete="email"], input[type="text"]').first();
await emailBox.fill(EMAIL);
await page.fill('input[type="password"]', PASS);
await page.locator('button[type="submit"]').first().click();
await page.waitForURL((u) => u.pathname !== '/', { timeout: 45000 });
await settle(2500);
log(`logged in, landed on ${new URL(page.url()).pathname}`);

const L = ids.locations; const I = ids.items; const T = ids.tags;
const depot = L['Saltmarsh Depot']; const lens = I['Fresnel Lens Polishing Kit']; const gauge = I['Tide Gauge Logger'];

// --- main pages (UI traffic) ---
for (const p of ['/locations', `/location/${depot}`, '/items', `/item/${lens}`, `/item/${gauge}/maintenance`, '/tags',
  `/tag/${T['Calibration Due']}`, '/maintenance', '/templates', '/collection', '/profile', '/home']) {
  await nav(p, 1500);
}

// --- scripted API sequence from inside the page ---
await api('GET', '/api/v1/users/self');
await api('GET', '/api/v1/groups');
await api('GET', '/api/v1/groups/statistics');
await api('GET', '/api/v1/groups/statistics/locations');
await api('GET', '/api/v1/groups/statistics/tags');
await api('GET', '/api/v1/entity-types');
await api('GET', '/api/v1/tags');
for (const id of Object.values(T)) await api('GET', `/api/v1/tags/${id}`);
const list = await api('GET', '/api/v1/entities?page=1&pageSize=50');
for (const id of Object.values(L)) await api('GET', `/api/v1/entities/${id}`);
for (const id of Object.values(I)) await api('GET', `/api/v1/entities/${id}`);
await api('GET', `/api/v1/entities/${lens}/path`);
await api('GET', `/api/v1/entities/${I['Copper Stockpot 40 L']}/path`);
await api('GET', `/api/v1/entities/${gauge}/maintenance?status=both`);
await api('GET', `/api/v1/entities/${I['Copper Stockpot 40 L']}/maintenance?status=both`);
await api('GET', '/api/v1/maintenance?status=both');
await api('GET', '/api/v1/entities/tree');
await api('GET', '/api/v1/entities?q=lens');
await api('GET', `/api/v1/entities?tags=${T['Calibration Due']}`);
await api('GET', '/api/v1/entities/fields');
await api('GET', `/api/v1/entities/fields/values?field=${encodeURIComponent('Lens Grade')}`);
const counter = list?.items?.find((e) => e.name === 'Quarry Tally Counter');
if (counter?.assetId) await api('GET', `/api/v1/assets/${counter.assetId}`);
await api('GET', '/api/v1/templates');
for (const id of Object.values(ids.templates)) await api('GET', `/api/v1/templates/${id}`);

// --- writes on two scratch items (PUT replaces the whole entity, so the update sends every field) ---
const workshop = L['Copperfield Annex Workshop'];
await recordWrites(api, {
  collection: '/api/v1/entities', list: '/api/v1/entities?page=1&pageSize=50', item: (id) => `/api/v1/entities/${id}`,
  id: (e) => e?.id, updateMethod: 'PUT',
  create: (n) => ({ name: `Rea scratch item ${n}`, description: `Scratch item ${n} written during the capture.`,
    entityTypeId: ids.entity_types.Item, parentId: workshop, quantity: n }),
  update: (n, created) => ({ id: created.id, name: `Rea scratch item ${n} (edited)`, description: `Edited scratch item ${n}.`,
    quantity: n + 2, entityTypeId: ids.entity_types.Item, parentId: workshop, tagIds: [], fields: [] }),
});
await settle(500);
await context.close(); // flushes the HAR
if (browser) await browser.close();
log(`HAR written to ${HAR}`);
console.log(HAR);
