# Results (generated 2026-10-02T22:20:46+00:00)

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

| detector | precision | 95% CI | recall | 95% CI | FPR | flagged | runtime s |
|---|---:|---|---:|---|---:|---:|---:|
| rules_critical | 1.0 | [1.0, 1.0] | 0.6677 | [0.6557, 0.6809] | 0.0 | 2,913 | 0.125 |
| rules_critical_plus_warning | 1.0 | [1.0, 1.0] | 0.6773 | [0.6658, 0.6916] | 0.0 | 2,955 | 0.125 |
| iqr | 0.0753 | [0.0719, 0.0794] | 0.3585 | [0.3454, 0.3734] | 0.098046 | 20,781 | 0.092 |
| rules_critical+iqr | 0.1657 | [0.1612, 0.1705] | 0.8746 | [0.8655, 0.884] | 0.098046 | 23,033 |  |
| iqr_log | 0.7528 | [0.7311, 0.773] | 0.3064 | [0.2926, 0.3197] | 0.00224 | 1,776 | 0.051 |
| rules_critical+iqr_log | 0.8777 | [0.8669, 0.8882] | 0.7222 | [0.7092, 0.7346] | 0.00224 | 3,590 |  |
| zscore | 0.3476 | [0.3316, 0.3672] | 0.2026 | [0.1921, 0.2143] | 0.008464 | 2,543 | 0.014 |
| rules_critical+zscore | 0.6748 | [0.6624, 0.6878] | 0.7889 | [0.7788, 0.8006] | 0.008464 | 5,101 |  |
| isolation_forest | 0.0994 | [0.0866, 0.1136] | 0.0456 | [0.0393, 0.0524] | 0.009204 | 2,003 | 1.768 |
| rules_critical+isolation_forest | 0.628 | [0.6149, 0.6403] | 0.6981 | [0.6852, 0.7114] | 0.009204 | 4,850 |  |
| fare_model | 0.7807 | [0.7622, 0.8017] | 0.2228 | [0.211, 0.2361] | 0.001393 | 1,245 | 0.186 |
| rules_critical+fare_model | 0.9232 | [0.9148, 0.9318] | 0.7522 | [0.7408, 0.7644] | 0.001393 | 3,555 |  |
| distance_model | 0.599 | [0.5683, 0.6272] | 0.1366 | [0.1264, 0.1474] | 0.002036 | 995 | 0.362 |
| rules_critical+distance_model | 0.8838 | [0.8721, 0.894] | 0.6954 | [0.6836, 0.7072] | 0.002036 | 3,433 |  |
| fare_model+distance_model | 0.6611 | [0.6407, 0.6803] | 0.2929 | [0.2804, 0.3077] | 0.003342 | 1,933 |  |
| rules_critical+fare_model+distance_model | 0.8384 | [0.8267, 0.8487] | 0.7791 | [0.7671, 0.79] | 0.003342 | 4,054 |  |

### Recall by error type

| error type | family | rules_critical | rules_critical_plus_warning | iqr | iqr_log | zscore | isolation_forest | fare_model | distance_model |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| distance_unit_error | rule_detectable | 1.0 | 1.0 | 1.0 | 1.0 | 0.8736 | 0.1209 | 0.7198 | 1.0 |
| distance_x5 | plausible | 0.0 | 0.1157 | 0.4656 | 0.1212 | 0.011 | 0.0303 | 0.022 | 0.3278 |
| dropoff_before_pickup | rule_detectable | 1.0 | 1.0 | 0.0962 | 1.0 | 0.0027 | 0.011 | 0.0742 | 0.2995 |
| exact_duplicate | rule_detectable | 1.0 | 1.0 | 0.1019 | 0.0028 | 0.011 | 0.0083 | 0.0 | 0.0 |
| fare_over_cap | rule_detectable | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 0.0 |
| fare_x10 | plausible | 0.0 | 0.0 | 0.9612 | 0.3712 | 0.6842 | 0.1773 | 1.0 | 0.0028 |
| invalid_payment_type | rule_detectable | 1.0 | 1.0 | 0.1264 | 0.0027 | 0.0055 | 0.0082 | 0.0027 | 0.0 |
| negative_fare | rule_detectable | 1.0 | 1.0 | 0.1813 | 1.0 | 0.0577 | 0.0055 | 0.8516 | 0.0 |
| null_mandatory | rule_detectable | 1.0 | 1.0 | 0.1044 | 0.0 | 0.0 | 0.0055 | 0.0 | 0.0 |
| passenger_overflow | rule_detectable | 1.0 | 1.0 | 0.0824 | 0.0 | 0.0055 | 0.0027 | 0.0 | 0.0 |
| stale_timestamp | rule_detectable | 1.0 | 1.0 | 0.1181 | 0.0082 | 0.0137 | 0.0137 | 0.0027 | 0.0055 |
| swapped_zones | plausible | 0.0 | 0.0 | 0.0826 | 0.0 | 0.0055 | 0.0055 | 0.0 | 0.0 |
| tip_spike | plausible | 0.0 | 0.0 | 0.9835 | 0.1653 | 0.7603 | 0.1543 | 0.0 | 0.0028 |

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

## fare_model v2 — target `fare_amount` ($), hgb_search_05 (HistGradientBoostingRegressor)

trained on yellow_2024-11 (500,000 sampled rule-valid rows), selected and calibrated on yellow_2024-12; flag threshold (log-ratio) 0.9078 = validation quantile 0.995

selection rule: smallest artifact among candidates within 1% of the best validation MAE

### Candidates on the validation month

| candidate | MAE $ | RMSE | median AE | R2 | fit s | size MB | within tolerance | selected |
|---|---:|---:|---:|---:|---:|---:|---|---|
| random_forest | 1.2645 | 4.911 | 0.354 | 0.9295 | 7.2 | 47.59 | yes |  |
| hgb_search_05 | 1.2666 | 4.980 | 0.364 | 0.9275 | 2.43 | 0.81 | yes | **yes** |
| hgb_search_07 | 1.2751 | 5.026 | 0.374 | 0.9262 | 3.37 | 1.28 | yes |  |
| hgb_search_08 | 1.2760 | 4.983 | 0.372 | 0.9274 | 3.64 | 1.04 | yes |  |
| hgb_search_00 | 1.2763 | 4.982 | 0.372 | 0.9274 | 4.45 | 1.07 | yes |  |
| hgb_search_02 | 1.2789 | 4.968 | 0.370 | 0.9279 | 4.04 | 0.79 |  |  |
| hgb_search_09 | 1.3007 | 4.982 | 0.375 | 0.9275 | 4.14 | 1.52 |  |  |
| hgb_default | 1.3028 | 5.005 | 0.393 | 0.9268 | 1.83 | 0.29 |  |  |
| hgb_search_01 | 1.3155 | 5.052 | 0.400 | 0.9254 | 0.92 | 0.18 |  |  |
| hgb_search_04 | 1.3378 | 5.009 | 0.405 | 0.9266 | 1.63 | 0.18 |  |  |
| hgb_search_06 | 1.3387 | 4.995 | 0.413 | 0.9271 | 1.64 | 0.19 |  |  |
| hgb_search_03 | 1.3535 | 5.003 | 0.429 | 0.9268 | 1.57 | 0.18 |  |  |
| baseline_linear | 4.5126 | 9.141 | 3.006 | 0.7557 | 0.04 | 0.00 |  |  |
| baseline_median | 11.0810 | 19.562 | 6.300 | -0.1187 | 0.0 | 0.00 |  |  |

### Performance per partition (all rule-valid records; MAE with 95% bootstrap interval)

| partition | split | n | MAE | 95% CI | RMSE | median AE | R2 | flagged | flag % | MAE / validation | status |
|---|---|---:|---:|---|---:|---:|---:|---:|---:|---:|---|
| yellow_2024-11 | train | 3,572,569 | 1.110 | [1.105, 1.114] | 4.654 | 0.363 | 0.9321 | 16,756 | 0.469 | 0.876 | ok |
| yellow_2024-12 | validation | 3,587,974 | 1.263 | [1.258, 1.269] | 5.280 | 0.366 | 0.9183 | 17,727 | 0.494 | 0.997 | ok |
| yellow_2025-01 | test | 3,328,587 | 1.100 | [1.095, 1.105] | 4.685 | 0.371 | 0.9220 | 9,178 | 0.276 | 0.868 | ok |
| yellow_2025-02 | test | 3,389,155 | 1.204 | [1.200, 1.208] | 4.339 | 0.412 | 0.9248 | 4,823 | 0.142 | 0.951 | ok |

### Rolling-origin backtest (selected configuration refit on month t, evaluated on t+1)

| train | evaluate | MAE | 95% CI | R2 |
|---|---|---:|---|---:|
| yellow_2024-11 | yellow_2024-12 | 1.292 | [1.274, 1.309] | 0.9245 |
| yellow_2024-12 | yellow_2025-01 | 1.225 | [1.209, 1.241] | 0.9245 |
| yellow_2025-01 | yellow_2025-02 | 1.203 | [1.188, 1.218] | 0.9242 |

### Permutation importance (increase in validation MAE)

| feature | ΔMAE |
|---|---:|
| trip_duration_min | 7.471 |
| trip_distance | 5.585 |
| RatecodeID | 2.580 |
| DOLocationID | 0.191 |
| PULocationID | 0.089 |
| VendorID | 0.078 |
| pickup_hour | 0.042 |
| passenger_count | 0.011 |
| payment_type | 0.011 |
| pickup_dow | 0.007 |

### MAE by payment type

| partition | type 0 | type 1 | type 2 | type 3 | type 4 |
|---|---:|---:|---:|---:|---:|
| yellow_2024-11 | 3.56 | 0.80 | 0.91 | 2.34 | 1.86 |
| yellow_2024-12 | 4.96 | 0.85 | 1.01 | 2.85 | 2.00 |
| yellow_2025-01 | 3.08 | 0.74 | 0.92 | 2.39 | 1.86 |
| yellow_2025-02 | 2.93 | 0.73 | 0.89 | 2.00 | 1.63 |

## distance_model v1 — target `trip_distance` (mi), hgb_search_09 (HistGradientBoostingRegressor)

trained on yellow_2024-11 (500,000 sampled rule-valid rows), selected and calibrated on yellow_2024-12; flag threshold (log-ratio) 1.5932 = validation quantile 0.995

selection rule: smallest artifact among candidates within 1% of the best validation MAE

### Candidates on the validation month

| candidate | MAE mi | RMSE | median AE | R2 | fit s | size MB | within tolerance | selected |
|---|---:|---:|---:|---:|---:|---:|---|---|
| hgb_search_00 | 0.7318 | 1.449 | 0.392 | 0.8919 | 6.79 | 2.36 | yes |  |
| hgb_search_07 | 0.7332 | 1.460 | 0.390 | 0.8903 | 8.54 | 3.86 | yes |  |
| hgb_search_05 | 0.7338 | 1.457 | 0.390 | 0.8907 | 5.0 | 2.01 | yes |  |
| hgb_search_02 | 0.7343 | 1.450 | 0.391 | 0.8917 | 6.42 | 2.04 | yes |  |
| hgb_search_08 | 0.7348 | 1.453 | 0.394 | 0.8913 | 8.81 | 2.95 | yes |  |
| hgb_search_09 | 0.7356 | 1.453 | 0.391 | 0.8913 | 3.43 | 1.48 | yes | **yes** |
| hgb_default | 0.7394 | 1.458 | 0.397 | 0.8905 | 4.35 | 1.08 |  |  |
| hgb_search_04 | 0.7396 | 1.453 | 0.397 | 0.8912 | 6.87 | 0.93 |  |  |
| hgb_search_03 | 0.7409 | 1.455 | 0.398 | 0.8910 | 4.85 | 0.68 |  |  |
| hgb_search_01 | 0.7425 | 1.482 | 0.392 | 0.8870 | 3.43 | 1.28 |  |  |
| hgb_search_06 | 0.7497 | 1.467 | 0.403 | 0.8892 | 3.09 | 0.42 |  |  |
| random_forest | 0.7894 | 1.610 | 0.379 | 0.8664 | 6.55 | 47.37 |  |  |
| baseline_median | 2.3157 | 4.671 | 0.910 | -0.1235 | 0.01 | 0.00 |  |  |
| baseline_linear | 2.5138 | 4.132 | 1.805 | 0.1209 | 0.02 | 0.00 |  |  |

### Performance per partition (all rule-valid records; MAE with 95% bootstrap interval)

| partition | split | n | MAE | 95% CI | RMSE | median AE | R2 | flagged | flag % | MAE / validation | status |
|---|---|---:|---:|---|---:|---:|---:|---:|---:|---:|---|
| yellow_2024-11 | train | 3,572,569 | 0.680 | [0.679, 0.681] | 1.339 | 0.357 | 0.9048 | 15,123 | 0.423 | 0.924 | ok |
| yellow_2024-12 | validation | 3,587,974 | 0.739 | [0.738, 0.740] | 1.444 | 0.392 | 0.8910 | 17,924 | 0.500 | 1.004 | ok |
| yellow_2025-01 | test | 3,328,587 | 0.665 | [0.664, 0.667] | 1.355 | 0.332 | 0.8934 | 16,233 | 0.488 | 0.904 | ok |
| yellow_2025-02 | test | 3,389,155 | 0.671 | [0.669, 0.672] | 1.311 | 0.338 | 0.8890 | 20,247 | 0.597 | 0.912 | ok |

### Rolling-origin backtest (selected configuration refit on month t, evaluated on t+1)

| train | evaluate | MAE | 95% CI | R2 |
|---|---|---:|---|---:|
| yellow_2024-11 | yellow_2024-12 | 0.746 | [0.742, 0.751] | 0.8881 |
| yellow_2024-12 | yellow_2025-01 | 0.670 | [0.665, 0.674] | 0.8893 |
| yellow_2025-01 | yellow_2025-02 | 0.686 | [0.681, 0.690] | 0.8823 |

### Permutation importance (increase in validation MAE)

| feature | ΔMAE |
|---|---:|
| trip_duration_min | 1.451 |
| PULocationID | 0.758 |
| DOLocationID | 0.587 |
| pickup_hour | 0.198 |
| RatecodeID | 0.082 |
| pickup_dow | 0.051 |
| VendorID | 0.008 |

### MAE by payment type

| partition | type 0 | type 1 | type 2 | type 3 | type 4 |
|---|---:|---:|---:|---:|---:|
| yellow_2024-11 | 1.01 | 0.64 | 0.66 | 0.70 | 0.74 |
| yellow_2024-12 | 1.07 | 0.70 | 0.74 | 0.75 | 0.84 |
| yellow_2025-01 | 0.92 | 0.62 | 0.66 | 0.66 | 0.77 |
| yellow_2025-02 | 0.94 | 0.60 | 0.63 | 0.60 | 0.71 |

## fare_model: operating points on the benchmark (thresholds from the validation month)

| review budget (alpha) | precision | recall | FPR | flagged | recall distance_x5 | recall fare_x10 |
|---:|---:|---:|---:|---:|---:|---:|
| 0.001 | 0.8361 | 0.1041 | 0.000454 | 543 | 0.0 | 0.9834 |
| 0.002 | 0.8049 | 0.1286 | 0.000694 | 697 | 0.0 | 1.0 |
| 0.005 | 0.7807 | 0.2228 | 0.001393 | 1,245 | 0.022 | 1.0 |
| 0.01 | 0.6837 | 0.3394 | 0.003495 | 2,166 | 0.7052 | 1.0 |
| 0.02 | 0.5825 | 0.3786 | 0.006041 | 2,836 | 0.8595 | 1.0 |

## distance_model: operating points on the benchmark (thresholds from the validation month)

| review budget (alpha) | precision | recall | FPR | flagged | recall distance_x5 | recall fare_x10 |
|---:|---:|---:|---:|---:|---:|---:|
| 0.001 | 0.7344 | 0.0862 | 0.000694 | 512 | 0.0028 | 0.0 |
| 0.002 | 0.6472 | 0.0942 | 0.001143 | 635 | 0.011 | 0.0 |
| 0.005 | 0.599 | 0.1366 | 0.002036 | 995 | 0.3278 | 0.0028 |
| 0.01 | 0.5421 | 0.1962 | 0.003689 | 1,579 | 0.7934 | 0.0028 |
| 0.02 | 0.4161 | 0.2269 | 0.007087 | 2,379 | 0.9366 | 0.0028 |

## Manual review of real fare_model flags

partition yellow_2025-01 (out-of-time), sample 40 (seed 7)

| verdict | count |
|---|---:|
| likely_data_error | 22 |
| flex_fare_semantics | 16 |
| undetermined | 1 |
| plausible_legitimate | 1 |

## Manual review of real distance_model flags

partition yellow_2025-01 (out-of-time), sample 40 (seed 7)

| verdict | count |
|---|---:|
| likely_data_error | 38 |
| undetermined | 1 |
| plausible_legitimate | 1 |

## Manual review of real anomalies

method: isolation_forest, partition yellow_2025-01, sample 40 (seed 11)

| verdict | count |
|---|---:|
| plausible_legitimate | 29 |
| likely_data_error | 6 |
| undetermined | 5 |
