"""Builds reports/results.json + reports/results.md from the warehouse and benchmark outputs.

Every number quoted in the README comes from these files; regenerate them with `python -m dqc report`.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from dqc import config, db

# The reported numbers come from ONE reference run (the latest run triggered by the reproduce script),
# so later reruns cannot silently change them; falls back to latest-per-partition.
REF_RUN = """(SELECT run_id FROM dq.pipeline_runs WHERE status='success' AND trigger='reproduce'
              ORDER BY started_at DESC LIMIT 1)"""
LATEST = f"""SELECT DISTINCT ON (pq.partition_id) pq.*, p.year_month, r.ruleset_version, r.code_version
            FROM dq.partition_quality pq JOIN dq.pipeline_runs r USING (run_id)
            JOIN dq.dataset_partitions p USING (partition_id) WHERE p.service='yellow'
              AND (NOT EXISTS {REF_RUN} OR pq.run_id = {REF_RUN})
            ORDER BY pq.partition_id, r.started_at DESC"""


def rerun_check() -> dict | None:
    """Compare the latest 'rerun' run against the reference run, partition by partition."""
    df = db.query_df(f"""
        WITH rr AS (SELECT run_id FROM dq.pipeline_runs WHERE status='success' AND trigger='rerun'
                    ORDER BY started_at DESC LIMIT 1)
        SELECT a.partition_id, a.quality_score AS ref_score, b.quality_score AS rerun_score,
               a.quarantined_records AS ref_q, b.quarantined_records AS rerun_q,
               a.duration_s AS ref_s, b.duration_s AS rerun_s,
               (b.stage_timings->>'raw_landing')::float AS rerun_raw_landing_s,
               (SELECT count(*) FROM raw.yellow_trips t WHERE t.partition_id = a.partition_id) AS raw_rows,
               a.rows_total
        FROM dq.partition_quality a JOIN dq.partition_quality b USING (partition_id)
        WHERE a.run_id = {REF_RUN} AND b.run_id = (SELECT run_id FROM rr)
        ORDER BY 1""")
    if df.is_empty():
        return None
    rows = df.to_dicts()
    return {"partitions": rows,
            "identical_results": all(r["ref_score"] == r["rerun_score"] and r["ref_q"] == r["rerun_q"] for r in rows),
            "no_duplicate_rows": all(r["raw_rows"] == r["rows_total"] for r in rows)}


def collect() -> dict:
    parts = db.query_df(LATEST).sort("partition_id").to_dicts()
    total_rows = sum(p["rows_total"] for p in parts)
    total_q = sum(p["quarantined_records"] for p in parts)
    total_w = sum(p["warning_only_records"] for p in parts)
    total_dur = sum(p["duration_s"] for p in parts)
    rules = db.query_df(f"""SELECT rr.partition_id, rr.rule_id, rr.severity, rr.records_checked, rr.failed_rows,
                                   rr.failure_rate FROM dq.rule_results rr JOIN ({LATEST}) l USING (run_id, partition_id)
                            ORDER BY rr.partition_id, rr.rule_id""").to_dicts()
    schema = db.query_df(f"""SELECT s.partition_id, s.check_name, s.column_name, s.severity, s.detail
                             FROM dq.schema_checks s JOIN ({LATEST}) l USING (run_id, partition_id)
                             ORDER BY 1""").to_dicts()
    drift = db.query_df(f"""SELECT d.partition_id, d.reference_partition_id, d.column_name, d.metric, d.value,
                                   d.threshold, d.status
                            FROM dq.drift_results d JOIN ({LATEST}) l USING (run_id, partition_id)
                            WHERE d.status IN ('alert','warn') ORDER BY 1, 3, 4""").to_dicts()
    anomalies = db.query_df(f"""SELECT a.partition_id, a.method, a.records_scored, a.anomalies, a.anomaly_rate,
                                       a.runtime_s FROM dq.anomaly_results a JOIN ({LATEST}) l USING (run_id, partition_id)
                                ORDER BY 1, 2""").to_dicts()
    runs = db.query_df("""SELECT run_id::text, status, trigger, rows_processed, duration_s, started_at
                          FROM dq.pipeline_runs ORDER BY started_at""").to_dicts()
    quarantine = db.query_df("""SELECT q.failed_rule, count(*) AS rows, count(DISTINCT q.record_id) AS records
                                FROM dq.quarantine q JOIN dq.dataset_partitions p USING (partition_id)
                                WHERE p.service='yellow' AND q.resolved_by_run_id IS NULL
                                GROUP BY 1 ORDER BY 2 DESC""").to_dicts()

    def _read(name):
        p = config.REPORTS_DIR / name
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "totals": {
            "partitions": len(parts), "records_processed": total_rows, "quarantined_records": total_q,
            "quarantined_pct": 100 * total_q / total_rows if total_rows else 0,
            "warning_only_records": total_w, "warning_only_pct": 100 * total_w / total_rows if total_rows else 0,
            "processing_s": total_dur, "rows_per_sec": total_rows / total_dur if total_dur else 0,
            "schema_changes_detected": sum(1 for s in schema if s["check_name"].endswith("_vs_previous")),
            "unexpected_schema_changes": sum(p["unexpected_schema_changes"] for p in parts),
            "drift_alerts": sum(1 for d in drift if d["status"] == "alert"),
            "drift_warnings": sum(1 for d in drift if d["status"] == "warn"),
        },
        "partitions": parts, "rules": rules, "schema_events": schema, "drift": drift,
        "anomalies": anomalies, "quarantine_by_rule": quarantine, "runs": runs,
        "benchmark": _read("benchmark.json"), "failure_demo": _read("failure_demo.json"),
        "anomaly_review": _read("anomaly_review.json"),
        "rerun_check": rerun_check(),
        "copilot": db.query_df("""SELECT provider, status, count(*) AS n FROM dq.copilot_suggestions
                                  GROUP BY 1, 2 ORDER BY 1, 2""").to_dicts(),
    }


def _md(res: dict) -> str:
    t = res["totals"]
    out = [f"# Results (generated {res['generated_at']})", "",
           "All values below are read from the warehouse / report files; regenerate with `python -m dqc report`.", "",
           "## Totals", "",
           f"- partitions: {t['partitions']}",
           f"- records processed: {t['records_processed']:,}",
           f"- quarantined records: {t['quarantined_records']:,} ({t['quarantined_pct']:.3f}%)",
           f"- warning-only records (kept, flagged): {t['warning_only_records']:,} ({t['warning_only_pct']:.3f}%)",
           f"- processing time (sum of partitions): {t['processing_s']:.1f}s -> {t['rows_per_sec']:,.0f} rows/s",
           f"- schema changes detected between consecutive partitions: {t['schema_changes_detected']} "
           f"(unexpected / contract-breaking: {t['unexpected_schema_changes']})",
           f"- drift alerts: {t['drift_alerts']} (warnings: {t['drift_warnings']})", "",
           "## Per partition", "",
           "| partition | rows | quarantined | % | warning-only | valid % | score | schema | duration s | rows/s | source lag d |",
           "|---|---:|---:|---:|---:|---:|---:|---|---:|---:|---:|"]
    for p in res["partitions"]:
        out.append(f"| {p['partition_id']} | {p['rows_total']:,} | {p['quarantined_records']:,} | "
                   f"{100 * p['quarantined_records'] / p['rows_total']:.3f} | {p['warning_only_records']:,} | "
                   f"{p['valid_record_rate']:.3f} | {p['quality_score']:.3f} | {p['schema_status']} | "
                   f"{p['duration_s']:.1f} | {p['rows_per_sec']:,.0f} | {p['source_lag_days'] or 0:.1f} |")
    stages = ["read_and_schema", "raw_landing", "profiling", "rules", "persist_quality", "anomaly", "drift"]
    out += ["", "## Stage timings (s)", "", "| partition | " + " | ".join(stages) + " |",
            "|---|" + "---:|" * len(stages)]
    for p in res["partitions"]:
        st = p["stage_timings"] or {}
        out.append(f"| {p['partition_id']} | " + " | ".join(
            f"{st[k]:.1f}" if st.get(k) is not None else "-" for k in stages) + " |")
    out += ["", "## Rule failures (failed rows / failure rate %)", "",
            "| rule | severity | " + " | ".join(p["partition_id"] for p in res["partitions"]) + " |",
            "|---|---|" + "---:|" * len(res["partitions"])]
    by_rule: dict = {}
    for r in res["rules"]:
        by_rule.setdefault((r["rule_id"], r["severity"]), {})[r["partition_id"]] = r
    for (rid, sev), cells in by_rule.items():
        out.append(f"| {rid} | {sev} | " + " | ".join(
            f"{cells[p['partition_id']]['failed_rows']:,} / {100 * cells[p['partition_id']]['failure_rate']:.3f}"
            if p["partition_id"] in cells else "-" for p in res["partitions"]) + " |")
    out += ["", "## Schema events", "", "| partition | check | column | severity | detail |", "|---|---|---|---|---|"]
    out += [f"| {s['partition_id']} | {s['check_name']} | {s['column_name']} | {s['severity']} | {s['detail']} |"
            for s in res["schema_events"]]
    out += ["", "## Drift alerts & warnings", "", "| partition | vs | column | metric | value | threshold | status |",
            "|---|---|---|---|---:|---:|---|"]
    out += [f"| {d['partition_id']} | {d['reference_partition_id']} | {d['column_name']} | {d['metric']} | "
            f"{d['value']:.4f} | {d['threshold']} | {d['status']} |" for d in res["drift"]]
    out += ["", "## Anomaly detectors on rule-valid records", "",
            "| partition | method | scored | flagged | % | runtime s |", "|---|---|---:|---:|---:|---:|"]
    out += [f"| {a['partition_id']} | {a['method']} | {a['records_scored']:,} | {a['anomalies']:,} | "
            f"{100 * a['anomaly_rate']:.3f} | {a['runtime_s']:.2f} |" for a in res["anomalies"]]
    b = res.get("benchmark")
    if b:
        out += ["", f"## Benchmark on injected errors ({b['partition']}, {b['clean_real_records']:,} real rule-clean "
                    f"records + {b['injected_error_rows']:,} labelled errors, seed {b['seed']})", "",
                "| detector | precision | recall | FPR | flagged | runtime s |", "|---|---:|---:|---:|---:|---:|"]
        for name, m in b["results"].items():
            rt = b["runtime_s"].get("rules" if name.startswith("rules_critical") and "+" not in name else name, "")
            out.append(f"| {name} | {m['precision']} | {m['recall']} | {m['false_positive_rate']} | {m['flagged']:,} | {rt} |")
        types = sorted({t for m in b["results"].values() for t in m["recall_by_error_type"]})
        keys = ["rules_critical", "rules_critical_plus_warning", "iqr", "iqr_log", "zscore", "isolation_forest"]
        out += ["", "### Recall by error type", "", "| error type | family | " + " | ".join(keys) + " |",
                "|---|---|" + "---:|" * len(keys)]
        for tp in types:
            out.append(f"| {tp} | {b['error_types'].get(tp, '')} | " + " | ".join(
                str(b["results"][k]["recall_by_error_type"].get(tp, "")) for k in keys) + " |")
    fd = res.get("failure_demo")
    if fd:
        out += ["", "## Failure demo", "", "| fixture | expected | observed | detected |", "|---|---|---|---|"]
        out += [f"| {c['fixture']} | {json.dumps(c['expected'])} | {json.dumps(c['observed'])} | {c['detected']} |"
                for c in fd["checks"]]
    rc = res.get("rerun_check")
    if rc:
        out += ["", "## Rerun check (same files, same code, second run)", "",
                f"identical quality results: {rc['identical_results']} · raw rows not duplicated: "
                f"{rc['no_duplicate_rows']}", "",
                "| partition | score ref | score rerun | quarantined ref | quarantined rerun | raw rows | "
                "duration ref s | duration rerun s | rerun raw landing s |", "|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
        out += [f"| {r['partition_id']} | {r['ref_score']:.4f} | {r['rerun_score']:.4f} | {r['ref_q']:,} | "
                f"{r['rerun_q']:,} | {r['raw_rows']:,} | {r['ref_s']:.1f} | {r['rerun_s']:.1f} | "
                f"{r['rerun_raw_landing_s']:.1f} |" for r in rc["partitions"]]
    ar = res.get("anomaly_review")
    if ar:
        out += ["", "## Manual review of real anomalies", "", f"method: {ar['method']}, partition {ar['partition']}, "
                f"sample {ar['sample_size']} (seed {ar['seed']})", "", "| verdict | count |", "|---|---:|"]
        out += [f"| {k} | {v} |" for k, v in ar["verdict_counts"].items()]
    return "\n".join(out) + "\n"


def write() -> str:
    res = collect()
    config.REPORTS_DIR.mkdir(exist_ok=True)
    (config.REPORTS_DIR / "results.json").write_text(json.dumps(res, indent=2, default=str), encoding="utf-8")
    md = _md(res)
    (config.REPORTS_DIR / "results.md").write_text(md, encoding="utf-8")
    return md
