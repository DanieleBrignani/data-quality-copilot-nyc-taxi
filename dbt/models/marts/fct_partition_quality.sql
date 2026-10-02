-- Latest quality snapshot per partition (trend source for dashboards).
select distinct on (pq.partition_id)
    pq.partition_id,
    p.year_month,
    pq.run_id,
    r.started_at as run_started_at,
    r.ruleset_version,
    pq.rows_total,
    pq.valid_rows,
    pq.quarantined_records,
    pq.warning_only_records,
    pq.valid_record_rate,
    pq.quality_score,
    pq.dimension_scores,
    pq.schema_status,
    pq.unexpected_schema_changes,
    pq.source_lag_days,
    pq.duration_s,
    pq.rows_per_sec
from {{ source('dq', 'partition_quality') }} pq
join {{ source('dq', 'pipeline_runs') }} r on r.run_id = pq.run_id
left join {{ source('dq', 'dataset_partitions') }} p on p.partition_id = pq.partition_id
order by pq.partition_id, r.started_at desc
