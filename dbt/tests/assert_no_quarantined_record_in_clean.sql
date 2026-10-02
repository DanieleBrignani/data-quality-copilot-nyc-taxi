-- A record under (unresolved) quarantine must never be published in the curated layer.
select c.record_id
from {{ ref('fct_clean_trips') }} c
join {{ source('dq', 'quarantine') }} q
  on q.record_id = c.record_id and q.resolved_by_run_id is null
