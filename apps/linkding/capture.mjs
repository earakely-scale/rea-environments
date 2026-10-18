// Drive the showcase linkding with Chromium via playwright-core and record a HAR with bodies.
// Login through the Django login form, then a scripted read sequence through fetch from inside the page against /api/
// (DRF session authentication: the sessionid cookie is carried automatically, unsafe methods send X-CSRFToken from the
// ld_csrftoken cookie), the main UI pages, and a write sequence on scratch objects. linkding's own UI is server-rendered and
// does not call /api/, so the API traffic in this capture is the scripted sequence.
import { chromium } from 'playwright-core';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

const BASE = process.env.BASE_URL || 'http://127.0.0.1:3203';
const DIR = process.env.CAPTURE_DIR || path.join(os.homedir(), 'capture', 'linkding');
const HAR = process.env.HAR_PATH || path.join(DIR, 'linkding.full.har');
const EXE = process.env.CHROMIUM_PATH || '/snap/bin/chromium';
const admin = Object.fromEntries(fs.readFileSync(path.join(DIR, '.admin'), 'utf8').split('\n').filter((l) => l.includes('='))
  .map((l) => { const i = l.indexOf('='); return [l.slice(0, i), l.slice(i + 1)]; }));
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
const page = context.pages()[0] || await context.newPage();
page.setDefaultTimeout(45000);

const settle = async (ms = 1000) => { await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => {}); await page.waitForTimeout(ms); };
const visit = async (p, ms) => { log(`visit ${p}`); await page.goto(`${BASE}${p}`, { waitUntil: 'domcontentloaded' }); await settle(ms); };
const api = async (method, p, body) => {
  const res = await page.evaluate(async ({ method, p, body }) => {
    const csrf = (document.cookie.match(/(?:^|;\s*)(?:ld_)?csrftoken=([^;]+)/) || [])[1] || ''; // linkding names it ld_csrftoken
    const headers = { accept: 'application/json', ...(body === undefined ? {} : { 'content-type': 'application/json' }), ...(method === 'GET' ? {} : { 'X-CSRFToken': csrf }) };
    const r = await fetch(p, { method, headers, body: body === undefined ? undefined : JSON.stringify(body), credentials: 'same-origin' });
    return { status: r.status, text: await r.text() };
  }, { method, p, body });
  log(`${method} ${p} -> ${res.status}`);
  try { return JSON.parse(res.text); } catch { return null; }
};

// --- login through the UI ---
await visit('/login/', 500);
await page.fill('input[name="username"]', 'rea-admin'); // fixed, non-secret user name (compose LD_SUPERUSER_NAME)
await page.fill('input[name="password"]', admin.LD_SUPERUSER_PASSWORD);
await Promise.all([page.waitForURL((u) => !u.pathname.startsWith('/login'), { timeout: 45000 }), page.click('form [type="submit"]')]);
await settle(1000);
log(`logged in, landed on ${new URL(page.url()).pathname}`);

const B = ids.bookmarks; const T = ids.tags; const BU = ids.bundles;
// --- scripted reads ---
await api('GET', '/api/user/profile/');
await api('GET', '/api/bookmarks/');
await api('GET', `/api/bookmarks/${B['granite-count']}/`);
for (const k of ['heron-menu', 'depot-gates', 'annex-carts', 'rota-winter', 'tide-january']) await api('GET', `/api/bookmarks/${B[k]}/`);
await api('GET', '/api/bookmarks/?limit=2&offset=0');
await api('GET', '/api/bookmarks/?limit=2&offset=2');
await api('GET', '/api/bookmarks/?q=%23audit');
await api('GET', '/api/bookmarks/?q=kelp');
await api('GET', `/api/bookmarks/?bundle=${BU['quarry-depot']}`);
await api('GET', '/api/bookmarks/archived/');
await api('GET', '/api/bookmarks/archived/?q=tide');
await api('GET', '/api/bookmarks/shared/');
await api('GET', `/api/bookmarks/check/?url=${encodeURIComponent('https://saltmarsh-depot.example.test/gate-log')}`);
await api('GET', `/api/bookmarks/check/?url=${encodeURIComponent('https://granite-ledger.example.test/quarterly-count')}`);
await api('GET', `/api/bookmarks/${B['granite-count']}/assets/`);
await api('GET', `/api/bookmarks/${B['granite-count']}/assets/${ids.assets['granite-tally']}/`);
await api('GET', '/api/tags/');
await api('GET', '/api/tags/?limit=3&offset=3');
for (const name of ['saltmarsh-depot', 'granite-ledger', 'blue-heron-kitchen', 'copperfield-annex', 'lighthouse-rota', 'menus', 'audit', 'night-shift']) {
  if (T[name]) await api('GET', `/api/tags/${T[name]}/`);
}
await api('GET', '/api/bundles/');
await api('GET', `/api/bundles/${BU['kitchen']}/`);
await api('GET', `/api/bundles/${BU['quarry-depot']}/`);
await api('GET', `/api/bookmarks/?bundle=${BU['kitchen']}`);
// more filters and paging: walk the unarchived list one bookmark at a time, linkding search syntax, a check of an unsaved URL
for (let off = 0; off < 5; off++) await api('GET', `/api/bookmarks/?limit=1&offset=${off}`);
await api('GET', '/api/bookmarks/?q=!unread');
await api('GET', '/api/bookmarks/?q=%23lighthouse-rota');
await api('GET', '/api/bookmarks/?q=Okafor');
await api('GET', '/api/bookmarks/?q=%23audit%20%23granite-ledger');
await api('GET', '/api/bookmarks/archived/?q=%23copperfield-annex');
await api('GET', `/api/bookmarks/check/?url=${encodeURIComponent('https://lighthouse-rota.example.test/winter-shifts')}`);
await api('GET', `/api/bookmarks/check/?url=${encodeURIComponent('https://copperfield-annex.example.test/loading-bay')}`);
await api('GET', `/api/bookmarks/${B['heron-menu']}/assets/`);
await api('GET', '/api/tags/?limit=2&offset=6');

// --- main UI pages (server-rendered) ---
for (const p of ['/bookmarks', '/bookmarks?q=%23granite-ledger', '/bookmarks/archived', '/tags', '/bundles', '/settings']) await visit(p, 800);

// --- write path on scratch objects ---
const sb = await api('POST', '/api/bookmarks/?disable_scraping&disable_html_snapshot', {
  url: 'https://scratch.example.test/rea-capture', title: 'Rea scratch bookmark', description: 'Scratch bookmark written during the capture.',
  notes: '', tag_names: ['night-shift'], unread: true, shared: false,
});
if (sb?.id) {
  await api('PATCH', `/api/bookmarks/${sb.id}/`, { title: 'Rea scratch bookmark (edited)', unread: false });
  await api('POST', `/api/bookmarks/${sb.id}/archive/`);
  await api('GET', `/api/bookmarks/${sb.id}/`);
  await api('POST', `/api/bookmarks/${sb.id}/unarchive/`);
  await api('PUT', `/api/bookmarks/${sb.id}/`, { url: 'https://scratch.example.test/rea-capture', title: 'Rea scratch bookmark (replaced)', description: 'Replaced scratch bookmark.', notes: 'Scratch note.', tag_names: ['night-shift'] });
  await api('DELETE', `/api/bookmarks/${sb.id}/`);
  await api('GET', `/api/bookmarks/${sb.id}/`);
}
const st = await api('POST', '/api/tags/', { name: 'rea-scratch-tag' });
if (st?.id) { await api('GET', `/api/tags/${st.id}/`); await api('DELETE', `/api/tags/${st.id}/`); }
const sbu = await api('POST', '/api/bundles/', { name: 'Rea scratch bundle', search: 'scratch', any_tags: '', all_tags: '', excluded_tags: '' });
if (sbu?.id) { await api('PATCH', `/api/bundles/${sbu.id}/`, { name: 'Rea scratch bundle (edited)' }); await api('DELETE', `/api/bundles/${sbu.id}/`); }
await api('GET', '/api/bookmarks/');
await api('GET', '/api/bundles/');
await settle(300);
await context.close();
if (browser) await browser.close();
log(`HAR written to ${HAR}`);
console.log(HAR);
