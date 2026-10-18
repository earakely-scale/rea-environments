// Drive the local NocoDB (127.0.0.1:3103) with the snap Chromium via playwright-core and record a HAR with bodies.
// Login through the UI, open the base, both tables (sidebar clicks), the table details page, then a scripted
// fetch sequence against the v2 meta/data API from inside the page. The JWT is read from the UI's localStorage
// and sent only as the xc-auth header (stripped by scope_har.py); it is never logged or written anywhere.
import { chromium } from "playwright-core";
import fs from "node:fs";

const DIR = "/home/ubuntu/capture/nocodb";
const BASE = process.env.BASE_URL || "http://127.0.0.1:3103";
const HAR = process.env.HAR_PATH || `${DIR}/nocodb.har`;
const PROFILE = `${DIR}/profile`;
const admin = Object.fromEntries(fs.readFileSync(`${DIR}/.admin`, "utf8").trim().split("\n").map((l) => l.split("=")));
const ids = JSON.parse(fs.readFileSync(`${DIR}/ids.json`, "utf8"));
const log = (m) => console.error(`[capture] ${m}`);

fs.rmSync(PROFILE, { recursive: true, force: true });
const context = await chromium.launchPersistentContext(PROFILE, {
  executablePath: process.env.CHROMIUM || "/snap/bin/chromium",
  headless: true,
  args: ["--no-sandbox", "--disable-gpu"],
  viewport: { width: 1400, height: 900 },
  recordHar: { path: HAR, content: "embed", mode: "full" },
});
const page = await context.newPage();
let apiCalls = 0;
page.on("request", (r) => { const u = new URL(r.url()); if (u.origin === BASE && u.pathname.startsWith("/api/")) apiCalls++; });

const settle = async (ms = 1500) => { await page.waitForLoadState("networkidle", { timeout: 20000 }).catch(() => {}); await page.waitForTimeout(ms); };
const visit = async (path) => { log(`visit ${path}`); await page.goto(`${BASE}${path}`, { waitUntil: "domcontentloaded" }); await settle(2500); };
// Sidebar navigation is client-side (no bootstrap reload); verify the URL moved to the table, else fall back to a direct visit.
const openTable = async (title, tableId) => {
  const handle = page.getByTestId(`tree-view-table-draggable-handle-${title}`).first();
  await handle.waitFor({ state: "visible", timeout: 15000 }).catch(() => {});
  await page.waitForTimeout(1500);
  for (const target of [handle, handle.locator("xpath=.."), page.locator(`[data-testid="tree-view-table-draggable-handle-${title}"]`).locator("xpath=ancestor::*[contains(@class,'nc-tree-item') or contains(@class,'nc-sidebar-node')][1]")]) {
    if (!(await target.count())) continue;
    log(`click ${title} table (grid view)`);
    await target.click({ force: true }).catch(() => {});
    const moved = await page.waitForURL((u) => u.pathname.includes(tableId), { timeout: 8000 }).then(() => true).catch(() => false);
    if (moved) { await settle(2500); return; }
  }
  log(`sidebar click did not navigate; visiting /nc/${ids.base_id}/${tableId} directly`);
  await visit(`/nc/${ids.base_id}/${tableId}`);
  await page.waitForURL((u) => u.pathname.includes(tableId), { timeout: 15000 }).catch(() => {});
};
// JSON calls issued from inside the page so they are browser traffic and land in the HAR.
const api = async (method, path, body) => {
  const res = await page.evaluate(async ({ method, path, body }) => {
    const tok = JSON.parse(localStorage.getItem("nocodb-gui-v2") || "{}").token;
    const r = await fetch(path, { method, headers: { "content-type": "application/json", accept: "application/json", "xc-auth": tok }, body: body === undefined ? undefined : JSON.stringify(body) });
    const text = await r.text();
    return { status: r.status, text: text.slice(0, 4000) };
  }, { method, path, body });
  log(`${method} ${path} -> ${res.status}`);
  let json = null; try { json = JSON.parse(res.text); } catch {}
  return json;
};

// 1. Login through the UI.
await visit("/");
await page.waitForSelector("#form_item_email", { timeout: 20000 });
await page.fill("#form_item_email", admin.email);
await page.fill("#form_item_password", admin.password);
await page.click("button[type=submit]");
await page.waitForURL((u) => !u.pathname.includes("signin"), { timeout: 20000 });
await settle(2500);
log(`logged in, url=${page.url()}`);

// 2. Base overview, then both tables through the sidebar (client-side navigation), then the table details page.
await visit(`/nc/${ids.base_id}`);
await openTable("Vessels", ids.vessels_table_id);
log(`vessels url=${page.url()}`);
await openTable("Port Calls", ids.port_calls_table_id);
const portCallsUrl = new URL(page.url());
log(`port calls url=${portCallsUrl.pathname}`);
if (!portCallsUrl.pathname.includes(ids.port_calls_table_id)) throw new Error("Port Calls table did not open");
await visit(`${portCallsUrl.pathname}?page=field`); // table details (fields) page

// 3. Scripted read / search / write / re-read sequence against the v2 API.
const V = ids.vessels_table_id, P = ids.port_calls_table_id, B = ids.base_id;
await api("GET", "/api/v1/version");
await api("GET", "/api/v2/meta/nocodb/info");
await api("GET", "/api/v2/meta/bases");
await api("GET", `/api/v2/meta/bases/${B}`);
await api("GET", `/api/v2/meta/bases/${B}/info`);
await api("GET", `/api/v2/meta/bases/${B}/tables`);
await api("GET", `/api/v2/meta/tables/${V}`);
await api("GET", `/api/v2/meta/tables/${P}`);
await api("GET", `/api/v2/meta/tables/${V}/views`);
await api("GET", `/api/v2/meta/tables/${P}/views`);
await api("GET", `/api/v2/tables/${V}/records?limit=25`);
await api("GET", `/api/v2/tables/${P}/records?limit=25`);
await api("GET", `/api/v2/tables/${V}/records?where=(status,eq,Active)&limit=25`);
await api("GET", `/api/v2/tables/${V}/records?where=(flag,eq,Malta)`);
await api("GET", `/api/v2/tables/${P}/records?where=(cranes,gte,3)&sort=eta`);
await api("GET", `/api/v2/tables/${P}/records?where=(berth,like,%25A%25)&fields=vessel,berth,eta`);
await api("GET", `/api/v2/tables/${V}/records?limit=3&offset=3&sort=-length_m`);
await api("GET", `/api/v2/tables/${V}/records/count`);
await api("GET", `/api/v2/tables/${P}/records/count?where=(cranes,eq,2)`);
for (const id of [1, 3, 8]) await api("GET", `/api/v2/tables/${V}/records/${id}`);
for (const id of [2, 5]) await api("GET", `/api/v2/tables/${P}/records/${id}`);
// scratch record: create, update, read, delete, re-read
const created = await api("POST", `/api/v2/tables/${V}/records`, { name: "Scratch Pilot", flag: "Tuvalu", length_m: 88, status: "Laid Up" });
const sid = created?.Id ?? created?.[0]?.Id;
if (sid !== undefined) {
  await api("PATCH", `/api/v2/tables/${V}/records`, [{ Id: sid, status: "Active", length_m: 90.5 }]);
  await api("GET", `/api/v2/tables/${V}/records/${sid}`);
  await api("GET", `/api/v2/tables/${V}/records?where=(name,eq,Scratch Pilot)`);
  await api("DELETE", `/api/v2/tables/${V}/records`, [{ Id: sid }]);
  await api("GET", `/api/v2/tables/${V}/records/${sid}`); // expected 404 after delete
} else {
  log("scratch record creation failed; skipping update/delete");
}
await api("GET", `/api/v2/tables/${V}/records/count`);
await settle(500);
await context.close(); // flushes the HAR
fs.rmSync(PROFILE, { recursive: true, force: true });
log(`api requests seen by the page: ${apiCalls}`);
log(`HAR written to ${HAR}`);
