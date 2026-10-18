// Drive the showcase EspoCRM with Chromium via playwright-core and record a HAR with bodies.
// Login through the web client, visit the main list and detail views, then a scripted read/write/read sequence through
// fetch from inside the page. The web client authenticates its API calls with `Espo-Authorization` /
// `Espo-Authorization-By-Token` headers carrying the session token; the script copies those header values from the
// client's own first API request (kept in memory only, never logged) and passes them to its fetch calls. The scoping step
// strips every header except content-type/accept, and drops /api/v1/App/user (the sign-in reply that carries the token).
import { chromium } from 'playwright-core';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

const BASE = process.env.BASE_URL || 'http://127.0.0.1:3216';
const DIR = process.env.CAPTURE_DIR || path.join(os.homedir(), 'capture', 'espocrm');
const HAR = process.env.HAR_PATH || path.join(DIR, 'espocrm.full.har');
const EXE = process.env.CHROMIUM_PATH || '/snap/bin/chromium';
const admin = Object.fromEntries(fs.readFileSync(path.join(DIR, '.admin'), 'utf8').split('\n').filter((l) => l.includes('='))
  .map((l) => { const i = l.indexOf('='); return [l.slice(0, i), l.slice(i + 1)]; }));
const USER = 'rea-admin'; const PASS = admin.ESPO_ADMIN_PASSWORD; // .admin holds secrets only (envbuild greps the HAR for every value in it)
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

// Remember the auth headers of the web client's first token-authenticated API request (values never printed).
let authHeaders = null;
page.on('request', (req) => {
  if (authHeaders || !req.url().startsWith(`${BASE}/api/v1/`)) return;
  const h = req.headers();
  if (h['espo-authorization'] && h['espo-authorization-by-token'] === 'true') {
    authHeaders = { 'Espo-Authorization': h['espo-authorization'], 'Espo-Authorization-By-Token': 'true' };
  }
});

const settle = async (ms = 1500) => { await page.waitForLoadState('networkidle', { timeout: 25000 }).catch(() => {}); await page.waitForTimeout(ms); };
const visit = async (hash, ms) => { log(`visit #${hash}`); await page.goto(`${BASE}/#${hash}`, { waitUntil: 'domcontentloaded' }); await settle(ms); };
let calls = 0;
const api = async (method, p, body) => {
  const res = await page.evaluate(async ({ method, p, body, headers }) => {
    const r = await fetch(`/api/v1/${p}`, { method, headers: { ...headers, 'content-type': 'application/json', accept: 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body) });
    return { status: r.status, text: await r.text() };
  }, { method, p, body, headers: authHeaders });
  calls += 1; log(`${method} /api/v1/${p} -> ${res.status}`);
  try { return JSON.parse(res.text); } catch { return null; }
};

// --- login through the web client ---
await page.goto(`${BASE}/`, { waitUntil: 'domcontentloaded' });
await page.waitForSelector('#field-userName');
await page.fill('#field-userName', USER);
await page.fill('#field-password', PASS);
await page.click('#btn-login');
await page.waitForSelector('#navbar', { state: 'attached', timeout: 45000 });
await settle(2500);
log(`logged in; auth headers captured: ${authHeaders ? 'yes' : 'no'}`);

const acc = ids.accounts; const con = ids.contacts; const opp = ids.opportunities;
const first = (o) => Object.values(o)[0];

// --- main pages (web-client traffic) ---
for (const [h, ms] of [['Account', 1500], [`Account/view/${acc['Granite Ledger Holdings']}`, 2500], ['Contact', 1500],
  [`Contact/view/${con['Ada Finch']}`, 2000], ['Lead', 1500], ['Opportunity', 1500], [`Opportunity/view/${first(opp)}`, 2000],
  ['Case', 1500], ['Task', 1500], ['KnowledgeBaseArticle', 1500]]) {
  await visit(h, ms);
}
if (!authHeaders) throw new Error('the web client made no token-authenticated API request');

// --- scripted API sequence from inside the page ---
// collections
for (const e of ['Account', 'Contact', 'Lead', 'Opportunity', 'Case', 'Task', 'Meeting', 'Call', 'KnowledgeBaseArticle', 'Campaign', 'TargetList', 'Team']) {
  await api('GET', `${e}?maxSize=20&offset=0&orderBy=createdAt&order=asc`);
}
// every seeded object by id
const byId = [['Account', ids.accounts], ['Contact', ids.contacts], ['Lead', ids.leads], ['Opportunity', ids.opportunities],
  ['Case', ids.cases], ['Task', ids.tasks], ['Meeting', ids.meetings], ['Call', ids.calls], ['KnowledgeBaseArticle', ids.kb],
  ['Campaign', ids.campaigns], ['TargetList', ids.targetLists], ['Team', ids.teams], ['User', ids.users]];
for (const [e, objs] of byId) for (const id of Object.values(objs)) await api('GET', `${e}/${id}`);
// related records
// (related lists answer with ids only unless `select` names the attributes)
await api('GET', `Account/${acc['Granite Ledger Holdings']}/contacts?select=name,firstName,lastName,emailAddress,description&maxSize=10`);
await api('GET', `Account/${acc['Blue Heron Kitchen']}/opportunities?select=name,stage,amount,amountCurrency,closeDate,description&maxSize=10`);
await api('GET', `Account/${acc['Saltmarsh Depot']}/cases?select=name,number,status,priority,type,description&maxSize=10`);
await api('GET', `Account/${acc['Granite Ledger Holdings']}/stream?maxSize=10`);
// searches and filters
// brackets percent-encoded, as the web client does (a raw `[` makes the HAR URL fail rea's uri format check)
const where = (type, attribute, value) => new URLSearchParams({ 'where[0][type]': type, 'where[0][attribute]': attribute, 'where[0][value]': value }).toString();
await api('GET', `Account?${where('equals', 'industry', 'Shipping')}&maxSize=10`);
await api('GET', `Contact?textFilter=${encodeURIComponent('Okafor')}&maxSize=10`);
await api('GET', `Opportunity?${where('greaterThan', 'amount', '10000')}&orderBy=amount&order=desc&maxSize=10`);
await api('GET', `Case?${where('equals', 'priority', 'Urgent')}&maxSize=10`);
// write path on a scratch task: create, update, re-read, delete, re-read
const created = await api('POST', 'Task', { name: 'Rea scratch task', status: 'Not Started', priority: 'Low', dateEndDate: '2026-11-30',
  assignedUserId: first(ids.users), parentType: 'Account', parentId: acc['Copperfield Annex'], description: 'Scratch task written during the capture.' });
if (created?.id) {
  const upd = await api('PUT', `Task/${created.id}`, { name: 'Rea scratch task (edited)', status: 'Started', description: 'Edited scratch task.' });
  log(`scratch task edited -> ${upd?.name}`);
  await api('GET', `Task/${created.id}`);
  await api('DELETE', `Task/${created.id}`);
  await api('GET', `Task/${created.id}`);
}
await api('GET', 'Task?maxSize=20&offset=0&orderBy=createdAt&order=asc');
await settle(500);
await context.close(); // flushes the HAR
if (browser) await browser.close();
log(`${calls} scripted calls; HAR written to ${HAR}`);
console.log(HAR);
