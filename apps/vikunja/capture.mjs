// Drive the showcase Vikunja web UI with Chromium via playwright-core and record a HAR with bodies.
// Login through the UI, a scripted read sequence through fetch from inside the page (first, so each tool's first record is a
// seeded object), the main UI pages, then a scripted create/update/delete of a scratch task. The 2.x web UI talks to the
// RESTful /api/v2 (POST creates, PATCH/PUT update), so the scripted calls use it too. The UI keeps its JWT in localStorage
// ("token") and sends it as a bearer header; the scripted calls read it in the page and do the same. Request headers are
// stripped by scope_har.py. Service workers are blocked: Vikunja's PWA worker otherwise records every page fetch twice.
import { chromium } from 'playwright-core';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

const BASE = process.env.BASE_URL || 'http://127.0.0.1:3211';
const DIR = process.env.CAPTURE_DIR || path.join(os.homedir(), 'capture', 'vikunja');
const HAR = process.env.HAR_PATH || path.join(DIR, 'vikunja.full.har');
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
    const r = await fetch(`/api/v2${p}`, { method, headers: { 'content-type': 'application/json', accept: 'application/json', authorization: `Bearer ${localStorage.getItem('token')}` },
      body: body === undefined ? undefined : JSON.stringify(body) });
    return { status: r.status, text: await r.text() };
  }, { method, p, body });
  log(`${method} /api/v2${p} -> ${res.status} (${res.text.length} bytes)`);
  let json = null; try { json = JSON.parse(res.text); } catch {}
  return json;
};

// --- login through the web UI ---
await visit('/login', 1000);
await page.fill('#username', 'rea-admin');
await page.fill('#password', admin.VIKUNJA_ADMIN_PASSWORD);
await page.keyboard.press('Enter');
await page.waitForURL((u) => !u.pathname.startsWith('/login'), { timeout: 45000 });
await settle(2500);
log(`logged in, landed on ${new URL(page.url()).pathname}; token in localStorage: ${await page.evaluate(() => !!localStorage.getItem('token'))}`);

// --- scripted read sequence from inside the page ---
const P = ids.projects; const VW = ids.views; const T = ids.tasks; const L = ids.labels; const TM = ids.teams;
await api('GET', '/info');
await api('GET', '/user');
await api('GET', '/projects?page=1&per_page=50');
for (const p of ['Granite Ledger', 'Lighthouse Rota', 'Lamp Room Upkeep', 'Blue Heron Kitchen', 'Copperfield Annex Repaint']) await api('GET', `/projects/${P[p]}`);
await api('GET', `/projects/${P['Lighthouse Rota']}/views`);
await api('GET', `/projects/${P['Granite Ledger']}/views/${VW['Granite Ledger'].List}/tasks`);
await api('GET', `/projects/${P['Blue Heron Kitchen']}/views/${VW['Blue Heron Kitchen'].Kanban}/buckets`);
await api('GET', `/projects/${P['Lighthouse Rota']}/teams`);
await api('GET', `/projects/${P['Blue Heron Kitchen']}/users`);
await api('GET', `/projects/${P['Granite Ledger']}/tasks/by-index/1`);
for (const t of ['Count the blocks in the tidal yard', 'Draft the January night-shift rota', 'Log the lamp oil budget', 'Trim the wicks before dusk',
  'Retire cart number 7', 'Order smoked kelp from the Saltmarsh Depot', 'Print the tide-table menu cards']) await api('GET', `/tasks/${T[t]}`);
await api('GET', `/tasks/${T['Count the blocks in the tidal yard']}/comments`);
await api('GET', `/tasks/${T['Order smoked kelp from the Saltmarsh Depot']}/comments/${ids.comments['Order smoked kelp from the Saltmarsh Depot']}`);
await api('GET', `/tasks/${T['Order smoked kelp from the Saltmarsh Depot']}/labels`);
await api('GET', `/tasks/${T['Draft the January night-shift rota']}/assignees`);
await api('GET', '/labels?page=1&per_page=50');
for (const l of ['kelp-order', 'tide-critical', 'quarry-audit']) await api('GET', `/labels/${L[l]}`);
await api('GET', '/teams?page=1&per_page=50');
for (const t of ['Quarry Auditors', 'Night Watch']) await api('GET', `/teams/${TM[t]}`);
await api('GET', `/filters/${ids.filters['Tide-critical open work']}`);
await api('GET', '/tasks?s=kelp');
await api('GET', `/tasks?filter=${encodeURIComponent('priority >= 3')}&sort_by=priority&order_by=desc`);
await api('GET', '/labels?s=quarry');
await api('GET', '/users?s=okafor');

// --- main UI pages ---
for (const p of ['/', '/projects', `/projects/${P['Lighthouse Rota']}/${VW['Lighthouse Rota'].List}`,
  `/projects/${P['Blue Heron Kitchen']}/${VW['Blue Heron Kitchen'].Kanban}`, `/tasks/${T['Count the blocks in the tidal yard']}`, '/labels', '/teams',
  `/teams/${TM['Night Watch']}/edit`]) {
  await visit(p, 1500);
}

// --- write path on a scratch task: create (POST), edit (PATCH), re-read, delete, re-read, re-list ---
const created = await api('POST', `/projects/${P['Lighthouse Rota']}/tasks`, { title: 'Rea scratch task', description: 'Scratch task written during the capture.', priority: 1 });
if (created?.id) {
  const upd = await api('PATCH', `/tasks/${created.id}`, { title: 'Rea scratch task (edited)', done: true });
  log(`scratch task edited -> ${upd?.title}`);
  await api('GET', `/tasks/${created.id}`);
  await api('DELETE', `/tasks/${created.id}`);
  await api('GET', `/tasks/${created.id}`);
}
await api('GET', `/projects/${P['Lighthouse Rota']}/views/${VW['Lighthouse Rota'].List}/tasks`);
await settle(500);
await context.close(); // flushes the HAR
if (browser) await browser.close();
log(`HAR written to ${HAR}`);
console.log(HAR);
