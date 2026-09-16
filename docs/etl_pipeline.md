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
| 5. Build star schema | Runs `06_star_schema.sql`, then reconciles fact_order_items vs. fact_orders revenue and fact_payments vs. raw.payments | Either reconciliation doesn't match to the cent |
| 6. Export CSVs | Re-exports every `analytics` table to `data_export/*.csv` | (does not fail the run — best-effort export) |

Every step logs to both the console and a timestamped file in `logs/`. On any
failure, the script logs a clear error and exits with a non-zero status —
it doesn't continue silently past a broken assumption.

## Configuration

The pipeline connects to `postgresql+psycopg2://postgres:postgres@localhost:5432/olist`
by default. Override this by setting the `OLIST_DB_URL` environment variable
(see `.env.example`) if your local setup differs.

## Design decision: no dbt

See `docs/methodology.md` for the full reasoning — in short, this is a
single, linear, single-contributor pipeline, and a plain Python orchestrator
over SQL files covers the same reproducibility ground without the added
tooling surface dbt brings for multi-model, multi-contributor projects.

## Rerunnability

Both raw and analytics schemas are built with `DROP SCHEMA ... CASCADE` at
the top of their DDL files, and the ingestion step uses `TRUNCATE` before
each table load — running the pipeline twice in a row produces an identical
result, not duplicated data.

## What the CSV export step is for

After the star schema is built and reconciled, every `analytics` table is
exported to `data_export/*.csv`. This makes the finished star schema usable
in a spreadsheet or any BI tool without a live database connection — it's a
general-purpose export, not tied to a specific dashboard tool, and no such
dashboard exists in this repository.

## What's automated vs. what isn't

- Steps 1–6 above are fully automated by `scripts/run_pipeline.py`.
- The pipeline assumes PostgreSQL is already running and the `olist` database
  exists — it does not provision infrastructure.
- The data-quality gate in Step 4 covers 4 of the ~9 relationship checks in
  the full audit (`docs/data_quality.md`) — it's a fast regression guard for
  known-clean relationships on every run, not a re-run of the entire
  exploratory audit. The full audit and the broader test suite
  (`docs/testing.md`) go further.

For a scheduled/production deployment, Steps 1–6 could run on a schedule via
cron, for example:

```bash
# /etc/cron.d/olist-pipeline — run daily at 2 AM
0 2 * * * cd /path/to/olist-command-center && /usr/bin/python3 scripts/run_pipeline.py >> logs/cron.log 2>&1
```

This is a suggested configuration, not something tested against a live
scheduler in this project.
