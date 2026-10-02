"""Statistical anomaly detection — runs AFTER deterministic rules, on rule-valid records only.

Anomaly detectors flag *unusual* records, not *wrong* records. They never quarantine:
their output is an investigation queue. See README "Why anomaly detection is not a rule".
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import numpy as np
import polars as pl
from sklearn.ensemble import IsolationForest


@dataclass
class DetectorResult:
    method: str
    flags: np.ndarray            # bool per row
    scores: np.ndarray           # higher = more anomalous
    runtime_s: float
    params: dict
    per_feature: dict | None = None


def _matrix(df: pl.DataFrame, features: list[str]) -> np.ndarray:
    return df.select([pl.col(f).cast(pl.Float64).fill_null(0.0) for f in features]).to_numpy()


def iqr(df: pl.DataFrame, features: list[str], k: float = 3.0, log_transform: bool = False) -> DetectorResult:
    """Tukey fences. `log_transform` applies sign(x)*log1p(|x|) first: taxi amounts/distances are
    heavily right-skewed, and plain fences flag every airport trip (measured: README)."""
    t = time.perf_counter()
    x = _matrix(df, features)
    if log_transform:
        x = np.sign(x) * np.log1p(np.abs(x))
    q1, q3 = np.nanpercentile(x, 25, axis=0), np.nanpercentile(x, 75, axis=0)
    spread = q3 - q1
    lo, hi = q1 - k * spread, q3 + k * spread
    out = (x < lo) | (x > hi)
    dist = np.maximum(lo - x, x - hi) / np.where(spread > 0, spread, 1.0)
    # zero-inflated features (Q1 == Q3, e.g. tolls) have no spread: every non-zero value would be an
    # "outlier", so they are excluded instead of silently flagging them.
    usable = spread > 0
    out = out & usable
    dist = np.where(usable, dist, -np.inf)
    per = {f: (int(out[:, i].sum()) if usable[i] else "skipped_zero_iqr") for i, f in enumerate(features)}
    fences = {"lower": lo, "upper": hi}
    if log_transform:
        fences = {k2: np.sign(v) * np.expm1(np.abs(v)) for k2, v in fences.items()}
    return DetectorResult("iqr_log" if log_transform else "iqr", out.any(axis=1), np.max(dist, axis=1),
                          time.perf_counter() - t,
                          {"k": k, "log_transform": log_transform, "features": features,
                           "lower": fences["lower"].round(3).tolist(), "upper": fences["upper"].round(3).tolist()},
                          per)


def zscore(df: pl.DataFrame, features: list[str], threshold: float = 4.0) -> DetectorResult:
    t = time.perf_counter()
    x = _matrix(df, features)
    mu, sd = x.mean(axis=0), x.std(axis=0)
    z = np.abs((x - mu) / np.where(sd > 0, sd, 1.0))
    out = z > threshold
    per = {f: int(out[:, i].sum()) for i, f in enumerate(features)}
    return DetectorResult("zscore", out.any(axis=1), z.max(axis=1), time.perf_counter() - t,
                          {"threshold": threshold}, per)


def isolation_forest(df: pl.DataFrame, features: list[str], train_sample: int = 200_000,
                     n_estimators: int = 100, contamination: float = 0.01, random_state: int = 42,
                     model: IsolationForest | None = None) -> tuple[DetectorResult, IsolationForest]:
    t = time.perf_counter()
    x = _matrix(df, features)
    if model is None:
        rng = np.random.default_rng(random_state)
        idx = rng.choice(len(x), size=min(train_sample, len(x)), replace=False)
        model = IsolationForest(n_estimators=n_estimators, contamination=contamination,
                                random_state=random_state, n_jobs=-1).fit(x[idx])
    fit_s = time.perf_counter() - t
    scores = -model.score_samples(x)  # higher = more anomalous
    flags = scores > -model.offset_  # identical to model.predict(x) == -1, without scoring twice
    return DetectorResult("isolation_forest", flags, scores, time.perf_counter() - t,
                          {"n_estimators": n_estimators, "contamination": contamination,
                           "train_sample": min(train_sample, len(x)), "fit_s": round(fit_s, 3)}), model
