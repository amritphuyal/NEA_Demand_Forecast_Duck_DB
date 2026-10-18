from nea_forecast import nea_widget
from nea_forecast.lake import connect

HTML = ('<div>Power Trade DMS <span>Energy Details</span> <p>7,850 MWh</p><p>NEA</p> <p>13,648 MWh</p>'
        '<p>NEA Subsidiary Companies</p> 46,414 MWh IPP 0 MWh Import 21,517 MWh Export 0 MWh Interruption '
        '67,912 MWh Total Energy Demand 46,395 MWh National Energy Demand 2,997 MW Total Peak Demand '
        '2,320 MW National Peak Demand </span> <div class="invisible flex')  # real page: window ends mid-tag


def test_parse_widget():
    r = nea_widget.parse(HTML)
    assert r == {"nea_gen_mwh": 7850, "nea_sub_gen_mwh": 13648, "ipp_gen_mwh": 46414, "import_mwh": 0,
                 "export_mwh": 21517, "interruption_mwh": 0, "total_energy_demand_mwh": 67912,
                 "national_energy_demand_mwh": 46395, "total_peak_mw": 2997, "national_peak_mw": 2320}


def test_ingest_keeps_only_changes(tmp_path, monkeypatch):
    pages = iter([HTML, HTML, HTML.replace("2,320 MW", "2,401 MW")])
    monkeypatch.setattr(nea_widget, "fetch", lambda url: next(pages).encode())
    con = connect(tmp_path)
    assert [nea_widget.ingest(con, tmp_path) for _ in range(3)] == [1, 0, 1]
    assert con.execute("select list(national_peak_mw order by first_seen) from silver.nea_widget").fetchone()[0] == [2320, 2401]
