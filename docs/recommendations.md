# Recommendations

## Results summary

| Area | Finding | Evidence |
|---|---|---|
| Revenue | R$13,221,498.11 in item revenue across 96,478 delivered orders; AOV R$137.04; steady growth from late 2016 through mid-2018 | `docs/sql_analysis.md`, `docs/kpi_dictionary.md` |
| Logistics | 91.89% on-time overall; Nordeste runs 14.33% late (1.77x the platform rate), with its worst states at 2-3x (AL 23.93%, MA 19.67%), concentrated regionally rather than by seller or category | `docs/logistics_analysis.md`, `docs/root_cause_analysis.md` |
| Sellers | The high-revenue/low-performance quadrant is the platform's single largest revenue block: 207 of 804 qualifying sellers, R$5.40M (KPI-consistent definition, current data). Originally reported as 212 sellers / R$5.37M — see `docs/seller_and_category_analysis.md` for the reconciliation | `docs/seller_and_category_analysis.md` |
| Categories | `office_furniture` is simultaneously the worst-reviewed category with meaningful volume (3.62 avg) and has the highest late rate (9.17%) of the seven top categories examined — though its 95% CI (7.7–10.9%) includes the 8.11% platform rate, so the late-rate difference is not statistically clear | `docs/seller_and_category_analysis.md` |
| Customers | Only 3.00% of customers repeat; 8.52% in the top 5% lifetime-spend tier. Caveat: much of that gradient is mechanical (repeat buyers accumulate spend) — by first-order value, high spenders repeat at 2.19% vs 3.19% for the lowest tier | `docs/customer_analysis.md` |

## Recommendation 1: seller-success program for the high-revenue/low-performance quadrant

**What:** targeted account management and fulfillment coaching for the
~207 sellers (212 in the original analysis) identified in `docs/seller_and_category_analysis.md`, starting with
the highest-revenue accounts in that quadrant (including the single largest
seller on the platform).

**Why:** this quadrant represents ~R$5.4M in revenue — more than the
high-revenue/high-performance quadrant (R$4.13M) — at a meaningfully lower average
on-time rate (89.1% vs. 95.5%) and review score (3.96 vs. 4.34). Improving
this group's performance protects revenue that's already at risk of churn or
reputational damage, rather than requiring new customer acquisition.

**Why not removal:** cutting off underperforming sellers would forfeit
~R$5.4M in revenue to solve a performance gap that (per Scenario 2 in
`docs/scenario_analysis.md`) is plausibly closeable through coaching at a
much lower cost than the revenue at stake.

## Recommendation 2: investigate Nordeste last-mile logistics specifically

**What:** a focused operational review of carrier performance and
fulfillment options for Nordeste-region deliveries, rather than a
platform-wide logistics initiative.

**Why:** `docs/root_cause_analysis.md` shows the late-delivery pattern in
this region holds across every seller-origin state examined — ruling out a
single bad seller as the explanation and pointing toward a
regional/logistics-infrastructure constraint. A platform-wide fix would
spend effort on states that aren't the problem; a regional fix targets where
the evidence actually points.

**Suggested next step:** pilot a regional carrier renegotiation or cross-dock
arrangement, informed by the conservative gap-closure estimate in
`docs/scenario_analysis.md`, before committing to a platform-wide logistics
overhaul.

## Recommendation 3: operational review of the `office_furniture` category

**What:** a category-specific review of `office_furniture` sellers'
fulfillment process and product-listing accuracy (e.g., damage in transit,
size/weight mismatches with buyer expectations, which can independently
depress both review scores and effective delivery reliability).

**Why:** this category has the lowest customer satisfaction of any category
with meaningful volume (3.62 avg review) and the heaviest freight burden
(25.0% of item revenue). Its late rate (9.17%) is the highest of the top
categories examined, but its 95% confidence interval (7.7–10.9%, n≈1,250)
includes the 8.11% platform rate, so lateness alone does not single it out —
the clearer signal is satisfaction (audit note, 2026-10). This
recommendation is intentionally scoped to investigation, not a specific fix,
since this project's data doesn't diagnose *why* the category underperforms
on both dimensions simultaneously.

## Recommendation 4: test retention outreach on high-value customers before scaling it

**What:** a *controlled pilot* of retention outreach for the top 5%
lifetime-spend tier (4,637 customers, 29.0% of revenue), with a held-out
comparison group — not a full loyalty program on the strength of the
observed gradient alone.

**Why (revised in the 2026-10 audit):** `docs/customer_analysis.md` shows
repeat rate is 8.52% in the top tier vs. 0.97% in the bottom tier, but the
tiers are built on *lifetime* spend, which repeat customers accumulate by
definition. Re-cut by **first-order** value, high spenders repeat *less*
(2.19%) than low spenders (3.19%). So the data does not show that high-value
customers are more loyal; it shows that the platform's most valuable
customers are disproportionately its repeat customers. That still makes
this group worth protecting (29% of revenue), but whether outreach changes
their behaviour has to be tested, not assumed. Geography remains the weaker
axis (a narrow 2.9%-3.4% band across states).

## What these recommendations deliberately don't claim

None of the four recommendations above come with a projected revenue lift,
cost estimate, or ROI figure, because this dataset doesn't support one —
there's no cost data for a seller-success program, no carrier-contract
pricing, and no controlled test of a retention campaign's actual conversion
rate. Where a rough scale-of-impact estimate is defensible, it's presented as
an explicit, conservative scenario in `docs/scenario_analysis.md` — clearly
separated from the observed findings above — rather than folded into these
recommendations as if it were already measured.
