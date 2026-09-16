# KPI Dictionary

This is the single source of truth for every KPI used throughout the
project's analysis and documentation — all SQL and all reported figures
conform to these definitions rather than redefining them ad hoc.

## 1. Revenue

**Definition:** `Revenue = SUM(order_items.price)` for orders where
`order_status = 'delivered'`. Freight is tracked as a **separate** KPI
(`Freight Revenue`), not merged into `Revenue`.

**Investigated before deciding, not assumed:**

| Definition | Total (delivered orders) |
|---|---:|
| Item price only | R$13,221,363.14 |
| Item price + freight | R$15,419,630.29 |
| `payment_value` (all payment rows) | R$15,422,461.77 |
| Difference: payment_value vs. (item price + freight) | R$2,831.48 (0.018%) |

**Why item price (not payment_value, not item+freight) is the primary
Revenue KPI:**

1. **Attributability** — `payment_value` lives at the order/payment grain,
   not the item grain. It can't be cleanly split across categories,
   products, or sellers when an order contains items from multiple
   categories. `price` is already at the correct grain for every category/
   product/seller breakdown.
2. **No fan-out risk** — 2,961 orders have multiple payment rows. Summing
   `payment_value` after any item-level join would double- or triple-count
   for those orders unless pre-aggregated defensively every time. `price`
   carries no such risk by construction.
3. **The aggregate gap is immaterial (0.018%)** — this isn't picking the
   convenient number over the correct one; both definitions agree almost
   exactly at the top line, and the reasons they diverge on individual
   orders (vouchers, discounts, partial payments) are documented in
   `docs/data_quality.md`.

**Freight is reported separately** because it's a pass-through logistics
cost, not sales value — folding it into "Revenue" would inflate the headline
number with something that isn't commercial performance.

**Assumption:** only `delivered` orders count. Undelivered orders have no
realized transaction to recognize as revenue, even if some have order_items
with a price (a canceled order might still have item rows).

## 2. Average Order Value (AOV)

**Definition:** `AOV = Revenue / COUNT(DISTINCT delivered order_id)`

Both numerator and denominator use the same `delivered` filter and the same
order population — a specific compatibility check, since a numerator and
denominator with different grain or filters would silently distort the
ratio.

**Result:** R$137.04.

## 3. On-Time Delivery Rate

**Definition:** among `delivered` orders with a non-null
`order_delivered_customer_date`:

```
on_time = order_delivered_customer_date <= order_estimated_delivery_date
on_time_rate = COUNT(on_time) / COUNT(all qualifying orders)
```

**Exclusions:** the 8 orders with `delivered` status but a NULL delivery date
are excluded — the comparison is undefined without both dates. Non-delivered
orders are excluded entirely — an order still in transit isn't "late" yet in
any meaningful sense.

**Result:** 91.89%.

## 4. Delivery Delay

**Definition:** `delay_days = order_delivered_customer_date -
order_estimated_delivery_date` (positive = late, negative = early), computed
only over the same qualifying population as On-Time Delivery Rate.

**Important clarification:** this formula does not depend on
`order_delivered_carrier_date` at all — it only needs purchase/estimated/
actual delivery dates. The 23-order "delivered before carrier handoff"
anomaly (`docs/data_quality.md`) does **not** corrupt this headline delay
metric. It does corrupt any *leg-level* breakdown (e.g., carrier-to-customer
transit time), which is a separate, more granular metric not defined here.

**Result:** platform average is negative (~-9.3 days) — Olist delivers
earlier than promised on average. Average delay and late-rate can diverge by
state, so both are reported (see `docs/sql_analysis.md`,
`docs/logistics_analysis.md`).

## 5. Cancellation Rate — three related, deliberately separate KPIs

| Metric | Formula | Result |
|---|---|---:|
| Cancellation Rate (strict) | `order_status = 'canceled'` / total orders | 0.63% (625 orders) |
| Unavailable Rate | `order_status = 'unavailable'` / total orders | 0.61% (609 orders) |
| Order Failure Rate (combined) | `order_status IN ('canceled','unavailable')` / total orders | 1.24% (1,234 orders) |

Kept separate because `canceled` and `unavailable` likely have different root
causes (customer/payment/fraud-driven cancellation vs. a stock/inventory
failure on the seller's side) and point to different interventions.
Collapsing them into one number would hide which lever to pull. The combined
figure is offered for an executive-level summary, with the two components
available on drill-down.

## 6. Review Score

**Definition:** `order_review_score = AVG(review_score)` across all review
rows tied to that `order_id` (handles the 555 orders with 2-3 reviews).
Category- and seller-level review scores are then `AVG(order_review_score)` —
averaging the order-level score, not the raw review rows, so a
multi-reviewed order doesn't get proportionally more weight.

**Validation:**

| Method | Result |
|---|---:|
| Raw row-level average (all 100,000 review rows) | 4.071 |
| Order-level average (order-deduplicated first) | 4.071 |

Identical to 3 decimal places at the platform-wide aggregate — the 555
affected orders are too small a share (0.6% of orders) to move the global
number. The order-level method is still used going forward, because it
matters more at the category/seller grain, where a multi-reviewed order
concentrated in a small category could move that category's average more
noticeably.

## KPI Dictionary Summary Table

| KPI | Formula | Population | Value |
|---|---|---|---:|
| Revenue | SUM(order_items.price) | delivered orders | R$13,221,498.11 |
| Freight Revenue | SUM(order_items.freight_value) | delivered orders | R$2,198,275.64 |
| AOV | Revenue / distinct delivered orders | delivered orders | R$137.04 |
| On-Time Delivery Rate | delivered_date <= estimated_date | delivered, non-null delivery date | 91.89% |
| Avg Delivery Delay | delivered_date - estimated_date | delivered, non-null delivery date | ~-9.3 days |
| Cancellation Rate | status = canceled | all orders | 0.63% |
| Unavailable Rate | status = unavailable | all orders | 0.61% |
| Order Failure Rate | status in (canceled, unavailable) | all orders | 1.24% |
| Review Score | AVG(order-level avg review_score) | orders with ≥1 review | 4.071 / 5 |
| Repeat Purchase Rate | customer_unique_id with 2+ delivered orders | delivered orders | 3.00% |
