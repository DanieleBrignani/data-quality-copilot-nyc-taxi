-- Every trip with its record-level verdict from the deterministic rule engine.
-- dq.record_quality only stores records with >= 1 failed rule; absence means "passed every rule".
select
    t.*,
    coalesce(q.is_valid, true)                         as is_valid,
    coalesce(q.failed_critical, array[]::text[])       as failed_critical_rules,
    coalesce(q.failed_warning, array[]::text[])        as failed_warning_rules,
    coalesce(cardinality(q.failed_warning), 0) > 0     as has_warning,
    q.run_id                                           as quality_run_id
from {{ ref('stg_trips') }} t
left join {{ source('dq', 'record_quality') }} q
       on q.partition_id = t.partition_id
      and q.record_id = t.record_id
