-- Unified, append-only event stream of every quality signal, across all runs (audit trail).
with runs as (
    select run_id, started_at from {{ source('dq', 'pipeline_runs') }}
),
latest as (
    select distinct on (pq.partition_id) pq.partition_id, pq.run_id
    from {{ source('dq', 'partition_quality') }} pq
    join runs r on r.run_id = pq.run_id
    order by pq.partition_id, r.started_at desc
),
events as (
    select run_id, partition_id, 'rule_failure' as event_type, severity, rule_id as subject,
           dimension as detail, failure_rate as metric_value, failed_rows as affected_rows,
           evaluated_at as event_at
    from {{ source('dq', 'rule_results') }}
    where failed_rows > 0

    union all
    select run_id, partition_id, 'schema_change', severity, coalesce(column_name, '__table__'),
           check_name || ': ' || coalesce(detail, ''), null, null, checked_at
    from {{ source('dq', 'schema_checks') }}

    union all
    select d.run_id, d.partition_id, 'drift', case d.status when 'alert' then 'critical' else 'warning' end,
           d.column_name, d.metric || ' vs ' || d.reference_partition_id, d.value, null, r.started_at
    from {{ source('dq', 'drift_results') }} d join runs r on r.run_id = d.run_id
    where d.status in ('alert', 'warn')

    union all
    select a.run_id, a.partition_id, 'anomaly', 'info', a.method,
           'investigation queue (not quarantined)', a.anomaly_rate, a.anomalies, r.started_at
    from {{ source('dq', 'anomaly_results') }} a join runs r on r.run_id = a.run_id
)
select
    md5(e.run_id::text || e.partition_id || e.event_type || e.subject || coalesce(e.detail, '')) as event_id,
    e.*,
    (l.run_id is not null) as is_latest_run
from events e
left join latest l on l.partition_id = e.partition_id and l.run_id = e.run_id
