# Adaptive Thresholds, Drift Monitoring, and Longitudinal Feedback

## Adaptive alert policy

The adaptive threshold is calculated by:

```text
adaptive_threshold = base_threshold
                   × age_band_multiplier
                   × season_phase_multiplier
                   × (1 + 0.20 × baseline_volatility_score)
```

The result is clipped to 75%–135% of the base threshold. The first policy defaults tighten sensitivity for younger age bands and recovery/taper phases, while pre-season and higher personal volatility loosen it modestly. These are **operational coaching thresholds**, not medical thresholds or statements about biological maturity. They must be versioned, approved by sports-science and safeguarding staff, and monitored for alert burden and subgroup effects.

| Input | Default behavior | Rationale |
|---|---|---|
| `age_band` | U13–U15 tighten; U16 neutral; U17–U19 slightly loosen | Avoids applying one load-tolerance rule across developmental cohorts. |
| `season_phase` | Recovery/taper tighten; competition neutral; pre-season/transition loosen | Reflects the intended training context rather than treating every calendar day alike. |
| `baseline_volatility_score` | Bounded coefficient of variation from prior 28 observed daily loads | Makes sensitivity player-specific while limiting one noisy history from dominating the policy. |

The production scanner reads `analytics.season_phase_calendar` and `analytics.v_player_load_baseline_volatility`. Missing phase or volatility values fall back to competition and zero volatility. The alert evidence records all inputs and the resulting threshold so a coach can understand why two players received different sensitivity.

## Player-specific baseline volatility

The SQL view in [`schemas/postgres/003_adaptive_trajectory_feedback.sql`](../schemas/postgres/003_adaptive_trajectory_feedback.sql) computes the prior-28-observation coefficient of variation:

```sql
baseline_volatility_score = stddev_samp(prior_loads) / mean(prior_loads)
```

It returns `NULL` until at least seven non-null observations exist and clips the usable score to `[0, 1]`. The view is joined by `player_id` and `activity_date`, preserving the established UUID linkage and avoiding identity data.

## Drift-monitoring dashboard

The implementation in [`src/football_prediction_lab/player_warehouse/drift.py`](../src/football_prediction_lab/player_warehouse/drift.py) compares a locked training baseline with current data for `confidence_score` and `player_load_au`. It computes:

| Statistic | Use | Suggested policy |
|---|---|---|
| Two-sample Kolmogorov–Smirnov statistic and p-value | Detects a difference between two continuous empirical distributions; SciPy exposes this as `ks_2samp` [1]. | Flag if `p < 0.01`, but interpret alongside effect size and sample size. |
| Population Stability Index | Measures bin-level movement using bins learned from baseline only. | Informational at `0.10`; investigate at `0.20`; escalate at `0.25`. |
| Missingness-rate delta | Detects ingestion or consent changes that can look like distribution stability. | Flag at an absolute five-percentage-point change. |
| Sample sufficiency | Prevents unstable conclusions from small academy windows. | Return `insufficient_data` below 20 valid observations per side. |

The monitor should compare current values against the exact training baseline snapshot used by the deployed model, not against a moving baseline. Store `baseline_version`, `feature_set_version`, `as_of_utc`, sample counts, missingness, KS values, PSI, and status in a governed monitoring table or artifact. A drift flag should trigger investigation and possibly a model hold; it should not automatically change player status or alert thresholds.

### Recommended Power BI page

Create a **Model Health / Feature Drift** page with a date slicer and feature selector. Use a line chart for daily/weekly median and interquartile range of `confidence_score` and `player_load_au`, overlaid with the training-baseline median and bands. Add cards for current sample size, missingness delta, KS p-value, KS statistic, PSI, last refresh time, and drift status. Add a matrix by `age_band` and `primary_position` only when the cell has an approved minimum cohort size; otherwise suppress the value and display `Insufficient cohort size`.

The page should contain a table with `feature_name`, `baseline_n`, `current_n`, `baseline_missing_rate`, `current_missing_rate`, `ks_p_value`, `psi`, `drift_status`, and `compared_at_utc`. The page must not display raw coach notes, free-text evidence, names, dates of birth, or safeguarding content. It should be accessible only to analytics, performance leadership, and authorized sports-science roles.

## Longitudinal development trajectory

`analytics.v_player_development_trajectory` returns per-player 6-month and 12-month slopes for analyst rating, progressive actions per 90, key passes per 90, confidence, and readiness. Slopes are normalized to change per 30 days, making the periods comparable when observations are irregular. The view also returns the latest metrics, event counts, and mean recovery days.

A stress event is defined for this operational report as a day with load ratio at least 1.50 or confidence at most -0.40. Recovery is the first subsequent observed day within 30 days with load ratio at most 1.20 and confidence at least -0.20. The resilience score is:

```text
recovery_rate × 1 / (1 + mean_recovery_days / 14)
```

It is bounded to `[0, 1]` and suppressed when there are fewer than two stress events or no recovered event. This is a **performance-recovery indicator**, not a psychological diagnosis. Coaches should see its components, observation count, and uncertainty rather than a standalone label.

## Coach feedback loop

The `analytics.coach_feedback_log` table captures the prediction reference, UUID-based player key, recommendation date, recommended decision, coach action, accuracy rating, optional future observed outcome, role, and a bounded feedback reason. It should be write-accessible only to authorized roles and should never require a coach to enter a player's name.

Feedback should be used in three separate ways:

1. **Monitoring.** Calculate agreement rates, override rates, calibration by recommendation type, and disagreement by age band/position/cohort. A high override rate is a signal to inspect the model or the workflow, not permission to silently tune the model.
2. **Label quality.** When a future outcome becomes available, compare feedback with an objective or independently reviewed outcome. Do not treat a subjective “inaccurate” rating as a ground-truth label without defining the outcome window and review protocol.
3. **Retraining.** Use approved feedback as a weighted evaluation/training sample in the next offline experiment. Weight should reflect role qualification, completeness, time proximity to the decision, and agreement with a defined outcome—not personal identity or seniority alone. Compare old and new models on a frozen temporal holdout, calibration, alert burden, and subgroup metrics. Deploy only after human approval and model-version registration.

A safe iterative loop is:

```text
prediction → coach action → delayed outcome → approved feedback
           → offline evaluation → ablation/calibration/fairness review
           → model registry approval → shadow scoring → controlled release
```

The feedback table is not a real-time self-learning mechanism. Automatic online weight updates are prohibited until the academy has a documented label policy, minimum sample size, drift review, rollback procedure, and safeguarding approval.

## Privacy and safeguarding controls

All tables and views use the established opaque `player_id` UUID. The dashboard and monitoring artifacts must omit direct identifiers and raw narratives. Consent must cover performance analytics, wellness, sports science, and research separately where applicable. Withdrawal should stop future processing and trigger a governed deletion or suppression workflow for raw notes, derived features, predictions, and feedback according to the academy retention policy.

Adaptive thresholds must not infer or expose biological maturity, health status, or a clinical psychological condition. High-risk alerts require a human review and should present proportionate actions such as a direct check-in or workload review. Any safeguarding disclosure must bypass ordinary analytics and route to the authorized safeguarding process.

## References

[1]: https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.ks_2samp.html "SciPy: scipy.stats.ks_2samp"
