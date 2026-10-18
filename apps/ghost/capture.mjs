// Drive the showcase Ghost admin with Chromium via playwright-core and record a HAR with bodies.
// Login through the admin UI, visit the main admin pages, then a scripted read/write/read sequence through fetch
// from inside the page (session cookie is carried automatically; Ghost's CSRF check reads Origin/Referer).
import { chromium } from 'playwright-core';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

const BASE = process.env.BASE_URL || 'http://127.0.0.1:3105';
const DIR = process.env.CAPTURE_DIR || path.join(os.homedir(), 'capture', 'ghost');
const HAR = process.env.HAR_PATH || path.join(DIR, 'ghost.full.har');
const EXE = process.env.CHROMIUM_PATH || '/snap/bin/chromium';
const admin = Object.fromEntries(fs.readFileSync(path.join(DIR, '.admin'), 'utf8').split('\n').filter((l) => l.includes('='))
  .map((l) => { const i = l.indexOf('='); return [l.slice(0, i), l.slice(i + 1)]; }));
const EMAIL = admin.GHOST_ADMIN_EMAIL; const PASS = admin.GHOST_ADMIN_PASSWORD;
let ids = {}; try { ids = JSON.parse(fs.readFileSync(path.join(DIR, 'seed-ids.json'), 'utf8')); } catch {}
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

const settle = async (ms = 1500) => { await page.waitForLoadState('networkidle', { timeout: 25000 }).catch(() => {}); await page.waitForTimeout(ms); };
const visit = async (p, ms) => { log(`visit ${p}`); await page.goto(`${BASE}${p}`, { waitUntil: 'domcontentloaded' }); await settle(ms); };
const api = async (method, p, body) => {
  const res = await page.evaluate(async ({ method, p, body }) => {
    const r = await fetch(p, { method, headers: { 'content-type': 'application/json', accept: 'application/json' }, body: body === undefined ? undefined : JSON.stringify(body) });
    const text = await r.text();
    return { status: r.status, text }; // full body: Ghost post payloads exceed a few KB
  }, { method, p, body });
  log(`${method} ${p} -> ${res.status}`);
  let json = null; try { json = JSON.parse(res.text); } catch {}
  return json;
};

// --- login through the admin UI ---
await visit('/ghost/#/signin', 500);
await page.waitForSelector('input[name="identification"]');
await page.fill('input[name="identification"]', EMAIL);
await page.fill('input[name="password"]', PASS);
await page.click('button[type="submit"]');
await page.waitForURL((u) => !u.hash.startsWith('#/signin'), { timeout: 45000 });
await settle(2500);
log(`logged in, landed on ${new URL(page.url()).hash}`);

// --- resolve seeded ids (seed-ids.json first, API by slug as fallback) ---
const slugPost = 'granite-ledger-quarterly-stone-count'; const slugPost2 = 'blue-heron-kitchen-tide-table-menu';
let postId = ids.posts?.[slugPost]; let tagId = ids.tags?.['granite-ledger']; let memberId = ids.members?.['ada-finch'];
if (!postId) postId = (await api('GET', `/ghost/api/admin/posts/slug/${slugPost}/`))?.posts?.[0]?.id;

// --- main admin pages (UI traffic) ---
for (const p of ['/ghost/#/posts', `/ghost/#/editor/post/${postId}`, '/ghost/#/pages', '/ghost/#/tags', '/ghost/#/members', '/ghost/#/settings']) {
  await visit(p, p.includes('settings') ? 3000 : 1500);
}

// --- scripted API sequence from inside the page ---
const site = await api('GET', '/ghost/api/admin/site/');
log(`ghost version ${site?.site?.version}`);
const posts = await api('GET', '/ghost/api/admin/posts/?limit=15&include=tags,authors');
if (!postId) postId = posts?.posts?.find((x) => x.slug === slugPost)?.id;
await api('GET', `/ghost/api/admin/posts/${postId}/`);
await api('GET', `/ghost/api/admin/posts/slug/${slugPost2}/`);
await api('GET', '/ghost/api/admin/pages/');
const tags = await api('GET', '/ghost/api/admin/tags/?include=count.posts');
if (!tagId) tagId = tags?.tags?.find((t) => t.slug === 'granite-ledger')?.id;
await api('GET', `/ghost/api/admin/tags/${tagId}/`);
const members = await api('GET', '/ghost/api/admin/members/?limit=15');
if (!memberId) memberId = members?.members?.[0]?.id;
await api('GET', `/ghost/api/admin/members/${memberId}/`);
await api('GET', '/ghost/api/admin/users/?include=roles');
await api('GET', '/ghost/api/admin/settings/');
await api('GET', '/ghost/api/admin/posts/?filter=tag:granite-ledger');
await api('GET', '/ghost/api/admin/posts/?filter=status:draft&limit=5');
// write path on a scratch post: create, edit, re-read, delete, re-read list
const created = await api('POST', '/ghost/api/admin/posts/?source=html', { posts: [{ title: 'Rea scratch post', html: '<p>Scratch body written during the capture.</p>', status: 'draft', tags: [{ name: 'Granite Ledger' }] }] });
const sp = created?.posts?.[0];
if (sp?.id) {
  const upd = await api('PUT', `/ghost/api/admin/posts/${sp.id}/?source=html`, { posts: [{ title: 'Rea scratch post (edited)', html: '<p>Edited scratch body.</p>', updated_at: sp.updated_at }] });
  log(`scratch post edited -> ${upd?.posts?.[0]?.title}`);
  await api('GET', `/ghost/api/admin/posts/${sp.id}/`);
  await api('DELETE', `/ghost/api/admin/posts/${sp.id}/`);
  await api('GET', `/ghost/api/admin/posts/${sp.id}/`);
}
await api('GET', '/ghost/api/admin/posts/?limit=15&include=tags,authors');
await settle(500);
await context.close(); // flushes the HAR
if (browser) await browser.close();
log(`HAR written to ${HAR}`);
console.log(HAR);
