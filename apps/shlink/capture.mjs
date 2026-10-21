// Drive the showcase Shlink with Chromium via playwright-core and record a HAR with bodies.
// Shlink ships no web UI (the separate shlink-web-client is not part of this image), so the browser opens a page on the
// app origin (GET /rest/health, the public health document) and runs a scripted read/write/read sequence through fetch
// from that page against the REST API (/rest/v3). Shlink authenticates REST calls with an API key; the key comes from
// ~/capture/shlink/.admin and is sent as the X-Api-Key header, which scoping strips from the HAR.
import { chromium } from 'playwright-core';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { recordWrites } from '../record_writes.mjs'; // shipped to ~/capture/ next to scope_har.py

const BASE = process.env.BASE_URL || 'http://127.0.0.1:3206';
const DIR = process.env.CAPTURE_DIR || path.join(os.homedir(), 'capture', 'shlink');
const HAR = process.env.HAR_PATH || path.join(DIR, 'shlink.full.har');
const EXE = process.env.CHROMIUM_PATH || '/snap/bin/chromium';
const admin = Object.fromEntries(fs.readFileSync(path.join(DIR, '.admin'), 'utf8').split('\n').filter((l) => l.includes('='))
  .map((l) => { const i = l.indexOf('='); return [l.slice(0, i), l.slice(i + 1)]; }));
const ids = JSON.parse(fs.readFileSync(path.join(DIR, 'seed-ids.json'), 'utf8'));
const log = (m) => console.error(`[capture] ${m}`);

const browser = await chromium.launch({ executablePath: EXE, headless: true, args: ['--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu'] });
const context = await browser.newContext({ recordHar: { path: HAR, content: 'embed', mode: 'full' } });
const page = await context.newPage();
page.setDefaultTimeout(45000);

const api = async (method, p, body) => {
  const res = await page.evaluate(async ({ method, p, body, key }) => {
    const r = await fetch(p, { method, headers: { 'content-type': 'application/json', accept: 'application/json', 'x-api-key': key }, body: body === undefined ? undefined : JSON.stringify(body) });
    return { status: r.status, text: await r.text() };
  }, { method, p, body, key: admin.SHLINK_API_KEY });
  log(`${method} ${p} -> ${res.status} (${res.text.length} B)`);
  try { return JSON.parse(res.text); } catch { return null; }
};

// --- the app origin page the fetches run from (no bundled UI) ---
await page.goto(`${BASE}/rest/health`, { waitUntil: 'domcontentloaded' });
log(`opened ${new URL(page.url()).pathname}: ${(await page.innerText('body')).slice(0, 80)}`);

const SC = ids.short_codes; const D = ids.domains[0];
const byTitle = (t) => SC[t].shortCode;
const order = ['Granite Ledger quarterly stone count', 'January tide tables for Granite Point', 'Blue Heron Kitchen spring-tide menu',
  'Saltmarsh Depot lamp-oil manifest SO-4471', 'Copperfield Annex beacon rebuild notes', 'Lighthouse Rota binder index',
  'Smoked kelp broth recipe card', 'Night shift handover checklist'];
const dq = (t) => (SC[t].domain ? `?domain=${encodeURIComponent(SC[t].domain)}` : '');

await api('GET', '/rest/health');
await api('GET', '/rest/v3/short-urls?orderBy=title-ASC');
await api('GET', '/rest/v3/short-urls?searchTerm=heron');
await api('GET', '/rest/v3/short-urls?tags%5B%5D=granite-ledger');
await api('GET', '/rest/v3/short-urls?orderBy=visits-DESC&itemsPerPage=3');
await api('GET', '/rest/v3/short-urls?itemsPerPage=3&page=2');
await api('GET', `/rest/v3/short-urls?domain=${encodeURIComponent(D)}`);
await api('GET', '/rest/v3/short-urls?tagsMode=all&tags%5B%5D=lighthouse-rota&tags%5B%5D=granite-ledger');
await api('GET', '/rest/v3/short-urls?excludeMaxVisitsReached=true&excludePastValidUntil=true');
for (const t of order) await api('GET', `/rest/v3/short-urls/${byTitle(t)}${dq(t)}`);
await api('GET', '/rest/v3/short-urls/depot-manifest'); // the custom-domain link is not found without ?domain= (404)
await api('GET', '/rest/v3/short-urls?searchTerm=granite&orderBy=dateCreated-DESC');
for (const t of order) await api('GET', `/rest/v3/short-urls/${byTitle(t)}/visits${dq(t)}`);
await api('GET', `/rest/v3/short-urls/${byTitle('Granite Ledger quarterly stone count')}/visits?excludeBots=true&itemsPerPage=5`);
await api('GET', `/rest/v3/short-urls/${byTitle('January tide tables for Granite Point')}/visits?startDate=${encodeURIComponent('2026-01-01T00:00:00+00:00')}`);
for (const t of order.slice(1).concat(order.slice(0, 1))) await api('GET', `/rest/v3/short-urls/${byTitle(t)}/redirect-rules${dq(t)}`);
await api('GET', '/rest/v3/tags');
await api('GET', '/rest/v3/tags/stats');
await api('GET', '/rest/v3/tags/stats?orderBy=visits-DESC');
await api('GET', '/rest/v3/tags?searchTerm=heron');
await api('GET', '/rest/v3/tags/stats?searchTerm=rota');
for (const tag of ['blue-heron-kitchen', 'granite-ledger', 'lighthouse-rota', 'saltmarsh-depot', 'copperfield-annex']) await api('GET', `/rest/v3/tags/${tag}/visits`);
await api('GET', '/rest/v3/tags/lighthouse-rota/visits?excludeBots=true&itemsPerPage=3');
await api('GET', '/rest/v3/domains');
await api('GET', `/rest/v3/domains/${encodeURIComponent(D)}/visits`);
await api('GET', '/rest/v3/domains/DEFAULT/visits');
await api('GET', '/rest/v3/domains/DEFAULT/visits?excludeBots=true&itemsPerPage=3');
await api('GET', '/rest/v3/visits');
await api('GET', '/rest/v3/visits/non-orphan');
await api('GET', '/rest/v3/visits/non-orphan?excludeBots=true&itemsPerPage=4');
await api('GET', `/rest/v3/visits/non-orphan?startDate=${encodeURIComponent('2026-01-01T00:00:00+00:00')}&itemsPerPage=5&page=2`);
await api('GET', '/rest/v3/visits/orphan');
await api('GET', '/rest/v3/visits/orphan?type=invalid_short_url');
await api('GET', '/rest/v3/mercure-info');
// writes on two scratch short URLs, each with its own custom slug
await recordWrites(api, {
  collection: '/rest/v3/short-urls', list: '/rest/v3/short-urls?orderBy=title-ASC', item: (code) => `/rest/v3/short-urls/${code}`,
  id: (s) => s?.shortCode,
  create: (n) => ({ longUrl: `https://lighthouse-rota.example.test/scratch-${n}`, customSlug: `rea-scratch-${n}`,
    title: `Rea scratch link ${n}`, tags: ['scratch'] }),
  update: (n) => ({ title: `Rea scratch link ${n} (edited)`, tags: ['scratch', 'lighthouse-rota'] }),
});
await context.close(); // flushes the HAR
await browser.close();
log(`HAR written to ${HAR}`);
console.log(HAR);
