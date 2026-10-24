# Seller and Category Analysis

## Methodology: seller scorecard and quadrant segmentation

**Population:** 804 of 3,095 sellers (26%) have ≥20 delivered orders (818
have ≥20 orders of any status — the population used in the original analysis) — the same volume
floor used throughout this project's SQL analysis, applied here so a seller
with 3 orders and one bad review isn't classified alongside a seller with
1,000+ orders. The other 74% of sellers are real but too low-volume for a
stable performance read; they remain visible in the raw data but are excluded
from the quadrant classification.

**A data-attribution issue investigated before trusting seller-level
order_status:** `order_status` lives at the order level, not the seller
level — but 98.7% of orders (97,388 of 98,666 orders-with-items) involve
exactly one seller, so attributing an order's status to "its" seller is clean
for the large majority. The remaining 1.3% (1,278 orders with 2+ sellers)
introduces minor noise into any single seller's failure-rate figure, which is
acknowledged explicitly rather than assumed away.

**Performance score:** `0.5 × (on_time_% / 100) + 0.5 × (avg_review_score /
5)` — equal weight between delivery timing and customer satisfaction.
Cancellation/unavailable rate was deliberately **not** folded into this
blended score — it's a rarer, more binary signal (most sellers have 0%) that
would get washed out by averaging into a continuous score, and it's shown
separately instead.

**Quadrant split:** median revenue (R$6,390; R$6,408 under the original
all-status basis) × median performance score, among the qualifying sellers — a median split rather than an arbitrary
fixed threshold, so "high" and "low" are relative to this platform's actual
seller base.

## The headline finding

Source: `analytics.v_seller_quadrant_summary` (`sql/08_business_findings.sql`,
added in the 2026-10 audit — the SQL behind this analysis was not previously
in the repository).

**Current, reproducible figures (KPI-consistent definition: ≥20 delivered
orders, revenue on delivered orders only, 99,224-row reviews file):**

| Quadrant | Sellers | Total revenue | Avg on-time | Avg review |
|---|---:|---:|---:|---:|
| High revenue, low performance | 207 | R$5,403,117 | 89.1% | 3.96 |
| High revenue, high performance | 195 | R$4,132,924 | 95.5% | 4.34 |
| Low revenue, low performance | 195 | R$691,948 | 87.9% | 3.97 |
| Low revenue, high performance | 207 | R$666,533 | 96.4% | 4.39 |

(804 qualifying sellers; median revenue R$6,390.)

**Originally reported figures (earlier analysis):** 212 sellers / R$5,366,989
in the high-revenue/low-performance quadrant, out of 818 qualifying sellers
with median revenue R$6,408.

**Reconciliation.** The 818 sellers and R$6,408 median reproduce *exactly*
only when the volume floor counts orders of any status and seller revenue
sums item prices across all statuses (the `as_originally_documented` basis in
the same view) — i.e. the original analysis did not apply the KPI
dictionary's delivered-only revenue filter here. On that basis the quadrant
contains 210 sellers / R$5,468,500 on the current data. The remaining gap to
212 comes from review scores: the original used the earlier 100,000-row
reviews file, which changes some sellers' performance score around the
median. Across every definition tested, the quadrant holds 206-213 sellers
and R$5.3M-R$5.5M, and it is the largest revenue quadrant in every variant —
the finding is robust; the exact headcount is definition-sensitive.

**The high-revenue/low-performance quadrant generates more total revenue than
the high-revenue/high-performance quadrant** (R$5.40M vs. R$4.13M) — meaning
the single largest concentration of platform revenue sits with sellers
performing below the platform median. This is the clearest, highest-leverage
finding in the seller/category analysis: it's not "some sellers are bad," it's
"the biggest revenue block on the platform is currently underperforming."

**What this suggests:** a retention/enablement problem, not a removal
problem. Losing ~R$5.4M in seller revenue by cutting off low-performers would
likely cost more than the performance gap itself (89.1% vs 95.5% on-time;
3.96 vs 4.34 review — meaningfully different, but not catastrophic). A
seller-success outreach program targeted at exactly these sellers is a
defensible, quantified recommendation (see `docs/recommendations.md`).

## Priority sellers (named, not hypothetical)

Revenue here is all-status item revenue (the original analysis's basis, which
reproduces these revenue figures exactly); review scores recomputed on the
99,224-row reviews file.

| Seller | State | Revenue | On-time | Review |
|---|---|---:|---:|---:|
| 4869f7a5… | SP | R$229,473 | 88.4% | 4.15 |
| 4a3ca931… | SP | R$200,473 | 89.0% | 3.85 |
| 7c67e144… | SP | R$187,924 | 89.9% | 3.50 |
| da8622b1… | SP | R$160,237 | 92.4% | 4.18 |
| 1025f0e2… | SP | R$138,969 | 89.9% | 4.01 |

(`fa1c13f2…`, R$194,042, was in this list originally; on the current reviews
file its performance score sits just above the median, so it moves to the
high-performance quadrant — an example of the definition sensitivity noted
above.)

The single largest seller on the platform (R$229K revenue) is itself in the
high-revenue/low-performance quadrant — this isn't a small-account problem,
it includes the platform's biggest account.

## Category performance

| Category | Revenue | Review | Late % |
|---|---:|---:|---:|
| Health & beauty | R$1.23M | 4.23 | 8.96% |
| Watches & gifts | R$1.17M | 4.12 | 8.52% |
| Bed, bath & table | R$1.02M | 4.00 | 8.75% |
| Sports & leisure | R$955K | 4.23 | 7.76% |
| Computer accessories | R$889K | 4.08 | 7.70% |
| Furniture & decor | R$712K | 4.06 | 8.48% |
| **Office furniture** (flagged) | R$268K | **3.64** | **9.17%** |

Revenue and late % reproduce the original figures exactly; review averages
are recomputed on the 99,224-row reviews file (order-level average per
category; the slightly different 3.62 for office furniture in
`docs/sql_analysis.md` comes from `sql/04` Q7's order×product grain).

`office_furniture` is the worst-reviewed category with meaningful volume, and
it also has the highest late rate of any category shown here — but that late
rate (9.17%) has a 95% confidence interval of 7.7–10.9%, which includes the
8.11% platform rate, so the lateness difference is not statistically clear
(audit note, 2026-10). The robust signals are its review score and its freight
burden (25.0% of item revenue, the highest of the top-20 categories), which
still make it a candidate for a dedicated operational review — see `docs/root_cause_analysis.md` and
`docs/scenario_analysis.md` for how this compounds further at the regional
and freight-cost level.

## Seller segments (who / why / what action)

**High Revenue, Low Performance (207 sellers, R$5.40M revenue — about 50% of
the qualifying sellers' revenue and 41% of all delivered item revenue; originally reported
as 212 sellers / R$5.37M).** Sellers above the platform median revenue but below median on the
blended performance score, including the single largest seller by revenue. A
modest performance gap here has outsized financial exposure — every
percentage point of on-time improvement in this segment moves more revenue
than the same improvement anywhere else. Action: seller-success outreach —
proactive account management, fulfillment coaching, a structured improvement
plan with a review checkpoint. Not removal — losing ~R$5.4M in revenue to
enforce a quality bar would very likely cost the business more than the
performance gap itself.

**High Revenue, High Performance (195 sellers, R$4.13M revenue).** The
platform's healthiest high-value segment — worth protecting and studying as a
benchmark. Action: retention-focused (preferential commission tiers,
marketing placement) rather than intervention-focused.

**Low Revenue, High Performance (207 sellers, R$667K revenue).** Small-volume
sellers who deliver reliably and get good reviews. Candidates for growth, not
fixing. Action: category/marketing support to help them scale order volume.

**Low Revenue, Low Performance (195 sellers, R$692K revenue).** Lowest
financial exposure of any quadrant. Action: lowest intervention priority — a
lightweight automated quality flag rather than active account management, since
the ROI on manual outreach here is weakest of the four segments.

## Why a blended score instead of two separate quadrant charts

A single performance axis (combining timing and satisfaction) keeps the
segmentation to one clean 2×2 that maps directly to a business action
(retain-and-improve vs. reward vs. investigate vs. monitor), rather than a
2×2×2 cube that would be harder to act on even if marginally more precise.
