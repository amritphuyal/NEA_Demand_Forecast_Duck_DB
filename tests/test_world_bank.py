import json
from pathlib import Path

from nea_forecast import world_bank
from nea_forecast.lake import connect

BODY = (Path(__file__).parent / "fixtures" / "wb_gdp.json").read_bytes()


def test_parse_skips_nulls():
    rows = world_bank.parse(json.loads(BODY))
    assert rows == [{"year": 2025, "indicator": "NY.GDP.MKTP.KD", "name": "GDP (constant 2015 US$)", "value": 36537085383.278},
                    {"year": 2024, "indicator": "NY.GDP.MKTP.KD", "name": "GDP (constant 2015 US$)", "value": 35000000000.0}]


def test_ingest_idempotent(tmp_path, monkeypatch):
    monkeypatch.setattr(world_bank, "fetch", lambda url: BODY)
    con = connect(tmp_path)
    world_bank.ingest(con, tmp_path)
    world_bank.ingest(con, tmp_path)
    n_ind = len(world_bank.load_sources()["world_bank"]["indicators"])
    assert con.execute("select count(*) from silver.macro_yearly").fetchone()[0] == 2  # fixture reused per indicator, same key
    assert n_ind >= 2
