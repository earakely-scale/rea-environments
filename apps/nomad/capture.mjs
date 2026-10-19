// Drive the showcase Nomad dev agent with Chromium via playwright-core and record a HAR with bodies.
// ACLs are off, so the web UI needs no sign-in: visit the main UI pages, then run a scripted read/write/read sequence
// through fetch from a same-origin JSON page (no UI scripts running). The UI's blocking "watch" queries (index=N long
// polls that stay open until state changes) are left out of the HAR with recordHar.urlFilter; their first, non-blocking
// fetches are recorded.
import { chromium } from 'playwright-core';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

const BASE = process.env.BASE_URL || 'http://127.0.0.1:3304';
const DIR = process.env.CAPTURE_DIR || path.join(os.homedir(), 'capture', 'nomad');
const HAR = process.env.HAR_PATH || path.join(DIR, 'nomad.full.har');
const EXE = process.env.CHROMIUM_PATH || '/snap/bin/chromium';
const ids = JSON.parse(fs.readFileSync(path.join(DIR, 'seed-ids.json'), 'utf8'));
const log = (m) => console.error(`[capture] ${m}`);

const launchOpts = { executablePath: EXE, headless: true, args: ['--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu'] };
const harOpts = { recordHar: { path: HAR, content: 'embed', mode: 'full', urlFilter: /^(?!.*[?&]index=)/ } };
const browser = await chromium.launch(launchOpts);
const context = await browser.newContext(harOpts);
const page = await context.newPage();
page.setDefaultTimeout(45000);

const visit = async (p, ms = 2000) => {
  log(`visit ${p}`);
  await page.goto(`${BASE}${p}`, { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(ms);
};
const api = async (method, p, body) => {
  const res = await page.evaluate(async ({ method, p, body }) => {
    const r = await fetch(p, { method, headers: { 'content-type': 'application/json', accept: 'application/json' }, body: body === undefined ? undefined : JSON.stringify(body) });
    return { status: r.status, text: await r.text() };
  }, { method, p, body });
  log(`${method} ${p} -> ${res.status} (${res.text.length} bytes)`);
  try { return JSON.parse(res.text); } catch { return null; }
};
const enc = encodeURIComponent;
const allocOf = (job, pick = 0) => (ids.allocations[job] || [])[pick];

// --- UI pages (no sign-in with ACLs off) ---
const kitchen = 'blue-heron-kitchen-orders@lighthouse-rota';
for (const p of ['/ui/jobs', `/ui/jobs/${kitchen}`, `/ui/jobs/${kitchen}/versions`, `/ui/jobs/${kitchen}/deployments`,
  '/ui/jobs/granite-ledger-stone-count@granite-ledger/allocations', `/ui/allocations/${allocOf('granite-ledger-stone-count')}`,
  '/ui/clients', `/ui/clients/${ids.node.id}`, '/ui/topology', '/ui/evaluations', '/ui/servers']) {
  await visit(p);
}

// --- scripted API sequence from a same-origin JSON page ---
await visit('/v1/status/leader', 300);
await api('GET', '/v1/regions');
await api('GET', '/v1/namespaces');
await api('GET', '/v1/namespace/lighthouse-rota');
await api('GET', '/v1/namespace/granite-ledger');
await api('GET', '/v1/node/pools');
await api('GET', '/v1/node/pool/saltmarsh-depot');
await api('GET', '/v1/node/pool/saltmarsh-depot/jobs');
await api('GET', '/v1/nodes');
await api('GET', `/v1/node/${ids.node.id}`);
await api('GET', `/v1/jobs?namespace=${enc('*')}`);
for (const [job, ns] of Object.entries(ids.jobs)) await api('GET', `/v1/job/${job}?namespace=${ns}`);
await api('GET', `/v1/job/${enc(ids.dispatched)}?namespace=granite-ledger`);
await api('GET', '/v1/job/blue-heron-kitchen-orders/versions?namespace=lighthouse-rota');
await api('GET', '/v1/job/blue-heron-kitchen-orders/allocations?namespace=lighthouse-rota');
await api('GET', '/v1/job/blue-heron-kitchen-orders/deployments?namespace=lighthouse-rota');
await api('GET', '/v1/job/blue-heron-kitchen-orders/summary?namespace=lighthouse-rota');
await api('GET', '/v1/job/granite-ledger-stone-count/evaluations?namespace=granite-ledger');
await api('GET', '/v1/job/saltmarsh-depot-cold-store/evaluations?namespace=default');
await api('GET', `/v1/allocation/${allocOf('granite-ledger-stone-count')}`);
await api('GET', `/v1/allocation/${allocOf('lighthouse-rota-night-watch')}`);
await api('GET', `/v1/allocation/${allocOf(ids.dispatched)}`);
if (ids.blocked_evals[0]) await api('GET', `/v1/evaluation/${ids.blocked_evals[0]}`);
const deps = await api('GET', `/v1/deployments?namespace=${enc('*')}`);
const dep = (deps || []).find((d) => d.JobID === 'blue-heron-kitchen-orders' && d.JobVersion === 1) || (deps || [])[0];
if (dep) await api('GET', `/v1/deployment/${dep.ID}`);
await api('GET', `/v1/evaluations?namespace=${enc('*')}`);
// searches and filters
await api('GET', `/v1/jobs?namespace=${enc('*')}&prefix=granite`);
await api('GET', `/v1/jobs?namespace=${enc('*')}&filter=${enc('Status == "pending"')}`);
await api('POST', '/v1/search/fuzzy', { Text: 'kelp', Context: 'all', Namespace: '*' });
// write path on a scratch job: register, read, update (new version), read versions, purge, re-read
const scratch = (note) => ({ Job: { ID: 'rea-scratch-tide-probe', Name: 'rea-scratch-tide-probe', Namespace: 'lighthouse-rota', Region: 'saltmarsh',
  Type: 'batch', Datacenters: ['granite-point'], Meta: { purpose: note },
  TaskGroups: [{ Name: 'probe', Count: 1, Tasks: [{ Name: 'tide-probe', Driver: 'raw_exec', Config: { command: '/bin/sh', args: ['-c', 'echo tide probe'] }, Resources: { CPU: 20, MemoryMB: 16 } }] }] } });
await api('POST', '/v1/jobs', scratch('scratch tide probe written during the capture'));
await api('GET', '/v1/job/rea-scratch-tide-probe?namespace=lighthouse-rota');
await api('POST', '/v1/job/rea-scratch-tide-probe?namespace=lighthouse-rota', scratch('scratch tide probe edited during the capture'));
await api('GET', '/v1/job/rea-scratch-tide-probe/versions?namespace=lighthouse-rota');
await api('DELETE', '/v1/job/rea-scratch-tide-probe?namespace=lighthouse-rota&purge=true');
await api('GET', '/v1/job/rea-scratch-tide-probe?namespace=lighthouse-rota');
await api('GET', '/v1/jobs?namespace=lighthouse-rota');
await page.waitForTimeout(500);
await context.close(); // flushes the HAR
await browser.close();
log(`HAR written to ${HAR}`);
console.log(HAR);
