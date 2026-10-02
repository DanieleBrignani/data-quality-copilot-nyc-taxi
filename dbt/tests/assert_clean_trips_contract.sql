-- Defense in depth: the curated layer must never contain values the rule engine forbids.
select record_id, 'contract_violation' as issue
from {{ ref('fct_clean_trips') }}
where fare_amount < 0 or total_amount < 0 or tip_amount < 0
   or trip_distance < 0 or trip_distance > 200
   or passenger_count > 6
   or dropoff_datetime <= pickup_datetime
