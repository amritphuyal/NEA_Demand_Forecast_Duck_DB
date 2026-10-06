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
