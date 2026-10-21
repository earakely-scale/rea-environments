// Drive the showcase Mealie web UI with Chromium via playwright-core and record a HAR with bodies.
// Login through the UI, a scripted read sequence through fetch from inside the page (first, so each tool's first record is a
// seeded object), the main UI pages, then writes on two scratch recipes, each read back at once. The UI keeps its JWT in the
// (non-httpOnly) cookie "mealie.access_token" and sends it as a bearer header; the scripted calls read the cookie in the page
// and do the same. Request headers and cookies are stripped by scope_har.py. Service workers are blocked (PWA).
import { chromium } from 'playwright-core';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { recordWrites } from '../record_writes.mjs'; // shipped to ~/capture/ next to scope_har.py

const BASE = process.env.BASE_URL || 'http://127.0.0.1:3212';
const DIR = process.env.CAPTURE_DIR || path.join(os.homedir(), 'capture', 'mealie');
const HAR = process.env.HAR_PATH || path.join(DIR, 'mealie.full.har');
const EXE = process.env.CHROMIUM_PATH || '/snap/bin/chromium';
const admin = Object.fromEntries(fs.readFileSync(path.join(DIR, '.admin'), 'utf8').split('\n').filter((l) => l.includes('='))
  .map((l) => { const i = l.indexOf('='); return [l.slice(0, i), l.slice(i + 1)]; }));
const ids = JSON.parse(fs.readFileSync(path.join(DIR, 'seed-ids.json'), 'utf8'));
const log = (m) => console.error(`[capture] ${m}`);

const launchOpts = { executablePath: EXE, headless: true, args: ['--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu'] };
const harOpts = { recordHar: { path: HAR, content: 'embed', mode: 'full' }, serviceWorkers: 'block' };
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
const api = async (method, p, body) => {
  const res = await page.evaluate(async ({ method, p, body }) => {
    const tok = decodeURIComponent((document.cookie.split('; ').find((c) => c.startsWith('mealie.access_token=')) || '').split('=').slice(1).join('='));
    const r = await fetch(p, { method, headers: { 'content-type': 'application/json', accept: 'application/json', authorization: `Bearer ${tok}` },
      body: body === undefined ? undefined : JSON.stringify(body) });
    return { status: r.status, text: await r.text() };
  }, { method, p, body });
  log(`${method} ${p} -> ${res.status} (${res.text.length} bytes)`);
  let json = null; try { json = JSON.parse(res.text); } catch {}
  return json;
};

// --- login through the web UI ---
await visit('/login', 1000);
await page.fill('#username', 'rea-admin@example.test');
await page.fill('#password', admin.MEALIE_ADMIN_PASSWORD);
await page.keyboard.press('Enter');
await page.waitForURL((u) => !u.pathname.startsWith('/login'), { timeout: 45000 });
await settle(2500);
log(`logged in, landed on ${new URL(page.url()).pathname}`);

// --- scripted read sequence from inside the page ---
const R = Object.keys(ids.recipes); const C = ids.categories; const TG = ids.tags; const TL = ids.tools; const SL = ids.shopping_lists;
await api('GET', '/api/app/about');
await api('GET', '/api/users/self');
await api('GET', '/api/groups/self');
await api('GET', '/api/households/self');
await api('GET', '/api/recipes?page=1&perPage=20&orderBy=name&orderDirection=asc');
for (const slug of ['granite-ledger-oat-bars', 'smoked-kelp-broth', 'lamp-watch-barley-stew', 'saltmarsh-samphire-hash', 'copperfield-ginger-tea']) await api('GET', `/api/recipes/${slug}`);
await api('GET', '/api/recipes/smoked-kelp-broth/comments');
await api('GET', `/api/comments/${ids.comments['granite-ledger-oat-bars']}`);
await api('GET', '/api/recipes?search=kelp&page=1&perPage=10');
await api('GET', `/api/recipes?categories=${C['Quarry Lunches']}&page=1&perPage=10`);
await api('GET', '/api/organizers/categories?page=1&perPage=50');
for (const c of ['Night-Shift Snacks', 'Tide-Table Suppers']) await api('GET', `/api/organizers/categories/${C[c]}`);
await api('GET', '/api/organizers/categories/slug/quarry-lunches');
await api('GET', '/api/organizers/tags?page=1&perPage=50');
await api('GET', `/api/organizers/tags/${TG['foraged']}`);
await api('GET', `/api/organizers/tools/${TL['Kelp smoker']}`);
for (const f of ['samphire', 'dried kelp']) await api('GET', `/api/foods/${ids.foods[f]}`);
await api('GET', `/api/units/${ids.units['crate']}`);
await api('GET', '/api/households/cookbooks?page=1&perPage=50');
for (const b of ['Quarry Packs', 'Spring Tide Menu']) await api('GET', `/api/households/cookbooks/${ids.cookbooks[b]}`);
await api('GET', '/api/households/shopping/lists?page=1&perPage=50');
for (const l of ['Saltmarsh Depot order', 'Granite Ledger pantry']) await api('GET', `/api/households/shopping/lists/${SL[l]}`);
await api('GET', `/api/households/shopping/items/${ids.shopping_items['Two jars of heather honey']}`);
await api('GET', '/api/households/mealplans?start_date=2026-11-14&end_date=2026-11-16&page=1&perPage=50');
for (const k of ['2026-11-16 side', '2026-11-14 dinner', '2026-11-15 lunch']) await api('GET', `/api/households/mealplans/${ids.mealplans[k]}`);

// --- main UI pages ---
for (const p of ['/g/lighthouse-rota', '/g/lighthouse-rota/r/smoked-kelp-broth', '/g/lighthouse-rota/cookbooks/spring-tide-menu',
  '/g/lighthouse-rota/recipes/categories', '/g/lighthouse-rota/recipes/tags', '/household/mealplan/planner/view', '/shopping-lists',
  `/shopping-lists/${SL['Saltmarsh Depot order']}`]) {
  await visit(p, 1500);
}

// --- writes on two scratch recipes (POST answers the new recipe's slug) ---
await recordWrites(api, {
  collection: '/api/recipes', list: '/api/recipes?page=1&perPage=20&orderBy=name&orderDirection=asc', item: (slug) => `/api/recipes/${slug}`,
  id: (slug) => (typeof slug === 'string' ? slug : undefined),
  create: (n) => ({ name: `Rea scratch recipe ${n}` }),
  update: (n) => ({ description: `Scratch recipe ${n} written during the capture.`, recipeYield: `${n + 1} bowls` }),
});
await settle(500);
await context.close(); // flushes the HAR
if (browser) await browser.close();
log(`HAR written to ${HAR}`);
console.log(HAR);
