"""Lake -> Parquet snapshot for the website (site/src/data). The site reads only these files, so the lake stays
the single source of truth: re-export, rebuild, redeploy."""
import json
import time
from datetime import datetime
from pathlib import Path

from nea_forecast import load_sources
from nea_forecast.outages import OUTAGES_JSON

OUT = Path("site/src/data")
# name on the site -> SQL. ml tables: latest backtest run + all live runs (older backtests stay in the lake)
TABLES = {
    "daily_features": "FROM gold.daily_features",
    "monthly_summary": "FROM gold.monthly_summary",
    "annual_history": "FROM gold.annual_history",
    "report_monthly_balance": "FROM gold.report_monthly_balance",
    "nea_daily": "FROM silver.nea_daily",
    "nea_widget": "FROM silver.nea_widget",
    "weather_daily": "FROM silver.weather_daily",
    "river_discharge_daily": "FROM silver.river_discharge_daily",
    "river_discharge_forecast": "FROM silver.river_discharge_forecast",
    "plant_outage": "FROM silver.plant_outage",
    "india_trade_monthly": "FROM silver.india_trade_monthly",
    "iex_cross_border_monthly": "FROM silver.iex_cross_border_monthly",
    "macro_yearly": "FROM silver.macro_yearly",
    "report_monthly": "FROM silver.report_monthly",
    "report_annual": "FROM silver.report_annual",
    "dim_calendar": "FROM silver.dim_calendar",
    "ingest_log": "SELECT source, key, status, fetched_at FROM bronze.ingest_log",
    "backtest_metrics": "FROM ml.backtest_metrics WHERE run_id = (SELECT max(run_id) FROM ml.backtest_metrics)",
    "forecasts": "FROM ml.forecasts WHERE run_id LIKE 'live-%' OR run_id = (SELECT max(run_id) FROM ml.forecasts "
                 "WHERE run_id LIKE 'bt-%')",
}


def points() -> list[dict]:
    """Everything with coordinates: weather points, river points (basin outlet / plant), outage plants."""
    src = load_sources()
    rows = [{"id": p["id"], "kind": "weather", "lat": p["lat"], "lon": p["lon"], "approx": False, "detail": None}
            for p in src["open_meteo_weather"]["points"]]
    rows += [{"id": p["id"], "kind": "river_basin" if p.get("basin") else "river_plant", "lat": p["lat"],
              "lon": p["lon"], "approx": False, "detail": None} for p in src["open_meteo_discharge"]["points"]]
    for e in json.loads(OUTAGES_JSON.read_text())["events"]:
        rows += [{"id": p["plant"], "kind": "outage", "lat": p["lat"], "lon": p["lon"], "approx": p["coord_approx"],
                  "detail": f"{p['capacity_mw']:g} MW, {p['status']}"} for p in e["plants"] if "lat" in p]
    return rows


def export(con, out: Path = OUT) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    manifest = {"exported_at": datetime.now().isoformat(timespec="seconds"), "tables": {}}
    for name, sql in TABLES.items():
        t = time.time()
        path = out / f"{name}.parquet"
        con.execute(f"COPY ({sql}) TO '{path}' (FORMAT parquet, COMPRESSION zstd)")
        cols = [d[0] for d in con.execute(f"SELECT * FROM '{path}' LIMIT 0").description]
        rows = con.execute(f"SELECT count(*) FROM '{path}'").fetchone()[0]
        manifest["tables"][name] = {"rows": rows, "columns": cols, "bytes": path.stat().st_size, "source": sql}
        print(f"  {name:26} {rows:7,} rows {path.stat().st_size / 1024:8,.0f} KB  {time.time() - t:.1f}s", flush=True)
    pts = points()
    con.execute("CREATE OR REPLACE TEMP TABLE _points AS SELECT * FROM (SELECT unnest(?, recursive := true))", [pts])
    con.execute(f"COPY _points TO '{out / 'points.parquet'}' (FORMAT parquet)")
    manifest["tables"]["points"] = {"rows": len(pts), "columns": list(pts[0]), "bytes": (out / "points.parquet").stat().st_size,
                                    "source": "sources.json + outages.json (outage coordinates approximate)"}
    sel = Path("docs/model/selection.json")  # which model ships per target/horizon (from `nea model`)
    if sel.exists():
        (out / "selection.json").write_text(sel.read_text())
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1))
    total = sum(v["bytes"] for v in manifest["tables"].values())
    print(f"✔ exported {len(manifest['tables'])} tables, {total / 1024 / 1024:.1f} MB -> {out}", flush=True)
    return manifest
