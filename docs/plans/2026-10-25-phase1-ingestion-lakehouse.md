# NEA Demand Forecast — Blueprint + Phase 1 (Ingestion & DuckLake) Implementation Plan

## Context

Mission: forecast Nepal (NEA) electricity demand, focused on **winter** (Nov–Apr) when run-of-river hydro drops, Kulekhani is the only storage, and Nepal imports from India. Repo today = bare `uv init` scaffold (`main.py`, empty README, `pyproject.toml` py>=3.12, no deps).

User decisions (2026-10-25):
- **Data gap:** use every source and fill gaps. Daily NEA reports (NDOR) on transd exist only **2023-04-14 → 2025-01-11** (639 PDFs, series frozen). Add monthly/yearly operational reports, NEA annual reports (long monthly/annual history), Wayback Machine copies of the legacy `nea.org.np/admin/assets/uploads/ldc/` PDFs. User chases NEA for post-2025 data in parallel.
- **Run host:** user's laptop **in Nepal** (DHM/BIPAD block foreign IPs; NEA has F5 bot protection, which blocked plain curl from this laptop → Playwright fallback).
- **Forecast targets:** daily short-term (peak MW + energy MWh, 7–30 d), winter seasonal monthly outlook, India import need directly.
- **Docs shape:** blueprint + phased plans. This file = Phase 1 detailed plan; Phase 2 (doc parsing + EDA) and Phase 3 (ML) plans get written after Phase 1 data is in hand. Phase 4 = Cloudflare site.

Research findings that drive the design:
- NDOR PDF = 1 page, text-based (Excel "Print to PDF"). Header `For Date: 2081/09/27 ( 2025/01/11 )`. Two tables: "Daily Energy Values (MWh)" (11 values) and "Peak Time Generation, Demand and Cross Border Exchange (MW)" (peak time + 9 values). No per-plant or reservoir data.
- transd listing: `https://transd.nea.org.np/en/category/daily-operational-reports-1?page=N` (64 pages × 10, newest first), server-rendered HTML; detail `https://transd.nea.org.np/detail/nepal-daily-operational-report-2081-09-27`; PDF `https://transd.nea.org.np/uploads/shares/Daily_op_reports/NDOR%20{YYYY}_{MM}_{DD}.pdf`. Pagination links are `http://` → force https. "Highlights" sidebar duplicates posts.
- Reference repo `github.com/Unknown-333/nea-data-warehouse` (Aayush Paudel): pdfplumber, positional columns, no listing scrape, full rewrite each run, Postgres+dbt. **No LICENSE file** (only MIT badge) → re-implement ideas, don't copy code; credit in README.
- DHM `https://www.dhm.gov.np/hydrology/river-watch` embeds `var coordinates = [...];` JSON (~309 gauges, latest reading only: `id, name, basin, district, latitude, longitude, series_id, waterLevel{value, datetime}, warning_level, danger_level, status, steady`).
- Open-Meteo (free, no key, non-commercial): ERA5 archive `archive-api.open-meteo.com/v1/archive` (1940→, ~5-day lag); GloFAS flood `flood-api.open-meteo.com/v1/flood?daily=river_discharge` (1984→, m³/s).
- DuckLake 1.0 stable (Apr 2026). No enforced PK/unique → upsert = delete+insert. DuckDB-file catalog = single writer (fine for a laptop).

**Plan file location on execution:** Task 1 copies this plan verbatim to `docs/plans/2026-10-25-phase1-ingestion-lakehouse.md` (the repo's blueprint record).

---

**Goal:** Incremental, LLM-free Python ingestion of NEA reports, weather, river discharge and gauge levels into a DuckLake lakehouse (bronze/silver/gold), queryable from DuckDB, plus the project's blueprint docs.

**Architecture:** `nea` CLI (argparse) runs per-source ingesters. Each ingester: discover → skip keys already in `bronze.ingest_log` → fetch (httpx, Playwright fallback on F5 challenge) → save immutable raw file under `data/raw/<source>/` → parse → upsert into `silver.*` DuckLake tables. Gold = SQL views joining NEA daily + calendar + weather + discharge. Raw files are the true bronze; silver can be rebuilt from them.

**Tech Stack:** Python 3.12, uv, httpx, beautifulsoup4, playwright (chromium), pdfplumber (NDOR tables), pymupdf4llm (long PDFs → Markdown), duckdb + ducklake extension, nepali-datetime, holidays, pytest.

**Spec:** user brief in this conversation + the Context section above (copied into `docs/blueprint.md` in Task 1).

## Global Constraints

- No LLM / AI API anywhere in the pipeline. Pure Python parsing.
- Python `>=3.12`, managed with `uv` (`uv add`, `uv run`). Package lives in `src/nea_forecast/`, CLI entry `nea = "nea_forecast.cli:main"`.
- Polite scraping: ≥2 s between requests to the same host, User-Agent `nea-demand-forecast/0.1 (+research; contact: repo owner)`, 3 retries with exponential backoff.
- Raw downloads are immutable: `data/raw/<source>/<key>.<ext>`; never overwritten unless `--force`. `data/` is gitignored.
- Lakehouse: `ATTACH 'ducklake:data/lake/nea.ducklake' AS lake (DATA_PATH 'data/lake/files/')`; schemas `bronze`, `silver`, `gold` (`ml` added in Phase 3).
- Every re-run is idempotent: no duplicate rows; a key is logged `ok` only after its silver upsert commits.
- Every task that changes the repo appends a dated entry to `docs/developer/decisions.md` (change log section) in the same commit.
- Tests run offline (`uv run pytest`) against committed fixtures in `tests/fixtures/`; live-network checks are manual verification steps only.
- Commits: Conventional Commits, subject ≤50 chars.

## Review Focus

1. **F5 challenge page saved as a PDF** → a body not starting with `%PDF` must never be written as `.pdf` or logged `ok`. Test in Task 3.
2. **Holiday / all-zero / malformed NDOR** → row stored with `qa_ok = false` (all-zero) or key logged `parse_error` (malformed); ingest continues with the next key. Tests in Task 4 and Task 5.
3. **Interrupted run then re-run** → no duplicates, failed keys retried. Test in Task 2 (upsert twice → same count) and Task 5 (log not written on parse failure).
4. **ERA5 trailing nulls (5-day lag)** → null days skipped, not stored as 0; next run refetches last 10 days. Test in Task 8.
5. **"rev1" re-issued report for same date** → same `date` key, later fetch replaces earlier, `source_url` recorded. Test in Task 5.

---

## File Structure

```
pyproject.toml                    # deps + [project.scripts] nea
sources.json                      # source registry (URLs, points, status) — read by code
README.md                         # overview, quickstart, credits
docs/blueprint.md                 # mission, architecture, roadmap phases 1–4, model strategy
docs/flow.md                      # end-to-end data flow + incremental logic + cron
docs/data-sources.md              # every source researched, status, extra data points
docs/developer/decisions.md       # ADR log + change log
docs/plans/2026-10-25-phase1-ingestion-lakehouse.md
src/nea_forecast/__init__.py
src/nea_forecast/lake.py          # connect, schema bootstrap, upsert, ingest_log
src/nea_forecast/schema.sql       # DDL for bronze/silver tables + gold views
src/nea_forecast/fetch.py         # httpx client, block detection, Playwright fallback
src/nea_forecast/ndor.py          # NDOR discover (transd + Wayback), parse PDF, ingest
src/nea_forecast/nea_docs.py      # monthly/yearly/annual reports → raw PDF + Markdown
src/nea_forecast/open_meteo.py    # weather + river discharge
src/nea_forecast/dhm.py           # river-watch gauge snapshot
src/nea_forecast/calendar.py      # dim_calendar (BS dates, holidays, season, FY)
src/nea_forecast/cli.py           # nea ingest|status|maintain
tests/test_lake.py, test_fetch.py, test_ndor.py, test_nea_docs.py, test_open_meteo.py, test_dhm.py, test_calendar.py
tests/fixtures/                   # 2 NDOR PDFs, listing/detail HTML, small JSON/HTML samples
```
Delete `main.py` (replaced by CLI).

---

### Task 1: Docs + project skeleton

**Files:**
- Create: `README.md`, `docs/blueprint.md`, `docs/flow.md`, `docs/data-sources.md`, `docs/developer/decisions.md`, `docs/plans/2026-10-25-phase1-ingestion-lakehouse.md`, `sources.json`, `src/nea_forecast/__init__.py`, `src/nea_forecast/cli.py`
- Modify: `pyproject.toml`, `.gitignore`; Delete: `main.py`

**Interfaces:**
- Produces: `nea_forecast.cli.main(argv: list[str] | None = None) -> int` with subcommands `ingest <source>...|all`, `status`, `maintain`; `INGESTERS: dict[str, Callable[[duckdb.DuckDBPyConnection], int]]` (empty now, each later task registers one). `load_sources() -> dict` in `nea_forecast/__init__.py` reads `sources.json`.

- [ ] **Step 1:** `uv add httpx beautifulsoup4 playwright pdfplumber pymupdf4llm duckdb nepali-datetime holidays && uv add --dev pytest`; `uv run playwright install chromium`. Add `[project.scripts] nea = "nea_forecast.cli:main"` and src-layout build backend (`uv_build`). Add `data/` to `.gitignore`. Delete `main.py`.
- [ ] **Step 2: Write docs** (content requirements; prose is the implementer's):
  - `README.md`: mission, quickstart (`uv sync`, `uv run playwright install chromium`, `uv run nea ingest all`, `uv run nea status`), layout, **Credits**: "Inspired by [nea-data-warehouse](https://github.com/Unknown-333/nea-data-warehouse) by Aayush Paudel (@Unknown-333) — NDOR URL pattern, field list, energy-balance check idea." Data attribution: NEA, DHM, Open-Meteo (CC BY 4.0), Copernicus GloFAS, ERA5.
  - `docs/blueprint.md`: Context section above; architecture diagram (ASCII: sources → raw → bronze log → silver → gold → ml → parquet export → Cloudflare Pages); roadmap: Phase 1 (this plan), Phase 2 (parse monthly/annual report tables into `silver.nea_monthly`, EDA), Phase 3 (models), Phase 4 (site); **Model strategy** (below); open risks (NDOR stops Jan-2025, short daily history = 2 winters, gov sites geo-blocked/bot-protected).
  - **Model strategy** section text must state: baselines first (seasonal naive, same-BS-date-last-year); then `statsforecast` AutoETS/AutoARIMA/MSTL with exogenous (temp, holidays, discharge); then LightGBM on lag/calendar/weather/discharge features; rolling-origin backtest, metrics MAE + MAPE overall and winter-only; pick the simplest model within 5% of best. **No LSTM** — ~640 daily points is too little; revisit only if daily history > 5 yrs. Seasonal outlook = monthly series from annual reports + ETS/SARIMA; import need = demand forecast − domestic generation forecast (generation regressed on GloFAS discharge, GloFAS seasonal forecast as future driver) and also modelled directly on `net_exchange_india_mwh`. All laptop-CPU.
  - `docs/flow.md`: per-source incremental rule table (NDOR: walk listing pages until a page has zero new slugs; Wayback: CDX list minus logged keys; docs: listing minus logged; Open-Meteo: from `max(date) − 10 d`; DHM: append snapshot, dedupe `(station_id, observed_at)`); recommended cron `0 */3 * * * cd <repo> && uv run nea ingest all >> data/ingest.log 2>&1`.
  - `docs/data-sources.md`: one section per source from Context + **extra data points** list: Kathmandu + Terai temperature (heating vs cooling), holidays/festivals (Dashain/Tihar dips), GloFAS discharge at hydro sites, GloFAS seasonal discharge forecast, Kulekhani level (news only; no feed), Grid-India NLDC PSP daily PDFs transnational exchange (`report.grid-india.in`) as post-2025 import proxy, World Bank GDP (`api.worldbank.org/v2/country/NPL/indicator/NY.GDP.MKTP.KD?format=json`), NEA "Energy Details" homepage widget, new-connections/industrial load (annual report). Mark each `verified` / `needs_user_verification`.
  - `docs/outreach/dhm-data-request.md`: the DHM email draft from this conversation (top-5 sites: Kulekhani reservoir, Tamakoshi@Busti, Kali Gandaki@Setibeni, Trishuli@Betrawati, Marsyangdi@Bimalnagar; daily discharge/level/precip/temp 2010→present; educational, non-commercial). `docs/data-sources.md` gets a `dhm_manual` entry (status `requested`); Phase 2 adds a CSV/Excel loader into `silver.river_discharge_daily` (`point` = DHM station index) once data arrives.
  - `docs/developer/decisions.md`: ADR entries (Context/Decision/Consequence, 3–5 lines each): ADR-001 uv + src layout; ADR-002 no LLM, pdfplumber for NDOR, pymupdf4llm (AGPL — ok for personal/open repo, swap to pdfplumber text if distributing closed) for long-report → Markdown; ADR-003 httpx primary, Playwright fallback only on F5 challenge; ADR-004 DuckLake w/ DuckDB-file catalog, local Parquet, upsert = delete+insert (no PK in DuckLake), upgrade to SQLite/Postgres catalog only if a second writer appears; ADR-005 raw files = bronze, immutable, silver rebuildable; ADR-006 re-implement (not copy) reference repo — no LICENSE; ADR-007 runs on laptop in Nepal (geo-blocks); ADR-008 model ladder, no LSTM; ADR-009 web gets Parquet exports, not the live catalog. Then `## Change log` with first entry.
- [ ] **Step 3: Write `sources.json`** — array of objects `{id, name, kind, urls, fetcher, history, cadence, status, target_table, notes}` for ids `nea_ndor`, `nea_ndor_wayback`, `nea_monthly_reports`, `nea_yearly_reports`, `nea_annual_reports`, `open_meteo_weather`, `open_meteo_discharge`, `dhm_river_watch`, `grid_india_psp` (status `planned`), `world_bank_gdp` (`planned`). Weather `points`: Kathmandu 27.70,85.32; Biratnagar 26.45,87.27; Birgunj 27.01,84.88; Bhairahawa 27.50,83.45; Nepalgunj 28.05,81.62; Dhangadhi 28.70,80.59. Discharge `points` (status `needs_user_verification` — approximate, verify each lands on the river cell): Kali Gandaki A 27.98,83.58; Trishuli 27.92,85.15; Marsyangdi 28.08,84.43; Upper Tamakoshi 27.90,86.21; Kulekhani 27.59,85.15; Sunkoshi 27.76,85.86; Karnali Chisapani 28.64,81.29; Koshi Chatara 26.87,87.16.
- [ ] **Step 4: Test** `tests/test_cli.py::test_help` — `main(["--help"])` raises `SystemExit(0)`; `test_sources_json_ids_unique` — ids unique and every entry has `status`.
- [ ] **Step 5:** `uv run pytest -v` → PASS; `uv run nea --help` prints subcommands.
- [ ] **Step 6: Commit** `chore: scaffold package, docs blueprint and source registry`.

### Task 2: DuckLake connection, schema, upsert, ingest log

**Files:** Create `src/nea_forecast/lake.py`, `src/nea_forecast/schema.sql`, `tests/test_lake.py`

**Interfaces:**
- Produces:
  - `connect(root: Path = Path("data"), read_only: bool = False) -> duckdb.DuckDBPyConnection` — installs/loads ducklake, attaches `lake`, `USE lake`, runs `schema.sql` (all `CREATE ... IF NOT EXISTS`).
  - `upsert(con, table: str, rows: list[dict], key: tuple[str, ...]) -> int` — one transaction: stage rows, `DELETE` matching keys, `INSERT`; returns rows written.
  - `seen(con, source: str) -> set[str]` — keys with status `ok` (or `not_found`, so 404s aren't retried).
  - `log(con, source: str, key: str, url: str, status: str, sha256: str | None = None) -> None` (status ∈ `ok|parse_error|not_found|fetch_error`; upserts on `(source, key)`).
- `schema.sql` tables:
  - `bronze.ingest_log(source VARCHAR, key VARCHAR, url VARCHAR, status VARCHAR, sha256 VARCHAR, fetched_at TIMESTAMP)`
  - `silver.nea_daily(date DATE, bs_date VARCHAR, nea_gen_mwh, nea_sub_gen_mwh, ipp_gen_mwh, import_mwh, total_available_mwh, export_mwh, net_met_mwh, interruption_mwh, deficit_mwh, requirement_mwh, net_exchange_india_mwh DOUBLE, peak_time TIME, peak_gen_mw, peak_import_mw, peak_availability_mw, peak_export_mw, peak_met_mw, peak_interruption_mw, peak_deficit_mw, peak_demand_mw, peak_net_exchange_india_mw DOUBLE, qa_ok BOOLEAN, source VARCHAR, source_url VARCHAR)`
  - `silver.nea_document(key VARCHAR, category VARCHAR, title VARCHAR, published DATE, pdf_path VARCHAR, md_path VARCHAR, source_url VARCHAR)`
  - `silver.weather_daily(date DATE, point VARCHAR, tmax_c, tmin_c, precip_mm DOUBLE)`
  - `silver.river_discharge_daily(date DATE, point VARCHAR, discharge_m3s DOUBLE)`
  - `silver.river_level_obs(station_id INTEGER, observed_at TIMESTAMP, name, basin, district VARCHAR, lat, lon, level_m, warning_level, danger_level DOUBLE, status VARCHAR)`
  - `silver.dim_calendar` and gold views are added in Task 10.

- [ ] **Step 1: Failing tests** (use `tmp_path`):
```python
def test_connect_creates_schema(tmp_path):
    con = connect(tmp_path)
    names = {r[0] for r in con.sql("select table_schema||'.'||table_name from information_schema.tables where table_catalog='lake'").fetchall()}
    assert {"bronze.ingest_log", "silver.nea_daily", "silver.weather_daily"} <= names

def test_upsert_idempotent_and_replaces(tmp_path):
    con = connect(tmp_path)
    rows = [{"date": date(2025,1,1), "point": "ktm", "tmax_c": 10.0, "tmin_c": 1.0, "precip_mm": 0.0}]
    upsert(con, "silver.weather_daily", rows, ("date", "point"))
    upsert(con, "silver.weather_daily", [{**rows[0], "tmax_c": 12.0}], ("date", "point"))
    assert con.sql("select count(*), max(tmax_c) from silver.weather_daily").fetchone() == (1, 12.0)

def test_seen_only_ok_and_not_found(tmp_path):
    con = connect(tmp_path)
    log(con, "nea_ndor", "a", "u", "ok"); log(con, "nea_ndor", "b", "u", "parse_error"); log(con, "nea_ndor", "c", "u", "not_found")
    assert seen(con, "nea_ndor") == {"a", "c"}

def test_reconnect_persists(tmp_path):
    con = connect(tmp_path); log(con, "s", "k", "u", "ok"); con.close()
    assert seen(connect(tmp_path), "s") == {"k"}
```
- [ ] **Step 2:** `uv run pytest tests/test_lake.py -v` → FAIL (ImportError).
- [ ] **Step 3:** Implement `lake.py` + `schema.sql`. Add `nea maintain` in CLI → `CALL ducklake_merge_adjacent_files('lake')` then `CALL ducklake_expire_snapshots('lake', older_than => now() - INTERVAL 30 DAY)` (verify function names against installed DuckLake docs; record in decisions.md). Add `nea status` → per silver table `count(*)`, `min/max(date)`.
- [ ] **Step 4:** `uv run pytest tests/test_lake.py -v` → PASS.
- [ ] **Step 5: Commit** `feat: ducklake connection, schema, idempotent upsert`.

### Task 3: HTTP fetch with bot-challenge fallback

**Files:** Create `src/nea_forecast/fetch.py`, `tests/test_fetch.py`

**Interfaces:**
- Produces:
  - `is_blocked(body: bytes, content_type: str) -> bool` — True if html body contains `Request Rejected`, `TSPD`, or `blocked by our security policy`.
  - `fetch(url: str, expect_pdf: bool = False) -> bytes` — httpx Client (browser-like headers + project UA suffix, cookies kept, timeout 60 s, follow redirects, https forced), per-host 2 s throttle, 3 retries on 5xx/timeouts; on `is_blocked` → `fetch_browser(url)`. Raises `NotFound` on 404, `Blocked` if browser also blocked, `FetchError` if `expect_pdf` and body doesn't start with `%PDF`.
  - `fetch_browser(url: str) -> bytes` — lazily started single Playwright chromium context; `page.goto(url)` on site root once to pass challenge, then `context.request.get(url).body()`.

- [ ] **Step 1: Failing tests:**
```python
def test_is_blocked_f5(): assert is_blocked(b"<html>Request Rejected ... support ID", "text/html")
def test_is_blocked_tspd(): assert is_blocked(b"<script>window.TSPD...", "text/html")
def test_pdf_not_blocked(): assert not is_blocked(b"%PDF-1.7 ...", "application/pdf")
def test_fetch_rejects_non_pdf(monkeypatch):  # httpx.MockTransport returning 200 text/html "<html>ok</html>"
    with pytest.raises(FetchError): fetch("https://x.test/a.pdf", expect_pdf=True)
def test_fetch_404(monkeypatch):  # MockTransport 404
    with pytest.raises(NotFound): fetch("https://x.test/missing.pdf")
```
(Expose module-level `_transport` override or a `client` param so tests inject `httpx.MockTransport`.)
- [ ] **Step 2:** run → FAIL. **Step 3:** implement. **Step 4:** run → PASS.
- [ ] **Step 5: Manual live check:** `uv run python -c "from nea_forecast.fetch import fetch; print(len(fetch('https://transd.nea.org.np/en/category/daily-operational-reports-1')))"` → prints length > 10000 and no exception; note in decisions.md whether httpx or the Playwright path served it.
- [ ] **Step 6: Commit** `feat: polite fetcher with F5 challenge fallback`.

### Task 4: NDOR PDF parser

**Files:** Create `src/nea_forecast/ndor.py` (parse part), `tests/test_ndor.py`, `tests/fixtures/NDOR_2081_09_27.pdf`, `tests/fixtures/NDOR_2080_01_01.pdf`, `tests/fixtures/zero.pdf` (optional, if an all-zero day is found during backfill — add later)

**Interfaces:**
- Produces: `class ParseError(Exception)`; `parse_pdf(path: Path) -> dict` returning keys = `silver.nea_daily` columns except `source`, `source_url`; `check_balance(row: dict, tol: float = 2.0) -> bool`.

- [ ] **Step 1:** Download fixtures with `fetch(..., expect_pdf=True)` from `https://transd.nea.org.np/uploads/shares/Daily_op_reports/NDOR%202081_09_27.pdf` and `...NDOR%202080_01_01.pdf`.
- [ ] **Step 2: Failing tests:**
```python
def test_parse_2081_09_27():
    r = parse_pdf(FIX / "NDOR_2081_09_27.pdf")
    assert r["date"] == date(2025, 1, 11) and r["bs_date"] == "2081-09-27"
    assert (r["nea_gen_mwh"], r["nea_sub_gen_mwh"], r["ipp_gen_mwh"], r["import_mwh"]) == (6251, 5017, 15623, 6845)
    assert (r["total_available_mwh"], r["export_mwh"], r["net_met_mwh"]) == (33735, 0, 33735)
    assert (r["interruption_mwh"], r["deficit_mwh"], r["requirement_mwh"], r["net_exchange_india_mwh"]) == (1700, 0, 35435, 6845)
    assert r["peak_time"] == time(17, 55)
    assert (r["peak_gen_mw"], r["peak_import_mw"], r["peak_availability_mw"], r["peak_export_mw"], r["peak_met_mw"]) == (1367, 211, 1578, 0, 1578)
    assert (r["peak_interruption_mw"], r["peak_deficit_mw"], r["peak_demand_mw"], r["peak_net_exchange_india_mw"]) == (350, 0, 1928, 211)
    assert r["qa_ok"] is True

def test_parse_oldest_layout():
    r = parse_pdf(FIX / "NDOR_2080_01_01.pdf")
    assert r["date"] == date(2023, 4, 14) and check_balance(r)

def test_check_balance_flags_bad():
    r = parse_pdf(FIX / "NDOR_2081_09_27.pdf"); r["import_mwh"] += 500
    assert not check_balance(r)

def test_all_zero_row_not_qa_ok():
    r = parse_pdf(FIX / "NDOR_2081_09_27.pdf"); assert qa_ok({**r, **{k: 0 for k in ENERGY_COLS}}) is False

def test_garbage_raises(tmp_path):
    p = tmp_path / "x.pdf"; p.write_bytes(minimal_pdf_with_text("hello"))  # build via pdfplumber-free bytes or skip if hard: use a 1-page PDF made with pymupdf
    with pytest.raises(ParseError): parse_pdf(p)
```
- [ ] **Step 3:** run → FAIL.
- [ ] **Step 4: Implement.** Approach: `pdfplumber` page 1 `extract_text()`; date via `For Date:\s*(\d{4}/\d{2}/\d{2})\s*\(\s*(\d{4}/\d{2}/\d{2})\s*\)`; energy = first line after "Daily Energy Values" containing exactly 11 numbers; peak = first line after "Peak Time" containing `HH:MM` + 9 numbers. Numbers regex `-?[\d,]+(?:\.\d+)?`, strip commas. If either line missing → `ParseError`. Balance rules (tol 2): `nea+sub+ipp+import ≈ available`; `available − export ≈ net_met`; `net_met + interruption + deficit ≈ requirement`; `peak_gen + peak_import ≈ peak_availability`; `peak_met + peak_interruption + peak_deficit ≈ peak_demand`. `qa_ok(row) = check_balance(row) and requirement_mwh > 0`. If the 2080 layout differs, fall back to `extract_tables()` label-matching and keep both tests green — record the difference in decisions.md.
- [ ] **Step 5:** run → PASS. **Step 6: Commit** `feat: NDOR pdf parser with energy-balance QA`.

### Task 5: NDOR discovery + incremental ingest (transd)

**Files:** Modify `src/nea_forecast/ndor.py`, `src/nea_forecast/cli.py`; Create `tests/fixtures/ndor_listing_p1.html`, `tests/fixtures/ndor_detail.html` (saved from live site), tests in `tests/test_ndor.py`

**Interfaces:**
- Consumes: `fetch`, `NotFound`, `parse_pdf`, `ParseError`, `qa_ok`, `upsert`, `seen`, `log`.
- Produces:
  - `parse_listing(html: str) -> list[tuple[str, str]]` — `(slug, detail_url)`, only `/detail/nepal-daily-operational-report-*`, https, deduped, page order.
  - `parse_detail(html: str) -> str` — first `a[href$=".pdf"]` containing `Daily_op_reports`.
  - `discover(known: set[str], max_pages: int = 80) -> list[tuple[str, str]]` — pages 1..N, stop after first page with zero unseen slugs (or empty page).
  - `ingest(con) -> int` — for each new slug: fetch detail → pdf (`expect_pdf=True`) → save `data/raw/nea_ndor/{slug}.pdf` → `parse_pdf` → upsert `silver.nea_daily` key `("date",)` with `source="transd"`, `source_url` → `log(ok, sha256)`. `ParseError` → `log(parse_error)`, continue. Registered as `INGESTERS["ndor"]`.

- [ ] **Step 1: Failing tests:**
```python
def test_parse_listing():
    items = parse_listing((FIX / "ndor_listing_p1.html").read_text())
    assert len(items) == 10 and len({s for s, _ in items}) == 10
    assert all(u.startswith("https://transd.nea.org.np/detail/nepal-daily-operational-report-") for _, u in items)

def test_parse_detail():
    assert parse_detail((FIX / "ndor_detail.html").read_text()).endswith(".pdf")

def test_discover_stops_at_known(monkeypatch):  # fetch stub: page1 -> fixture, page2 -> raise AssertionError
    items = parse_listing((FIX / "ndor_listing_p1.html").read_text())
    known = {s for s, _ in items[3:]}
    assert [s for s, _ in discover(known)] == [s for s, _ in items[:3]]

def test_ingest_idempotent_and_parse_error_logged(tmp_path, monkeypatch):
    # stub discover -> [("good", u1), ("bad", u2)], fetch -> fixture pdf bytes for good, garbage pdf for bad
    con = connect(tmp_path); ingest(con); ingest(con)
    assert con.sql("select count(*) from silver.nea_daily").fetchone()[0] == 1
    assert con.sql("select status from bronze.ingest_log where key='bad'").fetchone()[0] == "parse_error"

def test_rev1_replaces_same_date(tmp_path, monkeypatch):
    # two slugs both parsing to 2025-01-11, second with source_url ending 'rev1.pdf' -> 1 row, url rev1
```
- [ ] **Step 2:** FAIL → **Step 3:** implement → **Step 4:** PASS.
- [ ] **Step 5: Live backfill:** `uv run nea ingest ndor` then `uv run nea status` → `silver.nea_daily` ≈ 630+ rows, min date 2023-04-14, max 2025-01-11. Query `select count(*) from bronze.ingest_log where status<>'ok'` and list failures in decisions.md. Re-run `uv run nea ingest ndor` → finishes after 1 listing page, 0 new rows.
- [ ] **Step 6: Commit** `feat: incremental NDOR ingest from transd`.

### Task 6: Legacy NDOR via Wayback Machine (gap filler)

**Files:** Modify `src/nea_forecast/ndor.py`, `cli.py`, `tests/test_ndor.py`; Create `tests/fixtures/wayback_cdx.json` (3 handmade rows)

**Interfaces:**
- Produces: `parse_cdx(rows: list[list[str]]) -> list[tuple[str, str]]` → `(key, snapshot_url)` with key `NDOR_YYYY_MM_DD` from original URL, snapshot `https://web.archive.org/web/{timestamp}id_/{original}`, deduped by key (latest timestamp), NDOR files only (skip `NMOR`). `ingest_wayback(con) -> int` registered `INGESTERS["ndor_wayback"]`; source `nea_ndor_wayback`; skips dates already present in `silver.nea_daily` (transd wins: upsert only if date absent).
- CDX query (one per host `nea.org.np`, `www.nea.org.np`, `cms.nea.org.np`): `https://web.archive.org/cdx/search/cdx?url={host}/admin/assets/uploads/ldc/&matchType=prefix&output=json&filter=statuscode:200&fl=timestamp,original`.

- [ ] **Step 1: Failing test:** `test_parse_cdx` — fixture has 2 snapshots of same NDOR (different timestamps) + 1 NMOR → returns 1 item, latest timestamp, `id_` in URL.
- [ ] **Step 2–4:** FAIL → implement → PASS.
- [ ] **Step 5: Live:** `uv run nea ingest ndor_wayback`; record in `docs/data-sources.md` how many days recovered and date range (if CDX returns 0, mark source `unavailable` and move on).
- [ ] **Step 6: Commit** `feat: recover legacy NDOR pdfs from Wayback`.

### Task 7: NEA monthly / yearly / annual reports → raw PDF + Markdown

**Files:** Create `src/nea_forecast/nea_docs.py`, `tests/test_nea_docs.py`, `tests/fixtures/annual_listing.html`

**Interfaces:**
- Produces: `parse_doc_listing(html: str, base: str) -> list[tuple[str, str, str]]` → `(slug, title, detail_url)` for `/detail/` links; `ingest_docs(con) -> int` registered `INGESTERS["docs"]`. Categories from `sources.json` (`nea_monthly_reports`, `nea_yearly_reports`, `nea_annual_reports`): walk `?page=N` until empty, fetch detail, every `a[href$=".pdf"]` → `data/raw/nea_docs/{category}/{slug}.pdf`, convert `pymupdf4llm.to_markdown(pdf)` → `data/raw/nea_docs/{category}/{slug}.md`, upsert `silver.nea_document` key `("key",)`. No table parsing here (Phase 2 reads the Markdown to target tables).

- [ ] **Step 1: Failing test** `test_parse_doc_listing` — fixture yields ≥1 item, all `detail_url` https and unique.
- [ ] **Step 2–4:** FAIL → implement → PASS.
- [ ] **Step 5: Live:** `uv run nea ingest docs`; open one annual-report `.md` and note in `docs/data-sources.md` which tables hold monthly/annual peak demand & energy (page/heading) — input for Phase 2.
- [ ] **Step 6: Commit** `feat: archive NEA monthly/yearly/annual reports as pdf+markdown`.

### Task 8: Open-Meteo weather + GloFAS river discharge

**Files:** Create `src/nea_forecast/open_meteo.py`, `tests/test_open_meteo.py`, `tests/fixtures/om_archive.json`, `tests/fixtures/om_flood.json` (small, handmade, last day null)

**Interfaces:**
- Produces: `parse_daily(js: dict, point: str, mapping: dict[str, str]) -> list[dict]` (drops rows where all mapped values are null); `start_date(con, table: str, point: str, default: date) -> date` = `max(date) − 10 days` or default; `ingest_weather(con)`, `ingest_discharge(con)` registered `INGESTERS["weather"]`, `INGESTERS["discharge"]`. Default start 2010-01-01; end = today. Weather URL: `https://archive-api.open-meteo.com/v1/archive?latitude=..&longitude=..&start_date=..&end_date=..&daily=temperature_2m_max,temperature_2m_min,precipitation_sum&timezone=Asia/Kathmandu`. Flood URL: `https://flood-api.open-meteo.com/v1/flood?latitude=..&longitude=..&daily=river_discharge&start_date=..&end_date=..`. Raw JSON saved `data/raw/open_meteo/{kind}/{point}_{start}_{end}.json`.

- [ ] **Step 1: Failing tests:**
```python
def test_parse_daily_skips_null_tail():
    rows = parse_daily(json.loads((FIX/"om_archive.json").read_text()), "ktm",
                       {"temperature_2m_max": "tmax_c", "temperature_2m_min": "tmin_c", "precipitation_sum": "precip_mm"})
    assert rows[-1]["date"] < date.fromisoformat(js["daily"]["time"][-1]) and all(r["tmax_c"] is not None for r in rows)
def test_start_date_overlap(tmp_path):
    con = connect(tmp_path); upsert(con, "silver.weather_daily", [{"date": date(2025,1,20), "point":"ktm", "tmax_c":1.0,"tmin_c":0.0,"precip_mm":0.0}], ("date","point"))
    assert start_date(con, "silver.weather_daily", "ktm", date(2010,1,1)) == date(2025,1,10)
```
- [ ] **Step 2–4:** FAIL → implement → PASS.
- [ ] **Step 5: Live:** `uv run nea ingest weather discharge`; `nea status` shows 6 weather points and 8 discharge points from 2010. Spot-check: discharge at each point has a clear monsoon peak (Jul–Sep) ≫ winter (Jan–Mar); a point without that pattern is off-river → flag in `sources.json`.
- [ ] **Step 6: Commit** `feat: ingest ERA5 weather and GloFAS discharge`.

### Task 9: DHM river-watch gauge snapshots

**Files:** Create `src/nea_forecast/dhm.py`, `tests/test_dhm.py`, `tests/fixtures/dhm_river_watch.html` (handmade snippet with `var coordinates = [ {2 stations} ];`)

**Interfaces:**
- Produces: `parse_river_watch(html: str) -> list[dict]` → `silver.river_level_obs` columns (regex `var\s+coordinates\s*=\s*(\[.*?\])\s*;` with DOTALL, `json.loads`, skip stations with null `waterLevel`); `ingest_dhm(con)` registered `INGESTERS["dhm"]`, upsert key `("station_id", "observed_at")`, raw HTML saved `data/raw/dhm/{utc_ts}.html`.

- [ ] **Step 1: Failing tests:** `test_parse_river_watch` → 2 rows, `level_m` float, `observed_at` datetime; `test_null_level_skipped` → station with `waterLevel: null` dropped.
- [ ] **Step 2–4:** FAIL → implement → PASS.
- [ ] **Step 5: Live (from Nepal):** `uv run nea ingest dhm` → ~300 rows; re-run immediately → row count unchanged. If page structure differs, update fixture from live page and record in decisions.md.
- [ ] **Step 6: Commit** `feat: snapshot DHM river-watch gauge levels`.

### Task 10: Calendar dimension + gold views + full run

**Files:** Create `src/nea_forecast/calendar.py`, `tests/test_calendar.py`; Modify `schema.sql`, `cli.py`, docs.

**Interfaces:**
- Produces:
  - `build_calendar(start: date, end: date) -> list[dict]` → `silver.dim_calendar(date, bs_year, bs_month, bs_day, bs_date VARCHAR, dow, is_saturday, is_holiday, holiday_name, season, fiscal_year)`; `season` = `winter` for AD months Nov–Apr else `summer` (ADR: matches dry/wet hydrology); `fiscal_year` like `"2081/82"`, starting BS Shrawan 1 (month 4). Uses `nepali_datetime.date.from_datetime_date` and `holidays.country_holidays("NP", years=...)`. Registered `INGESTERS["calendar"]` (rebuilds 2010-01-01 → today+400 d, upsert key `("date",)`).
  - Gold views in `schema.sql`: `gold.daily_features` = `nea_daily` ⟕ `dim_calendar` ⟕ pivot of `weather_daily` (`tmin_ktm`, `tmax_ktm`, `tmean_terai` = mean of Terai points) ⟕ `discharge_index` (sum of `discharge_m3s` over all points per day), keyed by `date`, over the full calendar range (NEA columns null where missing); `gold.monthly_summary` = per BS-year/month sums of energy, max peak, sum `net_exchange_india_mwh`, winter flag.

- [ ] **Step 1: Failing tests:**
```python
def test_calendar_known_dates():
    rows = {r["date"]: r for r in build_calendar(date(2025,1,1), date(2025,1,31))}
    assert rows[date(2025,1,11)]["bs_date"] == "2081-09-27"
    assert rows[date(2025,1,11)]["is_saturday"] is True and rows[date(2025,1,11)]["season"] == "winter"
    assert rows[date(2025,1,11)]["fiscal_year"] == "2081/82"
def test_dashain_flagged():
    rows = build_calendar(date(2024,10,1), date(2024,10,31))
    assert any(r["is_holiday"] and "Dashain" in (r["holiday_name"] or "") for r in rows)
def test_gold_view_joins(tmp_path):
    con = connect(tmp_path); upsert(con, "silver.dim_calendar", build_calendar(date(2025,1,11), date(2025,1,11)), ("date",))
    assert con.sql("select bs_date from gold.daily_features where date='2025-01-11'").fetchone()[0] == "2081-09-27"
```
(Check `holidays` NP names; adjust the `"Dashain"` substring to the library's actual label, e.g. "Bijaya Dashami".)
- [ ] **Step 2–4:** FAIL → implement → PASS.
- [ ] **Step 5: Full verification:** `uv run pytest -v` all green; `uv run nea ingest all` then re-run (second run fast, no new rows except DHM snapshot + Open-Meteo overlap); `uv run nea status`; in `uv run python -c "from nea_forecast.lake import connect; print(connect(read_only=True).sql('select season, avg(peak_demand_mw), avg(net_exchange_india_mwh) from gold.daily_features where peak_demand_mw is not null group by 1'))"` → winter shows higher import than summer. `uv run nea maintain` succeeds.
- [ ] **Step 6:** Update `docs/flow.md` (final commands), `docs/data-sources.md` (statuses), `decisions.md` change log; mark Phase 1 done in `docs/blueprint.md`.
- [ ] **Step 7: Commit** `feat: calendar dimension, gold feature views; phase 1 complete`.

---

## After Phase 1 (separate plans, written once data exists)

- **Phase 2 — Doc parsing + EDA:** parse monthly/yearly/annual report tables (from Task 7 Markdown) into `silver.nea_monthly`; EDA script (`analysis/01_eda.py`): seasonality, winter vs summer demand/import, temperature & holiday effects, discharge ↔ domestic generation lag, data gaps.
- **Phase 3 — Models:** per blueprint Model strategy; outputs to `ml.forecasts(run_id, model, target, horizon_days, date, yhat, yhat_lo, yhat_hi, created_at)` and `ml.backtest_metrics`.
- **Phase 4 — Site:** `nea export` → `COPY` gold + ml tables to `site/data/*.parquet`; static Cloudflare Pages site reading Parquet via DuckDB-WASM (or pre-baked JSON if simpler).

## Verification (end of Phase 1)

1. `uv run pytest -v` → all pass offline.
2. `uv run nea ingest all` twice → second run adds no duplicate NDOR/doc/weather rows.
3. `uv run nea status` → `nea_daily` 2023-04-14..2025-01-11 (+ Wayback days), weather/discharge 2010..today−5d, DHM ≈300 stations/snapshot, calendar 2010..+400 d.
4. Query `gold.daily_features` from a fresh `duckdb` shell: `ATTACH 'ducklake:data/lake/nea.ducklake' AS lake (READ_ONLY); FROM lake.gold.daily_features LIMIT 5;`
5. Docs present: README credits, blueprint, flow, data-sources, decisions (ADR + change log), this plan under `docs/plans/`.
