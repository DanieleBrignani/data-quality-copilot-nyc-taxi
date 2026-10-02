# Results (generated 2026-09-30T19:01:06+00:00)

All values below are read from the warehouse / report files; regenerate with `python -m dqc report`.

## Totals

- partitions: 4
- records processed: 14,367,509
- quarantined records: 489,224 (3.405%)
- warning-only records (kept, flagged): 1,995,424 (13.888%)
- processing time (sum of partitions): 780.4s -> 18,410 rows/s
- schema changes detected between consecutive partitions: 1 (unexpected / contract-breaking: 0)
- drift alerts: 9 (warnings: 2)

## Per partition

| partition | rows | quarantined | % | warning-only | valid % | score | schema | duration s | rows/s | source lag d |
|---|---:|---:|---:|---:|---:|---:|---|---:|---:|---:|
| yellow_2024-11 | 3,646,369 | 73,800 | 2.024 | 411,958 | 97.976 | 95.152 | ok | 168.6 | 21,629 | 47.8 |
| yellow_2024-12 | 3,668,371 | 80,397 | 2.192 | 369,614 | 97.808 | 95.289 | ok | 211.5 | 17,346 | 51.9 |
| yellow_2025-01 | 3,475,226 | 146,639 | 4.220 | 497,833 | 95.780 | 92.199 | additive_change | 228.3 | 15,222 | 81.7 |
| yellow_2025-02 | 3,577,543 | 188,388 | 5.266 | 716,019 | 94.734 | 89.731 | additive_change | 172.0 | 20,794 | 53.7 |

## Stage timings (s)

| partition | read_and_schema | raw_landing | profiling | rules | persist_quality | anomaly | drift |
|---|---:|---:|---:|---:|---:|---:|---:|
| yellow_2024-11 | 1.3 | 41.7 | 7.2 | 15.2 | 44.9 | 58.4 | - |
| yellow_2024-12 | 1.8 | 95.9 | 7.7 | 16.1 | 39.8 | 41.4 | 8.7 |
| yellow_2025-01 | 0.8 | 127.3 | 3.2 | 12.2 | 36.3 | 41.0 | 7.6 |
| yellow_2025-02 | 1.3 | 101.0 | 2.1 | 8.9 | 31.6 | 23.1 | 4.1 |

## Rule failures (failed rows / failure rate %)

| rule | severity | yellow_2024-11 | yellow_2024-12 | yellow_2025-01 | yellow_2025-02 |
|---|---|---:|---:|---:|---:|
| DQ001_mandatory_fields_not_null | critical | 0 / 0.000 | 0 / 0.000 | 0 / 0.000 | 0 / 0.000 |
| DQ002_passenger_count_not_null | warning | 373,674 / 10.248 | 326,291 / 8.895 | 540,149 / 15.543 | 806,937 / 22.556 |
| DQ010_pickup_before_dropoff | critical | 1,861 / 0.051 | 1,223 / 0.033 | 2,051 / 0.059 | 5,164 / 0.144 |
| DQ011_trip_duration_max | critical | 12 / 0.000 | 18 / 0.000 | 20 / 0.001 | 16 / 0.000 |
| DQ012_pickup_in_partition_window | critical | 50 / 0.001 | 34 / 0.001 | 22 / 0.001 | 31 / 0.001 |
| DQ020_trip_distance_range | critical | 107 / 0.003 | 91 / 0.002 | 122 / 0.004 | 151 / 0.004 |
| DQ021_fare_amount_range | critical | 71,473 / 1.960 | 78,450 / 2.139 | 144,121 / 4.147 | 182,661 / 5.106 |
| DQ022_total_amount_range | critical | 60,565 / 1.661 | 70,500 / 1.922 | 63,039 / 1.814 | 55,183 / 1.542 |
| DQ023_tip_amount_non_negative | critical | 117 / 0.003 | 140 / 0.004 | 124 / 0.004 | 105 / 0.003 |
| DQ024_passenger_count_max | critical | 21 / 0.001 | 18 / 0.000 | 18 / 0.001 | 16 / 0.000 |
| DQ025_passenger_count_zero | warning | 28,370 / 0.778 | 30,397 / 0.829 | 24,656 / 0.709 | 21,751 / 0.608 |
| DQ026_implied_speed_plausible | warning | 955 / 0.026 | 1,005 / 0.027 | 933 / 0.027 | 798 / 0.022 |
| DQ030_vendor_id_accepted | critical | 0 / 0.000 | 0 / 0.000 | 0 / 0.000 | 0 / 0.000 |
| DQ031_payment_type_accepted | critical | 0 / 0.000 | 0 / 0.000 | 0 / 0.000 | 0 / 0.000 |
| DQ032_ratecode_accepted | critical | 0 / 0.000 | 0 / 0.000 | 0 / 0.000 | 0 / 0.000 |
| DQ033_store_and_fwd_flag_accepted | critical | 0 / 0.000 | 0 / 0.000 | 0 / 0.000 | 0 / 0.000 |
| DQ034_location_ids_known | critical | 0 / 0.000 | 0 / 0.000 | 0 / 0.000 | 0 / 0.000 |
| DQ035_location_unknown | warning | 18,123 / 0.497 | 18,322 / 0.499 | 16,015 / 0.461 | 13,771 / 0.385 |
| DQ040_total_amount_reconciles | warning | 4,925 / 0.150 | 6,519 / 0.195 | 31,255 / 1.065 | 4,890 / 0.176 |
| DQ050_exact_duplicate | critical | 0 / 0.000 | 0 / 0.000 | 0 / 0.000 | 0 / 0.000 |
| DQ051_business_key_duplicate | warning | 0 / 0.000 | 0 / 0.000 | 0 / 0.000 | 0 / 0.000 |

## Schema events

| partition | check | column | severity | detail |
|---|---|---|---|---|
| yellow_2025-01 | optional_column_present | cbd_congestion_fee | info | documented additive column |
| yellow_2025-01 | column_added_vs_previous | cbd_congestion_fee | info | new column (double) |
| yellow_2025-02 | optional_column_present | cbd_congestion_fee | info | documented additive column |

## Drift alerts & warnings

| partition | vs | column | metric | value | threshold | status |
|---|---|---|---|---:|---:|---|
| yellow_2024-12 | yellow_2024-11 | VendorID | cardinality_change_pct | 33.3333 | 20.0 | warn |
| yellow_2025-01 | yellow_2024-12 | passenger_count | null_rate_change_pp | 6.6481 | 2.0 | alert |
| yellow_2025-01 | yellow_2024-12 | payment_type | cardinality_change_pct | 20.0000 | 20.0 | warn |
| yellow_2025-01 | yellow_2024-12 | RatecodeID | null_rate_change_pp | 6.6481 | 2.0 | alert |
| yellow_2025-01 | yellow_2024-12 | store_and_fwd_flag | null_rate_change_pp | 6.6481 | 2.0 | alert |
| yellow_2025-01 | yellow_2024-12 | trip_duration_min | ks_statistic | 0.1081 | 0.1 | alert |
| yellow_2025-01 | yellow_2024-12 | trip_duration_min | mean_shift_pct | -19.6620 | 15.0 | alert |
| yellow_2025-01 | yellow_2024-12 | trip_duration_min | median_shift_pct | -15.1149 | 15.0 | alert |
| yellow_2025-02 | yellow_2025-01 | passenger_count | null_rate_change_pp | 7.0128 | 2.0 | alert |
| yellow_2025-02 | yellow_2025-01 | RatecodeID | null_rate_change_pp | 7.0128 | 2.0 | alert |
| yellow_2025-02 | yellow_2025-01 | store_and_fwd_flag | null_rate_change_pp | 7.0128 | 2.0 | alert |

## Anomaly detectors on rule-valid records

| partition | method | scored | flagged | % | runtime s |
|---|---|---:|---:|---:|---:|
| yellow_2024-11 | iqr | 3,572,569 | 311,070 | 8.707 | 2.89 |
| yellow_2024-11 | iqr_log | 3,572,569 | 4,849 | 0.136 | 3.49 |
| yellow_2024-11 | isolation_forest | 3,572,569 | 33,683 | 0.943 | 42.26 |
| yellow_2024-11 | zscore | 3,572,569 | 62,322 | 1.744 | 0.94 |
| yellow_2024-12 | iqr | 3,587,974 | 316,460 | 8.820 | 3.27 |
| yellow_2024-12 | iqr_log | 3,587,974 | 4,301 | 0.120 | 2.86 |
| yellow_2024-12 | isolation_forest | 3,587,974 | 35,614 | 0.993 | 28.22 |
| yellow_2024-12 | zscore | 3,587,974 | 60,619 | 1.690 | 0.90 |
| yellow_2025-01 | iqr | 3,328,587 | 295,939 | 8.891 | 1.87 |
| yellow_2025-01 | iqr_log | 3,328,587 | 6,828 | 0.205 | 2.55 |
| yellow_2025-01 | isolation_forest | 3,328,587 | 33,251 | 0.999 | 32.66 |
| yellow_2025-01 | zscore | 3,328,587 | 62,158 | 1.867 | 0.77 |
| yellow_2025-02 | iqr | 3,389,155 | 267,919 | 7.905 | 1.59 |
| yellow_2025-02 | iqr_log | 3,389,155 | 5,974 | 0.176 | 1.52 |
| yellow_2025-02 | isolation_forest | 3,389,155 | 33,890 | 1.000 | 17.56 |
| yellow_2025-02 | zscore | 3,389,155 | 70,776 | 2.088 | 0.41 |

## Benchmark on injected errors (yellow_2025-01, 200,000 real rule-clean records + 4,363 labelled errors, seed 42)

| detector | precision | recall | FPR | flagged | runtime s |
|---|---:|---:|---:|---:|---:|
| rules_critical | 1.0 | 0.6677 | 0.0 | 2,913 | 0.289 |
| rules_critical_plus_warning | 1.0 | 0.6773 | 0.0 | 2,955 | 0.289 |
| iqr | 0.0753 | 0.3585 | 0.098046 | 20,781 | 0.073 |
| rules_critical+iqr | 0.1657 | 0.8746 | 0.098046 | 23,033 |  |
| iqr_log | 0.7528 | 0.3064 | 0.00224 | 1,776 | 0.054 |
| rules_critical+iqr_log | 0.8777 | 0.7222 | 0.00224 | 3,590 |  |
| zscore | 0.3476 | 0.2026 | 0.008464 | 2,543 | 0.018 |
| rules_critical+zscore | 0.6748 | 0.7889 | 0.008464 | 5,101 |  |
| isolation_forest | 0.0994 | 0.0456 | 0.009204 | 2,003 | 2.077 |
| rules_critical+isolation_forest | 0.628 | 0.6981 | 0.009204 | 4,850 |  |

### Recall by error type

| error type | family | rules_critical | rules_critical_plus_warning | iqr | iqr_log | zscore | isolation_forest |
|---|---|---:|---:|---:|---:|---:|---:|
| distance_unit_error | rule_detectable | 1.0 | 1.0 | 1.0 | 1.0 | 0.8736 | 0.1209 |
| distance_x5 | plausible | 0.0 | 0.1157 | 0.4656 | 0.1212 | 0.011 | 0.0303 |
| dropoff_before_pickup | rule_detectable | 1.0 | 1.0 | 0.0962 | 1.0 | 0.0027 | 0.011 |
| exact_duplicate | rule_detectable | 1.0 | 1.0 | 0.1019 | 0.0028 | 0.011 | 0.0083 |
| fare_over_cap | rule_detectable | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 |
| fare_x10 | plausible | 0.0 | 0.0 | 0.9612 | 0.3712 | 0.6842 | 0.1773 |
| invalid_payment_type | rule_detectable | 1.0 | 1.0 | 0.1264 | 0.0027 | 0.0055 | 0.0082 |
| negative_fare | rule_detectable | 1.0 | 1.0 | 0.1813 | 1.0 | 0.0577 | 0.0055 |
| null_mandatory | rule_detectable | 1.0 | 1.0 | 0.1044 | 0.0 | 0.0 | 0.0055 |
| passenger_overflow | rule_detectable | 1.0 | 1.0 | 0.0824 | 0.0 | 0.0055 | 0.0027 |
| stale_timestamp | rule_detectable | 1.0 | 1.0 | 0.1181 | 0.0082 | 0.0137 | 0.0137 |
| swapped_zones | plausible | 0.0 | 0.0 | 0.0826 | 0.0 | 0.0055 | 0.0055 |
| tip_spike | plausible | 0.0 | 0.0 | 0.9835 | 0.1653 | 0.7603 | 0.1543 |

## Failure demo

| fixture | expected | observed | detected |
|---|---|---|---|
| schema_break | {"schema_status": "breaking", "rows_propagated": 0} | {"schema_status": "breaking", "raw_rows_loaded": 0, "critical_schema_events": ["type_mismatch:trip_distance", "missing_required_column:fare_amount"]} | True |
| duplicate | {"rule": "DQ050_exact_duplicate", "failed_rows": 25} | {"failed_rows": 25, "quarantined": 25, "valid_record_rate": 98.765} | True |
| invalid_amount | {"rule": "DQ021_fare_amount_range", "failed_rows": 40} | {"failed_rows": 40, "quarantined": 40, "valid_record_rate": 98.0} | True |
| missing_mandatory | {"rule": "DQ001_mandatory_fields_not_null", "failed_rows": 35} | {"failed_rows": 35, "quarantined": 35, "valid_record_rate": 98.25} | True |
| impossible_duration | {"rule": "DQ010_pickup_before_dropoff", "failed_rows": 12} | {"failed_rows": 12, "quarantined": 12, "valid_record_rate": 99.4} | True |
| invalid_passenger_count | {"rule": "DQ024_passenger_count_max", "failed_rows": 8} | {"failed_rows": 8, "quarantined": 8, "valid_record_rate": 99.6} | True |

## Rerun check (same files, same code, second run)

identical quality results: True · raw rows not duplicated: True

| partition | score ref | score rerun | quarantined ref | quarantined rerun | raw rows | duration ref s | duration rerun s | rerun raw landing s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| yellow_2024-11 | 95.1516 | 95.1516 | 73,800 | 73,800 | 3,646,369 | 168.6 | 53.9 | 3.3 |
| yellow_2024-12 | 95.2894 | 95.2894 | 80,397 | 80,397 | 3,668,371 | 211.5 | 80.1 | 4.0 |
| yellow_2025-01 | 92.1991 | 92.1991 | 146,639 | 146,639 | 3,475,226 | 228.3 | 113.0 | 20.7 |
| yellow_2025-02 | 89.7306 | 89.7306 | 188,388 | 188,388 | 3,577,543 | 172.0 | 193.7 | 6.7 |

## Manual review of real anomalies

method: isolation_forest, partition yellow_2025-01, sample 40 (seed 11)

| verdict | count |
|---|---:|
| plausible_legitimate | 29 |
| likely_data_error | 6 |
| undetermined | 5 |
