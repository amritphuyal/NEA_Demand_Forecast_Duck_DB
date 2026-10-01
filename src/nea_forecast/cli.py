import argparse
from collections.abc import Callable

# name -> ingest(con) -> rows written. Each source module registers itself here.
INGESTERS: dict[str, Callable] = {}


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
        for name in names:
            print(f"{name}: {INGESTERS[name](None)} rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
