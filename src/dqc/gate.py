"""CI quality gate.

A committed random sample of REAL records (data/fixtures/ci_real_sample_yellow_2025-01.parquet) is
run through the schema contract + rule engine on every push. Its quality score is compared with
the committed baseline (ci/quality_baseline.json):

* score drops by more than `max_score_drop` points          -> FAIL (a change degraded quality)
* valid-record rate drops by more than `max_valid_rate_drop_pp` -> FAIL
* score RISES by more than `max_score_drop` points           -> FAIL (unexplained improvement: a rule was
  probably loosened or removed; re-baseline deliberately with --update-baseline and justify it in the PR)

With --slo the gate also checks the latest partition results in the warehouse against the SLOs.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import polars as pl

from dqc import config, pipeline, rules, schema

SAMPLE_PATH = config.FIXTURES_DIR / "ci_real_sample_yellow_2025-01.parquet"
SAMPLE_ROWS = 50_000


def make_ci_sample(partition_id: str = "yellow_2025-01", path: Path = SAMPLE_PATH) -> Path:
    src = next(s for s in pipeline.manifest_sources() if s.partition_id == partition_id)
    pl.read_parquet(src.path).sample(SAMPLE_ROWS, seed=1).write_parquet(path)
    return path


def evaluate_sample(path: Path = SAMPLE_PATH, year_month: str = "2025-01", raw: pl.DataFrame | None = None) -> dict:
    raw = pl.read_parquet(path) if raw is None else raw
    df, sres = schema.validate_and_normalise(raw)
    if df is None:
        return {"schema_breaking": True, "quality_score": 0.0, "valid_record_rate": 0.0,
                "schema_events": [e.__dict__ for e in sres.events]}
    df = df.with_row_index("source_row").with_columns(record_id=pl.format("ci:{}", pl.col("source_row")))
    rs = rules.load_ruleset()
    ev = rules.evaluate(df, rs, year_month)
    flags = rules.record_flags(ev, rs)
    sc = pipeline.quality_scores(df.height, ev, rs, flags, config.thresholds()["quality_score"]["warning_weight"])
    return {"schema_breaking": False, "rows": df.height, "ruleset_version": rs.version,
            "quality_score": round(sc["quality_score"], 4), "valid_record_rate": round(sc["valid_record_rate"], 4),
            "rule_failure_rates": {r["rule_id"]: round(r["failure_rate"], 6)
                                   for r in ev.summary.iter_rows(named=True)}}


def compare(current: dict, baseline: dict, cfg: dict) -> list[str]:
    problems = []
    if current.get("schema_breaking"):
        return ["schema contract broken on CI sample"]
    d_score = current["quality_score"] - baseline["quality_score"]
    d_valid = current["valid_record_rate"] - baseline["valid_record_rate"]
    if d_score < -cfg["max_score_drop"]:
        problems.append(f"quality_score dropped {d_score:+.3f} pts (limit -{cfg['max_score_drop']})")
    if d_valid < -cfg["max_valid_rate_drop_pp"]:
        problems.append(f"valid_record_rate dropped {d_valid:+.3f} pp (limit -{cfg['max_valid_rate_drop_pp']})")
    if d_score > cfg["max_score_drop"]:
        problems.append(f"quality_score rose {d_score:+.3f} pts without a baseline update — was a rule loosened?")
    return problems


def slo_breaches(dsn: str | None = None) -> list[str]:
    from dqc import db
    slo = config.thresholds()["slo"]
    df = db.query_df("""
        SELECT DISTINCT ON (pq.partition_id) pq.partition_id, pq.valid_record_rate, pq.quality_score,
               pq.unexpected_schema_changes, pq.source_lag_days, pq.duration_s
        FROM dq.partition_quality pq JOIN dq.pipeline_runs r USING (run_id)
        JOIN dq.dataset_partitions p USING (partition_id)
        WHERE p.service = 'yellow'
        ORDER BY pq.partition_id, r.started_at DESC""", dsn=dsn)
    out = []
    for r in df.iter_rows(named=True):
        if r["valid_record_rate"] < slo["min_valid_record_rate_pct"]:
            out.append(f"{r['partition_id']}: valid_record_rate {r['valid_record_rate']:.2f} < {slo['min_valid_record_rate_pct']}")
        if r["quality_score"] < slo["min_quality_score"]:
            out.append(f"{r['partition_id']}: quality_score {r['quality_score']:.2f} < {slo['min_quality_score']}")
        if r["unexpected_schema_changes"] > slo["max_unexpected_schema_changes"]:
            out.append(f"{r['partition_id']}: {r['unexpected_schema_changes']} unexpected schema changes")
        if r["source_lag_days"] is not None and r["source_lag_days"] > slo["max_freshness_days"]:
            out.append(f"{r['partition_id']}: source lag {r['source_lag_days']:.1f}d > {slo['max_freshness_days']}d")
    return out


def main(update_baseline: bool = False, check_slo: bool = False) -> int:
    cfg = config.thresholds()["ci_gate"]
    baseline_path = config.ROOT / cfg["baseline_file"]
    if not SAMPLE_PATH.exists():
        make_ci_sample()
    current = evaluate_sample()
    if update_baseline or not baseline_path.exists():
        baseline_path.parent.mkdir(exist_ok=True)
        baseline_path.write_text(json.dumps(current, indent=2), encoding="utf-8")
        print(f"baseline written: score={current['quality_score']} valid={current['valid_record_rate']}")
        return 0
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    problems = compare(current, baseline, cfg)
    for rid, rate in current.get("rule_failure_rates", {}).items():
        before = baseline.get("rule_failure_rates", {}).get(rid)
        if before is None or abs(rate - before) > 1e-9:
            print(f"  rule {rid}: {before} -> {rate}")
    if check_slo:
        problems += slo_breaches()
    print(json.dumps({"baseline_score": baseline["quality_score"], "current_score": current["quality_score"],
                      "baseline_valid_rate": baseline["valid_record_rate"],
                      "current_valid_rate": current["valid_record_rate"], "problems": problems}, indent=2))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
