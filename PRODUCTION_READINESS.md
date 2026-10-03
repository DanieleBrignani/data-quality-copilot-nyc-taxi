# Production readiness review

Reviewed on 2026-10-03 against the repository as committed. Statuses are `PASS`, `PARTIAL` or `FAIL`; a `PASS` requires evidence in this repository (a file, a test, a recorded run).

## Verdict

**Not production-ready for an enterprise deployment. Ready as a single-node system on a trusted network.**

No category is `FAIL` after this review, but 14 of 29 are `PARTIAL`. The blocking gaps for a real production deployment are the ones a single machine cannot close: the CI workflow has never run on a hosted runner, there is no TLS or secret store, backups are manual, alerts fire but notify nobody, and nothing has been tested beyond the current volume (14.4M rows, 4 partitions).

### What this review changed

The audit first found four categories at `FAIL`. They were fixed before this document was written, and each fix has a test or a recorded run:

| Category | Finding | Fix | Evidence |
|---|---|---|---|
| Secret management | Database, service-role and Grafana passwords were hardcoded in 10 files | All credentials come from the environment (`.env`, gitignored); no code default; compose refuses to start without them | `tests/test_hardening.py::test_repository_contains_no_hardcoded_credentials`, `test_no_database_password_has_a_default` |
| Security | Every API endpoint that writes was unauthenticated; containers ran as root | `X-API-Key` required on writes, disabled when no key is configured; non-root image | `test_write_endpoints_*` (3 endpoints × 2 cases); `docker compose exec api id -un` → `app` |
| Retry strategy | A failed download failed the run; no backoff anywhere outside the Prefect task | Exponential backoff on transient errors, no retry on client errors | `test_transient_download_failures_are_retried_with_backoff`, `test_client_errors_are_not_retried` |
| Recovery | No backup, no restore procedure | `scripts/backup.sh`, `scripts/restore_check.sh` (restore into a scratch database, compare row counts) | `reports/recovery_check.json`: 17 tables, counts match, restore 30 s |

Two more defects surfaced during the review and were fixed: the Prefect flow would have failed on every run because the Soda SLO check fails on 2025-02 (a finding about the data, now a warning in a separate scan), and several README figures had no command behind them (now produced by `python -m dqc evidence` and checked by `scripts/verify_readme_numbers.py`).

## Review by category

### Data foundations

| Category | Requirement | Status | Evidence | Test | Limitation | Required improvement |
|---|---|---|---|---|---|---|
| Data source integrity | Source, version and content of every input are recorded and re-checked | PASS | `data/raw/manifest.json`: URL, SHA-256, size, row count, schema, download time, `Last-Modified`, ETag per file; hash re-verified on every run (`pipeline.read_partition`) | `test_tampered_raw_file_is_detected`, `test_raw_integrity_violation_fails_the_run` | TLC publishes no checksum: the first download is trusted as-is | Record the ETag history to detect upstream re-publication |
| Raw data immutability | Raw files are never modified after ingestion | PASS | Atomic rename, read-only bit, hash check; `python -m dqc verify-raw` returns 4 of 4 intact | `test_ingestion_is_idempotent_and_raw_is_read_only` | A local filesystem, not WORM storage: an administrator can still overwrite a file (it would be detected, not prevented) | Object storage with versioning and object lock |
| Data contracts | An explicit contract decides whether a file may enter | PASS | `config/thresholds.yaml` (`schema`), `src/dqc/schema.py`; a breaking change rejects the whole partition | `tests/test_schema.py` (7 tests), `test_schema_break_rejects_partition` | The contract covers columns and types, not value semantics (the Flex Fare change passed the contract) | Semantic checks per vendor and payment type |
| Schema evolution | Additive, breaking and unexpected changes are told apart | PASS | Real event handled: `cbd_congestion_fee` added in 2025-01, recorded in `dq.schema_checks`; schema diff against the previous partition | `test_diff_vs_previous_partition`, `test_unexpected_column_is_warned_and_dropped` | Contract changes are edited by hand in YAML | Contract versioning with a review step |
| Idempotency | Re-running produces the same state, with no duplicates | PASS | `reports/results.md` → *Rerun check*: identical scores and quarantine counts, 0 duplicated rows; model retraining reproduces the artifact byte for byte | `test_duplicate_ingestion_and_rerun_are_idempotent`, `test_training_is_idempotent_and_versions_only_change_with_the_model` | — | — |
| Lineage | Any curated row can be traced to its source row, run and code version | PARTIAL | `record_id` = partition + row number in the source file; `loaded_run_id`, `quality_run_id`; `dq.pipeline_runs` stores ruleset version, rules SHA-256 and git commit | `test_quarantine_rows_keep_original_values_and_never_drop_input` | Record-level only: no column-level lineage, dbt docs are not generated or published | `dbt docs generate`, a lineage catalogue |
| Database design | Schema fits the access patterns and can evolve | PARTIAL | `infra/postgres/init.sql`: list-partitioned raw table, primary keys, upsert key on quarantine, three roles | `tests/test_pipeline_db.py` (5 tests) | No migration tool: `init.sql` is `CREATE IF NOT EXISTS`, so a changed table needs a manual `ALTER` (this happened once, with the model tables) | Alembic or dbt-managed migrations |
| Data quality | Bad records are detected, isolated and never silently dropped | PASS | 23 versioned rules; 489,224 records quarantined with original values; dbt asserts `raw = clean + quarantined` on every build | `tests/test_rules.py` (17 tests), dbt `assert_no_silent_loss`, `python -m dqc demo-failures` (6 of 6 detected) | Rules are not validated by a TLC domain expert; the Flex Fare semantics are unresolved | Confirm the open cases with the data owner |

### Pipeline operations

| Category | Requirement | Status | Evidence | Test | Limitation | Required improvement |
|---|---|---|---|---|---|---|
| Orchestration | The whole workflow runs under an orchestrator | PARTIAL | `flows/quality_flow.py` executed end to end on 2025-02 (`reports/prefect_flow_run.txt`: exit 0, 8 min 41 s) | That recorded run | Run manually once, on one month; no schedule, no deployment, no Prefect server | A scheduled deployment with a work pool |
| Error handling | A failure is recorded, isolated and leaves no partial state | PASS | Each partition is one transaction (DDL included); a failed run is stored with status and error in `dq.pipeline_runs`; a metrics failure never breaks the pipeline | `test_raw_integrity_violation_fails_the_run`, `test_schema_break_rejects_partition` | The API has no global error handler: a database outage surfaces as HTTP 500 | Health-aware handlers and structured error responses |
| Retry strategy | Transient failures are retried, permanent ones are not | PARTIAL | Download: 4 attempts with exponential backoff, no retry on 4xx; Prefect ingestion task: 2 retries | `tests/test_hardening.py` (3 retry tests) | No retry on database or dbt steps; no dead-letter handling | Retries with jitter on database operations |
| Recovery | State can be restored after loss | PARTIAL | `scripts/backup.sh` + `scripts/restore_check.sh`; drill recorded in `reports/recovery_check.json` (37.6 MB backup, 30 s restore, counts match); `raw` and `analytics` are rebuilt from the immutable files | The drill itself (exit 1 on mismatch) | Manual, not scheduled; no point-in-time recovery; no off-machine copy; RPO and RTO are not defined | Scheduled backups, WAL archiving, an off-site copy |
| Rollback | A bad change can be undone | PARTIAL | Rules: revert the commit and re-run (idempotent; quarantine rows that stop failing are marked resolved, not deleted); models: `DQC_FARE_MODEL_VERSION` pins an earlier registered version | `test_quarantine_keeps_original_values_and_is_resolved_not_deleted`, `test_registry_roundtrip_and_threshold_calibration` | No rollback for database schema changes; the version pin is not covered by an end-to-end test | Migrations with down-steps; a rollback drill |

### Security and privacy

| Category | Requirement | Status | Evidence | Test | Limitation | Required improvement |
|---|---|---|---|---|---|---|
| Security | Least privilege, authenticated writes, no avoidable attack surface | PARTIAL | Three database roles (the copilot role can only insert suggestions; the dashboard and Grafana are read-only); API key on every write endpoint, compared in constant time; non-root container; parameterised SQL | `test_review_is_audited_and_copilot_role_cannot_touch_data`, `test_write_endpoints_*` | No TLS; read endpoints are open; Grafana allows anonymous viewing; one shared API key (no users, no roles); no rate limiting; no dependency or image scan | TLS termination, per-user authentication, a vulnerability scan in CI |
| Secret management | No secret in the repository; secrets injected at run time | PARTIAL | `.env` (gitignored) with generated values; `.env.example` holds placeholders only; `docker-compose.yml` uses `${VAR:?}`; service-role passwords are set from the environment at database initialisation | `test_repository_contains_no_hardcoded_credentials`, `test_no_database_password_has_a_default`, `test_connect_without_credentials_fails_with_an_explicit_message` | Plain-text `.env` on disk; no rotation; the CI workflow contains throwaway credentials for its ephemeral database | A secret manager and a rotation policy |
| Privacy | No personal data is collected, stored or exported without need | PASS | TLC trip records carry no rider or driver identifier and no coordinates, only zone ids; the built-in copilot sends nothing outside the machine; Prefect usage telemetry is disabled in the flow | — (no personal data to test) | The optional LLM provider would send quarantined sample records to an external API; reviewer names are stored as free text | A data-processing note before enabling the LLM provider |

### Testing and delivery

| Category | Requirement | Status | Evidence | Test | Limitation | Required improvement |
|---|---|---|---|---|---|---|
| Testing | Logic is covered by automated tests | PASS | 72 unit tests, no database needed (`reports/test_counts.json`) | `pytest` | Coverage is not measured | A coverage report with a threshold |
| Integration testing | Components are tested together against a real database | PASS | 5 tests on an isolated PostgreSQL database: idempotency, quarantine resolution, schema break, integrity failure, audit and privileges | `pytest -m db` | One database version (PostgreSQL 16) | A version matrix |
| End-to-end testing | The whole system is exercised on real data | PASS | `scripts/reproduce.sh` on 14,367,509 real rows; failure demo with 6 defect fixtures; dbt 21 of 21, Soda contract 16 of 16 | The script and `python -m dqc demo-failures` | The script takes about 53 minutes on this machine (last uninterrupted run: 2026-10-03, exit 0), too long for a CI job | A smaller end-to-end profile for CI |
| CI/CD | Every change is tested and gated automatically; releases are automated | PARTIAL | `.github/workflows/ci.yml`: lint, unit tests, quality gate, then integration on a PostgreSQL service; the gate is tested (`tests/test_gate.py`) | The same commands pass locally | **The workflow has never run on GitHub**: the repository is not published yet. No deployment stage, no image publishing | Publish, get a green run, add a release pipeline |
| Containerization | Services run from reproducible images | PARTIAL | `Dockerfile` (non-root, cached dependency layer), `docker-compose.yml` with health checks and restart policies for 5 services | Stack started and probed during this review | The batch pipeline runs from a host virtualenv, not a container; images are tagged, not pinned by digest; the image does not use the lock file | Containerise the pipeline, pin digests, build from the lock file |

### Observability and service levels

| Category | Requirement | Status | Evidence | Test | Limitation | Required improvement |
|---|---|---|---|---|---|---|
| Observability | The system's state is visible and alerts exist | PARTIAL | `/metrics` exporter derived from the warehouse, Prometheus alert rules, provisioned Grafana dashboard, Streamlit dashboard; alerts verified firing | Live checks during this review | Alerts are not routed (no Alertmanager, nobody is notified); logs are plain text; no tracing | Alert routing, structured logs |
| SLIs | Quality and performance indicators are measured per run | PASS | `dq.partition_quality`: valid-record rate, quality score, source lag, duration, rows per second, per stage timings | `reports/results.md` | — | — |
| SLOs | Targets exist, are measured and are enforced | PASS | `config/thresholds.yaml` (`slo`); enforced by `python -m dqc gate --slo`, Soda and Prometheus; breaches reported: 2025-01 score and source lag, 2025-02 valid rate and score | `soda/checks_slo.yml` (2 of 3 pass, recorded in `reports/test_counts.json`); `python -m dqc gate --slo` exits 1 | Targets were set from two months of data; no error budget | An error-budget policy |
| Performance | Throughput and stage costs are measured | PASS | 660 s for 14,367,509 rows (21,780 rows/s) in the reference run; per-stage timings in `reports/results.md` | `scripts/reproduce.sh` | Wall-clock time varies from run to run on this shared machine; raw landing is the slowest stage | Bulk load from object storage |
| Scalability | Behaviour at higher volume is known | PARTIAL | Partitions are independent and processed one at a time; each partition is a separate table | — | **Not tested beyond the current volume.** Each partition is processed in memory; this review saw the 16 GB machine run out of memory when two analyses ran at once | Streaming or chunked evaluation, parallel partitions, a load test |

### Governance

| Category | Requirement | Status | Evidence | Test | Limitation | Required improvement |
|---|---|---|---|---|---|---|
| Documentation | A newcomer can understand, run and operate the system | PARTIAL | `README.md`, `RECRUITER_SUMMARY.md`, `docs/MODEL_CARD.md`, this file, `.env.example`, docstrings | — | No operations runbook (what to do when an alert fires); no architecture decision records | A runbook per alert |
| Reproducibility | Every reported number can be regenerated | PASS | `scripts/reproduce.sh`; `python -m dqc evidence`; `scripts/verify_readme_numbers.py` → 964 numbers checked, 0 without a source; fixed seeds; `requirements-lock.txt` | `reports/readme_numbers_audit.md` | The number check is permissive for one- and two-digit values (see the script's docstring); the lock file is not enforced by the image | Build images from the lock file |
| Cost awareness | Resource use is measured and the cost drivers are known | PARTIAL | Measured: 4.25 GB for raw landing, 1.14 GB for quarantine, 37.6 MB per backup, 660 s of pipeline compute per full run; model selection weighs artifact size (0.81 MB chosen over 47.59 MB) | `reports/evidence.json` → `warehouse` | No monetary estimate; nothing runs on a metered platform; the optional LLM provider's cost was never measured because it was never run | A cost model per partition for a target platform |

## Status summary

| Status | Count | Categories |
|---|---:|---|
| PASS | 15 | Data source integrity, raw data immutability, data contracts, schema evolution, idempotency, data quality, error handling, privacy, testing, integration testing, end-to-end testing, SLIs, SLOs, performance, reproducibility |
| PARTIAL | 14 | Lineage, database design, orchestration, retry strategy, recovery, rollback, security, secret management, CI/CD, containerization, observability, scalability, documentation, cost awareness |
| FAIL | 0 | — |

## Claims this review does not make

- No production traffic, users or adoption: the system has run only on this build machine.
- No reliability figure: there is no uptime history to compute one from.
- No cost saving: nothing was measured against an alternative.
- No statement that the CI workflow passes on GitHub: it has not run there.
- The optional LLM provider was never executed; nothing is claimed about its output.
