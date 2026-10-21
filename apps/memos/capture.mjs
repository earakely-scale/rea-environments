// Drive the showcase Memos with Chromium via playwright-core and record a HAR with bodies.
// Login through the web UI, visit the main pages, then a scripted read/write/read sequence through fetch from inside the
// page. The Memos web UI talks Connect RPC with binary protobuf (POST /memos.api.v1.<Service>/<Method>,
// application/proto), which is not JSON, so the scripted sequence uses the same services through their JSON REST mapping
// under /api/v1. The UI keeps its short-lived access token in localStorage (`memos_access_token`, the refresh token is
// an HttpOnly cookie); the script reads it in the page and sends it as `Authorization: Bearer ...`. Headers are stripped
// by scoping. The writes create, edit and delete two scratch memos, each read back at once by name and in the memo list
// (record_writes.mjs).
import { chromium } from 'playwright-core';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { recordWrites } from '../record_writes.mjs'; // shipped to ~/capture/ next to scope_har.py

const BASE = process.env.BASE_URL || 'http://127.0.0.1:3205';
const DIR = process.env.CAPTURE_DIR || path.join(os.homedir(), 'capture', 'memos');
const HAR = process.env.HAR_PATH || path.join(DIR, 'memos.full.har');
const EXE = process.env.CHROMIUM_PATH || '/snap/bin/chromium';
const admin = Object.fromEntries(fs.readFileSync(path.join(DIR, '.admin'), 'utf8').split('\n').filter((l) => l.includes('='))
  .map((l) => { const i = l.indexOf('='); return [l.slice(0, i), l.slice(i + 1)]; }));
const ids = JSON.parse(fs.readFileSync(path.join(DIR, 'seed-ids.json'), 'utf8'));
const log = (m) => console.error(`[capture] ${m}`);

const browser = await chromium.launch({ executablePath: EXE, headless: true, args: ['--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu'] });
const context = await browser.newContext({ recordHar: { path: HAR, content: 'embed', mode: 'full' }, viewport: { width: 1440, height: 900 } });
const page = await context.newPage();
page.setDefaultTimeout(45000);

const settle = async (ms = 1500) => { await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => {}); await page.waitForTimeout(ms); };
const visit = async (p, ms) => { await page.goto(`${BASE}${p}`, { waitUntil: 'domcontentloaded' }); await settle(ms); log(`visit ${p} -> ${new URL(page.url()).pathname}`); };
const api = async (method, p, body) => {
  const res = await page.evaluate(async ({ method, p, body }) => {
    const tok = localStorage.getItem('memos_access_token');
    const r = await fetch(p, { method, headers: { 'content-type': 'application/json', accept: 'application/json', authorization: `Bearer ${tok}` }, body: body === undefined ? undefined : JSON.stringify(body) });
    return { status: r.status, text: await r.text() };
  }, { method, p, body });
  log(`${method} ${p} -> ${res.status} (${res.text.length} B)`);
  try { return JSON.parse(res.text); } catch { return null; }
};

// --- login through the web UI ---
await visit('/auth', 1500);
await page.fill('#signin-username', 'rea-admin');
await page.fill('#signin-password', admin.MEMOS_REA_ADMIN_PASSWORD);
await page.click('button[type="submit"]');
await page.waitForURL((u) => !u.pathname.startsWith('/auth'), { timeout: 45000 });
await settle(2000);
log(`logged in, landed on ${new URL(page.url()).pathname}`);

const M = ids.memos; const C = ids.comments; const SP = ids.spaces.crew; const VW = ids.views.granite;
const uid = (n) => n.split('/').pop();

// --- main UI pages (Connect/protobuf traffic, dropped by scoping as non-JSON) ---
for (const p of ['/', '/explore', '/archived', `/memos/${uid(M['stone-count'])}`, '/u/ada-finch', '/inbox', '/setting']) await visit(p, 1500);

// --- scripted JSON REST sequence from inside the page ---
await api('GET', '/api/v1/instance/profile');
await api('GET', '/api/v1/users');
for (const u of ['ada-finch', 'rea-admin', 'rui-castellanos', 'mina-okafor']) await api('GET', `/api/v1/users/${u}`);
await api('GET', '/api/v1/memos?pageSize=20');
await api('GET', '/api/v1/memos?state=ARCHIVED');
await api('GET', `/api/v1/memos?filter=${encodeURIComponent('"granite-ledger" in tags')}`);
await api('GET', `/api/v1/memos?filter=${encodeURIComponent('content.contains("tide")')}`);
await api('GET', `/api/v1/memos?filter=${encodeURIComponent('pinned == true')}`);
await api('GET', `/api/v1/memos?filter=${encodeURIComponent('creator == "users/ada-finch"')}`);
await api('GET', `/api/v1/memos?filter=${encodeURIComponent('visibility == "PUBLIC"')}&orderBy=${encodeURIComponent('update_time asc')}`);
await api('GET', `/api/v1/users?filter=${encodeURIComponent("username == 'mina-okafor'")}`);
await api('GET', `/api/v1/memos?filter=${encodeURIComponent('has_task_list == true')}`);
await api('GET', `/api/v1/memos?filter=${encodeURIComponent('"lighthouse-rota" in tags')}`);
const order = ['kitchen', 'winter-rota', 'stone-count', 'lamp-oil', 'checklist', 'beacon', 'tide-table', 'cart-seven', 'crew-meeting'];
for (const k of order) await api('GET', `/api/v1/${M[k]}`);
for (const k of ['ada-on-rota', 'rui-on-count', 'admin-on-tide']) await api('GET', `/api/v1/${C[k]}`);
for (const k of ['winter-rota', 'stone-count', 'tide-table', 'kitchen', 'cart-seven', 'checklist', 'crew-meeting', 'lamp-oil']) await api('GET', `/api/v1/${M[k]}/comments`);
for (const k of ['stone-count', 'winter-rota', 'kitchen', 'checklist', 'tide-table', 'cart-seven']) await api('GET', `/api/v1/${M[k]}/reactions`);
for (const k of ['checklist', 'stone-count', 'winter-rota', 'tide-table']) await api('GET', `/api/v1/${M[k]}/relations`);
await api('GET', `/api/v1/${M['kitchen']}/attachments`);
await api('GET', '/api/v1/spaces');
await api('GET', `/api/v1/${SP}`);
await api('GET', `/api/v1/${SP}/members`);
await api('GET', `/api/v1/${SP}/invitations`);
await api('GET', `/api/v1/${SP}/invitations/mina-okafor`);
await api('GET', `/api/v1/${SP}/members/ada-finch`);
await api('GET', '/api/v1/users/rea-admin/spaceInvitations');
await api('GET', `/api/v1/${ids.spaces.kitchen}/invitations/rea-admin`);
await api('GET', '/api/v1/users/rea-admin/views');
await api('GET', `/api/v1/${VW}`);
await api('GET', '/api/v1/users/rea-admin/settings');
await api('GET', '/api/v1/users/rea-admin/settings/GENERAL');
await api('GET', '/api/v1/instance/stats');
await api('GET', '/api/v1/users/rea-admin/notifications');
// --- writes on two scratch memos ---
const memo = (name) => `/api/v1/${name}`;
const MEMO_LIST = '/api/v1/memos?pageSize=20';
const readMemo = async (name) => { await api('GET', memo(name)); await api('GET', MEMO_LIST); };
const scratch = await recordWrites(api, {
  collection: '/api/v1/memos', list: MEMO_LIST, item: memo, id: (m) => m?.name,
  create: (n) => ({ content: `#scratch Rea scratch memo ${n} written during the capture.`, visibility: 'PRIVATE' }),
  remove: false,
});
// an update names the field it changes in updateMask, which the helper's update path cannot carry
for (const [i, name] of scratch.entries()) {
  await api('PATCH', `${memo(name)}?updateMask=content`, { name, content: `#scratch Rea scratch memo ${i + 1} (edited).` });
  await readMemo(name);
}
for (const name of scratch) { await api('DELETE', memo(name)); await readMemo(name); }
await settle(500);
await context.close(); // flushes the HAR
await browser.close();
log(`HAR written to ${HAR}`);
console.log(HAR);
