"""End-to-end quality pipeline for one or more partitions.

raw parquet (immutable, hash-verified)
  -> schema contract          (breaking change => partition rejected, nothing propagates)
  -> raw landing in Postgres  (idempotent: skipped when the same file sha256 is already loaded)
  -> profiling snapshot
  -> deterministic rules      -> record verdicts + quarantine (upsert, never delete)
  -> anomaly detection        (valid records only; investigation queue, never quarantines)
  -> drift vs previous partition
  -> partition quality score + SLO inputs
The curated layer (fct_clean_trips) is built by dbt from raw + dq.record_quality.
"""

from __future__ import annotations

import json
import logging
import subprocess
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

import numpy as np
import polars as pl

from dqc import anomaly, config, db, drift, ingest, metrics, profiling, rules, schema

log = logging.getLogger("dqc.pipeline")


@dataclass
class PartitionSource:
    partition_id: str
    year_month: str
    path: Path
    sha256: str
    source_url: str
    service: str = "yellow"
    file_format: str = "parquet"
    size_bytes: int | None = None
    row_count: int | None = None
    source_schema: dict | None = None
    downloaded_at: str | None = None
    source_last_modified: str | None = None

    @classmethod
    def from_manifest(cls, entry: dict, data_dir: Path = config.DATA_DIR) -> "PartitionSource":
        return cls(entry["partition_id"], entry["year_month"], data_dir / entry["local_path"], entry["sha256"],
                   entry["source_url"], entry["service"], entry["file_format"], entry["size_bytes"],
                   entry["row_count"], entry["schema"], entry["downloaded_at_utc"], entry.get("http_last_modified"))

    @classmethod
    def from_file(cls, path: Path, partition_id: str, year_month: str) -> "PartitionSource":
        d = ingest.describe_parquet(path)
        return cls(partition_id, year_month, path, ingest.sha256_file(path), f"file://{path.name}",
                   size_bytes=path.stat().st_size, row_count=d["row_count"], source_schema=d["schema"])


def manifest_sources(manifest_path: Path = config.MANIFEST_PATH) -> list[PartitionSource]:
    m = ingest.load_manifest(manifest_path)
    return sorted((PartitionSource.from_manifest(e, manifest_path.parent.parent) for e in m["files"].values()),
                  key=lambda s: (s.service, s.year_month))


def code_version() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=config.ROOT,
                                       stderr=subprocess.DEVNULL, text=True).strip()
    except Exception:
        from dqc import __version__
        return __version__


def read_partition(src: PartitionSource) -> tuple[pl.DataFrame | None, schema.SchemaResult]:
    actual = ingest.sha256_file(src.path)
    if actual != src.sha256:
        raise ingest.IntegrityError(f"{src.path}: sha256 {actual} != registered {src.sha256}")
    raw = pl.read_parquet(src.path)
    df, sres = schema.validate_and_normalise(raw)
    if df is None:
        return None, sres
    df = df.with_row_index("source_row").with_columns(
        source_row=pl.col("source_row").cast(pl.Int64),
        record_id=pl.format("{}:{}", pl.lit(src.partition_id), pl.col("source_row")),
    )
    return df, sres


def _month_end(year_month: str) -> datetime:
    return rules.month_window(year_month)[1].replace(tzinfo=timezone.utc)


# --------------------------------------------------------------------------- persistence steps
def register_partition(conn, src: PartitionSource) -> None:
    lm = parsedate_to_datetime(src.source_last_modified) if src.source_last_modified else None
    conn.execute(
        """INSERT INTO dq.dataset_partitions (partition_id, service, year_month, source_url, file_format, sha256,
               size_bytes, row_count, source_schema, downloaded_at, source_last_modified)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
           ON CONFLICT (partition_id) DO UPDATE SET sha256=EXCLUDED.sha256, size_bytes=EXCLUDED.size_bytes,
               row_count=EXCLUDED.row_count, source_schema=EXCLUDED.source_schema,
               source_last_modified=EXCLUDED.source_last_modified""",
        (src.partition_id, src.service, src.year_month, src.source_url, src.file_format, src.sha256,
         src.size_bytes, src.row_count, json.dumps(src.source_schema), src.downloaded_at, lm))


def load_raw(conn, src: PartitionSource, df: pl.DataFrame, run_id: str) -> str:
    """Idempotent landing: returns 'skipped_same_sha' | 'loaded' | 'reloaded'."""
    row = conn.execute("SELECT loaded_sha256 FROM dq.dataset_partitions WHERE partition_id=%s",
                       (src.partition_id,)).fetchone()
    table = db.raw_partition_table(src.partition_id)
    exists = conn.execute("SELECT to_regclass(%s)", (table,)).fetchone()[0] is not None
    if row and row[0] == src.sha256 and exists:
        n = conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
        if n == df.height:
            return "skipped_same_sha"
    action = "reloaded" if exists else "loaded"
    conn.execute(f"DROP TABLE IF EXISTS {table}")
    # Bulk path: COPY into an index-free table, then ATTACH (index built once, not row by row).
    conn.execute(f"CREATE TABLE {table} (LIKE raw.yellow_trips INCLUDING DEFAULTS)")
    conn.execute(f"ALTER TABLE {table} ADD CONSTRAINT {table.split('.')[1]}_pid CHECK "
                 f"(partition_id = '{src.partition_id}')")
    out = df.select(
        pl.lit(src.partition_id).alias("partition_id"), "record_id", "source_row",
        *[pl.col(c).alias(w) for c, w in db.RAW_COLUMN_MAP.items()],
        pl.lit(run_id).alias("loaded_run_id"),
    )
    db.copy_df(conn, table, out)
    conn.execute(f"ALTER TABLE raw.yellow_trips ATTACH PARTITION {table} FOR VALUES IN ('{src.partition_id}')")
    conn.execute("""UPDATE dq.dataset_partitions SET loaded_sha256=%s, loaded_run_id=%s, loaded_at=now()
                    WHERE partition_id=%s""", (src.sha256, run_id, src.partition_id))
    return action


def persist_rule_results(conn, run_id, pid, summary: pl.DataFrame, flags: pl.DataFrame,
                         quarantine: pl.DataFrame) -> dict:
    db.copy_df(conn, "dq.rule_results", summary.select(
        pl.lit(run_id).alias("run_id"), pl.lit(pid).alias("partition_id"), "rule_id", "rule_version", "severity",
        "dimension", "columns", "records_checked", "failed_rows", "failure_rate"))

    conn.execute("DELETE FROM dq.record_quality WHERE partition_id=%s", (pid,))
    db.copy_df(conn, "dq.record_quality", flags.select(
        pl.lit(pid).alias("partition_id"), "record_id", "is_valid", "failed_critical", "failed_warning",
        pl.lit(run_id).alias("run_id")))

    conn.execute("CREATE TEMP TABLE q_stage (LIKE dq.quarantine INCLUDING DEFAULTS) ON COMMIT DROP")
    db.copy_df(conn, "q_stage", quarantine.select(
        "record_id", pl.lit(pid).alias("partition_id"), "failed_rule", "rule_version", "severity",
        "original_value", "reason", "original_record",
        pl.lit(run_id).alias("pipeline_run_id"), pl.lit(run_id).alias("last_seen_run_id")))
    ins = conn.execute(
        """INSERT INTO dq.quarantine (record_id, partition_id, failed_rule, rule_version, severity, original_value,
               reason, original_record, pipeline_run_id, last_seen_run_id)
           SELECT record_id, partition_id, failed_rule, rule_version, severity, original_value, reason,
                  original_record, pipeline_run_id, last_seen_run_id FROM q_stage
           ON CONFLICT (record_id, failed_rule) DO UPDATE SET
               last_seen_run_id = EXCLUDED.last_seen_run_id, rule_version = EXCLUDED.rule_version,
               original_value = EXCLUDED.original_value, reason = EXCLUDED.reason, resolved_by_run_id = NULL
           RETURNING (xmax = 0) AS inserted""").fetchall()
    resolved = conn.execute(
        """UPDATE dq.quarantine SET resolved_by_run_id=%s
           WHERE partition_id=%s AND last_seen_run_id <> %s AND resolved_by_run_id IS NULL""",
        (run_id, pid, run_id)).rowcount
    new = sum(1 for (i,) in ins if i)
    return {"quarantine_rows": quarantine.height, "quarantine_new": new,
            "quarantine_existing": len(ins) - new, "quarantine_resolved": resolved}


def quality_scores(df_rows: int, ev: rules.RuleEvaluation, ruleset: rules.RuleSet, flags: pl.DataFrame,
                   warning_weight: float) -> dict:
    crit_fail = flags.filter(~pl.col("is_valid")).height
    warn_only = flags.filter(pl.col("is_valid") & (pl.col("failed_warning").list.len() > 0)).height
    score = 100.0 * (1 - (crit_fail + warning_weight * warn_only) / df_rows) if df_rows else 0.0
    dims = {}
    for dim in sorted({r.dimension for r in ruleset.rules}):
        ids = [r.rule_id for r in ruleset.rules if r.dimension == dim]
        failing = ev.failures.select(pl.any_horizontal(ids).sum()).item()
        dims[dim] = round(100.0 * (1 - failing / df_rows), 4) if df_rows else 0.0
    return {"valid_rows": df_rows - crit_fail, "quarantined_records": crit_fail, "warning_only_records": warn_only,
            "valid_record_rate": 100.0 * (df_rows - crit_fail) / df_rows if df_rows else 0.0,
            "quality_score": score, "dimension_scores": dims}


def run_anomaly(conn, run_id, pid, valid: pl.DataFrame, cfg: dict) -> list[dict]:
    feats = cfg["features"]
    results = [
        anomaly.iqr(valid, feats, cfg["iqr_k"]),
        anomaly.iqr(valid, feats, cfg["iqr_k"], log_transform=True),
        anomaly.zscore(valid, feats, cfg["zscore_threshold"]),
        anomaly.isolation_forest(valid, feats, cfg["iforest_train_sample"], cfg["iforest_n_estimators"],
                                 cfg["iforest_contamination"], cfg["random_state"])[0],
    ]
    out = []
    for r in results:
        n_anom = int(r.flags.sum())
        row = {"run_id": run_id, "partition_id": pid, "method": r.method, "records_scored": valid.height,
               "anomalies": n_anom, "anomaly_rate": n_anom / valid.height if valid.height else 0.0,
               "runtime_s": round(r.runtime_s, 3), "params": r.params, "per_feature": r.per_feature}
        out.append(row)
        top = np.argsort(-r.scores)[: cfg["top_n_persist"]]
        top = top[r.flags[top]]
        if len(top):
            sub = valid[top.tolist()].select("record_id", *feats).with_columns(
                pl.Series("score", r.scores[top]))
            db.copy_df(conn, "dq.anomaly_records", sub.select(
                pl.lit(run_id).alias("run_id"), pl.lit(pid).alias("partition_id"), pl.lit(r.method).alias("method"),
                "record_id", "score", pl.struct(feats).struct.json_encode().alias("features")))
    db.insert_dicts(conn, "dq.anomaly_results", out)
    return out


# --------------------------------------------------------------------------- main entry points
def process_partition(conn, run_id: str, src: PartitionSource, ruleset: rules.RuleSet,
                      reference: PartitionSource | None = None, run_anomalies: bool = True) -> dict:
    th = config.thresholds()
    timings: dict[str, float] = {}
    t0 = time.perf_counter()

    def lap(name: str, since: float) -> float:
        now = time.perf_counter()
        timings[name] = round(now - since, 3)
        return now

    register_partition(conn, src)
    df, sres = read_partition(src)
    t = lap("read_and_schema", t0)
    diffs = (schema.diff_vs_previous(src.source_schema or {}, reference.source_schema or {})
             if reference is not None and reference.source_schema else [])
    for e in [*sres.events, *diffs]:
        conn.execute("INSERT INTO dq.schema_checks VALUES (%s,%s,%s,%s,%s,%s,now())",
                     (run_id, src.partition_id, e.check, e.column, e.severity, e.detail))
    status = "breaking" if sres.is_breaking else (
        "additive_change" if any(e.severity != "critical" for e in sres.events) else "ok")
    metrics.SCHEMA_FAILURES.labels(src.partition_id).inc(sum(e.severity == "critical" for e in sres.events))

    if df is None:
        # Partition rejected: nothing reaches raw landing, quarantine or curated layers.
        conn.execute(
            """INSERT INTO dq.partition_quality (run_id, partition_id, rows_total, valid_rows, quarantined_records,
                   warning_only_records, valid_record_rate, quality_score, schema_status, unexpected_schema_changes,
                   duration_s, stage_timings) VALUES (%s,%s,%s,0,0,0,0,0,'breaking',%s,%s,%s)""",
            (run_id, src.partition_id, src.row_count or 0, sres.unexpected_changes, time.perf_counter() - t0,
             json.dumps(timings)))
        conn.commit()
        return {"partition_id": src.partition_id, "schema_status": "breaking", "rows": src.row_count,
                "schema_events": [e.__dict__ for e in sres.events]}

    load_action = load_raw(conn, src, df, run_id)
    t = lap("raw_landing", t)

    dfd = profiling.with_derived(df)
    prof = profiling.profile(dfd)
    db.copy_df(conn, "dq.profile_snapshots", prof.select(
        pl.lit(run_id).alias("run_id"), pl.lit(src.partition_id).alias("partition_id"), *prof.columns))
    t = lap("profiling", t)

    ev = rules.evaluate(df, ruleset, src.year_month)
    flags = rules.record_flags(ev, ruleset)
    quarantine = rules.quarantine_rows(df, flags, ruleset)
    t = lap("rules", t)
    q_stats = persist_rule_results(conn, run_id, src.partition_id, ev.summary, flags, quarantine)
    t = lap("persist_quality", t)

    scores = quality_scores(df.height, ev, ruleset, flags, th["quality_score"]["warning_weight"])
    anomalies = []
    if run_anomalies:
        invalid_ids = flags.filter(~pl.col("is_valid")).select("record_id")
        valid = dfd.join(invalid_ids, on="record_id", how="anti")
        anomalies = run_anomaly(conn, run_id, src.partition_id, valid, th["anomaly"])
        t = lap("anomaly", t)

    drift_rows = []
    if reference is not None:
        ref_df, _ = read_partition(reference)
        if ref_df is not None:
            drift_rows = drift.compare(profiling.with_derived(ref_df), dfd, th["drift"])
            db.insert_dicts(conn, "dq.drift_results", [
                {"run_id": run_id, "partition_id": src.partition_id,
                 "reference_partition_id": reference.partition_id, **r} for r in drift_rows])
        t = lap("drift", t)

    duration = time.perf_counter() - t0
    month_end = _month_end(src.year_month)
    lag = None
    if src.source_last_modified:
        lag = (parsedate_to_datetime(src.source_last_modified) - month_end).total_seconds() / 86400
    age = (datetime.now(timezone.utc) - month_end).total_seconds() / 86400
    conn.execute(
        """INSERT INTO dq.partition_quality (run_id, partition_id, rows_total, valid_rows, quarantined_records,
               warning_only_records, valid_record_rate, quality_score, dimension_scores, schema_status,
               unexpected_schema_changes, source_lag_days, data_age_days, duration_s, rows_per_sec, stage_timings)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        (run_id, src.partition_id, df.height, scores["valid_rows"], scores["quarantined_records"],
         scores["warning_only_records"], scores["valid_record_rate"], scores["quality_score"],
         json.dumps(scores["dimension_scores"]), status, sres.unexpected_changes, lag, age, duration,
         df.height / duration, json.dumps(timings)))
    conn.commit()

    metrics.record_partition(src.partition_id, df.height, ev.summary, scores, drift_rows, duration)
    return {"partition_id": src.partition_id, "schema_status": status, "load_action": load_action,
            "rows": df.height, **scores, **q_stats, "duration_s": round(duration, 2),
            "rows_per_sec": round(df.height / duration), "timings": timings,
            "drift_alerts": sum(r["status"] == "alert" for r in drift_rows),
            "anomalies": {a["method"]: a["anomalies"] for a in anomalies}}


def run(sources: list[PartitionSource] | None = None, trigger: str = "cli", run_anomalies: bool = True,
        references: dict[str, PartitionSource] | None = None, dsn: str | None = None) -> dict:
    """Process partitions in chronological order; each partition's drift reference is the previous one."""
    sources = sources if sources is not None else manifest_sources()
    ruleset = rules.load_ruleset()
    run_id = str(uuid.uuid4())
    started = time.perf_counter()
    with db.connect(dsn) as conn:
        conn.execute(
            """INSERT INTO dq.pipeline_runs (run_id, started_at, status, trigger, ruleset_version, rules_sha256,
                   code_version, partitions) VALUES (%s, now(), 'running', %s, %s, %s, %s, %s)""",
            (run_id, trigger, ruleset.version, ruleset.sha256, code_version(), [s.partition_id for s in sources]))
        for rec in rules.ruleset_as_records(ruleset):
            conn.execute(
                """INSERT INTO dq.rule_definitions (rule_id, rule_version, ruleset_version, severity, dimension,
                       rule_type, description, definition) VALUES (%(rule_id)s, %(rule_version)s,
                       %(ruleset_version)s, %(severity)s, %(dimension)s, %(rule_type)s, %(description)s,
                       %(definition)s) ON CONFLICT (rule_id, rule_version) DO NOTHING""", rec)
        conn.commit()
        results = []
        try:
            all_known = manifest_sources()
            for src in sources:
                ref = (references or {}).get(src.partition_id)
                if ref is None:
                    # only partitions whose raw file is actually present can serve as drift reference
                    prev = [s for s in all_known if s.service == src.service and s.year_month < src.year_month
                            and s.path.exists()]
                    ref = prev[-1] if prev else None
                log.info("processing %s (reference=%s)", src.partition_id, ref.partition_id if ref else None)
                results.append(process_partition(conn, run_id, src, ruleset, ref, run_anomalies))
            status, error = "success", None
        except Exception as exc:  # recorded, then re-raised
            conn.rollback()
            status, error = "failed", repr(exc)
            raise
        finally:
            duration = time.perf_counter() - started
            rows = sum(r.get("rows") or 0 for r in results)
            conn.execute("""UPDATE dq.pipeline_runs SET finished_at=now(), status=%s, rows_processed=%s,
                            duration_s=%s, error=%s WHERE run_id=%s""", (status, rows, duration, error, run_id))
            conn.commit()
            metrics.RUN_DURATION.observe(duration)
            metrics.push()
    return {"run_id": run_id, "status": status, "duration_s": round(duration, 2), "rows_processed": rows,
            "partitions": results}
