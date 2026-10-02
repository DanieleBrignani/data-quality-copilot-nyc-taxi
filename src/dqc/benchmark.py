"""Detector benchmark on labelled, injected errors.

Protocol
1. Take N REAL records from a partition that pass every deterministic rule (critical + warning).
   These are the "clean" negatives. (Caveat, stated in the README: passing the rules does not prove
   a record is correct, so FPR is an upper bound for "flags on rule-clean data".)
2. Inject known errors into a random 2% of them (plus appended exact duplicates). Each error
   type is either *rule-detectable* (violates an explicit contract) or *plausible* (wrong but
   within valid ranges — the class that only statistical methods might catch).
3. Run every detector on the mixed frame and compute precision / recall / FPR, overall and per type.

Everything is seeded; `python -m dqc benchmark` reproduces the numbers in reports/benchmark.json.
"""

from __future__ import annotations

import json
import time

import numpy as np
import polars as pl

from dqc import anomaly, config, pipeline, profiling, rules
from dqc.ml import fare_model
from dqc.ml import features as ml_features

ERROR_TYPES = {
    # name: (family, description)
    "negative_fare": ("rule_detectable", "fare_amount sign flipped"),
    "dropoff_before_pickup": ("rule_detectable", "drop-off 7 min before pickup"),
    "null_mandatory": ("rule_detectable", "PULocationID set to NULL"),
    "passenger_overflow": ("rule_detectable", "passenger_count = 9"),
    "distance_unit_error": ("rule_detectable", "trip_distance x 1000 (feet/miles confusion)"),
    "invalid_payment_type": ("rule_detectable", "payment_type = 9"),
    "stale_timestamp": ("rule_detectable", "pickup/drop-off shifted to 2009"),
    "fare_x10": ("plausible", "fare_amount and total_amount x 10 (decimal shift), still < $1000 cap"),
    "distance_x5": ("plausible", "trip_distance x 5, still < 200 mi"),
    "tip_spike": ("plausible", "tip_amount = 3 x fare (total adjusted consistently)"),
    "swapped_zones": ("plausible", "PU and DO location swapped"),
}
# re-labelled at injection time when a "plausible" corruption happens to cross a hard limit
DERIVED_TYPES = {"fare_over_cap": "rule_detectable", "exact_duplicate": "rule_detectable"}
SEED = 42


def _clean_real_sample(partition_id: str, n: int) -> pl.DataFrame:
    src = next(s for s in pipeline.manifest_sources() if s.partition_id == partition_id)
    df, _ = pipeline.read_partition(src)
    rs = rules.load_ruleset()
    ev = rules.evaluate(df, rs, src.year_month)
    flagged = rules.record_flags(ev, rs).select("record_id")
    return df.join(flagged, on="record_id", how="anti").sample(n, seed=SEED)


def inject(clean: pl.DataFrame, rate: float = 0.02, seed: int = SEED) -> pl.DataFrame:
    rng = np.random.default_rng(seed)
    n = clean.height
    df = clean.with_columns(label=pl.lit("clean"))
    types = [t for t in ERROR_TYPES]
    k = int(n * rate)
    idx = rng.choice(n, size=k, replace=False)
    assign = np.array(types)[np.arange(k) % len(types)]
    lab = np.full(n, "clean", dtype=object)
    lab[idx] = assign
    df = df.with_columns(label=pl.Series(lab.tolist()))
    L = pl.col("label")
    df = df.with_columns(
        fare_amount=pl.when(L == "negative_fare").then(-pl.col("fare_amount").abs() - 0.5)
        .when(L == "fare_x10").then(pl.col("fare_amount") * 10).otherwise(pl.col("fare_amount")),
        total_amount=pl.when(L == "fare_x10").then(pl.col("total_amount") + pl.col("fare_amount") * 9)
        .when(L == "tip_spike").then(pl.col("total_amount") - pl.col("tip_amount") + 3 * pl.col("fare_amount"))
        .otherwise(pl.col("total_amount")),
        tip_amount=pl.when(L == "tip_spike").then(3 * pl.col("fare_amount")).otherwise(pl.col("tip_amount")),
        tpep_dropoff_datetime=pl.when(L == "dropoff_before_pickup")
        .then(pl.col("tpep_pickup_datetime") - pl.duration(minutes=7))
        .when(L == "stale_timestamp").then(pl.col("tpep_dropoff_datetime") - pl.duration(days=365 * 16))
        .otherwise(pl.col("tpep_dropoff_datetime")),
        tpep_pickup_datetime=pl.when(L == "stale_timestamp")
        .then(pl.col("tpep_pickup_datetime") - pl.duration(days=365 * 16)).otherwise(pl.col("tpep_pickup_datetime")),
        PULocationID=pl.when(L == "null_mandatory").then(None)
        .when(L == "swapped_zones").then(pl.col("DOLocationID")).otherwise(pl.col("PULocationID")),
        DOLocationID=pl.when(L == "swapped_zones").then(pl.col("PULocationID")).otherwise(pl.col("DOLocationID")),
        passenger_count=pl.when(L == "passenger_overflow").then(pl.lit(9, pl.Int64))
        .otherwise(pl.col("passenger_count")),
        trip_distance=pl.when(L == "distance_unit_error").then(pl.col("trip_distance") * 1000 + 250)
        .when(L == "distance_x5").then(pl.col("trip_distance") * 5).otherwise(pl.col("trip_distance")),
        payment_type=pl.when(L == "invalid_payment_type").then(pl.lit(9, pl.Int64)).otherwise(pl.col("payment_type")),
    )
    # the "plausible" distance_x5 must stay plausible; if it crossed a hard limit it would be mislabelled
    df = df.with_columns(label=pl.when((L == "distance_x5") & (pl.col("trip_distance") > 200))
                         .then(pl.lit("distance_unit_error")).otherwise(L))
    df = df.with_columns(label=pl.when((L == "fare_x10") & (pl.col("fare_amount") > 1000))
                         .then(pl.lit("fare_over_cap")).otherwise(L))
    # exact duplicates appended (the copy is the error, the original is clean)
    dups = df.filter(L == "clean").sample(max(1, int(n * rate / len(types))), seed=seed).with_columns(
        label=pl.lit("exact_duplicate"))
    out = pl.concat([df, dups]).with_row_index("source_row").with_columns(
        source_row=pl.col("source_row").cast(pl.Int64),
        record_id=pl.format("bench:{}", pl.col("source_row")))
    return out


def _metrics(pred: np.ndarray, is_err: np.ndarray, labels: np.ndarray) -> dict:
    tp = int((pred & is_err).sum())
    fp = int((pred & ~is_err).sum())
    fn = int((~pred & is_err).sum())
    tn = int((~pred & ~is_err).sum())
    per_type = {}
    for t in sorted(set(labels) - {"clean"}):
        m = labels == t
        per_type[t] = round(float(pred[m].mean()), 4)
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "precision": round(tp / (tp + fp), 4) if tp + fp else None,
            "recall": round(tp / (tp + fn), 4) if tp + fn else None,
            "false_positive_rate": round(fp / (fp + tn), 6) if fp + tn else None,
            "flagged": tp + fp, "recall_by_error_type": per_type}


def run(partition_id: str = "yellow_2025-01", sample: int = 200_000) -> dict:
    th = config.thresholds()["anomaly"]
    clean = _clean_real_sample(partition_id, sample)
    df = inject(clean.drop("record_id", "source_row"))
    labels = df["label"].to_numpy().astype(str)
    is_err = labels != "clean"
    data = df.drop("label")
    ym = partition_id.split("_", 1)[1]
    rs = rules.load_ruleset()

    results, timings = {}, {}
    t = time.perf_counter()
    ev = rules.evaluate(data, rs, ym)
    flags = rules.record_flags(ev, rs)
    timings["rules"] = time.perf_counter() - t
    crit_ids = set(flags.filter(~pl.col("is_valid"))["record_id"])
    any_ids = set(flags["record_id"])
    rid = data["record_id"].to_numpy()
    results["rules_critical"] = _metrics(np.isin(rid, list(crit_ids)), is_err, labels)
    results["rules_critical_plus_warning"] = _metrics(np.isin(rid, list(any_ids)), is_err, labels)

    # statistical detectors see what they would see in production: the records that passed the rules
    feats = th["features"]
    feat_df = profiling.with_derived(data)
    dets = {
        "iqr": lambda: anomaly.iqr(feat_df, feats, th["iqr_k"]),
        "iqr_log": lambda: anomaly.iqr(feat_df, feats, th["iqr_k"], log_transform=True),
        "zscore": lambda: anomaly.zscore(feat_df, feats, th["zscore_threshold"]),
        "isolation_forest": lambda: anomaly.isolation_forest(
            feat_df, feats, th["iforest_train_sample"], th["iforest_n_estimators"], th["iforest_contamination"],
            th["random_state"])[0],
    }
    for name, fn in dets.items():
        r = fn()
        timings[name] = r.runtime_s
        results[name] = _metrics(r.flags, is_err, labels)
        # layered: rules first, then the detector on the survivors (how the pipeline actually works)
        layered = np.isin(rid, list(crit_ids)) | r.flags
        results[f"rules_critical+{name}"] = _metrics(layered, is_err, labels)

    # supervised residual detector (trained on 2024-11, calibrated on 2024-12: this partition is out-of-time)
    lm = fare_model.load()
    if lm is not None and partition_id not in (lm.meta["train_partition"], lm.meta["validation_partition"]):
        t = time.perf_counter()
        _, _, fm_flags = lm.score_frame(ml_features.add_features(feat_df))
        timings["fare_model"] = time.perf_counter() - t
        results["fare_model"] = _metrics(fm_flags, is_err, labels)
        crit = np.isin(rid, list(crit_ids))
        results["rules_critical+fare_model"] = _metrics(crit | fm_flags, is_err, labels)
        log_flags = anomaly.iqr(feat_df, feats, th["iqr_k"], log_transform=True).flags
        results["rules_critical+iqr_log+fare_model"] = _metrics(crit | fm_flags | log_flags, is_err, labels)

    out = {
        "fare_model_version": lm.version if lm is not None else None,
        "partition": partition_id, "clean_real_records": clean.height, "injected_error_rows": int(is_err.sum()),
        "total_rows": df.height, "error_types": {**{k: v[0] for k, v in ERROR_TYPES.items()}, **DERIVED_TYPES},
        "label_counts": dict(zip(*np.unique(labels, return_counts=True), strict=True)),
        "results": results,
        "runtime_s": {k: round(v, 3) for k, v in timings.items()},
        "rows_per_sec": {k: round(df.height / v) for k, v in timings.items() if v > 0},
        "seed": SEED,
    }
    out["label_counts"] = {str(k): int(v) for k, v in out["label_counts"].items()}
    config.REPORTS_DIR.mkdir(exist_ok=True)
    (config.REPORTS_DIR / "benchmark.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    return out


