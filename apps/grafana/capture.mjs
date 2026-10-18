// Step 3: drive Grafana with snap Chromium through playwright-core and record a HAR with embedded bodies.
// Login through the UI, visit the main pages, then issue a scripted JSON API sequence from inside the page with fetch.
import fs from 'node:fs';
import path from 'node:path';
import { chromium } from 'playwright-core';

const HERE = path.dirname(new URL(import.meta.url).pathname);
const BASE = process.env.BASE_URL || 'http://127.0.0.1:3101';
const HAR = process.env.HAR_PATH || path.join(HERE, 'grafana.full.har');
const EXE = process.env.CHROMIUM || '/snap/bin/chromium';
const PROFILE = path.join(HERE, 'profile');
const admin = Object.fromEntries(fs.readFileSync(path.join(HERE, '.admin'), 'utf8').split('\n').filter(Boolean).map((l) => l.split('=', 2)));
const USER = 'rea-admin';
const PASS = admin.ADMIN_PASSWORD;
if (!PASS) throw new Error('ADMIN_PASSWORD missing from .admin');

const log = (m) => console.error(`[capture] ${m}`);
fs.rmSync(PROFILE, { recursive: true, force: true });
const context = await chromium.launchPersistentContext(PROFILE, {
  executablePath: EXE, headless: true, args: ['--no-sandbox', '--disable-gpu'], viewport: { width: 1400, height: 900 },
  recordHar: { path: HAR, content: 'embed', mode: 'full' },
});
const page = await context.newPage();
const settle = async (ms = 1500) => { await page.waitForLoadState('networkidle', { timeout: 20000 }).catch(() => {}); await page.waitForTimeout(ms); };
const visit = async (p) => { log(`visit ${p}`); await page.goto(`${BASE}${p}`, { waitUntil: 'domcontentloaded' }); await settle(); };
const calls = [];
const api = async (method, p, body) => {
  const res = await page.evaluate(async ({ method, p, body }) => {
    const r = await fetch(p, { method, headers: { 'content-type': 'application/json', accept: 'application/json', 'x-grafana-org-id': '1' }, body: body === undefined ? undefined : JSON.stringify(body) });
    const text = await r.text();
    return { status: r.status, text: text.slice(0, 4000) };
  }, { method, p, body });
  log(`${method} ${p} -> ${res.status}`);
  calls.push({ method, path: p, status: res.status });
  let json = null; try { json = JSON.parse(res.text); } catch {}
  return json;
};

// Login through the UI.
await visit('/login');
const userBox = page.locator('input[name="user"], [data-testid="data-testid Username input field"]').first();
const passBox = page.locator('input[name="password"], [data-testid="data-testid Password input field"]').first();
await userBox.fill(USER);
await passBox.fill(PASS);
await page.locator('button[type="submit"], [data-testid="data-testid Login button"]').first().click();
await page.waitForURL((u) => !u.pathname.startsWith('/login'), { timeout: 20000 }).catch(() => {});
const skip = page.getByRole('button', { name: /skip/i });
if (await skip.count()) { await skip.first().click().catch(() => {}); }
await settle();
log(`logged in, at ${page.url()}`);

// Main pages.
for (const p of ['/dashboards', '/connections/datasources', '/admin/users', '/admin/teams', '/explore', '/alerting/list', '/d/granite-ledger/granite-ledger-overview', '/d/blue-heron-kitchen/blue-heron-kitchen-ops']) {
  await visit(p);
}

// Scripted JSON API sequence: lists, reads by id, searches, create/update/read/delete of scratch objects, re-reads.
await api('GET', '/api/health');
await api('GET', '/api/org');
await api('GET', '/api/user');
const ada = await api('GET', '/api/users/lookup?loginOrEmail=ada.finch');
if (ada?.id) { await api('GET', `/api/users/${ada.id}`); await api('GET', `/api/users/${ada.id}/teams`); }
const teams = await api('GET', '/api/teams/search?name=Night%20Shift');
const teamId = teams?.teams?.[0]?.id;
if (teamId) { await api('GET', `/api/teams/${teamId}`); await api('GET', `/api/teams/${teamId}/members`); }
await api('GET', '/api/folders');
await api('GET', '/api/folders/lighthouse-rota');
await api('GET', '/api/search?query=Granite&type=dash-db');
await api('GET', '/api/search?query=&tag=kitchen&type=dash-db');
await api('GET', '/api/search?folderUIDs=lighthouse-rota');
await api('GET', '/api/dashboards/uid/granite-ledger');
await api('GET', '/api/dashboards/uid/granite-ledger/versions');
await api('GET', '/api/dashboards/uid/blue-heron-kitchen');
await api('GET', '/api/datasources');
await api('GET', '/api/datasources/uid/rea-testdata');
await api('GET', '/api/annotations?dashboardUID=granite-ledger&limit=10');
await api('GET', '/api/annotations?tags=seed&tags=audit&limit=10');
const playlists = await api('GET', '/api/playlists');
const plUid = Array.isArray(playlists) ? playlists[0]?.uid : undefined;
if (plUid) { await api('GET', `/api/playlists/${plUid}`); await api('GET', `/api/playlists/${plUid}/items`); }
await api('GET', '/api/org/users');
await api('GET', '/api/teams/search?query=Night');
await api('GET', '/api/users/search?query=ada&perpage=10&page=1');

// Scratch objects: create folder + dashboard, update the folder, read both back, delete both, re-read after delete.
const sf = await api('POST', '/api/folders', { uid: 'scratch-pier', title: 'Scratch Pier' });
const sd = await api('POST', '/api/dashboards/db', { folderUid: sf?.uid || 'scratch-pier', overwrite: false, message: 'scratch', dashboard: { uid: 'scratch-tide', title: 'Scratch Tide Table', tags: ['scratch'], schemaVersion: 39, panels: [{ id: 1, type: 'text', title: 'Tide Notes', gridPos: { x: 0, y: 0, w: 12, h: 6 }, options: { mode: 'markdown', content: 'High tide at the scratch pier is 14:10.' } }] } });
await api('PUT', '/api/folders/scratch-pier', { title: 'Scratch Pier Renamed', overwrite: true });
await api('GET', '/api/folders/scratch-pier');
await api('GET', `/api/dashboards/uid/${sd?.uid || 'scratch-tide'}`);
await api('GET', '/api/search?query=Scratch&type=dash-db');
await api('DELETE', `/api/dashboards/uid/${sd?.uid || 'scratch-tide'}`);
await api('DELETE', '/api/folders/scratch-pier');
await api('GET', `/api/dashboards/uid/${sd?.uid || 'scratch-tide'}`);
await api('GET', '/api/folders/scratch-pier');
await api('GET', '/api/folders');

await settle(500);
await context.close(); // flushes the HAR
fs.writeFileSync(path.join(HERE, 'capture-calls.json'), JSON.stringify(calls, null, 2));
log(`HAR written to ${HAR} (${fs.statSync(HAR).size} bytes); ${calls.length} scripted calls`);
console.log(HAR);
