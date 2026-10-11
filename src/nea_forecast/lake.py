from datetime import datetime
from pathlib import Path

import duckdb

SCHEMA = Path(__file__).with_name("schema.sql")


def connect(root: Path = Path("data"), read_only: bool = False) -> duckdb.DuckDBPyConnection:
    """Attach the DuckLake lakehouse as `lake` and make sure all tables/views exist."""
    lake_dir = Path(root) / "lake"
    lake_dir.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.execute("INSTALL ducklake; LOAD ducklake")
    opts = "READ_ONLY" if read_only else f"DATA_PATH '{lake_dir / 'files'}/'"
    con.execute(f"ATTACH 'ducklake:{lake_dir / 'nea.ducklake'}' AS lake ({opts})")
    con.execute("USE lake")
    if not read_only:
        con.execute(SCHEMA.read_text())
    return con


def upsert(con: duckdb.DuckDBPyConnection, table: str, rows: list[dict], key: tuple[str, ...]) -> int:
    """Replace rows with matching key (DuckLake has no PK): delete + insert in one transaction."""
    rows = list({tuple(r[k] for k in key): r for r in rows}.values())  # last wins within batch
    if not rows:
        return 0
    cols = list(rows[0])
    col_list = ", ".join(cols)
    # stage outside the lake transaction: DuckDB allows writing one catalog per transaction
    con.execute(f"CREATE OR REPLACE TEMP TABLE _stage AS SELECT {col_list} FROM {table} LIMIT 0")
    con.executemany(f"INSERT INTO _stage VALUES ({', '.join('?' * len(cols))})",
                    [tuple(r[c] for c in cols) for r in rows])
    match = " AND ".join(f"s.{k} = t.{k}" for k in key)
    con.execute("BEGIN")
    try:
        con.execute(f"DELETE FROM {table} t WHERE EXISTS (SELECT 1 FROM _stage s WHERE {match})")
        con.execute(f"INSERT INTO {table} ({col_list}) SELECT {col_list} FROM _stage")
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    return len(rows)


def seen(con: duckdb.DuckDBPyConnection, source: str) -> set[str]:
    """Keys that must not be fetched again (done, or known missing)."""
    q = "SELECT key FROM bronze.ingest_log WHERE source = ? AND status IN ('ok', 'not_found')"
    return {r[0] for r in con.execute(q, [source]).fetchall()}


def log(con: duckdb.DuckDBPyConnection, source: str, key: str, url: str, status: str,
        sha256: str | None = None) -> None:
    log_many(con, source, [(key, url, status, sha256)])


def log_many(con: duckdb.DuckDBPyConnection, source: str, entries: list[tuple]) -> None:
    """entries: (key, url, status, sha256). One commit for the lot: each commit is a lake snapshot."""
    now = datetime.now()
    upsert(con, "bronze.ingest_log", [{"source": source, "key": k, "url": u, "status": st, "sha256": sha,
                                       "fetched_at": now} for k, u, st, sha in entries], ("source", "key"))
