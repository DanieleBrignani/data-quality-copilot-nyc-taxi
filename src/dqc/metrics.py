"""Prometheus instrumentation.

Two paths:
* in-process pipeline metrics (this registry) — optionally pushed to a Pushgateway (DQC_PUSHGATEWAY);
* warehouse-derived gauges served by the API at /metrics (see api/main.py: DQWarehouseCollector),
  so Prometheus always reflects the persisted quality history, even between batch runs.
"""

from __future__ import annotations

import logging

import polars as pl
from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, push_to_gateway

from dqc import config

REGISTRY = CollectorRegistry()
RECORDS_CHECKED = Counter("dq_records_checked", "Records evaluated by the rule engine", ["partition"],
                          registry=REGISTRY)
QUALITY_FAILURES = Counter("dq_quality_failures", "Rule failures (record x rule)", ["partition", "rule_id",
                                                                                    "severity"], registry=REGISTRY)
QUARANTINED = Counter("dq_quarantined_records", "Records quarantined", ["partition"], registry=REGISTRY)
SCHEMA_FAILURES = Counter("dq_schema_failures", "Breaking schema contract violations", ["partition"],
                          registry=REGISTRY)
DRIFT_ALERTS = Counter("dq_drift_alerts", "Drift metrics above alert threshold", ["partition"], registry=REGISTRY)
RUN_DURATION = Histogram("dq_quality_run_duration_seconds", "Pipeline run duration",
                         buckets=(10, 30, 60, 120, 300, 600, 900, 1800, 3600), registry=REGISTRY)
PARTITION_DURATION = Gauge("dq_partition_duration_seconds", "Partition processing time", ["partition"],
                           registry=REGISTRY)
QUALITY_SCORE = Gauge("dq_quality_score", "Quality score (0-100)", ["partition"], registry=REGISTRY)


def record_partition(pid: str, rows: int, summary: pl.DataFrame, scores: dict, drift_rows: list[dict],
                     duration: float) -> None:
    RECORDS_CHECKED.labels(pid).inc(rows)
    for r in summary.iter_rows(named=True):
        if r["failed_rows"]:
            QUALITY_FAILURES.labels(pid, r["rule_id"], r["severity"]).inc(r["failed_rows"])
    QUARANTINED.labels(pid).inc(scores["quarantined_records"])
    DRIFT_ALERTS.labels(pid).inc(sum(d["status"] == "alert" for d in drift_rows))
    PARTITION_DURATION.labels(pid).set(duration)
    QUALITY_SCORE.labels(pid).set(scores["quality_score"])


def push() -> None:
    if not config.PUSHGATEWAY:
        return
    try:
        push_to_gateway(config.PUSHGATEWAY, job="dqc_pipeline", registry=REGISTRY)
    except Exception as exc:  # metrics must never break the pipeline
        logging.getLogger("dqc.metrics").warning("pushgateway unavailable: %s", exc)
