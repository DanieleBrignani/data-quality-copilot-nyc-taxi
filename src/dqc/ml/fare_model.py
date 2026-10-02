"""Expected-fare model: train, select, calibrate, register, score, monitor.

Idea: a trip whose fare is far from what distance, duration, zones and rate code imply is suspicious
even when every value is individually valid — exactly the "plausible" errors the rules cannot express.

Protocol (out-of-time, no shuffling across months):
    train       yellow_2024-11   fit candidates
    validation  yellow_2024-12   model selection + flag-threshold calibration
    test        yellow_2025-01+  reported once, never used for any decision

The detector flags a record when  |ln((fare + FLOOR) / (predicted + FLOOR))|  exceeds the validation
quantile `1 - alpha`. Like every statistical detector in this project it feeds the investigation
queue; it never quarantines.
"""

from __future__ import annotations

import hashlib
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
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LinearRegression
from sklearn.model_selection import KFold
from sklearn.pipeline import Pipeline, make_pipeline
from sklearn.preprocessing import TargetEncoder

from dqc import config, db, pipeline
from dqc.ml import features as F

MODELS_DIR = config.ROOT / "models"
MODEL_NAME = "fare_model"
FLOOR = 5.0          # $: keeps the log-ratio stable on very small fares
ALPHA = 0.005        # share of validation records above the flag threshold, by construction
SEED = 42
RETRAIN_MAE_RATIO = 1.25   # monitoring: test MAE > 1.25 x validation MAE -> retraining recommended


# --------------------------------------------------------------------------- candidates
class MedianBaseline:
    def fit(self, x, y):
        self.value_ = float(np.median(y))
        return self

    def predict(self, x):
        return np.full(len(x), self.value_)


def _hgb(**kw) -> Pipeline:
    enc = TargetEncoder(cv=KFold(5, shuffle=True, random_state=SEED))
    return make_pipeline(ColumnTransformer([("zones", enc, F.ZONE_IDX)], remainder="passthrough"),
                         HistGradientBoostingRegressor(random_state=SEED, **kw))


def candidates() -> dict:
    lin_cols = [F.FEATURES.index("trip_distance"), F.FEATURES.index("trip_duration_min")]
    return {
        "baseline_median": MedianBaseline(),
        "baseline_linear_distance_duration": make_pipeline(
            ColumnTransformer([("keep", "passthrough", lin_cols)]), LinearRegression()),
        "hgb_small": _hgb(learning_rate=0.1, max_iter=200, max_leaf_nodes=31),
        "hgb_large": _hgb(learning_rate=0.1, max_iter=400, max_leaf_nodes=63),
        "hgb_large_l1": _hgb(loss="absolute_error", learning_rate=0.1, max_iter=400, max_leaf_nodes=63),
    }


def metrics(y: np.ndarray, pred: np.ndarray) -> dict:
    err = y - pred
    ss_tot = float(((y - y.mean()) ** 2).sum())
    return {"n": int(len(y)), "mae": float(np.abs(err).mean()), "rmse": float(np.sqrt((err ** 2).mean())),
            "median_ae": float(np.median(np.abs(err))),
            "r2": float(1 - (err ** 2).sum() / ss_tot) if ss_tot else float("nan")}


def relative_deviation(y: np.ndarray, pred: np.ndarray) -> np.ndarray:
    """Symmetric log-ratio |ln((fare + FLOOR) / (predicted + FLOOR))|.

    The first version used |fare - predicted| / max(predicted, FLOOR): it is bounded by 1 when the fare is
    too LOW, so under-charged trips (e.g. distance x5 with an unchanged fare) could never be flagged
    (measured recall 0.00). The log-ratio treats "x times too high" and "x times too low" alike.
    """
    return np.abs(np.log((np.maximum(y, 0.0) + FLOOR) / (np.maximum(pred, 0.0) + FLOOR)))


# --------------------------------------------------------------------------- registry
@dataclass
class LoadedModel:
    model: object
    meta: dict

    @property
    def version(self) -> int:
        return self.meta["version"]

    @property
    def threshold(self) -> float:
        return self.meta["flag_threshold"]

    def predict(self, x: np.ndarray) -> np.ndarray:
        return self.model.predict(x)

    def score_frame(self, df: pl.DataFrame) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """(predicted fare, relative deviation, flag) for a frame that has features + fare_amount."""
        pred = self.predict(F.matrix(df))
        y = df[F.TARGET].cast(pl.Float64).fill_null(np.nan).to_numpy()
        dev = relative_deviation(y, pred)
        return pred, dev, np.nan_to_num(dev, nan=np.inf) > self.threshold


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def latest_version(models_dir: Path = MODELS_DIR) -> int | None:
    vs = sorted(int(p.stem.rsplit("_v", 1)[1]) for p in models_dir.glob(f"{MODEL_NAME}_v*.json"))
    return vs[-1] if vs else None


def load(version: int | None = None, models_dir: Path = MODELS_DIR) -> LoadedModel | None:
    version = version or latest_version(models_dir)
    if version is None:
        return None
    meta = json.loads((models_dir / f"{MODEL_NAME}_v{version}.json").read_text(encoding="utf-8"))
    artifact = models_dir / meta["artifact"]
    if not artifact.exists():
        return None
    if _sha256(artifact) != meta["artifact_sha256"]:
        raise RuntimeError(f"{artifact} does not match the registered sha256 — refusing to load")
    return LoadedModel(joblib.load(artifact), meta)


def register(meta: dict, dsn: str | None = None) -> None:
    with db.connect(dsn) as conn:
        conn.execute(
            """INSERT INTO dq.model_registry (model_name, version, created_at, algorithm, params, features,
                   train_partition, validation_partition, train_rows, train_data_sha256, selection, validation_metrics,
                   flag_threshold, alpha, artifact, artifact_sha256, environment)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT (model_name, version) DO NOTHING""",
            (MODEL_NAME, meta["version"], meta["created_at"], meta["algorithm"], json.dumps(meta["params"]),
             json.dumps(meta["features"]), meta["train_partition"], meta["validation_partition"], meta["train_rows"],
             meta["train_data_sha256"], json.dumps(meta["selection"]), json.dumps(meta["validation_metrics"]),
             meta["flag_threshold"], meta["alpha"], meta["artifact"], meta["artifact_sha256"],
             json.dumps(meta["environment"])))
        conn.commit()


# --------------------------------------------------------------------------- training
def fit_and_select(xtr, ytr, xva, yva) -> tuple[str, object, dict]:
    """Fit every candidate on train, pick the lowest validation MAE. Returns (name, model, table)."""
    table, fitted = {}, {}
    for name, est in candidates().items():
        t = time.perf_counter()
        est.fit(xtr, ytr)
        table[name] = {**metrics(yva, est.predict(xva)), "fit_s": round(time.perf_counter() - t, 2)}
        fitted[name] = est
    best = min(table, key=lambda k: table[k]["mae"])
    return best, fitted[best], table


def train(train_partition: str = "yellow_2024-11", validation_partition: str = "yellow_2024-12",
          train_sample: int = 500_000, validation_sample: int = 300_000, models_dir: Path = MODELS_DIR,
          dsn: str | None = None, register_in_db: bool = True) -> dict:
    tr = F.valid_frame(train_partition, train_sample, SEED)
    va = F.valid_frame(validation_partition, validation_sample, SEED)
    xtr, ytr = F.matrix(tr), tr[F.TARGET].to_numpy()
    xva, yva = F.matrix(va), va[F.TARGET].to_numpy()

    best, model, table = fit_and_select(xtr, ytr, xva, yva)
    pred = model.predict(xva)
    threshold = float(np.quantile(relative_deviation(yva, pred), 1 - ALPHA))

    rng = np.random.default_rng(SEED)
    idx = rng.choice(len(xva), size=min(20_000, len(xva)), replace=False)
    imp = permutation_importance(model, xva[idx], yva[idx], scoring="neg_mean_absolute_error", n_repeats=3,
                                 random_state=SEED)
    importance = {f: round(float(v), 4) for f, v in sorted(zip(F.FEATURES, imp.importances_mean, strict=True),
                                                           key=lambda kv: -kv[1])}
    by_payment = (va.with_columns(abs_err=pl.Series(np.abs(yva - pred))).group_by("payment_type")
                  .agg(n=pl.len(), mae=pl.col("abs_err").mean()).sort("payment_type").to_dicts())

    models_dir.mkdir(parents=True, exist_ok=True)
    version = (latest_version(models_dir) or 0) + 1
    artifact = models_dir / f"{MODEL_NAME}_v{version}.joblib"
    joblib.dump(model, artifact, compress=3)
    reg = model.steps[-1][1] if hasattr(model, "steps") else model
    meta = {
        "model_name": MODEL_NAME, "version": version,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "algorithm": f"{best} ({type(reg).__name__})",
        "params": {k: v for k, v in getattr(reg, "get_params", dict)().items()
                   if k in ("loss", "learning_rate", "max_iter", "max_leaf_nodes", "random_state")},
        "features": F.FEATURES, "target": F.TARGET,
        "train_partition": train_partition, "validation_partition": validation_partition,
        "train_rows": int(len(xtr)), "validation_rows": int(len(xva)),
        "train_data_sha256": next(s.sha256 for s in pipeline.manifest_sources()
                                  if s.partition_id == train_partition),
        "selection": table, "selected": best, "validation_metrics": table[best],
        "validation_mae_by_payment_type": by_payment,
        "permutation_importance_mae": importance,
        "flag_threshold": threshold, "alpha": ALPHA, "relative_deviation_floor": FLOOR,
        "artifact": artifact.name, "artifact_sha256": _sha256(artifact),
        "environment": {"python": platform.python_version(), "scikit_learn": sklearn.__version__,
                        "numpy": np.__version__, "seed": SEED},
    }
    (models_dir / f"{MODEL_NAME}_v{version}.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    if register_in_db:
        register(meta, dsn)
    return meta


# --------------------------------------------------------------------------- batch scoring + monitoring
def score_partitions(version: int | None = None, top_n: int = 500, dsn: str | None = None) -> list[dict]:
    """Score every real partition; persist per-partition performance and the top flagged records."""
    lm = load(version)
    if lm is None:
        raise RuntimeError("no trained model: run `python -m dqc ml train` first")
    val_mae = lm.meta["validation_metrics"]["mae"]
    out = []
    with db.connect(dsn) as conn:
        register(lm.meta, dsn)
        conn.execute("DELETE FROM dq.model_metrics WHERE model_name=%s AND version=%s", (MODEL_NAME, lm.version))
        conn.execute("DELETE FROM dq.model_flags WHERE model_name=%s AND version=%s", (MODEL_NAME, lm.version))
        for src in pipeline.manifest_sources():
            pid = src.partition_id
            split = ("train" if pid == lm.meta["train_partition"] else
                     "validation" if pid == lm.meta["validation_partition"] else "test")
            t = time.perf_counter()
            df = F.valid_frame(pid)
            pred, dev, flag = lm.score_frame(df)
            y = df[F.TARGET].to_numpy()
            m = metrics(y, pred)
            by_pt = (df.with_columns(abs_err=pl.Series(np.abs(y - pred)), flag=pl.Series(flag))
                     .group_by("payment_type").agg(n=pl.len(), mae=pl.col("abs_err").mean(),
                                                   flag_rate=pl.col("flag").mean()).sort("payment_type").to_dicts())
            ratio = m["mae"] / val_mae
            row = {"model_name": MODEL_NAME, "version": lm.version, "partition_id": pid, "split": split, **m,
                   "flagged": int(flag.sum()), "flag_rate": float(flag.mean()), "mae_vs_validation": ratio,
                   "status": "retrain_recommended" if split == "test" and ratio > RETRAIN_MAE_RATIO else "ok",
                   "by_payment_type": by_pt, "scoring_s": round(time.perf_counter() - t, 2)}
            db.insert_dicts(conn, "dq.model_metrics", [row])
            top = np.argsort(-dev)[:top_n]
            top = top[flag[top]]
            if len(top):
                sub = df[top.tolist()].select("record_id", *F.FEATURES, F.TARGET).with_columns(
                    pl.Series("predicted_fare", pred[top]), pl.Series("relative_deviation", dev[top]))
                db.copy_df(conn, "dq.model_flags", sub.select(
                    pl.lit(MODEL_NAME).alias("model_name"), pl.lit(lm.version).alias("version"),
                    pl.lit(pid).alias("partition_id"), "record_id", F.TARGET, "predicted_fare", "relative_deviation",
                    pl.struct(F.FEATURES).struct.json_encode().alias("features")))
            conn.commit()
            out.append(row)
    return out
