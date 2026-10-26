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


def test_ingest_continues_after_failure(monkeypatch, tmp_path, capsys):
    from nea_forecast import cli
    def boom(con): raise RuntimeError("site down")
    monkeypatch.setattr(cli, "INGESTERS", {"a": boom, "b": lambda con: 3})
    monkeypatch.setattr(cli, "connect", lambda: type("Con", (), {"close": lambda self: None})())
    assert cli.main(["ingest", "all"]) == 0  # partial failure: logged, chain continues
    out = capsys.readouterr().out
    assert "a: FAILED" in out and "site down" in out and "b: 3 rows" in out and "partial ingest: 1/2" in out
    monkeypatch.setattr(cli, "INGESTERS", {"a": boom})
    assert cli.main(["ingest", "all"]) == 1  # everything failed (e.g. offline): stop the chain
