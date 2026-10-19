// Drive the showcase Vault UI with Chromium via playwright-core and record a HAR with bodies.
// Sign in through the UI with the userpass admin, visit the main UI pages, then a scripted read/write/read sequence through
// fetch from inside the page. The UI keeps its client token in browser storage; the in-page helper reads it there and sends
// it as X-Vault-Token, so the token never reaches this script. scope_har.py drops the login exchange and every header.
import { chromium } from 'playwright-core';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

const BASE = process.env.BASE_URL || 'http://127.0.0.1:3303';
const DIR = process.env.CAPTURE_DIR || path.join(os.homedir(), 'capture', 'vault');
const HAR = process.env.HAR_PATH || path.join(DIR, 'vault.full.har');
const EXE = process.env.CHROMIUM_PATH || '/snap/bin/chromium';
const admin = Object.fromEntries(fs.readFileSync(path.join(DIR, '.admin'), 'utf8').split('\n').filter((l) => l.includes('='))
  .map((l) => { const i = l.indexOf('='); return [l.slice(0, i), l.slice(i + 1)]; }));
const ids = JSON.parse(fs.readFileSync(path.join(DIR, 'seed-ids.json'), 'utf8'));
const log = (m) => console.error(`[capture] ${m}`);

const launchOpts = { executablePath: EXE, headless: true, args: ['--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu'] };
const browser = await chromium.launch(launchOpts);
const context = await browser.newContext({ recordHar: { path: HAR, content: 'embed', mode: 'full' } });
const page = await context.newPage();
page.setDefaultTimeout(45000);

const settle = async (ms = 1500) => { await page.waitForLoadState('networkidle', { timeout: 25000 }).catch(() => {}); await page.waitForTimeout(ms); };
const visit = async (p, ms) => { log(`visit ${p}`); await page.goto(`${BASE}${p}`, { waitUntil: 'domcontentloaded' }); await settle(ms); };
const api = async (method, p, body) => {
  const res = await page.evaluate(async ({ method, p, body }) => {
    const find = (store) => {
      for (let i = 0; i < store.length; i++) {
        try { const v = JSON.parse(store.getItem(store.key(i))); if (v && typeof v.token === 'string' && /^hv[sb]\./.test(v.token)) return v.token; } catch {}
      }
      return null;
    };
    const tok = find(localStorage) || find(sessionStorage);
    if (!tok) return { status: -1, text: '' };
    const headers = { accept: 'application/json', 'X-Vault-Token': tok, 'X-Vault-Request': 'true' };
    if (body !== undefined) headers['content-type'] = 'application/json';
    const r = await fetch(p, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });
    return { status: r.status, text: await r.text() };
  }, { method, p, body });
  log(`${method} ${p} -> ${res.status}`);
  if (res.status === -1) throw new Error('no client token in browser storage after sign-in');
  try { return JSON.parse(res.text); } catch { return null; }
};

// --- sign in through the UI (userpass) ---
await visit('/ui/vault/auth?with=userpass', 1000);
await page.selectOption('select[name="selectedAuthMethod"]', 'userpass').catch(() => {});
await page.fill('input[name="username"]', admin.VAULT_ADMIN_USER);
await page.fill('input[name="password"]', admin.VAULT_ADMIN_PASSWORD);
await page.click('button[type="submit"]');
await page.waitForURL((u) => !u.pathname.startsWith('/ui/vault/auth'), { timeout: 45000 });
await settle(2500);
log(`signed in, landed on ${new URL(page.url()).pathname}`);

// --- main UI pages (UI traffic) ---
for (const p of ['/ui/vault/dashboard', '/ui/vault/secrets', '/ui/vault/secrets/rota-config/kv/list',
  '/ui/vault/secrets/rota-config/kv/lighthouse-rota%2Fshift-plan', '/ui/vault/secrets/ledger-config/kv/list',
  '/ui/vault/policies/acl', '/ui/vault/policy/acl/granite-ledger-ops', '/ui/vault/access',
  '/ui/vault/access/identity/entities', '/ui/vault/access/identity/groups']) {
  await visit(p, 1500);
}

// --- scripted API sequence from inside the page ---
const health = await api('GET', '/v1/sys/health');
log(`vault version ${health?.version}`);
await api('GET', '/v1/sys/mounts');
await api('GET', '/v1/sys/mounts/rota-config/tune');
await api('GET', '/v1/sys/auth');
await api('GET', '/v1/sys/policies/acl?list=true');
for (const p of ids.policies) await api('GET', `/v1/sys/policies/acl/${p}`);
await api('GET', '/v1/rota-config/metadata/?list=true');
await api('GET', '/v1/rota-config/metadata/lighthouse-rota/?list=true');
for (const k of ids.kv['rota-config']) await api('GET', `/v1/rota-config/data/${k}`);
await api('GET', '/v1/rota-config/metadata/saltmarsh-depot/inventory');
await api('GET', '/v1/rota-config/metadata/blue-heron-kitchen/menu-cycle');
await api('GET', '/v1/ledger-config/metadata/?list=true');
await api('GET', '/v1/ledger-config/data/granite-ledger/quarry-audit');
await api('GET', '/v1/ledger-config/metadata/granite-ledger/quarry-audit');
await api('GET', '/v1/rota-config/data/lighthouse-rota/shift-plan?version=1');
await api('GET', '/v1/identity/entity/id?list=true');
for (const id of Object.values(ids.entities)) await api('GET', `/v1/identity/entity/id/${id}`);
await api('GET', '/v1/identity/entity/name/rui-castellanos');
await api('GET', '/v1/identity/entity-alias/id?list=true');
for (const id of Object.values(ids.aliases).slice(0, 2)) await api('GET', `/v1/identity/entity-alias/id/${id}`);
await api('GET', '/v1/identity/group/id?list=true');
for (const id of Object.values(ids.groups)) await api('GET', `/v1/identity/group/id/${id}`);
await api('GET', '/v1/identity/group/name/blue-heron-kitchen-staff');
await api('GET', `/v1/auth/userpass/users?list=true`);

// --- write path on scratch objects: create, update, re-read, delete, re-read ---
const note = '/v1/rota-config/data/scratch/rea-scratch-note';
await api('POST', note, { data: { owner: 'Rea scratch', region: 'Copperfield Annex loading bay', tier: 'scratch tier' } });
await api('POST', note, { data: { owner: 'Rea scratch', region: 'Copperfield Annex loading bay', tier: 'scratch tier (edited)' } });
await api('GET', note);
await api('DELETE', '/v1/rota-config/metadata/scratch/rea-scratch-note');
await api('GET', note);
await api('PUT', '/v1/sys/policies/acl/rea-scratch-policy', { policy: 'path "rota-config/data/scratch/*" {\n  capabilities = ["read"]\n}\n' });
await api('GET', '/v1/sys/policies/acl/rea-scratch-policy');
await api('DELETE', '/v1/sys/policies/acl/rea-scratch-policy');
await api('GET', '/v1/sys/policies/acl/rea-scratch-policy');
const ent = await api('POST', '/v1/identity/entity', { name: 'rea-scratch-entity', metadata: { team: 'Copperfield Annex', desk: 'Scratch Desk' } });
const eid = ent?.data?.id;
if (eid) {
  await api('POST', `/v1/identity/entity/id/${eid}`, { metadata: { team: 'Copperfield Annex', desk: 'Scratch Desk (edited)' } });
  await api('GET', `/v1/identity/entity/id/${eid}`);
  await api('DELETE', `/v1/identity/entity/id/${eid}`);
  await api('GET', `/v1/identity/entity/id/${eid}`);
}
await api('GET', '/v1/rota-config/metadata/?list=true');
await api('GET', '/v1/identity/entity/id?list=true');
await settle(500);
await context.close(); // flushes the HAR
await browser.close();
log(`HAR written to ${HAR}`);
console.log(HAR);
