# Recommendations

## Results summary

| Area | Finding | Evidence |
|---|---|---|
| Revenue | R$13,221,498.11 in item revenue across 96,478 delivered orders; AOV R$137.04; steady growth from late 2016 through mid-2018 | `docs/sql_analysis.md`, `docs/kpi_dictionary.md` |
| Logistics | 91.89% on-time overall, but late rate is 2-3x higher in Nordeste states, concentrated regionally rather than by seller or category | `docs/logistics_analysis.md`, `docs/root_cause_analysis.md` |
| Sellers | 212 sellers (26% of the qualifying seller base) generate R$5.37M in revenue — the platform's single largest revenue block — while performing below the platform's median on both on-time delivery and review score | `docs/seller_and_category_analysis.md` |
| Categories | `office_furniture` is simultaneously the worst-reviewed category with meaningful volume (3.50 avg) and has the highest late rate (9.17%) of the categories examined | `docs/seller_and_category_analysis.md` |
| Customers | Only 3.00% of customers repeat, but repeat rate rises to 8.52% in the top 5% spend tier — a real, usable segmentation axis, unlike frequency or geography | `docs/customer_analysis.md` |

## Recommendation 1: seller-success program for the high-revenue/low-performance quadrant

**What:** targeted account management and fulfillment coaching for the 212
sellers identified in `docs/seller_and_category_analysis.md`, starting with
the highest-revenue accounts in that quadrant (including the single largest
seller on the platform).

**Why:** this quadrant represents R$5.37M in revenue — more than the
high-revenue/high-performance quadrant — at a meaningfully lower average
on-time rate (89.1% vs. 95.4%) and review score (3.89 vs. 4.30). Improving
this group's performance protects revenue that's already at risk of churn or
reputational damage, rather than requiring new customer acquisition.

**Why not removal:** cutting off underperforming sellers would forfeit
R$5.37M in revenue to solve a performance gap that (per Scenario 2 in
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

**Why:** this category is the worst performer on two independent measures —
customer satisfaction (3.50 avg review, lowest with meaningful volume) and
operational reliability (9.17% late rate, highest of the categories
examined) — which is a stronger signal than either metric alone. This
recommendation is intentionally scoped to investigation, not a specific fix,
since this project's data doesn't diagnose *why* the category underperforms
on both dimensions simultaneously.

## Recommendation 4: build retention outreach around customer value, not geography

**What:** a loyalty or retention program targeted at the top 5% spend tier
(4,637 customers, 29.0% of revenue), rather than a geography-based campaign.

**Why:** `docs/customer_analysis.md` shows repeat-purchase rate varies
sharply by spend tier (8.52% vs. 0.97% for high- vs. low-value customers) but
barely at all by state (a narrow 2.9%-3.4% band everywhere). Spending effort
on a geographic campaign would be optimizing an axis with almost no signal;
value-tier targeting works with a real, already-observed behavioral pattern.

## What these recommendations deliberately don't claim

None of the four recommendations above come with a projected revenue lift,
cost estimate, or ROI figure, because this dataset doesn't support one —
there's no cost data for a seller-success program, no carrier-contract
pricing, and no controlled test of a retention campaign's actual conversion
rate. Where a rough scale-of-impact estimate is defensible, it's presented as
an explicit, conservative scenario in `docs/scenario_analysis.md` — clearly
separated from the observed findings above — rather than folded into these
recommendations as if it were already measured.
