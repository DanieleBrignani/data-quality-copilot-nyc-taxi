"""Manual review of anomalies flagged on REAL rule-valid data (false-positive analysis).

step 1  `python -m dqc.anomaly_review sample`  -> reports/anomaly_review_sample.csv
        random (seeded) sample of Isolation-Forest-flagged records, enriched with zone names,
        derived speed and $/mile to make human inspection possible.
step 2  a human fills reports/anomaly_review_labels.csv (record_id, verdict, note) using the
        criteria in README "False Positive Analysis".
step 3  `python -m dqc.anomaly_review summarize` -> reports/anomaly_review.json
"""

from __future__ import annotations

import json
import sys

import polars as pl

from dqc import anomaly, config, pipeline, profiling, rules

PARTITION = "yellow_2025-01"
SAMPLE = 40
SEED = 11
SAMPLE_CSV = config.REPORTS_DIR / "anomaly_review_sample.csv"
LABELS_CSV = config.REPORTS_DIR / "anomaly_review_labels.csv"


def sample() -> pl.DataFrame:
    th = config.thresholds()["anomaly"]
    src = next(s for s in pipeline.manifest_sources() if s.partition_id == PARTITION)
    df, _ = pipeline.read_partition(src)
    rs = rules.load_ruleset()
    flags = rules.record_flags(rules.evaluate(df, rs, src.year_month), rs)
    valid = profiling.with_derived(df.join(flags.filter(~pl.col("is_valid")).select("record_id"),
                                           on="record_id", how="anti"))
    res, _ = anomaly.isolation_forest(valid, th["features"], th["iforest_train_sample"],
                                      th["iforest_n_estimators"], th["iforest_contamination"], th["random_state"])
    flagged = valid.filter(pl.Series(res.flags)).with_columns(if_score=pl.Series(res.scores[res.flags]))
    zones = pl.read_csv(config.REFERENCE_DIR / "taxi_zone_lookup.csv").select(
        pl.col("LocationID").cast(pl.Int64), pl.col("Zone"))
    s = (flagged.sample(SAMPLE, seed=SEED)
         .join(zones.rename({"LocationID": "PULocationID", "Zone": "pu_zone"}), on="PULocationID", how="left")
         .join(zones.rename({"LocationID": "DOLocationID", "Zone": "do_zone"}), on="DOLocationID", how="left")
         .with_columns(mph=(pl.col("trip_distance") / (pl.col("trip_duration_min") / 60)).round(1),
                       usd_per_mile=(pl.col("fare_amount") / pl.col("trip_distance")).round(2))
         .select("record_id", "if_score", "VendorID", "RatecodeID", "payment_type", "pu_zone", "do_zone",
                 "trip_distance", "trip_duration_min", "mph", "fare_amount", "usd_per_mile", "tip_amount",
                 "tolls_amount", "total_amount"))
    config.REPORTS_DIR.mkdir(exist_ok=True)
    s.write_csv(SAMPLE_CSV)
    return s


def summarize() -> dict:
    labels = pl.read_csv(LABELS_CSV)
    if SAMPLE_CSV.exists():  # the seeded sample must be exactly the set of records that was reviewed
        sampled = set(pl.read_csv(SAMPLE_CSV)["record_id"])
        if sampled != set(labels["record_id"]):
            raise ValueError("anomaly sample changed since review: labels no longer match; re-review needed")
    counts = dict(labels.group_by("verdict").len().sort("len", descending=True).iter_rows())
    out = {"method": "isolation_forest", "partition": PARTITION, "sample_size": labels.height, "seed": SEED,
           "verdict_counts": counts,
           "estimated_false_positive_share": round(counts.get("plausible_legitimate", 0) / labels.height, 3),
           "note": ("Verdicts assigned manually by a single reviewer against the criteria documented in the "
                    "README; not validated by an independent TLC domain expert.")}
    (config.REPORTS_DIR / "anomaly_review.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    return out


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "sample"
    if cmd == "sample":
        pl.Config.set_tbl_rows(50)
        pl.Config.set_tbl_cols(20)
        pl.Config.set_tbl_width_chars(250)
        print(sample())
    else:
        print(json.dumps(summarize(), indent=2))
