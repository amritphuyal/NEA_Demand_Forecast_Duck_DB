# Decisions

Architecture decisions (ADR) + change log. Every repo change appends a change-log entry.

## ADR-001 uv + src layout
- **Context:** fresh `uv init` project.
- **Decision:** `uv` for deps/venv; package in `src/nea_forecast/`; CLI `nea` via `[project.scripts]`.
- **Consequence:** `uv run nea …` everywhere; no requirements.txt.

## ADR-002 No LLM; pdfplumber for NDOR, pymupdf4llm for long reports
- **Context:** NDOR PDFs are 1-page, text-based, fixed layout. Annual reports are 100+ pages.
- **Decision:** pdfplumber text + regex for NDOR (MIT, deterministic). pymupdf4llm converts long reports to Markdown for later table targeting.
- **Consequence:** zero token cost. pymupdf4llm is AGPL — fine for a personal/open repo; swap to pdfplumber text if ever distributed closed-source.

## ADR-003 httpx first, Playwright fallback
- **Context:** NEA sites use F5 bot protection (curl got "Request Rejected" / TSPD challenge).
- **Decision:** httpx with browser-like headers, cookies, 2 s/host throttle, 3 retries. Only on detected challenge → headless Chromium via Playwright.
- **Consequence:** fast path stays light; Chromium only when needed.

## ADR-004 DuckLake with DuckDB-file catalog
- **Context:** single laptop, single writer; need Parquet + SQL + snapshots.
- **Decision:** `ducklake:data/lake/nea.ducklake`, data in `data/lake/files/`. Upsert = delete + insert in one transaction (DuckLake has no PK/unique).
- **Consequence:** one writer at a time. Move catalog to SQLite/Postgres only if a second writer appears.

## ADR-005 Raw files are bronze
- **Context:** parsers will change as layouts change.
- **Decision:** every download saved immutably under `data/raw/<source>/`; `bronze.ingest_log` tracks status per key.
- **Consequence:** silver can be rebuilt from disk without re-scraping.

## ADR-006 Re-implement reference repo, don't copy
- **Context:** [nea-data-warehouse](https://github.com/Unknown-333/nea-data-warehouse) has an MIT badge but no LICENSE file.
- **Decision:** reuse ideas (URL pattern, fields, balance check) with credit in README; write own code.
- **Consequence:** no licence ambiguity.

## ADR-007 Run on a laptop in Nepal
- **Context:** DHM/BIPAD refuse non-Nepal IPs; NEA bot protection is IP/fingerprint sensitive.
- **Decision:** local cron on the user's laptop; no CI scraping.
- **Consequence:** no cloud scheduler; Phase 4 publishes Parquet exports.

## ADR-008 Model ladder, no LSTM
- **Context:** ~640 daily points (2 winters) + long monthly series.
- **Decision:** baselines → statsforecast (ETS/ARIMA/MSTL + exog) → LightGBM; pick simplest within 5% of best on winter backtests.
- **Consequence:** laptop-CPU friendly; revisit deep models only with > 5 yrs daily data.

## ADR-009 Website reads Parquet exports
- **Context:** Cloudflare Pages is static; DuckDB-WASM can't attach a DuckLake catalog reliably.
- **Decision:** `COPY` gold + ml tables to Parquet for the site.
- **Consequence:** site is a read-only snapshot; refresh = re-export + deploy.

## Change log

- **2026-10-25** — Scaffold: deps (httpx, bs4, playwright, pdfplumber, pymupdf4llm, duckdb 2.0, nepali-datetime, holidays), `nea` CLI, `sources.json`, docs (blueprint, flow, data-sources, decisions, DHM email), Phase 1 plan. Removed `main.py`.
- **2026-10-25** — Lakehouse: `lake.py` (connect/upsert/seen/log), `schema.sql` (bronze log + silver tables), `nea status`, `nea maintain` (merge_adjacent_files → expire_snapshots 30 d → cleanup_old_files). DuckDB 2.0: `Relation.fetchone()` removed → use `con.execute(...).fetchone()`. Upsert stages rows in a TEMP table outside the lake transaction (one writable catalog per transaction).
- **2026-10-25** — Fetcher: `fetch.py` (httpx, 2 s/host throttle, retries, https forcing, F5 block detection, Playwright fallback). Live finding: plain httpx and Playwright `context.request` both get F5 "Request Rejected"/TSPD; cookie reuse in httpx also fails. Only full browser navigation (`page.goto` + networkidle) passed, twice, then the IP got flagged and even navigation returned "Request Rejected" (255 B). Wayback CDX has **no** NDOR PDFs (transd or legacy ldc paths) → Task 6 source `unavailable`. Browser fallback needs rework (navigation-based + download capture, slower pace) — pending user decision.
- **2026-10-25** — Fetcher fix (user chose headed browser): F5 detects automation, not IP (same IP works in a normal browser). Browser fallback now = Playwright persistent profile (`data/browser-profile`) on installed **Google Chrome**, headed by default (`NEA_HEADLESS=1` to override), `--enable-automation` dropped + `AutomationControlled` disabled. HTML via page navigation; PDFs via in-page `fetch()` (F5 script attaches tokens). Host that blocks once goes straight to browser (no extra flagged hits), 6 s + jitter pace. `TSPD` alone no longer means blocked (F5 injects it into real pages) — only small (<20 KB) TSPD pages. Verified live: listing + NDOR 2081_09_27 + 2080_01_01. Task 6 (Wayback) dropped: CDX has no NDOR copies.
- **2026-10-25** — NDOR parser (`ndor.py`): pdfplumber text + regex (date header, one 11-number energy line, one `HH:MM` + 9-number peak line); same layout 2080→2081, only header punctuation differs (`For Date 2080/01/01(2023/04/14)`). `qa_ok` = energy/peak balance within ±2 and requirement > 0. `pymupdf4llm` 2.0 on PyPI is an empty package → pinned `<2` (1.28.2, pulls pymupdf + onnxruntime).
- **2026-10-25** — NDOR ingest: listing links via regex (no BeautifulSoup needed). PDF URL built from slug (`…-2081-09-27` → `NDOR%202081_09_27.pdf`), detail page only as fallback (404 / rev slugs) → half the browser hits. Ingest runs oldest-first so newest re-issue wins and an interrupted backfill leaves done posts at the listing tail (keeps "stop at first fully-known page" correct). `Blocked` aborts the run.
- **2026-10-25** — Open-Meteo weather + GloFAS discharge ingesters (from `max(date) − 10 d`, all-null days skipped). Live check: Trishuli point Jan mean 17 m³/s vs Aug 595 m³/s (on-river). DHM river-watch ingester built from researched structure (handmade fixture); live check pending — dhm.gov.np timed out from laptop 2026-10-25. `nea ingest all` now isolates failures per source (exit 1, others still run).
- **2026-10-25** — Calendar + gold: `silver.dim_calendar` (BS date via `nepali_datetime`, `holidays` NP — Dashain labelled e.g. "Bijaya Dashami", season winter = Nov–Apr, FY from 1 Shrawan). Views `gold.daily_features` (calendar ⟕ NEA ⟕ Kathmandu/Terai weather ⟕ discharge index) and `gold.monthly_summary` (per BS month). Views use `IF NOT EXISTS` so connects don't write snapshots; drop a view to change it.
- **2026-10-25** — NEA docs ingester (`nea_docs.py`): monthly/yearly/annual listings filtered by slug keyword (sidebar repeats other posts), every PDF on the detail page → `data/raw/nea_docs/{monthly|yearly|annual}/{slug}.pdf` + `.md` (pymupdf4llm). In-page browser fetch now returns base64 (FileReader) instead of a JSON byte array — needed for 50 MB annual reports. Live run + fixture check pending (Chrome profile busy with NDOR backfill).
- **2026-10-25** — NDOR date header sometimes unpadded (`For Date: 2080/01/4 ( 2023/05/1 )`) → regex accepts 1–2 digit month/day, `bs_date` zero-padded. Days that failed in the first backfill are `parse_error` with PDFs on disk → next `nea ingest ndor` re-parses them without re-downloading.
- **2026-10-25** — Parallel NEA fetch (user request): `fetch_many` runs `BATCH=4` parallel in-page `fetch()` calls per throttled browser round (6 s + jitter) → ~0.5 req/s vs 0.12. Listing walk and NDOR PDFs both batched (~4× faster backfill). Kept small because F5 blocked bursts earlier; `Blocked` still aborts and re-runs resume from saved PDFs.
- **2026-10-25** — Fetch fallback/backoff spec (user: 20 parallel): `NEA_BATCH` (default 20) parallel in-page fetches per round, 6 s + jitter between rounds. On F5 block / 429 / 5xx / page crash: back off 30→60→120→240 s, halve batch, re-solve challenge with real navigation (crash → relaunch Chrome); after 4 consecutive blocks raise `Blocked` (re-run resumes from saved PDFs). 404 → detail page; other per-URL errors → `fetch_error`, retried next run. Backfill run 2 (batch 4) reached 136 days (2023-04-14 → 2023-08-27) before Chrome page closed (`TargetClosedError`).
- **2026-10-25** — Speed fix (user: still slow, try headless). Measured headless real Chrome (masked flags): listing 2.4 s, 20 PDFs in one in-page round 1.0 s (HTTP/1.1). Bottleneck was ours: 2 lake commits per PDF (~1,000 snapshots) + 6–10 s throttle. Now: headless default (`NEA_HEADED=1` to show window), one `nea_daily` upsert + one `log_many` per round, browser delay 2 s + jitter.
- **2026-10-25** — NDOR backfill complete: 633 reports → 612 days (2023-04-14 → 2025-01-11). `-r1` re-issues live in `uploads/shares/press_release/` and replace the original row. Gaps: 21 days never posted; 5 posted as `.html` (NEA serves "Access Restricted") → `not_found`; 2081-08-15 detail page has no NDOR link (user to check). 2024-08-09..12 are all-zero reports → `qa_ok=false`. Fixed: failed keys deep in the listing are now retried each run (discover stops early).
- **2026-10-25** — Discharge points: initial coords landed on side cells (Koshi 0/5 m³/s). Snapped to max-flow GloFAS cell: Karnali (28.59, 81.24) 345/3645, Koshi (26.82, 87.06) 451/4824, added Narayani/Gandaki at Devghat (27.71, 84.38) 257/4512 (Jan–Mar / Jul–Sep means). `gold.daily_features.discharge_index` = sum of these 3 basins (+ `q_narayani/q_koshi/q_karnali`); per-plant points kept but flagged (snapping jumped to other rivers). Open-Meteo 429 → wait Retry-After/60 s. Weather 6 points + calendar loaded. First check: winter domestic gen 26 GWh/d vs summer 44; net India +5.3 GWh/d import vs −7.0 export.
- **2026-10-25** — Run logs: every `nea` CLI run tees stdout to `data/logs/<YYYYmmdd-HHMMSS>-<cmd>.log` with per-line timestamps. NEA docs: monthly listing ignores `?page=` (repeats page 1) → walk stops when a page adds nothing not already queued; NMOR 2080_02..09 PDFs 404 on NEA's side → `not_found`. DHM down (site offline, reportedly PHP vulnerability) → source `unavailable`, ingester kept.
- **2026-10-25** — Report extraction (`reports.py`, `nea ingest reports`, `nea search <regex>`). PyMuPDF `find_tables()` shreds NEA's chart-style balance tables (62-col grids), so parse pymupdf4llm Markdown instead: any table with Nepali month names across the header row or down the first column → `silver.report_monthly` (doc, fy, table, title, series, bs_month, value); annual LDC summary (system/national peak MW, energy GWh) by regex → `silver.report_annual`. `gold.report_monthly_balance` picks national/system demand, import, export, storage, IPP, interruption per (fy, month, MW|GWh). Dry run: FY 2076/77 → 2082/83 balance tables found; 2025/26 national peak 2479 MW matches LDC summary. Kulekhani reservoir level exists only as chart images (needs OCR) → use Kulekhani monthly generation from station tables as storage proxy.
- **2026-10-25** — Report consistency check: monthly balance tables are text only in FY 2077/78, 2078/79 (partly garbled: 10–11 months), 2081/82, 2082/83 — the clean ones reconcile with each report's LDC summary (2081/82: 14,065 vs 14,067 GWh; 2082/83: 15,140 vs 15,139.94). FY 2079/80, 2080/81 and ≤ 2076/77 balance tables are images. Best consistent source: the multi-year "Total Energy Available & Peak Demand" chart text → `silver.report_energy_history` / `gold.annual_history`: 2013–2026 annual NEA/subsidiary/IPP/import/total GWh + national (and from 2022 system) peak MW, each row validated by sources = total, identical across every report that repeats a year. Flag: FY 2079/80 chart peaks (1870/1986) ≠ its LDC summary (1986.39/2171.15). LDC regex now handles `(11 July 2023)` and missing units.
- **2026-10-25** — OCR (`ocr.py`, `nea ingest ocr`): RapidOCR (PaddleOCR on ONNX, pip-only, reuses onnxruntime). Compared on FY 2080/81 capacity page: RapidOCR 29 s/page, OnnxTR 313 s/page, same digits; Tesseract skipped (system package, weaker on tables). Only 4 balance tables are image-only (FY 2079/80 p149–150, FY 2080/81 p187–188); older reports (≤ 2019) have no monthly balance tables. Rows rebuilt by y-clustering; a month is kept only if sources (IPP+subsidiary+ROR+import+storage+solar+thermal+interruption) = national demand + export (±5 MW / ±2 GWh). OCR boxes cached in `data/raw/nea_docs/ocr/*.json`. NEA labels the FY 2079/80 energy table "(MW)"; unit taken from "Energy" → GWh.
- **2026-10-25** — Transparency: every ingest step prints `▶ start` / `✔ N rows in Xs` / `✖ FAILED after Xs`, plus per-item progress (per report, per OCR page with valid months, per Open-Meteo point with date range), all teed with timestamps into `data/logs/`.
