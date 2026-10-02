-- Data Quality Copilot — warehouse schema.
-- raw       : landing copy of the immutable parquet files (append/replace per partition, never updated)
-- dq        : quality metadata, audit trail, quarantine, copilot suggestions
-- analytics : dbt models (stg_trips, int_trip_quality, fct_clean_trips, fct_quality_events)

CREATE SCHEMA IF NOT EXISTS raw;
CREATE SCHEMA IF NOT EXISTS dq;
CREATE SCHEMA IF NOT EXISTS analytics;

-- ---------------------------------------------------------------- raw
CREATE TABLE IF NOT EXISTS raw.yellow_trips (
    partition_id          text        NOT NULL,
    record_id             text        NOT NULL,
    source_row            bigint      NOT NULL,
    vendor_id             integer,
    pickup_datetime       timestamp,
    dropoff_datetime      timestamp,
    passenger_count       integer,
    trip_distance         double precision,
    ratecode_id           integer,
    store_and_fwd_flag    text,
    pu_location_id        integer,
    do_location_id        integer,
    payment_type          integer,
    fare_amount           double precision,
    extra                 double precision,
    mta_tax               double precision,
    tip_amount            double precision,
    tolls_amount          double precision,
    improvement_surcharge double precision,
    total_amount          double precision,
    congestion_surcharge  double precision,
    airport_fee           double precision,
    cbd_congestion_fee    double precision,
    loaded_run_id         uuid        NOT NULL,
    PRIMARY KEY (partition_id, record_id)
) PARTITION BY LIST (partition_id);

-- ---------------------------------------------------------------- dq: runs & partitions
CREATE TABLE IF NOT EXISTS dq.pipeline_runs (
    run_id            uuid PRIMARY KEY,
    started_at        timestamptz NOT NULL,
    finished_at       timestamptz,
    status            text NOT NULL,          -- running | success | failed
    trigger           text,
    ruleset_version   text,
    rules_sha256      text,
    code_version      text,
    partitions        text[],
    rows_processed    bigint,
    duration_s        double precision,
    error             text
);

CREATE TABLE IF NOT EXISTS dq.dataset_partitions (
    partition_id        text PRIMARY KEY,
    service             text NOT NULL,
    year_month          text NOT NULL,
    source_url          text NOT NULL,
    file_format         text NOT NULL,
    sha256              text NOT NULL,
    size_bytes          bigint,
    row_count           bigint,
    source_schema       jsonb,
    downloaded_at       timestamptz,
    source_last_modified timestamptz,
    loaded_sha256       text,                 -- sha of the file currently loaded in raw.yellow_trips
    loaded_run_id       uuid,
    loaded_at           timestamptz
);

-- ---------------------------------------------------------------- dq: rules & results
CREATE TABLE IF NOT EXISTS dq.rule_definitions (
    rule_id          text NOT NULL,
    rule_version     integer NOT NULL,
    ruleset_version  text NOT NULL,
    severity         text NOT NULL,
    dimension        text NOT NULL,
    rule_type        text NOT NULL,
    description      text NOT NULL,
    definition       jsonb NOT NULL,
    first_seen_at    timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (rule_id, rule_version)
);

CREATE TABLE IF NOT EXISTS dq.schema_checks (
    run_id        uuid NOT NULL,
    partition_id  text NOT NULL,
    check_name    text NOT NULL,
    column_name   text,
    severity      text NOT NULL,
    detail        text,
    checked_at    timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS dq.rule_results (
    run_id           uuid NOT NULL,
    partition_id     text NOT NULL,
    rule_id          text NOT NULL,
    rule_version     integer NOT NULL,
    severity         text NOT NULL,
    dimension        text NOT NULL,
    columns          text,
    records_checked  bigint NOT NULL,
    failed_rows      bigint NOT NULL,
    failure_rate     double precision NOT NULL,
    evaluated_at     timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (run_id, partition_id, rule_id)
);

-- Current record-level verdict (only records with >= 1 failed rule). Replaced per partition.
CREATE TABLE IF NOT EXISTS dq.record_quality (
    partition_id     text NOT NULL,
    record_id        text NOT NULL,
    is_valid         boolean NOT NULL,
    failed_critical  text[] NOT NULL,
    failed_warning   text[] NOT NULL,
    run_id           uuid NOT NULL,
    PRIMARY KEY (partition_id, record_id)
);

CREATE TABLE IF NOT EXISTS dq.partition_quality (
    run_id                  uuid NOT NULL,
    partition_id            text NOT NULL,
    rows_total              bigint NOT NULL,
    valid_rows              bigint NOT NULL,
    quarantined_records     bigint NOT NULL,
    warning_only_records    bigint NOT NULL,
    valid_record_rate       double precision NOT NULL,
    quality_score           double precision NOT NULL,
    dimension_scores        jsonb,
    schema_status           text NOT NULL,     -- ok | additive_change | breaking (rejected)
    unexpected_schema_changes integer NOT NULL,
    source_lag_days         double precision,  -- TLC publication delay after month end
    data_age_days           double precision,  -- run time - month end
    duration_s              double precision,
    rows_per_sec            double precision,
    stage_timings           jsonb,
    computed_at             timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (run_id, partition_id)
);

CREATE TABLE IF NOT EXISTS dq.profile_snapshots (
    run_id            uuid NOT NULL,
    partition_id      text NOT NULL,
    column_name       text NOT NULL,
    dtype             text,
    row_count         bigint,
    null_count        bigint,
    null_rate         double precision,
    distinct_count    bigint,
    cardinality_ratio double precision,
    min               double precision,
    max               double precision,
    min_text          text,
    max_text          text,
    mean              double precision,
    median            double precision,
    std               double precision,
    p01 double precision, p05 double precision, p25 double precision,
    p75 double precision, p95 double precision, p99 double precision,
    PRIMARY KEY (run_id, partition_id, column_name)
);

CREATE TABLE IF NOT EXISTS dq.drift_results (
    run_id                  uuid NOT NULL,
    partition_id            text NOT NULL,
    reference_partition_id  text NOT NULL,
    column_name             text NOT NULL,
    metric                  text NOT NULL,
    value                   double precision,
    threshold               double precision,
    status                  text NOT NULL,     -- ok | warn | alert | info | n/a
    PRIMARY KEY (run_id, partition_id, column_name, metric)
);

CREATE TABLE IF NOT EXISTS dq.anomaly_results (
    run_id           uuid NOT NULL,
    partition_id     text NOT NULL,
    method           text NOT NULL,
    records_scored   bigint NOT NULL,
    anomalies        bigint NOT NULL,
    anomaly_rate     double precision NOT NULL,
    runtime_s        double precision NOT NULL,
    params           jsonb,
    per_feature      jsonb,
    PRIMARY KEY (run_id, partition_id, method)
);

CREATE TABLE IF NOT EXISTS dq.anomaly_records (
    run_id        uuid NOT NULL,
    partition_id  text NOT NULL,
    method        text NOT NULL,
    record_id     text NOT NULL,
    score         double precision NOT NULL,
    features      jsonb,
    PRIMARY KEY (run_id, method, record_id)
);

-- ---------------------------------------------------------------- dq: quarantine
-- One row per (record, failed critical rule). Idempotent: reruns upsert on the natural key,
-- records that stop failing are marked resolved (never deleted); review_status is preserved.
CREATE TABLE IF NOT EXISTS dq.quarantine (
    quarantine_id         bigserial PRIMARY KEY,
    record_id             text NOT NULL,
    partition_id          text NOT NULL,
    failed_rule           text NOT NULL,
    rule_version          integer NOT NULL,
    severity              text NOT NULL,
    original_value        text,
    reason                text NOT NULL,
    original_record       jsonb NOT NULL,
    pipeline_run_id       uuid NOT NULL,       -- run that first quarantined the record
    last_seen_run_id      uuid NOT NULL,
    quarantined_at        timestamptz NOT NULL DEFAULT now(),
    resolved_by_run_id    uuid,
    review_status         text NOT NULL DEFAULT 'pending'
                          CHECK (review_status IN ('pending','confirmed_invalid','false_positive','fixed_upstream')),
    reviewed_by           text,
    reviewed_at           timestamptz,
    review_note           text,
    UNIQUE (record_id, failed_rule)
);
CREATE INDEX IF NOT EXISTS quarantine_partition_idx ON dq.quarantine (partition_id, failed_rule);

CREATE TABLE IF NOT EXISTS dq.quarantine_review_log (
    id             bigserial PRIMARY KEY,
    quarantine_id  bigint NOT NULL REFERENCES dq.quarantine(quarantine_id),
    old_status     text,
    new_status     text NOT NULL,
    reviewed_by    text NOT NULL,
    note           text,
    reviewed_at    timestamptz NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------- dq: ML model registry & monitoring
CREATE TABLE IF NOT EXISTS dq.model_registry (
    model_name           text NOT NULL,
    version              integer NOT NULL,
    created_at           timestamptz NOT NULL,
    target               text NOT NULL,
    algorithm            text NOT NULL,
    params               jsonb,
    features             jsonb NOT NULL,
    train_partition      text NOT NULL,
    validation_partition text NOT NULL,
    train_rows           bigint,
    train_data_sha256    text NOT NULL,       -- sha256 of the raw file the model was trained on
    selection            jsonb,               -- validation metrics of every candidate
    validation_metrics   jsonb,
    backtest             jsonb,               -- rolling-origin evaluation (month t -> month t+1)
    flag_threshold       double precision NOT NULL,
    alpha                double precision NOT NULL,
    artifact             text NOT NULL,
    artifact_sha256      text NOT NULL,
    environment          jsonb,
    PRIMARY KEY (model_name, version)
);

CREATE TABLE IF NOT EXISTS dq.model_metrics (
    model_name         text NOT NULL,
    version            integer NOT NULL,
    partition_id       text NOT NULL,
    split              text NOT NULL,         -- train | validation | test (out-of-time)
    n                  bigint NOT NULL,
    mae                double precision NOT NULL,
    mae_ci_low         double precision,      -- 95% bootstrap interval
    mae_ci_high        double precision,
    rmse               double precision NOT NULL,
    median_ae          double precision NOT NULL,
    r2                 double precision NOT NULL,
    flagged            bigint NOT NULL,
    flag_rate          double precision NOT NULL,
    mae_vs_validation  double precision NOT NULL,
    status             text NOT NULL,         -- ok | retrain_recommended
    by_payment_type    jsonb,
    scoring_s          double precision,
    scored_at          timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (model_name, version, partition_id)
);

CREATE TABLE IF NOT EXISTS dq.model_flags (
    model_name       text NOT NULL,
    version          integer NOT NULL,
    partition_id     text NOT NULL,
    record_id        text NOT NULL,
    actual_value     double precision,
    predicted_value  double precision,
    log_ratio        double precision,
    features         jsonb,
    PRIMARY KEY (model_name, version, record_id)
);

-- ---------------------------------------------------------------- dq: copilot (suggestions only)
CREATE TABLE IF NOT EXISTS dq.copilot_suggestions (
    suggestion_id     bigserial PRIMARY KEY,
    created_at        timestamptz NOT NULL DEFAULT now(),
    incident_type     text NOT NULL,          -- rule_failure | drift | schema | anomaly
    incident_ref      text NOT NULL,          -- e.g. run_id/partition_id/rule_id
    partition_id      text,
    evidence          jsonb NOT NULL,         -- exact facts sent to the model (from dq tables)
    evidence_sha256   text NOT NULL,
    provider          text NOT NULL,          -- anthropic | deterministic_template
    model             text,
    prompt_version    text NOT NULL,
    response          jsonb NOT NULL,
    label             text NOT NULL DEFAULT 'SUGGESTION — not verified, requires human review',
    status            text NOT NULL DEFAULT 'proposed'
                      CHECK (status IN ('proposed','accepted','rejected')),
    reviewed_by       text,
    reviewed_at       timestamptz,
    review_note       text
);

-- Least privilege: the copilot role can read quality metadata and INSERT suggestions. Nothing else.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'dqc_copilot') THEN
        CREATE ROLE dqc_copilot LOGIN PASSWORD 'copilot';
    END IF;
END $$;
GRANT USAGE ON SCHEMA dq TO dqc_copilot;
GRANT SELECT ON ALL TABLES IN SCHEMA dq TO dqc_copilot;
GRANT INSERT ON dq.copilot_suggestions TO dqc_copilot;
GRANT USAGE ON SEQUENCE dq.copilot_suggestions_suggestion_id_seq TO dqc_copilot;
REVOKE ALL ON SCHEMA raw FROM dqc_copilot;
REVOKE ALL ON SCHEMA analytics FROM dqc_copilot;

-- Read-only role for Grafana / dashboards
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'dqc_reader') THEN
        CREATE ROLE dqc_reader LOGIN PASSWORD 'reader';
    END IF;
END $$;
GRANT USAGE ON SCHEMA dq, analytics TO dqc_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA dq TO dqc_reader;
ALTER DEFAULT PRIVILEGES IN SCHEMA analytics GRANT SELECT ON TABLES TO dqc_reader;
ALTER DEFAULT PRIVILEGES IN SCHEMA dq GRANT SELECT ON TABLES TO dqc_reader;
