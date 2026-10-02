-- Curated layer: only records that passed every CRITICAL rule. Warning flags are carried along.
{{ config(indexes=[{'columns': ['record_id'], 'unique': true}, {'columns': ['partition_id']}]) }}
select
    record_id, partition_id, source_row, vendor_id, pickup_datetime, dropoff_datetime, trip_duration_min,
    pickup_date, passenger_count, trip_distance, ratecode_id, store_and_fwd_flag, pu_location_id,
    do_location_id, payment_type, fare_amount, extra, mta_tax, tip_amount, tolls_amount,
    improvement_surcharge, total_amount, congestion_surcharge, airport_fee, cbd_congestion_fee,
    has_warning, failed_warning_rules, quality_run_id
from {{ ref('int_trip_quality') }}
where is_valid
