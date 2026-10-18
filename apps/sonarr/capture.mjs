// Drive the showcase Sonarr with Chromium via playwright-core and record a HAR with bodies.
// Forms login through the UI, a few UI pages (the Sonarr UI itself calls /api/v3 with the X-Api-Key header it reads from
// window.Sonarr.apiKey), then a scripted read/write/read sequence of fetch calls from inside the page that sends the same
// header the UI sends. Headers never reach the scoped HAR. The capture never opens Settings > General and never calls
// /api/v3/config/host, whose response carries the API key and the password.
import { chromium } from 'playwright-core';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

const BASE = process.env.BASE_URL || 'http://127.0.0.1:3221';
const DIR = process.env.CAPTURE_DIR || path.join(os.homedir(), 'capture', 'sonarr');
const HAR = process.env.HAR_PATH || path.join(DIR, 'sonarr.full.har');
const EXE = process.env.CHROMIUM_PATH || '/snap/bin/chromium';
const admin = Object.fromEntries(fs.readFileSync(path.join(DIR, '.admin'), 'utf8').split('\n').filter((l) => l.includes('='))
  .map((l) => { const i = l.indexOf('='); return [l.slice(0, i), l.slice(i + 1)]; }));
const USER = 'rea-admin'; const PASS = admin.REA_ADMIN_PASSWORD;
const ids = JSON.parse(fs.readFileSync(path.join(DIR, 'seed-ids.json'), 'utf8'));
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

const settle = async (ms = 1500) => { await page.waitForLoadState('networkidle', { timeout: 20000 }).catch(() => {}); await page.waitForTimeout(ms); };
// Navigate inside the single-page app (one bootstrap of the UI's own API calls instead of one per page load).
const nav = async (p, ms) => {
  log(`visit ${p}`);
  await page.evaluate((p) => { window.history.pushState({}, '', p); window.dispatchEvent(new PopStateEvent('popstate', { state: {} })); }, p);
  await settle(ms);
};
const calls = [];
const api = async (method, p, body) => {
  const res = await page.evaluate(async ({ method, p, body }) => {
    const headers = { accept: 'application/json', 'x-api-key': window.Sonarr.apiKey };
    if (body !== undefined) headers['content-type'] = 'application/json';
    const r = await fetch(p, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });
    return { status: r.status, text: await r.text() };
  }, { method, p, body });
  log(`${method} ${p} -> ${res.status}`); calls.push({ method, path: p, status: res.status });
  try { return JSON.parse(res.text); } catch { return null; }
};

// --- forms login through the UI ---
log('visit /login');
await page.goto(`${BASE}/login`, { waitUntil: 'domcontentloaded' });
await page.fill('input[name="username"]', USER);
await page.fill('input[name="password"]', PASS);
await Promise.all([page.waitForURL((u) => !u.pathname.startsWith('/login'), { timeout: 45000 }), page.click('button[type="submit"]')]);
await settle(4000);
log(`logged in, landed on ${new URL(page.url()).pathname}`);

// --- main pages (UI traffic) ---
const PAGES = (process.env.PAGES || '/calendar,/activity/queue,/wanted/missing,/settings/profiles,/settings/customformats,/settings/tags,/settings/connect,/system/status').split(',');
for (const p of PAGES) await nav(p, 2000);

// --- scripted API sequence from inside the page (rootFolder/autoTagging spelled as the UI spells them) ---
const A = '/api/v3';
const st = await api('GET', `${A}/system/status`); log(`sonarr ${st?.version}`);
const first = (m, k) => [m[k], ...Object.values(m).filter((v) => v !== m[k])];
await api('GET', `${A}/tag`);
for (const id of first(ids.tags, 'granite-ledger')) await api('GET', `${A}/tag/${id}`);
await api('GET', `${A}/tag/detail`);
for (const id of [ids.tags['lighthouse-rota'], ids.tags['blue-heron-kitchen']]) await api('GET', `${A}/tag/detail/${id}`);
await api('GET', `${A}/rootFolder`);
for (const id of Object.values(ids.rootfolders)) await api('GET', `${A}/rootFolder/${id}`);
await api('GET', `${A}/customformat`);
for (const id of first(ids.customformats, 'Blue Heron Kitchen Subtitles')) await api('GET', `${A}/customformat/${id}`);
await api('GET', `${A}/qualityprofile`);
for (const id of first(ids.qualityprofiles, 'Granite Ledger Archive SD')) await api('GET', `${A}/qualityprofile/${id}`);
await api('GET', `${A}/releaseprofile`);
for (const id of first(ids.releaseprofiles, 'Tide Table Filter')) await api('GET', `${A}/releaseprofile/${id}`);
await api('GET', `${A}/delayprofile`);
for (const id of Object.keys(ids.delayprofiles).reverse()) await api('GET', `${A}/delayprofile/${id}`);
await api('GET', `${A}/notification`);
for (const id of first(ids.notifications, 'Night Shift Pager')) await api('GET', `${A}/notification/${id}`);
await api('GET', `${A}/importlistexclusion`);
for (const id of first(ids.importlistexclusions, 'The Saltmarsh Depot Hour')) await api('GET', `${A}/importlistexclusion/${id}`);
await api('GET', `${A}/importlistexclusion/paged?page=1&pageSize=10&sortKey=title&sortDirection=ascending`);
await api('GET', `${A}/autoTagging`);
for (const id of Object.values(ids.autotagging)) await api('GET', `${A}/autoTagging/${id}`);
const qd = await api('GET', `${A}/qualitydefinition`);
for (const q of (qd || []).filter((x) => ['HDTV-1080p', 'DVD'].includes(x.quality?.name))) await api('GET', `${A}/qualitydefinition/${q.id}`);
await api('GET', `${A}/language`);
await api('GET', `${A}/language/1`);
await api('GET', `${A}/config/naming`);
await api('GET', `${A}/config/mediamanagement`);
await api('GET', `${A}/config/ui`);
await api('GET', `${A}/health`);
await api('GET', `${A}/diskspace`);
await api('GET', `${A}/system/task`);
await api('GET', `${A}/calendar?start=2026-10-01T00:00:00Z&end=2026-10-31T23:59:59Z`);
await api('GET', `${A}/wanted/missing?page=1&pageSize=10&sortKey=airDateUtc&sortDirection=descending`);
await api('GET', `${A}/series`);
// write path on a scratch tag and a scratch release profile: create, update, read, delete, re-read
const tag = await api('POST', `${A}/tag`, { label: 'rea-scratch' });
if (tag?.id) {
  await api('PUT', `${A}/tag/${tag.id}`, { id: tag.id, label: 'rea-scratch-renamed' });
  await api('GET', `${A}/tag/${tag.id}`);
  await api('DELETE', `${A}/tag/${tag.id}`);
  await api('GET', `${A}/tag/${tag.id}`);
}
const rp = await api('POST', `${A}/releaseprofile`, { name: 'Rea Scratch Profile', enabled: true, required: ['repack'], ignored: [], indexerId: 0, tags: [] });
if (rp?.id) {
  await api('PUT', `${A}/releaseprofile/${rp.id}`, { ...rp, name: 'Rea Scratch Profile (edited)', ignored: ['sample'] });
  await api('DELETE', `${A}/releaseprofile/${rp.id}`);
}
await api('GET', `${A}/tag`);
await api('GET', `${A}/releaseprofile`);
await settle(500);
await context.close(); // flushes the HAR
if (browser) await browser.close();
fs.writeFileSync(path.join(DIR, 'capture-calls.json'), JSON.stringify(calls, null, 1));
log(`HAR written to ${HAR}; ${calls.length} scripted calls`);
console.log(HAR);
