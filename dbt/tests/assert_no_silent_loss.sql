-- Reconciliation: raw = clean + quarantined, per partition. Any gap means records were silently lost.
with raw as (select partition_id, count(*) n from {{ ref('stg_trips') }} group by 1),
clean as (select partition_id, count(*) n from {{ ref('fct_clean_trips') }} group by 1),
quar as (
    select partition_id, count(distinct record_id) n
    from {{ source('dq', 'quarantine') }}
    where resolved_by_run_id is null
    group by 1
)
select raw.partition_id, raw.n as raw_n, coalesce(clean.n, 0) as clean_n, coalesce(quar.n, 0) as quarantined_n
from raw
left join clean on clean.partition_id = raw.partition_id
left join quar on quar.partition_id = raw.partition_id
where raw.n <> coalesce(clean.n, 0) + coalesce(quar.n, 0)
