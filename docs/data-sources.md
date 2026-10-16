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

## Open-Meteo weather (ERA5) — `verified`

`https://archive-api.open-meteo.com/v1/archive?latitude=..&longitude=..&start_date=..&end_date=..&daily=temperature_2m_max,temperature_2m_min,precipitation_sum&timezone=Asia/Kathmandu`. 1940→, ~5-day lag, no key (non-commercial). Points: Kathmandu + Terai cities (Biratnagar, Birgunj, Bhairahawa, Nepalgunj, Dhangadhi).

## Open-Meteo Flood / GloFAS river discharge — `needs_user_verification`

`https://flood-api.open-meteo.com/v1/flood?latitude=..&longitude=..&daily=river_discharge&start_date=..&end_date=..`. Daily m³/s, 1984→, ~5 km grid. Points at major hydro sites (see `sources.json`); coordinates approximate — each must show monsoon peak ≫ winter or it's off-river.

## DHM river-watch — `unavailable` (site down since 2026-10-25, reportedly PHP vulnerability)

https://www.dhm.gov.np/hydrology/river-watch embeds `var coordinates = [...]` JSON (~309 gauges: id, name, basin, district, lat/lon, `waterLevel{value, datetime}`, warning/danger level). Latest reading only → history accumulates from our snapshots. Geo-blocked outside Nepal. Historical data only via request form / email.

## DHM historical (email) — `requested`

Draft: `docs/outreach/dhm-data-request.md`. Top-5 sites: Kulekhani reservoir, Tamakoshi @ Busti, Kali Gandaki @ Setibeni, Trishuli @ Betrawati, Marsyangdi @ Bimalnagar. Daily discharge, level, precipitation, temperature, 2010→present.

## Other data points for forecasting

| Data point | Why | Source | Status |
|---|---|---|---|
| Kathmandu + Terai temperature | winter heating / summer cooling load | Open-Meteo ERA5 | verified |
| Holidays & festivals (Dashain, Tihar) | demand dips | `holidays` package (`NP`) | verified |
| River discharge at hydro sites | domestic generation capacity | GloFAS | needs_user_verification |
| GloFAS seasonal discharge forecast (7 months) | future winter supply driver | Open-Meteo flood API | planned |
| Kulekhani reservoir level | storage for winter peaks | news only, no feed; ask NEA/DHM | requested |
| India exchange after Jan 2025 | import target when NDOR missing | Grid-India NLDC PSP PDFs (`report.grid-india.in`) | planned |
| GDP | demand trend | World Bank API `NY.GDP.MKTP.KD` | planned |
| Peak demand snapshot | sanity check | nea.org.np homepage "Energy Details" widget | planned |
| New connections / industrial load | demand growth | NEA annual report | Phase 2 |
