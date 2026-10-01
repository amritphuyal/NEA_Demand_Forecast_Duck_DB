import pytest

from nea_forecast import load_sources, SOURCES_JSON
from nea_forecast.cli import main
import json


def test_help():
    with pytest.raises(SystemExit) as e:
        main(["--help"])
    assert e.value.code == 0


def test_sources_json_ids_unique():
    raw = json.loads(SOURCES_JSON.read_text())
    assert len({s["id"] for s in raw}) == len(raw) == len(load_sources())
    assert all("status" in s for s in raw)
