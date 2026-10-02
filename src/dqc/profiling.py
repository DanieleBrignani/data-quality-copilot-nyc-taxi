"""Column profiling: one snapshot row per (partition, column)."""

from __future__ import annotations

import polars as pl

QUANTILES = (0.01, 0.05, 0.25, 0.75, 0.95, 0.99)


def with_derived(df: pl.DataFrame) -> pl.DataFrame:
    """Derived columns used by profiling, drift and anomaly detection (never written back to raw)."""
    return df.with_columns(
        trip_duration_min=(pl.col("tpep_dropoff_datetime") - pl.col("tpep_pickup_datetime")).dt.total_seconds() / 60.0
    )


def profile(df: pl.DataFrame, exclude: tuple[str, ...] = ("record_id", "source_row")) -> pl.DataFrame:
    n = df.height
    rows = []
    for col in df.columns:
        if col in exclude:
            continue
        s = df[col]
        nulls = s.null_count()
        distinct = s.n_unique()
        row = {
            "column_name": col, "dtype": str(s.dtype), "row_count": n, "null_count": nulls,
            "null_rate": nulls / n if n else 0.0, "distinct_count": distinct,
            "cardinality_ratio": distinct / n if n else 0.0,
            "min": None, "max": None, "mean": None, "median": None, "std": None,
            **{f"p{int(q * 100):02d}": None for q in QUANTILES},
        }
        if s.dtype.is_numeric():
            nn = s.drop_nulls().cast(pl.Float64)
            if nn.len():
                row.update(min=nn.min(), max=nn.max(), mean=nn.mean(), median=nn.median(), std=nn.std(),
                           **{f"p{int(q * 100):02d}": nn.quantile(q, "linear") for q in QUANTILES})
            row["min_text"], row["max_text"] = None, None
        else:
            nn = s.drop_nulls()
            row["min_text"] = str(nn.min()) if nn.len() else None
            row["max_text"] = str(nn.max()) if nn.len() else None
        rows.append(row)
    return pl.DataFrame(rows, infer_schema_length=None)
