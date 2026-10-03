"""PostgreSQL helpers (psycopg 3). Bulk loads go through COPY."""

from __future__ import annotations

import io
import json
import os
import re
from contextlib import contextmanager
from pathlib import Path

import polars as pl
import psycopg
from psycopg import sql as psql

from dqc import config

# canonical (source) column -> warehouse column
RAW_COLUMN_MAP = {
    "VendorID": "vendor_id",
    "tpep_pickup_datetime": "pickup_datetime",
    "tpep_dropoff_datetime": "dropoff_datetime",
    "passenger_count": "passenger_count",
    "trip_distance": "trip_distance",
    "RatecodeID": "ratecode_id",
    "store_and_fwd_flag": "store_and_fwd_flag",
    "PULocationID": "pu_location_id",
    "DOLocationID": "do_location_id",
    "payment_type": "payment_type",
    "fare_amount": "fare_amount",
    "extra": "extra",
    "mta_tax": "mta_tax",
    "tip_amount": "tip_amount",
    "tolls_amount": "tolls_amount",
    "improvement_surcharge": "improvement_surcharge",
    "total_amount": "total_amount",
    "congestion_surcharge": "congestion_surcharge",
    "Airport_fee": "airport_fee",
    "cbd_congestion_fee": "cbd_congestion_fee",
}


@contextmanager
def connect(dsn: str | None = None):
    dsn = dsn or config.PG_DSN
    if not dsn:
        raise RuntimeError("database credentials are not configured: set DQC_PG_PASSWORD (or DQC_PG_DSN) in the "
                           "environment or in .env — see .env.example")
    with psycopg.connect(dsn, autocommit=False) as conn:
        yield conn


def init_schema(conn: psycopg.Connection) -> None:
    sql = (config.ROOT / "infra" / "postgres" / "init.sql").read_text(encoding="utf-8")
    conn.execute(sql)
    # Service roles are created without a password; it is set here from the environment, never from the repo.
    for role, env in (("dqc_copilot", "DQC_COPILOT_PASSWORD"), ("dqc_reader", "DQC_READER_PASSWORD")):
        password = os.environ.get(env)
        if password:
            conn.execute(psql.SQL("ALTER ROLE {} PASSWORD {}").format(psql.Identifier(role), psql.Literal(password)))
    conn.commit()


def dsn_for_database(name: str) -> str:
    if not config.PG_DSN:
        raise RuntimeError("database credentials are not configured (see .env.example)")
    return config.PG_DSN.rsplit("/", 1)[0] + f"/{name}"


def recreate_database(name: str) -> str:
    """Drop + create an isolated database (demo / tests) with the full schema. Returns its DSN."""
    if not re.fullmatch(r"[a-z_][a-z0-9_]*", name):
        raise ValueError(f"unsafe database name: {name!r}")
    with psycopg.connect(dsn_for_database(os.environ.get("DQC_PG_DB", "dqc")), autocommit=True) as conn:
        conn.execute(f"DROP DATABASE IF EXISTS {name} WITH (FORCE)")
        conn.execute(f"CREATE DATABASE {name}")
    dsn = dsn_for_database(name)
    with connect(dsn) as conn:
        init_schema(conn)
    return dsn


def _pg_array(col: str) -> pl.Expr:
    return pl.format("{{{}}}", pl.col(col).list.join(",")).alias(col)


def copy_df(conn: psycopg.Connection, table: str, df: pl.DataFrame, chunk_rows: int = 250_000) -> int:
    """COPY a Polars frame into `table` (columns matched by name). List columns -> Postgres arrays."""
    if df.is_empty():
        return 0
    list_cols = [c for c, t in df.schema.items() if isinstance(t, pl.List)]
    if list_cols:
        df = df.with_columns([_pg_array(c) for c in list_cols])
    cols = ", ".join(f'"{c}"' for c in df.columns)
    with conn.cursor() as cur:
        with cur.copy(f"COPY {table} ({cols}) FROM STDIN WITH (FORMAT csv, NULL '\\N')") as cp:
            for off in range(0, df.height, chunk_rows):
                buf = io.BytesIO()
                df.slice(off, chunk_rows).write_csv(buf, include_header=False, null_value="\\N",
                                                     datetime_format="%Y-%m-%d %H:%M:%S%.f")
                cp.write(buf.getvalue())
    return df.height


def insert_dicts(conn: psycopg.Connection, table: str, rows: list[dict]) -> None:
    if not rows:
        return
    cols = list(rows[0].keys())
    placeholders = ", ".join(["%s"] * len(cols))
    sql = f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({placeholders})"
    vals = [[json.dumps(r[c]) if isinstance(r[c], (dict, list)) else r[c] for c in cols] for r in rows]
    with conn.cursor() as cur:
        cur.executemany(sql, vals)


def raw_partition_table(partition_id: str) -> str:
    return "raw.p_" + re.sub(r"[^a-z0-9]", "_", partition_id.lower())


def query_df(sql: str, params: tuple | dict | None = None, dsn: str | None = None) -> pl.DataFrame:
    with connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        if cur.description is None:
            return pl.DataFrame()
        cols = [d.name for d in cur.description]
        return pl.DataFrame(cur.fetchall(), schema=cols, orient="row", infer_schema_length=None)


def read_sql_file(path: Path) -> str:
    return path.read_text(encoding="utf-8")
