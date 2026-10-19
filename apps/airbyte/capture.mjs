// Drive the showcase Airbyte web UI with Chromium via playwright-core and record a HAR with bodies.
// Sign in through the UI, visit the main pages, then a scripted read/write/read sequence against the public REST API
// (/api/public/v1) through fetch from inside the page. The bearer token for those calls is exchanged outside the browser
// (Node fetch, not recorded) from the client id/secret in .admin; scope_har.py strips request headers from the HAR.
// Requests to any other origin (analytics, fonts) are aborted so nothing leaves the VM from the browser.
import { chromium } from 'playwright-core';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

const BASE = process.env.BASE_URL || 'http://127.0.0.1:3302';
const DIR = process.env.CAPTURE_DIR || path.join(os.homedir(), 'capture', 'airbyte');
const HAR = process.env.HAR_PATH || path.join(DIR, 'airbyte.full.har');
const EXE = process.env.CHROMIUM_PATH || '/snap/bin/chromium';
const P = '/api/public/v1';
const FAKER = 'dfd88b22-b603-4c3d-aad7-3701784586b1';
const DEVNULL = 'a7bcc9d8-13b3-4e49-b80d-d020b90045e3';
const admin = Object.fromEntries(fs.readFileSync(path.join(DIR, '.admin'), 'utf8').split('\n').filter((l) => l.includes('='))
  .map((l) => { const i = l.indexOf('='); return [l.slice(0, i), l.slice(i + 1)]; }));
const ids = JSON.parse(fs.readFileSync(path.join(DIR, 'seed-ids.json'), 'utf8'));
const log = (m) => console.error(`[capture] ${m}`);

let tok = null; let tokAt = 0;
const token = async () => {
  if (!tok || Date.now() - tokAt > 600000) {
    const r = await fetch(`${BASE}${P}/applications/token`, { method: 'POST', headers: { 'content-type': 'application/json', accept: 'application/json' },
      body: JSON.stringify({ client_id: admin.AIRBYTE_CLIENT_ID, client_secret: admin.AIRBYTE_CLIENT_SECRET, 'grant-type': 'client_credentials' }) });
    if (!r.ok) throw new Error(`token exchange failed: ${r.status}`);
    tok = (await r.json()).access_token; tokAt = Date.now();
  }
  return tok;
};

const launchOpts = { executablePath: EXE, headless: true, args: ['--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu'] };
const browser = await chromium.launch(launchOpts);
const context = await browser.newContext({ recordHar: { path: HAR, content: 'embed', mode: 'full' } });
await context.route('**/*', (r) => (r.request().url().startsWith(BASE) ? r.continue() : r.abort()));
const page = await context.newPage();
page.setDefaultTimeout(60000);

const settle = async (ms = 2000) => { await page.waitForLoadState('networkidle', { timeout: 25000 }).catch(() => {}); await page.waitForTimeout(ms); };
const visit = async (p, ms) => { log(`visit ${p}`); await page.goto(`${BASE}${p}`, { waitUntil: 'domcontentloaded' }); await settle(ms); };
// The server's CORS filter answers 403 to PATCH and DELETE that carry a browser Origin header (GET and POST pass), so those
// two methods go through the context's request API instead: same context, recorded in the same HAR, no Origin header.
const api = async (method, p, body) => {
  const t = await token();
  if (method === 'PATCH' || method === 'DELETE') {
    const r = await context.request.fetch(`${BASE}${P}${p}`, { method, headers: { 'content-type': 'application/json', accept: 'application/json', authorization: `Bearer ${t}` },
      data: body === undefined ? undefined : JSON.stringify(body) });
    const text = await r.text();
    log(`${method} ${P}${p} -> ${r.status()} ${text.length}B (context request)`);
    try { return JSON.parse(text); } catch { return null; }
  }
  const res = await page.evaluate(async ({ method, p, body, t }) => {
    const r = await fetch(p, { method, headers: { 'content-type': 'application/json', accept: 'application/json', authorization: `Bearer ${t}` },
      body: body === undefined ? undefined : JSON.stringify(body) });
    return { status: r.status, text: await r.text() };
  }, { method, p: `${P}${p}`, body, t });
  log(`${method} ${P}${p} -> ${res.status} ${res.text.length}B`);
  try { return JSON.parse(res.text); } catch { return null; }
};

const W = ids.workspaces['Lighthouse Rota Pipelines']; const W2 = ids.workspaces['Saltmarsh Depot Sandbox'];
const S = ids.sources; const D = ids.destinations; const C = ids.connections; const T = ids.tags;

// --- sign in through the web UI ---
await visit('/login', 1000);
await page.waitForSelector('input[name="username"]');
await page.fill('input[name="username"]', admin.AIRBYTE_ADMIN_EMAIL);
await page.fill('input[name="password"]', admin.AIRBYTE_ADMIN_PASSWORD);
await page.click('button[type="submit"]');
await page.waitForURL((u) => !u.pathname.startsWith('/login'), { timeout: 60000 });
await settle(3000);
log(`signed in, landed on ${new URL(page.url()).pathname}`);

// --- main UI pages (their own traffic is /api/v1 RPC, outside the scope regex) ---
for (const p of [`/workspaces/${W}/connections`, `/workspaces/${W}/connections/${C['Granite Ledger census to Quiet Drain']}/status`,
  `/workspaces/${W}/connections/${C['Granite Ledger census to Quiet Drain']}/timeline`, `/workspaces/${W}/source`,
  `/workspaces/${W}/source/${S['Blue Heron Kitchen Orders']}`, `/workspaces/${W}/destination`, `/workspaces/${W}/settings`]) {
  await visit(p, 2000);
}

// --- scripted public API sequence from inside the page ---
// organization and workspaces
await api('GET', '/organizations');
await api('GET', '/workspaces');
await api('GET', `/workspaces/${W2}`);
await api('GET', `/workspaces/${W}`);
await api('GET', '/workspaces?includeDeleted=true');
await api('GET', '/permissions');
// sources
await api('GET', '/sources');
await api('GET', `/sources?workspaceIds=${W2}`);
await api('GET', '/sources?limit=2&offset=0');
await api('GET', '/sources?limit=2&offset=2');
for (const n of ['Copperfield Annex Visitor Log', 'Granite Ledger Stone Census', 'Saltmarsh Depot Tide Readings', 'Blue Heron Kitchen Orders']) await api('GET', `/sources/${S[n]}`);
// destinations
await api('GET', '/destinations');
await api('GET', `/destinations?workspaceIds=${W}`);
await api('GET', `/destinations?workspaceIds=${W2}`);
for (const n of ['Lighthouse Rota Quiet Drain', 'Saltmarsh Depot Dev Null', 'Copperfield Annex Null Sink']) await api('GET', `/destinations/${D[n]}`);
// connections and their streams
await api('GET', '/connections');
await api('GET', `/connections?workspaceIds=${W2}`);
await api('GET', '/connections?includeDeleted=true&limit=10');
for (const n of ['Saltmarsh Depot tide readings relay', 'Blue Heron Kitchen nightly orders feed', 'Granite Ledger census to Quiet Drain']) await api('GET', `/connections/${C[n]}`);
await api('GET', `/streams?sourceId=${S['Blue Heron Kitchen Orders']}&destinationId=${D['Copperfield Annex Null Sink']}`);
await api('GET', `/streams?sourceId=${S['Saltmarsh Depot Tide Readings']}&destinationId=${D['Saltmarsh Depot Dev Null']}`);
// tags
await api('GET', '/tags');
await api('GET', `/tags?workspaceIds=${W2}`);
for (const n of ['Kitchen Night Shift', 'Tide Table Crew', 'Quarry Audit']) await api('GET', `/tags/${T[n]}`);
// jobs
await api('GET', '/jobs');
await api('GET', `/jobs?connectionId=${C['Granite Ledger census to Quiet Drain']}&limit=5`);
await api('GET', '/jobs?jobType=sync&status=succeeded');
await api('GET', `/jobs?workspaceIds=${W}&limit=5`);
for (const j of ids.jobs) await api('GET', `/jobs/${j}`);
// connector definitions used by the seeded objects
await api('GET', `/workspaces/${W}/definitions/sources/${FAKER}`);
await api('GET', `/workspaces/${W}/definitions/destinations/${DEVNULL}`);
await api('GET', `/workspaces/${W}/definitions/destinations`);

// --- write path on scratch objects: create, edit, re-read, delete, re-read ---
const src = await api('POST', '/sources', { name: 'Rea scratch source', workspaceId: W, definitionId: FAKER,
  configuration: { sourceType: 'faker', count: 15, seed: 2, records_per_slice: 15, always_updated: false, parallelism: 1 } });
if (src?.sourceId) {
  await api('PATCH', `/sources/${src.sourceId}`, { name: 'Rea scratch source (edited)', configuration: { sourceType: 'faker', count: 20, seed: 2, records_per_slice: 20, always_updated: false, parallelism: 1 } });
  await api('GET', `/sources/${src.sourceId}`);
  await api('GET', `/sources?workspaceIds=${W}`);
  await api('DELETE', `/sources/${src.sourceId}`);
  await api('GET', `/sources/${src.sourceId}`);
}
const tag = await api('POST', '/tags', { name: 'Rea scratch tag', color: '7A7A7A', workspaceId: W });
if (tag?.tagId) {
  await api('PATCH', `/tags/${tag.tagId}`, { name: 'Rea scratch tag (edited)', color: '5A5A5A' });
  await api('GET', `/tags/${tag.tagId}`);
  await api('DELETE', `/tags/${tag.tagId}`);
  await api('GET', '/tags');
}
// trigger a manual sync of the Saltmarsh Depot relay and read the new job
const job = await api('POST', '/jobs', { connectionId: C['Saltmarsh Depot tide readings relay'], jobType: 'sync' });
if (job?.jobId) await api('GET', `/jobs/${job.jobId}`);
await api('GET', `/jobs?connectionId=${C['Saltmarsh Depot tide readings relay']}`);

// --- re-reads of the seeded objects after the writes ---
await api('GET', '/sources');
await api('GET', '/connections');
for (const n of ['Granite Ledger Stone Census', 'Copperfield Annex Visitor Log']) await api('GET', `/sources/${S[n]}`);
await api('GET', `/destinations/${D['Lighthouse Rota Quiet Drain']}`);
await api('GET', `/connections/${C['Blue Heron Kitchen nightly orders feed']}`);
await api('GET', `/tags/${T['Quarry Audit']}`);
await api('GET', `/workspaces/${W}`);
if (job?.jobId) await api('GET', `/jobs/${job.jobId}`);

await visit(`/workspaces/${W}/connections`, 1500);
await context.close(); // flushes the HAR
await browser.close();
log(`HAR written to ${HAR}`);
console.log(HAR);
