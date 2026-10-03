"""Reproduces the exploratory measurements quoted in the README (python -m dqc evidence).

The pipeline reports cover what the platform does on every run. This module covers the one-off
measurements that justified design decisions — the thresholds, the rule versions that were discarded,
the experiments that failed — so that those numbers also have a command behind them.
Writes reports/evidence.json.
"""

from __future__ import annotations

import dataclasses
import json

import numpy as np
import polars as pl

from dqc import benchmark, config, db, pipeline, profiling, rules
from dqc.ml import features as F
from dqc.ml import residual

COMPONENTS = ["fare_amount", "extra", "mta_tax", "tip_amount", "tolls_amount", "improvement_surcharge",
              "congestion_surcharge", "Airport_fee", "cbd_congestion_fee"]
BUSINESS_KEY = ["VendorID", "tpep_pickup_datetime", "tpep_dropoff_datetime", "PULocationID", "DOLocationID",
                "trip_distance"]


def _pct(a: int, b: int) -> float:
    return round(100 * a / b, 4) if b else 0.0


def partition_facts(src: pipeline.PartitionSource, ruleset: rules.RuleSet) -> dict:
    df, _ = pipeline.read_partition(src)
    n = df.height
    start, end = rules.month_window(src.year_month)
    out: dict = {"rows": n}

    # --- extremes that grounded the range rules
    out["max_trip_distance"] = df["trip_distance"].max()
    out["max_fare_amount"] = df["fare_amount"].max()
    out["p9999_trip_distance"] = round(df["trip_distance"].quantile(0.9999), 2)
    out["p9999_fare_amount"] = round(df["fare_amount"].quantile(0.9999), 2)
    outside = df.filter((pl.col("tpep_pickup_datetime") < start) | (pl.col("tpep_pickup_datetime") >= end))
    out["pickup_outside_month"] = outside.height
    out["pickup_years_outside_month"] = sorted(outside["tpep_pickup_datetime"].dt.year().unique().to_list())

    # --- passenger_count nulls vs Flex Fare
    null_pc = pl.col("passenger_count").is_null()
    flex = pl.col("payment_type") == 0
    out["passenger_count_nulls"] = df.filter(null_pc).height
    out["flex_fare_rows"] = df.filter(flex).height
    out["nulls_are_exactly_flex_fare"] = df.filter(null_pc != flex).height == 0
    out["flex_fare_share_pct"] = _pct(out["flex_fare_rows"], n)

    # --- total reconciliation: the two discarded versions
    z = {c: pl.col(c).fill_null(0.0) for c in COMPONENTS}
    residual_expr = pl.col("total_amount") - pl.sum_horizontal(list(z.values()))
    v1_fail = df.filter(residual_expr.abs() > 0.01).height
    cs, af = z["congestion_surcharge"], z["Airport_fee"]
    v2_ok = pl.any_horizontal([(residual_expr + k).abs() <= 0.01 for k in (pl.lit(0.0), cs, af, cs + af)])
    non_flex = df.filter(~flex)
    out["reconciliation_v1_naive_fail_pct"] = _pct(v1_fail, n)
    out["reconciliation_v2_fail_pct"] = _pct(non_flex.filter(~v2_ok).height, non_flex.height)

    # --- duplicates on the business key
    groups = df.group_by(BUSINESS_KEY).agg(n=pl.len(), neg=(pl.col("total_amount") < 0).sum()).filter(pl.col("n") > 1)
    out["business_key_collision_groups"] = groups.height
    out["business_key_groups_with_reversal"] = groups.filter(pl.col("neg") > 0).height
    out["exact_duplicates"] = n - df.select(pl.exclude("record_id", "source_row")).unique().height

    # --- negative fares
    neg = df.filter(pl.col("fare_amount") < 0)
    neg_flex = neg.filter(flex)
    out["negative_fare_rows"] = neg.height
    out["negative_fare_flex_fare"] = neg_flex.height
    out["negative_fare_flex_share_pct"] = _pct(neg_flex.height, neg.height)
    out["negative_fare_flex_with_non_negative_total_pct"] = _pct(neg_flex.filter(pl.col("total_amount") >= 0).height,
                                                               neg_flex.height)
    out["negative_fare_by_payment_type"] = dict(neg.group_by("payment_type").len().sort("payment_type").iter_rows())

    # --- rare categories behind the cardinality warnings
    out["payment_type_5_rows"] = df.filter(pl.col("payment_type") == 5).height
    out["vendor_7_rows"] = df.filter(pl.col("VendorID") == 7).height
    out["vendor_7_share_pct"] = _pct(out["vendor_7_rows"], n)
    out["distinct_vendors"] = df["VendorID"].n_unique()

    # --- rule-valid population: zero-distance patterns and the original (unfixed) IQR
    flags = rules.record_flags(rules.evaluate(df, ruleset, src.year_month), ruleset)
    valid = profiling.with_derived(df.join(flags.filter(~pl.col("is_valid")).select("record_id"), on="record_id",
                                           how="anti"))
    v = valid.height
    zero = valid.filter((pl.col("trip_distance") == 0) & (pl.col("fare_amount") > 0))
    diff = pl.col("PULocationID") != pl.col("DOLocationID")
    long_diff = zero.filter(diff & (pl.col("trip_duration_min") >= 5))
    short = zero.filter(pl.col("trip_duration_min") < 1)
    out["valid_rows"] = v
    out["zero_distance_charged_pct_of_valid"] = _pct(zero.height, v)
    out["zero_distance_diff_zones_5min_rows"] = long_diff.height
    out["zero_distance_diff_zones_5min_pct_of_valid"] = _pct(long_diff.height, v)
    out["zero_distance_diff_zones_5min_flex_share_pct"] = _pct(long_diff.filter(pl.col("payment_type") == 0).height,
                                                             long_diff.height)
    out["charged_under_1min_pct_of_valid"] = _pct(short.height, v)
    out["charged_under_1min_ratecode5_share_pct"] = _pct(short.filter(pl.col("RatecodeID") == 5).height, short.height)

    feats = config.thresholds()["anomaly"]["features"]
    x = valid.select([pl.col(f).cast(pl.Float64).fill_null(0.0) for f in feats]).to_numpy()
    q1, q3 = np.percentile(x, 25, axis=0), np.percentile(x, 75, axis=0)
    lo, hi = q1 - 3 * (q3 - q1), q3 + 3 * (q3 - q1)
    flagged = (x < lo) | (x > hi)                      # original version: zero-IQR features NOT skipped
    out["iqr_unfixed_flagged_pct_of_valid"] = _pct(int(flagged.any(axis=1).sum()), v)
    out["iqr_unfixed_flagged_by_feature"] = {f: int(flagged[:, i].sum()) for i, f in enumerate(feats)}
    out["iqr_unfixed_trip_distance_upper_fence"] = round(float(hi[feats.index("trip_distance")]), 2)
    return out


def detector_experiments(ruleset: rules.RuleSet, partition_id: str = "yellow_2025-01", sample: int = 200_000) -> dict:
    """The model experiments described under 'What failed': old score, zone-pair lookup, clean-pool effect."""
    out: dict = {}
    src = next(s for s in pipeline.manifest_sources() if s.partition_id == partition_id)

    def bench_frame(rs: rules.RuleSet) -> tuple[pl.DataFrame, np.ndarray]:
        df, _ = pipeline.read_partition(src)
        flagged = rules.record_flags(rules.evaluate(df, rs, src.year_month), rs).select("record_id")
        clean = df.join(flagged, on="record_id", how="anti").sample(sample, seed=benchmark.SEED)
        mixed = benchmark.inject(clean.drop("record_id", "source_row"))
        return F.add_features(mixed.drop("label")), mixed["label"].to_numpy().astype(str)

    frame, labels = bench_frame(ruleset)
    is_err = labels != "clean"

    def recall(flag, kind):
        return round(float(flag[labels == kind].mean()), 4)

    fare = residual.load("fare_model")
    va = F.valid_frame(fare.meta["validation_partition"], 300_000, residual.SEED)
    y_va, p_va = va[F.FARE.target].to_numpy(), fare.predict(F.matrix(va, F.FARE))
    old = lambda y, p: np.abs(y - p) / np.maximum(p, F.FARE.floor)   # noqa: E731  first, asymmetric score
    thr_old = float(np.quantile(old(y_va, p_va), 1 - residual.ALPHA))
    y_b = frame[F.FARE.target].cast(pl.Float64).fill_null(np.nan).to_numpy()
    p_b = fare.predict(F.matrix(frame, F.FARE))
    old_flag = np.nan_to_num(old(y_b, p_b), nan=np.inf) > thr_old
    _, _, new_flag = fare.score_frame(frame)
    out["fare_model_asymmetric_score_recall_distance_x5"] = recall(old_flag, "distance_x5")
    out["fare_model_log_ratio_recall_distance_x5"] = recall(new_flag, "distance_x5")

    # zone-pair median distance as a reference (the lookup that was tried before the distance model)
    train = F.valid_frame(fare.meta["train_partition"])
    pair = (train.filter(pl.col("trip_distance") > 0).group_by("PULocationID", "DOLocationID")
            .agg(n=pl.len(), med=pl.col("trip_distance").median()).filter(pl.col("n") >= 30))
    score = ((pl.col("trip_distance") + 0.5) / (pl.col("med") + 0.5)).log().abs()
    s_va = va.join(pair, on=["PULocationID", "DOLocationID"], how="left").select(score.alias("s"))["s"]
    thr_pair = s_va.drop_nulls().quantile(1 - residual.ALPHA)
    pair_flag = (frame.join(pair, on=["PULocationID", "DOLocationID"], how="left")
                 .select((score > thr_pair).fill_null(False).alias("f"))["f"].to_numpy())
    out["zone_pair_lookup_recall_distance_unit_error"] = recall(pair_flag, "distance_unit_error")
    out["zone_pair_lookup_recall_distance_x5"] = recall(pair_flag, "distance_x5")

    dist = residual.load("distance_model")
    _, _, d_flag = dist.score_frame(frame)
    out["distance_model_recall_distance_x5"] = recall(d_flag, "distance_x5")

    def precision(flag, err):
        return round(float((flag & err).sum() / flag.sum()), 4)

    out["precision_current_ruleset"] = {"fare_model": precision(new_flag, is_err), "distance_model": precision(d_flag, is_err)}
    # the same models, with the benchmark's "clean" pool defined by the previous ruleset (no DQ027 / DQ028)
    prev = dataclasses.replace(ruleset, rules=tuple(r for r in ruleset.rules
                                                    if not r.rule_id.startswith(("DQ027", "DQ028"))))
    frame_prev, labels_prev = bench_frame(prev)
    err_prev = labels_prev != "clean"
    out["precision_without_zero_distance_rules"] = {
        "fare_model": precision(fare.score_frame(frame_prev)[2], err_prev),
        "distance_model": precision(dist.score_frame(frame_prev)[2], err_prev)}
    return out


def warehouse_facts() -> dict:
    row = db.query_df("""SELECT (SELECT count(*) FROM dq.quarantine WHERE resolved_by_run_id IS NULL) AS quarantine_rows,
                                (SELECT count(DISTINCT record_id) FROM dq.quarantine
                                 WHERE resolved_by_run_id IS NULL) AS quarantined_records,
                                pg_total_relation_size('dq.quarantine') AS quarantine_bytes,
                                (SELECT sum(pg_total_relation_size(inhrelid)) FROM pg_inherits
                                 WHERE inhparent = 'raw.yellow_trips'::regclass) AS raw_bytes""").to_dicts()[0]
    row["quarantine_gb"] = round(row["quarantine_bytes"] / 1e9, 2)
    row["raw_gb"] = round(float(row["raw_bytes"]) / 1e9, 2)
    return {k: (int(v) if k.endswith(("bytes", "rows", "records")) else v) for k, v in row.items()}


def run(with_experiments: bool = True) -> dict:
    ruleset = rules.load_ruleset()
    out = {"ruleset_version": ruleset.version,
           "partitions": {s.partition_id: partition_facts(s, ruleset) for s in pipeline.manifest_sources()}}
    if with_experiments:
        out["detector_experiments"] = detector_experiments(ruleset)
    try:
        out["warehouse"] = warehouse_facts()
    except Exception as exc:  # the file-based facts do not need a database
        out["warehouse"] = {"unavailable": repr(exc)[:200]}
    config.REPORTS_DIR.mkdir(exist_ok=True)
    (config.REPORTS_DIR / "evidence.json").write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    return out
