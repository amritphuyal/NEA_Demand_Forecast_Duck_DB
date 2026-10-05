import argparse
from collections.abc import Callable

from nea_forecast import dhm, ndor, open_meteo
from nea_forecast.lake import connect

# name -> ingest(con) -> rows written
INGESTERS: dict[str, Callable] = {
    "ndor": ndor.ingest,
    "weather": open_meteo.ingest_weather,
    "discharge": open_meteo.ingest_discharge,
    "dhm": dhm.ingest,
}


def status(con) -> None:
    tables = con.execute("SELECT table_schema||'.'||table_name FROM information_schema.tables "
                         "WHERE table_catalog='lake' AND table_type='BASE TABLE' ORDER BY 1").fetchall()
    for (t,) in tables:
        cols = {c[0] for c in con.execute(f"DESCRIBE {t}").fetchall()}
        rng = ", min(date), max(date)" if "date" in cols else ""
        print(t, *con.execute(f"SELECT count(*){rng} FROM {t}").fetchone())
    for row in con.execute("SELECT source, status, count(*) FROM bronze.ingest_log GROUP BY ALL ORDER BY ALL").fetchall():
        print("  log", *row)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="nea", description="NEA demand forecast data pipeline")
    sub = ap.add_subparsers(dest="cmd", required=True)
    ing = sub.add_parser("ingest", help="fetch new data from sources")
    ing.add_argument("sources", nargs="+", help="source names or 'all'")
    sub.add_parser("status", help="row counts and date ranges per table")
    sub.add_parser("maintain", help="compact lake files, expire old snapshots")
    args = ap.parse_args(argv)

    if args.cmd == "ingest":
        names = list(INGESTERS) if args.sources == ["all"] else args.sources
        unknown = set(names) - set(INGESTERS)
        if unknown:
            ap.error(f"unknown sources: {sorted(unknown)}; known: {sorted(INGESTERS)}")
        con, failed = connect(), []
        for name in names:
            try:
                print(f"{name}: {INGESTERS[name](con)} rows", flush=True)
            except Exception as e:  # one dead source must not stop the others
                print(f"{name}: FAILED {type(e).__name__}: {e}", flush=True)
                failed.append(name)
        return 1 if failed else 0
    elif args.cmd == "status":
        status(connect())
    elif args.cmd == "maintain":
        con = connect()
        con.execute("CALL ducklake_merge_adjacent_files('lake')")
        con.execute("CALL ducklake_expire_snapshots('lake', older_than => now() - INTERVAL 30 DAY)")
        con.execute("CALL ducklake_cleanup_old_files('lake', cleanup_all => true)")
        print("maintained")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
