# NOAA Tides and Currents API capture notes (rea showcase)

Replaces the assigned SEC EDGAR app: `data.sec.gov` answered the showcase User-Agent
(`rea-environments showcase (https://github.com/earakely-scale/rea-environments)`) with 403 "Your Request Originates from an
Undeclared Automated Tool", both from curl and from Chromium (two requests in total). SEC fair access requires a contact
email address in the User-Agent, which the showcase rules do not allow, so the alternate was used.

- API: NOAA CO-OPS (Center for Operational Oceanographic Products and Services) public APIs on
  `https://api.tidesandcurrents.noaa.gov`: the Metadata API (`/mdapi/prod/webapi/`), the Data API
  (`/api/prod/datagetter`) and the Derived Product API (`/dpapi/prod/webapi/`). No key, no login. The APIs publish no
  version number beyond the `prod` path segment, so the environment version is `v1`.
- Licence of the content: U.S. public domain (works of the U.S. federal government).
- No instance, no compose file, no seed: the capture reads real public records.
- Tooling on the VM: rea 6.6.0, playwright-core 1.58.2, Chromium 155.0.8059.79 (snap), node v24.22.0, python 3.12.3.

## Fair access followed
- A declared User-Agent set on the Playwright context (no email address in it), and `application=rea-environments_showcase`
  on every Data API request, as CO-OPS asks of API users.
- One request at a time with a 600 ms pause after each (under 2 requests per second); 72 requests in the whole session.
- Short ranges only: two days of high/low predictions, three hours of six-minute water levels, two hours of weather
  readings, one year of monthly means, five days of verified high/low.

## Pipeline (all under ~/capture/noaa-tides on the VM)
1. `NODE_PATH=~/capture/node_modules node noaa-tides/capture.mjs`: opens one station document
   (`/mdapi/prod/webapi/stations/9414290.json`, San Francisco) so every later in-page `fetch` is same-origin, then:
   the air-gap station collection (`stations.json?type=airgap`, 21 stations); nine more station records by id (Key West
   8724580, Seattle 9447130, Galveston Pier 21 8771450, Sewells Point 8638610, San Diego 9410170, Eastport 8410140,
   Anchorage 9455920, Grand Isle 8761724, Hilo 1617760); station sub-resources by id (details x5, datums x5, harmonic
   constituents x3, sensors x4, flood levels x4, notices x2, products x1, benchmarks x2); Data API filtered queries
   (predictions hilo x6, water_level x3, monthly_mean x2, high_low, wind, air_temperature, water_temperature, air_pressure,
   datums); Derived Product API (sea level trends x3, annual high-tide flooding counts x2).
   A first run aborted after 10 requests on an unhandled transient `Failed to fetch`; the script now retries a failed
   fetch once after 2.5 s and always closes the context so the HAR is flushed. In the kept run one benchmarks read
   failed once and was retried.
2. `python3 -I scope_har.py noaa-tides.full.har noaa-tides.scoped.har --origin https://api.tidesandcurrents.noaa.gov --keep-regex '^/(mdapi|api|dpapi)/prod/'`
   -> kept 56 (GET 56; 55 x 200, 1 x 400); dropped big-body 3 (the sea level trends endpoint ignored the station filter and
   returned every station, 319 KB each), non-json 1 (the failed attempt above). Forbidden-word scan of the scoped HAR: 0.
3. `python3 ~/showcase/envbuild.py all noaa-tides`.

## Recorded oddities worth knowing
- `datagetter?product=datums` answers 400 with a plain-text note that datums moved to the Metadata API.
- `datagetter?product=water_temperature` for Seattle answers 200 with `{"error": {"message": "No data was found..."}}`.
- Station sub-resources carry no station name; the station record (`stations/{id}.json`) does.
