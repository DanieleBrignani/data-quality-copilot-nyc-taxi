"""Fare-model tests: feature contract, leakage guard, selection, calibration, registry integrity, serving."""

from __future__ import annotations

import json
from datetime import datetime, timedelta

import numpy as np
import polars as pl
import pytest

from dqc.ml import fare_model
from dqc.ml import features as F
from tests.conftest import trips_frame, valid_trip


def _synthetic(n: int, seed: int = 0) -> pl.DataFrame:
    """Meter-like fares: 3 + 2.5/mile + 0.5/min + noise. Controlled fixture, not benchmark data."""
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(n):
        dist, dur = float(rng.uniform(0.5, 15)), float(rng.uniform(3, 50))
        p = datetime(2025, 1, 6, 8) + timedelta(minutes=5 * i)
        rows.append(valid_trip(trip_distance=dist, tpep_pickup_datetime=p,
                               tpep_dropoff_datetime=p + timedelta(minutes=dur),
                               fare_amount=round(3 + 2.5 * dist + 0.5 * dur + float(rng.normal(0, 0.5)), 2),
                               PULocationID=int(rng.integers(1, 30)), DOLocationID=int(rng.integers(1, 30))))
    return F.add_features(trips_frame(rows))


def test_feature_contract_has_no_target_or_monetary_leakage():
    assert not set(F.FEATURES) & F.FORBIDDEN
    assert F.TARGET not in F.FEATURES


def test_matrix_shape_order_and_missing_encoding():
    df = F.add_features(trips_frame([valid_trip(passenger_count=None, RatecodeID=None)]))
    x = F.matrix(df)
    assert x.shape == (1, len(F.FEATURES))
    assert x[0, F.FEATURES.index("passenger_count")] == F.MISSING
    assert x[0, F.FEATURES.index("trip_duration_min")] == 20.0
    assert x[0, F.FEATURES.index("pickup_hour")] == 8


def test_relative_deviation_is_symmetric_and_handles_low_fares():
    hi = fare_model.relative_deviation(np.array([95.0]), np.array([5.0]))[0]
    lo = fare_model.relative_deviation(np.array([5.0]), np.array([95.0]))[0]
    assert hi == pytest.approx(lo)                       # 10x too high == 10x too low
    assert fare_model.relative_deviation(np.array([20.0]), np.array([20.0]))[0] == 0.0
    assert np.isfinite(fare_model.relative_deviation(np.array([-3.0]), np.array([10.0]))[0])


def test_selection_picks_a_learned_model_over_the_baselines():
    tr, va = _synthetic(1500, 1), _synthetic(500, 2)
    best, model, table = fare_model.fit_and_select(F.matrix(tr), tr[F.TARGET].to_numpy(),
                                                   F.matrix(va), va[F.TARGET].to_numpy())
    assert set(table) == set(fare_model.candidates())
    assert table[best]["mae"] == min(v["mae"] for v in table.values())
    assert table[best]["mae"] < table["baseline_median"]["mae"] / 5
    assert not best.startswith("baseline_median")


@pytest.fixture
def registered(tmp_path):
    tr, va = _synthetic(1500, 1), _synthetic(500, 2)
    _, model, table = fare_model.fit_and_select(F.matrix(tr), tr[F.TARGET].to_numpy(),
                                                F.matrix(va), va[F.TARGET].to_numpy())
    import joblib
    artifact = tmp_path / "fare_model_v1.joblib"
    joblib.dump(model, artifact)
    dev = fare_model.relative_deviation(va[F.TARGET].to_numpy(), model.predict(F.matrix(va)))
    meta = {"model_name": "fare_model", "version": 1, "flag_threshold": float(np.quantile(dev, 0.995)),
            "artifact": artifact.name, "artifact_sha256": fare_model._sha256(artifact),
            "validation_metrics": {"mae": 0.5}}
    (tmp_path / "fare_model_v1.json").write_text(json.dumps(meta))
    return tmp_path, va


def test_registry_roundtrip_and_threshold_calibration(registered):
    models_dir, va = registered
    lm = fare_model.load(models_dir=models_dir)
    assert lm.version == 1 and fare_model.latest_version(models_dir) == 1
    _, _, flag = lm.score_frame(va)
    assert 0.0 <= flag.mean() <= 0.02            # ~alpha of the calibration set, by construction


def test_detector_flags_decimal_shift_and_missing_fare(registered):
    models_dir, va = registered
    lm = fare_model.load(models_dir=models_dir)
    bad = va.head(50).with_columns(fare_amount=pl.col("fare_amount") * 10)
    assert lm.score_frame(bad)[2].all()
    assert lm.score_frame(va.head(5).with_columns(fare_amount=pl.lit(None, pl.Float64)))[2].all()


def test_tampered_artifact_is_refused(registered):
    models_dir, _ = registered
    with open(models_dir / "fare_model_v1.joblib", "ab") as fh:
        fh.write(b"x")
    with pytest.raises(RuntimeError, match="sha256"):
        fare_model.load(models_dir=models_dir)


def test_predict_endpoint(registered, monkeypatch):
    from fastapi.testclient import TestClient

    import api.main as api_main

    models_dir, _ = registered
    lm = fare_model.load(models_dir=models_dir)
    monkeypatch.setattr(api_main, "_model", lambda: lm)
    client = TestClient(api_main.app)
    trip = {"trip_distance": 4.0, "pickup_datetime": "2025-01-06T08:00:00", "dropoff_datetime": "2025-01-06T08:20:00",
            "PULocationID": 5, "DOLocationID": 9, "RatecodeID": 1, "VendorID": 2, "payment_type": 1,
            "passenger_count": 1}
    r = client.post("/predict/fare", json=trip).json()
    assert r["predicted_fare"] == pytest.approx(3 + 2.5 * 4 + 0.5 * 20, abs=3.0)
    assert client.post("/predict/fare", json={**trip, "fare_amount": r["predicted_fare"]}).json()["flagged"] is False
    assert client.post("/predict/fare", json={**trip, "fare_amount": 900.0}).json()["flagged"] is True
    bad = {**trip, "dropoff_datetime": "2025-01-06T07:00:00"}
    assert client.post("/predict/fare", json=bad).status_code == 422
