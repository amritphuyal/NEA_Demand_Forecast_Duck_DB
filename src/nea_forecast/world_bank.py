"""World Bank yearly indicators for Nepal (GDP, population): demand-growth drivers for the seasonal model."""
import json
from pathlib import Path

from nea_forecast import load_sources
from nea_forecast.fetch import fetch
from nea_forecast.lake import upsert

URL = "https://api.worldbank.org/v2/country/NPL/indicator/{}?format=json&per_page=100"


def parse(js: list) -> list[dict]:
    return [{"year": int(r["date"]), "indicator": r["indicator"]["id"], "name": r["indicator"]["value"],
             "value": r["value"]} for r in js[1] or [] if r["value"] is not None]


def ingest(con, root: Path = Path("data")) -> int:
    """Full refresh each run: one small call per indicator, and the World Bank revises past years."""
    raw = Path(root) / "raw" / "world_bank"
    raw.mkdir(parents=True, exist_ok=True)
    n = 0
    for ind in load_sources()["world_bank"]["indicators"]:
        body = fetch(URL.format(ind))
        (raw / f"{ind}.json").write_bytes(body)
        rows = parse(json.loads(body))
        n += upsert(con, "silver.macro_yearly", rows, ("year", "indicator"))
        span = f" ({rows[-1]['year']}..{rows[0]['year']})" if rows else ""
        print(f"  world bank {ind}: {len(rows)} years{span}", flush=True)
    return n
