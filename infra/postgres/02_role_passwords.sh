#!/bin/sh
# Runs once, when the Postgres data directory is first initialised (docker-entrypoint-initdb.d).
# Sets the service-role passwords from the container environment; nothing is hardcoded in the repository.
set -eu
: "${DQC_COPILOT_PASSWORD:?DQC_COPILOT_PASSWORD is required}"
: "${DQC_READER_PASSWORD:?DQC_READER_PASSWORD is required}"
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
     -v copilot_pw="$DQC_COPILOT_PASSWORD" -v reader_pw="$DQC_READER_PASSWORD" <<'SQL'
ALTER ROLE dqc_copilot PASSWORD :'copilot_pw';
ALTER ROLE dqc_reader  PASSWORD :'reader_pw';
SQL
