// Drive the seeded Gitea with snap Chromium through playwright-core and record a HAR with bodies:
// UI login, page visits, then a scripted /api/v1 read/write/read sequence issued with fetch from inside the page.
// Credentials come from ./.admin (never printed); seeded ids from ./seed.json. Prints the HAR path on stdout.
import { chromium } from 'playwright-core';
import fs from 'node:fs';
import path from 'node:path';

const HERE = path.dirname(new URL(import.meta.url).pathname);
const BASE = process.env.BASE_URL || 'http://127.0.0.1:3102';
const HAR = process.env.HAR_PATH || path.join(HERE, 'gitea.har');
const EXE = process.env.CHROMIUM || '/snap/bin/chromium';
const admin = Object.fromEntries(fs.readFileSync(path.join(HERE, '.admin'), 'utf8').split('\n').filter(Boolean).map((l) => l.split(/=(.*)/s).slice(0, 2)));
const seed = JSON.parse(fs.readFileSync(path.join(HERE, 'seed.json'), 'utf8'));
const ORG = seed.org, GL = 'granite-ledger', BHK = 'blue-heron-kitchen';
const gl = seed.repos[GL], bhk = seed.repos[BHK];
const log = (m) => console.error(`[capture] ${m}`);

const browser = await chromium.launch({ executablePath: EXE, headless: true, args: ['--no-sandbox', '--disable-gpu', '--disable-dev-shm-usage'] });
const context = await browser.newContext({ recordHar: { path: HAR, content: 'embed', mode: 'full' }, viewport: { width: 1280, height: 900 } });
const page = await context.newPage();

const settle = async (ms = 800) => { await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => {}); await page.waitForTimeout(ms); };
const visit = async (p) => { const r = await page.goto(`${BASE}${p}`, { waitUntil: 'domcontentloaded' }); log(`visit ${p} -> ${r?.status()}`); await settle(); return r?.status(); };

// UI login (the login exchange itself is dropped at scoping time).
await visit('/user/login');
await page.fill('input[name="user_name"]', admin.ADMIN_USER);
await page.fill('input[name="password"]', admin.ADMIN_PASS);
await Promise.all([page.waitForURL((u) => !u.pathname.startsWith('/user/login'), { timeout: 20000 }), page.press('input[name="password"]', 'Enter')]);
await settle();
log(`logged in, now at ${new URL(page.url()).pathname}`);

// API helper: fetch from inside the page so the exchange is browser traffic and lands in the HAR.
// Session auth is tried first; if the API refuses the web session, the scoped read/write token from .admin is used
// (the header is stripped by scope_har.py and never reaches the scoped HAR).
let authHeader = null;
const api = async (method, p, body) => {
  const res = await page.evaluate(async ({ method, p, body, authHeader }) => {
    const headers = { accept: 'application/json' };
    if (body !== undefined) headers['content-type'] = 'application/json';
    if (authHeader) headers.authorization = authHeader;
    const r = await fetch(p, { method, headers, credentials: 'same-origin', body: body === undefined ? undefined : JSON.stringify(body) });
    const text = await r.text();
    return { status: r.status, text: text.slice(0, 4000) };
  }, { method, p, body, authHeader });
  log(`${method} ${p} -> ${res.status}`);
  let json = null; try { json = JSON.parse(res.text); } catch {}
  return { status: res.status, json };
};
const probe = await api('GET', '/api/v1/user');
if (probe.status !== 200) {
  authHeader = `token ${admin.API_TOKEN}`;
  const again = await api('GET', '/api/v1/user');
  if (again.status !== 200) { log('API auth failed with session and token'); await context.close(); await browser.close(); process.exit(2); }
  log('API auth: scoped token header');
} else { log('API auth: web session'); }

// Page visits.
const pages = ['/', '/explore/repos', `/${ORG}`, `/${ORG}/${GL}`, `/${ORG}/${GL}/src/branch/main/ledger/2026-q1.csv`, `/${ORG}/${GL}/issues`,
  `/${ORG}/${GL}/issues/${gl.issues[0]}`, `/${ORG}/${GL}/issues/${gl.issues[1]}`, `/${ORG}/${GL}/pulls`, `/${ORG}/${GL}/pulls/${gl.pr}`,
  `/${ORG}/${GL}/pulls/${gl.pr}/files`, `/${ORG}/${GL}/milestones`, `/${ORG}/${GL}/labels`, `/${ORG}/${GL}/branches`, `/${ORG}/${BHK}`,
  `/${ORG}/${BHK}/issues/${bhk.issues[0]}`, `/${seed.users[0]}`, `/${seed.users[1]}`, '/-/admin', '/-/admin/users', '/issues', '/pulls', '/milestones', '/notifications'];
for (const p of pages) await visit(p);

// Scripted reads.
const R = `/api/v1/repos/${ORG}`;
const reads = ['/api/v1/version', '/api/v1/user', '/api/v1/user/repos', '/api/v1/user/orgs', '/api/v1/user/settings',
  `/api/v1/users/${seed.users[0]}`, `/api/v1/users/${seed.users[1]}`, `/api/v1/users/${seed.users[0]}/repos`, `/api/v1/users/${seed.users[0]}/orgs`,
  `/api/v1/users/${seed.users[1]}/heatmap`, '/api/v1/users/search?q=ada', '/api/v1/users/search?q=rui&limit=5',
  `/api/v1/orgs/${ORG}`, `/api/v1/orgs/${ORG}/repos`, `/api/v1/orgs/${ORG}/members`, `/api/v1/orgs/${ORG}/teams`, `/api/v1/orgs/${ORG}/labels`,
  `/api/v1/teams/${seed.team_id}`, `/api/v1/teams/${seed.team_id}/members`, `/api/v1/teams/${seed.team_id}/repos`,
  `${R}/${GL}`, `${R}/${BHK}`, `${R}/${GL}/contents`, `${R}/${GL}/contents/README.md`, `${R}/${GL}/contents/ledger/2026-q1.csv`, `${R}/${GL}/contents/docs/rota.md`,
  `${R}/${BHK}/contents/README.md`, `${R}/${GL}/contents/docs/spring-tide-shifts.md?ref=${gl.branch}`,
  `${R}/${GL}/branches`, `${R}/${GL}/branches/main`, `${R}/${GL}/branches/${gl.branch}`, `${R}/${BHK}/branches`,
  `${R}/${GL}/commits?sha=main&limit=10`, `${R}/${GL}/git/refs`, `${R}/${GL}/git/trees/main`, `${R}/${GL}/tags`, `${R}/${GL}/releases`, `${R}/${GL}/collaborators`,
  `${R}/${GL}/topics`, `${R}/${GL}/stargazers`, `${R}/${GL}/subscribers`, `${R}/${GL}/forks`, `${R}/${GL}/activities/feeds`,
  `${R}/${GL}/issues?state=all`, `${R}/${GL}/issues?state=closed`, `${R}/${GL}/issues?state=open&labels=high-tide`, `${R}/${GL}/issues?milestones=Spring%20Tide`,
  `${R}/${GL}/issues?q=hinge&type=issues`, `${R}/${GL}/issues/${gl.issues[0]}`, `${R}/${GL}/issues/${gl.issues[1]}`, `${R}/${GL}/issues/${gl.issues[2]}`,
  `${R}/${GL}/issues/${gl.issues[0]}/comments`, `${R}/${GL}/issues/${gl.issues[1]}/comments`, `${R}/${GL}/issues/${gl.issues[0]}/labels`,
  `${R}/${GL}/issues/${gl.issues[1]}/timeline`, `${R}/${GL}/issues/${gl.issues[0]}/reactions`, `${R}/${GL}/issues/comments`,
  `${R}/${BHK}/issues?state=all`, `${R}/${BHK}/issues/${bhk.issues[0]}`, `${R}/${BHK}/labels`,
  `${R}/${GL}/labels`, `${R}/${GL}/labels/${gl.labels['high-tide']}`, `${R}/${GL}/labels/${gl.labels['low-tide']}`,
  `${R}/${GL}/milestones`, `${R}/${GL}/milestones/${gl.milestone['Spring Tide']}`,
  `${R}/${GL}/pulls`, `${R}/${GL}/pulls?state=all`, `${R}/${GL}/pulls/${gl.pr}`, `${R}/${GL}/pulls/${gl.pr}/files`, `${R}/${GL}/pulls/${gl.pr}/commits`, `${R}/${GL}/pulls/${gl.pr}/reviews`,
  '/api/v1/repos/search?q=granite', '/api/v1/repos/search?q=heron&limit=5', '/api/v1/repos/issues/search?q=chowder', '/api/v1/repos/issues/search?q=ledger&state=all',
  '/api/v1/admin/users', '/api/v1/admin/orgs', '/api/v1/notifications', '/api/v1/settings/ui', '/api/v1/settings/repository', '/api/v1/settings/api', '/api/v1/nodeinfo'];
const got = {};
for (const p of reads) got[p] = await api('GET', p);
const mainSha = got[`${R}/${GL}/branches/main`]?.json?.commit?.id;
if (mainSha) { await api('GET', `${R}/${GL}/git/commits/${mainSha}`); await api('GET', `${R}/${GL}/commits/${mainSha}/statuses`); }

// Scratch issue on blue-heron-kitchen: create, read, update, comment, read, delete the comment, close, read back.
const created = await api('POST', `${R}/${BHK}/issues`, { title: 'Scratch: pantry stock count', body: 'Temporary issue created by the capture run.' });
const n = created.json?.number;
if (n) {
  await api('GET', `${R}/${BHK}/issues/${n}`);
  await api('PATCH', `${R}/${BHK}/issues/${n}`, { title: 'Scratch: pantry stock count (revised)', body: 'Temporary issue created by the capture run; revised once.' });
  const c = await api('POST', `${R}/${BHK}/issues/${n}/comments`, { body: 'Counted 14 tins of chopped tomatoes.' });
  await api('GET', `${R}/${BHK}/issues/${n}/comments`);
  await api('GET', `${R}/${BHK}/issues/${n}`);
  if (c.json?.id) await api('DELETE', `${R}/${BHK}/issues/comments/${c.json.id}`);
  await api('GET', `${R}/${BHK}/issues/${n}/comments`);
  await api('PATCH', `${R}/${BHK}/issues/${n}`, { state: 'closed' });
  await api('GET', `${R}/${BHK}/issues/${n}`);
  await api('GET', `${R}/${BHK}/issues?state=closed`);
}
await settle(500);
await context.close(); // flushes the HAR
await browser.close();
console.log(HAR);
