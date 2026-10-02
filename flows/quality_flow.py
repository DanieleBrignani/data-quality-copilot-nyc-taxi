"""Prefect orchestration of the full quality workflow.

    python flows/quality_flow.py --months 2024-11 2024-12 2025-01 2025-02

ingest (idempotent) -> verify raw hashes -> quality pipeline (per partition, chronological)
-> dbt build (models + tests) -> soda contract scan -> SLO gate -> copilot suggestions (optional)
Every task is a thin wrapper around the same functions the CLI uses, so there is one code path.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

from prefect import flow, get_run_logger, task

from dqc import gate, ingest, pipeline

ROOT = Path(__file__).resolve().parents[1]
BIN = Path(sys.executable).parent


@task(retries=2, retry_delay_seconds=30)
def ingest_month(month: str) -> dict:
    r = ingest.ingest_month(month)
    return {k: r[k] for k in ("partition_id", "action", "row_count", "sha256")}


@task
def verify_raw() -> None:
    bad = [r for r in ingest.verify_raw_layer() if not r["ok"]]
    if bad:
        raise ingest.IntegrityError(f"raw layer tampered: {bad}")


@task
def run_quality(partition_ids: list[str]) -> dict:
    srcs = [s for s in pipeline.manifest_sources() if s.partition_id in partition_ids]
    return pipeline.run(srcs, trigger="prefect")


def _cmd(args: list[str], cwd: Path) -> None:
    log = get_run_logger()
    env = {**os.environ, "DQC_PG_HOST": os.environ.get("DQC_PG_HOST", "localhost"),
           "DQC_PG_PORT": os.environ.get("DQC_PG_PORT", "5433"), "DQC_PG_USER": "dqc",
           "DQC_PG_PASSWORD": "dqc", "DQC_PG_DB": "dqc"}
    res = subprocess.run(args, cwd=cwd, env=env, capture_output=True, text=True)
    log.info(res.stdout[-4000:])
    if res.returncode:
        log.error(res.stderr[-4000:])
        raise RuntimeError(f"{args[0]} failed ({res.returncode})")


@task
def dbt_build() -> None:
    _cmd([str(BIN / "dbt"), "build", "--profiles-dir", "."], ROOT / "dbt")


@task
def soda_scan() -> None:
    _cmd([str(BIN / "soda"), "scan", "-d", "dqc", "-c", "configuration.yml", "checks_clean_trips.yml"], ROOT / "soda")


@task
def slo_gate() -> list[str]:
    breaches = gate.slo_breaches()
    if breaches:
        get_run_logger().warning("SLO breaches: %s", breaches)
    return breaches


@task
def copilot_suggestions(limit: int) -> int:
    from dqc import copilot
    return len(copilot.explain_latest(limit))


@flow(name="nyc-taxi-data-quality")
def quality_flow(months: list[str], copilot_limit: int = 0) -> dict:
    ingested = [ingest_month(m) for m in months]
    verify_raw()
    result = run_quality([i["partition_id"] for i in ingested])
    dbt_build()
    soda_scan()
    breaches = slo_gate()
    n = copilot_suggestions(copilot_limit) if copilot_limit else 0
    return {"run_id": result["run_id"], "slo_breaches": breaches, "copilot_suggestions": n}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--months", nargs="+", default=["2024-11", "2024-12", "2025-01", "2025-02"])
    ap.add_argument("--copilot", type=int, default=0)
    a = ap.parse_args()
    print(quality_flow(a.months, a.copilot))
