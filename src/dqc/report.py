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


def models_section() -> list[dict]:
    from dqc.ml import residual
    out = []
    regs = db.query_df("SELECT DISTINCT ON (model_name) * FROM dq.model_registry ORDER BY model_name, version DESC")
    for r in regs.sort("model_name", descending=True).to_dicts():
        mm = db.query_df("""SELECT partition_id, split, n, mae, mae_ci_low, mae_ci_high, rmse, median_ae, r2, flagged,
                                   flag_rate, mae_vs_validation, status, by_payment_type FROM dq.model_metrics
                            WHERE model_name=%s AND version=%s ORDER BY partition_id""", (r["model_name"], r["version"]))
        lm = residual.load(r["model_name"], r["version"])
        out.append({"registry": r, "monitoring": mm.to_dicts(), "meta": lm.meta if lm else {}})
    return out


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
        "models": models_section(),
        "fare_model_review": _read("fare_model_review.json"),
        "distance_model_review": _read("distance_model_review.json"),
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
        out += ["", f"## Benchmark on injected errors ({b['partition']}, {b['label_counts']['clean']:,} real "
                    f"rule-clean records + {b['injected_error_rows']:,} labelled errors, seed {b['seed']})", "",
                "| detector | precision | 95% CI | recall | 95% CI | FPR | flagged | runtime s |",
                "|---|---:|---|---:|---|---:|---:|---:|"]
        for name, m in b["results"].items():
            rt = b["runtime_s"].get("rules" if name.startswith("rules_critical") and "+" not in name else name, "")
            out.append(f"| {name} | {m['precision']} | {m.get('precision_ci95', '')} | {m['recall']} | "
                       f"{m.get('recall_ci95', '')} | "
                       f"{m['false_positive_rate']} | {m['flagged']:,} | {rt} |")
        types = sorted({t for m in b["results"].values() for t in m["recall_by_error_type"]})
        keys = [k for k in ("rules_critical", "rules_critical_plus_warning", "iqr", "iqr_log", "zscore",
                             "isolation_forest", "fare_model", "distance_model") if k in b["results"]]
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
    for fm in res.get("models") or []:
        g, meta = fm["registry"], fm["meta"]
        unit = meta.get("unit", "")
        out += ["", f"## {g['model_name']} v{g['version']} — target `{g['target']}` ({unit}), {g['algorithm']}", "",
                f"trained on {g['train_partition']} ({g['train_rows']:,} sampled rule-valid rows), selected and "
                f"calibrated on {g['validation_partition']}; flag threshold (log-ratio) {g['flag_threshold']:.4f} "
                f"= validation quantile {1 - g['alpha']}", "", f"selection rule: {meta.get('selection_rule', '')}", "",
                "### Candidates on the validation month", "",
                f"| candidate | MAE {unit} | RMSE | median AE | R2 | fit s | size MB | within tolerance | selected |",
                "|---|---:|---:|---:|---:|---:|---:|---|---|"]
        for k, v in sorted(g["selection"].items(), key=lambda kv: kv[1]["mae"]):
            out.append(f"| {k} | {v['mae']:.4f} | {v['rmse']:.3f} | {v['median_ae']:.3f} | {v['r2']:.4f} | {v['fit_s']} | "
                       f"{v['size_bytes'] / 1e6:.2f} | {'yes' if v.get('within_tolerance') else ''} | "
                       f"{'**yes**' if k == meta.get('selected') else ''} |")
        out += ["", "### Performance per partition (all rule-valid records; MAE with 95% bootstrap interval)", "",
                "| partition | split | n | MAE | 95% CI | RMSE | median AE | R2 | flagged | flag % | MAE / validation | status |",
                "|---|---|---:|---:|---|---:|---:|---:|---:|---:|---:|---|"]
        out += [f"| {m['partition_id']} | {m['split']} | {m['n']:,} | {m['mae']:.3f} | "
                f"[{m['mae_ci_low']:.3f}, {m['mae_ci_high']:.3f}] | {m['rmse']:.3f} | {m['median_ae']:.3f} | "
                f"{m['r2']:.4f} | {m['flagged']:,} | {100 * m['flag_rate']:.3f} | {m['mae_vs_validation']:.3f} | "
                f"{m['status']} |" for m in fm["monitoring"]]
        if g.get("backtest"):
            out += ["", "### Rolling-origin backtest (selected configuration refit on month t, evaluated on t+1)", "",
                    "| train | evaluate | MAE | 95% CI | R2 |", "|---|---|---:|---|---:|"]
            out += [f"| {x['train']} | {x['evaluate']} | {x['mae']:.3f} | [{x['mae_ci95'][0]:.3f}, {x['mae_ci95'][1]:.3f}] | "
                    f"{x['r2']:.4f} |" for x in g["backtest"]]
        if meta.get("permutation_importance_mae"):
            out += ["", "### Permutation importance (increase in validation MAE)", "", "| feature | ΔMAE |", "|---|---:|"]
            out += [f"| {k} | {v:.3f} |" for k, v in meta["permutation_importance_mae"].items()]
        out += ["", "### MAE by payment type", "",
                "| partition | " + " | ".join(f"type {i}" for i in range(5)) + " |", "|---|" + "---:|" * 5]
        for m in fm["monitoring"]:
            by = {x["payment_type"]: x["mae"] for x in (m["by_payment_type"] or [])}
            out.append(f"| {m['partition_id']} | " + " | ".join(
                f"{by[i]:.2f}" if i in by else "-" for i in range(5)) + " |")
    ops = (res.get("benchmark") or {}).get("operating_points") or {}
    for name, pts in ops.items():
        out += ["", f"## {name}: operating points on the benchmark (thresholds from the validation month)", "",
                "| review budget (alpha) | precision | recall | FPR | flagged | recall distance_x5 | recall fare_x10 |",
                "|---:|---:|---:|---:|---:|---:|---:|"]
        out += [f"| {a} | {m['precision']} | {m['recall']} | {m['false_positive_rate']} | {m['flagged']:,} | "
                f"{m['recall_by_error_type'].get('distance_x5', '')} | {m['recall_by_error_type'].get('fare_x10', '')} |"
                for a, m in pts.items()]
    for key in ("fare_model_review", "distance_model_review"):
        fr = res.get(key)
        if fr:
            out += ["", f"## Manual review of real {fr['method']} flags", "",
                    f"partition {fr['partition']} (out-of-time), sample {fr['sample_size']} (seed {fr['seed']})", "",
                    "| verdict | count |", "|---|---:|"]
            out += [f"| {k} | {v} |" for k, v in fr["verdict_counts"].items()]
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
