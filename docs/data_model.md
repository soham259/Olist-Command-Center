# Data Model

## Part 1: Relational model (raw layer)

`sql/03_constraints_and_indexes.sql` adds foreign key constraints and indexes
to the `raw` schema. This was safe to do only because the data-quality audit
(`docs/data_quality.md`) had already verified zero orphan rows on every
relationship being constrained — the FK constraints didn't fail on creation,
which itself re-confirms those findings rather than just formalizing them.

### Enforced foreign keys

| Child table | Column | References |
|---|---|---|
| orders | customer_id | customers.customer_id |
| order_items | order_id | orders.order_id |
| order_items | product_id | products.product_id |
| order_items | seller_id | sellers.seller_id |
| payments | order_id | orders.order_id |
| reviews | order_id | orders.order_id |

### One relationship deliberately not enforced as a hard FK

`products.product_category_name → category_translation.product_category_name`
— 13 products reference 2 category names with no translation row. Forcing a
hard FK here would mean either failing the DDL or deleting/nulling 13
legitimate product rows, which conflicts with the principle that the raw
layer mirrors the source as-is. The gap is handled downstream instead: the
analytics layer coalesces to the original Portuguese name when no translation
exists.

### Verified cardinality (measured, not assumed)

```
customers (1) ──< orders (1)
```
Every `customer_id` maps to exactly one order (99,441 orders, 99,441 distinct
`customer_id` values, all count = 1) — confirming `customer_id` is
order-scoped, not a person identity. Repeat purchases only become visible
through `customer_unique_id`.

```
orders (1) ──< order_items (many)
```
88,863 orders have exactly 1 item; the rest scale down from there (7,516 have
2 items, a long tail out to a few orders with 8-10 items). This is why
`fact_order_items` is the finest-grain fact table for revenue — using
order-level data for revenue would either need pre-aggregation or risk
undercounting multi-item orders.

```
orders (1) ──< payments (often 1, sometimes many)
```
96,479 orders (97%) have exactly 1 payment row; 2,961 orders have 2+
(installment splits or mixed payment methods). **This is the most important
cardinality fact for revenue calculation** — joining `order_items` directly to
`payments` without pre-aggregating one side first fans out revenue on those
2,961 orders.

```
orders (1) ──< reviews (usually 1, occasionally 2-3)
```
98,886 orders have exactly 1 review; 551 have 2; 4 have 3. Same fan-out risk
as payments if joined carelessly to order_items.

```
products (1) ──< order_items (many)     |     sellers (1) ──< order_items (many)
```
Confirmed many-to-one in both directions — one product appears in up to 527
order line items across 431 distinct orders; one seller appears in over
2,000 line items.

### Why this matters for the star schema

The two "sometimes many" relationships — payments and reviews relative to
orders — are why a single flat `fact_order_items` joined to everything would
be dangerous. Summing revenue after joining order_items → payments would
inflate revenue for the 2,961 orders with multiple payment rows. This
mechanism is demonstrated concretely below, not just described.

### Indexes added (beyond primary keys)

FK columns aren't auto-indexed by Postgres on the referencing side, only on
the referenced primary-key side — so explicit indexes were added on every FK
column (`orders.customer_id`, `order_items.order_id/product_id/seller_id`,
`payments.order_id`, `reviews.order_id`), plus supporting indexes for common
analytical filters: `orders.order_purchase_timestamp`, `orders.order_status`,
`customers.customer_state`, `sellers.seller_state`,
`products.product_category_name`, `geolocation.geolocation_zip_code_prefix`.

### Entity relationship diagram (raw layer)

```
customers (1) ──< orders (1)
                     │
                     ├──< order_items (many) >── products (1)
                     │         │
                     │         └──> sellers (1)
                     │
                     ├──< payments (1, sometimes 2+)   [installment splits — DO NOT
                     │                                   join to order_items without
                     │                                   pre-aggregating]
                     │
                     └──< reviews (1, sometimes 2-3)   [SAME fan-out risk]

geolocation: many rows per zip_code_prefix — connects to customers/sellers
             via zip_code_prefix, not a formal FK (no single geolocation
             row uniquely identifies a zip prefix)
```

---

## Part 2: Dimensional star schema (analytics layer)

Built in `sql/06_star_schema.sql`, schema `analytics`.

### Grain decisions

| Table | Grain | Row count |
|---|---|---:|
| fact_order_items | one row per order item | 112,650 |
| fact_orders | one row per order | 99,441 |
| fact_payments | one row per payment record | 103,886 |
| dim_customer | one row per **person** (customer_unique_id) | 96,096 |
| dim_product | one row per product | 32,951 |
| dim_seller | one row per seller | 3,095 |
| dim_geography | one row per zip_code_prefix | 19,015 |
| dim_date | one row per calendar day, 2016-2018 | 1,096 |

### Why fact_orders carries pre-aggregated measures instead of being "thin"

`fact_orders` carries `item_revenue`, `freight_revenue`, `payment_value`,
`review_score`, `is_on_time`, and `delay_days`, computed once at ETL time
rather than left for downstream reporting to derive via joins. If a report
joined `fact_order_items` to `payments` or `reviews` live, it would recreate
exactly the fan-out bug this project guards against. Pre-aggregating means the
dangerous join happens once, in SQL, where it's easy to verify.

### Why fact_reviews was NOT created

Review scoring was already resolved to exactly one number per order
(`AVG(review_score)` across that order's reviews), and that number lives in
`fact_orders.review_score`. No business question requires review *text* or
individual review *timestamps* — the only things a standalone `fact_reviews`
table would add. `raw.reviews` remains available if a future analysis
genuinely needs review text.

### Why fact_payments is still kept separate

Even though `fact_orders.payment_value` already has the aggregated total, a
separate `fact_payments` table answers a genuine question `fact_orders`
can't: installment counts and payment-method mix (credit_card 73.9% / boleto
19.0% / voucher 5.6% / debit_card 1.5%). Since payments have no date field of
their own in the source data, `fact_payments.date_key` is a denormalized copy
of the parent order's purchase date, so it can be filtered by `dim_date`
directly without a fact-to-fact join.

### Dimension deduplication decisions (verified with data)

**dim_customer:** grain is `customer_unique_id`. 39 people show more than one
state across their orders (38 with 2 states, 1 with 3) — resolved by taking
each person's most frequently occurring state/city, tie-broken
deterministically. This affects 0.04% of customers and isn't material to any
state-level rollup.

**dim_geography:** the raw `geolocation` table has no natural key (261,831
duplicate rows) and, on closer inspection, up to 5 different city-name
spellings for the same zip prefix (free-text entry noise) and 8 zip prefixes
spanning 2 different states. Resolved by taking the most-frequent city/state
per prefix and averaging all lat/lng points for that prefix — an explicit
approximation for state/city-level rollups, not precise individual-address
mapping.

### Validation performed

| Check | Result |
|---|---|
| fact_order_items revenue vs. fact_orders' pre-aggregated revenue | Identical: R$13,221,498.11 both ways |
| fact_payments total vs. raw.payments total | Identical: R$16,008,872.12 both ways |
| On-time delivery rate recomputed from fact_orders | 91.89% — matches the SQL analysis exactly |
| Row counts vs. source | fact_order_items = 112,650, fact_orders = 99,441, fact_payments = 103,886 — all exact |

**The fan-out risk was proven, not just asserted.** A deliberate "wrong"
query — joining `order_items` directly to `payments` and summing price — was
run side by side with the correct figure:

| Method | Revenue |
|---|---:|
| Correct (fact_order_items, no fan-out) | R$13,591,643.70 (all statuses) |
| Wrong (order_items naively joined to payments) | R$14,209,115.34 (all statuses) |

The naive join inflates revenue by ~4.5% — a concrete demonstration of the
fan-out mechanism the raw-layer grain analysis above flagged as a risk.

### Entity relationship diagram (analytics layer)

```
                    dim_date
                       │
    dim_customer ──┐   │   ┌── dim_product
                    │   │   │
                fact_order_items ── dim_seller
                    │
                fact_orders (1:1 with orders, pre-aggregated measures)
                    │
                fact_payments (many:1 with orders, own date_key)

dim_geography: standalone, joined via zip_code_prefix from dim_customer/
               dim_seller when a query needs lat/lng — not a hard FK
               (matches the raw-layer decision above)
```
