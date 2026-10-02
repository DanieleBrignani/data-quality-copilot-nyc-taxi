"""Controlled failure demo.

Builds small fixture files from REAL rule-valid records (so everything else about them is
realistic), injects one known defect per fixture, runs the full pipeline on them in an isolated
database (`dqc_demo`) and asserts that each defect is caught by the expected control.
Fixtures live in data/fixtures/ and are never mixed with the benchmark partitions.
"""

from __future__ import annotations

import json
from pathlib import Path

import polars as pl

from dqc import config, db, pipeline, rules

DEMO_DB = "dqc_demo"
BASE_PARTITION = "yellow_2025-01"
N_BASE = 2_000


def ensure_demo_db() -> str:
    return db.recreate_database(DEMO_DB)


def _clean_base(fixtures_dir: Path) -> pl.DataFrame:
    """2,000 real Jan-2025 records that pass every rule (critical and warning)."""
    src = next(s for s in pipeline.manifest_sources() if s.partition_id == BASE_PARTITION)
    df, _ = pipeline.read_partition(src)
    ev = rules.evaluate(df.head(200_000), rules.load_ruleset(), "2025-01")
    flagged = rules.record_flags(ev, rules.load_ruleset()).select("record_id")
    clean = df.head(200_000).join(flagged, on="record_id", how="anti").sample(N_BASE, seed=7)
    return clean.drop("record_id", "source_row")


def build_fixtures(fixtures_dir: Path = config.FIXTURES_DIR) -> list[dict]:
    fixtures_dir.mkdir(parents=True, exist_ok=True)
    base = _clean_base(fixtures_dir)
    specs = []

    def write(name: str, frame: pl.DataFrame, expect: dict, description: str):
        path = fixtures_dir / f"fixture_{name}_2025-01.parquet"
        frame.write_parquet(path)
        specs.append({"name": name, "path": path.name, "rows": frame.height, "description": description,
                      "expect": expect})

    # 1. schema break: a mandatory column disappears and another changes type
    write("schema_break", base.drop("fare_amount").with_columns(pl.col("trip_distance").cast(pl.String)),
          {"schema_status": "breaking", "rows_propagated": 0},
          "fare_amount column removed and trip_distance delivered as string")

    # 2. duplicates: 25 records delivered twice
    write("duplicate", pl.concat([base, base.head(25)]),
          {"rule": "DQ050_exact_duplicate", "failed_rows": 25}, "25 rows re-sent (exact copies)")

    # 3. invalid amount: 30 negative fares, 10 absurd fares
    idx = pl.int_range(pl.len())
    write("invalid_amount", base.with_columns(
        fare_amount=pl.when(idx < 30).then(-pl.col("fare_amount").abs() - 1)
        .when(idx < 40).then(pl.lit(25_000.0)).otherwise(pl.col("fare_amount"))),
        {"rule": "DQ021_fare_amount_range", "failed_rows": 40}, "30 negative fares and 10 fares of $25,000")

    # 4. missing mandatory field: 20 null pickup timestamps, 15 null drop-off zones
    write("missing_mandatory", base.with_columns(
        tpep_pickup_datetime=pl.when(idx < 20).then(None).otherwise(pl.col("tpep_pickup_datetime")),
        DOLocationID=pl.when((idx >= 20) & (idx < 35)).then(None).otherwise(pl.col("DOLocationID"))),
        {"rule": "DQ001_mandatory_fields_not_null", "failed_rows": 35},
        "20 null pickup timestamps + 15 null drop-off zones")

    # 5. impossible trip duration: 12 drop-offs before pickup
    write("impossible_duration", base.with_columns(
        tpep_dropoff_datetime=pl.when(idx < 12).then(pl.col("tpep_pickup_datetime") - pl.duration(minutes=5))
        .otherwise(pl.col("tpep_dropoff_datetime"))),
        {"rule": "DQ010_pickup_before_dropoff", "failed_rows": 12}, "12 drop-offs 5 minutes before pickup")

    # 6. invalid passenger count
    write("invalid_passenger_count", base.with_columns(
        passenger_count=pl.when(idx < 8).then(pl.lit(9, pl.Int64)).otherwise(pl.col("passenger_count"))),
        {"rule": "DQ024_passenger_count_max", "failed_rows": 8}, "8 trips with 9 passengers")

    (fixtures_dir / "fixtures_manifest.json").write_text(json.dumps(specs, indent=2), encoding="utf-8")
    return specs


def run_demo() -> dict:
    specs = build_fixtures()
    dsn = ensure_demo_db()
    sources = [pipeline.PartitionSource.from_file(config.FIXTURES_DIR / s["path"], f"fixture_{s['name']}", "2025-01")
               for s in specs]
    for s in sources:
        s.service = "fixture"
    res = pipeline.run(sources, trigger="failure_demo", run_anomalies=False, dsn=dsn)
    by_pid = {p["partition_id"]: p for p in res["partitions"]}
    checks = []
    with db.connect(dsn) as conn:
        for s in specs:
            pid = f"fixture_{s['name']}"
            exp, got = s["expect"], by_pid[pid]
            if "schema_status" in exp:
                n_raw = conn.execute("SELECT count(*) FROM raw.yellow_trips WHERE partition_id=%s", (pid,)).fetchone()[0]
                n_q = conn.execute("SELECT count(*) FROM dq.quarantine WHERE partition_id=%s", (pid,)).fetchone()[0]
                events = [e["check"] + ":" + str(e["column"]) for e in got.get("schema_events", [])
                          if e["severity"] == "critical"]
                ok = got["schema_status"] == "breaking" and n_raw == 0 and n_q == 0
                checks.append({"fixture": s["name"], "expected": exp, "detected": ok,
                               "observed": {"schema_status": got["schema_status"], "raw_rows_loaded": n_raw,
                                            "critical_schema_events": events}})
                continue
            failed = conn.execute(
                "SELECT failed_rows FROM dq.rule_results WHERE run_id=%s AND partition_id=%s AND rule_id=%s",
                (res["run_id"], pid, exp["rule"])).fetchone()[0]
            quarantined = conn.execute(
                "SELECT count(DISTINCT record_id) FROM dq.quarantine WHERE partition_id=%s AND failed_rule=%s",
                (pid, exp["rule"])).fetchone()[0]
            ok = failed == exp["failed_rows"] and quarantined == exp["failed_rows"]
            checks.append({"fixture": s["name"], "expected": exp, "detected": ok,
                           "observed": {"failed_rows": failed, "quarantined": quarantined,
                                        "valid_record_rate": round(got["valid_record_rate"], 3)}})
    out = {"run_id": res["run_id"], "database": DEMO_DB, "checks": checks,
           "all_detected": all(c["detected"] for c in checks)}
    config.REPORTS_DIR.mkdir(exist_ok=True)
    (config.REPORTS_DIR / "failure_demo.json").write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    return out

