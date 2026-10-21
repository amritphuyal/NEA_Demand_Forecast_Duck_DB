# Data Flow

```
nea ingest <source>|all
  └─ per source: discover → skip keys in bronze.ingest_log → fetch → save raw → parse → upsert silver → log ok
nea status     row counts + date ranges
nea maintain   merge small Parquet files, expire old snapshots
```

## Per-source rules

| Source (`nea ingest …`) | Discover | Incremental rule | Raw file | Silver table (key) |
|---|---|---|---|---|
| `ndor` | transd listing `?page=1..N` → detail page → PDF link | stop at first listing page with zero unseen slugs | `data/raw/nea_ndor/{slug}.pdf` | `nea_daily` (`date`) |
| `docs` | monthly / yearly / annual listings → detail → PDFs | listing minus logged keys | `data/raw/nea_docs/{category}/{slug}.pdf` + `.md` | `nea_document` (`key`) |
| `weather` | Open-Meteo archive per point | from `max(date) − 10 d` (ERA5 lag), else 2010-01-01 | `data/raw/open_meteo/weather/…json` | `weather_daily` (`date, point`) |
| `discharge` | Open-Meteo flood per point | same as weather | `data/raw/open_meteo/discharge/…json` | `river_discharge_daily` (`date, point`) |
| `dhm` | DHM river-watch page | append snapshot | `data/raw/dhm/{utc_ts}.html` | `river_level_obs` (`station_id, observed_at`) |
| `calendar` | generated | rebuild 2010 → today + 400 d | — | `dim_calendar` (`date`) |

Rules that hold everywhere:
- A key is logged `ok` only after its silver upsert commits → crash mid-run = retry next run.
- `parse_error` / `fetch_error` keys are retried next run; `not_found` keys are not.
- Upsert = delete matching keys + insert, in one transaction (DuckLake has no primary keys).
- Raw files are never overwritten; silver can be rebuilt from them.

## Schedule (laptop in Nepal)

NEA fetches use headless real Chrome (automation flags masked). If F5 starts blocking, set `NEA_HEADED=1` (needs `DISPLAY` of the logged-in session).

```cron
0 */3 * * * cd /path/to/repo && uv run nea ingest all >> data/ingest.log 2>&1
30 6 * * * cd /path/to/repo && uv run nea forecast >> data/ingest.log 2>&1   # daily: winter outlook (+ daily once the widget has 8 days)
# re-run `nea model` (backtest + selection) after each winter, or when models change
0 4 * * 0   cd /path/to/repo && uv run nea maintain   >> data/ingest.log 2>&1
```
