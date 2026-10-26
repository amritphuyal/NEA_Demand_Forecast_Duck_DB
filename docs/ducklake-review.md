# How I use DuckDB and DuckLake in this repo

This is a review of how my NEA demand forecast project stores and queries its data. Every number below comes from a command I ran on 2026-10-26 or from a file in this repo. The command sits next to the result. Anything marked **Suggestion** is my opinion about what to change. It is not something the repo does today.

**Versions.** `uv.lock` pins `duckdb` 2.0.0. DuckLake is not in `uv.lock`, because it is a DuckDB extension installed at runtime. I read the versions from the running system:

```sql
SELECT extension_name, extension_version FROM duckdb_extensions()
WHERE extension_name IN ('ducklake', 'sqlite_scanner', 'excel')
-- ducklake 417a9117f5, sqlite_scanner e223dc0149, excel 81bb84b115 (all from 'core')

FROM __ducklake_metadata_lake.ducklake_metadata
-- version 1.1, data_path data/lake/data/, encrypted false
```

The catalog uses DuckLake format **1.1**. I checked every DuckLake feature below against the "1.1 stable" docs on ducklake.select (fetched 2026-10-26).

## 1. The catalog and where the data lives

`src/nea_forecast/lake.py` opens one in-memory DuckDB and attaches the lake:

```python
con.execute("INSTALL ducklake; LOAD ducklake; INSTALL sqlite")
opts = "READ_ONLY" if read_only else f"DATA_PATH '{lake_dir / 'data'}/'"
con.execute(f"ATTACH 'ducklake:sqlite:{lake_dir / 'nea.sqlite'}' AS lake ({opts})")
con.execute("USE lake")
```

- **Catalog (metadata):** `data/lake/nea.sqlite`, a SQLite file.
- **Data:** Parquet files under `data/lake/data/`.
- Writers attach with `DATA_PATH`. Readers (`nea eda`, `nea findings`, `nea export`, `nea sql`) attach with `READ_ONLY`.

**Why SQLite and not a DuckDB file.** I started with a DuckDB-file catalog. Its file lock blocked even read-only access while an ingest was running, so `nea status` and ad-hoc queries failed during a backfill (ADR-004 and the 2026-10-25 change log entry in `docs/developer/decisions.md`). The DuckLake 1.1 docs say the same thing: a DuckDB catalog file can be attached by "only one process ... at a time unless every process attaches it with READ_ONLY". For SQLite they say "SQLite allows only one writer at a time" and "DuckLake retries lock conflicts when using a SQLite catalog". They recommend SQLite for "local data warehousing using multiple local clients". That is my case.

**Catalog size before and after.** The change log says "14 MB → <1 MB after copy, old one had piled-up snapshot files". What I measure today:

| What | Command | Result |
|---|---|---|
| Old DuckDB catalog file | `ls -la data/lake/backup-duckdb-catalog/` | `nea.ducklake` 12,070,912 bytes |
| Old catalog folder, with its Parquet | `du -sb data/lake/backup-duckdb-catalog` | 13,407,545 bytes |
| Current SQLite catalog | `ls -la data/lake/` | `nea.sqlite` 471,040 bytes |

The "14 MB" in the change log is a rounded figure for the whole backup folder (13.4 MB). The SQLite catalog is still under 1 MB after a day and a half of writes, and it now also holds inlined rows (section 7).

## 2. Layers: bronze, silver, gold, ml

`schema.sql` creates four schemas. Every `connect()` that can write runs the whole file. All statements use `IF NOT EXISTS`, so a connect does not write a new snapshot.

```sql
SELECT table_schema, table_type, count(*), string_agg(table_name, ', ' ORDER BY table_name)
FROM information_schema.tables WHERE table_catalog = 'lake' GROUP BY ALL ORDER BY ALL
```

| Schema | Kind | Count | Objects |
|---|---|---|---|
| bronze | table | 1 | `ingest_log` |
| silver | table | 15 | `dim_calendar`, `iex_cross_border_monthly`, `india_trade_monthly`, `macro_yearly`, `nea_daily`, `nea_document`, `nea_widget`, `plant_outage`, `report_annual`, `report_energy_history`, `report_monthly`, `river_discharge_daily`, `river_discharge_forecast`, `river_level_obs`, `weather_daily` |
| gold | **view** | 4 | `annual_history`, `daily_features`, `monthly_summary`, `report_monthly_balance` |
| ml | table | 2 | `backtest_metrics`, `forecasts` |

- **bronze** is the log of what ran: one row per source and key, with status `ok`, `not_found`, `parse_error` or `fetch_error`. The raw files themselves sit outside the lake in `data/raw/<source>/` and are never overwritten (ADR-005). That means I can rebuild silver from disk without scraping again.
- **silver** holds clean source tables. Each one is written by one ingester through `upsert`.
- **gold** is all views, no stored data. A view always reflects the current silver tables, so there is nothing to refresh. The cost is that the view SQL runs on every read. At this size that is not a problem.
- **ml** holds model output: backtest metrics and forecasts. `run_id` tells backtest runs (`bt-*`) from live runs (`live-YYYYmmdd`).

To change a gold view I have to `DROP VIEW` first, because `CREATE VIEW IF NOT EXISTS` will not replace it (comment in `schema.sql`).

## 3. The upsert pattern

DuckLake 1.1 docs: "The only constraint type that is currently supported is NOT NULL. It does not support PRIMARY KEY, FOREIGN KEY, UNIQUE or CHECK constraints." So there is no `INSERT ... ON CONFLICT` to lean on. `lake.upsert` does it by hand:

```python
rows = list({tuple(r[k] for k in key): r for r in rows}.values())   # last wins within the batch
con.execute(f"CREATE OR REPLACE TEMP TABLE _stage AS SELECT {col_list} FROM {table} LIMIT 0")
con.executemany(f"INSERT INTO _stage VALUES (...)", rows)
con.execute("BEGIN")
con.execute(f"DELETE FROM {table} t WHERE EXISTS (SELECT 1 FROM _stage s WHERE {match})")
con.execute(f"INSERT INTO {table} ({col_list}) SELECT {col_list} FROM _stage")
con.execute("COMMIT")   # ROLLBACK and re-raise on any error
```

Three details matter:

1. **Dedupe in Python first.** Two rows with the same key in one batch would both be inserted, since nothing in the table stops it.
2. **Stage in a TEMP table, outside the transaction.** A TEMP table lives in the in-memory DuckDB, not in the lake. DuckDB lets one transaction write to only one attached catalog. If I filled the TEMP table inside `BEGIN ... COMMIT`, the transaction would touch two catalogs and fail. The comment in `lake.py` and the change log both record this.
3. **Delete and insert in one transaction.** A reader sees either the old rows or the new rows, never a gap. One commit is one DuckLake snapshot.

The key is a convention in code, for example `("source", "key")` for `ingest_log`. Nothing in the catalog enforces it. A bug in one ingester could still write duplicates. `tests/test_lake.py` has `test_upsert_idempotent_and_replaces` and `test_upsert_dedupes_within_batch` for the helper itself.

**A bug the snapshots showed.** `outages.py` ran `DELETE FROM silver.plant_outage` as its own commit and then called `upsert`. Snapshot 405 (`inlined_delete`) and snapshot 406 (`inlined_insert`) are those two commits, so a reader in between saw an empty table. I fixed it with `upsert(..., replace_all=True)`, which deletes every row inside the same transaction as the insert. `test_upsert_replace_all_is_one_snapshot` checks that a full replace adds exactly one snapshot. No other ingester runs its own `DELETE` (`grep -rn -i delete src/nea_forecast/*.py`).

`bronze.ingest_log` gets `ok` only after the silver write commits (`docs/architecture.md`, section 3). A crash mid-run leaves the key unlogged, so the next run fetches it again.

## 4. Concurrency

What was tested:

- The change log (2026-10-25, SQLite move) says: "Tested: reader sees committed data during an open write transaction; writers serialize." That was a manual test at the time. It is now in the test suite (below).
- `test_reader_works_while_writer_connected` in `tests/test_lake.py` checks that a `read_only=True` reader can attach while a writer is attached. It does not hold a write transaction open.
- So I added `test_reader_sees_committed_data_during_open_write`. The writer commits row `a`, runs `BEGIN`, inserts row `b`, and a second connection reads. The reader sees only `a`, without waiting. After `COMMIT` it sees both.

```
$ uv run pytest -q
110 passed in 90.15s (0:01:30)
```

Limits:

- **One writer at a time.** SQLite allows one writer. DuckLake retries lock conflicts, so two writers wait for each other instead of failing straight away. They do not run in parallel. ADR-004: "writers serialize, readers never block."
- **All on one laptop.** The catalog is a local file and the data path is a local folder. No other machine can write to this lake.
- `nea status` used to call `connect()` without `read_only`, so it attached as a writer. It now uses `connect(read_only=True)`, like `eda`, `export` and `sql`.

## 5. Snapshots and time travel

Every commit is a snapshot. Live numbers:

```sql
SELECT count(*), min(snapshot_id), max(snapshot_id), min(snapshot_time), max(snapshot_time)
FROM ducklake_snapshots('lake')
-- 412 snapshots, id 0 to 411
-- first: 0   2026-10-25 22:07:11 +05:45   {schemas_created: [main]}
-- last:  411 2026-10-26 17:31:53 +05:45   {tables_inserted_into: [26], tables_deleted_from: [26]}

SELECT snapshot_time::DATE, count(*) FROM ducklake_snapshots('lake') GROUP BY 1
-- 2026-10-25: 259, 2026-10-26: 153
```

Snapshot 0 is the moment I created the SQLite catalog. Earlier history stayed in the old DuckDB catalog. Snapshot 411 is an upsert (a delete and an insert on table id 26 in one commit), which is what section 3 predicts.

**Few snapshots per write.** The change log (2026-10-25, "Speed fix") says the NDOR backfill used to make 2 lake commits per PDF, about 1,000 snapshots. Now each browser round does one `nea_daily` upsert and one `log_many`. `log_many` exists only to batch log rows into one commit: "One commit for the lot: each commit is a lake snapshot" (`lake.py`).

**Time travel.** The syntax in `docs/lake.md` matches the DuckLake 1.1 docs. I ran all three forms today:

```sql
SELECT (SELECT count(*) FROM silver.weather_daily),
       (SELECT count(*) FROM silver.weather_daily AT (VERSION => 200))
-- 36858, 36852

SELECT count(*) FROM silver.weather_daily AT (TIMESTAMP => now() - INTERVAL '12 hours')
-- 36852

ATTACH 'ducklake:sqlite:data/lake/nea.sqlite' AS lake_then (READ_ONLY, SNAPSHOT_VERSION 200)
SELECT count(*) FROM lake_then.silver.weather_daily
-- 36852
```

History starts at snapshot 0. `AT (TIMESTAMP => now() - INTERVAL '1 day')` fails with `No snapshot found at timestamp 2026-10-25 13:58:26.709069+00`, because that is before I created the SQLite catalog. Anything older is only in the backup DuckDB catalog.

The pipeline code never reads an old version. Time travel is something I can do by hand. The forecast and backtest tables keep their own history through `run_id`.

**Maintenance.** `nea maintain` in `cli.py`:

```python
con.execute("CALL ducklake_merge_adjacent_files('lake')")
con.execute("CALL ducklake_expire_snapshots('lake', older_than => now() - INTERVAL 30 DAY)")
con.execute("CALL ducklake_cleanup_old_files('lake', cleanup_all => true)")
```

1. Merge small Parquet files from small commits into bigger ones.
2. Expire snapshots older than 30 days. Time travel back further than 30 days stops working after this.
3. Delete the files that expired snapshots and merges left behind.

All three functions and their parameters match the 1.1 docs. The docs also note that a `CHECKPOINT` runs, in order, `ducklake_flush_inlined_data`, `ducklake_expire_snapshots`, `ducklake_merge_adjacent_files`, `ducklake_rewrite_data_files`, `ducklake_cleanup_old_files` and `ducklake_delete_orphaned_files`. My routine is a subset of that.

**Has it run?** `docs/architecture.md` and `docs/flow.md` describe a Sunday 04:00 cron for `nea maintain`. The crontab on my laptop does not have it:

```
$ crontab -l | grep nea
0 15 * * * cronitor exec nea-daily-deploy "cd ~/All_Repo/NEA_Demand_Forecast_Duck_DB && uv run nea ingest all && uv run nea forecast && cd site && npm run deploy" >> ~/nea-deploy.log 2>&1

$ ls data/logs | grep maintain
20261025-225544-maintain.log
```

So `nea maintain` had run once, on 2026-10-25 at 22:55. The docs described a 3-hourly ingest and a Sunday maintain that were never installed. What I changed:

- `nea maintain` now runs `CALL ducklake_flush_inlined_data('lake')` first (section 7). On a copy of the lake it took the Parquet count from 123 to 117, left 0 files scheduled for deletion, kept every row count, and gave `nea_widget`, `plant_outage` and `iex_cross_border_monthly` one Parquet file each.
- `docs/architecture.md` (and the site copy) and `docs/flow.md` now show the real daily 15:00 chain: `nea ingest all && nea forecast && npm run deploy`.
- `docs/deploy.md` lists a Sunday 17:00 `nea maintain` line. It still has to be added to the crontab with `crontab -e`.

## 6. The website reads a Parquet export, not the lake

The site is static files on Cloudflare Pages. `nea export` (`src/nea_forecast/export.py`) attaches the lake `READ_ONLY` and runs one `COPY` per table:

```python
con.execute(f"COPY ({sql}) TO '{path}' (FORMAT parquet, COMPRESSION zstd)")
```

The `ml` tables are filtered on the way out: only the latest backtest run plus all live runs. Older backtests stay in the lake.

In the browser, `site/src/components/db.js` loads DuckDB-WASM 1.32.0 (engine v1.4.3, upgraded from 1.29.0 after this review) from jsDelivr, registers each Parquet file and creates a view per table (`CREATE VIEW daily_features AS SELECT * FROM 'daily_features.parquet'`). Every chart is a SQL query against those views.

Why not attach the lake from the browser? ADR-009 says: "Cloudflare Pages is static. DuckDB-WASM can't attach a DuckLake catalog reliably." I found no DuckLake doc page on this, so I tested it in headless Chrome with Playwright:

| DuckDB-WASM | Engine | `LOAD ducklake` | `ATTACH 'ducklake:sqlite:nea.sqlite'` |
|---|---|---|---|
| 1.29.0 (what the site pinned) | v1.1.1 | `IO Error: Extension .../v1.1.1/wasm_eh/ducklake.duckdb_extension.wasm is not available` | not reached |
| 1.32.0 (latest stable on npm, 2025-12-16) | v1.4.3 | loaded | `Unable to open database "nea.sqlite": unable to open database file`, with the catalog registered via `registerFileBuffer` |

So with a SQLite catalog the claim holds today. I did not test other catalog types in the browser. Even if attach worked, the browser would fetch the catalog plus every data file, including files kept only for time travel. The export is one flat file per table. Two more reasons in the repo:

- The DuckDB-WASM `.wasm` files are 35 to 40 MB, above Cloudflare's 25 MiB per-file limit. That is why the site loads DuckDB-WASM from jsDelivr and does not self-host it (`db.js` comment, change log 2026-10-26).
- The site stays a read-only snapshot. Refresh means export, build, deploy.

Export size:

```
$ python3 -c "import json;m=json.load(open('site/src/data/manifest.json'));t=m['tables'];print(m['exported_at'],len(t),sum(v['bytes'] for v in t.values()))"
2026-10-26T19:09:14 20 797045
```

20 Parquet tables (19 from the lake plus `points`, built from `sources.json` and `outages.json`), 797,045 bytes in total, about 0.8 MB. `site/src/data/` also holds `manifest.json` and `selection.json`, 22 files in all (`ls site/src/data | wc -l`). The largest files are `weather_daily` (197,945 bytes), `daily_features` (194,779) and `river_discharge_daily` (192,313).

## 7. Other DuckDB features I use

**Extensions.**

- `ducklake`, for the lake itself.
- `sqlite` (it shows up as `sqlite_scanner`). I do not query SQLite directly. It is the catalog backend that `ducklake:sqlite:` needs.
- `excel`, in `cerc.py`. The CERC market reports are `.xlsx` files. I read them with `read_xlsx` instead of adding openpyxl:

  ```sql
  SELECT * FROM read_xlsx(?, sheet=?, header=false, all_varchar=true, range='A1:L80')
  ```

  The explicit `range` is there because merged title rows otherwise hide the other columns (comment in `cerc.py`).

**Data inlining, which I did not set up on purpose.** The DuckLake 1.1 docs say "Data inlining is enabled by default with a row limit of 10". Small inserts are stored as rows in the catalog instead of as new Parquet files. My catalog has 18 inlined-data tables (`FROM __ducklake_metadata_lake.ducklake_inlined_data_tables`), and these tables have rows in them that are still live:

| Table | Inlined live rows |
|---|---|
| `ingest_log` | 69 |
| `iex_cross_border_monthly` | 69 |
| `river_discharge_daily` | 32 |
| `report_energy_history` | 30 |
| `weather_daily` | 24 |
| `report_annual` | 20 |
| `plant_outage` | 10 |
| `report_monthly` | 9 |
| `nea_widget` | 1 |

(Counted with `SELECT count(*) FROM __ducklake_metadata_lake.<inlined table> WHERE _ducklake_end_snapshot IS NULL` for each table.) `nea_widget`, `plant_outage` and `iex_cross_border_monthly` have no Parquet file at all. All of their rows live in `nea.sqlite`. Inlined rows only move to Parquet when `ducklake_flush_inlined_data` or `CHECKPOINT` runs, so `nea maintain` now flushes first (section 5).

**SQL I lean on.** From `schema.sql`, `eda.py`, `model.py`, `export.py` and `queries/`:

- `FILTER (...)` on aggregates to pivot long data into columns. `gold.daily_features` turns `weather_daily` and `river_discharge_daily` (one row per date and point) into one row per date, for example `max(tmin_c) FILTER (point = 'kathmandu') AS tmin_ktm`, and `discharge_index` as the sum of three basins.
- `SELECT c.*, n.* EXCLUDE (date, bs_date, source, source_url), ...` with `USING (date)` joins, so the wide feature view stays short.
- `QUALIFY row_number() OVER (...) = 1` to keep the newest report per year (`gold.annual_history`) and to prefer OCR over text (`gold.report_monthly_balance`).
- A named `WINDOW w AS (PARTITION BY m.fy, m.unit)` with `QUALIFY` to drop a whole fiscal year when its total disagrees with the annual history.
- `GROUP BY ALL`, `FROM`-first queries, `bool_or`, `any_value`.
- `corr`, `regr_slope` and `regr_r2` in `eda.py` for temperature effects and GDP elasticity.
- `lag(value) OVER (ORDER BY year)` in `model.py` for GDP growth.
- `unnest(?, recursive := true)` in `export.py` to turn a Python list of dicts into a table in one statement.

## 8. DuckDB 2.0 problems and workarounds

**`Relation.fetchone()` is gone.** The change log (2026-10-25, Lakehouse) records it, and I confirmed it today:

```
>>> con.sql("SELECT 1").fetchone()
AttributeError: Relations no longer have fetchone(): a relation keeps no result between calls, so every call runs it again. Use rel.limit(1).fetchall() instead.
```

The repo uses `con.execute(...).fetchone()` everywhere instead. `con.execute` returns a cursor with a result, so `fetchone` still works there.

**Self-join internal error.** The change log (2026-10-25, Phase 2 Tasks 2 and 3) says a SQL self-join on `gold.daily_features` for the lag scan hit `INTERNAL Error: dict-surviving cache`. The workaround is in `eda.py`: `_lag_curve` pulls two date-keyed dicts and computes `statistics.correlation` in Python. `reconcile` merges the four import series in Python for the same reason.

I tried to reproduce it today with a self-join of my own (`range(0, 31)` lags joined to `gold.daily_features` on `x.date = y.date - k`). It ran without error on duckdb 2.0.0. The original failing query was never committed (`git log -S "dict-surviving"` finds only the commit that added the Python version), so I cannot say whether the bug is fixed or whether my query has a different shape. The Python workaround stays.

## 9. Live numbers

All of these were run on 2026-10-26.

**`uv run nea status`**

```
bronze.ingest_log 749
ml.backtest_metrics 3832
ml.forecasts 6558 2024-06-01 2027-04-01
silver.dim_calendar 6543 2010-01-01 2027-11-30
silver.iex_cross_border_monthly 69
silver.india_trade_monthly 454
silver.macro_yearly 132
silver.nea_daily 612 2023-04-14 2025-01-11
silver.nea_document 32
silver.nea_widget 1
silver.plant_outage 10
silver.report_annual 20
silver.report_energy_history 30
silver.report_monthly 4212
silver.river_discharge_daily 49144 2010-01-01 2026-10-26
silver.river_discharge_forecast 1528 2026-10-26 2027-05-04
silver.river_level_obs 0
silver.weather_daily 36858 2010-01-01 2026-10-26
  log cerc ok 39
  log nea_docs_annual not_found 2
  log nea_docs_annual ok 29
  log nea_docs_monthly not_found 8
  log nea_docs_monthly ok 2
  log nea_docs_yearly ok 1
  log nea_ndor not_found 6
  log nea_ndor ok 633
  log ocr ok 29
```

`river_level_obs` is empty because the DHM site is down (`docs/lake.md`).

**Snapshots** (`FROM ducklake_snapshots('lake')`): 412, ids 0 to 411, first 2026-10-25 22:07:11 +05:45, last 2026-10-26 17:31:53 +05:45.

**Rows per layer** (exact `count(*)` per base table, summed by schema):

| Layer | Tables | Rows |
|---|---|---|
| bronze | 1 | 749 |
| silver | 15 | 99,645 |
| ml | 2 | 10,390 |
| gold | 4 views | none stored |
| **total** | 18 | **110,784** |

**Parquet files under `data/lake/data/`**

```
$ find data/lake/data -type f -name '*.parquet' | wc -l
123
$ find data/lake/data -type f -name '*.parquet' -printf '%s\n' | awk '{s+=$1} END {print s}'
1783671
```

123 files, 1,783,671 bytes (1.8 MB). The catalog explains all 123:

| Kind | Query on `__ducklake_metadata_lake` | Files | Bytes |
|---|---|---|---|
| Live data files | `ducklake_data_file WHERE end_snapshot IS NULL` | 56 | 1,186,420 |
| Live delete files | `ducklake_delete_file WHERE end_snapshot IS NULL` | 7 | 124,377 |
| Old data files kept for time travel | `ducklake_data_file WHERE end_snapshot IS NOT NULL` | 38 | 344,807 |
| Scheduled for deletion | `ducklake_files_scheduled_for_deletion` | 22 | |

56 + 7 + 38 + 22 = 123. The live data files are small: min 713 bytes, median 3,335 bytes, max 231,401 bytes. The biggest table on disk is `river_discharge_daily`, 10 files and 430,683 bytes.

**Catalog file:** `data/lake/nea.sqlite`, 471,040 bytes (`ls -la data/lake/`).

## 10. What I would change next

**Done since the first draft of this review:** flush inlined rows in `nea maintain`, schedule docs that match the real crontab plus a Sunday maintain line to install, `nea status` as a reader, the open-transaction concurrency test, the `outages.py` one-commit fix (sections 3 to 5), and the DuckDB-WASM upgrade (below).

The rest are **suggestions**. None of them is in the repo.

**Suggestion: install the maintain cron line, then consider `CHECKPOINT`.** Worth it, and cheap. Maintain has run once. Since then 154 snapshots have piled up (`... WHERE snapshot_time > '2026-10-25 22:55:44+05:45'`), and 22 files wait for deletion. At 1.8 MB nothing hurts yet, but every daily ingest adds files. Later I could swap the four calls for a single `CHECKPOINT`, which in DuckLake 1.1 also rewrites files with many deletes and removes orphaned files. If I switch, I need to set `expire_older_than` to 30 days with `set_option` so the time-travel window stays the same.

**Done: DuckDB-WASM 1.29.0 → 1.32.0.** 1.29.0 (engine v1.1.1) dates from 2024-10-07. 1.32.0 (engine v1.4.3) is the latest stable on npm. It does not make attaching the lake possible (section 6), but it brings the browser engine closer to the 2.0.0 the lake uses. After the upgrade I loaded all 9 pages in headless Chrome and found no console errors and no query errors. `SELECT version()` in the SQL explorer returns `v1.4.3`, and `weather_daily` has 36,858 rows, the same as the lake.

**Suggestion: a Postgres catalog if there are ever concurrent writers.** Not worth it at this size. There is one writer, a cron job on one laptop. The DuckLake docs recommend Postgres for "a multi-user lakehouse with potentially remote clients". I have neither. It would add a server to run and back up for no gain. I would revisit it only if a second machine needed to write, for example a cloud job that fetches sources that are reachable from outside Nepal.

**Suggestion: partition the large silver tables.** Not worth it. The largest table, `river_discharge_daily`, has 49,144 rows in 10 files totalling 430,683 bytes. Partitioning by `year(date)` would split it into more, smaller files. That is the opposite of what a lake with a 3 KB median file size needs. The docs also say partitioning "only affect[s] new data written to the table", so older files would keep their layout until rewritten. I would think about it at tens of millions of rows.

**Data inlining for the small, frequent widget writes.** Nothing to do. Inlining is on by default with a 10-row limit, and each widget snapshot is one row, so it lands in the catalog, not in a new tiny Parquet file. The missing flush is now part of `nea maintain`.

## Sources

- DuckLake 1.1 docs: [Choosing a catalog database](https://ducklake.select/docs/stable/duckdb/usage/choosing_a_catalog_database), [Data inlining](https://ducklake.select/docs/stable/duckdb/advanced_features/data_inlining), [Constraints](https://ducklake.select/docs/stable/duckdb/advanced_features/constraints), [Partitioning](https://ducklake.select/docs/stable/duckdb/advanced_features/partitioning), [Time travel](https://ducklake.select/docs/stable/duckdb/usage/time_travel), [Recommended maintenance](https://ducklake.select/docs/stable/duckdb/maintenance/recommended_maintenance), [CHECKPOINT](https://ducklake.select/docs/stable/duckdb/maintenance/checkpoint), [Cleanup of files](https://ducklake.select/docs/stable/duckdb/maintenance/cleanup_of_files).
- Repo: `src/nea_forecast/lake.py`, `schema.sql`, `cli.py`, `export.py`, `eda.py`, `cerc.py`, `site/src/components/db.js`, `tests/test_lake.py`, `docs/lake.md`, `docs/architecture.md`, `docs/flow.md`, `docs/developer/decisions.md` (ADR-004, ADR-005, ADR-009 and change log).
