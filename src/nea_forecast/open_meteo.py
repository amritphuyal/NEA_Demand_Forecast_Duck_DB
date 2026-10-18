"""Open-Meteo: ERA5 daily weather + GloFAS daily river discharge. Free, no key (non-commercial)."""
import json
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urlencode

from nea_forecast import load_sources
from nea_forecast.fetch import fetch
from nea_forecast.lake import upsert

START = date(2010, 1, 1)
OVERLAP = timedelta(days=10)  # ERA5 lags ~5 days; refetch recent window so late values fill in
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
    raw = Path(root) / "raw" / "open_meteo" / kind
    raw.mkdir(parents=True, exist_ok=True)
    n, end = 0, date.today()
    for p in load_sources()[source_id]["points"]:
        start = start_date(con, table, p["id"])
        q = {"latitude": p["lat"], "longitude": p["lon"], "start_date": start, "end_date": end,
             "daily": ",".join(mapping), **extra}
        body = fetch(f"{base}?{urlencode(q)}")
        (raw / f"{p['id']}_{start}_{end}.json").write_bytes(body)
        k = upsert(con, table, parse_daily(json.loads(body), p["id"], mapping), ("date", "point"))
        print(f"  {kind} {p['id']}: {start} .. {end}: {k} rows", flush=True)
        n += k
    return n


def ingest_weather(con, root: Path = Path("data")) -> int:
    return _ingest(con, root, "open_meteo_weather", "weather", "https://archive-api.open-meteo.com/v1/archive",
                   WEATHER, "silver.weather_daily", {"timezone": "Asia/Kathmandu"})


def ingest_discharge(con, root: Path = Path("data")) -> int:
    return _ingest(con, root, "open_meteo_discharge", "discharge", "https://flood-api.open-meteo.com/v1/flood",
                   FLOOD, "silver.river_discharge_daily", {})
