"""Manual review of fare-model flags on REAL out-of-time data (false-positive analysis).

    python -m dqc.ml.review sample      -> reports/fare_model_review_sample.csv   (seeded random sample of flags)
    (a human fills reports/fare_model_review_labels.csv: record_id, verdict, note)
    python -m dqc.ml.review summarize   -> reports/fare_model_review.json
"""

from __future__ import annotations

import json
import sys

import polars as pl

from dqc import config
from dqc.ml import fare_model
from dqc.ml import features as F

PARTITION = "yellow_2025-01"   # test split: never used for training, selection or calibration
SAMPLE, SEED = 40, 7
SAMPLE_CSV = config.REPORTS_DIR / "fare_model_review_sample.csv"
LABELS_CSV = config.REPORTS_DIR / "fare_model_review_labels.csv"


def sample() -> pl.DataFrame:
    lm = fare_model.load()
    df = F.valid_frame(PARTITION)
    pred, dev, flag = lm.score_frame(df)
    flagged = df.with_columns(predicted_fare=pl.Series(pred).round(2), log_ratio=pl.Series(dev).round(3)).filter(
        pl.Series(flag))
    zones = pl.read_csv(config.REFERENCE_DIR / "taxi_zone_lookup.csv").select(
        pl.col("LocationID").cast(pl.Int64), pl.col("Zone"))
    s = (flagged.sample(SAMPLE, seed=SEED)
         .join(zones.rename({"LocationID": "PULocationID", "Zone": "pu_zone"}), on="PULocationID", how="left")
         .join(zones.rename({"LocationID": "DOLocationID", "Zone": "do_zone"}), on="DOLocationID", how="left")
         .with_columns(mph=(pl.col("trip_distance") / (pl.col("trip_duration_min") / 60)).round(1),
                       trip_duration_min=pl.col("trip_duration_min").round(1))
         .select("record_id", "log_ratio", "fare_amount", "predicted_fare", "VendorID", "RatecodeID", "payment_type",
                 "pu_zone", "do_zone", "trip_distance", "trip_duration_min", "mph", "tip_amount", "total_amount"))
    s.write_csv(SAMPLE_CSV)
    return s


def summarize() -> dict:
    labels = pl.read_csv(LABELS_CSV)
    if SAMPLE_CSV.exists() and set(pl.read_csv(SAMPLE_CSV)["record_id"]) != set(labels["record_id"]):
        raise ValueError("fare-model sample changed since review: labels no longer match; re-review needed")
    counts = dict(labels.group_by("verdict").len().sort("len", descending=True).iter_rows())
    out = {"method": "fare_model", "model_version": fare_model.latest_version(), "partition": PARTITION,
           "sample_size": labels.height, "seed": SEED, "verdict_counts": counts,
           "estimated_false_positive_share": round(counts.get("plausible_legitimate", 0) / labels.height, 3),
           "note": ("Verdicts assigned by the project author (AI-assisted build, not an independent TLC "
                    "domain expert) against the criteria documented in the README.")}
    (config.REPORTS_DIR / "fare_model_review.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    return out


if __name__ == "__main__":
    if (sys.argv[1] if len(sys.argv) > 1 else "sample") == "sample":
        pl.Config.set_tbl_rows(50)
        pl.Config.set_tbl_cols(20)
        pl.Config.set_tbl_width_chars(260)
        pl.Config.set_fmt_str_lengths(26)
        print(sample())
    else:
        print(json.dumps(summarize(), indent=2))
