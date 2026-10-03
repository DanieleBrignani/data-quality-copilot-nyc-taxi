"""Generates infra/grafana/dashboards/data_quality.json (run: python infra/grafana/build_dashboard.py)."""

import json
from pathlib import Path

PG = {"type": "grafana-postgresql-datasource", "uid": "dqc_pg"}
PROM = {"type": "prometheus", "uid": "prometheus"}

LATEST = """(SELECT DISTINCT ON (pq.partition_id) pq.*, p.year_month
  FROM dq.partition_quality pq JOIN dq.pipeline_runs r USING (run_id)
  JOIN dq.dataset_partitions p USING (partition_id) WHERE p.service='yellow'
  ORDER BY pq.partition_id, r.started_at DESC)"""


def sql_panel(pid, title, sql, kind, x, y, w, h, fmt="time_series", unit=None, extra=None):
    p = {"id": pid, "title": title, "type": kind, "datasource": PG,
         "gridPos": {"x": x, "y": y, "w": w, "h": h},
         "targets": [{"refId": "A", "datasource": PG, "rawQuery": True, "editorMode": "code",
                      "format": fmt, "rawSql": sql}],
         "fieldConfig": {"defaults": {}, "overrides": []}, "options": {}}
    if unit:
        p["fieldConfig"]["defaults"]["unit"] = unit
    if extra:
        p.update(extra)
    return p


def prom_panel(pid, title, expr, kind, x, y, w, h, unit=None):
    p = {"id": pid, "title": title, "type": kind, "datasource": PROM,
         "gridPos": {"x": x, "y": y, "w": w, "h": h},
         "targets": [{"refId": "A", "datasource": PROM, "expr": expr, "legendFormat": "{{partition}}"}],
         "fieldConfig": {"defaults": {}, "overrides": []}, "options": {},
         # live values: the dashboard's time range covers the historical data months, Prometheus only "now"
         "timeFrom": "1h"}
    if unit:
        p["fieldConfig"]["defaults"]["unit"] = unit
    return p


month = "to_date(year_month || '-01', 'YYYY-MM-DD')"
panels = [
    # headline stats read the warehouse: they must show the latest partitions whatever the time range
    sql_panel(1, "Quality score per partition (latest run)",
              f"SELECT partition_id AS metric, quality_score AS value FROM {LATEST} x ORDER BY 1",
              "stat", 0, 0, 8, 5, fmt="table",
              extra={"options": {"reduceOptions": {"values": True, "calcs": ["lastNotNull"], "fields": "/^value$/"},
                                 "textMode": "value_and_name", "colorMode": "value"}}),
    sql_panel(2, "Valid record rate % per partition",
              f"SELECT partition_id AS metric, valid_record_rate AS value FROM {LATEST} x ORDER BY 1",
              "stat", 8, 0, 8, 5, fmt="table", unit="percent",
              extra={"options": {"reduceOptions": {"values": True, "calcs": ["lastNotNull"], "fields": "/^value$/"},
                                 "textMode": "value_and_name", "colorMode": "value"}}),
    sql_panel(3, "Drift alerts per partition",
              f"""SELECT l.partition_id AS metric, count(*) FILTER (WHERE d.status = 'alert') AS value
                  FROM {LATEST} l LEFT JOIN dq.drift_results d USING (run_id, partition_id) GROUP BY 1 ORDER BY 1""",
              "stat", 16, 0, 8, 5, fmt="table",
              extra={"options": {"reduceOptions": {"values": True, "calcs": ["lastNotNull"], "fields": "/^value$/"},
                                 "textMode": "value_and_name", "colorMode": "value"}}),
    # live Prometheus series (scraped from the API's /metrics): last hour, independent of the dashboard range
    prom_panel(12, "Prometheus: dq_quality_score (live scrape, last hour)", "dq_quality_score", "timeseries",
               0, 41, 24, 7),
    sql_panel(4, "Quality score over time",
              f"SELECT {month} AS time, quality_score, valid_record_rate FROM {LATEST} x ORDER BY 1",
              "timeseries", 0, 5, 12, 8),
    sql_panel(5, "Dataset volume vs quarantine volume",
              f"SELECT {month} AS time, rows_total AS rows, quarantined_records AS quarantined, "
              f"warning_only_records AS warning_only FROM {LATEST} x ORDER BY 1",
              "timeseries", 12, 5, 12, 8, extra={"fieldConfig": {"defaults": {"custom": {"drawStyle": "bars"}},
                                                                "overrides": []}}),
    sql_panel(6, "Rules failing (latest run per partition)",
              f"""SELECT rr.partition_id, rr.rule_id, rr.severity, rr.failed_rows, round((100*rr.failure_rate)::numeric, 4) AS failure_pct
                  FROM dq.rule_results rr JOIN {LATEST} l USING (run_id, partition_id)
                  WHERE rr.failed_rows > 0 ORDER BY rr.partition_id, rr.failed_rows DESC""",
              "table", 0, 13, 12, 10, fmt="table"),
    sql_panel(7, "Failure rate by column (%)",
              f"""SELECT {month.replace('year_month', 'l.year_month')} AS time, rr.columns AS metric,
                         100*sum(rr.failed_rows)::float/max(rr.records_checked) AS value
                  FROM dq.rule_results rr JOIN {LATEST} l USING (run_id, partition_id)
                  WHERE rr.failed_rows > 0 GROUP BY 1, 2 ORDER BY 1""",
              "timeseries", 12, 13, 12, 10, unit="percent"),
    sql_panel(8, "Drift metrics (alerts & warnings)",
              f"""SELECT d.partition_id, d.reference_partition_id AS reference, d.column_name, d.metric,
                         round(d.value::numeric, 4) AS value, d.threshold, d.status
                  FROM dq.drift_results d JOIN {LATEST} l USING (run_id, partition_id)
                  WHERE d.status IN ('alert','warn') ORDER BY d.partition_id, d.status, d.column_name""",
              "table", 0, 23, 16, 10, fmt="table"),
    sql_panel(9, "Freshness: TLC publication lag (days after month end)",
              f"SELECT {month} AS time, source_lag_days FROM {LATEST} x ORDER BY 1", "timeseries", 16, 23, 8, 10),
    sql_panel(10, "Schema events",
              """SELECT s.partition_id, s.check_name, s.column_name, s.severity, s.detail
                 FROM dq.schema_checks s JOIN dq.dataset_partitions p USING (partition_id)
                 WHERE p.service='yellow' ORDER BY s.checked_at DESC LIMIT 50""",
              "table", 0, 33, 12, 8, fmt="table"),
    sql_panel(11, "Anomaly detectors (investigation queue, not quarantined)",
              f"""SELECT a.partition_id, a.method, a.anomalies, round((100*a.anomaly_rate)::numeric, 3) AS rate_pct,
                         round(a.runtime_s::numeric, 2) AS runtime_s
                  FROM dq.anomaly_results a JOIN {LATEST} l USING (run_id, partition_id) ORDER BY 1, 2""",
              "table", 12, 33, 12, 8, fmt="table"),
]

dashboard = {
    "uid": "dq-copilot", "title": "Data Quality Copilot — NYC Taxi", "schemaVersion": 39, "version": 1,
    "time": {"from": "2024-10-01T00:00:00Z", "to": "2025-03-31T00:00:00Z"}, "refresh": "1m",
    "tags": ["data-quality"], "panels": panels,
}
out = Path(__file__).parent / "dashboards" / "data_quality.json"
out.write_text(json.dumps(dashboard, indent=2), encoding="utf-8")
print(out)
