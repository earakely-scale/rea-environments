// Drive the showcase Grist with Chromium via playwright-core and record a HAR with bodies.
// Sign in through the UI (Grist's single-user "minimal" login: the Sign in button signs the browser in as
// GRIST_DEFAULT_EMAIL, no password), visit the home, two workspaces and the three seeded documents, then a scripted
// read/write/read sequence of fetch calls from inside the page against the REST API under /o/docs/api (the prefix the UI itself uses). The session cookie is carried automatically;
// writes add the X-Requested-With header Grist's CSRF check asks for on cookie-authenticated requests.
import { chromium } from 'playwright-core';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

const BASE = process.env.BASE_URL || 'http://127.0.0.1:3220';
const DIR = process.env.CAPTURE_DIR || path.join(os.homedir(), 'capture', 'grist');
const HAR = process.env.HAR_PATH || path.join(DIR, 'grist.full.har');
const EXE = process.env.CHROMIUM_PATH || '/snap/bin/chromium';
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

const settle = async (ms = 1500) => { await page.waitForLoadState('networkidle', { timeout: 20000 }).catch(() => {}); await page.waitForTimeout(ms); };
const visit = async (p, ms) => { log(`visit ${p}`); await page.goto(`${BASE}${p}`, { waitUntil: 'domcontentloaded' }); await settle(ms); };
const calls = [];
const api = async (method, p, body) => {
  const res = await page.evaluate(async ({ method, p, body }) => {
    const headers = { accept: 'application/json', 'x-requested-with': 'XMLHttpRequest' };
    if (body !== undefined) headers['content-type'] = 'application/json';
    const r = await fetch(p, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });
    return { status: r.status, text: await r.text() };
  }, { method, p, body });
  log(`${method} ${p} -> ${res.status}`); calls.push({ method, path: p, status: res.status });
  try { return JSON.parse(res.text); } catch { return null; }
};
const q = (o) => encodeURIComponent(JSON.stringify(o));
// The web UI addresses the REST API under the org prefix (/o/docs/api/...), so the scripted calls do too.
const A = '/o/docs/api';

// --- sign in through the UI ---
await visit('/', 2500);
const signIn = page.getByText('Sign in', { exact: true }).first();
if (await signIn.isVisible().catch(() => false)) {
  await Promise.all([page.waitForURL((u) => !u.pathname.startsWith('/login'), { timeout: 45000 }).catch(() => {}), signIn.click()]);
  await settle(2500);
} else {
  await visit('/login', 2500);
}
const who = await api('GET', `${A}/profile/user`);
log(`signed in as ${who?.name}, landed on ${new URL(page.url()).pathname}`);

// --- main pages (UI traffic) ---
const W = ids.workspaces; const D = ids.docs; const ORG = ids.org_id;
const NSP = D['Night Shift Planner']; const BHK = D['Blue Heron Kitchen Menu']; const QA = D['Quarry Audit 2026'];
for (const p of ['/o/docs/', `/o/docs/ws/${W['Lighthouse Rota']}/`, `/o/docs/ws/${W['Granite Ledger']}/`, `/o/docs/${NSP}/`, `/o/docs/${BHK}/`, `/o/docs/${QA}/`]) {
  await visit(p, p.includes('/ws/') || p === '/o/docs/' ? 1500 : 3500);
}

// --- scripted API sequence from inside the page ---
await api('GET', `${A}/orgs`);
await api('GET', `${A}/orgs/${ORG}`);
await api('GET', `${A}/orgs/${ORG}/workspaces`);
await api('GET', `${A}/orgs/${ORG}/access`);
for (const w of [W['Granite Ledger'], W['Lighthouse Rota'], W.Home]) await api('GET', `${A}/workspaces/${w}`);
await api('GET', `${A}/workspaces/${W['Lighthouse Rota']}/access`);
for (const d of [QA, NSP, BHK]) await api('GET', `${A}/docs/${d}`);
for (const d of [QA, NSP, BHK]) await api('GET', `${A}/docs/${d}/access`);
await api('GET', `${A}/workspaces/${W['Granite Ledger']}/access`);
for (const d of [BHK, NSP, QA]) await api('GET', `${A}/docs/${d}/tables`);
const TABLES = [[BHK, 'Dishes'], [NSP, 'Keepers'], [NSP, 'Shifts'], [NSP, 'Supplies'], [QA, 'Terraces'], [QA, 'Carts']];
for (const [d, t] of TABLES) await api('GET', `${A}/docs/${d}/tables/${t}/columns`);
for (const [d, t] of TABLES) await api('GET', `${A}/docs/${d}/tables/${t}/records`);
await api('GET', `${A}/docs/${NSP}/tables/Keepers/records?filter=${q({ Station: ['Lamp Room'] })}`);
await api('GET', `${A}/docs/${NSP}/tables/Supplies/records?filter=${q({ Reorder: [true] })}`);
await api('GET', `${A}/docs/${QA}/tables/Terraces/records?sort=-Blocks&limit=2`);
await api('GET', `${A}/docs/${BHK}/tables/Dishes/records?filter=${q({ Course: ['main'] })}`);
await api('GET', `${A}/docs/${NSP}/sql?q=${encodeURIComponent('select Name, Station from Keepers order by Name')}`);
await api('GET', `${A}/docs/${QA}/sql?q=${encodeURIComponent('select Name, Blocks, Auditor from Terraces where Blocks > 90')}`);
await api('GET', `${A}/docs/${BHK}/sql?q=${encodeURIComponent('select Title, Cook from Dishes order by Covers desc')}`);
await api('GET', `${A}/docs/${NSP}/tables/Shifts/columns?hidden=true`);
await api('GET', `${A}/docs/${NSP}/tables/Shifts/records?limit=1`);
await api('GET', `${A}/docs/${QA}/tables/Carts/records?filter=${q({ Retired: [false] })}`);
await api('GET', `${A}/docs/${NSP}/attachments`);
// write path 1: a scratch record in Supplies (create, update, read back by filter, delete, re-read)
const added = await api('POST', `${A}/docs/${NSP}/tables/Supplies/records`, { records: [{ fields: { Item: 'Rea Scratch crate', Quantity: 3, Unit: 'crates', Location: 'Copperfield Annex' } }] });
const rid = added?.records?.[0]?.id;
if (rid) {
  await api('PATCH', `${A}/docs/${NSP}/tables/Supplies/records`, { records: [{ id: rid, fields: { Quantity: 5 } }] });
  await api('GET', `${A}/docs/${NSP}/tables/Supplies/records?filter=${q({ Item: ['Rea Scratch crate'] })}`);
  await api('POST', `${A}/docs/${NSP}/tables/Supplies/records/delete`, [rid]);
}
await api('GET', `${A}/docs/${NSP}/tables/Supplies/records?sort=Item`);
// write path 2: a scratch document (create, rename, read, delete, re-read)
const sdoc = await api('POST', `${A}/workspaces/${W['Granite Ledger']}/docs`, { name: 'Rea Scratch Ledger' });
if (typeof sdoc === 'string') {
  await api('PATCH', `${A}/docs/${sdoc}`, { name: 'Rea Scratch Ledger (renamed)' });
  await api('GET', `${A}/docs/${sdoc}`);
  await api('DELETE', `${A}/docs/${sdoc}`);
  await api('GET', `${A}/docs/${sdoc}`);
}
await api('GET', `${A}/workspaces/${W['Granite Ledger']}`);
await settle(500);
await context.close(); // flushes the HAR
if (browser) await browser.close();
fs.writeFileSync(path.join(DIR, 'capture-calls.json'), JSON.stringify(calls, null, 1));
log(`HAR written to ${HAR}; ${calls.length} scripted calls`);
console.log(HAR);
