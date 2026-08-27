# Operational Enhancements: Performance, Alerts, CI/CD, and Dashboard Logic

**Scope:** PostgreSQL 15+, Python/SQLAlchemy operations, GitHub Actions, and Power BI
**Repository:** `lo77667/football-prediction-lab`

## 1. PostgreSQL performance design

The migration [`schemas/postgres/002_partitioned_summary_alerts.sql`](../schemas/postgres/002_partitioned_summary_alerts.sql) implements declarative range partitioning by `activity_date`. PostgreSQL's range bounds are lower-inclusive and upper-exclusive, which makes annual partitions straightforward and enables date predicates to prune irrelevant partitions [1]. The migration creates annual partitions for 2015–2035 plus a default partition, copies legacy rows, creates partition-local indexes through the parent, and runs `ANALYZE`.

The choice of `activity_date` is deliberate. `facts.player_load_daily` already owns that key. `facts.player_match_performance` is match-grain and therefore derives `activity_date` from `core.match.kickoff_utc::date`; `season_code` is carried as a reporting attribute rather than used as the partition key. This keeps operational retention and dashboard date filters aligned. If the academy's history extends beyond 2035, create the next partition before the first insert into the default partition.

The migration keeps renamed legacy tables during cutover. This provides a rollback and reconciliation point, but they should not remain indefinitely: after row-count, checksum, application smoke, and dashboard checks pass, archive or drop them in a separately approved migration. A production cutover should run in a maintenance window because the initial `ACCESS EXCLUSIVE` locks and backfill can block writes. For a large table, use a staged migration with a shadow partitioned table, incremental backfill, dual-write or short controlled downtime, and a final rename.

### Materialized view and refresh strategy

`analytics.mv_player_daily_summary` is one row per `(player_id, activity_date)` and pre-aggregates match actions, load, rolling prior-28-observation load, latest eligible reviewed qualitative scores, and missingness flags. A unique index on `(player_id, activity_date)` supports fast dashboard filters and is required for `REFRESH MATERIALIZED VIEW CONCURRENTLY` [2].

Refresh it after all daily structured data and reviewed qualitative features have landed. The refresh must run in autocommit mode because PostgreSQL does not allow the `CONCURRENTLY` form inside a transaction block. A managed scheduler, Airflow/Prefect/Dagster task, or `pg_cron` job can run:

```sql
REFRESH MATERIALIZED VIEW CONCURRENTLY analytics.mv_player_daily_summary;
ANALYZE analytics.mv_player_daily_summary;
```

Use a single-flight lock in the scheduler so two refreshes cannot overlap. Record refresh start, completion, duration, row count, and error in the platform's job log. Alert if the view is older than the agreed service-level objective, if the default partition is non-empty, or if the refresh fails twice. For very large history, retain this interface but replace the full materialization with an incrementally maintained summary table; the dashboard contract should not change.

## 2. Coach-alert design

`analytics.coach_alerts` is an operational event table, not a model-label table. It stores `alert_type`, enum-backed `severity`, `player_id`, `alert_date`, a human-readable `trigger_reason`, machine-readable `evidence`, source snapshot date, acknowledgment state, reviewer fields, resolution fields, and a unique `dedupe_key`. The unique key makes retries safe and preserves one active alert per player/date/pattern unless a future policy explicitly allows multiple alert instances.

The Python implementation is in [`src/football_prediction_lab/player_warehouse/alerts.py`](../src/football_prediction_lab/player_warehouse/alerts.py). `build_high_risk_alerts()` is pure and testable; `scan_and_insert_coach_alerts()` reads only the requested day from the materialized view and inserts with `ON CONFLICT (dedupe_key) DO NOTHING`.

The initial high-risk rule is intentionally conservative:

```text
player_load_au / prior_28_observation_load_avg >= 1.50
AND reviewed confidence_score <= -0.40
AND both values are present
```

Missing baseline or missing qualitative evidence does not become a risk alert. It remains a review/data-quality state. The alert is a prompt for a coach check-in and workload review, not an automated medical or selection decision. Thresholds should be calibrated against academy practice and reviewed by sports science and safeguarding staff.

A daily job should execute only after the summary refresh succeeds:

```python
from datetime import date
from sqlalchemy import create_engine
from football_prediction_lab.player_warehouse.alerts import scan_and_insert_coach_alerts

engine = create_engine("postgresql+psycopg://...")
inserted = scan_and_insert_coach_alerts(
    engine,
    alert_date=date.today(),
    load_ratio_threshold=1.50,
    confidence_threshold=-0.40,
)
print(f"inserted_alerts={inserted}")
```

Credentials belong in the runtime secret manager, never in source control or the command history. The scheduler should also emit metrics for rows scanned, alerts generated, inserts skipped by deduplication, and failures.

## 3. GitHub Actions failure analysis

A workflow that terminates in approximately four seconds with no step logs usually failed before the runner reached the first visible step. Common categories are:

| Category | Examples | Diagnostic action |
|---|---|---|
| Workflow/run admission | Invalid workflow syntax, disabled Actions, branch protection or policy restriction, unavailable billing/runner entitlement | Inspect workflow validation, repository/org Actions settings, and the run's job-level conclusion. |
| Runner allocation | No compatible hosted runner, transient GitHub runner outage, invalid label, job canceled while queued | Re-run once, check GitHub Status, use a stable label such as `ubuntu-22.04`, and inspect queue/cancellation metadata. |
| Service or artifact failure | GitHub cannot provision the job, action artifact/log blob unavailable, token cannot access run logs or annotations | Check the run URL with an authorized maintainer token and open GitHub Support if repeated across commits. |
| Pre-step action failure | Checkout or setup action fails before normal shell output | Pin supported action majors, use `fetch-depth: 0`, and put essential diagnostics immediately after setup. |
| Cancellation/concurrency | A newer push cancels the prior run, or a manual re-run is superseded | Inspect the run's cancellation reason and use a deliberate concurrency group. |
| Secret or permission policy | Organization policy blocks an action or the workflow lacks required permission | Keep permissions least-privilege, inspect policy settings, and avoid assuming that `contents: read` grants checks/log access. |

The previous repository run exhibited the important distinction: local tests passed, while the remote job ended in seconds with no visible steps and the connected token could not retrieve logs/annotations. A step-level debug block cannot repair a job that never starts. The hardened [`quality-gate.yml`](../.github/workflows/quality-gate.yml) improves reproducibility and diagnostics for failures that do reach the runner, while repeated pre-step failures still require GitHub-side runner, Actions-policy, or token-permission investigation.

GitHub's documentation describes workflow-run logs as the place to identify the failed step [3] and supports enabling step debug logging with the `ACTIONS_STEP_DEBUG` variable [4]. The new workflow's `if: failure()` block prints sanitized environment and runner details after step-level failure. It deliberately redacts variables whose names suggest secrets, and it never prints secret values.

The workflow also uses a Python 3.11/3.12 matrix, pinned Ubuntu runner generation, pip caching keyed by `pyproject.toml`, `pip check`, explicit compilation, module-qualified pytest/Ruff invocations, whitespace validation, a timeout, and concurrency cancellation for obsolete runs. These controls improve diagnosis and repeatability but do not hide infrastructure failures behind `continue-on-error`.

## 4. Power BI Daily Go/No-Go logic

The DAX implementation is in [`docs/powerbi_daily_go_no_go.dax`](powerbi_daily_go_no_go.dax). It produces both a numeric score and a categorical decision. The score maps readiness from `[-1, 1]` into `[0, 1]`, maps the load ratio to tolerance bands, and weights readiness 60% and load tolerance 40%. The categorical measure returns `REVIEW` when inputs are missing, `NO-GO` for extreme load or materially low confidence/readiness, `GO` when the combined score is at least `0.65`, and `REVIEW` otherwise.

For correct results, the visual should filter to one player and one activity date. Use the table's own `player_load_au`, `prior_28_observation_load_avg`, `readiness_score`, and `confidence_score` fields. Show the numeric score, decision, freshness timestamp, missingness indicator, and a tooltip explaining that the result is decision support only. Do not use the measure as an automatic session selector or medical clearance.

## 5. Rollout checklist

| Stage | Gate |
|---|---|
| Database migration | Apply to a staging clone, verify partitions, compare legacy/new row counts and checksums, test insert routing, and inspect plans with date predicates. |
| Materialization | Run a complete refresh, create the unique index, test concurrent refresh, and measure dashboard query latency before and after. |
| Alerts | Backtest thresholds on approved historical data, review false-positive burden with coaches, test acknowledgment/resolution workflows, and validate retry idempotency. |
| CI/CD | Confirm both Python matrix jobs reach the debug step on intentional failures, test artifact/log access with a maintainer token, and verify branch protection recognizes the new workflow. |
| Dashboard | Validate DAX under one-player/one-day, squad, and missing-data contexts; ensure raw narratives remain hidden. |
| Production | Approve retention, role-based access, service credentials, refresh SLO, alert escalation, and rollback procedures. |

## References

[1]: https://www.postgresql.org/docs/15/ddl-partitioning.html "PostgreSQL 15: Table Partitioning"

[2]: https://www.postgresql.org/docs/15/sql-refreshmaterializedview.html "PostgreSQL 15: REFRESH MATERIALIZED VIEW"

[3]: https://docs.github.com/actions/managing-workflow-runs/using-workflow-run-logs "GitHub Actions: Using workflow run logs"

[4]: https://docs.github.com/actions/managing-workflow-runs/enabling-debug-logging "GitHub Actions: Enabling debug logging"
