#!/usr/bin/env bash
# Backs up what cannot be rebuilt from the raw files: the `dq` schema (run history, quarantine with its
# human review status, copilot suggestions, model registry).
# `raw` and `analytics` are NOT backed up on purpose: they are rebuilt deterministically from the immutable,
# hash-verified raw files (python -m dqc run; dbt build).
#   scripts/backup.sh                     -> backups/dq_<UTC timestamp>.dump
set -euo pipefail
cd "$(dirname "$0")/.."
[ -f .env ] || { echo "missing .env (see .env.example)"; exit 1; }
set -a; . ./.env; set +a
mkdir -p backups
out="backups/dq_$(date -u +%Y%m%dT%H%M%SZ).dump"
docker compose exec -T postgres pg_dump -U "${DQC_PG_USER:-dqc}" -d "${DQC_PG_DB:-dqc}" -n dq -Fc > "$out"
[ -s "$out" ] || { echo "backup is empty"; rm -f "$out"; exit 1; }
echo "$out"
