# Customer Analysis

## Repeat purchase baseline

3.00% of customers are repeat buyers (2,801 of 93,358), computed correctly on
`customer_unique_id` rather than `customer_id` (see `docs/data_dictionary.md`
for why that distinction matters — `customer_id` is 1:1 with orders by
construction, so grouping by it would make every customer look like a
one-time buyer). 97% of customers have exactly one order. This is a low
repeat-purchase rate, stated plainly rather than dressed up — it's realistic
for a fragmented multi-seller marketplace where the customer's relationship
is often with Olist-the-platform rather than any specific seller.

## Why RFM-style segmentation was investigated and rejected on Frequency

The instinctive approach for customer segmentation is RFM (Recency /
Frequency / Monetary). It was investigated here and rejected specifically on
the Frequency dimension, with data to justify it:

- 90,557 of 93,358 delivered-order customers (97.0%) have exactly 1 order.
  Frequency has almost no variance to segment on — an RFM model's Frequency
  axis would put 97% of the customer base in the same bucket, making it
  nearly useless as a segmentation dimension here.
- Repeat-purchase rate was also checked for geographic variation (which would
  suggest a usable frequency signal by region instead): it doesn't vary
  meaningfully. Every major state sits in a narrow 2.9%–3.4% band. No state
  stands out as a meaningfully more "loyal" market.

## Monetary-value segmentation (the axis that does have variance)

| Segment | Customers | % of customers | Segment revenue | % of revenue | Repeat rate within segment |
|---|---:|---:|---:|---:|---:|
| High-value (top 5%, ≥R$420 total spend) | 4,637 | 5.0% | R$3,838,375 | 29.0% | 8.52% |
| Mid-value (R$90–420) | 40,304 | 43.2% | R$7,020,573 | 53.1% | 4.80% |
| Low-value (<R$90) | 48,417 | 51.9% | R$2,362,550 | 17.9% | 0.97% |

**The genuinely useful finding this segmentation produces:** repeat-purchase
rate rises sharply with spend tier — high-value customers repeat at 8.52%,
nearly 9x the low-value segment's 0.97%, and meaningfully above the mid-value
tier too. The overall platform repeat rate (3.0%) is a blended average that
hides this real gradient. High spend and repeat behavior are correlated in a
way that geography is not, which makes customer value, not customer
location, the more promising axis for a loyalty or retention program.

Source: `analytics.v_customer_spend_tier` (`sql/08_business_findings.sql`).
All figures in the table above reproduce exactly on the supplied data.

## Audit caveat (2026-10): the spend gradient is largely mechanical

The tiers are built on **lifetime** spend (the sum over all of a customer's
delivered orders). A customer with two or more orders accumulates spend
across them, so repeat customers drift into the top tier by construction:
311 of the 395 repeat customers in the top tier have an *average* order
value below the R$420 threshold — they are there because they bought more
than once.

Re-cutting the same 93,358 customers by the value of their **first** order
(`analytics.v_repeat_by_first_order_tier`) removes that circularity:

| First-order value | Customers | Repeat rate |
|---|---:|---:|
| ≥ R$420 | 4,337 | 2.19% |
| R$90–420 | 39,496 | 2.85% |
| < R$90 | 49,525 | 3.19% |

By first-order value, high spenders repeat slightly **less** often, not more.

**What this means:** the 8.52% vs 3.00% comparison is arithmetically correct
and a fair *description* of the platform's most valuable customers (they are
disproportionately repeat buyers, and the tier holds 29% of revenue). It is
**not** evidence that spending more makes customers more loyal, or that
high-value customers are a group "already primed to repeat".

**What this suggests:** the top lifetime-spend tier is worth protecting
because of its revenue share, but any loyalty programme for it should be
tested against a held-out comparison group before scaling (see
`docs/recommendations.md`, Recommendation 4).

**What this segmentation does NOT claim:** it does not identify *why*
high-value customers repeat more. That could be the value tier itself
driving loyalty, or a third factor (e.g., these customers buy from the
best-performing sellers/categories) driving both higher spend and higher
satisfaction/repeat behavior simultaneously. That distinction would need a
dedicated causal analysis this project doesn't attempt.
