# Model card — `fare_model` v1

All figures come from `reports/results.md` (section *Fare model*) and `models/fare_model_v1.json`; `scripts/reproduce.sh` retrains the model and reproduces them, including the artifact's sha256.

## Intended use

Estimate the **expected metered fare** (`fare_amount`, USD) of a NYC yellow-taxi trip from attributes known when the trip ends, and flag records whose actual fare is far from that expectation. It is a **data-quality detector**: flags go to an investigation queue (`dq.model_flags`). It does **not** quarantine, correct or price anything, and must not be used to set or audit fares for individual drivers or passengers.

## Data

| split | partition | role | rows used |
|---|---|---|---:|
| train | yellow_2024-11 | fit all candidates | 500,000 (seeded sample of 3,572,569 rule-valid rows) |
| validation | yellow_2024-12 | model selection, flag-threshold calibration, permutation importance | 300,000 (sample) |
| test | yellow_2025-01, yellow_2025-02 | reported only — never used for any decision | 3,328,587 and 3,389,155 (all rule-valid rows) |

Splits are **chronological** (no shuffling across months): the test months are in the future relative to training, and include the congestion-pricing launch (5 Jan 2025). Only records that pass every critical rule are used, so label noise from known-invalid fares is excluded; records that pass the rules but are still wrong remain in the training data (see Limitations).

## Features and leakage control

`trip_distance`, `trip_duration_min`, `RatecodeID`, `VendorID`, `payment_type`, `passenger_count`, `pickup_hour`, `pickup_dow`, `PULocationID`, `DOLocationID`.

No monetary column is a feature (`tip`, `tolls`, `total`, `extra`, surcharges are forbidden by `features.FORBIDDEN`; a unit test enforces it). Zones (265 categories) are target-encoded with 5-fold cross-fitting inside the scikit-learn pipeline, so the encoding of a training row never uses that row's own target. Missing values are encoded as −1.

## Model

`HistGradientBoostingRegressor` (squared error, learning rate 0.1, 400 iterations, 63 leaves, seed 42), chosen as the lowest validation MAE among five candidates:

| candidate | validation MAE $ | RMSE $ | R² |
|---|---:|---:|---:|
| median baseline | 11.081 | 19.562 | −0.119 |
| linear regression on distance + duration | 4.513 | 9.141 | 0.756 |
| HGB small (200 it., 31 leaves) | 1.358 | 5.030 | 0.926 |
| **HGB large (400 it., 63 leaves)** | **1.303** | **5.005** | **0.927** |
| HGB large, absolute-error loss | 1.385 | 6.743 | 0.867 |

The search is deliberately small: three boosted configurations and two baselines, compared on one validation month. No claim is made that this is the best achievable model.

## Performance

| partition | split | MAE $ | RMSE $ | median AE $ | R² | MAE / validation |
|---|---|---:|---:|---:|---:|---:|
| yellow_2024-11 | train (mostly in-sample) | 1.148 | 4.655 | 0.392 | 0.932 | 0.88 |
| yellow_2024-12 | validation | 1.299 | 5.297 | 0.395 | 0.918 | 1.00 |
| yellow_2025-01 | **test** | 1.128 | 4.700 | 0.398 | 0.922 | 0.87 |
| yellow_2025-02 | **test** | 1.232 | 4.362 | 0.440 | 0.924 | 0.95 |

No degradation out of time: the congestion fee is a separate column, so the metered fare relationship did not move. The median error is ~$0.40; the mean is pulled up by a heavy tail (RMSE ≈ 4–5).

**Error is not uniform across segments** (MAE, $):

| partition | Flex Fare (0) | credit card (1) | cash (2) | no charge (3) | dispute (4) |
|---|---:|---:|---:|---:|---:|
| yellow_2024-12 | 4.98 | 0.90 | 1.03 | 2.85 | 2.02 |
| yellow_2025-01 | 3.06 | 0.77 | 0.96 | 2.43 | 1.93 |
| yellow_2025-02 | 2.94 | 0.77 | 0.93 | 1.97 | 1.70 |

Flex Fare records are 3–5× harder to predict than card or cash trips: their `fare_amount` does not follow the meter. This is independent evidence for the Flex Fare semantics issue found by the rules.

**Permutation importance** (increase in validation MAE when a feature is shuffled): duration 7.35, distance 5.55, RatecodeID 2.51, drop-off zone 0.12, VendorID 0.10, pickup zone 0.05, hour 0.03, payment type 0.01, passenger count 0.01, day of week 0.004.

## Detector

Score: `|ln((fare + 5) / (predicted + 5))|` — symmetric, so "10× too high" and "10× too low" score the same. Threshold 0.9195 = the 99.5th percentile of the score on the validation month, i.e. **0.5% of validation records are flagged by construction**. On the test months the flag rate is 0.27% and 0.14%.

Benchmark on 200,000 real Jan-2025 rule-clean records + 4,363 labelled injected errors:

| detector | precision | recall | false-positive rate |
|---|---:|---:|---:|
| fare model alone | 0.78 | 0.22 | 0.14% |
| rules + fare model | 0.92 | 0.76 | 0.14% |
| rules + log-IQR | 0.88 | 0.72 | 0.22% |
| Isolation Forest alone | 0.10 | 0.05 | 0.92% |

It catches 100% of `fare ×10`, 83% of negative fares and 58% of distance unit errors, and **0–6%** of `tip spike`, `distance ×5` and `swapped zones`.

Manual review of 40 random real flags (Jan 2025, seed 7): 23 likely data errors (mostly trips with ~0 distance and ~0 duration that still carry a fare), 15 Flex Fare semantic inconsistencies, 1 legitimate (a no-charge trip), 1 undetermined → **1 false positive in 40**, against 29 in 40 for Isolation Forest. Verdicts were assigned by the project author, not an independent domain expert.

## Limitations

- **Not a fare authority.** Negotiated fares (RatecodeID 5) and Flex Fares are not determined by distance and time; predictions there are averages of unrelated prices.
- **Zero-distance / zero-duration records**: the model flags them, but partly for the wrong reason — it predicts the average negotiated fare for an input it has rarely seen. A rule ("fare charged with no distance and no duration") would be the right control; the model's contribution was to surface the pattern.
- **Out-of-distribution feature combinations** are handled poorly: a distance multiplied by 5 with an unchanged duration is detected only 6% of the time, because duration dominates the prediction.
- **It cannot see errors that leave the fare relationship intact**: swapped zones, wrong tips, wrong passenger counts.
- **Label noise**: training labels are "passed the rules", not "verified correct".
- **Threshold is a quantile**, so some share of any month is always flagged; the flag rate is not a measure of data quality by itself.
- **One model, one validation month, one training run.** No confidence intervals, no cross-validation across months, no comparison with other model families.
- **Fairness / geography**: errors by borough or zone were not analysed.

## Operations

- **Registry**: `models/fare_model_v1.json` (metadata) + `.joblib` (artifact, 292 KB) and table `dq.model_registry`: version, algorithm, hyper-parameters, features, training partition and the **sha256 of the raw training file**, all candidates' validation metrics, threshold, artifact sha256, library versions. Loading refuses an artifact whose sha256 does not match (tested).
- **Reproducibility**: fixed seeds; retraining on the same raw file reproduces the same metrics, threshold and artifact hash.
- **Serving**: `POST /predict/fare` (read-only) and `GET /model`.
- **Monitoring**: `dq.model_metrics` per partition; Prometheus gauges `dq_model_mae`, `dq_model_mae_vs_validation`, `dq_model_flag_rate`; alert `FareModelDegraded` when MAE exceeds 1.25× the validation MAE. Retraining is a manual, versioned step (`python -m dqc ml train`), never automatic.
