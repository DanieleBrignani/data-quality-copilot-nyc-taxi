"""Quality API: read quality history, review quarantine, request copilot suggestions, expose /metrics."""

from __future__ import annotations

import os
from typing import Literal

import psycopg
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, generate_latest
from prometheus_client.core import CounterMetricFamily, GaugeMetricFamily
from pydantic import BaseModel

from dqc import config

DSN = os.environ.get("DQC_PG_DSN", config.PG_DSN)
app = FastAPI(title="Data Quality Copilot — NYC Taxi", version="0.1.0")

LATEST = """
    SELECT DISTINCT ON (pq.partition_id) pq.*
    FROM dq.partition_quality pq JOIN dq.pipeline_runs r USING (run_id)
    JOIN dq.dataset_partitions p USING (partition_id)
    WHERE p.service = 'yellow'
    ORDER BY pq.partition_id, r.started_at DESC"""


def q(sql: str, params: tuple | dict | None = None) -> list[dict]:
    with psycopg.connect(DSN) as conn, conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
        cur.execute(sql, params)
        return cur.fetchall() if cur.description else []


@app.get("/health")
def health():
    q("SELECT 1")
    return {"status": "ok"}


@app.get("/runs")
def runs(limit: int = 20):
    return q("SELECT * FROM dq.pipeline_runs ORDER BY started_at DESC LIMIT %s", (limit,))


@app.get("/partitions")
def partitions():
    return q(f"SELECT l.*, p.year_month, p.sha256, p.source_url, p.row_count AS source_row_count "
             f"FROM ({LATEST}) l JOIN dq.dataset_partitions p USING (partition_id) ORDER BY partition_id")


@app.get("/partitions/{partition_id}/rules")
def partition_rules(partition_id: str):
    rows = q("""SELECT rr.* FROM dq.rule_results rr
                JOIN (SELECT run_id FROM dq.partition_quality pq JOIN dq.pipeline_runs r USING (run_id)
                      WHERE partition_id=%s ORDER BY r.started_at DESC LIMIT 1) l USING (run_id)
                WHERE rr.partition_id=%s ORDER BY failure_rate DESC""", (partition_id, partition_id))
    if not rows:
        raise HTTPException(404, "partition not found")
    return rows


@app.get("/rules")
def rule_definitions():
    return q("SELECT * FROM dq.rule_definitions ORDER BY rule_id, rule_version")


@app.get("/drift")
def drift(status: str = "alert"):
    return q("""SELECT d.* FROM dq.drift_results d JOIN dq.pipeline_runs r USING (run_id)
                WHERE d.status = %s ORDER BY r.started_at DESC, d.partition_id, d.column_name""", (status,))


@app.get("/anomalies")
def anomalies():
    return q("""SELECT a.* FROM dq.anomaly_results a JOIN dq.pipeline_runs r USING (run_id)
                ORDER BY r.started_at DESC, a.partition_id, a.method""")


@app.get("/quarantine")
def quarantine(partition_id: str | None = None, rule_id: str | None = None,
               review_status: str | None = None, limit: int = Query(50, le=1000)):
    return q("""SELECT quarantine_id, record_id, partition_id, failed_rule, rule_version, severity,
                       original_value, reason, pipeline_run_id, quarantined_at, review_status, original_record
                FROM dq.quarantine
                WHERE resolved_by_run_id IS NULL
                  AND (%(p)s::text IS NULL OR partition_id = %(p)s)
                  AND (%(r)s::text IS NULL OR failed_rule = %(r)s)
                  AND (%(s)s::text IS NULL OR review_status = %(s)s)
                ORDER BY quarantine_id LIMIT %(l)s""",
             {"p": partition_id, "r": rule_id, "s": review_status, "l": limit})


class Review(BaseModel):
    status: Literal["confirmed_invalid", "false_positive", "fixed_upstream", "pending"]
    reviewer: str
    note: str | None = None


@app.patch("/quarantine/{quarantine_id}/review")
def review(quarantine_id: int, body: Review):
    """Human review changes only the review status (audited). It never republishes the record."""
    with psycopg.connect(DSN) as conn:
        row = conn.execute("SELECT review_status FROM dq.quarantine WHERE quarantine_id=%s FOR UPDATE",
                           (quarantine_id,)).fetchone()
        if not row:
            raise HTTPException(404, "not found")
        conn.execute("""UPDATE dq.quarantine SET review_status=%s, reviewed_by=%s, reviewed_at=now(), review_note=%s
                        WHERE quarantine_id=%s""", (body.status, body.reviewer, body.note, quarantine_id))
        conn.execute("""INSERT INTO dq.quarantine_review_log (quarantine_id, old_status, new_status, reviewed_by, note)
                        VALUES (%s,%s,%s,%s,%s)""", (quarantine_id, row[0], body.status, body.reviewer, body.note))
    return {"quarantine_id": quarantine_id, "old_status": row[0], "new_status": body.status}


@app.get("/copilot/suggestions")
def suggestions(limit: int = 20):
    return q("SELECT * FROM dq.copilot_suggestions ORDER BY suggestion_id DESC LIMIT %s", (limit,))


@app.post("/copilot/explain")
def copilot_explain(limit: int = Query(3, le=10)):
    from dqc import copilot
    return copilot.explain_latest(limit)


class SuggestionReview(BaseModel):
    status: Literal["accepted", "rejected"]
    reviewer: str
    note: str | None = None


@app.patch("/copilot/suggestions/{suggestion_id}")
def review_suggestion(suggestion_id: int, body: SuggestionReview):
    """Accepting a suggestion records the decision only; any rule change still goes through a PR."""
    with psycopg.connect(DSN) as conn:
        n = conn.execute("""UPDATE dq.copilot_suggestions SET status=%s, reviewed_by=%s, reviewed_at=now(),
                            review_note=%s WHERE suggestion_id=%s""",
                         (body.status, body.reviewer, body.note, suggestion_id)).rowcount
    if not n:
        raise HTTPException(404, "not found")
    return {"suggestion_id": suggestion_id, "status": body.status}


# --------------------------------------------------------------------------- Prometheus
class DQWarehouseCollector:
    """Derives metrics from the persisted quality history at scrape time."""

    def collect(self):
        latest = q(LATEST)
        checked = CounterMetricFamily("dq_records_checked", "Records checked (latest run per partition)",
                                      labels=["partition"])
        quarantined = CounterMetricFamily("dq_quarantined_records", "Records quarantined", labels=["partition"])
        score = GaugeMetricFamily("dq_quality_score", "Quality score 0-100", labels=["partition"])
        valid = GaugeMetricFamily("dq_valid_record_rate", "Valid record rate %", labels=["partition"])
        duration = GaugeMetricFamily("dq_quality_run_duration_seconds", "Partition processing time",
                                     labels=["partition"])
        rps = GaugeMetricFamily("dq_rows_per_second", "Throughput", labels=["partition"])
        lag = GaugeMetricFamily("dq_source_lag_days", "TLC publication delay after month end", labels=["partition"])
        schema_fail = CounterMetricFamily("dq_schema_failures", "Unexpected schema changes", labels=["partition"])
        for r in latest:
            p = r["partition_id"]
            checked.add_metric([p], r["rows_total"])
            quarantined.add_metric([p], r["quarantined_records"])
            score.add_metric([p], r["quality_score"])
            valid.add_metric([p], r["valid_record_rate"])
            duration.add_metric([p], r["duration_s"] or 0)
            rps.add_metric([p], r["rows_per_sec"] or 0)
            lag.add_metric([p], r["source_lag_days"] or 0)
            schema_fail.add_metric([p], r["unexpected_schema_changes"])
        yield from (checked, quarantined, score, valid, duration, rps, lag, schema_fail)

        failures = CounterMetricFamily("dq_quality_failures", "Failed rows per rule (latest run)",
                                       labels=["partition", "rule_id", "severity"])
        rate = GaugeMetricFamily("dq_rule_failure_rate", "Failure rate per rule", labels=["partition", "rule_id"])
        for r in q(f"""SELECT rr.partition_id, rr.rule_id, rr.severity, rr.failed_rows, rr.failure_rate
                       FROM dq.rule_results rr JOIN ({LATEST}) l USING (run_id, partition_id)"""):
            failures.add_metric([r["partition_id"], r["rule_id"], r["severity"]], r["failed_rows"])
            rate.add_metric([r["partition_id"], r["rule_id"]], r["failure_rate"])
        yield failures
        yield rate

        drift = CounterMetricFamily("dq_drift_alerts", "Drift metrics above alert threshold", labels=["partition"])
        for r in q(f"""SELECT d.partition_id, count(*) FILTER (WHERE d.status='alert') AS n
                       FROM dq.drift_results d JOIN ({LATEST}) l USING (run_id, partition_id)
                       GROUP BY 1"""):
            drift.add_metric([r["partition_id"]], r["n"])
        yield drift


REGISTRY = CollectorRegistry()
REGISTRY.register(DQWarehouseCollector())


@app.get("/metrics")
def metrics():
    return Response(generate_latest(REGISTRY), media_type=CONTENT_TYPE_LATEST)
