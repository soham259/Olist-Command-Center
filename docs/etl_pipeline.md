# ETL Pipeline

`scripts/run_pipeline.py` — one command, fully reproducible:

```bash
python3 scripts/run_pipeline.py
```

## What it does, step by step

| Step | What happens | Fails the run if... |
|---|---|---|
| 1. Validate source files | Checks all 9 CSVs exist and match expected row counts | Any file missing or row count doesn't match |
| 2. Build raw schema | Runs `01_raw_schema.sql`, loads all 9 tables, verifies loaded count = source count per table | Any table's post-load count mismatches |
| 3. Apply constraints | Runs `03_constraints_and_indexes.sql` (6 FKs + 12 indexes) | Any FK constraint violates (referential integrity broke) |
| 4. Data-quality gate | Re-runs 4 of the audit's orphan-row checks as hard assertions | Any orphan row count > 0 |
| 5. Build star schema | Runs `06_star_schema.sql`, `08_business_findings.sql` and `09_reporting_views.sql` (views + build metadata), then reconciles fact_order_items vs. fact_orders revenue and fact_payments vs. raw.payments | Either SQL file errors (it is rolled back), or either reconciliation doesn't match to the cent |
| 6. Data-quality scorecard | Runs `07_data_quality_scorecard.sql` and logs all 16 lines (every value computed live) | The query errors |
| 7. Export CSVs | Re-exports every `analytics` table to `data_export/*.csv` | Any export fails (e.g. folder not writable) |

**SQL execution order and dependencies.** Only 01, 03, 06, 07, 08 and 09 are
executed by the pipeline. 02 (audit), 04 and 05 (analysis) are read-only
investigation scripts you run yourself with `psql -f` after the pipeline;
they only need the `raw` schema. 08 must run after 06, because 06 drops and
recreates the `analytics` schema. 09 runs after 08 because it reuses its views. After the pipeline,
`python scripts/generate_visuals.py` reads these views to produce every chart and table.

Every step logs to both the console and a timestamped file in `logs/`. On any
failure, the script logs a clear error and exits with a non-zero status —
it doesn't continue silently past a broken assumption.

## Configuration

The pipeline connects to `postgresql+psycopg2://postgres:postgres@localhost:5432/olist`
by default. Override it by setting `OLIST_DB_URL`, either as an environment
variable or in a `.env` file at the project root (copy `.env.example`). All
scripts and tests read it through `scripts/config.py`, so there is exactly
one place it is resolved. The pipeline logs the target database (password
masked) at start-up — check it before letting it run, because steps 2 and 5
drop and recreate the `raw` and `analytics` schemas in that database.

## Design decision: no dbt

See `docs/methodology.md` for the full reasoning — in short, this is a
single, linear, single-contributor pipeline, and a plain Python orchestrator
over SQL files covers the same reproducibility ground without the added
tooling surface dbt brings for multi-model, multi-contributor projects.

## Rerunnability

Both raw and analytics schemas are built with `DROP SCHEMA ... CASCADE` at
the top of their DDL files, and the ingestion step uses `TRUNCATE` before
each table load — running the pipeline twice in a row produces an identical
result, not duplicated data. (Verified in the 2026-10 audit: two
back-to-back runs on the same database, then the full test suite, all
passed. The standalone `scripts/ingest_raw.py` now reuses these same steps.)

## What the CSV export step is for

After the star schema is built and reconciled, every `analytics` table is
exported to `data_export/*.csv`. This makes the finished star schema usable
in a spreadsheet or any BI tool without a live database connection — it's a
general-purpose export, not tied to a specific dashboard tool, and no such
dashboard exists in this repository.

## What's automated vs. what isn't

- Steps 1–7 above are fully automated by `scripts/run_pipeline.py`.
- The pipeline assumes PostgreSQL is already running and the `olist` database
  exists — it does not provision infrastructure.
- The data-quality gate in Step 4 covers 4 of the ~9 relationship checks in
  the full audit (`docs/data_quality.md`) — it's a fast regression guard for
  known-clean relationships on every run, not a re-run of the entire
  exploratory audit. The full audit and the broader test suite
  (`docs/testing.md`) go further.

For a scheduled/production deployment, Steps 1–7 could run on a schedule via
cron, for example:

```bash
# /etc/cron.d/olist-pipeline — run daily at 2 AM
0 2 * * * cd /path/to/olist-command-center && /usr/bin/python3 scripts/run_pipeline.py >> logs/cron.log 2>&1
```

This is a suggested configuration, not something tested against a live
scheduler in this project.
