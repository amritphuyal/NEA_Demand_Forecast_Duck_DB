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
