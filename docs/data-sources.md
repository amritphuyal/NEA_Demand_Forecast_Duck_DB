# Data Sources

Status: `verified` (checked live) · `needs_user_verification` · `requested` · `planned` · `unavailable`. Machine-readable copy: `sources.json`.

## NEA Daily Operational Report (NDOR) — `verified`

- Listing: https://transd.nea.org.np/en/category/daily-operational-reports-1?page=N (64 pages × 10, newest first, server-rendered HTML).
- Detail: `https://transd.nea.org.np/detail/nepal-daily-operational-report-2081-09-27`; PDF `https://transd.nea.org.np/uploads/shares/Daily_op_reports/NDOR%202081_09_27.pdf`.
- Range: **2023-04-14 → 2025-01-11** (BS 2080_01_01 → 2081_09_27). Series looks frozen.
- One-page text PDF (Excel print). Header `For Date: 2081/09/27 ( 2025/01/11 )`.
  - **Daily Energy Values (MWh):** NEA, NEA Subsidiary, IPP, Import, Total Energy Available, Energy Export, Net Energy Met (INPS Demand), Energy Interruption, Energy not served/Generation Deficit, Energy Requirement, Net exchange with India.
  - **Peak Time (MW):** Peak Time, Generation, Import, Recorded Peak Availability, Export, Demand met at Peak Time, Interruption, Deficit, Peak Demand (Requirement), Net exchange with India.
- Gotchas: pagination links are `http://` (force https); "Highlights" sidebar duplicates posts; some reports re-issued as "rev1"; F5 bot protection (curl blocked).

## Legacy NDOR via Wayback — `unavailable`

Old path `nea.org.np/admin/assets/uploads/ldc/NDOR {BS}.pdf` (also `www.`, `cms.`) now 404. Checked 2026-10-25: Wayback CDX holds no NDOR copies. Dropped.

## NEA monthly / yearly / annual reports — `verified`

- Monthly: https://transd.nea.org.np/category/monthly-operational-reports (~20 posts, BS 2080).
- Yearly: https://transd.nea.org.np/en/category/yearly-operational-reports-1 (Yearly Summary 2079/80).
- Annual: https://nea.org.np/en/category/annual-reports (4 pages; e.g. https://nea.org.np/detail/annual-report-20252026).
- Stored as PDF + Markdown (pymupdf4llm). Which tables hold monthly/annual peak & energy: recorded here after Task 7.

## Data extracted from NEA reports — `verified` (Phase 2, `nea ingest reports ocr`)

| Table | What | Coverage | How validated |
|---|---|---|---|
| `gold.annual_history` | Annual NEA / subsidiary / IPP / **import** / total energy (GWh), **national peak** (+ system peak from 2022) MW | 2013 → 2026 (FY 2069/70 → 2082/83) | sources = total per row; identical across every report repeating a year; FY 2079/80 chart peaks disagree with LDC (LDC kept as `ldc_national_peak_mw`) |
| `gold.report_monthly_balance` | Monthly national / system demand, **import**, **export**, storage, IPP, interruption — MW and GWh | FY 2078/79 (partial) → 2082/83 | per-month table arithmetic + FY total vs annual history; OCR (RapidOCR) preferred, text fallback |
| `silver.report_annual` | LDC summary: annual system/national peak MW (+ date) and energy GWh | FY 2078/79 → 2082/83 | — |
| `silver.report_monthly` | Every month-wise table in every report (raw, generic): incl. per-station monthly generation (Kulekhani etc.), import/export by border point | varies | none (raw) |

Not extractable: Kulekhani reservoir water level (chart image only). Monthly operational reports: 2 exist (2080-10/11), day-wise; NMOR 2080_02..09 404 on NEA's server. FY 2077/78 monthly tables dropped (balanced but mislabeled).

## Open-Meteo weather (ERA5) — `verified`

`https://archive-api.open-meteo.com/v1/archive?latitude=..&longitude=..&start_date=..&end_date=..&daily=temperature_2m_max,temperature_2m_min,precipitation_sum&timezone=Asia/Kathmandu`. 1940→, ~5-day lag, no key (non-commercial). Points: Kathmandu + Terai cities (Biratnagar, Birgunj, Bhairahawa, Nepalgunj, Dhangadhi).

## Open-Meteo Flood / GloFAS river discharge — `verified`

`https://flood-api.open-meteo.com/v1/flood?latitude=..&longitude=..&daily=river_discharge&start_date=..&end_date=..`. Daily m³/s, 1984→, ~5 km grid. Points: 3 basin outlets (Karnali, Koshi, Narayani → `discharge_index`) + 5 plants (Kali Gandaki, Trishuli, Marsyangdi, Upper Tamakoshi, Sunkoshi), each snapped to its main-channel cell (5×5 search ±0.1°, mean flow 2015–24 vs known river size). Kulekhani dropped: catchment too small for the grid. Modelled flow, not gauge truth → validate with DHM data.

## DHM river-watch — `unavailable` (site down since 2026-10-25, reportedly PHP vulnerability)

https://www.dhm.gov.np/hydrology/river-watch embeds `var coordinates = [...]` JSON (~309 gauges: id, name, basin, district, lat/lon, `waterLevel{value, datetime}`, warning/danger level). Latest reading only → history accumulates from our snapshots. Geo-blocked outside Nepal. Historical data only via request form / email.

## DHM historical (email) — `requested` (sent 2026-10-25, awaiting reply)

Draft: `docs/outreach/dhm-data-request.md`. Top-5 sites: Kulekhani reservoir, Tamakoshi @ Busti, Kali Gandaki @ Setibeni, Trishuli @ Betrawati, Marsyangdi @ Bimalnagar. Daily discharge, level, precipitation, temperature, 2010→present.

## Other data points for forecasting

| Data point | Why | Source | Status |
|---|---|---|---|
| Kathmandu + Terai temperature | winter heating / summer cooling load | Open-Meteo ERA5 | verified |
| Holidays & festivals (Dashain, Tihar) | demand dips | `holidays` package (`NP`) | verified |
| River discharge at hydro sites | domestic generation capacity | GloFAS | verified |
| GloFAS seasonal discharge forecast (7 months) | future winter supply driver | Open-Meteo flood API | planned |
| Kulekhani reservoir level | storage for winter peaks | news only, no feed; ask NEA/DHM | requested |
| India exchange after Jan 2025 | import target when NDOR missing | **India customs TradeStat** (monthly 2018 →, `silver.india_trade_monthly`) + **CERC Table 46** IEX buy/sell + price (2023 →, `silver.iex_cross_border_monthly`) — verified. Grid-India daily PSP | unavailable (2026-10-25: `report.grid-india.in` gone from DNS, `grid-india.in` resets connections; user checking in browser) |
| GDP, population | demand trend | World Bank API `NY.GDP.MKTP.KD`, `SP.POP.TOTL` → `silver.macro_yearly`, joined into `gold.annual_history` | verified (1960–2025) |
| Peak demand snapshot | sanity check | nea.org.np homepage "Energy Details" widget | planned |
| New connections / industrial load | demand growth | NEA annual report | Phase 2 |
