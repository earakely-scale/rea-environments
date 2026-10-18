// Drive the showcase Keycloak admin console with Chromium via playwright-core and record a HAR with bodies.
// Login through the admin console (master realm login page), visit the main pages of the "lighthouse-rota" realm, then a
// scripted read/write/read sequence through fetch from inside the page. The console keeps its access token in memory
// (keycloak-js, 60 s lifespan in master), so the scripted calls take a bearer token from the admin-cli password grant inside
// the page and refresh it before it expires; the token request is outside the scoped paths and headers are stripped anyway.
import { chromium } from 'playwright-core';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

const BASE = process.env.BASE_URL || 'http://127.0.0.1:3210';
const DIR = process.env.CAPTURE_DIR || path.join(os.homedir(), 'capture', 'keycloak');
const HAR = process.env.HAR_PATH || path.join(DIR, 'keycloak.full.har');
const EXE = process.env.CHROMIUM_PATH || '/snap/bin/chromium';
const admin = Object.fromEntries(fs.readFileSync(path.join(DIR, '.admin'), 'utf8').split('\n').filter((l) => l.includes('='))
  .map((l) => { const i = l.indexOf('='); return [l.slice(0, i), l.slice(i + 1)]; }));
const USER = 'rea-admin'; const PASS = admin.KC_ADMIN_PASSWORD;
const ids = JSON.parse(fs.readFileSync(path.join(DIR, 'seed-ids.json'), 'utf8'));
const RL = ids.realm; const R = `/admin/realms/${RL}`;
const log = (m) => console.error(`[capture] ${m}`);

const launchOpts = { executablePath: EXE, headless: true, args: ['--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu'] };
const harOpts = { recordHar: { path: HAR, content: 'embed', mode: 'full' } };
let browser = null; let context;
if (process.env.USER_DATA_DIR) {
  context = await chromium.launchPersistentContext(process.env.USER_DATA_DIR, { ...launchOpts, ...harOpts });
} else {
  browser = await chromium.launch(launchOpts);
  context = await browser.newContext(harOpts);
}
const page = context.pages()[0] || await context.newPage();
page.setDefaultTimeout(45000);

const settle = async (ms = 1500) => { await page.waitForLoadState('networkidle', { timeout: 20000 }).catch(() => {}); await page.waitForTimeout(ms); };
// A hash-only change keeps the console on its current realm, so every page visit is a full reload.
const visit = async (p, ms) => { log(`visit ${p}`); await page.goto(`${BASE}${p}`, { waitUntil: 'domcontentloaded' }); await page.reload({ waitUntil: 'domcontentloaded' }); await settle(ms); };
const api = async (method, p, body) => {
  const res = await page.evaluate(async ({ method, p, body, u, pw }) => {
    const now = Date.now();
    if (!globalThis.__reaTok || globalThis.__reaTok.exp < now) {
      const form = new URLSearchParams({ grant_type: 'password', client_id: 'admin-cli', username: u, password: pw });
      const t = await (await fetch('/realms/master/protocol/openid-connect/token', { method: 'POST', body: form })).json();
      globalThis.__reaTok = { v: t.access_token, exp: now + (t.expires_in - 15) * 1000 };
    }
    const r = await fetch(p, { method, headers: { 'content-type': 'application/json', accept: 'application/json', authorization: `Bearer ${globalThis.__reaTok.v}` },
      body: body === undefined ? undefined : JSON.stringify(body) });
    return { status: r.status, text: await r.text(), location: r.headers.get('location') };
  }, { method, p, body, u: USER, pw: PASS });
  log(`${method} ${p} -> ${res.status} (${res.text.length} bytes)`);
  let json = null; try { json = JSON.parse(res.text); } catch {}
  return { status: res.status, json, location: res.location };
};

// --- login through the admin console ---
await page.goto(`${BASE}/admin/master/console/`, { waitUntil: 'domcontentloaded' });
await page.waitForSelector('input#username');
await page.fill('input#username', USER);
await page.fill('input#password', PASS);
await page.click('#kc-login');
await page.waitForURL((u) => u.pathname.startsWith('/admin/master/console'), { timeout: 45000 });
await settle(3000);
log(`logged in, landed on ${page.url().replace(BASE, '')}`);

// --- scripted read sequence from inside the page (first, so each tool's first record is a seeded object) ---
const U = ids.users; const G = ids.groups; const C = ids.clients;
await api('GET', R);
await api('GET', `${R}/users?briefRepresentation=true&first=0&max=20`);
for (const u of ['rui.castellanos', 'mina.okafor', 'tomas.vey', 'ada.finch']) await api('GET', `${R}/users/${U[u]}`);
await api('GET', `${R}/users?search=okafor`);
await api('GET', `${R}/users/${U['ada.finch']}/groups`);
await api('GET', `${R}/users/${U['rui.castellanos']}/role-mappings/realm`);
await api('GET', `${R}/users/${U['mina.okafor']}/role-mappings/clients/${C['blue-heron-kitchen-till']}`);
await api('GET', `${R}/groups?first=0&max=20`);
for (const g of ['Quarry Crew', 'Night Shift', 'Galley Team', 'Lamp Room Crew']) await api('GET', `${R}/groups/${G[g]}`);
await api('GET', `${R}/groups/${G['Night Shift']}/children`);
await api('GET', `${R}/groups/${G['Quarry Crew']}/members`);
await api('GET', `${R}/groups?search=galley`);
await api('GET', `${R}/clients?clientId=granite-ledger-portal`);
for (const c of ['blue-heron-kitchen-till', 'granite-ledger-portal']) await api('GET', `${R}/clients/${C[c]}`);
await api('GET', `${R}/clients/${C['granite-ledger-portal']}/roles`);
await api('GET', `${R}/clients/${C['blue-heron-kitchen-till']}/roles/till-operator`);
await api('GET', `${R}/roles`);
await api('GET', `${R}/roles/tide-keeper`);
await api('GET', `${R}/roles-by-id/${ids.roles['quarry-auditor']}`);
await api('GET', `${R}/roles/galley-steward/groups`);
await api('GET', `${R}/client-scopes/${ids.client_scopes['tide-tables']}`);
await api('GET', `${R}/organizations?first=0&max=10`);
for (const o of ['saltmarsh-depot', 'copperfield-annex']) await api('GET', `${R}/organizations/${ids.organizations[o]}`);
await api('GET', `${R}/organizations/${ids.organizations['saltmarsh-depot']}/members`);
await api('GET', `${R}/authentication/flows/${ids.flows['granite gate browser']}`);

// --- main console pages of the seeded realm (UI traffic) ---
for (const p of [`#/${RL}/users`, `#/${RL}/users/${U['ada.finch']}/settings`, `#/${RL}/groups`, `#/${RL}/clients`,
  `#/${RL}/clients/${C['granite-ledger-portal']}/settings`, `#/${RL}/roles`, `#/${RL}/client-scopes`, `#/${RL}/organizations`,
  `#/${RL}/authentication`, `#/${RL}/realm-settings`]) {
  await visit(`/admin/master/console/${p}`, 1500);
}

// write path on a scratch user: create, edit, re-read, delete, re-read, re-list. POST /users answers 201 with no body and no
// content type (the scoper drops it), so the scratch user is created through the partial-import endpoint, which answers JSON.
const created = await api('POST', `${R}/partialImport`, { ifResourceExists: 'SKIP', users: [{ username: 'rea-scratch-user', firstName: 'Scratch', lastName: 'Visitor', email: 'rea-scratch@example.test', enabled: true }] });
const sid = created.json?.results?.find((x) => x.resourceType === 'USER')?.id || (await api('GET', `${R}/users?username=rea-scratch-user&exact=true`)).json?.[0]?.id;
if (sid) {
  await api('PUT', `${R}/users/${sid}`, { firstName: 'Scratchy', lastName: 'Visitor', email: 'rea-scratch@example.test' });
  await api('GET', `${R}/users/${sid}`);
  await api('DELETE', `${R}/users/${sid}`);
  await api('GET', `${R}/users/${sid}`);
}
await api('GET', `${R}/users/count`);
await settle(500);
await context.close(); // flushes the HAR
if (browser) await browser.close();
log(`HAR written to ${HAR}`);
console.log(HAR);
