"""Residual models: train, select, calibrate, register, score, monitor.

Idea: a trip whose fare (or distance) is far from what the rest of the record implies is suspicious even
when every value is individually valid — the "plausible" errors that rules cannot express.

Protocol (out-of-time, no shuffling across months):
    train       yellow_2024-11   fit every candidate
    validation  yellow_2024-12   model selection + flag-threshold calibration
    test        yellow_2025-01+  reported once, never used for any decision

A record is flagged when  |ln((actual + floor) / (predicted + floor))|  exceeds the validation quantile
`1 - ALPHA`. The same ALPHA is used for every model: it is a review budget fixed in advance, not a value
tuned on the benchmark. Flags feed the investigation queue; they never quarantine.
"""

from __future__ import annotations

import hashlib
import io
import json
import platform
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import polars as pl
import sklearn
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LinearRegression
from sklearn.model_selection import KFold
from sklearn.pipeline import Pipeline, make_pipeline
from sklearn.preprocessing import TargetEncoder

from dqc import config, db, pipeline
from dqc.ml import features as F
from dqc.ml.features import ModelSpec

MODELS_DIR = config.ROOT / "models"
ALPHA = 0.005                 # review budget: share of validation records above the flag threshold
ALPHA_GRID = (0.001, 0.002, 0.005, 0.01, 0.02)   # operating points reported for the precision/recall curve
SEED = 42
SEARCH_CONFIGS = 10           # seeded random search over gradient-boosting hyper-parameters
SELECTION_TOLERANCE = 0.01    # candidates within 1% of the best validation MAE are considered equivalent
RF_TRAIN_ROWS = 200_000
RETRAIN_MAE_RATIO = 1.25      # monitoring: test MAE > 1.25 x validation MAE -> retraining recommended
BOOTSTRAP = 500


# --------------------------------------------------------------------------- candidates
class MedianBaseline:
    def fit(self, x, y):
        self.value_ = float(np.median(y))
        return self

    def predict(self, x):
        return np.full(len(x), self.value_)


class SubsampledForest:
    """Random forest on the first RF_TRAIN_ROWS rows (already a random sample): a different model family."""

    def fit(self, x, y):
        self.model_ = RandomForestRegressor(n_estimators=100, max_depth=18, min_samples_leaf=5, n_jobs=-1,
                                            random_state=SEED).fit(x[:RF_TRAIN_ROWS], y[:RF_TRAIN_ROWS])
        return self

    def predict(self, x):
        return self.model_.predict(x)


def _hgb(spec: ModelSpec, **kw) -> Pipeline:
    enc = TargetEncoder(cv=KFold(5, shuffle=True, random_state=SEED))
    return make_pipeline(ColumnTransformer([("zones", enc, spec.zone_idx)], remainder="passthrough"),
                         HistGradientBoostingRegressor(random_state=SEED, **kw))


def search_space(n: int = SEARCH_CONFIGS) -> list[dict]:
    rng = np.random.default_rng(SEED)
    out = []
    for _ in range(n):
        out.append({"learning_rate": float(rng.choice([0.05, 0.1, 0.2])), "max_iter": int(rng.choice([300, 600, 1000])),
                    "max_leaf_nodes": int(rng.choice([31, 63, 127, 255])),
                    "min_samples_leaf": int(rng.choice([20, 50, 200])),
                    "l2_regularization": float(rng.choice([0.0, 1.0, 10.0]))})
    return out


def candidates(spec: ModelSpec = F.FARE, search: int = SEARCH_CONFIGS) -> dict:
    out: dict = {"baseline_median": MedianBaseline()}
    lin = [i for i, f in enumerate(spec.features) if f in ("trip_distance", "trip_duration_min")]
    out["baseline_linear"] = make_pipeline(ColumnTransformer([("keep", "passthrough", lin)]), LinearRegression())
    out["random_forest"] = SubsampledForest()
    out["hgb_default"] = _hgb(spec, learning_rate=0.1, max_iter=400, max_leaf_nodes=63)
    for i, kw in enumerate(search_space(search)):
        out[f"hgb_search_{i:02d}"] = _hgb(spec, **kw)
    return out


def metrics(y: np.ndarray, pred: np.ndarray) -> dict:
    err = y - pred
    ss_tot = float(((y - y.mean()) ** 2).sum())
    return {"n": int(len(y)), "mae": float(np.abs(err).mean()), "rmse": float(np.sqrt((err ** 2).mean())),
            "median_ae": float(np.median(np.abs(err))),
            "r2": float(1 - (err ** 2).sum() / ss_tot) if ss_tot else float("nan")}


def bootstrap_ci(values: np.ndarray, n_boot: int = BOOTSTRAP, max_bootstrap_n: int = 200_000, seed: int = SEED) -> list[float]:
    """95% interval for the mean of `values` (e.g. absolute errors -> MAE), on the SAME rows as the point estimate.

    Percentile bootstrap up to `max_bootstrap_n` rows; above that the bootstrap distribution of a mean is
    indistinguishable from the normal approximation mean +/- 1.96 * sd / sqrt(n), which is used instead.
    """
    v = np.asarray(values, dtype=float)
    if len(v) > max_bootstrap_n:
        half = 1.96 * v.std(ddof=1) / np.sqrt(len(v))
        return [float(v.mean() - half), float(v.mean() + half)]
    rng = np.random.default_rng(seed)
    means = np.array([v[rng.integers(0, len(v), len(v))].mean() for _ in range(n_boot)])
    return [float(np.quantile(means, 0.025)), float(np.quantile(means, 0.975))]


def relative_deviation(y: np.ndarray, pred: np.ndarray, floor: float = F.FARE.floor) -> np.ndarray:
    """Symmetric log-ratio |ln((actual + floor) / (predicted + floor))|.

    The first version used |actual - predicted| / max(predicted, floor): it is bounded by 1 when the value is
    too LOW, so under-charged trips could never be flagged (measured recall 0.00). The log-ratio treats
    "x times too high" and "x times too low" alike.
    """
    return np.abs(np.log((np.maximum(y, 0.0) + floor) / (np.maximum(pred, 0.0) + floor)))


def _size_bytes(est) -> int:
    buf = io.BytesIO()
    joblib.dump(est, buf, compress=3)
    return buf.getbuffer().nbytes


# --------------------------------------------------------------------------- registry
@dataclass
class LoadedModel:
    model: object
    meta: dict

    @property
    def spec(self) -> ModelSpec:
        return F.SPECS[self.meta["model_name"]]

    @property
    def version(self) -> int:
        return self.meta["version"]

    @property
    def threshold(self) -> float:
        return self.meta["flag_threshold"]

    def predict(self, x: np.ndarray) -> np.ndarray:
        return self.model.predict(x)

    def score_frame(self, df: pl.DataFrame, threshold: float | None = None) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """(prediction, log-ratio deviation, flag) for a frame that has the features and the target."""
        spec = self.spec
        pred = self.predict(F.matrix(df, spec))
        y = df[spec.target].cast(pl.Float64).fill_null(np.nan).to_numpy()
        dev = relative_deviation(y, pred, spec.floor)
        return pred, dev, np.nan_to_num(dev, nan=np.inf) > (self.threshold if threshold is None else threshold)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def latest_version(name: str = F.FARE.name, models_dir: Path = MODELS_DIR) -> int | None:
    vs = sorted(int(p.stem.rsplit("_v", 1)[1]) for p in models_dir.glob(f"{name}_v*.json"))
    return vs[-1] if vs else None


def load(name: str = F.FARE.name, version: int | None = None, models_dir: Path = MODELS_DIR) -> LoadedModel | None:
    version = version or latest_version(name, models_dir)
    if version is None:
        return None
    meta = json.loads((models_dir / f"{name}_v{version}.json").read_text(encoding="utf-8"))
    artifact = models_dir / meta["artifact"]
    if not artifact.exists():
        return None
    if _sha256(artifact) != meta["artifact_sha256"]:
        raise RuntimeError(f"{artifact} does not match the registered sha256 — refusing to load")
    return LoadedModel(joblib.load(artifact), meta)


def register(meta: dict, dsn: str | None = None) -> None:
    with db.connect(dsn) as conn:
        conn.execute(
            """INSERT INTO dq.model_registry (model_name, version, created_at, target, algorithm, params, features,
                   train_partition, validation_partition, train_rows, train_data_sha256, selection, validation_metrics,
                   backtest, flag_threshold, alpha, artifact, artifact_sha256, environment)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT (model_name, version) DO NOTHING""",
            (meta["model_name"], meta["version"], meta["created_at"], meta["target"], meta["algorithm"],
             json.dumps(meta["params"]), json.dumps(meta["features"]), meta["train_partition"],
             meta["validation_partition"], meta["train_rows"], meta["train_data_sha256"],
             json.dumps(meta["selection"]), json.dumps(meta["validation_metrics"]), json.dumps(meta["backtest"]),
             meta["flag_threshold"], meta["alpha"], meta["artifact"], meta["artifact_sha256"],
             json.dumps(meta["environment"])))
        conn.commit()


# --------------------------------------------------------------------------- training
def fit_and_select(xtr, ytr, xva, yva, spec: ModelSpec = F.FARE, search: int = SEARCH_CONFIGS) -> tuple[str, object, dict]:
    """Fit every candidate on train and score it on the validation month.

    Selection rule (fixed before looking at any result): among the candidates whose validation MAE is within
    SELECTION_TOLERANCE of the best one, take the smallest serialised model. A 1% MAE difference is irrelevant
    for a detector, while a 100x larger artifact is a real serving cost.
    """
    table, fitted = {}, {}
    for name, est in candidates(spec, search).items():
        t = time.perf_counter()
        est.fit(xtr, ytr)
        fit_s = time.perf_counter() - t
        table[name] = {**metrics(yva, est.predict(xva)), "fit_s": round(fit_s, 2), "size_bytes": _size_bytes(est)}
        fitted[name] = est
    best_mae = min(v["mae"] for v in table.values())
    eligible = [k for k, v in table.items() if v["mae"] <= best_mae * (1 + SELECTION_TOLERANCE)]
    chosen = min(eligible, key=lambda k: (table[k]["size_bytes"], k))
    for k, v in table.items():
        v["within_tolerance"] = k in eligible
    return chosen, fitted[chosen], table


def backtest(spec: ModelSpec, estimator_name: str, partitions: list[str], sample: int = 300_000) -> list[dict]:
    """Rolling origin: fit the selected configuration on month t, evaluate on month t+1, for every pair."""
    frames = {p: F.valid_frame(p, sample, SEED) for p in partitions}
    out = []
    for a, b in zip(partitions, partitions[1:], strict=False):
        est = candidates(spec)[estimator_name].fit(F.matrix(frames[a], spec), frames[a][spec.target].to_numpy())
        y = frames[b][spec.target].to_numpy()
        pred = est.predict(F.matrix(frames[b], spec))
        out.append({"train": a, "evaluate": b, **metrics(y, pred), "mae_ci95": bootstrap_ci(np.abs(y - pred))})
    return out


def train(name: str = F.FARE.name, train_partition: str = "yellow_2024-11",
          validation_partition: str = "yellow_2024-12", train_sample: int = 500_000,
          validation_sample: int = 300_000, models_dir: Path = MODELS_DIR, dsn: str | None = None,
          register_in_db: bool = True, run_backtest: bool = True) -> dict:
    spec = F.SPECS[name]
    tr = F.valid_frame(train_partition, train_sample, SEED)
    va = F.valid_frame(validation_partition, validation_sample, SEED)
    xtr, ytr = F.matrix(tr, spec), tr[spec.target].to_numpy()
    xva, yva = F.matrix(va, spec), va[spec.target].to_numpy()

    best, model, table = fit_and_select(xtr, ytr, xva, yva, spec)
    pred = model.predict(xva)
    dev = relative_deviation(yva, pred, spec.floor)
    thresholds = {str(a): float(np.quantile(dev, 1 - a)) for a in ALPHA_GRID}

    rng = np.random.default_rng(SEED)
    idx = rng.choice(len(xva), size=min(20_000, len(xva)), replace=False)
    imp = permutation_importance(model, xva[idx], yva[idx], scoring="neg_mean_absolute_error", n_repeats=3,
                                 random_state=SEED)
    importance = {f: round(float(v), 4) for f, v in sorted(zip(spec.features, imp.importances_mean, strict=True),
                                                           key=lambda kv: -kv[1])}
    by_payment = (va.with_columns(abs_err=pl.Series(np.abs(yva - pred))).group_by("payment_type")
                  .agg(n=pl.len(), mae=pl.col("abs_err").mean()).sort("payment_type").to_dicts())

    models_dir.mkdir(parents=True, exist_ok=True)
    buf = io.BytesIO()
    joblib.dump(model, buf, compress=3)
    payload = buf.getvalue()
    current = load(name, models_dir=models_dir)
    unchanged = current is not None and current.meta["artifact_sha256"] == hashlib.sha256(payload).hexdigest()
    # Deterministic retraining that reproduces the registered model byte for byte keeps its version;
    # only the evaluation metadata is refreshed.
    version = current.version if unchanged else (latest_version(name, models_dir) or 0) + 1
    artifact = models_dir / f"{name}_v{version}.joblib"
    if not unchanged:
        artifact.write_bytes(payload)
    reg = model.steps[-1][1] if hasattr(model, "steps") else model
    keep = ("loss", "learning_rate", "max_iter", "max_leaf_nodes", "min_samples_leaf", "l2_regularization",
            "random_state")
    all_parts = [s.partition_id for s in pipeline.manifest_sources()]
    meta = {
        "model_name": name, "version": version, "target": spec.target, "unit": spec.unit,
        "created_at": (current.meta["created_at"] if unchanged else
                       datetime.now(timezone.utc).isoformat(timespec="seconds")),
        "algorithm": f"{best} ({type(reg).__name__})",
        "params": {k: v for k, v in getattr(reg, "get_params", dict)().items() if k in keep},
        "features": list(spec.features),
        "train_partition": train_partition, "validation_partition": validation_partition,
        "train_rows": int(len(xtr)), "validation_rows": int(len(xva)),
        "train_data_sha256": next(s.sha256 for s in pipeline.manifest_sources() if s.partition_id == train_partition),
        "selection_rule": f"smallest artifact among candidates within {SELECTION_TOLERANCE:.0%} of the best validation MAE",
        "selection": table, "selected": best,
        "validation_metrics": {**table[best], "mae_ci95": bootstrap_ci(np.abs(yva - pred))},
        "validation_mae_by_payment_type": by_payment,
        "permutation_importance_mae": importance,
        "backtest": backtest(spec, best, all_parts) if run_backtest else [],
        "flag_threshold": thresholds[str(ALPHA)], "alpha": ALPHA, "threshold_by_alpha": thresholds,
        "log_ratio_floor": spec.floor,
        "artifact": artifact.name, "artifact_sha256": _sha256(artifact),
        "environment": {"python": platform.python_version(), "scikit_learn": sklearn.__version__,
                        "numpy": np.__version__, "seed": SEED},
    }
    (models_dir / f"{name}_v{version}.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    if register_in_db:
        register(meta, dsn)
    return {**meta, "unchanged": unchanged}


# --------------------------------------------------------------------------- batch scoring + monitoring
def score_partitions(name: str = F.FARE.name, version: int | None = None, top_n: int = 500,
                     dsn: str | None = None) -> list[dict]:
    """Score every real partition; persist per-partition performance and the top flagged records."""
    lm = load(name, version)
    if lm is None:
        raise RuntimeError(f"no trained {name}: run `python -m dqc ml train` first")
    spec = lm.spec
    val_mae = lm.meta["validation_metrics"]["mae"]
    out = []
    with db.connect(dsn) as conn:
        register(lm.meta, dsn)
        conn.execute("DELETE FROM dq.model_metrics WHERE model_name=%s AND version=%s", (name, lm.version))
        conn.execute("DELETE FROM dq.model_flags WHERE model_name=%s AND version=%s", (name, lm.version))
        for src in pipeline.manifest_sources():
            pid = src.partition_id
            split = ("train" if pid == lm.meta["train_partition"] else
                     "validation" if pid == lm.meta["validation_partition"] else "test")
            t = time.perf_counter()
            df = F.valid_frame(pid)
            pred, dev, flag = lm.score_frame(df)
            y = df[spec.target].to_numpy()
            m = metrics(y, pred)
            by_pt = (df.with_columns(abs_err=pl.Series(np.abs(y - pred)), flag=pl.Series(flag))
                     .group_by("payment_type").agg(n=pl.len(), mae=pl.col("abs_err").mean(),
                                                   flag_rate=pl.col("flag").mean()).sort("payment_type").to_dicts())
            ci = bootstrap_ci(np.abs(y - pred))
            ratio = m["mae"] / val_mae
            row = {"model_name": name, "version": lm.version, "partition_id": pid, "split": split, **m,
                   "mae_ci_low": ci[0], "mae_ci_high": ci[1],
                   "flagged": int(flag.sum()), "flag_rate": float(flag.mean()), "mae_vs_validation": ratio,
                   "status": "retrain_recommended" if split == "test" and ratio > RETRAIN_MAE_RATIO else "ok",
                   "by_payment_type": by_pt, "scoring_s": round(time.perf_counter() - t, 2)}
            db.insert_dicts(conn, "dq.model_metrics", [row])
            top = np.argsort(-dev)[:top_n]
            top = top[flag[top]]
            if len(top):
                sub = df[top.tolist()].select("record_id", *spec.features, spec.target).with_columns(
                    pl.Series("predicted_value", pred[top]), pl.Series("log_ratio", dev[top]))
                db.copy_df(conn, "dq.model_flags", sub.select(
                    pl.lit(name).alias("model_name"), pl.lit(lm.version).alias("version"),
                    pl.lit(pid).alias("partition_id"), "record_id", pl.col(spec.target).alias("actual_value"),
                    "predicted_value", "log_ratio", pl.struct(spec.features).struct.json_encode().alias("features")))
            conn.commit()
            out.append(row)
    return out
