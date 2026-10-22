"""Open-Meteo: ERA5 daily weather + GloFAS daily river discharge. Free, no key (non-commercial)."""
import json
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urlencode

from nea_forecast import load_sources
from nea_forecast.fetch import fetch
from nea_forecast.lake import upsert

START = date(2010, 1, 1)
OVERLAP = timedelta(days=3)  # last days are provisional (ERA5T, GloFAS updates): refetch them; ERA5 itself
# lags ~5 days, and those still-empty days are skipped by parse_daily, so they are fetched next run anyway
WEATHER = {"temperature_2m_max": "tmax_c", "temperature_2m_min": "tmin_c", "precipitation_sum": "precip_mm"}
FLOOD = {"river_discharge": "discharge_m3s"}


def parse_daily(js: dict, point: str, mapping: dict[str, str]) -> list[dict]:
    """Rows with at least one value; all-null days (not yet published) are skipped, not zeroed."""
    d = js["daily"]
    rows = []
    for i, t in enumerate(d["time"]):
        vals = {col: d[api][i] for api, col in mapping.items()}
        if any(v is not None for v in vals.values()):
            rows.append({"date": date.fromisoformat(t), "point": point, **vals})
    return rows


def start_date(con, table: str, point: str) -> date:
    last = con.execute(f"SELECT max(date) FROM {table} WHERE point = ?", [point]).fetchone()[0]
    return last - OVERLAP if last else START


def _ingest(con, root: Path, source_id: str, kind: str, base: str, mapping: dict, table: str, extra: dict) -> int:
    """All points in one request (Open-Meteo takes comma-separated coordinates), from the earliest
    per-point start: normally last stored day - OVERLAP, so only the recent window is fetched."""
    raw = Path(root) / "raw" / "open_meteo" / kind
    raw.mkdir(parents=True, exist_ok=True)
    pts, end = load_sources()[source_id]["points"], date.today()
    start = min(start_date(con, table, p["id"]) for p in pts)
    q = {"latitude": ",".join(str(p["lat"]) for p in pts), "longitude": ",".join(str(p["lon"]) for p in pts),
         "start_date": start, "end_date": end, "daily": ",".join(mapping), **extra}
    body = fetch(f"{base}?{urlencode(q)}")
    (raw / f"{start}_{end}.json").write_bytes(body)
    js = json.loads(body)
    n = 0
    for p, d in zip(pts, js if isinstance(js, list) else [js]):
        k = upsert(con, table, parse_daily(d, p["id"], mapping), ("date", "point"))
        print(f"  {kind} {p['id']}: {start} .. {end}: {k} rows", flush=True)
        n += k
    return n


def ingest_weather(con, root: Path = Path("data")) -> int:
    return _ingest(con, root, "open_meteo_weather", "weather", "https://archive-api.open-meteo.com/v1/archive",
                   WEATHER, "silver.weather_daily", {"timezone": "Asia/Kathmandu"})


def ingest_discharge(con, root: Path = Path("data")) -> int:
    return _ingest(con, root, "open_meteo_discharge", "discharge", "https://flood-api.open-meteo.com/v1/flood",
                   FLOOD, "silver.river_discharge_daily", {})


FORECAST = {"river_discharge_mean": "discharge_m3s", "river_discharge_p25": "p25", "river_discharge_p75": "p75"}


def ingest_discharge_forecast(con, root: Path = Path("data")) -> int:
    """GloFAS forecast to ~7 months ahead (daily 30-day + seasonal), ensemble mean/p25/p75, all points in
    one request. Kept per issue date so past forecasts stay queryable (and can be scored later)."""
    pts = load_sources()["open_meteo_discharge"]["points"]
    q = {"latitude": ",".join(str(p["lat"]) for p in pts), "longitude": ",".join(str(p["lon"]) for p in pts),
         "daily": ",".join(FORECAST), "forecast_days": 210}
    body = fetch(f"https://flood-api.open-meteo.com/v1/flood?{urlencode(q)}")
    issued = date.today()
    raw = Path(root) / "raw" / "open_meteo" / "discharge_forecast"
    raw.mkdir(parents=True, exist_ok=True)
    (raw / f"{issued}.json").write_bytes(body)
    js = json.loads(body)
    rows = [{"issued": issued, **r} for p, d in zip(pts, js if isinstance(js, list) else [js])
            for r in parse_daily(d, p["id"], FORECAST)]
    n = upsert(con, "silver.river_discharge_forecast", rows, ("issued", "date", "point"))
    span = f"{min(r['date'] for r in rows)} .. {max(r['date'] for r in rows)}" if rows else "none"
    print(f"  discharge forecast issued {issued}: {len(pts)} points, {span}", flush=True)
    return n
