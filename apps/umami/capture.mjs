// Drive the showcase Umami UI with Chromium via playwright-core and record a HAR with bodies.
// Login through the UI form, visit the main pages, then a scripted read/write/read sequence through fetch from inside the
// page. Umami's UI keeps its bearer token in localStorage ("umami.auth"), not in a cookie, so the scripted calls read it there
// and send it as an Authorization header, exactly as the UI does; scope_har.py strips that header from the HAR.
import { chromium } from 'playwright-core';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

const BASE = process.env.BASE_URL || 'http://127.0.0.1:3215';
const DIR = process.env.CAPTURE_DIR || path.join(os.homedir(), 'capture', 'umami');
const HAR = process.env.HAR_PATH || path.join(DIR, 'umami.full.har');
const EXE = process.env.CHROMIUM_PATH || '/snap/bin/chromium';
const admin = Object.fromEntries(fs.readFileSync(path.join(DIR, '.admin'), 'utf8').split('\n').filter((l) => l.includes('='))
  .map((l) => { const i = l.indexOf('='); return [l.slice(0, i), l.slice(i + 1)]; }));
const USER = 'rea-admin'; const PASS = admin.UMAMI_ADMIN_PASSWORD;
const ids = JSON.parse(fs.readFileSync(path.join(DIR, 'seed-ids.json'), 'utf8'));
const log = (m) => console.error(`[capture] ${m}`);

const launchOpts = { executablePath: EXE, headless: true, args: ['--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu'] };
const harOpts = { recordHar: { path: HAR, content: 'embed', mode: 'full' }, viewport: { width: 1440, height: 900 } };
let browser = null; let context;
if (process.env.USER_DATA_DIR) {
  context = await chromium.launchPersistentContext(process.env.USER_DATA_DIR, { ...launchOpts, ...harOpts });
} else {
  browser = await chromium.launch(launchOpts);
  context = await browser.newContext(harOpts);
}
// The UI loads website favicons from a third-party icon service; keep the browser on the app's own origin.
await context.route((url) => !url.href.startsWith(BASE), (route) => route.abort());
const page = context.pages()[0] || await context.newPage();
page.setDefaultTimeout(45000);

const settle = async (ms = 1500) => { await page.waitForLoadState('networkidle', { timeout: 20000 }).catch(() => {}); await page.waitForTimeout(ms); };
const visit = async (p, ms) => { log(`visit ${p}`); await page.goto(`${BASE}${p}`, { waitUntil: 'domcontentloaded' }); await settle(ms); };
const nav = async (href) => {
  const link = page.locator(`a[href="${href}"]`).first();
  if (await link.count() && await link.isVisible().catch(() => false)) { log(`click ${href}`); await link.click(); await settle(2000); }
  else await visit(href, 2000);
};
const api = async (method, p, body) => {
  const res = await page.evaluate(async ({ method, p, body }) => {
    let token = localStorage.getItem('umami.auth') || '';
    try { token = JSON.parse(token); } catch {}
    const headers = { accept: 'application/json', authorization: `Bearer ${token}` };
    if (body !== undefined) headers['content-type'] = 'application/json';
    const r = await fetch(p, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });
    return { status: r.status, text: await r.text() };
  }, { method, p, body });
  log(`${method} ${p} -> ${res.status}`);
  try { return JSON.parse(res.text); } catch { return null; }
};

// --- login through the UI form ---
await visit('/login', 1000);
await page.locator('input[name="username"]').fill(USER);
await page.locator('input[name="password"]').fill(PASS);
await Promise.all([page.waitForURL((u) => !u.pathname.startsWith('/login'), { timeout: 45000 }), page.locator('button[type="submit"]').click()]);
await settle(2500);
log(`logged in, landed on ${new URL(page.url()).pathname}`);

const W = ids.websites; const rota = W['Lighthouse Rota Portal']; const ledger = W['Granite Ledger Docs']; const heron = W['Blue Heron Kitchen'];
const T = ids.teams;

// --- main UI pages ---
for (const p of ['/websites', `/websites/${ledger}`, `/websites/${rota}/events`, `/websites/${heron}/sessions`, '/links', '/pixels', '/boards', '/teams', '/admin/users']) {
  await nav(p);
}

// --- scripted API sequence from inside the page ---
const end = Date.now(); const start = end - 7 * 86400 * 1000; const win = `startAt=${start}&endAt=${end}`;
await api('GET', '/api/me');
await api('GET', '/api/websites?page=1&pageSize=20&includeTeams=1');
for (const id of [rota, ledger, heron]) await api('GET', `/api/websites/${id}`);
await api('GET', '/api/teams?page=1&pageSize=20');
for (const id of Object.values(T)) { await api('GET', `/api/teams/${id}`); await api('GET', `/api/teams/${id}/users`); }
await api('GET', `/api/teams/${T['Saltmarsh Depot Analytics']}/websites`);
await api('GET', '/api/admin/users?page=1&pageSize=20');
for (const u of ['ada.finch', 'tomas.vey', 'rea-admin']) await api('GET', `/api/users/${ids.users[u]}`);
await api('GET', `/api/users/${ids.users['ada.finch']}/teams`);
await api('GET', '/api/links?page=1&pageSize=20');
await api('GET', `/api/links/${ids.links['Tide Table Signup']}`);
await api('GET', '/api/pixels?page=1&pageSize=20');
await api('GET', `/api/pixels/${ids.pixels['Granite Ledger Newsletter Pixel']}`);
await api('GET', '/api/boards?page=1&pageSize=20');
await api('GET', `/api/boards/${ids.boards['Night Shift Overview']}`);
await api('GET', `/api/websites/${ledger}/annotations`);
await api('GET', `/api/websites/${ledger}/annotations/${ids.annotations['Granite Ledger Docs']}`);
await api('GET', `/api/websites/${heron}/segments?type=segment`);
await api('GET', `/api/websites/${heron}/segments/${ids.segments['Kelp Broth Readers']}`);
await api('GET', `/api/websites/${ledger}/goals`);
await api('GET', `/api/websites/${ledger}/goals/${ids.goals['Ledger PDF Downloads']}`);
await api('GET', `/api/websites/${rota}/funnels`);
await api('GET', `/api/websites/${rota}/funnels/${ids.funnels['Rota Signup Funnel']}`);
// statistics over the seeded traffic (the last seven days)
await api('GET', `/api/websites/${rota}/stats?${win}`);
await api('GET', `/api/websites/${rota}/metrics?${win}&type=title`);
await api('GET', `/api/websites/${ledger}/metrics?${win}&type=referrer`);
await api('GET', `/api/websites/${heron}/metrics?${win}&type=browser`);
await api('GET', `/api/websites/${rota}/metrics?${win}&type=event`);
await api('GET', `/api/websites/${heron}/pageviews?${win}&unit=day&timezone=UTC`);
await api('GET', `/api/websites/${rota}/event-data/properties?${win}`);
await api('GET', `/api/websites/${ledger}/event-data/values?${win}&event=download-ledger-pdf&propertyName=quarter`);
await api('GET', `/api/websites/${rota}/session-data/properties?${win}`);
await api('GET', `/api/websites/${rota}/session-data/values?${win}&propertyName=crew`);
const sessions = await api('GET', `/api/websites/${rota}/sessions?${win}&page=1&pageSize=20`);
const sid = (sessions?.data || [])[0]?.id;
if (sid) {
  await api('GET', `/api/websites/${rota}/sessions/${sid}`);
  await api('GET', `/api/websites/${rota}/sessions/${sid}/activity?${win}`);
  await api('GET', `/api/websites/${rota}/sessions/${sid}/properties`);
}
await api('GET', `/api/websites/${ledger}/events?${win}&page=1&pageSize=20`);
await api('GET', `/api/websites/${ledger}/daterange`);
// a search
await api('GET', '/api/websites?page=1&pageSize=20&includeTeams=1&search=heron');
// write path on a scratch website: create, edit, re-read, delete, re-read
const created = await api('POST', '/api/websites', { name: 'Rea scratch website', domain: 'scratch.lighthouse-rota.example.test' });
if (created?.id) {
  const upd = await api('POST', `/api/websites/${created.id}`, { name: 'Rea scratch website (edited)', domain: 'scratch.lighthouse-rota.example.test' });
  log(`scratch website edited -> ${upd?.name}`);
  await api('GET', `/api/websites/${created.id}`);
  await api('DELETE', `/api/websites/${created.id}`);
  await api('GET', `/api/websites/${created.id}`);
}
await api('GET', '/api/websites?page=1&pageSize=20&includeTeams=1');
await settle(500);
await context.close(); // flushes the HAR
if (browser) await browser.close();
log(`HAR written to ${HAR}`);
console.log(HAR);
