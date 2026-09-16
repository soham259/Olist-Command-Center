# Seller and Category Analysis

## Methodology: seller scorecard and quadrant segmentation

**Population:** 818 of 3,095 sellers (26%) have ≥20 orders — the same volume
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

**Quadrant split:** median revenue (R$6,408) × median performance score,
among the 818 qualifying sellers — a median split rather than an arbitrary
fixed threshold, so "high" and "low" are relative to this platform's actual
seller base.

## The headline finding

| Quadrant | Sellers | Total revenue | Avg on-time | Avg review |
|---|---:|---:|---:|---:|
| High revenue, low performance | 212 | R$5,366,989 | 89.1% | 3.89 |
| High revenue, high performance | 197 | R$4,411,381 | 95.4% | 4.30 |
| Low revenue, low performance | 197 | R$697,396 | 87.8% | 3.85 |
| Low revenue, high performance | 212 | R$686,786 | 96.2% | 4.35 |

**The high-revenue/low-performance quadrant generates more total revenue than
the high-revenue/high-performance quadrant** (R$5.37M vs. R$4.41M) — meaning
the single largest concentration of platform revenue sits with sellers
performing below the platform median. This is the clearest, highest-leverage
finding in the seller/category analysis: it's not "some sellers are bad," it's
"the biggest revenue block on the platform is currently underperforming."

**What this suggests:** a retention/enablement problem, not a removal
problem. Losing R$5.37M in seller revenue by cutting off low-performers would
likely cost more than the performance gap itself (89.1% vs 95.4% on-time;
3.89 vs 4.30 review — meaningfully different, but not catastrophic). A
seller-success outreach program targeted at exactly these 212 sellers is a
defensible, quantified recommendation (see `docs/recommendations.md`).

## Priority sellers (named, not hypothetical)

| Seller | State | Revenue | On-time | Review |
|---|---|---:|---:|---:|
| 4869f7a5… | SP | R$229,473 | 88.4% | 4.12 |
| 4a3ca931… | SP | R$200,473 | 89.0% | 3.80 |
| fa1c13f2… | SP | R$194,042 | 89.8% | 4.33 |
| 7c67e144… | SP | R$187,924 | 89.9% | 3.48 |
| da8622b1… | SP | R$160,237 | 92.4% | 4.17 |

The single largest seller on the platform (R$229K revenue) is itself in the
high-revenue/low-performance quadrant — this isn't a small-account problem,
it includes the platform's biggest account.

## Category performance

| Category | Revenue | Review | Late % |
|---|---:|---:|---:|
| Health & beauty | R$1.23M | 4.18 | 8.96% |
| Watches & gifts | R$1.17M | 4.06 | 8.52% |
| Bed, bath & table | R$1.02M | 3.90 | 8.75% |
| Sports & leisure | R$955K | 4.15 | 7.76% |
| Computer accessories | R$889K | 3.98 | 7.70% |
| Furniture & decor | R$712K | 3.94 | 8.48% |
| **Office furniture** (flagged) | R$268K | **3.50** | **9.17%** |

`office_furniture` is the worst-reviewed category with meaningful volume, and
it also has the highest late rate of any category shown here. It's
simultaneously the worst on an independent satisfaction metric (reviews) and
an independent operational metric (late %), which makes it a stronger
candidate for a dedicated operational review than a category flagged on only
one dimension — see `docs/root_cause_analysis.md` and
`docs/scenario_analysis.md` for how this compounds further at the regional
and freight-cost level.

## Seller segments (who / why / what action)

**High Revenue, Low Performance (212 sellers, R$5.37M revenue — 33% of item
revenue).** Sellers above the platform median revenue but below median on the
blended performance score, including the single largest seller by revenue. A
modest performance gap here has outsized financial exposure — every
percentage point of on-time improvement in this segment moves more revenue
than the same improvement anywhere else. Action: seller-success outreach —
proactive account management, fulfillment coaching, a structured improvement
plan with a review checkpoint. Not removal — losing R$5.37M in revenue to
enforce a quality bar would very likely cost the business more than the
performance gap itself.

**High Revenue, High Performance (197 sellers, R$4.41M revenue).** The
platform's healthiest high-value segment — worth protecting and studying as a
benchmark. Action: retention-focused (preferential commission tiers,
marketing placement) rather than intervention-focused.

**Low Revenue, High Performance (212 sellers, R$687K revenue).** Small-volume
sellers who deliver reliably and get good reviews. Candidates for growth, not
fixing. Action: category/marketing support to help them scale order volume.

**Low Revenue, Low Performance (197 sellers, R$697K revenue).** Lowest
financial exposure of any quadrant. Action: lowest intervention priority — a
lightweight automated quality flag rather than active account management, since
the ROI on manual outreach here is weakest of the four segments.

## Why a blended score instead of two separate quadrant charts

A single performance axis (combining timing and satisfaction) keeps the
segmentation to one clean 2×2 that maps directly to a business action
(retain-and-improve vs. reward vs. investigate vs. monitor), rather than a
2×2×2 cube that would be harder to act on even if marginally more precise.
