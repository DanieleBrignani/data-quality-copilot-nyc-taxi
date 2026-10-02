"""Test helpers. Unit tests use tiny hand-built frames (controlled fixtures), never the benchmark data."""

from __future__ import annotations

import os
from datetime import datetime, timedelta

import polars as pl
import psycopg
import pytest

from dqc import config


def valid_trip(**overrides) -> dict:
    base = {
        "VendorID": 2,
        "tpep_pickup_datetime": datetime(2025, 1, 10, 8, 0, 0),
        "tpep_dropoff_datetime": datetime(2025, 1, 10, 8, 20, 0),
        "passenger_count": 1,
        "trip_distance": 3.2,
        "RatecodeID": 1,
        "store_and_fwd_flag": "N",
        "PULocationID": 161,
        "DOLocationID": 236,
        "payment_type": 1,
        "fare_amount": 18.4,
        "extra": 0.0,
        "mta_tax": 0.5,
        "tip_amount": 4.0,
        "tolls_amount": 0.0,
        "improvement_surcharge": 1.0,
        "total_amount": 27.15,
        "congestion_surcharge": 2.5,
        "Airport_fee": 0.0,
        "cbd_congestion_fee": 0.75,
    }
    base.update(overrides)
    return base


def trips_frame(rows: list[dict], with_ids: bool = True) -> pl.DataFrame:
    schema = {
        "VendorID": pl.Int64, "tpep_pickup_datetime": pl.Datetime("us"), "tpep_dropoff_datetime": pl.Datetime("us"),
        "passenger_count": pl.Int64, "trip_distance": pl.Float64, "RatecodeID": pl.Int64,
        "store_and_fwd_flag": pl.String, "PULocationID": pl.Int64, "DOLocationID": pl.Int64,
        "payment_type": pl.Int64, "fare_amount": pl.Float64, "extra": pl.Float64, "mta_tax": pl.Float64,
        "tip_amount": pl.Float64, "tolls_amount": pl.Float64, "improvement_surcharge": pl.Float64,
        "total_amount": pl.Float64, "congestion_surcharge": pl.Float64, "Airport_fee": pl.Float64,
        "cbd_congestion_fee": pl.Float64,
    }
    df = pl.DataFrame(rows, schema=schema)
    if with_ids:
        df = df.with_row_index("source_row").with_columns(
            source_row=pl.col("source_row").cast(pl.Int64),
            record_id=pl.format("t:{}", pl.col("source_row")))
    return df


def many_valid(n: int, start: datetime = datetime(2025, 1, 5)) -> list[dict]:
    out = []
    for i in range(n):
        p = start + timedelta(minutes=7 * i)
        out.append(valid_trip(tpep_pickup_datetime=p, tpep_dropoff_datetime=p + timedelta(minutes=12 + i % 9),
                              trip_distance=1.0 + (i % 13) * 0.4, PULocationID=1 + i % 263))
    return out


def _db_available() -> bool:
    try:
        with psycopg.connect(config.PG_DSN, connect_timeout=2):
            return True
    except Exception:
        return False


@pytest.fixture(scope="session")
def db_available():
    if os.environ.get("DQC_SKIP_DB") == "1" or not _db_available():
        pytest.skip("PostgreSQL not reachable (set DQC_PG_DSN)")
    return True
