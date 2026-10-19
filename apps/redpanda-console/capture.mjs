// Drive the showcase Redpanda Console with Chromium via playwright-core and record a HAR with bodies.
// The free edition has no login: visit the main pages (overview, topics, a topic, groups, a group, schema registry, a
// subject), then a scripted read/write/read sequence through fetch from inside the page against the REST API under /api/.
import { chromium } from 'playwright-core';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

const BASE = process.env.BASE_URL || 'http://127.0.0.1:3305';
const DIR = process.env.CAPTURE_DIR || path.join(os.homedir(), 'capture', 'redpanda-console');
const HAR = process.env.HAR_PATH || path.join(DIR, 'redpanda-console.full.har');
const EXE = process.env.CHROMIUM_PATH || '/snap/bin/chromium';
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

const settle = async (ms = 1500) => { await page.waitForLoadState('networkidle', { timeout: 8000 }).catch(() => {}); await page.waitForTimeout(ms); };
const visit = async (p, ms) => { log(`visit ${p}`); await page.goto(`${BASE}${p}`, { waitUntil: 'domcontentloaded' }); await settle(ms); };
const api = async (method, p, body) => {
  const res = await page.evaluate(async ({ method, p, body }) => {
    const r = await fetch(p, { method, headers: { 'content-type': 'application/json', accept: 'application/json' }, body: body === undefined ? undefined : JSON.stringify(body) });
    return { status: r.status, text: await r.text() };
  }, { method, p, body });
  log(`${method} ${p} -> ${res.status}`);
  let json = null; try { json = JSON.parse(res.text); } catch {}
  return json;
};
const enc = encodeURIComponent;
const b64 = (s) => Buffer.from(s).toString('base64');

const T = { stone: 'granite-ledger.stone-counts', tide: 'blue-heron-kitchen.tide-orders', shift: 'lighthouse-rota.shift-handover',
  oil: 'copperfield-annex.lamp-oil-deliveries', crate: 'saltmarsh-depot.crate-manifests' };
const SCRATCH = 'rea-scratch.lamp-trials';

// --- main pages (UI traffic) ---
for (const p of ['/overview', '/topics', `/topics/${enc(T.stone)}`, '/groups', '/groups/blue-heron-kitchen-pass', '/schema-registry',
  `/schema-registry/subjects/${enc('lighthouse-rota.shift-handover-value')}?version=latest`]) {
  await visit(p, 1500);
}
await visit('/overview', 500);

// --- scripted API sequence from inside the page ---
await api('GET', '/api/cluster');
await api('GET', '/api/brokers');
await api('GET', '/api/brokers/0/config');
await api('GET', '/api/topics');
await api('GET', '/api/consumer-groups');
await api('GET', '/api/schema-registry/subjects');
await api('GET', '/api/schema-registry/config');
await api('GET', '/api/schema-registry/mode');
await api('GET', '/api/schema-registry/contexts');
await api('GET', '/api/schema-registry/schemas/types');
await api('GET', '/api/operations/reassign-partitions');
// topics by name
for (const t of [T.shift, T.stone, T.tide, T.oil, T.crate]) await api('GET', `/api/topics/${enc(t)}/consumers`);
for (const t of [T.crate, T.stone, T.oil]) await api('GET', `/api/topics/${enc(t)}/partitions`);
await api('GET', `/api/topics/${enc(T.crate)}/configuration`);
await api('GET', `/api/topics/${enc(T.shift)}/documentation`);
// consumer groups by id
for (const g of ['saltmarsh-depot-tally', 'lighthouse-rota-keepers', 'granite-ledger-auditors', 'blue-heron-kitchen-pass']) await api('GET', `/api/consumer-groups/${enc(g)}`);
// schema subjects, versions, references and ids
await api('GET', `/api/schema-registry/subjects/${enc('lighthouse-rota.shift-handover-value')}/versions/latest`);
await api('GET', `/api/schema-registry/subjects/${enc('lighthouse-rota.keeper')}/versions/1`);
await api('GET', `/api/schema-registry/subjects/${enc('granite-ledger.stone-counts-value')}/versions/2`);
await api('GET', `/api/schema-registry/subjects/${enc('blue-heron-kitchen.tide-orders-value')}/versions/latest`);
await api('GET', `/api/schema-registry/subjects/${enc('saltmarsh-depot.crate-manifests-value')}/versions/latest`);
await api('GET', `/api/schema-registry/subjects/${enc('lighthouse-rota.keeper')}/versions/1/referencedby`);
for (const id of [6, 3, 5]) await api('GET', `/api/schema-registry/schemas/ids/${id}/versions`);
await api('GET', `/api/schema-registry/config/${enc('lighthouse-rota.shift-handover-value')}`);
await api('GET', `/api/schema-registry/config/${enc('blue-heron-kitchen.tide-orders-value')}`);
// filtered queries
await api('GET', `/api/topics-configs?topicNames=${enc(`${T.crate},${T.oil}`)}&configKeys=${enc('cleanup.policy,retention.ms')}`);
await api('GET', `/api/operations/topic-details?topicNames=${enc(`${T.tide},${T.shift}`)}`);
await api('GET', `/api/topics-offsets?topicNames=${enc(`${T.stone},${T.oil}`)}&timestamp=-1`);
// write path on a scratch topic and a scratch subject: create, edit, re-read, delete, re-read
await api('POST', '/api/topics', { topicName: SCRATCH, partitionCount: 1, replicationFactor: 1, configs: [{ name: 'cleanup.policy', value: 'delete' }] });
await api('PATCH', `/api/topics/${enc(SCRATCH)}/configuration`, { configs: [{ key: 'retention.ms', op: 'SET', value: '3600000' }] });
await api('POST', '/api/topics-records', { topicNames: [SCRATCH], compressionType: 0, useTransactions: false,
  records: [{ key: b64('trial-1'), value: b64(JSON.stringify({ lamp: 'Copperfield Annex test lamp', burn_hours: 6, checked_by: 'Tomas Vey' })), headers: [], partitionId: -1 }] });
await api('GET', `/api/topics/${enc(SCRATCH)}/partitions`);
await api('GET', `/api/topics-configs?topicNames=${enc(SCRATCH)}&configKeys=${enc('retention.ms,cleanup.policy')}`);
const subj = `${SCRATCH}-value`;
await api('POST', `/api/schema-registry/subjects/${enc(subj)}/versions`, { schemaType: 'AVRO', references: [], params: { normalize: false },
  schema: JSON.stringify({ type: 'record', name: 'LampTrial', namespace: 'com.example.annex', fields: [{ name: 'lamp', type: 'string' }, { name: 'burn_hours', type: 'int' }] }) });
await api('GET', `/api/schema-registry/subjects/${enc(subj)}/versions/latest`);
await api('DELETE', `/api/schema-registry/subjects/${enc(subj)}?permanent=false`);
await api('DELETE', `/api/schema-registry/subjects/${enc(subj)}?permanent=true`);
await api('DELETE', `/api/topics/${enc(SCRATCH)}`);
// Re-read the lists only: the broker runs with auto_create_topics_enabled (dev-container mode), so naming the deleted
// topic again (partitions, configs) would quietly recreate it.
await api('GET', '/api/topics');
await api('GET', '/api/schema-registry/subjects');
await settle(500);
await context.close(); // flushes the HAR
if (browser) await browser.close();
log(`HAR written to ${HAR}`);
console.log(HAR);
