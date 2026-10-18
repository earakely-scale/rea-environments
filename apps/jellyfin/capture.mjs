// Drive the showcase Jellyfin web client with Chromium via playwright-core and record a HAR with bodies.
// Login through the web client's manual login form, visit the main views (hash routes, so the client loads once), then a
// scripted read/write/read sequence through fetch from inside the page. The web client keeps its access token in
// localStorage (jellyfin_credentials), not in a cookie, so the scripted calls read it there and send it in the
// Authorization header, which the scoping tool strips from the HAR.
import { chromium } from 'playwright-core';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

const BASE = process.env.BASE_URL || 'http://127.0.0.1:3224';
const DIR = process.env.CAPTURE_DIR || path.join(os.homedir(), 'capture', 'jellyfin');
const HAR = process.env.HAR_PATH || path.join(DIR, 'jellyfin.full.har');
const EXE = process.env.CHROMIUM_PATH || '/snap/bin/chromium';
const USER = 'rea-admin';
const admin = Object.fromEntries(fs.readFileSync(path.join(DIR, '.admin'), 'utf8').split('\n').filter((l) => l.includes('='))
  .map((l) => { const i = l.indexOf('='); return [l.slice(0, i), l.slice(i + 1)]; }));
const ids = JSON.parse(fs.readFileSync(path.join(DIR, 'seed-ids.json'), 'utf8'));
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

const settle = async (ms = 1500) => { await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => {}); await page.waitForTimeout(ms); };
const visit = async (p, ms) => { log(`visit ${p}`); await page.goto(`${BASE}${p}`, { waitUntil: 'domcontentloaded' }); await settle(ms); };
const api = async (method, p, body) => {
  const res = await page.evaluate(async ({ method, p, body }) => {
    const creds = JSON.parse(localStorage.getItem('jellyfin_credentials') || '{}').Servers?.[0] || {};
    const device = localStorage.getItem('_deviceId2') || 'rea-capture';
    const auth = `MediaBrowser Client="Jellyfin Web", Device="Chromium", DeviceId="${device}", Version="10.10.7", Token="${creds.AccessToken}"`;
    const r = await fetch(p, { method, headers: { 'content-type': 'application/json', accept: 'application/json', authorization: auth },
      body: body === undefined ? undefined : JSON.stringify(body) });
    return { status: r.status, text: await r.text() };
  }, { method, p, body });
  log(`${method} ${p.split('?')[0]} -> ${res.status}`);
  try { return JSON.parse(res.text); } catch { return null; }
};

// --- login through the web client ---
await visit('/web/#/login.html', 2500);
if (!(await page.locator('#txtManualName').isVisible().catch(() => false))) {
  const manual = page.locator('.btnManual');
  if (await manual.count()) { await manual.first().click(); await page.waitForTimeout(800); }
}
await page.fill('#txtManualName', USER);
await page.fill('#txtManualPassword', admin.JELLYFIN_ADMIN_PASSWORD);
await page.locator('.manualLoginForm button[type="submit"]').first().click();
await page.waitForURL((u) => !u.hash.includes('login'), { timeout: 45000 });
await settle(2500);
log(`logged in, landed on ${new URL(page.url()).hash}`);

const U = ids.users; const uid = U[USER]; const L = ids.libraries; const A = ids.albums; const T = ids.tracks;
const P = ids.photos; const B = ids.books; const pl = ids.playlists['Night Watch Mix']; const bs = ids.collections['Granite Ledger Sessions'];
// --- main views (UI traffic) ---
for (const p of [`/web/#/music.html?topParentId=${L['Lighthouse Rota Music']}`, `/web/#/details?id=${A['Lighthouse Rota Suite']}`,
  `/web/#/list.html?parentId=${L['Saltmarsh Depot Photos']}`, `/web/#/list.html?parentId=${L['Copperfield Annex Reading Room']}`,
  `/web/#/details?id=${pl}`, '/web/#/dashboard', '/web/#/dashboard/users', '/web/#/dashboard/libraries']) {
  await visit(p, 1500);
}

// --- scripted API sequence from inside the page ---
await api('GET', '/System/Info');
await api('GET', '/Users');
await api('GET', `/Users/${U['Ada Finch']}`);
await api('GET', '/Users/Me');
await api('GET', '/Library/VirtualFolders');
await api('GET', '/Library/MediaFolders');
await api('GET', `/UserViews?userId=${uid}`);
await api('GET', `/Items/${A['Lighthouse Rota Suite']}?userId=${uid}`);
await api('GET', `/Items/${T['Kelp Broth Blues']}?userId=${uid}`);
await api('GET', `/Users/${uid}/Items/${A['Saltmarsh Depot Sessions']}`);
await api('GET', `/Items?userId=${uid}&parentId=${A['Lighthouse Rota Suite']}&sortBy=IndexNumber&fields=Overview,Genres`);
await api('GET', `/Items/${T['Tide Table Waltz']}/Ancestors?userId=${uid}`);
await api('GET', `/Artists?userId=${uid}&fields=Overview`);
await api('GET', `/Artists/${encodeURIComponent('Ada Finch Quartet')}?userId=${uid}`);
await api('GET', `/Artists/${encodeURIComponent('Blue Heron Kitchen Band')}?userId=${uid}`);
await api('GET', `/MusicGenres?userId=${uid}`);
await api('GET', `/MusicGenres/${encodeURIComponent('Kitchen Jazz')}?userId=${uid}`);
await api('GET', `/Albums/${A['Lighthouse Rota Suite']}/Similar?userId=${uid}&limit=3`);
await api('GET', `/Playlists/${pl}/Items?userId=${uid}`);
await api('GET', `/Items/${pl}?userId=${uid}`);
await api('GET', `/Items?userId=${uid}&parentId=${bs}&fields=Overview`);
await api('GET', `/Items/${P['Copperfield Annex Roof'] || Object.values(P)[0]}?userId=${uid}`);
await api('GET', `/Items?userId=${uid}&recursive=true&includeItemTypes=Book&fields=Overview,Tags`);
await api('GET', `/Items/${Object.values(B)[0]}/Similar?userId=${uid}&limit=3`);
await api('GET', `/UserItems/${T['Lamp Oil Reel']}/UserData?userId=${uid}`);
await api('GET', `/Items/Latest?userId=${uid}&parentId=${L['Lighthouse Rota Music']}&limit=5`);
await api('GET', `/Items/Filters?userId=${uid}&parentId=${L['Lighthouse Rota Music']}`);
await api('GET', `/Items/Counts?userId=${uid}`);
// searches and filters
await api('GET', `/Search/Hints?userId=${uid}&searchTerm=Granite&limit=10`);
await api('GET', `/Items?userId=${uid}&recursive=true&searchTerm=Kelp&includeItemTypes=Audio`);
await api('GET', `/Items?userId=${uid}&recursive=true&isFavorite=true&includeItemTypes=Audio`);
// write path on a scratch playlist: create, add an item, edit its metadata, favourite, re-read, delete, re-read
const created = await api('POST', '/Playlists', { Name: 'Rea Scratch Playlist', Ids: [T['Granite Ledger']], UserId: uid, MediaType: 'Audio' });
const sid = created?.Id;
if (sid) {
  await api('POST', `/Playlists/${sid}/Items?ids=${T['Copperfield Annex Shuffle']}&userId=${uid}`);
  const dto = await api('GET', `/Items/${sid}?userId=${uid}`);
  if (dto) await api('POST', `/Items/${sid}`, { ...dto, Overview: 'Scratch playlist written during the capture.' });
  await api('POST', `/UserFavoriteItems/${sid}?userId=${uid}`);
  await api('GET', `/Playlists/${sid}/Items?userId=${uid}`);
  await api('DELETE', `/Items/${sid}`);
  await api('GET', `/Items/${sid}?userId=${uid}`);
}
await api('GET', `/Items?userId=${uid}&recursive=true&includeItemTypes=Playlist`);
await settle(500);
await context.close(); // flushes the HAR
if (browser) await browser.close();
log(`HAR written to ${HAR}`);
console.log(HAR);
