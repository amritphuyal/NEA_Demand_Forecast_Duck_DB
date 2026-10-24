"""Capacity out of service (floods, lost transmission, reservoir shortfall) from outages.json -> silver.plant_outage.
Full refresh: the JSON is the hand-kept, sourced register (edit it as NEA restores plants)."""
import json
from pathlib import Path

from nea_forecast.lake import upsert

OUTAGES_JSON = Path(__file__).resolve().parents[2] / "outages.json"


def rows(doc: dict) -> list[dict]:
    return [{"event": e["event"], "plant": p["plant"], "river": p.get("river"), "capacity_mw": float(p["capacity_mw"]),
             "kind": p["kind"], "status": p["status"], "outage_start": e["outage_start"],
             "expected_return": p.get("expected_return"), "winter_energy_gwh": p.get("winter_energy_gwh"),
             "note": p.get("note"), "source_url": " ".join(e["sources"])} for e in doc["events"] for p in e["plants"]]


def ingest(con, root: Path = Path("data")) -> int:
    r = rows(json.loads(OUTAGES_JSON.read_text()))
    con.execute("DELETE FROM silver.plant_outage")  # tiny table; the JSON register is the truth
    n = upsert(con, "silver.plant_outage", r, ("event", "plant"))
    mw = sum(x["capacity_mw"] for x in r)
    print(f"  outages: {n} entries, {mw:,.0f} MW out of service", flush=True)
    return n
