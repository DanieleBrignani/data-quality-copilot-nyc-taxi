# Results (generated 2026-10-02T21:28:41+00:00)

All values below are read from the warehouse / report files; regenerate with `python -m dqc report`.

## Totals

- partitions: 4
- records processed: 14,367,509
- quarantined records: 489,224 (3.405%)
- warning-only records (kept, flagged): 1,995,424 (13.888%)
- processing time (sum of partitions): 658.7s -> 21,812 rows/s
- schema changes detected between consecutive partitions: 1 (unexpected / contract-breaking: 0)
- drift alerts: 9 (warnings: 2)

## Per partition

| partition | rows | quarantined | % | warning-only | valid % | score | schema | duration s | rows/s | source lag d |
|---|---:|---:|---:|---:|---:|---:|---|---:|---:|---:|
| yellow_2024-11 | 3,646,369 | 73,800 | 2.024 | 411,958 | 97.976 | 95.152 | ok | 128.6 | 28,354 | 47.8 |
| yellow_2024-12 | 3,668,371 | 80,397 | 2.192 | 369,614 | 97.808 | 95.289 | ok | 130.1 | 28,202 | 51.9 |
| yellow_2025-01 | 3,475,226 | 146,639 | 4.220 | 497,833 | 95.780 | 92.199 | additive_change | 178.5 | 19,465 | 81.7 |
| yellow_2025-02 | 3,577,543 | 188,388 | 5.266 | 716,019 | 94.734 | 89.731 | additive_change | 221.5 | 16,153 | 53.7 |

## Stage timings (s)

| partition | read_and_schema | raw_landing | profiling | rules | persist_quality | anomaly | drift |
|---|---:|---:|---:|---:|---:|---:|---:|
| yellow_2024-11 | 0.5 | 81.9 | 2.3 | 6.7 | 15.9 | 21.4 | - |
| yellow_2024-12 | 0.4 | 72.6 | 2.2 | 7.6 | 25.2 | 19.0 | 3.1 |
| yellow_2025-01 | 0.4 | 113.1 | 1.9 | 9.4 | 28.9 | 21.7 | 3.2 |
| yellow_2025-02 | 0.3 | 154.0 | 2.0 | 8.8 | 34.7 | 18.1 | 3.5 |

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
| yellow_2024-11 | iqr | 3,572,569 | 311,070 | 8.707 | 1.60 |
| yellow_2024-11 | iqr_log | 3,572,569 | 4,849 | 0.136 | 1.47 |
| yellow_2024-11 | isolation_forest | 3,572,569 | 33,683 | 0.943 | 15.27 |
| yellow_2024-11 | zscore | 3,572,569 | 62,322 | 1.744 | 0.36 |
| yellow_2024-12 | iqr | 3,587,974 | 316,460 | 8.820 | 0.91 |
| yellow_2024-12 | iqr_log | 3,587,974 | 4,301 | 0.120 | 1.29 |
| yellow_2024-12 | isolation_forest | 3,587,974 | 35,614 | 0.993 | 14.68 |
| yellow_2024-12 | zscore | 3,587,974 | 60,619 | 1.690 | 0.35 |
| yellow_2025-01 | iqr | 3,328,587 | 295,939 | 8.891 | 1.50 |
| yellow_2025-01 | iqr_log | 3,328,587 | 6,828 | 0.205 | 1.27 |
| yellow_2025-01 | isolation_forest | 3,328,587 | 33,251 | 0.999 | 15.99 |
| yellow_2025-01 | zscore | 3,328,587 | 62,158 | 1.867 | 0.38 |
| yellow_2025-02 | iqr | 3,389,155 | 267,919 | 7.905 | 0.86 |
| yellow_2025-02 | iqr_log | 3,389,155 | 5,974 | 0.176 | 1.04 |
| yellow_2025-02 | isolation_forest | 3,389,155 | 33,890 | 1.000 | 13.79 |
| yellow_2025-02 | zscore | 3,389,155 | 70,776 | 2.088 | 0.35 |

## Benchmark on injected errors (yellow_2025-01, 200,000 real rule-clean records + 4,363 labelled errors, seed 42)

| detector | precision | recall | FPR | flagged | runtime s |
|---|---:|---:|---:|---:|---:|
| rules_critical | 1.0 | 0.6677 | 0.0 | 2,913 | 0.174 |
| rules_critical_plus_warning | 1.0 | 0.6773 | 0.0 | 2,955 | 0.174 |
| iqr | 0.0753 | 0.3585 | 0.098046 | 20,781 | 0.043 |
| rules_critical+iqr | 0.1657 | 0.8746 | 0.098046 | 23,033 |  |
| iqr_log | 0.7528 | 0.3064 | 0.00224 | 1,776 | 0.052 |
| rules_critical+iqr_log | 0.8777 | 0.7222 | 0.00224 | 3,590 |  |
| zscore | 0.3476 | 0.2026 | 0.008464 | 2,543 | 0.014 |
| rules_critical+zscore | 0.6748 | 0.7889 | 0.008464 | 5,101 |  |
| isolation_forest | 0.0994 | 0.0456 | 0.009204 | 2,003 | 1.691 |
| rules_critical+isolation_forest | 0.628 | 0.6981 | 0.009204 | 4,850 |  |
| fare_model | 0.776 | 0.2152 | 0.001383 | 1,210 | 0.172 |
| rules_critical+fare_model | 0.924 | 0.7552 | 0.001383 | 3,566 |  |
| rules_critical+iqr_log+fare_model | 0.8453 | 0.7788 | 0.003173 | 4,020 |  |

### Recall by error type

| error type | family | rules_critical | rules_critical_plus_warning | iqr | iqr_log | zscore | isolation_forest | fare_model |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| distance_unit_error | rule_detectable | 1.0 | 1.0 | 1.0 | 1.0 | 0.8736 | 0.1209 | 0.5824 |
| distance_x5 | plausible | 0.0 | 0.1157 | 0.4656 | 0.1212 | 0.011 | 0.0303 | 0.0579 |
| dropoff_before_pickup | rule_detectable | 1.0 | 1.0 | 0.0962 | 1.0 | 0.0027 | 0.011 | 0.1071 |
| exact_duplicate | rule_detectable | 1.0 | 1.0 | 0.1019 | 0.0028 | 0.011 | 0.0083 | 0.0 |
| fare_over_cap | rule_detectable | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 |
| fare_x10 | plausible | 0.0 | 0.0 | 0.9612 | 0.3712 | 0.6842 | 0.1773 | 1.0 |
| invalid_payment_type | rule_detectable | 1.0 | 1.0 | 0.1264 | 0.0027 | 0.0055 | 0.0082 | 0.0027 |
| negative_fare | rule_detectable | 1.0 | 1.0 | 0.1813 | 1.0 | 0.0577 | 0.0055 | 0.8269 |
| null_mandatory | rule_detectable | 1.0 | 1.0 | 0.1044 | 0.0 | 0.0 | 0.0055 | 0.0027 |
| passenger_overflow | rule_detectable | 1.0 | 1.0 | 0.0824 | 0.0 | 0.0055 | 0.0027 | 0.0 |
| stale_timestamp | rule_detectable | 1.0 | 1.0 | 0.1181 | 0.0082 | 0.0137 | 0.0137 | 0.0027 |
| swapped_zones | plausible | 0.0 | 0.0 | 0.0826 | 0.0 | 0.0055 | 0.0055 | 0.0 |
| tip_spike | plausible | 0.0 | 0.0 | 0.9835 | 0.1653 | 0.7603 | 0.1543 | 0.0 |

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
| yellow_2024-11 | 95.1516 | 95.1516 | 73,800 | 73,800 | 3,646,369 | 128.6 | 80.9 | 3.5 |
| yellow_2024-12 | 95.2894 | 95.2894 | 80,397 | 80,397 | 3,668,371 | 130.1 | 94.3 | 3.2 |
| yellow_2025-01 | 92.1991 | 92.1991 | 146,639 | 146,639 | 3,475,226 | 178.5 | 95.4 | 5.3 |
| yellow_2025-02 | 89.7306 | 89.7306 | 188,388 | 188,388 | 3,577,543 | 221.5 | 107.3 | 3.1 |

## Fare model v1 (hgb_large (HistGradientBoostingRegressor))

trained on yellow_2024-11 (500,000 sampled rule-valid rows), selected and calibrated on yellow_2024-12; flag threshold (log-ratio) 0.9195 = validation quantile 0.995

### Model selection on the validation month

| candidate | MAE $ | RMSE $ | median AE $ | R2 | fit s |
|---|---:|---:|---:|---:|---:|
| hgb_large | 1.303 | 5.005 | 0.393 | 0.9268 | 1.65 |
| hgb_small | 1.358 | 5.030 | 0.418 | 0.9260 | 1.85 |
| hgb_large_l1 | 1.385 | 6.743 | 0.342 | 0.8671 | 13.91 |
| baseline_median | 11.081 | 19.562 | 6.300 | -0.1187 | 0.45 |
| baseline_linear_distance_duration | 4.513 | 9.141 | 3.006 | 0.7557 | 1.34 |

### Performance per partition (all rule-valid records)

| partition | split | n | MAE $ | RMSE $ | median AE $ | R2 | flagged | flag % | MAE / validation | status |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| yellow_2024-11 | train | 3,572,569 | 1.148 | 4.655 | 0.392 | 0.9321 | 16,507 | 0.462 | 0.881 | ok |
| yellow_2024-12 | validation | 3,587,974 | 1.299 | 5.297 | 0.395 | 0.9177 | 17,460 | 0.487 | 0.997 | ok |
| yellow_2025-01 | test | 3,328,587 | 1.128 | 4.700 | 0.398 | 0.9215 | 8,867 | 0.266 | 0.866 | ok |
| yellow_2025-02 | test | 3,389,155 | 1.232 | 4.362 | 0.440 | 0.9240 | 4,619 | 0.136 | 0.946 | ok |

### Permutation importance (increase in validation MAE, $)

| feature | ΔMAE |
|---|---:|
| trip_duration_min | 7.348 |
| trip_distance | 5.547 |
| RatecodeID | 2.511 |
| DOLocationID | 0.125 |
| VendorID | 0.096 |
| PULocationID | 0.054 |
| pickup_hour | 0.033 |
| payment_type | 0.013 |
| passenger_count | 0.011 |
| pickup_dow | 0.004 |

### MAE by payment type ($)

| partition | type 0 | type 1 | type 2 | type 3 | type 4 |
|---|---:|---:|---:|---:|---:|
| yellow_2024-11 | 3.61 | 0.83 | 0.94 | 2.31 | 1.90 |
| yellow_2024-12 | 4.98 | 0.90 | 1.03 | 2.85 | 2.02 |
| yellow_2025-01 | 3.06 | 0.77 | 0.96 | 2.43 | 1.93 |
| yellow_2025-02 | 2.94 | 0.77 | 0.93 | 1.97 | 1.70 |

## Manual review of real fare-model flags

partition yellow_2025-01 (out-of-time), sample 40 (seed 7)

| verdict | count |
|---|---:|
| likely_data_error | 23 |
| flex_fare_semantics | 15 |
| undetermined | 1 |
| plausible_legitimate | 1 |

## Manual review of real anomalies

method: isolation_forest, partition yellow_2025-01, sample 40 (seed 11)

| verdict | count |
|---|---:|
| plausible_legitimate | 29 |
| likely_data_error | 6 |
| undetermined | 5 |
