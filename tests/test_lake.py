from datetime import date

from nea_forecast.lake import connect, log, seen, upsert


def test_connect_creates_schema(tmp_path):
    con = connect(tmp_path)
    names = {r[0] for r in con.sql(
        "select table_schema||'.'||table_name from information_schema.tables where table_catalog='lake'").fetchall()}
    assert {"bronze.ingest_log", "silver.nea_daily", "silver.weather_daily"} <= names


def test_upsert_idempotent_and_replaces(tmp_path):
    con = connect(tmp_path)
    rows = [{"date": date(2025, 1, 1), "point": "ktm", "tmax_c": 10.0, "tmin_c": 1.0, "precip_mm": 0.0}]
    upsert(con, "silver.weather_daily", rows, ("date", "point"))
    upsert(con, "silver.weather_daily", [{**rows[0], "tmax_c": 12.0}], ("date", "point"))
    assert con.execute("select count(*), max(tmax_c) from silver.weather_daily").fetchone() == (1, 12.0)


def test_upsert_dedupes_within_batch(tmp_path):
    con = connect(tmp_path)
    r = {"date": date(2025, 1, 1), "point": "ktm", "tmax_c": 10.0, "tmin_c": 1.0, "precip_mm": 0.0}
    assert upsert(con, "silver.weather_daily", [r, {**r, "tmax_c": 11.0}], ("date", "point")) == 1
    assert con.execute("select tmax_c from silver.weather_daily").fetchone() == (11.0,)


def test_upsert_replace_all_is_one_snapshot(tmp_path):
    con = connect(tmp_path)
    r = {"date": date(2025, 1, 1), "point": "ktm", "tmax_c": 10.0, "tmin_c": 1.0, "precip_mm": 0.0}
    upsert(con, "silver.weather_daily", [r, {**r, "point": "bir"}], ("date", "point"))
    before = con.execute("select max(snapshot_id) from ducklake_snapshots('lake')").fetchone()[0]
    upsert(con, "silver.weather_daily", [{**r, "tmax_c": 12.0}], ("date", "point"), replace_all=True)
    assert con.execute("select max(snapshot_id) from ducklake_snapshots('lake')").fetchone()[0] == before + 1
    assert con.execute("select point, tmax_c from silver.weather_daily").fetchall() == [("ktm", 12.0)]


def test_seen_only_ok_and_not_found(tmp_path):
    con = connect(tmp_path)
    log(con, "nea_ndor", "a", "u", "ok")
    log(con, "nea_ndor", "b", "u", "parse_error")
    log(con, "nea_ndor", "c", "u", "not_found")
    assert seen(con, "nea_ndor") == {"a", "c"}


def test_reconnect_persists(tmp_path):
    con = connect(tmp_path)
    log(con, "s", "k", "u", "ok")
    con.close()
    assert seen(connect(tmp_path), "s") == {"k"}


def test_reader_works_while_writer_connected(tmp_path):
    w = connect(tmp_path)
    log(w, "s", "k", "u", "ok")
    r = connect(tmp_path, read_only=True)  # DuckDB-file catalog would raise a lock error here
    assert seen(r, "s") == {"k"}
