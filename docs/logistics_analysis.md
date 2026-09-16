# Logistics Analysis

## Headline metrics

| Metric | Value |
|---|---:|
| On-Time Delivery % | 91.89% |
| Late Delivery % | 8.11% (7,826 orders) |
| Avg Delay vs. Estimate | -9.3 days (negative = early on average) |
| Order Failure Rate | 1.24% (canceled + unavailable) |

## Why late % leads over average delay

Average delay and late-rate can disagree. Alagoas (AL) has one of the least
negative average delays in the state ranking (looks close to "on time" on
average) but the highest late-order percentage of any state (23.93%). A
report that only showed average delay would make AL look mediocre-but-fine;
late rate makes the real problem visible immediately. Every state-level
breakdown here leads with late %, with average delay shown only as a
secondary figure.

## Root-cause drill-down: State → Seller Origin → Category → Review Score

Using AL (the worst late-rate state) as the concrete starting example:

**Question:** is AL's high late rate caused by a specific bad seller, or
something about reaching AL itself?

**Finding:** lateness is spread across every seller state that ships to AL —
SP sellers (the largest volume, 256 orders) run 25.27% late to AL; PR sellers
run even worse at 46.51% late; MG and RJ sellers also show meaningfully
elevated lateness. If one specific seller were the problem, the expected
pattern would be one bad actor and several clean ones. Instead the pattern
holds across different sellers from different states — pointing toward a
**last-mile logistics/carrier-network problem specific to reaching AL**, not a
seller-quality problem. This same distance-driven mechanism holds at the full
regional level; see `docs/root_cause_analysis.md` for the Nordeste-wide
version of this finding.

**What this does NOT prove:** it's an association pattern across seller
states with meaningful volume to AL, not a formal statistical test
controlling for package weight, distance, product category, or other
confounders. It's a strong lead for further investigation, not a settled
causal conclusion.

## Review score association (explicitly not causal)

| Delivery outcome | Avg review score | Orders |
|---|---:|---:|
| On-time | 4.28 | 88,644 |
| Late | 2.55 | 7,826 |

A 1.73-point gap on a 5-point scale, and the gap holds consistently across
every state examined (SP: 4.32 vs 2.89, RJ: 4.23 vs 2.12, MG: 4.27 vs 2.65,
and others) — not just in one region. This consistency makes the association
more credible as a real pattern, but it's stated as **"late deliveries are
associated with lower review scores," not "late delivery causes lower review
scores."** A late order might also be more likely to involve a damaged item,
a customer already unhappy about something else, or a product category prone
to both delay and dissatisfaction — confounders that this analysis doesn't
rule out.

## March 2018 on-time dip

The monthly on-time trend shows a sharp dip to 78.6% in March 2018 (vs. the
91.89% platform average). The states driving that dip hardest (MA 44.9%, CE
46.2%, PA 47.8%, ES 55.6%) are the same states already identified as
chronically underperforming in the overall late-rate ranking. This suggests
March 2018 was a particularly bad month for a persistent regional weak
point, not an isolated national event — a more defensible read than
speculating about a specific one-off cause without evidence for it.
