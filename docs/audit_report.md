# Audit Report — October 2026

End-to-end audit of the pipeline, SQL, tests, documentation and business
case against the 9 supplied Olist CSV files. Every statement below is
labelled with how it is known:

- **[executed]** — produced by actually running code during the audit
- **[cross-checked]** — reproduced by a second, independent calculation path
  (pandas directly on the CSVs, no database)
- **[static]** — found by reading code/docs, not by running them
- **[not reproduced]** — a documented figure the supplied data does not yield

## 1. Summary

| | Before audit | After audit |
|---|---|---|
| Pipeline runs end-to-end | **No** — stopped at step 1 (reviews row count), and would then have failed loading `order_items` | Yes, ~2 min on a fresh database [executed] |
| Original 37 tests | Never executed (README said so) | 37/37 pass [executed] |
| Business-finding tests | None | 12 added, 12/12 pass [executed] |
| Tests for the 14 data-quality checks | 5 of 14 checks asserted | All 14 asserted (12 tests added in `test_scorecard_checks.py`), 12/12 pass [executed] |
| SQL behind headline findings | Not in repository | `sql/08_business_findings.sql` (views) |
| Revenue R$13,221,498.11 / 96,478 orders / AOV R$137.04 | Documented | Reproduced [executed][cross-checked] |

Root cause of most documentation drift: the docs were written against an
earlier revision of `olist_order_reviews_dataset.csv` (100,000 rows); the
supplied file is the 99,224-row revision. The other 8 files match.

## 2. Environment used for execution

Linux container, PostgreSQL 16, Python 3.13, pandas 3.1.0, SQLAlchemy 2.1.6,
psycopg2-binary 2.9.13, pytest 9.1.1, Node 22 (business case only). **Not yet
run on Windows** — `docs/windows_runbook.md` covers that.

## 3. Dataset inventory [executed]

Parsed with pandas; "PK dup" = duplicates on the candidate key.

| Dataset | Rows | Cols | Columns with nulls (count) | Exact dup rows | PK dup |
|---|---:|---:|---|---:|---:|
| customers | 99,441 | 5 | none | 0 | 0 (`customer_id`) |
| orders | 99,441 | 8 | approved_at 160; delivered_carrier 1,783; delivered_customer 2,965 | 0 | 0 |
| order_items | 112,650 | 7 | none | 0 | 0 (`order_id, order_item_id`) |
| payments | 103,886 | 5 | none | 0 | 0 (`order_id, payment_sequential`) |
| reviews | 99,224 | 7 | comment_title 87,656; comment_message 58,247 | 0 | 0 on `(review_id, order_id)`; 814 on `review_id` alone |
| products | 32,951 | 9 | category + 3 text/photo cols 610; 4 dimension cols 2 | 0 | 0 |
| sellers | 3,095 | 4 | none | 0 | 0 |
| geolocation | 1,000,163 | 5 | none | **261,831** | n/a (no natural key) |
| category_translation | 71 | 2 | none | 0 | 0 |
| **Total** | **1,550,922** | | | | |

Timestamps are stored as text in the CSVs; all parse cleanly (0 unparseable).
Expected-but-legitimate nulls: delivery dates on undelivered orders, optional
review text, 610 products without category metadata.

**Geolocation.** 261,831 exact duplicate rows; 19,015 distinct zip prefixes,
most with many coordinate points. It is loaded raw, then collapsed to one row
per prefix in `dim_geography`. No fact table or analysis query joins to it,
so it cannot fan out revenue; it is an available dimension, not one the
findings depend on. Joining raw geolocation to customers on zip prefix
*would* multiply rows — the dedup is what prevents that.

## 4. Issues found and fixed

Severity: P0 = cannot run / wrong numbers; P1 = wrong KPI, broken test,
missing validation; P2 = reliability/docs; P3 = cosmetic.

| # | Sev | Issue | Root cause | Fix (file) | Verified by |
|---|---|---|---|---|---|
| 1 | P0 | Pipeline halted at step 1: reviews expected 100,000, file has 99,224 | Counts written against an earlier file revision, hard-coded in 3 places | Single manifest `scripts/config.py`; value 99,224 with provenance note | Pipeline step 1 [executed]; `test_raw_row_counts` |
| 2 | P0 | Load of `order_items` fails: `column "shipping_limit_date" does not exist` | Raw DDL omitted a source column | Added `shipping_limit_date TIMESTAMP NOT NULL` (`sql/01_raw_schema.sql`) | Pipeline step 2 [executed] |
| 3 | P1 | Port 5433 (README, `.env.example`) vs 5432 (all code); `.env` never actually read; `export $(cat .env)` fails on Windows and on the comment lines in `.env.example` | Config duplicated per file | `scripts/config.py` resolves env var → `.env` → default 5432; README/`.env.example` aligned | Pipeline logs masked target URL [executed] |
| 4 | P1 | `scripts/ingest_raw.py` fails once constraints exist (`TRUNCATE` on FK-referenced tables) and never re-applies constraints | Second, drifted copy of load logic | Rewritten to reuse pipeline steps 1–4 | Ran after a full build [executed] |
| 5 | P1 | Scorecard (`sql/07`) printed hard-coded text: "1,467,918 rows" and "827 review_ids (1,629 rows)" — both wrong for this data | Literals instead of queries | All lines computed live; pipeline step 6 now logs it | Step 6 output [executed] |
| 6 | P1 | Headline findings (Nordeste, seller quadrant, spend tiers) had no SQL in repo | Analysis done outside the pipeline | `sql/08_business_findings.sql` views; `tests/test_business_findings.py` | 12/12 tests [executed][cross-checked] |
| 7 | P1 | Repeat-rate-by-spend-tier finding interpreted causally ("primed to repeat") | Tiers use lifetime spend, which repeat buyers accumulate by construction | Added first-order-value view and caveat; Recommendation 4 revised (docs + business case) | `test_first_order_tier_does_not_show_spend_gradient` |
| 8 | P1 | Seller quadrant revenue used all order statuses, contradicting KPI dictionary | Filter not applied | Both bases in `v_seller_quadrant`; KPI-consistent is primary | `test_seller_quadrant_*` |
| 9 | P1 | `test_review_id_is_KNOWN_not_unique` pinned 827 | File revision | Pinned 814 (assertion intent unchanged) | Test passes |
| 10 | P2 | `delay_days` used `EXTRACT(DAY FROM interval)` — truncates toward zero (an order 15 h late showed delay 0 but `is_on_time = FALSE`) | Interval field extraction | Fractional days via `EPOCH/86400` (`sql/06`) | Avg delay −11.18 [executed] |
| 11 | P2 | `sql/05` Q6 late % used truncated `delay_days > 0` → AL 21.41% vs 23.93% elsewhere | Two late definitions | Uses timestamp rule like every other figure | AL = 23.93% [executed] |
| 12 | P2 | Raw geolocation lat/lng `NUMERIC(10,7)` rounded source values (32 extra "duplicates": 261,863 vs 261,831) | Lossy type | `DOUBLE PRECISION` | Scorecard = 261,831 [executed] |
| 13 | P2 | `dim_geography` `DISTINCT ON` had no tie-break → non-deterministic city spelling | Missing ORDER BY keys | Added city/state tie-break | Static |
| 14 | P2 | SQL/CSV/log files read with OS default encoding (cp1252 on Windows) | Implicit encoding | Explicit UTF-8 everywhere | Static (Windows untested) |
| 15 | P2 | SQL file failure left no file context; connections not always disposed | Error handling | Per-file transaction + rollback + named error; `engine.dispose()` in `finally` | Deliberate failure test [executed] |
| 16 | P2 | `verify_schema.py` only printed; never failed | No assertions | Checks columns + row counts, exits 1 on any problem | [executed] |
| 17 | P2 | Unpinned dependencies | — | Tested version ranges in `requirements*.txt` | Install [executed] |
| 18 | P2 | Docs inconsistent with each other and the data (see §7) | File revision + manual transcription | Corrected, with audit notes where a figure changed | §7 |

**Not changed (judgement calls, documented instead):**
- Strict on-time rule (delivery during the estimated day = late; 1,292
  orders). Kept for consistency; calendar-date rule would give 93.23%
  on-time. Documented in `docs/kpi_dictionary.md`.
- `dim_customer` keeps one modal state per person (39 people span >1 state).
  Regional analysis therefore uses the per-order state from `raw.customers`.
- Load uses `pandas.to_sql` (≈2 min total). PostgreSQL `COPY` would be faster
  but was not needed.

## 5. Execution report [executed]

Commands (Linux equivalents of the Windows runbook):

```
python scripts/verify_schema.py   -> SCHEMA CHECK PASSED
python scripts/run_pipeline.py    -> completed successfully (~126 s), exit 0
pytest tests -v                   -> 61 passed
```

Also executed: a second back-to-back pipeline run on the same database
(idempotency), `scripts/ingest_raw.py` after a full build, and a run with
one CSV removed (stopped at step 1, exit code 1, clear message).

Post-run table counts (`analytics.v_row_inventory`):

| Layer | Table | Rows |
|---|---|---:|
| raw | 9 tables | 1,550,922 (as in §3) |
| analytics | dim_date | 1,096 |
| analytics | dim_customer | 96,096 |
| analytics | dim_product | 32,951 |
| analytics | dim_seller | 3,095 |
| analytics | dim_geography | 19,015 |
| analytics | fact_order_items | 112,650 |
| analytics | fact_orders | 99,441 |
| analytics | fact_payments | 103,886 |

Reconciliations: `fact_order_items` vs `fact_orders` delivered revenue
R$13,221,498.11 both; `fact_payments` vs `raw.payments` R$16,008,872.12 both.

## 6. Headline claims — verification

| Claim (README / project summary) | Exact definition | Status | Evidence |
|---|---|---|---|
| ~1.45M rows | Rows in the 9 raw tables | **Inconsistent with evidence** — actual 1,550,922 (~1.55M). No code or doc derives 1.45M; the old scorecard literal (1,467,918) matches nothing. The stated figure *understates* what the pipeline loads. | `test_total_raw_rows` [executed][cross-checked] |
| 14 data-quality issues | Lines of the scorecard in `docs/data_quality.md` | **Reproduced** — 14 checks, each with SQL and a handling decision; 12 non-zero, 2 clean-but-guarded | §8 |
| 37 tests | `tests/test_data_quality.py` | **Reproduced** — 37 collected, 37 pass (after fixing stale pins) | §9 |
| R$13.2M revenue, 96K orders | SUM(item price), status = delivered; distinct orders | **Reproduced** — R$13,221,498.11; 96,478; AOV R$137.04 | tests [executed][cross-checked] |
| Nordeste 2–3× platform late rate | Late = delivered after estimate timestamp; delivered orders with a date; platform includes Nordeste | **Partially supported** — region aggregate 14.33% = **1.77×** (1.92× rest of Brazil); AL 2.95× and MA 2.42× are within 2–3×; other 7 states 1.3–2.0× | `test_nordeste_*` [executed][cross-checked] |
| 212 sellers, R$5.37M, coaching opportunity | ≥20 orders; 0.5·on-time + 0.5·review/5; median splits | **Partially supported** — 207 / R$5.40M (KPI-consistent), 210 / R$5.47M (original all-status basis); 818 sellers and R$6,408 median reproduce exactly on the original basis. Largest revenue quadrant under every variant. Exact 212 not reproducible with the current reviews file. | `test_seller_quadrant_*` [executed] |
| Repeat rate 3% → 8.5% in top 5% spenders | `customer_unique_id`; 2+ delivered orders; tier = lifetime spend ≥ R$420 (≈p95) | **Reproduced numerically** (3.00%, 8.52%, 4,637 customers) — **interpretation corrected**: by first-order value the gradient reverses (2.19% vs 3.19%) | `test_top_spend_tier_repeat_rate`, `test_first_order_tier_…` [executed][cross-checked] |

## 7. Documentation corrections

| Document | Was | Now | Why |
|---|---|---|---|
| data_dictionary, data/README | reviews 100,000; 827 reused ids; 551/555 multi-review orders; null 88.28%/58.25%; order_items 6 cols | 99,224; 789 ids (814 surplus rows); 543/547; 88.34%/58.70%; 7 cols | Supplied file |
| kpi_dictionary | revenue table R$13,221,363.14 / R$15,419,630.29 (contradicted its own summary of R$13,221,498.11) | R$13,221,498.11 / R$15,419,773.75 | Internal inconsistency |
| kpi_dictionary, logistics | avg delay ≈ −9.3 days | −11.18 days | Not reproducible under any definition tried |
| kpi_dictionary | review avg 4.071 | 4.087 | File revision |
| data_quality | 3,407 orders with >1 payment | 2,961 (matches data_model and sql_analysis) | Internal inconsistency |
| sql_analysis | AL 21.41% late; office_furniture 3.61 (n=1,254) | 23.93%; 3.62 (n=1,244) | Fix #11; file revision |
| root_cause, recommendations, scenarios, README | "Nordeste 2–3×" | Region 1.77×; worst states 2–3× | §6 |
| seller_and_category, recommendations, scenarios, business case | 212 / R$5.37M quadrant table | Reproduced table + reconciliation | §6 |
| customer_analysis, recommendations, business case | "primed to repeat" loyalty rationale | Mechanical-gradient caveat; pilot recommendation | Fix #7 |
| business case | Office furniture review 3.50; "distance-driven" stated as established | 3.62; MA-seller counter-example noted; framed as leading hypothesis | Verified numbers |
| testing, assumptions, README | "not executed" | Execution record | Executed |

## 8. The 14 data-quality checks — traceability

| # | Issue | Detection (SQL) | Handling | Test | Value (supplied data) |
|---|---|---|---|---|---|
| 1 | Orphan FKs across 6 core relationships | `02` A1–A6; `07` | Enforced as FKs (`03`) | 6× `test_referential_integrity`; pipeline step 4 | 0 (clean, guarded) |
| 2 | Products with untranslated category | `02` A7; `07` | COALESCE to Portuguese name in `dim_product` | `test_known_category_translation_gap` | 13 products / 2 categories |
| 3 | Orders with no items | `02` A8; `07` | Excluded from revenue via INNER JOIN | `test_scorecard_check_count[03…]`, `test_item_less_orders_excluded_from_revenue` | 775 |
| 4 | Delivered before purchase | `02` B1; `07` | — | `test_no_delivery_before_purchase` | 0 (clean, guarded) |
| 5 | Delivered before carrier handoff | `02` B4; `07` | Excluded from leg-level timing | `test_scorecard_check_count[05…]` | 23 |
| 6 | Carrier handoff before approval | `02` B5; `07` | Retained, flagged | `test_known_carrier_before_approval_anomaly_count` | 1,359 |
| 7 | "Delivered" with null delivery date | `02` B7; `07` | Excluded from on-time/delay (`is_on_time` NULL) | `test_scorecard_check_count[07…]`, `test_null_delivery_date_orders_excluded_from_on_time` | 8 |
| 8 | Canceled with a delivery date | `02` B8; `07` | Flagged | `test_scorecard_check_count[08…]` | 6 |
| 9 | Zero-value payments | `02` C1; `07` | Excluded from avg-payment metrics | `test_scorecard_check_count[09…]` | 9 |
| 10 | Payment vs item+freight mismatch > R$1 | `02` C6–C7; `07` | Revenue defined on item price | `test_scorecard_check_count[10…]` | 249 orders |
| 11 | `review_id` not unique | `02` D2; `07` | Composite PK `(review_id, order_id)` | `test_review_id_is_KNOWN_not_unique` | 789 ids / 814 surplus rows |
| 12 | Geolocation full-row duplicates | `07` | Deduplicated in `dim_geography` | `test_scorecard_check_count[12…]`, `test_geolocation_deduplicates_to_one_row_per_prefix` | 261,831 → 19,015 prefixes |
| 13 | Missing delivery date | `07` | Expected for undelivered orders | `test_scorecard_check_count[13…]` | 2,965 (2.98%) |
| 14 | Missing review comment text | `07` | Optional field; not used | `test_scorecard_check_count[14…]` | 58,247 (58.70%) |

Every one of the 14 checks now has at least one pytest assertion. The nine
that previously had none are in `tests/test_scorecard_checks.py`, kept out
of the original file so the original suite still counts 37.

## 9. The 37 original tests — inventory [executed]

| Test (function × parameters) | Validates | Expected | Actual | Status |
|---|---|---|---|---|
| `test_raw_row_counts` ×9 | Each raw table count = manifest | config.py values | equal | 9 pass |
| `test_referential_integrity` ×6 | Zero orphans per FK | 0 | 0 | 6 pass |
| `test_known_category_translation_gap` | Known gap unchanged | 13 | 13 | pass |
| `test_revenue_reconciles_item_grain_vs_order_grain` | Item vs order grain revenue | equal | 13,221,498.11 both | pass |
| `test_revenue_matches_kpi_dictionary` | Published revenue | 13,221,498.11 | same | pass |
| `test_payments_reconcile_star_vs_raw` | fact_payments = raw | equal | 16,008,872.12 both | pass |
| `test_aov_matches_published_figure` | AOV | 137.04 | 137.04 | pass |
| `test_on_time_rate_matches_published_figure` | On-time % | 91.89 | 91.89 | pass |
| `test_repeat_purchase_rate_matches_published_figure` | Repeat % | 3.00 | 3.00 | pass |
| `test_no_delivery_before_purchase` | Impossible dates | 0 | 0 | pass |
| `test_no_approval_before_purchase` | Impossible dates | 0 | 0 | pass |
| `test_no_estimated_delivery_before_purchase` | Impossible dates | 0 | 0 | pass |
| `test_known_carrier_before_approval_anomaly_count` | Known anomaly | 1,359 | 1,359 | pass |
| `test_order_id_is_unique` | Key uniqueness | 0 dups | 0 | pass |
| `test_customer_id_is_unique` | Key uniqueness | 0 dups | 0 | pass |
| `test_product_id_is_unique` | Key uniqueness | 0 dups | 0 | pass |
| `test_review_id_is_KNOWN_not_unique` | Known non-uniqueness | 814 (was 827) | 814 | pass |
| `test_fact_order_items_grain_matches_source` | Fact grain | 112,650 | 112,650 | pass |
| `test_fact_orders_grain_matches_source` | Fact grain | 99,441 | 99,441 | pass |
| `test_fact_payments_grain_matches_source` | Fact grain | 103,886 | 103,886 | pass |
| `test_dimension_joins_do_not_fan_out_fact_order_items` | No fan-out across 4 dims | 112,650 | 112,650 | pass |
| `test_dim_product_key_is_unique` | Surrogate key | 0 dups | 0 | pass |
| `test_dim_customer_key_is_unique` | Surrogate key | 0 dups | 0 | pass |
| `test_dim_customer_natural_key_is_unique` | Natural key | 0 dups | 0 | pass |

Character of the suite: all 37 are integration tests against a live
database built from the real files; none are unit tests of Python code. Most
pin documented numbers (regression guards); the grain/fan-out and
reconciliation tests are the ones that check structural correctness.

## 10. Schema and join cardinality

| Join | Cardinality | Fan-out risk and handling |
|---|---|---|
| customers → orders (`customer_id`) | 1:1 by construction | `customer_id` is per order; people are `customer_unique_id` (96,096) |
| orders → order_items | 1:N (775 orders have 0) | Revenue summed at item grain; INNER JOIN drops item-less orders |
| orders → payments | 1:N (2,961 orders >1 row; 1 order has 0) | Never joined to items; pre-aggregated in `fact_orders` |
| orders → reviews | 1:N (547 orders >1 review) | Averaged per order first |
| order_items → products / sellers | N:1 | Safe; tested by the fan-out test |
| order with several sellers | 1.3% of orders | Seller revenue uses only that seller's items; order-level flags shared |
| products → category_translation | N:1, 13 unmatched | LEFT JOIN + COALESCE |
| zip prefix → geolocation | 1:N (up to hundreds of points) | Would multiply rows; collapsed in `dim_geography` |

Star schema: facts `fact_order_items` (order item), `fact_orders` (order),
`fact_payments` (payment row); dimensions `dim_date`, `dim_customer` (person),
`dim_product`, `dim_seller`, `dim_geography` (zip prefix, not yet joined by a
fact). FKs from facts to dimensions are declared and enforced.

## 11. Remaining issues / not done

- Windows execution not yet performed (runbook provided).
- Exact 212 / R$5.37M and ~1.45M figures cannot be reproduced from the
  supplied files; the earlier 100,000-row reviews revision was not available
  to test against.
- Business-case and doc figures not covered by a test (category table,
  seller-origin breakdown, March 2018 dip) were re-run once during the audit
  and matched, but are not pinned.
- `dim_geography` is not referenced by any fact table.

## 12. Change log (files)

| File | Change | Fixes | Validated by |
|---|---|---|---|
| `scripts/config.py` (new) | DB URL resolution incl. `.env`, data folder, row-count manifest, table map | #1, #3 | Pipeline + tests |
| `scripts/run_pipeline.py` | Uses config; UTF-8 I/O; per-file transactional SQL execution with rollback; logs masked target DB; runs `08`; new scorecard step; disposes engine | #1–3, #5, #6, #14, #15 | Fresh + repeat runs, failure run |
| `scripts/ingest_raw.py` | Reuses pipeline steps 1–4 | #4 | Run after full build |
| `scripts/verify_schema.py` | Column + row-count checks, exit code | #16 | Run |
| `sql/01_raw_schema.sql` | `shipping_limit_date`; geolocation DOUBLE PRECISION; comment counts | #2, #12 | Load counts, scorecard |
| `sql/05_advanced_sql.sql` | Q6 consistent late rule, fractional days | #11 | psql run |
| `sql/06_star_schema.sql` | Fractional `delay_days`; deterministic `dim_geography` | #10, #13 | Tests |
| `sql/07_data_quality_scorecard.sql` | All values computed live | #5 | Pipeline step 6 |
| `sql/08_business_findings.sql` (new) | Views for Nordeste, seller quadrant, spend tiers, row inventory | #6–8 | 12 tests |
| `tests/conftest.py` (new) | Import path for config | #3 | Test run |
| `tests/test_data_quality.py` | Config import; engine disposal; review_id pin 814 | #1, #9 | 37 pass |
| `tests/test_business_findings.py` (new) | 12 finding tests | #6–8 | 12 pass |
| `tests/test_scorecard_checks.py` (new) | 12 tests covering the 9 previously untested scorecard checks + 3 handling decisions | §8 | 12 pass |
| `requirements*.txt` | Version ranges | #17 | Install |
| `.env.example` | Port 5432, guidance | #3 | — |
| `README.md`, `data/README.md`, `docs/*.md` | Verified figures, setup, troubleshooting | #18 | §7 |
| `business_case/build_business_case.js`, `.docx`, `package-lock.json` | Verified figures, revised Rec 4, regenerated | #7, #8, #18 | Rendered and read |

## 13. Commit hygiene

Safe to commit: everything above. Must stay uncommitted (already
gitignored): `raw_data/*.csv`, `data_export/`, `logs/*.log`, `.env`,
`.venv/`, `business_case/node_modules/`. No credentials appear in any
tracked file (`.env.example` holds a placeholder only).
