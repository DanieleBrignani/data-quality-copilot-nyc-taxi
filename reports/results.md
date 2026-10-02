# Results (generated 2026-10-02T23:29:02+00:00)

All values below are read from the warehouse / report files; regenerate with `python -m dqc report`.

## Totals

- partitions: 4
- records processed: 14,367,509
- quarantined records: 489,224 (3.405%)
- warning-only records (kept, flagged): 2,116,777 (14.733%)
- processing time (sum of partitions): 492.8s -> 29,154 rows/s
- schema changes detected between consecutive partitions: 1 (unexpected / contract-breaking: 0)
- drift alerts: 9 (warnings: 2)

## Per partition

| partition | rows | quarantined | % | warning-only | valid % | score | schema | duration s | rows/s | source lag d |
|---|---:|---:|---:|---:|---:|---:|---|---:|---:|---:|
| yellow_2024-11 | 3,646,369 | 73,800 | 2.024 | 442,354 | 97.976 | 94.943 | ok | 95.5 | 38,202 | 47.8 |
| yellow_2024-12 | 3,668,371 | 80,397 | 2.192 | 404,585 | 97.808 | 95.051 | ok | 86.1 | 42,630 | 51.9 |
| yellow_2025-01 | 3,475,226 | 146,639 | 4.220 | 526,416 | 95.780 | 91.994 | additive_change | 108.3 | 32,088 | 81.7 |
| yellow_2025-02 | 3,577,543 | 188,388 | 5.266 | 743,422 | 94.734 | 89.539 | additive_change | 203.0 | 17,622 | 53.7 |

## Stage timings (s)

| partition | read_and_schema | raw_landing | profiling | rules | persist_quality | anomaly | drift |
|---|---:|---:|---:|---:|---:|---:|---:|
| yellow_2024-11 | 0.3 | 52.8 | 2.0 | 7.4 | 14.3 | 18.8 | - |
| yellow_2024-12 | 0.4 | 40.6 | 2.0 | 7.2 | 12.4 | 20.0 | 3.5 |
| yellow_2025-01 | 0.3 | 41.6 | 3.0 | 8.4 | 28.4 | 23.2 | 3.3 |
| yellow_2025-02 | 0.5 | 121.8 | 2.1 | 8.7 | 41.5 | 21.8 | 6.6 |

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
| DQ027_zero_distance_between_zones | warning | 33,832 / 0.928 | 36,728 / 1.001 | 58,735 / 1.690 | 69,752 / 1.950 |
| DQ028_charged_without_trip | warning | 24,685 / 0.677 | 27,254 / 0.743 | 22,104 / 0.636 | 20,270 / 0.567 |
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
| yellow_2024-11 | iqr | 3,572,569 | 311,070 | 8.707 | 1.08 |
| yellow_2024-11 | iqr_log | 3,572,569 | 4,849 | 0.136 | 1.11 |
| yellow_2024-11 | isolation_forest | 3,572,569 | 33,683 | 0.943 | 14.54 |
| yellow_2024-11 | zscore | 3,572,569 | 62,322 | 1.744 | 0.33 |
| yellow_2024-12 | iqr | 3,587,974 | 316,460 | 8.820 | 1.13 |
| yellow_2024-12 | iqr_log | 3,587,974 | 4,301 | 0.120 | 1.13 |
| yellow_2024-12 | isolation_forest | 3,587,974 | 35,614 | 0.993 | 15.69 |
| yellow_2024-12 | zscore | 3,587,974 | 60,619 | 1.690 | 0.35 |
| yellow_2025-01 | iqr | 3,328,587 | 295,939 | 8.891 | 1.27 |
| yellow_2025-01 | iqr_log | 3,328,587 | 6,828 | 0.205 | 1.23 |
| yellow_2025-01 | isolation_forest | 3,328,587 | 33,251 | 0.999 | 18.25 |
| yellow_2025-01 | zscore | 3,328,587 | 62,158 | 1.867 | 0.37 |
| yellow_2025-02 | iqr | 3,389,155 | 267,919 | 7.905 | 1.28 |
| yellow_2025-02 | iqr_log | 3,389,155 | 5,974 | 0.176 | 1.03 |
| yellow_2025-02 | isolation_forest | 3,389,155 | 33,890 | 1.000 | 16.11 |
| yellow_2025-02 | zscore | 3,389,155 | 70,776 | 2.088 | 0.40 |

## Benchmark on injected errors (yellow_2025-01, 200,000 real rule-clean records + 4,363 labelled errors, seed 42)

| detector | precision | 95% CI | recall | 95% CI | FPR | flagged | runtime s |
|---|---:|---|---:|---|---:|---:|---:|
| rules_critical | 1.0 | [1.0, 1.0] | 0.6679 | [0.6559, 0.6815] | 0.0 | 2,914 | 0.136 |
| rules_critical_plus_warning | 1.0 | [1.0, 1.0] | 0.6766 | [0.6648, 0.6901] | 0.0 | 2,952 | 0.136 |
| iqr | 0.0753 | [0.0721, 0.0788] | 0.353 | [0.3406, 0.3664] | 0.096505 | 20,455 | 0.061 |
| rules_critical+iqr | 0.1678 | [0.163, 0.1733] | 0.8742 | [0.8651, 0.884] | 0.096505 | 22,729 |  |
| iqr_log | 0.7595 | [0.7421, 0.778] | 0.317 | [0.3047, 0.331] | 0.002235 | 1,821 | 0.059 |
| rules_critical+iqr_log | 0.8795 | [0.8684, 0.8892] | 0.733 | [0.7207, 0.7463] | 0.002235 | 3,636 |  |
| zscore | 0.3612 | [0.3438, 0.3802] | 0.2031 | [0.1926, 0.2149] | 0.007995 | 2,453 | 0.018 |
| rules_critical+zscore | 0.6865 | [0.6745, 0.6982] | 0.7864 | [0.7757, 0.7997] | 0.007995 | 4,998 |  |
| isolation_forest | 0.1013 | [0.0892, 0.1155] | 0.0465 | [0.0405, 0.0527] | 0.009184 | 2,003 | 2.079 |
| rules_critical+isolation_forest | 0.6279 | [0.6144, 0.6416] | 0.6963 | [0.6841, 0.7102] | 0.009184 | 4,838 |  |
| fare_model | 0.8766 | [0.8568, 0.8938] | 0.2198 | [0.2081, 0.2323] | 0.000689 | 1,094 | 0.239 |
| rules_critical+fare_model | 0.9604 | [0.9539, 0.9662] | 0.7509 | [0.7398, 0.7629] | 0.000689 | 3,411 |  |
| distance_model | 0.8953 | [0.8702, 0.9158] | 0.1313 | [0.1215, 0.1412] | 0.000342 | 640 | 0.528 |
| rules_critical+distance_model | 0.9783 | [0.9726, 0.9828] | 0.6938 | [0.6817, 0.7072] | 0.000342 | 3,094 |  |
| fare_model+distance_model | 0.8655 | [0.8457, 0.8834] | 0.286 | [0.2722, 0.2989] | 0.00099 | 1,442 |  |
| rules_critical+fare_model+distance_model | 0.9458 | [0.9374, 0.9529] | 0.7765 | [0.7657, 0.7877] | 0.00099 | 3,582 |  |

### Recall by error type

| error type | family | rules_critical | rules_critical_plus_warning | iqr | iqr_log | zscore | isolation_forest | fare_model | distance_model |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| distance_unit_error | rule_detectable | 1.0 | 1.0 | 1.0 | 1.0 | 0.9066 | 0.1209 | 0.7253 | 1.0 |
| distance_x5 | plausible | 0.0 | 0.1047 | 0.427 | 0.1212 | 0.0083 | 0.0413 | 0.0055 | 0.3113 |
| dropoff_before_pickup | rule_detectable | 1.0 | 1.0 | 0.0879 | 1.0 | 0.0082 | 0.022 | 0.0577 | 0.2582 |
| exact_duplicate | rule_detectable | 1.0 | 1.0 | 0.0909 | 0.0 | 0.0055 | 0.0083 | 0.0 | 0.0 |
| fare_over_cap | rule_detectable | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 0.0 |
| fare_x10 | plausible | 0.0 | 0.0 | 0.975 | 0.4278 | 0.6056 | 0.1722 | 1.0 | 0.0 |
| invalid_payment_type | rule_detectable | 1.0 | 1.0 | 0.0989 | 0.0055 | 0.011 | 0.011 | 0.0 | 0.0 |
| negative_fare | rule_detectable | 1.0 | 1.0 | 0.1813 | 1.0 | 0.0495 | 0.0137 | 0.8489 | 0.0027 |
| null_mandatory | rule_detectable | 1.0 | 1.0 | 0.1181 | 0.0 | 0.011 | 0.011 | 0.0 | 0.0027 |
| passenger_overflow | rule_detectable | 1.0 | 1.0 | 0.0769 | 0.0027 | 0.0055 | 0.0137 | 0.0 | 0.0 |
| stale_timestamp | rule_detectable | 1.0 | 1.0 | 0.0962 | 0.0027 | 0.0082 | 0.0082 | 0.0 | 0.0 |
| swapped_zones | plausible | 0.0 | 0.0 | 0.0909 | 0.0028 | 0.0028 | 0.011 | 0.0 | 0.0 |
| tip_spike | plausible | 0.0 | 0.0 | 0.9945 | 0.2342 | 0.8127 | 0.1185 | 0.0 | 0.0 |

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
| yellow_2024-11 | 94.9432 | 94.9432 | 73,800 | 73,800 | 3,646,369 | 95.5 | 82.7 | 4.2 |
| yellow_2024-12 | 95.0511 | 95.0511 | 80,397 | 80,397 | 3,668,371 | 86.1 | 157.9 | 10.4 |
| yellow_2025-01 | 91.9935 | 91.9935 | 146,639 | 146,639 | 3,475,226 | 108.3 | 139.3 | 4.8 |
| yellow_2025-02 | 89.5391 | 89.5391 | 188,388 | 188,388 | 3,577,543 | 203.0 | 162.6 | 4.3 |

## fare_model v2 — target `fare_amount` ($), hgb_search_05 (HistGradientBoostingRegressor)

trained on yellow_2024-11 (500,000 sampled rule-valid rows), selected and calibrated on yellow_2024-12; flag threshold (log-ratio) 0.9078 = validation quantile 0.995

selection rule: smallest artifact among candidates within 1% of the best validation MAE

### Candidates on the validation month

| candidate | MAE $ | RMSE | median AE | R2 | fit s | size MB | within tolerance | selected |
|---|---:|---:|---:|---:|---:|---:|---|---|
| random_forest | 1.2645 | 4.911 | 0.354 | 0.9295 | 59.63 | 47.59 | yes |  |
| hgb_search_05 | 1.2666 | 4.980 | 0.364 | 0.9275 | 11.14 | 0.81 | yes | **yes** |
| hgb_search_07 | 1.2751 | 5.026 | 0.374 | 0.9262 | 15.0 | 1.28 | yes |  |
| hgb_search_08 | 1.2760 | 4.983 | 0.372 | 0.9274 | 15.16 | 1.04 | yes |  |
| hgb_search_00 | 1.2763 | 4.982 | 0.372 | 0.9274 | 14.01 | 1.07 | yes |  |
| hgb_search_02 | 1.2789 | 4.968 | 0.370 | 0.9279 | 14.01 | 0.79 |  |  |
| hgb_search_09 | 1.3007 | 4.982 | 0.375 | 0.9275 | 23.43 | 1.52 |  |  |
| hgb_default | 1.3028 | 5.005 | 0.393 | 0.9268 | 8.1 | 0.29 |  |  |
| hgb_search_01 | 1.3155 | 5.052 | 0.400 | 0.9254 | 5.8 | 0.18 |  |  |
| hgb_search_04 | 1.3378 | 5.009 | 0.405 | 0.9266 | 8.88 | 0.18 |  |  |
| hgb_search_06 | 1.3387 | 4.995 | 0.413 | 0.9271 | 4.79 | 0.19 |  |  |
| hgb_search_03 | 1.3535 | 5.003 | 0.429 | 0.9268 | 7.08 | 0.18 |  |  |
| baseline_linear | 4.5126 | 9.141 | 3.006 | 0.7557 | 1.64 | 0.00 |  |  |
| baseline_median | 11.0810 | 19.562 | 6.300 | -0.1187 | 0.1 | 0.00 |  |  |

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
| hgb_search_00 | 0.7318 | 1.449 | 0.392 | 0.8919 | 34.42 | 2.36 | yes |  |
| hgb_search_07 | 0.7332 | 1.460 | 0.390 | 0.8903 | 45.64 | 3.86 | yes |  |
| hgb_search_05 | 0.7338 | 1.457 | 0.390 | 0.8907 | 25.62 | 2.01 | yes |  |
| hgb_search_02 | 0.7343 | 1.450 | 0.391 | 0.8917 | 26.12 | 2.04 | yes |  |
| hgb_search_08 | 0.7348 | 1.453 | 0.394 | 0.8913 | 46.75 | 2.95 | yes |  |
| hgb_search_09 | 0.7356 | 1.453 | 0.391 | 0.8913 | 18.79 | 1.48 | yes | **yes** |
| hgb_default | 0.7394 | 1.458 | 0.397 | 0.8905 | 16.58 | 1.08 |  |  |
| hgb_search_04 | 0.7396 | 1.453 | 0.397 | 0.8912 | 20.11 | 0.93 |  |  |
| hgb_search_03 | 0.7409 | 1.455 | 0.398 | 0.8910 | 17.32 | 0.68 |  |  |
| hgb_search_01 | 0.7425 | 1.482 | 0.392 | 0.8870 | 15.85 | 1.28 |  |  |
| hgb_search_06 | 0.7497 | 1.467 | 0.403 | 0.8892 | 9.6 | 0.42 |  |  |
| random_forest | 0.7894 | 1.610 | 0.379 | 0.8664 | 28.45 | 47.37 |  |  |
| baseline_median | 2.3157 | 4.671 | 0.910 | -0.1235 | 0.01 | 0.00 |  |  |
| baseline_linear | 2.5138 | 4.132 | 1.805 | 0.1209 | 0.06 | 0.00 |  |  |

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
| 0.001 | 0.8953 | 0.1038 | 0.00027 | 506 | 0.0 | 0.9917 |
| 0.002 | 0.8864 | 0.1288 | 0.000367 | 634 | 0.0 | 1.0 |
| 0.005 | 0.8766 | 0.2198 | 0.000689 | 1,094 | 0.0055 | 1.0 |
| 0.01 | 0.8062 | 0.3355 | 0.001796 | 1,816 | 0.6887 | 1.0 |
| 0.02 | 0.6983 | 0.3773 | 0.003628 | 2,357 | 0.8623 | 1.0 |

## distance_model: operating points on the benchmark (thresholds from the validation month)

| review budget (alpha) | precision | recall | FPR | flagged | recall distance_x5 | recall fare_x10 |
|---:|---:|---:|---:|---:|---:|---:|
| 0.001 | 0.9742 | 0.0864 | 5.1e-05 | 387 | 0.0 | 0.0 |
| 0.002 | 0.949 | 0.0937 | 0.000112 | 431 | 0.0165 | 0.0 |
| 0.005 | 0.8953 | 0.1313 | 0.000342 | 640 | 0.3113 | 0.0 |
| 0.01 | 0.7786 | 0.1934 | 0.001224 | 1,084 | 0.7961 | 0.0028 |
| 0.02 | 0.5512 | 0.2271 | 0.004117 | 1,798 | 0.9532 | 0.0056 |

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
