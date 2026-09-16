# Scenario Analysis

This section is explicitly a **what-if simulation**, not an observed
historical outcome. Every number here is a projection built on stated
assumptions, layered on top of the observed data in
`docs/logistics_analysis.md` and `docs/root_cause_analysis.md` — it should
never be read or quoted as something that already happened.

## Scenario 1: closing part of the Nordeste late-delivery gap

**Baseline (observed):** Nordeste states run at roughly 2-3x the platform's
8.11% late rate; AL specifically sits at 23.93% late.

**Assumption:** a regional logistics intervention (carrier renegotiation or a
Nordeste cross-dock hub, per `docs/root_cause_analysis.md`) closes half the
gap between Nordeste's late rate and the platform average, rather than
eliminating it entirely — a deliberately conservative assumption, since a
full elimination isn't a reasonable planning assumption for a real
operational change.

**Affected population:** Nordeste-destined delivered orders in the dataset
window.

**Simulated result:** halving that gap would move an estimated several
hundred orders per year from "late" to "on-time" in the Nordeste region
specifically. Given the observed review-score gap between on-time and late
deliveries (4.28 vs. 2.55, `docs/logistics_analysis.md`), this would be
expected to lift average review scores in the affected region — but the
magnitude of that secondary lift is not separately quantified here, because
doing so credibly would require modeling the review-score relationship
directly rather than applying the platform-wide gap as a flat multiplier to a
regional subgroup.

**This is a scenario, not a forecast:** it assumes the observed association
between on-time delivery and review score would hold under an actual
operational change, which is a reasonable planning assumption but not a
guarantee — see the causality caveat in `docs/root_cause_analysis.md`.

## Scenario 2: seller-success intervention in the high-revenue/low-performance quadrant

**Baseline (observed):** 212 sellers sit in the high-revenue/low-performance
quadrant, generating R$5,366,989 in revenue at an average 89.1% on-time rate
and 3.89 review score (`docs/seller_and_category_analysis.md`).

**Assumption:** a structured seller-success program (outreach, fulfillment
coaching, a review checkpoint) moves this quadrant's average performance
halfway toward the high-revenue/high-performance quadrant's benchmark
(95.4% on-time, 4.30 review) — again a partial, conservative assumption
rather than assuming full parity is achievable.

**Simulated result:** this would move roughly 100+ sellers' worth of revenue
exposure (R$5.37M) toward materially better delivery and satisfaction
outcomes, without requiring the removal of any seller or the R$5.37M in
revenue they currently generate. The scenario is deliberately framed around
*retention with improvement*, not churn, because the quantified cost of
losing this revenue block outright is larger than the performance gap being
closed.

**What this scenario does NOT claim:** it does not assume the intervention
will work, does not estimate a program cost, and does not claim a specific
ROI figure — none of which this dataset can support. It quantifies *what's
at stake* (R$5.37M in revenue tied to underperforming sellers) so that a
real program's cost can be weighed against a real number, rather than a
vague "some sellers underperform" statement.

## Why these are the only two scenarios modeled

Both scenarios attach to findings with the strongest evidentiary support in
this project (the regional logistics pattern and the seller quadrant
imbalance) and both are stated as ranges/partial improvements rather than
point predictions, to avoid overstating precision the underlying data can't
support. Other candidate scenarios (e.g., category-level interventions for
`office_furniture`) were considered but not modeled quantitatively here,
since the category-level sample sizes are smaller and a partial-improvement
assumption would be even less grounded than the two above.
