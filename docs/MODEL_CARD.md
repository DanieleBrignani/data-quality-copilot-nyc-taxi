# Model card — `fare_model` v2 and `distance_model` v1

All figures come from `reports/results.md` and `models/*.json`. `scripts/reproduce.sh` retrains both models; training is deterministic, so it reproduces the same artifacts byte for byte.

## Intended use

Two regression models used as **data-quality detectors** on NYC yellow-taxi trip records:

| model | predicts | question |
|---|---|---|
| `fare_model` | metered fare (`fare_amount`, USD) | is this fare consistent with this trip? |
| `distance_model` | trip distance (`trip_distance`, miles) | is this distance consistent with this trip? |

A record whose actual value is far from the prediction is flagged and sent to an investigation queue (`dq.model_flags`). The models do **not** quarantine, correct or price anything, and must not be used to set or audit fares for individual drivers or passengers.

## Data

| split | partition | role | rows |
|---|---|---|---:|
| train | yellow_2024-11 | fit every candidate | 500,000 (seeded sample of 3,572,569 rule-valid rows) |
| validation | yellow_2024-12 | model selection, flag-threshold calibration, permutation importance | 300,000 (sample) |
| test | yellow_2025-01, yellow_2025-02 | reported only — never used for a decision | 3,328,587 and 3,389,155 (all rule-valid rows) |

Splits are chronological. The test months are in the future relative to training and include the congestion-pricing launch (5 Jan 2025). Only records that pass every critical rule are used; records that pass the rules but are still wrong remain in the training data (see Limitations).

## Features and leakage control

- `fare_model`: `trip_distance`, `trip_duration_min`, `RatecodeID`, `VendorID`, `payment_type`, `passenger_count`, `pickup_hour`, `pickup_dow`, `PULocationID`, `DOLocationID`.
- `distance_model`: `trip_duration_min`, `RatecodeID`, `VendorID`, `pickup_hour`, `pickup_dow`, `PULocationID`, `DOLocationID`.

No model sees its own target or any monetary column (tip, tolls, total, extra, surcharges). The distance model does not see the fare either, so a wrong fare cannot hide a wrong distance. A unit test enforces all three constraints. Zones (265 categories) are target-encoded with 5-fold cross-fitting inside the scikit-learn pipeline. Missing values are encoded as −1.

## Candidates and selection

Per model: a median baseline, a linear baseline, a random forest (trained on 200k rows), a default gradient boosting, and a seeded random search over 10 gradient-boosting configurations (learning rate, iterations, leaves, minimum leaf size, L2).

**Selection rule, fixed before looking at results:** among the candidates within 1% of the best validation MAE, take the smallest serialised model.

| | fare model (MAE $) | distance model (MAE mi) |
|---|---:|---:|
| median baseline | 11.081 | 2.316 |
| linear baseline | 4.513 | 2.514 |
| random forest | **1.2645** (47.6 MB) | 0.789 (47.4 MB) |
| gradient boosting, default | 1.303 (0.29 MB) | 0.739 (1.08 MB) |
| best searched configuration | 1.2666 (0.81 MB) | 0.732 (2.36 MB) |
| **selected** | **1.2666 (0.81 MB)** — lr 0.1, 600 iterations, 255 leaves, min leaf 50, L2 1.0 | **0.736 (1.48 MB)** — lr 0.2, 600 iterations, 255 leaves, min leaf 200, L2 10.0 |

For the fare model the random forest is the most accurate by $0.002 and 59× larger; the rule selects the gradient boosting. The whole search improved the fare MAE by 3% over the default configuration: the model is limited by the data, not by the algorithm. No statistical test was run between candidates; "within 1%" is a practical tolerance, not a significance claim.

## Performance

MAE with a 95% interval computed on the same rows as the estimate (normal approximation above 200k rows, percentile bootstrap below).

**Fare model ($)**

| partition | split | MAE | 95% CI | median AE | R² | MAE / validation |
|---|---|---:|---|---:|---:|---:|
| yellow_2024-11 | train (mostly in-sample) | 1.110 | [1.105, 1.114] | 0.36 | 0.932 | 0.88 |
| yellow_2024-12 | validation | 1.263 | [1.258, 1.269] | 0.37 | 0.918 | 1.00 |
| yellow_2025-01 | **test** | 1.100 | [1.095, 1.105] | 0.37 | 0.922 | 0.87 |
| yellow_2025-02 | **test** | 1.204 | [1.200, 1.208] | 0.41 | 0.925 | 0.95 |

**Distance model (miles)**

| partition | split | MAE | 95% CI | R² | MAE / validation |
|---|---|---:|---|---:|---:|
| yellow_2024-11 | train (mostly in-sample) | 0.680 | [0.679, 0.681] | 0.905 | 0.92 |
| yellow_2024-12 | validation | 0.739 | [0.738, 0.740] | 0.891 | 1.00 |
| yellow_2025-01 | **test** | 0.665 | [0.664, 0.667] | 0.893 | 0.90 |
| yellow_2025-02 | **test** | 0.671 | [0.669, 0.672] | 0.889 | 0.91 |

**Rolling-origin backtest** — the selected configuration refit on month *t* and evaluated on *t+1* (300k sampled rows):

| train → evaluate | fare MAE $ [95% CI] | fare R² | distance MAE mi [95% CI] | distance R² |
|---|---|---:|---|---:|
| 2024-11 → 2024-12 | 1.292 [1.274, 1.309] | 0.925 | 0.746 [0.742, 0.751] | 0.888 |
| 2024-12 → 2025-01 | 1.225 [1.209, 1.241] | 0.925 | 0.670 [0.665, 0.674] | 0.889 |
| 2025-01 → 2025-02 | 1.203 [1.188, 1.218] | 0.924 | 0.686 [0.681, 0.690] | 0.882 |

Performance does not depend on which month is used for training, and there is no degradation across the congestion-pricing launch: the fee is a separate column, so neither relationship moved. The backtest evaluates; it selects nothing.

**Error is not uniform across segments.** Fare-model MAE by payment type ($):

| partition | Flex Fare (0) | credit card (1) | cash (2) | no charge (3) | dispute (4) |
|---|---:|---:|---:|---:|---:|
| yellow_2024-12 | 4.96 | 0.85 | 1.01 | 2.85 | 2.00 |
| yellow_2025-01 | 3.08 | 0.74 | 0.92 | 2.39 | 1.86 |
| yellow_2025-02 | 2.93 | 0.73 | 0.89 | 2.00 | 1.63 |

Flex Fare records are 3–6× harder to price than card or cash trips: their `fare_amount` does not follow the meter. This is independent evidence for the Flex Fare semantics issue found by the rules. The distance model shows a much smaller gap (0.92–1.07 mi for Flex Fare vs 0.60–0.70 for card), as expected: distance does not depend on how the fare is reported.

**Permutation importance** (increase in validation MAE): fare model — duration 7.47, distance 5.58, rate code 2.58, drop-off zone 0.19, pickup zone 0.09, vendor 0.08, hour 0.04. Distance model — duration 1.45, pickup zone 0.76, drop-off zone 0.59, hour 0.20, rate code 0.08.

## Detectors

Score: `|ln((actual + floor) / (predicted + floor))|` (floor $5 for the fare, 0.5 mi for the distance) — symmetric, so "10× too high" and "10× too low" score the same. Threshold: the 99.5th percentile of the score on the validation month, i.e. a **0.5% review budget fixed in advance and identical for both models** (fare 0.908, distance 1.593). By construction 0.5% of validation records are flagged; on the test months the fare model flags 0.28% and 0.14%, the distance model 0.49% and 0.60%.

Benchmark: 200,000 real Jan-2025 records that pass every rule of ruleset 1.4.0 + 4,363 labelled injected errors; 95% bootstrap intervals over benchmark rows. Under ruleset 1.3.0 the same models scored precision 0.78 (fare) and 0.60 (distance): the two new rules removed zero-distance records from the "clean" pool — records the models were flagging correctly.

| detector | precision | recall | false-positive rate |
|---|---|---|---:|
| fare model | 0.88 [0.86–0.89] | 0.22 [0.21–0.23] | 0.07% |
| distance model | 0.90 [0.87–0.92] | 0.13 [0.12–0.14] | 0.03% |
| rules + fare model | 0.96 [0.95–0.97] | 0.75 [0.74–0.76] | 0.07% |
| rules + both models | 0.95 [0.94–0.95] | 0.78 [0.77–0.79] | 0.10% |
| rules + log-IQR | 0.88 [0.87–0.89] | 0.73 [0.72–0.75] | 0.22% |
| Isolation Forest | 0.10 [0.09–0.12] | 0.05 [0.04–0.05] | 0.92% |

Operating points (thresholds from the validation month; the budget was not changed after seeing this):

| budget | fare: precision / recall | fare: `fare ×10` | distance: precision / recall | distance: `distance ×5` |
|---:|---|---:|---|---:|
| 0.1% | 0.90 / 0.10 | 0.99 | 0.97 / 0.09 | 0.00 |
| 0.2% | 0.89 / 0.13 | 1.00 | 0.95 / 0.09 | 0.02 |
| **0.5%** | **0.88 / 0.22** | **1.00** | **0.90 / 0.13** | **0.31** |
| 1.0% | 0.81 / 0.34 | 1.00 | 0.78 / 0.19 | 0.80 |
| 2.0% | 0.70 / 0.38 | 1.00 | 0.55 / 0.23 | 0.95 |

Manual review of 40 random real flags per model (Jan 2025, seed 7):

| verdict | fare model | distance model |
|---|---:|---:|
| likely data error | 22 | 38 |
| Flex Fare semantic inconsistency | 16 | 0 |
| plausible legitimate | 1 | 1 |
| undetermined | 1 | 1 |

One false positive in 40 for each model, against 29 in 40 for Isolation Forest. Verdicts were assigned manually by a single reviewer, not by an independent domain expert.

## Limitations

- **Not a fare authority.** Negotiated fares (RatecodeID 5) and Flex Fares are not determined by distance and time; predictions there are averages of unrelated prices.
- **Zero-distance / zero-duration records**: the fare model flags them partly for the wrong reason — it predicts an average negotiated fare for an input it rarely saw. Both manual reviews pointed to a missing rule; it now exists (DQ027 / DQ028, ruleset 1.4.0).
- **Errors that leave the modelled relationship intact are invisible**: swapped pickup/drop-off zones (0%), tip spikes (0%), wrong passenger counts.
- **`distance ×5` is only partly caught** at the fixed budget (31%); a larger budget catches more at the cost of precision.
- **Label noise**: training labels are "passed the rules", not "verified correct" — the reviews show that zero-distance trips are in the training data.
- **Thresholds are quantiles**, so some share of any month is always flagged; the flag rate is not a measure of data quality by itself.
- **One validation month for selection**, a 10-configuration search, two model families, no significance test between candidates.
- **Intervals are for the mean error**, not prediction intervals for individual trips.
- **Benchmark errors are synthetic** corruptions of real records; recall on real-world error types may differ.
- **Fairness / geography**: errors by borough or zone were not analysed.

## Operations

- **Registry**: `models/<name>_v<N>.json` + `.joblib` and table `dq.model_registry`: version, algorithm, hyper-parameters, features, training partition and the **sha256 of the raw training file**, every candidate's metrics and size, the selection rule, thresholds for five budgets, backtest, artifact sha256, library versions. History is kept: `fare_model` v1 (default configuration, 0.29 MB) and v2 (after the search) are both registered. Loading refuses an artifact whose sha256 does not match (tested).
- **Reproducibility**: fixed seeds; retraining on the same raw file reproduces the artifact byte for byte and therefore does not create a new version (tested).
- **Serving**: `POST /predict/fare` (read-only) and `GET /model`.
- **Monitoring**: `dq.model_metrics` per model and partition; Prometheus gauges `dq_model_mae`, `dq_model_mae_vs_validation`, `dq_model_flag_rate`; alert `ModelDegraded` when MAE exceeds 1.25× the validation MAE. Retraining is a manual, versioned step (`python -m dqc ml train`), never automatic.
