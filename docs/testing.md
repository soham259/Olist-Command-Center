# Testing

`tests/test_data_quality.py` — 37 collected test cases (via `pytest`
parametrization) across 24 test functions.

```bash
pytest tests/test_data_quality.py -v
```

## Requirements to run

These tests query a **live PostgreSQL database** with the pipeline already
run (`scripts/run_pipeline.py`) — they are not unit tests against the raw
CSVs directly, and they cannot run in a clean environment with no database.
Set `OLIST_DB_URL` (see `.env.example`) if your local connection string
differs from the default.

## What's covered

| Group | Tests | What it checks |
|---|---:|---|
| Raw row counts | 9 (parametrized) | Every raw table's loaded row count matches the known source count |
| Referential integrity | 6 (parametrized) | Zero orphan rows across every enforced FK relationship |
| Known data gaps | 2 | The category-translation gap (13 products) and the review_id-not-unique finding are still present as documented, not silently "fixed" by a future data refresh |
| Revenue reconciliation | 3 | Item-grain vs. order-grain revenue match; revenue matches the published KPI dictionary figure; fact_payments matches raw.payments |
| Published KPI regression | 2 | AOV and on-time rate match the figures published in `docs/kpi_dictionary.md` and `docs/logistics_analysis.md` |
| Repeat-purchase regression | 1 | The 3.00% repeat-purchase figure in `docs/customer_analysis.md` still holds |
| Date-sequencing anomalies | 4 | The exact anomaly counts from `docs/data_quality.md` (0 delivered-before-purchase, 0 approved-before-purchase, 0 estimated-before-purchase, and the known carrier-before-approval count) haven't drifted |
| Duplicate business keys | 4 | order_id, customer_id, and product_id stay unique; review_id is confirmed to still NOT be unique (an intentional negative test) |
| Star-schema grain | 7 | fact_order_items, fact_orders, and fact_payments row counts match their source tables; dimension joins don't fan out fact_order_items; dim_product/dim_customer surrogate and natural keys stay unique |

## Why these specific tests, not a generic test suite

Every test here pins a number this project already reported somewhere in its
documentation — the point isn't generic data-quality testing, it's a
regression guard that catches the documentation going stale if the
underlying data or pipeline changes in the future. If a future Olist data
refresh changed the review_id collision count, for example, the relevant
test would fail loudly rather than the documentation silently becoming
inaccurate.

## What "NOT EXECUTED" means here

This test suite, and the full pipeline, require a running PostgreSQL
instance with the dataset loaded — neither was available in the environment
used to prepare this repository for publication. **The tests were read and
reasoned through for correctness, but not run end-to-end here.** Treat them
as "ready to run, not verified to pass" until you run them yourself locally.

To verify locally:

```bash
# 1. Start PostgreSQL and create the database
createdb olist

# 2. Place the 9 raw CSVs in raw_data/ (see data/README.md)

# 3. Run the pipeline
python3 scripts/run_pipeline.py

# 4. Run the test suite
pytest tests/test_data_quality.py -v
```
