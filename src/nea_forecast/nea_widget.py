"""NEA homepage 'Energy Details' widget: the only public daily NEA figures after the daily reports
stopped (Jan 2025). Undated and overwritten daily, so each run snapshots it and a row is kept only
when the numbers change; first_seen tells when NEA updated it (figures are most likely the previous day)."""
import hashlib
import re
from datetime import datetime
from pathlib import Path

from nea_forecast.fetch import fetch
from nea_forecast.lake import upsert

URL = "https://nea.org.np/"
FIELDS = {"nea": "nea_gen_mwh", "nea subsidiary companies": "nea_sub_gen_mwh", "ipp": "ipp_gen_mwh",
          "import": "import_mwh", "export": "export_mwh", "interruption": "interruption_mwh",
          "total energy demand": "total_energy_demand_mwh", "national energy demand": "national_energy_demand_mwh",
          "total peak demand": "total_peak_mw", "national peak demand": "national_peak_mw"}
# label runs until the next number or any non-letter; window is wide because inline SVG/base64 sit between fields
PAIR_RE = re.compile(r"([\d,]+(?:\.\d+)?)\s*(?:MWh|MW)\s+([A-Za-z][A-Za-z ]*?)(?=\s*(?:[^A-Za-z ]|$)|\s+\d)")


def parse(html: str) -> dict:
    i = html.find("Energy Details")
    if i < 0:
        raise ValueError("NEA homepage: 'Energy Details' widget not found (layout changed?)")
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html[i + len("Energy Details"):i + 20000])).strip()
    out = {}
    for val, label in PAIR_RE.findall(text):
        col = FIELDS.get(label.strip().lower())
        if col:
            out.setdefault(col, float(val.replace(",", "")))  # page repeats the widget (mobile copy)
    if len(out) < len(FIELDS):
        raise ValueError(f"NEA widget: only parsed {sorted(out)}")
    return out


def ingest(con, root: Path = Path("data")) -> int:
    html = fetch(URL)
    now = datetime.now()
    raw = Path(root) / "raw" / "nea_widget"
    raw.mkdir(parents=True, exist_ok=True)
    (raw / f"{now:%Y%m%dT%H%M%S}.html").write_bytes(html)
    row = parse(html.decode("utf-8", "replace"))
    h = hashlib.sha256(repr(sorted(row.items())).encode()).hexdigest()[:16]
    if con.execute("SELECT 1 FROM silver.nea_widget WHERE values_hash = ?", [h]).fetchone():
        print(f"  nea widget unchanged (national peak {row['national_peak_mw']:.0f} MW)", flush=True)
        return 0
    upsert(con, "silver.nea_widget", [{"first_seen": now, "values_hash": h, **row}], ("values_hash",))
    print(f"  nea widget NEW: national peak {row['national_peak_mw']:.0f} MW, import {row['import_mwh']:.0f} MWh, "
          f"export {row['export_mwh']:.0f} MWh", flush=True)
    return 1
