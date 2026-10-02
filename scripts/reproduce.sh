#!/usr/bin/env bash
# Reproduces every number in README.md / reports/results.md from scratch.
# Raw files are kept (immutable, hash-verified); the WAREHOUSE is wiped and rebuilt.
#   PY=/path/to/python scripts/reproduce.sh
set -uo pipefail
cd "$(dirname "$0")/.."
PY="${PY:-python}"
BIN="$(dirname "$(command -v "$PY")")"
export PYTHONIOENCODING=utf-8 DQC_PG_HOST=localhost DQC_PG_PORT=5433 DQC_PG_USER=dqc DQC_PG_PASSWORD=dqc DQC_PG_DB=dqc
MONTHS="2024-11 2024-12 2025-01 2025-02"
step() { echo; echo "=== $* ==="; }

step "fresh warehouse"
docker compose down -v
docker compose up -d postgres
until docker compose exec -T postgres pg_isready -U dqc -d dqc >/dev/null 2>&1; do sleep 2; done
sleep 3

step "ingest (idempotent) + verify immutable raw layer"
"$PY" -m dqc ingest $MONTHS
"$PY" -m dqc verify-raw || exit 1

step "quality pipeline — reference run"
"$PY" -m dqc run --trigger reproduce > reports/run_reproduce.json || exit 1

step "quality pipeline — rerun on identical inputs (idempotency check)"
"$PY" -m dqc run --trigger rerun > reports/run_rerun.json || exit 1

step "dbt build (models + tests)"
(cd dbt && "$BIN/dbt" build --profiles-dir .) | tee reports/dbt_build.log | tail -3

step "soda contract (SLO check is EXPECTED to fail on 2025-02 — see README)"
(cd soda && "$BIN/soda" scan -d dqc -c configuration.yml checks_clean_trips.yml) > reports/soda_scan.log 2>&1
echo "soda exit code: $?" | tee -a reports/soda_scan.log

step "ML: train fare + distance models (2024-11), select + calibrate (2024-12), backtest, score every partition"
# training is deterministic and idempotent: an identical retrained artifact does not create a new version
"$PY" -W ignore -m dqc ml train > reports/ml_train.json 2> /dev/null || exit 1
"$PY" -W ignore -m dqc ml score > reports/ml_score.json 2> /dev/null || exit 1
for m in fare_model distance_model; do
  "$PY" -W ignore -m dqc.ml.review sample $m > /dev/null 2>&1 && "$PY" -W ignore -m dqc.ml.review summarize $m > /dev/null || exit 1
done

step "failure demo, benchmark, anomaly review, copilot"
"$PY" -m dqc demo-failures > /dev/null || exit 1
"$PY" -m dqc benchmark > /dev/null || exit 1
"$PY" -m dqc.anomaly_review sample > /dev/null && "$PY" -m dqc.anomaly_review summarize || exit 1
"$PY" -m dqc copilot --limit 5 > reports/copilot_suggestions.json

step "gates"
"$PY" -m dqc gate > reports/gate.log; echo "gate (code change) exit: $?" | tee -a reports/gate.log
"$PY" -m dqc gate --slo > reports/gate_slo.log; echo "gate --slo exit: $?" | tee -a reports/gate_slo.log

step "report"
"$PY" -m dqc report > /dev/null
docker compose up -d
echo "done -> reports/results.md"
