// Drive the showcase n8n editor with Chromium via playwright-core and record a HAR with bodies.
// Sign in through the editor UI, visit the main pages (workflow list, two workflow canvases, executions, data tables,
// settings), then a scripted read/write/read sequence through fetch from inside the page against the editor's own REST
// API (/rest/*). The session cookie travels automatically; n8n also binds the session to the editor's `browser-id`
// header, whose value the script reads from the page's localStorage (in memory only, never logged). The scoping step
// strips every header except content-type/accept.
import { chromium } from 'playwright-core';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { recordWrites } from '../record_writes.mjs'; // shipped to ~/capture/ next to scope_har.py

const BASE = process.env.BASE_URL || 'http://127.0.0.1:3218';
const DIR = process.env.CAPTURE_DIR || path.join(os.homedir(), 'capture', 'n8n');
const HAR = process.env.HAR_PATH || path.join(DIR, 'n8n.full.har');
const EXE = process.env.CHROMIUM_PATH || '/snap/bin/chromium';
const admin = Object.fromEntries(fs.readFileSync(path.join(DIR, '.admin'), 'utf8').split('\n').filter((l) => l.includes('='))
  .map((l) => { const i = l.indexOf('='); return [l.slice(0, i), l.slice(i + 1)]; }));
const EMAIL = 'rea-admin@example.test'; const PASS = admin.N8N_OWNER_PASSWORD;
const ids = JSON.parse(fs.readFileSync(path.join(DIR, 'seed-ids.json'), 'utf8'));
const log = (m) => console.error(`[capture] ${m}`);

const launchOpts = { executablePath: EXE, headless: true, args: ['--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu'] };
const harOpts = { recordHar: { path: HAR, content: 'embed', mode: 'full' } };
let browser = null; let context;
if (process.env.USER_DATA_DIR) {
  context = await chromium.launchPersistentContext(process.env.USER_DATA_DIR, { ...launchOpts, ...harOpts });
} else {
  browser = await chromium.launch(launchOpts);
  context = await browser.newContext({ ...harOpts, viewport: { width: 1440, height: 900 } });
}
const page = context.pages()[0] || await context.newPage();
page.setDefaultTimeout(45000);

const settle = async (ms = 1500) => { await page.waitForLoadState('networkidle', { timeout: 20000 }).catch(() => {}); await page.waitForTimeout(ms); };
const visit = async (p, ms) => { log(`visit ${p}`); await page.goto(`${BASE}${p}`, { waitUntil: 'domcontentloaded' }); await settle(ms); };
let calls = 0;
const api = async (method, p, body) => {
  const res = await page.evaluate(async ({ method, p, body }) => {
    const headers = { 'content-type': 'application/json', accept: 'application/json' };
    const bid = window.localStorage.getItem('n8n-browserId'); if (bid) headers['browser-id'] = bid;
    const r = await fetch(`/rest/${p}`, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });
    return { status: r.status, text: await r.text() };
  }, { method, p, body });
  calls += 1; log(`${method} /rest/${p.split('?')[0]} -> ${res.status}`);
  try { return JSON.parse(res.text); } catch { return null; }
};
const q = (o) => new URLSearchParams(Object.fromEntries(Object.entries(o).map(([k, v]) => [k, typeof v === 'string' ? v : JSON.stringify(v)]))).toString();

// --- sign in through the editor UI ---
// Land on the personal settings page instead of the workflow list, so the first recorded /rest/workflows and
// /rest/executions reads are the scripted ones below (plain query values) rather than the editor's JSON-valued `filter`
// queries: a tool whose first record has a JSON string as a query value becomes a task some agents cannot call (the
// value reaches the replay server as an object and fails its `string` schema).
await visit(`/signin?redirect=${encodeURIComponent('/settings/personal')}`, 800);
await page.fill('input[name="emailOrLdapLoginId"]', EMAIL);
await page.fill('input[name="password"]', PASS);
await page.click('[data-test-id="form-submit-button"]');
await page.waitForURL((u) => !u.pathname.startsWith('/signin'), { timeout: 45000 });
await settle(2500);
log(`signed in, landed on ${new URL(page.url()).pathname}`);

const W = ids.workflows; const T = ids.tags; const X = ids.executions; const P = ids.projects.personal; const D = ids.dataTables;
await api('GET', `workflows?${q({ sortBy: 'name:asc', skip: '0', take: '50' })}`);
await api('GET', `executions?${q({ limit: '10' })}`);

// --- main pages (editor traffic) ---
// Navigate inside the single-page app through its Vue router: a full page load re-runs the editor's whole bootstrap
// (settings, roles, projects, licence...) and would bury the scripted calls under repeated records.
const nav = async (p, ms) => {
  const ok = await page.evaluate(async (p) => {
    const router = document.querySelector('#app')?.__vue_app__?.config?.globalProperties?.$router;
    if (!router) return false; await router.push(p); return true;
  }, p);
  log(`nav ${p}${ok ? '' : ' (router not found, full load)'}`);
  if (!ok) await page.goto(`${BASE}${p}`, { waitUntil: 'domcontentloaded' });
  await settle(ms);
};
for (const [p, ms] of [[`/workflow/${W['Granite Ledger stone count digest']}`, 3500],
  [`/workflow/${W['Blue Heron Kitchen sitting planner']}/executions`, 2500], ['/home/executions', 2000],
  [`/projects/${P}/datatables`, 2000], ['/settings/personal', 1500], ['/home/credentials', 1500], ['/home/workflows', 1500]]) {
  // (not /settings/users: that page requests /rest/users?sortBy[]=... with raw brackets, which rea's HAR uri check rejects)
  await nav(p, ms);
}

// --- scripted API sequence from inside the page ---
await api('GET', 'users');
await api('GET', `tags?${q({ withUsageCount: 'true' })}`);
await api('GET', `workflows?${q({ includeScopes: 'true', sortBy: 'name:asc', skip: '0', take: '50' })}`);
for (const id of Object.values(W)) await api('GET', `workflows/${id}`);
await api('GET', `workflows?${q({ filter: { tags: ['Quarterly Audit'] }, sortBy: 'name:asc' })}`);
await api('GET', `workflows?${q({ filter: { query: 'Saltmarsh' } })}`);
await api('GET', 'active-workflows');
await api('GET', `executions?${q({ limit: '10' })}`);
for (const [name, id] of Object.entries(X)) {
  await api('GET', `executions?${q({ filter: { workflowId: W[name] }, limit: '10' })}`);
  await api('GET', `executions/${id}`);
  await api('GET', `workflows/${W[name]}/executions/last-successful`);
}
await api('GET', 'projects/personal');
await api('GET', 'projects/my-projects');
await api('GET', `projects/${P}`);
await api('GET', `projects/${P}/data-tables?${q({ skip: '0', take: '20', sortBy: 'name:asc' })}`);
await api('GET', `data-tables-global?${q({ skip: '0', take: '20' })}`);
for (const id of Object.values(D)) {
  await api('GET', `projects/${P}/data-tables/${id}/columns`);
  await api('GET', `projects/${P}/data-tables/${id}/rows?${q({ skip: '0', take: '20' })}`);
}
await api('GET', `projects/${P}/data-tables/${D['Lamp Oil Drops']}/rows?${q({ skip: '0', take: '20', filter: { type: 'and', filters: [{ columnName: 'barge', condition: 'eq', value: 'Ember Compass' }] } })}`);
await api('GET', 'credentials');
// writes on two scratch workflows, each archived before its delete. Tags are not written: rea does not model them, and tag
// writes in the same capture leave the workflow writes unmodelled too.
await recordWrites(api, {
  collection: 'workflows', list: `workflows?${q({ includeScopes: 'true', sortBy: 'name:asc', skip: '0', take: '50' })}`,
  item: (id) => `workflows/${id}`, id: (w) => w?.data?.id,
  create: (n) => ({ name: `Rea scratch workflow ${n}`, active: false, connections: {}, settings: { executionOrder: 'v1' },
    nodes: [{ parameters: {}, name: 'Start scratch', type: 'n8n-nodes-base.manualTrigger', typeVersion: 1, position: [0, 0] }] }),
  update: (n, created) => ({ name: `Rea scratch workflow ${n} (edited)`, versionId: created.data.versionId }),
  beforeDelete: (id) => [['POST', `workflows/${id}/archive`, {}]],
});
await settle(500);
await context.close(); // flushes the HAR
if (browser) await browser.close();
log(`${calls} scripted calls; HAR written to ${HAR}`);
console.log(HAR);
