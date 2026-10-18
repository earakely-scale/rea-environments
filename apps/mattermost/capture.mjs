// Drive the seeded Mattermost Team Edition with the local Chromium via playwright-core and record a HAR with bodies.
// Login happens through the UI form; the credentials are read from the 600-mode .admin file and never logged.
import { chromium } from 'playwright-core';
import fs from 'node:fs';

const BASE = process.env.BASE_URL || 'http://127.0.0.1:3104';
const HAR = process.env.HAR_PATH || 'mattermost.full.har';
const CHROME = process.env.CHROME || '/snap/bin/chromium';
const dotenv = (p) => Object.fromEntries(fs.readFileSync(p, 'utf8').split('\n').filter((l) => l.includes('=') && !l.startsWith('#')).map((l) => { const i = l.indexOf('='); return [l.slice(0, i), l.slice(i + 1)]; }));
const admin = dotenv(process.env.ADMIN_FILE || '.admin');
const ids = JSON.parse(fs.readFileSync(process.env.IDS_FILE || 'seed-ids.json', 'utf8'));
const T = ids.team, C = ids.channels, U = ids.users;
const log = (m) => console.error(`[capture] ${m}`);

const browser = await chromium.launch({ executablePath: CHROME, headless: true, args: ['--no-sandbox'] });
const context = await browser.newContext({ recordHar: { path: HAR, content: 'embed', mode: 'full' }, viewport: { width: 1400, height: 900 } });
// skip the "open in desktop app or browser" landing page
await context.addInitScript(() => { try { localStorage.setItem('__landingPageSeen__', 'true'); } catch {} });
const page = await context.newPage();

const settle = async (ms = 1500) => { await page.waitForLoadState('networkidle', { timeout: 20000 }).catch(() => {}); await page.waitForTimeout(ms); };
const visit = async (path) => { log(`visit ${path}`); await page.goto(`${BASE}${path}`, { waitUntil: 'domcontentloaded' }); await settle(); };
const click = async (sel, label) => {
  const el = page.locator(sel).first();
  if (!(await el.count())) { log(`missing ${label}`); return false; }
  log(`click ${label}`);
  await el.click({ timeout: 5000 }).catch((e) => log(`click ${label} failed: ${e.message.split('\n')[0]}`));
  await settle(1000);
  return true;
};
// JSON calls issued from inside the page so they are browser traffic and land in the HAR; Mattermost wants the CSRF header on writes.
const api = async (method, path, body) => {
  const res = await page.evaluate(async ({ method, path, body }) => {
    const csrf = (document.cookie.match(/(?:^|; )MMCSRF=([^;]+)/) || [])[1] || '';
    const headers = { accept: 'application/json', 'x-requested-with': 'XMLHttpRequest' };
    if (csrf) headers['x-csrf-token'] = csrf;
    if (body !== undefined) headers['content-type'] = 'application/json';
    const r = await fetch(path, { method, headers, body: body === undefined ? undefined : JSON.stringify(body), credentials: 'same-origin' });
    const text = await r.text();
    return { status: r.status, text: text.slice(0, 4000) };
  }, { method, path, body });
  log(`${method} ${path} -> ${res.status}`);
  let json = null; try { json = JSON.parse(res.text); } catch {}
  return json;
};

// 1. login through the UI
await visit('/login');
await page.fill('#input_loginId', admin.MM_ADMIN_USER);
await page.fill('#input_password-input', admin.MM_ADMIN_PASS);
await page.click('#saveSetting');
await page.waitForURL((u) => !u.pathname.startsWith('/login'), { timeout: 20000 }).catch(() => {});
await settle();
log(`logged in, at ${new URL(page.url()).pathname}`);

// 2. team, each channel, the thread, members list, pinned, channel info, user settings
for (const name of ['granite-ledger', 'blue-heron-kitchen', 'night-shift', 'keel-room']) await visit(`/${T.name}/channels/${name}`);
await visit(`/${T.name}/pl/${ids.thread_replies[0].id}`);
await visit(`/${T.name}/threads`);
await visit(`/${T.name}/threads/${ids.thread_root}`);
await visit(`/${T.name}/channels/granite-ledger`);
await click('#member_rhs', 'channel members');
await click('#channelHeaderPinButton', 'pinned messages');
await click('#channel-info-btn', 'channel info');
if (await click('button[aria-label="Settings"]', 'user settings')) { await page.keyboard.press('Escape'); await settle(500); }

// 3. scripted JSON sequence: collections, seeded objects by id, searches, create/update/react/read/delete, re-reads
const tid = T.id, gl = C['granite-ledger'].id, bh = C['blue-heron-kitchen'].id, ns = C['night-shift'].id, kr = C['keel-room'].id;
await api('GET', '/api/v4/users/me');
await api('GET', '/api/v4/users/me/teams');
await api('GET', `/api/v4/teams/${tid}`);
await api('GET', `/api/v4/teams/name/${T.name}`);
await api('GET', `/api/v4/teams/${tid}/channels`);
await api('GET', `/api/v4/teams/${tid}/channels/name/granite-ledger`);
await api('GET', `/api/v4/teams/${tid}/stats`);
await api('GET', `/api/v4/teams/${tid}/members`);
for (const cid of [gl, bh, ns, kr]) { await api('GET', `/api/v4/channels/${cid}`); await api('GET', `/api/v4/channels/${cid}/posts?per_page=30`); }
await api('GET', `/api/v4/channels/${gl}/stats`);
await api('GET', `/api/v4/channels/${gl}/members`);
await api('GET', `/api/v4/channels/${bh}/members`);
await api('GET', `/api/v4/channels/${gl}/members/${U['ada.finch'].id}`);
await api('GET', `/api/v4/channels/${gl}/pinned`);
await api('GET', `/api/v4/posts/${ids.pinned}`);
await api('GET', `/api/v4/posts/${ids.thread_root}`);
await api('GET', `/api/v4/posts/${ids.thread_root}/thread`);
await api('GET', `/api/v4/posts/${ids.thread_replies[0].id}`);
await api('GET', `/api/v4/posts/${ids.reacted.post_id}/reactions`);
await api('GET', `/api/v4/users?in_team=${tid}&page=0&per_page=60`);
await api('GET', `/api/v4/users?in_channel=${kr}&page=0&per_page=60`);
for (const u of ['ada.finch', 'rui.castellanos']) { await api('GET', `/api/v4/users/${U[u].id}`); await api('GET', `/api/v4/users/username/${u}`); }
await api('GET', `/api/v4/users/${U['ada.finch'].id}/teams`);
await api('GET', `/api/v4/users/${U['rui.castellanos'].id}/teams/${tid}/channels`);
await api('POST', `/api/v4/teams/${tid}/posts/search`, { terms: 'ledger', is_or_search: false });
await api('POST', `/api/v4/teams/${tid}/posts/search`, { terms: 'handover', is_or_search: false });
await api('POST', '/api/v4/users/search', { term: 'ada', team_id: tid });
await api('POST', `/api/v4/teams/${tid}/channels/search`, { term: 'heron' });
const scratch = await api('POST', '/api/v4/posts', { channel_id: ns, message: 'Scratch post from the capture run: lamp test at 03:15.' });
if (scratch?.id) {
  await api('GET', `/api/v4/posts/${scratch.id}`);
  await api('PUT', `/api/v4/posts/${scratch.id}`, { id: scratch.id, message: 'Scratch post from the capture run: lamp test moved to 03:45.' });
  await api('POST', '/api/v4/reactions', { user_id: U.admin.id, post_id: scratch.id, emoji_name: 'white_check_mark' });
  await api('GET', `/api/v4/posts/${scratch.id}`);
  await api('GET', `/api/v4/posts/${scratch.id}/reactions`);
  await api('DELETE', `/api/v4/posts/${scratch.id}`);
  await api('GET', `/api/v4/posts/${scratch.id}`); // 404 after delete
}
await api('GET', `/api/v4/channels/${ns}/posts?per_page=30`);
await api('GET', '/api/v4/system/ping');

await settle(500);
await context.close(); // flushes the HAR
await browser.close();
log(`HAR written to ${HAR}`);
