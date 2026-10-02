import json

import polars as pl
import pytest

from dqc import config, gate

CFG = {"max_score_drop": 2.0, "max_valid_rate_drop_pp": 2.0}


@pytest.fixture(scope="module")
def sample():
    if not gate.SAMPLE_PATH.exists():
        pytest.skip("committed CI sample missing")
    return pl.read_parquet(gate.SAMPLE_PATH)


@pytest.fixture(scope="module")
def baseline():
    return json.loads((config.ROOT / config.thresholds()["ci_gate"]["baseline_file"]).read_text())


def test_unchanged_code_and_data_pass_the_gate(sample, baseline):
    assert gate.compare(gate.evaluate_sample(raw=sample), baseline, CFG) == []


def test_degraded_data_fails_the_gate(sample, baseline):
    # a regression that corrupts 5% of fares (e.g. a broken upstream transformation)
    idx = pl.int_range(pl.len())
    bad = sample.with_columns(fare_amount=pl.when(idx % 20 == 0).then(-1.0).otherwise(pl.col("fare_amount")))
    problems = gate.compare(gate.evaluate_sample(raw=bad), baseline, CFG)
    assert any("dropped" in p for p in problems)


def test_schema_regression_fails_the_gate(sample, baseline):
    assert gate.compare(gate.evaluate_sample(raw=sample.drop("total_amount")), baseline, CFG) == [
        "schema contract broken on CI sample"]


def test_unexplained_improvement_fails_the_gate(baseline):
    loosened = {**baseline, "quality_score": baseline["quality_score"] + 3.0}
    assert any("rose" in p for p in gate.compare(loosened, baseline, CFG))
