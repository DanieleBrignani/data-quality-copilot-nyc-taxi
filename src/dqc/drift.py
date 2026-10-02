"""Distribution drift between chronological partitions.

Metrics
  * PSI (numeric: quantile bins of the reference; categorical: category frequencies)
  * Kolmogorov-Smirnov D statistic (+ p-value, reported but NOT used for alerting: with
    hundreds of thousands of rows every p-value is ~0, so we alert on the effect size D)
  * null-rate change (percentage points), cardinality change (%), mean / median shift (%)
  * volume change (%)
"""

from __future__ import annotations

import numpy as np
import polars as pl
from scipy import stats

EPS = 1e-6


def psi_numeric(ref: np.ndarray, cur: np.ndarray, bins: int = 10) -> float:
    ref, cur = ref[~np.isnan(ref)], cur[~np.isnan(cur)]
    if len(ref) == 0 or len(cur) == 0:
        return float("nan")
    edges = np.unique(np.quantile(ref, np.linspace(0, 1, bins + 1)[1:-1]))
    edges = np.concatenate(([-np.inf], edges, [np.inf]))
    r = np.histogram(ref, edges)[0] / len(ref)
    c = np.histogram(cur, edges)[0] / len(cur)
    r, c = np.clip(r, EPS, None), np.clip(c, EPS, None)
    return float(np.sum((c - r) * np.log(c / r)))


def psi_categorical(ref: pl.Series, cur: pl.Series) -> float:
    rf = ref.cast(pl.String).fill_null("__NULL__").value_counts(normalize=True, name="p")
    cf = cur.cast(pl.String).fill_null("__NULL__").value_counts(normalize=True, name="p")
    name = rf.columns[0]
    j = rf.join(cf, on=name, how="full", coalesce=True, suffix="_c").fill_null(0.0)
    r = np.clip(j["p"].to_numpy(), EPS, None)
    c = np.clip(j["p_c"].to_numpy(), EPS, None)
    return float(np.sum((c - r) * np.log(c / r)))


def _status(value: float, alert: float, warn: float | None = None) -> str:
    if value is None or np.isnan(value):
        return "n/a"
    if abs(value) >= alert:
        return "alert"
    if warn is not None and abs(value) >= warn:
        return "warn"
    return "ok"


def _pct_change(ref: float | None, cur: float | None) -> float:
    if ref is None or cur is None or ref == 0:
        return float("nan")
    return 100.0 * (cur - ref) / abs(ref)


def compare(ref: pl.DataFrame, cur: pl.DataFrame, cfg: dict, seed: int = 42) -> list[dict]:
    out: list[dict] = []

    def add(column, metric, value, threshold, status):
        out.append({"column_name": column, "metric": metric,
                    "value": None if value is None or (isinstance(value, float) and np.isnan(value)) else float(value),
                    "threshold": threshold, "status": status})

    vol = _pct_change(ref.height, cur.height)
    add("__table__", "volume_change_pct", vol, cfg["volume_alert_pct"], _status(vol, cfg["volume_alert_pct"]))

    n = cfg["sample_size"]
    rs = ref.sample(min(n, ref.height), seed=seed) if ref.height else ref
    cs = cur.sample(min(n, cur.height), seed=seed) if cur.height else cur

    for col in cfg["numeric_columns"]:
        if col not in ref.columns or col not in cur.columns:
            continue
        r = rs[col].cast(pl.Float64).to_numpy()
        c = cs[col].cast(pl.Float64).to_numpy()
        psi = psi_numeric(r, c, cfg["psi_bins"])
        add(col, "psi", psi, cfg["psi_alert"], _status(psi, cfg["psi_alert"], cfg["psi_warn"]))
        rn, cn = r[~np.isnan(r)], c[~np.isnan(c)]
        if len(rn) and len(cn):
            ks = stats.ks_2samp(rn, cn)
            add(col, "ks_statistic", ks.statistic, cfg["ks_alert"], _status(ks.statistic, cfg["ks_alert"]))
            add(col, "ks_pvalue", ks.pvalue, None, "info")
        rmean, rstd = ref[col].mean(), ref[col].std()
        # % shift is meaningless when the reference is ~0 relative to its spread -> reported as n/a
        tiny = rmean is None or rstd is None or abs(rmean) < 0.05 * max(rstd, 1e-12)
        ms = _pct_change(rmean, cur[col].mean())
        add(col, "mean_shift_pct", ms, cfg["mean_shift_alert_pct"],
            "n/a" if tiny else _status(ms, cfg["mean_shift_alert_pct"]))
        smd = (cur[col].mean() - rmean) / rstd if rstd else float("nan")
        add(col, "mean_shift_std", smd, cfg["std_mean_shift_alert"], _status(smd, cfg["std_mean_shift_alert"]))
        rmed = ref[col].median()
        md = _pct_change(rmed, cur[col].median())
        add(col, "median_shift_pct", md, cfg["mean_shift_alert_pct"],
            "n/a" if tiny or not rmed else _status(md, cfg["mean_shift_alert_pct"]))

    for col in cfg["numeric_columns"] + cfg["categorical_columns"]:
        if col not in ref.columns or col not in cur.columns:
            continue
        dn = 100.0 * (cur[col].null_count() / max(cur.height, 1) - ref[col].null_count() / max(ref.height, 1))
        add(col, "null_rate_change_pp", dn, cfg["null_rate_alert_pp"], _status(dn, cfg["null_rate_alert_pp"]))

    for col in cfg["categorical_columns"]:
        if col not in ref.columns or col not in cur.columns:
            continue
        psi = psi_categorical(ref[col], cur[col])
        add(col, "psi", psi, cfg["psi_alert"], _status(psi, cfg["psi_alert"], cfg["psi_warn"]))
        cc = _pct_change(ref[col].n_unique(), cur[col].n_unique())
        # share of current rows whose category never appeared in the reference partition
        known = ref[col].drop_nulls().unique().implode()
        new_share = cur.select((~pl.col(col).is_in(known) & pl.col(col).is_not_null()).mean()).item() or 0.0
        add(col, "new_category_share_pct", 100 * new_share, None, "info")
        status = _status(cc, cfg["cardinality_alert_pct"])
        if status == "alert" and 100 * new_share < cfg["min_new_category_share_pct"]:
            status = "warn"  # a handful of rows in a new category must not page anyone (measured: 1 row)
        add(col, "cardinality_change_pct", cc, cfg["cardinality_alert_pct"], status)
    return out
