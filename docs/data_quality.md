# Data Quality

All checks referenced here are read-only (`sql/02_data_quality_audit.sql`,
re-run as a consolidated scorecard in `sql/07_data_quality_scorecard.sql`).
Nothing was deleted from the raw data at any point. Every issue below was
classified — legitimate / missing data / suspicious / likely error — and
given an explicit retain / exclude / transform / flag decision.

## A. Referential integrity

| Relationship | Orphan rows | Verdict |
|---|---:|---|
| orders → customers | 0 | Clean |
| order_items → orders | 0 | Clean |
| order_items → products | 0 | Clean |
| order_items → sellers | 0 | Clean |
| payments → orders | 0 | Clean |
| reviews → orders | 0 | Clean |
| products → category_translation | 13 rows (2 distinct categories) | See A1 |
| orders with no order_items | 775 | See A2 |
| orders with no payment | 1 | See A3 |

**A1 — Missing category translations.** Two category names have no English
translation: `portateis_cozinha_e_preparadores_de_alimentos` and `pc_gamer`
(13 products total). Classified as missing reference data, not a product-data
error. Decision: coalesce to the original Portuguese name when displaying
English category names, so these 13 products don't silently disappear from
category-level reporting.

**A2 — 775 orders with zero order_items.** Breakdown by status: `unavailable`
(603), `canceled` (164), `created` (5), `invoiced` (2), `shipped` (1).
Classified as legitimate business behavior — an order that was never
fulfilled can reasonably have no item rows. Decision: retained in
`raw.orders`, but excluded from any revenue or item-grain metric via an INNER
JOIN (not a LEFT JOIN followed by a filter), documented explicitly in
`docs/kpi_dictionary.md`.

**A3 — 1 order with `delivered` status and zero payment rows.** Classified as
likely data error — a delivered order with no recorded payment is
inconsistent with the business process. Decision: retained and flagged in a
data-quality view; excluded from payment-based KPIs, but still counted in
order-count and delivery KPIs where it isn't the numerator.

## B. Date anomalies

| Check | Bad rows | Verdict |
|---|---:|---|
| Delivered before purchase | 0 | Clean |
| Approved before purchase | 0 | Clean |
| Estimated delivery before purchase | 0 | Clean |
| Delivered to customer before handed to carrier | 23 | See B1 |
| Carrier handoff before order approval | 1,359 | See B2 |
| Delivered status but no delivery date | 8 | See B3 |
| Canceled status but has a delivery date | 6 | See B4 |

**B1 — 23 orders where customer-delivery date precedes carrier-handoff
date.** Classified as likely data/logging error. Decision: excluded from
delivery-*duration* calculations, since the sequence is untrustworthy; still
counted toward on-time-vs-late classification, which only needs the customer
delivery date.

**B2 — 1,359 orders where carrier handoff precedes formal approval.**
Concentrated from April 2018 onward (393 in April, 566 in July 2018 alone),
essentially absent before then. Classified as a legitimate process/systems
change (e.g., carrier pickup scans logged before the payment-approval
timestamp finalizes), not row-level corruption. Decision: retained and
flagged, not excluded from any KPI. `order_approved_at` shouldn't be treated
as a strict sequencing gate for logistics timing after this point.

**B3 — 8 "delivered" orders with a null customer-delivery date.** Classified
as missing data — status says delivered but the timestamp wasn't captured (7
of 8 have a carrier-handoff date close to their estimated window, so the
order plausibly was delivered). Decision: excluded from delivery-duration and
on-time/late classification (can't compute without both dates); retained in
revenue and order-count metrics, which don't depend on this field.

**B4 — 6 "canceled" orders that nonetheless have a customer-delivery date**,
several with a multi-week gap between purchase and "delivery." Classified as
suspicious — possibly a cancellation logged after physical delivery (e.g. a
post-delivery dispute). Decision: flagged for exclusion from double-counting
in on-time-delivery-rate and cancellation-rate simultaneously; documented as a
known limitation of the `order_status` field.

## C. Payment anomalies

| Check | Result |
|---|---|
| Zero-value payments | 9 rows |
| Zero installments | 2 rows |
| Max installments observed | 24 (18 orders use exactly 24) |
| Payment type mix | credit_card 73.9%, boleto 19.0%, voucher 5.6%, debit_card 1.5%, not_defined 0.003% |
| Orders with >1 payment row | 3,407 orders (out of 99,440) — mostly 2–3 rows |
| Payment-total vs. item-total reconciliation | 98,089 / 98,665 comparable orders match exactly; 249 orders differ by >R$1 |

**C1 — 9 zero-value payment rows, 2 zero-installment rows.** Likely
legitimate for `payment_type = 'voucher'` (a R$0 voucher line alongside a
real payment). Decision: excluded from "average payment value" metrics (they'd
drag the average down meaninglessly); the order itself is retained everywhere
else.

**C2 — 3 `not_defined` payment_type rows.** Negligible in volume (0.003%).
Decision: bucketed as "Other/Unclassified" in payment-type breakdowns rather
than dropped.

**C3 — 249 orders where SUM(payment_value) differs from SUM(price+freight) by
more than R$1**, up to R$182.81 in the largest case (one case is negative —
paid less than the item total). Classified as suspicious but very likely
legitimate — vouchers, partial refunds, or coupon discounts that this dataset
doesn't itemize separately. Affects 0.25% of orders. Decision: retained
as-is; `payment_value` and `item price + freight` are not treated as
interchangeable definitions of revenue — resolved explicitly in
`docs/kpi_dictionary.md`.

**C4 — orders with many payment rows** (up to 29 installment rows on one
order). Classified as legitimate — high installment counts (up to 24x) are a
normal Brazilian credit-market practice ("parcelamento"). Decision: retained
as-is; installment count used descriptively, never assumed to equal
`payment_sequential` row count.

## D. Duplicate / cardinality checks

| Check | Result |
|---|---|
| customer_unique_id with >1 order | 2,997 unique customers; max 17 orders by one customer |
| review_id reused across >1 order | 827 review_ids, up to 3 distinct orders sharing one review_id |

**D1 — Repeat customers (2,997 of 96,096 unique people, ~3.1%).** Legitimate —
this is exactly what a repeat-purchase KPI is meant to capture. Decision:
retained; `customer_unique_id` (not `customer_id`) used for all customer-level
analysis.

**D2 — review_id collisions across distinct orders**, up to 3 orders sharing
one review_id. Almost certainly a source-side ID-generation quirk. Decision:
never join or aggregate on `review_id` alone — the composite natural key
`(review_id, order_id)` is used everywhere.

## What this means going forward

- Revenue had to explicitly choose between `payment_value` and `item price +
  freight` — the two don't reconcile perfectly for ~0.25% of orders, a known,
  quantified limitation rather than a surprise found later (see
  `docs/kpi_dictionary.md`).
- Delivery KPIs are computed only over orders with valid, internally
  consistent dates — roughly 31 orders (23 + 8) need explicit exclusion, out
  of 99,441 (~0.03%), immaterial to headline numbers but worth stating.
- `order_approved_at` cannot be treated as a hard sequencing gate for
  logistics timing from April 2018 onward — a genuine finding about how the
  business's own data capture changed over time.
- No rows are deleted anywhere. Every decision is either "retain as-is,"
  "retain but exclude from a specific metric," or "transform the display
  value."

## Data-quality scorecard (consolidated)

| Category | Finding | Impact on business reporting |
|---|---|---|
| Referential integrity | 0 orphan rows across all 6 enforced FK relationships | None — every order/item/payment/review traces to a real parent record |
| Reference data gap | 13 products (2 categories) have no English translation | Handled via COALESCE; would silently vanish from category reports without it |
| Order completeness | 775 orders (0.78%) have zero order_items | Fully explained by order_status; excluded from revenue via INNER JOIN, not silently included at zero |
| Date anomaly | 0 orders delivered before purchase | Clean — no impact |
| Date anomaly | 23 orders delivered before carrier handoff | Excluded from leg-level timing; does NOT affect the headline Delivery Delay KPI |
| Date anomaly | 1,359 orders show carrier handoff before approval, concentrated after April 2018 | A genuine business-process signal, documented as a reporting caveat |
| Status/date mismatch | 8 "delivered" orders with null delivery date | Excluded from on-time-rate and delay calculations |
| Status/date mismatch | 6 "canceled" orders with a delivery date present | Flagged to prevent double-counting across KPIs |
| Payment anomaly | 9 zero-value payment rows | Excluded from average-payment-value metrics; retained in order-level metrics |
| Payment/item reconciliation | 249 orders (0.25%) differ by >R$1 between item total and payment total | Explains why Revenue is defined on item price, not payment_value |
| Duplicate key risk | `review_id` reused across 827 distinct order pairs | Composite key `(review_id, order_id)` used everywhere |
| No natural key | Geolocation table: 261,831 of 1,000,163 rows are full duplicates | Deduplicated to 19,015 zip-prefix rows for `dim_geography` |
| Missing values | 2.98% of orders missing delivery date | Consistent with in-progress/canceled/unavailable orders |
| Missing values | 58.25% of reviews have no comment text | Expected — optional field; doesn't affect review score analysis |

Every one of these 14 issues was investigated, classified, and given an
explicit handling decision before any KPI was built on top of it. None were
silently dropped. "Clean," for this dataset, doesn't mean "no issues found" —
it means every issue found has a documented, defensible, and consistently
applied handling rule, which is the bar this project holds itself to.

`sql/07_data_quality_scorecard.sql` re-runs these checks against the current
database state, so this table doubles as a regression check that nothing
drifts on a future data refresh.
