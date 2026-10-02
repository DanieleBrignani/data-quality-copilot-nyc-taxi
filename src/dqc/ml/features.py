"""Feature engineering and model specifications. One definition, used by training, batch scoring and the API.

Two residual models share the same machinery:

* ``fare_model``      expected fare      given the trip          -> "is this fare consistent with this trip?"
* ``distance_model``  expected distance  given zones + duration  -> "is this distance consistent with this trip?"

Leakage rules (enforced by tests): a model never sees its own target, and no model sees a monetary
column (tip, tolls, total, surcharges). The distance model additionally never sees the fare, so the two
detectors fail independently.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import polars as pl

from dqc import pipeline, profiling, rules

MONETARY = {"fare_amount", "total_amount", "tip_amount", "tolls_amount", "extra", "mta_tax", "improvement_surcharge",
            "congestion_surcharge", "Airport_fee", "cbd_congestion_fee"}
ZONES = ("PULocationID", "DOLocationID")   # high-cardinality categoricals -> target-encoded inside the pipeline
MISSING = -1.0


@dataclass(frozen=True)
class ModelSpec:
    name: str
    target: str
    features: tuple[str, ...]
    floor: float            # added to both sides of the log-ratio so tiny values do not explode it
    unit: str

    @property
    def zone_idx(self) -> list[int]:
        return [self.features.index(z) for z in ZONES]

    @property
    def forbidden(self) -> set[str]:
        return MONETARY | {self.target}


FARE = ModelSpec("fare_model", "fare_amount",
                 ("trip_distance", "trip_duration_min", "RatecodeID", "VendorID", "payment_type", "passenger_count",
                  "pickup_hour", "pickup_dow", *ZONES), floor=5.0, unit="$")
DISTANCE = ModelSpec("distance_model", "trip_distance",
                     ("trip_duration_min", "RatecodeID", "VendorID", "pickup_hour", "pickup_dow", *ZONES),
                     floor=0.5, unit="mi")
SPECS = {s.name: s for s in (FARE, DISTANCE)}

# backwards-compatible aliases for the fare model
TARGET, FEATURES, FORBIDDEN = FARE.target, list(FARE.features), FARE.forbidden


def add_features(df: pl.DataFrame) -> pl.DataFrame:
    if "trip_duration_min" not in df.columns:
        df = profiling.with_derived(df)
    return df.with_columns(pickup_hour=pl.col("tpep_pickup_datetime").dt.hour().cast(pl.Int64),
                           pickup_dow=pl.col("tpep_pickup_datetime").dt.weekday().cast(pl.Int64))


def matrix(df: pl.DataFrame, spec: ModelSpec = FARE) -> np.ndarray:
    """Model input: fixed column order, missing values encoded as -1 (trees split on it explicitly)."""
    return df.select([pl.col(c).cast(pl.Float64).fill_null(MISSING) for c in spec.features]).to_numpy()


def valid_frame(partition_id: str, sample: int | None = None, seed: int = 0) -> pl.DataFrame:
    """Rule-valid records of a real partition with model features (the population the models serve)."""
    src = next(s for s in pipeline.manifest_sources() if s.partition_id == partition_id)
    df, _ = pipeline.read_partition(src)
    rs = rules.load_ruleset()
    flags = rules.record_flags(rules.evaluate(df, rs, src.year_month), rs)
    df = df.join(flags.filter(~pl.col("is_valid")).select("record_id"), on="record_id", how="anti")
    if sample and sample < df.height:
        df = df.sample(sample, seed=seed)
    return add_features(df)
