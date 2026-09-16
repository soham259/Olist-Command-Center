# Data Dictionary

## Source verification

The CSVs were sourced from a public GitHub mirror of the Olist dataset
(Kaggle itself wasn't reachable from the build environment) and checked
against the dataset's well-known public statistics before being trusted:

| Check | Expected (known dataset) | Found in mirror | Result |
|---|---:|---:|---|
| Orders | 99,441 | 99,441 | Match |
| Order items | 112,650 | 112,650 | Match |
| Products | 32,951 | 32,951 | Match |
| Sellers | 3,095 | 3,095 | Match |
| Geolocation rows | ~1,000,163 | 1,000,163 | Match |

One extra file present in the mirror, `brazil_code_states.csv`, is not part
of the official 9-file Olist release and was excluded from `raw_data/` and
from ingestion.

## Files (9 official files)

| File | Rows | Columns |
|---|---:|---:|
| olist_customers_dataset.csv | 99,441 | 5 |
| olist_orders_dataset.csv | 99,441 | 8 |
| olist_order_items_dataset.csv | 112,650 | 6 |
| olist_order_payments_dataset.csv | 103,886 | 5 |
| olist_order_reviews_dataset.csv | 100,000 | 7 |
| olist_products_dataset.csv | 32,951 | 9 |
| olist_sellers_dataset.csv | 3,095 | 4 |
| olist_geolocation_dataset.csv | 1,000,163 | 5 |
| product_category_name_translation.csv | 71 | 2 |

**Note on the reviews file:** a naive `wc -l` line count on the raw CSV
reports 105,759 lines, but the true row count (parsed correctly) is 100,000.
The difference comes from embedded newline characters inside quoted
`review_comment_message` text — line-counting a CSV isn't the same as
row-counting it once a column contains free text.

## Candidate keys and grain (verified, not assumed)

| Table | Candidate key | Notes |
|---|---|---|
| customers | `customer_id` | Unique, 0 duplicates (99,441/99,441) |
| orders | `order_id` | Unique, 0 duplicates |
| order_items | `(order_id, order_item_id)` | Unique composite key, 0 duplicates |
| payments | `(order_id, payment_sequential)` | Unique composite key, 0 duplicates |
| reviews | ~~`review_id`~~ → `(review_id, order_id)` | **`review_id` alone is NOT unique** — 827 review_id values are reused across two different order_ids (1,629 rows affected). The composite key `(review_id, order_id)` is unique. |
| products | `product_id` | Unique, 0 duplicates |
| sellers | `seller_id` | Unique, 0 duplicates |
| geolocation | none | 261,831 fully duplicate rows out of 1,000,163 — expected for a zip-lookup table scraped at address level; deduplication is handled downstream (`docs/data_model.md`), not forced at raw-load time |
| category_translation | `product_category_name` | Unique, 0 duplicates |

## Key finding: `customer_id` vs. `customer_unique_id`

- `customer_id`: 99,441 unique values — one per row, essentially an
  order-context ID.
- `customer_unique_id`: 96,096 unique values.
- 2,997 `customer_unique_id` values appear more than once.

**Implication:** `customer_id` identifies a customer *per order
relationship*, not a person. Any repeat-purchase or customer-level analysis
has to use `customer_unique_id`, or repeat customers get undercounted (a
customer with 3 orders would otherwise look like 3 different one-time
customers).

## Key finding: reviews are not strictly 1:1 with orders

| Reviews per order | Order count |
|---:|---:|
| 1 | 98,886 |
| 2 | 551 |
| 3 | 4 |

Joining `reviews` to `orders` naively (assuming 1:1) risks fan-out for ~555
orders. Handled explicitly in the star schema (`docs/data_model.md`) by
averaging all reviews attached to an order into a single order-level score.

## Null / missing value summary

| Table | Column | Null % | Likely cause |
|---|---|---:|---|
| orders | order_approved_at | 0.16% | Order likely never approved (canceled before approval) |
| orders | order_delivered_carrier_date | 1.79% | Not yet shipped / canceled |
| orders | order_delivered_customer_date | 2.98% | Not yet delivered / canceled / lost |
| reviews | review_comment_title | 88.28% | Optional field — most customers don't title their review |
| reviews | review_comment_message | 58.25% | Optional free-text field |
| products | product_category_name (+ 3 related cols) | 1.85% | Missing product metadata, 610 products |
| products | dimension/weight columns | 0.01% | 2 products only — negligible |

None of these were deleted. Each is classified and handled explicitly in
`docs/data_quality.md` rather than row-deleted globally.

## order_status distribution

| Status | Count |
|---|---:|
| delivered | 96,478 |
| shipped | 1,107 |
| canceled | 625 |
| unavailable | 609 |
| invoiced | 314 |
| processing | 301 |
| created | 5 |
| approved | 2 |

This directly informs the KPI definitions in `docs/kpi_dictionary.md` — for
example, on-time delivery % is computed only over `delivered` orders.

## Date-range sanity check

`order_purchase_timestamp` spans 2016-09-04 to 2018-10-17, consistent with the
documented ~2016–2018 dataset window. A direct check for `delivered_customer_date
< purchase_timestamp` (an impossible sequence) returned zero violating orders —
a good early signal on date integrity. The fuller set of date-sequencing
anomalies is covered in `docs/data_quality.md`.

## Raw layer design decisions (`sql/01_raw_schema.sql`)

- No foreign keys enforced at the raw layer — referential integrity is
  investigated first (`docs/data_quality.md`) and enforced afterward
  (`sql/03_constraints_and_indexes.sql`), not assumed.
- Original Olist column names preserved exactly, including the source typo
  `product_name_lenght` (not "length") — changing it would make joins against
  the source documentation confusing; it's aliased cleanly in the analytics
  layer instead.
- `reviews`' primary key is `(review_id, order_id)`, not `review_id` alone,
  per the finding above.
