import numpy as np
import polars as pl

from dqc import anomaly, drift


def test_psi_is_zero_for_identical_and_large_for_shifted():
    rng = np.random.default_rng(0)
    a = rng.normal(10, 2, 50_000)
    assert drift.psi_numeric(a, a.copy()) < 1e-9
    assert drift.psi_numeric(a, rng.normal(10, 2, 50_000)) < 0.01
    assert drift.psi_numeric(a, rng.normal(13, 2, 50_000)) > 0.25


def test_psi_categorical_handles_new_categories():
    ref = pl.Series([1] * 90 + [2] * 10)
    cur = pl.Series([1] * 50 + [2] * 10 + [7] * 40)
    assert drift.psi_categorical(ref, ref) < 1e-9
    assert drift.psi_categorical(ref, cur) > 0.25


def _cfg():
    return {"sample_size": 10_000, "psi_bins": 10, "psi_warn": 0.1, "psi_alert": 0.25, "ks_alert": 0.1,
            "null_rate_alert_pp": 2.0, "cardinality_alert_pct": 20.0, "mean_shift_alert_pct": 15.0,
            "min_new_category_share_pct": 0.1,
            "volume_alert_pct": 20.0, "std_mean_shift_alert": 0.2, "numeric_columns": ["x"], "categorical_columns": ["c"]}


def test_compare_flags_shift_nulls_volume_and_cardinality():
    rng = np.random.default_rng(1)
    ref = pl.DataFrame({"x": rng.normal(0, 1, 20_000), "c": rng.integers(0, 5, 20_000)})
    cur = pl.DataFrame({"x": np.where(rng.random(30_000) < 0.1, np.nan, rng.normal(1.5, 1, 30_000)),
                        "c": rng.integers(0, 9, 30_000)}).with_columns(pl.col("x").fill_nan(None))
    res = {(r["column_name"], r["metric"]): r for r in drift.compare(ref, cur, _cfg())}
    assert res[("__table__", "volume_change_pct")]["status"] == "alert"
    assert res[("x", "psi")]["status"] == "alert"
    assert res[("x", "ks_statistic")]["status"] == "alert"
    assert res[("x", "mean_shift_std")]["status"] == "alert"
    assert res[("x", "mean_shift_pct")]["status"] == "n/a"  # reference mean ~0
    assert res[("x", "null_rate_change_pp")]["status"] == "alert"
    assert res[("c", "cardinality_change_pct")]["status"] == "alert"


def test_compare_is_quiet_on_same_distribution():
    rng = np.random.default_rng(2)
    ref = pl.DataFrame({"x": rng.normal(0, 1, 20_000), "c": rng.integers(0, 5, 20_000)})
    cur = pl.DataFrame({"x": rng.normal(0, 1, 20_000), "c": rng.integers(0, 5, 20_000)})
    alerts = [r for r in drift.compare(ref, cur, _cfg()) if r["status"] == "alert"]
    assert alerts == []


def test_iqr_and_zscore_catch_extreme_values():
    rng = np.random.default_rng(3)
    x = rng.normal(10, 1, 5_000)
    x[:5] = 1_000
    df = pl.DataFrame({"f": x})
    assert anomaly.iqr(df, ["f"], 3.0).flags[:5].all()
    assert anomaly.zscore(df, ["f"], 4.0).flags[:5].all()


def test_isolation_forest_flags_about_contamination_share():
    rng = np.random.default_rng(4)
    df = pl.DataFrame({"a": rng.normal(0, 1, 20_000), "b": rng.normal(0, 1, 20_000)})
    res, model = anomaly.isolation_forest(df, ["a", "b"], train_sample=5_000, contamination=0.01)
    # by construction ~1% is flagged even on perfectly clean data -> it cannot be a validity rule
    assert 0.005 < res.flags.mean() < 0.02
    assert (res.flags == (model.predict(df.to_numpy()) == -1)).all()


def test_iqr_skips_zero_inflated_features_and_log_variant_is_tighter_on_skew():
    rng = np.random.default_rng(5)
    tolls = np.where(rng.random(10_000) < 0.05, 6.94, 0.0)          # Q1 == Q3 == 0
    dist = rng.lognormal(0.5, 0.8, 10_000)                          # right-skewed like trip_distance
    df = pl.DataFrame({"tolls": tolls, "dist": dist})
    plain = anomaly.iqr(df, ["tolls", "dist"], 3.0)
    logged = anomaly.iqr(df, ["tolls", "dist"], 3.0, log_transform=True)
    assert plain.per_feature["tolls"] == "skipped_zero_iqr"
    assert logged.flags.sum() < plain.flags.sum()


def test_rare_new_category_is_a_warning_not_an_alert():
    ref = pl.DataFrame({"x": [1.0] * 10_000, "c": [1, 2, 3] * 3333 + [1]})
    cur = pl.DataFrame({"x": [1.0] * 10_000, "c": [1, 2, 3] * 3333 + [5]})  # one row in a brand-new category
    res = {(r["column_name"], r["metric"]): r for r in drift.compare(ref, cur, _cfg())}
    assert res[("c", "cardinality_change_pct")]["status"] == "warn"
    assert res[("c", "new_category_share_pct")]["value"] == 0.01
