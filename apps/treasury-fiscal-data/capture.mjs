// Record the U.S. Treasury Fiscal Data API (public domain, no key) with Chromium via playwright-core: open one API URL so
// in-page fetch is same-origin, then a scripted sequence of small GETs, one at a time with a 600 ms pause (under 2 requests
// per second), every query narrowed to at most five rows (filter, fields, page[size]=5). A declared User-Agent is set on the
// context; the run stops before 140 requests to the API host.
import { chromium } from 'playwright-core';
import os from 'node:os';
import path from 'node:path';

const ORIGIN = 'https://api.fiscaldata.treasury.gov';
const B = '/services/api/fiscal_service';
const UA = 'rea-environments showcase (https://github.com/earakely-scale/rea-environments)';
const DIR = process.env.CAPTURE_DIR || path.join(os.homedir(), 'capture', 'treasury-fiscal-data');
const HAR = process.env.HAR_PATH || path.join(DIR, 'treasury-fiscal-data.full.har');
const EXE = process.env.CHROMIUM_PATH || '/snap/bin/chromium';
const MAX_REQUESTS = 140;
const log = (m) => console.error(`[capture] ${m}`);

const browser = await chromium.launch({ executablePath: EXE, headless: true, args: ['--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu'] });
const context = await browser.newContext({ userAgent: UA, recordHar: { path: HAR, content: 'embed', mode: 'full' } });
const page = await context.newPage();
page.setDefaultTimeout(45000);
let sent = 0;
page.on('request', (r) => { if (r.url().startsWith(ORIGIN)) sent += 1; });

// Encode a query value but keep the API's filter punctuation (: , ( )) readable.
const enc = (v) => encodeURIComponent(v).replace(/%3A/g, ':').replace(/%2C/g, ',');
const url = (p, q) => `${B}/${p}?` + Object.entries({ ...q, 'page[size]': q['page[size]'] || 5 }).map(([k, v]) => `${enc(k)}=${enc(String(v))}`).join('&');
const get = async (p, q) => {
  if (sent >= MAX_REQUESTS) throw new Error(`request budget reached (${sent})`);
  const u = url(p, q);
  const res = await page.evaluate(async (u) => {
    const r = await fetch(u, { headers: { accept: 'application/json' } });
    return { status: r.status, text: await r.text() };
  }, u);
  let json = null; try { json = JSON.parse(res.text); } catch {}
  log(`GET ${u} -> ${res.status} rows=${json?.data?.length ?? '-'} total=${json?.meta?.['total-count'] ?? '-'} bytes=${res.text.length}`);
  await page.waitForTimeout(600);
  return json;
};
const rows = (j) => (j && Array.isArray(j.data) ? j.data : []);

// --- open the API origin (any URL on it) so the scripted fetches are same-origin ---
const first = `${ORIGIN}${url('v2/accounting/od/debt_outstanding', { filter: 'record_date:gte:2022-09-30' })}`;
log(`open ${first}`);
await page.goto(first, { waitUntil: 'domcontentloaded' });
await page.waitForTimeout(1500);

const OD1 = 'v1/accounting/od'; const OD2 = 'v2/accounting/od'; const DTS = 'v1/accounting/dts';
const FX = `${OD1}/rates_of_exchange`; const FXF = 'country_currency_desc,exchange_rate,effective_date,record_date';
// exchange rates (quarterly): three countries on one date, then single currencies by key
await get(FX, { filter: 'record_date:eq:2026-09-30,country:in:(Japan,Norway,Switzerland)', fields: FXF });
await get(FX, { filter: 'country_currency_desc:eq:Canada-Dollar,record_date:gte:2025-10-01', sort: '-record_date', fields: FXF });
for (const c of ['Mexico-Peso', 'Euro Zone-Euro', 'United Kingdom-Pound', 'India-Rupee', 'Brazil-Real', 'Australia-Dollar', 'Korea-Won']) {
  await get(FX, { filter: `country_currency_desc:eq:${c},record_date:eq:2026-09-30`, fields: FXF });
}
await get(FX, { filter: 'country_currency_desc:eq:Japan-Yen,record_date:gte:2025-10-01', sort: '-record_date', fields: FXF });
// average interest rates on Treasury securities (monthly)
await get(`${OD2}/avg_interest_rates`, { filter: 'record_date:eq:2026-09-30,src_line_nbr:lte:4' });
await get(`${OD2}/avg_interest_rates`, { filter: 'security_desc:eq:Treasury Bills,record_date:gte:2026-05-01', sort: '-record_date' });
await get(`${OD2}/avg_interest_rates`, { filter: 'security_desc:eq:Treasury Notes,record_date:gte:2026-05-01', sort: '-record_date' });
await get(`${OD2}/avg_interest_rates`, { filter: 'record_date:eq:2026-09-30,src_line_nbr:gte:8,src_line_nbr:lte:12' });
// U.S. Treasury-owned gold
await get(`${OD2}/gold_reserve`, { filter: 'record_date:eq:2026-09-30,facility_desc:eq:Mint Held Gold - Deep Storage' });
await get(`${OD2}/gold_reserve`, { filter: 'record_date:eq:2026-09-30,facility_desc:eq:Federal Reserve Bank Held Gold' });
await get(`${OD2}/gold_reserve`, { filter: 'record_date:eq:2026-09-30,facility_desc:eq:Mint Held Gold - Working Stock' });
// interest expense on the public debt
await get(`${OD2}/interest_expense`, { filter: 'record_date:eq:2026-09-30,src_line_nbr:lte:3' });
await get(`${OD2}/interest_expense`, { filter: 'record_date:eq:2026-09-30,expense_type_desc:eq:Treasury Bills' });
await get(`${OD2}/interest_expense`, { filter: 'record_date:eq:2026-09-30,expense_type_desc:eq:Treasury Bonds' });
// Title XII advances to state unemployment funds
const tx = await get(`${OD2}/title_xii`, { filter: 'record_date:eq:2026-10-15' });
for (const st of [...new Set(rows(tx).map((r) => r.state_nm))].slice(0, 2)) await get(`${OD2}/title_xii`, { filter: `state_nm:eq:${st}`, sort: '-record_date' });
// agency net cost (Financial Report of the U.S. Government)
const nc = await get(`${OD2}/statement_net_cost`, { filter: 'record_date:eq:2025-09-30,src_line_nbr:lte:5' });
for (const ag of rows(nc).map((r) => r.agency_nm).filter(Boolean).slice(1, 3)) await get(`${OD2}/statement_net_cost`, { filter: `agency_nm:eq:${ag},record_date:gte:2021-09-30`, sort: '-record_date' });
// Daily Treasury Statement
await get(`${DTS}/operating_cash_balance`, { filter: 'record_date:eq:2026-10-15,src_line_nbr:lte:3' });
await get(`${DTS}/operating_cash_balance`, { filter: 'record_date:eq:2026-10-14,src_line_nbr:lte:3' });
await get(`${DTS}/deposits_withdrawals_operating_cash`, { filter: 'record_date:eq:2026-10-15,transaction_type:eq:Deposits,src_line_nbr:lte:4' });
for (const c of ['Dept of Education (ED)', 'Dept of Energy (DOE)', 'National Science Foundation (NSF)', 'SSA - Supplemental Security Income']) {
  await get(`${DTS}/deposits_withdrawals_operating_cash`, { filter: `record_date:eq:2026-10-15,transaction_catg:eq:${c}` });
}
// Treasury securities auctions
const AF = 'cusip,security_type,security_term,auction_date,issue_date,maturity_date,offering_amt,auction_format,high_yield,int_rate';
const au = await get(`${OD1}/auctions_query`, { filter: 'auction_date:eq:2026-10-22', fields: AF });
for (const cu of rows(au).map((r) => r.cusip).filter(Boolean).slice(0, 1)) await get(`${OD1}/auctions_query`, { filter: `cusip:eq:${cu}`, fields: AF });
await get(`${OD1}/auctions_query`, { filter: 'security_term:eq:10-Year,auction_date:gte:2026-06-01', sort: '-auction_date', fields: AF });
await get(`${OD1}/auctions_query`, { filter: 'security_term:eq:30-Year,auction_date:gte:2026-06-01', sort: '-auction_date', fields: AF });
await get(`${OD1}/auctions_query`, { filter: 'security_term:eq:2-Year,auction_date:gte:2026-06-01', sort: '-auction_date', fields: AF });
// revenue collections
await get('v2/revenue/rcm', { filter: 'record_date:eq:2026-10-15,src_line_nbr:lte:3' });
await get('v2/revenue/rcm', { filter: 'record_date:eq:2026-10-14,src_line_nbr:lte:3' });
// Monthly Treasury Statement, outlays by agency
const MF = 'classification_desc,current_month_net_outly_amt,current_fytd_net_outly_amt,prior_fytd_net_outly_amt,record_date';
await get('v1/accounting/mts/mts_table_5', { filter: 'record_date:eq:2026-09-30,src_line_nbr:lte:3', fields: MF });
await get('v1/accounting/mts/mts_table_5', { filter: 'record_date:eq:2026-09-30,classification_desc:in:(Total--Department of Energy,Total--Department of Education,Total--Department of the Interior)', fields: MF });
// savings bond and securities sales, maturity rates
await get(`${OD1}/securities_sales`, { filter: 'record_date:eq:2026-10-31,src_line_nbr:lte:3' });
await get(`${OD1}/securities_sales`, { filter: 'security_class_desc:eq:I,record_date:gte:2026-06-30', sort: '-record_date' });
await get(`${OD1}/federal_maturity_rates`, { filter: 'record_date:gte:2025-09-30', sort: '-record_date' });
// debt to the penny and total debt outstanding
await get(`${OD2}/debt_to_penny`, { filter: 'record_date:gte:2026-10-09,record_date:lte:2026-10-15', sort: '-record_date' });
await get(`${OD2}/debt_to_penny`, { filter: 'record_date:eq:2026-09-30' });
await get(`${OD2}/debt_to_penny`, { filter: 'record_date:eq:2026-06-30' });
await get(`${OD2}/debt_outstanding`, { filter: 'record_date:eq:2026-09-30' });
// receivables reported by agencies (Treasury Report on Receivables)
const TF = 'agency_name,receivable_type_description,funding_type_description,beginning_fiscal_year_amt,new_receivables_amt,collections_total_amt,record_date';
await get('v2/debt/tror', { filter: 'record_date:eq:2026-06-30,agency_name:eq:Department of Education', fields: TF });
await get('v2/debt/tror', { filter: 'record_date:eq:2026-06-30,agency_name:eq:Department of Agriculture', fields: TF });

await page.waitForTimeout(500);
await context.close(); // flushes the HAR
await browser.close();
log(`requests to ${ORIGIN}: ${sent}; HAR written to ${HAR}`);
console.log(HAR);
