# SQL Analysis

Queries live in `sql/04_sql_foundation.sql` and `sql/05_advanced_sql.sql`.
Every query answers a specific business question — none exist purely to
demonstrate syntax.

## Working revenue definition used in this analysis

`revenue = SUM(order_items.price)`, freight tracked separately, on
`delivered` orders, joined via an INNER JOIN from orders to order_items.
Item-grain data has a clean, verified 1-row-per-item structure (no fan-out
risk), and `payment_value` was avoided at this grain because 2,961 orders
have multiple payment rows — summing it after any item-level join would
inflate those orders' revenue. The full formal definition, including why this
beats `payment_value` as the platform-wide KPI, is in
`docs/kpi_dictionary.md`.

## Foundational queries

**Total revenue.** INNER JOIN from orders to order_items — an item-less order
contributes nothing and shouldn't appear. A LEFT JOIN would let the 775
item-less orders appear with a NULL price, either breaking the SUM or (worse)
coalescing to 0 and dragging down AOV by inflating the denominator without
inflating the numerator. **Result: 96,478 delivered orders, R$13,221,498.11 in
item revenue, R$2,198,275.64 in freight, AOV = R$137.04.**

**Monthly revenue trend.** Uses `DATE_TRUNC('month', order_purchase_timestamp)`
rather than the delivery date, since revenue should be recognized at the
point of purchase commitment, not fulfillment. Revenue grows steadily from
R$135 in Sep 2016 (dataset start, single order) through ~R$988K in Nov 2017
(likely a Black Friday effect) up to a plateau around R$850K–980K/month
through mid-2018. Data thins out sharply after August 2018 — a dataset
boundary, not a business decline.

**Revenue by category.** `products → category_translation` is a LEFT JOIN,
not INNER, since 2 categories (13 products) have no English translation; an
INNER JOIN would silently drop that revenue from the ranking. Top 5 of 15
categories: `health_beauty` leads at R$1.23M (9.33%), followed by
`watches_gifts` (R$1.17M, 8.82%), `bed_bath_table` (R$1.02M, 7.74%),
`sports_leisure` (R$955K, 7.22%), `computers_accessories` (R$889K, 6.72%).
Revenue is fairly distributed across categories — no single category
dominates.

**Revenue by state + AOV.** São Paulo (SP) dominates volume — 40,501 orders,
R$5.07M revenue, more than 3x the next state (RJ, R$1.76M) — but SP has the
lowest AOV of any state (R$125.12), while small remote states have the
highest: PB (R$217.77), AP (R$199.62), AC (R$199.14). This is consistent with
freight costs scaling with distance from the São Paulo logistics hub
inflating order value in remote states, though this query alone doesn't
prove that causally (see `docs/root_cause_analysis.md` for the follow-up).

**On-time vs. late delivery rate.** Filtered to `order_status = 'delivered'
AND order_delivered_customer_date IS NOT NULL`, excluding the 8 orders with a
status/date mismatch. **Result: 91.89% on-time, 8.11% late (7,826 of 96,470
delivered orders).** This is the headline logistics KPI (see
`docs/logistics_analysis.md` for where the late 8% concentrates).

**Order status breakdown.** A CASE expression buckets 8 raw statuses into
`completed` / `failed` / `in_progress`. 97.02% of orders complete
(`delivered`); a combined 1.24% "failed" (0.63% canceled + 0.61%
unavailable); 1.74% still `in_progress` in the dataset snapshot.

**Categories with meaningful volume and below-average reviews.** Uses HAVING
(not WHERE) because the filter depends on the GROUP BY aggregation itself,
with a volume floor (`orders_with_review >= 50`) so a category with 2 orders
and one bad review doesn't rank as "worst." Reviews are pre-averaged to one
score per order in a CTE before joining to category, to avoid the 547
multi-reviewed orders counting twice. Worst 5: `office_furniture` (3.62 avg,
n=1,244), `fashion_male_clothing` (3.77, n=105), `audio` (3.84, n=345),
`home_confort` (3.88, n=390), `bed_bath_table` (3.94, n=9,177) — recomputed
on the 99,224-row reviews file.
`office_furniture` recurs throughout this project as a flagged category — see
`docs/root_cause_analysis.md` and `docs/scenario_analysis.md`.

**Repeat purchase behavior.** Grouped by `customer_unique_id`, not
`customer_id` (which is 1:1 with orders by construction — grouping by it
would make every customer look like a one-time buyer). **Result: 3.00% of
customers are repeat buyers (2,801 of 93,358), 97% are one-time** — realistic
for a fragmented multi-seller marketplace where the customer's relationship
is often with Olist-the-platform rather than any specific seller (see
`docs/customer_analysis.md`).

## Advanced queries

**Month-over-month revenue growth (LAG).** A CTE stages the monthly revenue
calculation once; `LAG(revenue) OVER (ORDER BY month)` pulls the previous
row's value for a % change calculation. December 2016 shows only R$10.90 in
revenue (effectively one stray order), which makes January 2017's growth
figure read as **+1,025,573%** — mathematically correct, practically
meaningless, an artifact of a near-zero denominator. **MoM growth % should be
suppressed or footnoted for any month below a materiality threshold**,
otherwise a reader could reasonably (and wrongly) conclude revenue increased
10,000x in a month. `NULLIF(..., 0)` in the denominator avoids a
division-by-zero error for any month with literal zero prior revenue.

**Running cumulative revenue.** `SUM(revenue) OVER (ORDER BY month)`, an
unbounded-preceding running total. Reaches R$13,221,498.11 by August 2018,
matching the simple aggregate exactly — a useful reconciliation check.

**3-month rolling average revenue.** `ROWS BETWEEN 2 PRECEDING AND CURRENT
ROW` smooths single-month noise (the Dec-2016 trough, the Nov-2017 spike),
climbing from ~R$20K (Oct 2016) to a plateau around R$850K–970K by mid-2018 —
the cleaner series for a trend line.

**Top 10 sellers by revenue (RANK vs. DENSE_RANK).** Top seller (SP-based)
generated R$226,987.93 across 1,124 orders. 9 of the top 10 sellers are based
in SP — one exception from BA ranked #2. In this specific top-10 there are no
exact revenue ties, so `RANK()` and `DENSE_RANK()` happen to produce
identical output — the distinction matters in principle but doesn't change
this particular list.

**Top 3 categories per state (ROW_NUMBER, PARTITION BY).** `bed_bath_table`,
`health_beauty`, and `watches_gifts` dominate in all three of SP, RJ, and MG —
just in different orders. The category mix is fairly stable across Olist's
biggest states, which suggests regional strategy is more likely a
logistics/fulfillment story than a "sell different things in different
states" story.

**Average delivery delay by state.** Every state's average delay is
negative — Olist delivers earlier than its own estimate almost everywhere on
average, most likely because `order_estimated_delivery_date` bakes in a
deliberate buffer rather than because logistics is uniformly excellent.
Alagoas (AL) shows about −8 days average delay but **23.93% late** — the
highest late rate in the list. (*Audit note (2026-10): this query previously
computed late % as `delay_days > 0` on a day count truncated by
`EXTRACT(DAY ...)`, which gave 21.41% and disagreed with the KPI dictionary's
timestamp rule; it now uses the same rule as every other late-rate figure.*) Average delay and late-rate can disagree, because a
state can have a few very-early deliveries pulling its average down while
still having the highest proportion of individually late orders — which is
why late-rate, not average delay, is used as the primary logistics KPI (see
`docs/logistics_analysis.md`). A volume floor (`HAVING COUNT(*) >= 30`)
excludes tiny states from the ranking.

**Sellers with above-average delivery delay.** `AVG(avg_seller_delay) OVER
()` computes the platform benchmark (the average of per-seller averages,
about −11.4 days on the current data) on the same row set as the per-seller
figure. The single worst-performing seller with meaningful volume
(≥20 orders) averages +1.4 days late — a genuinely different sign from the
platform's norm of roughly −11 days. A volume floor
(`HAVING COUNT(DISTINCT order_id) >= 20`) prevents a seller with one late
order from topping the list.
