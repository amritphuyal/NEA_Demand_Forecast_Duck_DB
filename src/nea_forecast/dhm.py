"""DHM river-watch: latest gauge level per station, embedded as JSON in the page."""
import json
import re
from datetime import datetime
from pathlib import Path

from nea_forecast.fetch import fetch
from nea_forecast.lake import upsert

URL = "https://www.dhm.gov.np/hydrology/river-watch"
COORDS_RE = re.compile(r"var\s+coordinates\s*=\s*(\[.*?\])\s*;", re.S)


def _num(v) -> float | None:
    return float(v) if v not in (None, "") else None


def parse_river_watch(html: str) -> list[dict]:
    m = COORDS_RE.search(html)
    if not m:
        raise ValueError("DHM river-watch: 'var coordinates' not found (layout changed?)")
    rows = []
    for s in json.loads(m.group(1)):
        wl = s.get("waterLevel") or {}
        if wl.get("value") is None:
            continue
        rows.append({"station_id": int(s["id"]), "observed_at": datetime.fromisoformat(wl["datetime"]),
                     "name": s.get("name"), "basin": s.get("basin"), "district": s.get("district"),
                     "lat": _num(s.get("latitude")), "lon": _num(s.get("longitude")), "level_m": _num(wl["value"]),
                     "warning_level": _num(s.get("warning_level")), "danger_level": _num(s.get("danger_level")),
                     "status": s.get("status")})
    return rows


def ingest(con, root: Path = Path("data")) -> int:
    print(f"  dhm: fetching {URL}", flush=True)
    html = fetch(URL)
    raw = Path(root) / "raw" / "dhm"
    raw.mkdir(parents=True, exist_ok=True)
    (raw / f"{datetime.now():%Y%m%dT%H%M%S}.html").write_bytes(html)
    return upsert(con, "silver.river_level_obs", parse_river_watch(html.decode("utf-8", "replace")),
                  ("station_id", "observed_at"))
