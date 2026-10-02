"""Command line entry point: `python -m dqc <command>`."""

from __future__ import annotations

import argparse
import json
import logging
import sys

from dqc import ingest


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    p = argparse.ArgumentParser(prog="dqc")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("ingest", help="download TLC months into the immutable raw layer")
    s.add_argument("months", nargs="+", help="YYYY-MM")
    s.add_argument("--service", default="yellow")

    sub.add_parser("verify-raw", help="re-hash raw files against the manifest")
    sub.add_parser("init-db", help="create schemas/tables")

    s = sub.add_parser("run", help="run the quality pipeline")
    s.add_argument("--partitions", nargs="*", help="partition ids (default: all in manifest)")
    s.add_argument("--no-anomaly", action="store_true")
    s.add_argument("--trigger", default="cli", help="label stored on the run (reproduce | rerun | cli)")

    s = sub.add_parser("demo-failures", help="run the pipeline on controlled failure fixtures")
    s = sub.add_parser("benchmark", help="precision / recall / FPR on labelled injected errors")
    s.add_argument("--partition", default="yellow_2025-01")
    s.add_argument("--sample", type=int, default=200_000)

    s = sub.add_parser("gate", help="CI quality gate against the committed baseline")
    s.add_argument("--update-baseline", action="store_true")
    s.add_argument("--slo", action="store_true", help="also check warehouse partitions against SLOs")

    s = sub.add_parser("copilot", help="generate audited suggestions for the latest incidents")
    s.add_argument("--limit", type=int, default=5)

    s = sub.add_parser("ml", help="expected-fare model: train | score")
    s.add_argument("action", choices=["train", "score"])

    sub.add_parser("report", help="write reports/results.json + results.md from the warehouse")

    a = p.parse_args(argv)

    if a.cmd == "ingest":
        for m in a.months:
            r = ingest.ingest_month(m, a.service)
            print(json.dumps({k: r[k] for k in ("partition_id", "action", "row_count", "sha256")}))
        ingest.ingest_zone_lookup()
    elif a.cmd == "verify-raw":
        res = ingest.verify_raw_layer()
        print(json.dumps(res, indent=2))
        return 0 if all(r["ok"] for r in res) else 1
    elif a.cmd == "init-db":
        from dqc import db
        with db.connect() as conn:
            db.init_schema(conn)
    elif a.cmd == "run":
        from dqc import pipeline
        srcs = pipeline.manifest_sources()
        if a.partitions:
            srcs = [s for s in srcs if s.partition_id in a.partitions]
        res = pipeline.run(srcs, trigger=a.trigger, run_anomalies=not a.no_anomaly)
        print(json.dumps(res, indent=2, default=str))
    elif a.cmd == "demo-failures":
        from dqc import failure_demo
        res = failure_demo.run_demo()
        print(json.dumps(res, indent=2, default=str))
        return 0 if res["all_detected"] else 1
    elif a.cmd == "benchmark":
        from dqc import benchmark
        print(json.dumps(benchmark.run(a.partition, a.sample), indent=2, default=str))
    elif a.cmd == "gate":
        from dqc import gate
        return gate.main(update_baseline=a.update_baseline, check_slo=a.slo)
    elif a.cmd == "copilot":
        from dqc import copilot
        print(json.dumps(copilot.explain_latest(a.limit), indent=2, default=str))
    elif a.cmd == "ml":
        from dqc.ml import fare_model
        res = fare_model.train() if a.action == "train" else fare_model.score_partitions()
        print(json.dumps(res, indent=2, default=str))
    elif a.cmd == "report":
        from dqc import report
        print(report.write())
    return 0


if __name__ == "__main__":
    sys.exit(main())
