"""Manual review of residual-model flags on REAL out-of-time data (false-positive analysis).

    python -m dqc.ml.review sample fare_model      -> reports/fare_model_review_sample.csv   (seeded random flags)
    (a human fills reports/<model>_review_labels.csv: record_id, verdict, note)
    python -m dqc.ml.review summarize fare_model   -> reports/fare_model_review.json
"""

from __future__ import annotations

import json
import sys

import polars as pl

from dqc import config
from dqc.ml import features as F
from dqc.ml import residual

PARTITION = "yellow_2025-01"   # test split: never used for training, selection or calibration
SAMPLE, SEED = 40, 7


def _paths(name: str):
    return (config.REPORTS_DIR / f"{name}_review_sample.csv", config.REPORTS_DIR / f"{name}_review_labels.csv",
            config.REPORTS_DIR / f"{name}_review.json")


def sample(name: str = F.FARE.name) -> pl.DataFrame:
    lm = residual.load(name)
    df = F.valid_frame(PARTITION)
    pred, dev, flag = lm.score_frame(df)
    flagged = df.with_columns(predicted=pl.Series(pred).round(2), log_ratio=pl.Series(dev).round(3)).filter(
        pl.Series(flag))
    zones = pl.read_csv(config.REFERENCE_DIR / "taxi_zone_lookup.csv").select(
        pl.col("LocationID").cast(pl.Int64), pl.col("Zone"))
    s = (flagged.sample(SAMPLE, seed=SEED)
         .join(zones.rename({"LocationID": "PULocationID", "Zone": "pu_zone"}), on="PULocationID", how="left")
         .join(zones.rename({"LocationID": "DOLocationID", "Zone": "do_zone"}), on="DOLocationID", how="left")
         .with_columns(mph=(pl.col("trip_distance") / (pl.col("trip_duration_min") / 60)).round(1),
                       trip_duration_min=pl.col("trip_duration_min").round(1))
         .select("record_id", "log_ratio", pl.col(lm.spec.target).alias("actual"), "predicted", "VendorID",
                 "RatecodeID", "payment_type", "pu_zone", "do_zone", "trip_distance", "trip_duration_min", "mph",
                 "fare_amount", "tip_amount", "total_amount"))
    s.write_csv(_paths(name)[0])
    return s


def summarize(name: str = F.FARE.name) -> dict:
    sample_csv, labels_csv, out_json = _paths(name)
    labels = pl.read_csv(labels_csv)
    if sample_csv.exists() and set(pl.read_csv(sample_csv)["record_id"]) != set(labels["record_id"]):
        raise ValueError(f"{name}: sample changed since review, labels no longer match; re-review needed")
    counts = dict(labels.group_by("verdict").len().sort("len", descending=True).iter_rows())
    out = {"method": name, "model_version": residual.latest_version(name), "partition": PARTITION,
           "sample_size": labels.height, "seed": SEED, "verdict_counts": counts,
           "estimated_false_positive_share": round(counts.get("plausible_legitimate", 0) / labels.height, 3),
           "note": ("Verdicts assigned manually by a single reviewer against the criteria documented in the "
                    "README; not validated by an independent TLC domain expert.")}
    out_json.write_text(json.dumps(out, indent=2), encoding="utf-8")
    return out


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "sample"
    model = sys.argv[2] if len(sys.argv) > 2 else F.FARE.name
    if cmd == "sample":
        pl.Config.set_tbl_rows(50)
        pl.Config.set_tbl_cols(20)
        pl.Config.set_tbl_width_chars(260)
        pl.Config.set_fmt_str_lengths(24)
        print(sample(model))
    else:
        print(json.dumps(summarize(model), indent=2))
