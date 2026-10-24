# Scenario Analysis

This section is explicitly a **what-if simulation**, not an observed
historical outcome. Every number here is a projection built on stated
assumptions, layered on top of the observed data in
`docs/logistics_analysis.md` and `docs/root_cause_analysis.md` — it should
never be read or quoted as something that already happened.

## Scenario 1: closing part of the Nordeste late-delivery gap

**Baseline (observed):** the Nordeste region runs at 14.33% late, 1.77x the
platform's 8.11% rate; its worst states run 2-3x (AL 23.93%, MA 19.67%).

**Assumption:** a regional logistics intervention (carrier renegotiation or a
Nordeste cross-dock hub, per `docs/root_cause_analysis.md`) closes half the
gap between Nordeste's late rate and the platform average, rather than
eliminating it entirely — a deliberately conservative assumption, since a
full elimination isn't a reasonable planning assumption for a real
operational change.

**Affected population:** Nordeste-destined delivered orders in the dataset
window.

**Simulated result:** Nordeste has 1,296 late orders out of 9,044 delivered;
at the platform rate it would have ~733, so the gap is ~563 orders over the
dataset window. Halving that gap would move roughly 280 orders from "late" to "on-time" in the Nordeste region
specifically. Given the observed review-score gap between on-time and late
deliveries (4.29 vs. 2.57, `docs/logistics_analysis.md`), this would be
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

**Baseline (observed):** 207 sellers sit in the high-revenue/low-performance
quadrant (KPI-consistent definition, current data), generating R$5,403,117 in
revenue at an average 89.1% on-time rate and 3.96 review score
(`docs/seller_and_category_analysis.md`; originally reported as 212 sellers /
R$5,366,989 — reconciliation in that document).

**Assumption:** a structured seller-success program (outreach, fulfillment
coaching, a review checkpoint) moves this quadrant's average performance
halfway toward the high-revenue/high-performance quadrant's benchmark
(95.5% on-time, 4.34 review) — again a partial, conservative assumption
rather than assuming full parity is achievable.

**Simulated result:** this would move the quadrant's revenue exposure
(~R$5.4M) toward materially better delivery and satisfaction
outcomes, without requiring the removal of any seller or the ~R$5.4M in
revenue they currently generate. The scenario is deliberately framed around
*retention with improvement*, not churn, because the quantified cost of
losing this revenue block outright is larger than the performance gap being
closed.

**What this scenario does NOT claim:** it does not assume the intervention
will work, does not estimate a program cost, and does not claim a specific
ROI figure — none of which this dataset can support. It quantifies *what's
at stake* (~R$5.4M in revenue tied to underperforming sellers) so that a
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
