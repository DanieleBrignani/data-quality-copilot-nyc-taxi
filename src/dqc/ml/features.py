"""Feature engineering for the fare model. One definition, used by training, batch scoring and the API.

Leakage rules (enforced by `FEATURES`, tested):
* nothing derived from the target or from other monetary columns (tip, tolls, total, surcharges);
* only attributes known when the trip ends: distance, duration, zones, rate code, vendor, clock.
"""

from __future__ import annotations

import numpy as np
import polars as pl

from dqc import pipeline, profiling, rules

TARGET = "fare_amount"
NUMERIC = ["trip_distance", "trip_duration_min", "RatecodeID", "VendorID", "payment_type", "passenger_count",
           "pickup_hour", "pickup_dow"]
ZONES = ["PULocationID", "DOLocationID"]          # high-cardinality categoricals -> target-encoded in the model
FEATURES = NUMERIC + ZONES
ZONE_IDX = [FEATURES.index(z) for z in ZONES]
FORBIDDEN = {"fare_amount", "total_amount", "tip_amount", "tolls_amount", "extra", "mta_tax", "improvement_surcharge",
             "congestion_surcharge", "Airport_fee", "cbd_congestion_fee"}
MISSING = -1.0


def add_features(df: pl.DataFrame) -> pl.DataFrame:
    if "trip_duration_min" not in df.columns:
        df = profiling.with_derived(df)
    return df.with_columns(pickup_hour=pl.col("tpep_pickup_datetime").dt.hour().cast(pl.Int64),
                           pickup_dow=pl.col("tpep_pickup_datetime").dt.weekday().cast(pl.Int64))


def matrix(df: pl.DataFrame) -> np.ndarray:
    """Model input: fixed column order, missing values encoded as -1 (trees split on it explicitly)."""
    return df.select([pl.col(c).cast(pl.Float64).fill_null(MISSING) for c in FEATURES]).to_numpy()


def valid_frame(partition_id: str, sample: int | None = None, seed: int = 0) -> pl.DataFrame:
    """Rule-valid records of a real partition with model features (the population the model serves)."""
    src = next(s for s in pipeline.manifest_sources() if s.partition_id == partition_id)
    df, _ = pipeline.read_partition(src)
    rs = rules.load_ruleset()
    flags = rules.record_flags(rules.evaluate(df, rs, src.year_month), rs)
    df = df.join(flags.filter(~pl.col("is_valid")).select("record_id"), on="record_id", how="anti")
    if sample and sample < df.height:
        df = df.sample(sample, seed=seed)
    return add_features(df)
