# Testing

`tests/test_data_quality.py` — 37 collected test cases (via `pytest`
parametrization) across 24 test functions. This is the original suite.

`tests/test_business_findings.py` — 12 test cases added during the 2026-10
audit. They pin the headline findings (delivered orders, total raw rows,
Nordeste rates, seller quadrant, spend tiers and the first-order caveat) to
the views in `sql/08_business_findings.sql`. Kept in a separate file so the
original 37 can still be counted and discussed on their own.

`tests/test_scorecard_checks.py` — 12 test cases added during the 2026-10
audit. Before it, 9 of the 14 data-quality checks in `docs/data_quality.md`
were only printed by the scorecard; it pins each of them (9 parametrized
cases) and asserts 3 of their handling decisions (geolocation dedup to one
row per prefix, item-less orders carry no revenue, undated "delivered"
orders excluded from on-time).

```bash
pytest -v                                # everything (81 tests)
pytest -m "not db" -v                    # the 18 that need no database
pytest tests/test_data_quality.py -v     # original 37 only
```

## Execution record (2026-10 audit)

Run on Linux, PostgreSQL 16, Python 3.13, pandas 3.1, SQLAlchemy 2.1,
psycopg2 2.9.13, pytest 9.1, against a freshly created database after a full
`scripts/run_pipeline.py` run (~2 minutes):

| Suite | Collected | Passed | Failed |
|---|---:|---:|---:|
| `test_data_quality.py` (original) | 37 | 37 | 0 |
| `test_business_findings.py` (added) | 12 | 12 | 0 |
| `test_scorecard_checks.py` (added) | 12 | 12 | 0 |
| `test_generate_visuals.py` (added) | 19 | 19 | 0 |
| `test_notebook.py` (added) | 1 | 1 | 0 |

`tests/test_notebook.py` executes `notebooks/Olist_Analysis.ipynb` from top to
bottom and checks there are no errors, at least 12 charts, and that the
verified headline figures appear in its output.

`tests/test_generate_visuals.py` covers `scripts/generate_visuals.py`: 18
unit tests that need no database (Wilson intervals, small-sample flags, every
data-quality status rule, a check that every measured check has a rule, bad
connection strings, and an unreachable server exiting with code 1 without
printing the password) and 1 integration test that builds the whole report
and checks its numbers (revenue, orders, late rate, Nordeste 14.33% / 1.77×,
207 coaching candidates, 8.52% top-tier repeat rate, no failed checks, no
password in any output). Database-backed tests are marked `db` (see
`pytest.ini`).

Before the audit's fixes, the pipeline could not run at all (it stopped on
the reviews row-count check, then on the missing `shipping_limit_date`
column). Once it could run, 36 of the original 37 passed on the first try; the
one failure was a stale pinned value (review_id duplicates: 827 in the
earlier 100,000-row reviews file, 814 in the supplied file). Two other
pinned values were updated for the same reason: the raw reviews row count
(100,000 → 99,224, now read from `scripts/config.py`). No assertion was
removed or loosened.

Not yet executed on Windows — see `docs/windows_runbook.md`.

## Requirements to run

These tests query a **live PostgreSQL database** with the pipeline already
run (`scripts/run_pipeline.py`) — they are not unit tests against the raw
CSVs directly, and they cannot run in a clean environment with no database.
Set `OLIST_DB_URL` (see `.env.example`) if your local connection string
differs from the default.

## What's covered

| Group | Tests | What it checks |
|---|---:|---|
| Raw row counts | 9 (parametrized) | Every raw table's loaded row count matches the source manifest in `scripts/config.py` |
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

## How to verify locally

```bash
# 1. Start PostgreSQL and create the database
createdb olist

# 2. Place the 9 raw CSVs in raw_data/ (see data/README.md)

# 3. Run the pipeline
python3 scripts/run_pipeline.py

# 4. Run the test suite
pytest tests -v
```
