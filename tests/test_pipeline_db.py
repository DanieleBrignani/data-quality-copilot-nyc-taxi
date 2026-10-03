"""Integration tests against PostgreSQL (isolated database `dqc_test`). Run with: pytest -m db"""

from __future__ import annotations

from datetime import timedelta

import pytest

from dqc import db, pipeline
from tests.conftest import many_valid, trips_frame, valid_trip

pytestmark = pytest.mark.db


@pytest.fixture(scope="module")
def dsn(db_available):
    return db.recreate_database("dqc_test")


def _source(tmp_path, rows, name="fx", pid="fixture_it"):
    path = tmp_path / f"{name}.parquet"
    trips_frame(rows, with_ids=False).write_parquet(path)
    src = pipeline.PartitionSource.from_file(path, pid, "2025-01")
    src.service = "fixture"
    return src


def _count(dsn, sql, *params):
    with db.connect(dsn) as conn:
        return conn.execute(sql, params).fetchone()[0]


def _bad_rows():
    base = many_valid(50)
    base[0] = valid_trip(fare_amount=-10.0, total_amount=-10.0)
    base[1] = valid_trip(passenger_count=9)
    p = base[2]["tpep_pickup_datetime"]
    base[2] = valid_trip(tpep_pickup_datetime=p, tpep_dropoff_datetime=p - timedelta(minutes=3))
    return base


def test_duplicate_ingestion_and_rerun_are_idempotent(dsn, tmp_path):
    src = _source(tmp_path, _bad_rows(), pid="fixture_idem")
    first = pipeline.run([src], trigger="test", run_anomalies=False, dsn=dsn)["partitions"][0]
    second = pipeline.run([src], trigger="test", run_anomalies=False, dsn=dsn)["partitions"][0]
    assert first["load_action"] == "loaded" and second["load_action"] == "skipped_same_sha"
    assert _count(dsn, "SELECT count(*) FROM raw.yellow_trips WHERE partition_id=%s", "fixture_idem") == 50
    # 3 bad records -> 4 quarantine rows (the negative-fare record fails DQ021 and DQ022)
    assert first["quarantine_new"] == 4 and second["quarantine_new"] == 0 and second["quarantine_existing"] == 4
    assert _count(dsn, "SELECT count(*) FROM dq.quarantine WHERE partition_id=%s", "fixture_idem") == 4
    # history is kept: two runs, two quality snapshots, identical results
    assert _count(dsn, "SELECT count(*) FROM dq.partition_quality WHERE partition_id=%s", "fixture_idem") == 2
    assert first["quality_score"] == second["quality_score"]


def test_quarantine_keeps_original_values_and_is_resolved_not_deleted(dsn, tmp_path):
    rows = _bad_rows()
    pipeline.run([_source(tmp_path, rows, "v1", "fixture_fix")], trigger="test", run_anomalies=False, dsn=dsn)
    with db.connect(dsn) as conn:
        orig = conn.execute("""SELECT original_value, original_record->>'fare_amount', review_status
                               FROM dq.quarantine WHERE partition_id='fixture_fix'
                               AND failed_rule='DQ021_fare_amount_range'""").fetchone()
    assert orig == ("fare_amount=-10.0", "-10.0", "pending")

    rows[0] = valid_trip(fare_amount=10.0, total_amount=14.75, tip_amount=0.0)  # upstream fix
    res = pipeline.run([_source(tmp_path, rows, "v2", "fixture_fix")], trigger="test", run_anomalies=False,
                       dsn=dsn)["partitions"][0]
    assert res["load_action"] == "reloaded"
    assert res["quarantine_resolved"] == 2  # DQ021 + DQ022 rows of the fixed record
    assert _count(dsn, "SELECT count(*) FROM dq.quarantine WHERE partition_id='fixture_fix'") == 4  # nothing deleted
    assert _count(dsn, """SELECT count(DISTINCT record_id) FROM dq.quarantine
                          WHERE partition_id='fixture_fix' AND resolved_by_run_id IS NULL""") == 2


def test_schema_break_rejects_partition(dsn, tmp_path):
    path = tmp_path / "broken.parquet"
    trips_frame(many_valid(10), with_ids=False).drop("fare_amount").write_parquet(path)
    src = pipeline.PartitionSource.from_file(path, "fixture_broken", "2025-01")
    src.service = "fixture"
    res = pipeline.run([src], trigger="test", run_anomalies=False, dsn=dsn)["partitions"][0]
    assert res["schema_status"] == "breaking"
    assert _count(dsn, "SELECT count(*) FROM raw.yellow_trips WHERE partition_id='fixture_broken'") == 0
    assert _count(dsn, """SELECT count(*) FROM dq.schema_checks WHERE partition_id='fixture_broken'
                          AND check_name='missing_required_column' AND column_name='fare_amount'""") == 1
    assert _count(dsn, """SELECT quality_score FROM dq.partition_quality
                          WHERE partition_id='fixture_broken'""") == 0


def test_raw_integrity_violation_fails_the_run(dsn, tmp_path):
    src = _source(tmp_path, many_valid(5), "tamper", "fixture_tamper")
    src.sha256 = "0" * 64
    with pytest.raises(Exception, match="sha256"):
        pipeline.run([src], trigger="test", run_anomalies=False, dsn=dsn)
    assert _count(dsn, "SELECT count(*) FROM dq.pipeline_runs WHERE status='failed'") >= 1


def test_review_is_audited_and_copilot_role_cannot_touch_data(dsn, tmp_path, monkeypatch):
    import psycopg

    pipeline.run([_source(tmp_path, _bad_rows(), "rv", "fixture_review")], trigger="test",
                 run_anomalies=False, dsn=dsn)
    monkeypatch.setenv("DQC_PG_DSN", dsn)
    import importlib

    import api.main as api_main
    importlib.reload(api_main)
    from fastapi.testclient import TestClient

    client = TestClient(api_main.app)
    qid = client.get("/quarantine", params={"partition_id": "fixture_review"}).json()[0]["quarantine_id"]
    body = {"status": "false_positive", "reviewer": "tester", "note": "reversal pair"}
    monkeypatch.setenv("DQC_API_KEY", "test-key")
    assert client.patch(f"/quarantine/{qid}/review", json=body).status_code == 401      # no key -> refused
    r = client.patch(f"/quarantine/{qid}/review", json=body, headers={"X-API-Key": "test-key"})
    assert r.status_code == 200 and r.json()["old_status"] == "pending"
    assert _count(dsn, "SELECT count(*) FROM dq.quarantine_review_log WHERE quarantine_id=%s", qid) == 1
    assert client.get("/metrics").status_code == 200

    from dqc import config
    copilot_dsn = config.role_dsn("dqc_copilot", "DQC_COPILOT_PASSWORD", database="dqc_test")
    assert copilot_dsn, "DQC_COPILOT_PASSWORD must be set for this test"
    with psycopg.connect(copilot_dsn) as conn:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute("UPDATE dq.quarantine SET review_status='pending'")
    with psycopg.connect(copilot_dsn) as conn:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute("DELETE FROM raw.yellow_trips")
