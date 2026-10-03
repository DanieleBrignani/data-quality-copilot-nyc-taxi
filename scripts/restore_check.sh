#!/usr/bin/env bash
# Recovery drill: restores a backup into a scratch database and proves it is complete by comparing
# row counts of every dq table with the live database. Writes reports/recovery_check.json.
#   scripts/restore_check.sh [backups/dq_....dump]      (default: newest backup; takes one first if none)
# To restore for real into an empty warehouse:
#   docker compose exec -T postgres pg_restore -U "$DQC_PG_USER" -d "$DQC_PG_DB" --no-owner < backups/<file>
set -euo pipefail
cd "$(dirname "$0")/.."
[ -f .env ] || { echo "missing .env (see .env.example)"; exit 1; }
set -a; . ./.env; set +a
U="${DQC_PG_USER:-dqc}"; DB="${DQC_PG_DB:-dqc}"; SCRATCH="dqc_restore_check"
dump="${1:-$(ls -t backups/dq_*.dump 2>/dev/null | head -1 || true)}"
[ -n "$dump" ] || dump="$(scripts/backup.sh)"
psql() { docker compose exec -T postgres psql -U "$U" -At "$@"; }

t0=$(date +%s)
psql -d "$DB" -c "DROP DATABASE IF EXISTS $SCRATCH WITH (FORCE)" -c "CREATE DATABASE $SCRATCH" > /dev/null
docker compose exec -T postgres pg_restore -U "$U" -d "$SCRATCH" --no-owner --no-privileges < "$dump"
t1=$(date +%s)

counts() {   # table|rows for every table of schema dq (exact counts)
  psql -d "$1" -c "SELECT table_name || '|' || (xpath('/row/c/text()', query_to_xml('select count(*) as c from dq.' || quote_ident(table_name), false, true, '')))[1]::text FROM information_schema.tables WHERE table_schema='dq' ORDER BY 1"
}
live="$(counts "$DB")"; restored="$(counts "$SCRATCH")"
psql -d "$DB" -c "DROP DATABASE $SCRATCH WITH (FORCE)" > /dev/null

ok=true; [ "$live" = "$restored" ] || ok=false
mkdir -p reports
{
  echo "{"
  echo "  \"backup_file\": \"$(basename "$dump")\","
  echo "  \"backup_bytes\": $(wc -c < "$dump" | tr -d ' '),"
  echo "  \"restore_seconds\": $((t1 - t0)),"
  echo "  \"tables\": {"
  echo "$restored" | awk -F'|' '{printf "%s    \"%s\": %s", (NR>1?",\n":""), $1, $2} END {print ""}'
  echo "  },"
  echo "  \"row_counts_match_live\": $ok"
  echo "}"
} > reports/recovery_check.json
cat reports/recovery_check.json
$ok || { echo "RESTORE DOES NOT MATCH LIVE DATABASE"; exit 1; }
