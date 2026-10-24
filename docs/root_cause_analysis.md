# Root Cause Analysis

## Starting observation

The state-level breakdown in `docs/sql_analysis.md` and
`docs/logistics_analysis.md` shows late-delivery rates are not evenly spread
across Brazil. Nordeste states (Brazil's northeast region) recur at the top
of the late-rate ranking: AL (23.93%), MA (19.67%), PI (15.97%), CE (15.32%),
SE (15.22%) and BA (14.04%) sit well above the 8.11% platform average, while
South/Southeast states cluster close to or below it. All 9 Nordeste states
are above the platform rate (lowest: RN 10.76%). Source:
`analytics.v_state_late_rate` / `analytics.v_region_late_rate`
(`sql/08_business_findings.sql`).

This section investigates why, using AL as the primary drill-down example and
checking whether the same mechanism generalizes across the wider Nordeste
region rather than stopping at one state.

## Candidate explanations considered

1. **A specific bad seller ships disproportionately to these states.**
2. **Distance from the São Paulo logistics hub** (most sellers are
   concentrated in SP/PR/MG/RJ) drives longer, less reliable transit.
3. **A product-category mix effect** — if Nordeste states happen to buy more
   of an already-problematic category (e.g. `office_furniture`), that could
   explain part of the gap independent of geography.

## Finding 1: not a single-seller problem

Breaking down AL's late deliveries by seller-origin state shows lateness
elevated across every seller state that ships there — SP sellers (256
orders, the largest share) run 25.27% late to AL; PR sellers run 46.51% late;
MG and RJ sellers are also elevated. If one bad seller explained the pattern,
the data would show one high-late-rate seller state and several
low-late-rate ones. Instead every seller-origin state underperforms when
shipping to AL specifically, which points to something about the
destination, not a specific origin seller.

## Finding 2: the pattern holds across the Nordeste region, not just AL

Extending the same seller-origin breakdown to all Nordeste states (not just
AL) shows the same structure repeating: regardless of which state a seller
ships from, orders to Nordeste destinations run late meaningfully more often
than orders to São Paulo/South/Southeast destinations from the same sellers.
This is the strongest evidence in this analysis for a **regional last-mile
logistics constraint** rather than a seller-quality or single-state anomaly —
the same sellers perform differently depending only on where the package is
going.

## Finding 3: category mix is not the primary driver

Checking whether Nordeste states simply buy more of the worst-reviewed
category (`office_furniture`) as an alternative explanation: `office_furniture`
does not show meaningfully higher order share in Nordeste states compared to
the national mix. The regional lateness pattern persists across the general
category mix, not concentrated in one problem category — ruling out "it's
really a category effect wearing a geography disguise" as the primary
explanation.

## What this analysis supports, and what it doesn't

| Level | Statement |
|---|---|
| **Observed pattern** | The Nordeste region as a whole runs at 14.33% late — **1.77x** the 8.11% platform rate (1.92x the rest of Brazil). The worst Nordeste states reach **2-3x** the platform rate (AL 2.95x, MA 2.42x); the other seven run 1.3x-2.0x. Elevated lateness is consistent across multiple states and multiple seller-origin states. |
| **Possible explanation** | A distance/logistics-infrastructure constraint in reaching Nordeste destinations, consistent with every seller-origin state showing the same directional effect. |
| **Supported conclusion** | The problem is destination-driven, not attributable to a specific bad seller or to a specific product category's regional popularity. |
| **NOT supported** | A formal causal claim (e.g., "distance from SP causes X extra days of delay per 1,000km") — this analysis doesn't control for carrier assignment, package weight/size, or fulfillment-center location, any of which could also correlate with destination region. |

## Why this matters operationally

If the root cause were a specific bad seller, the fix would be
seller-specific coaching or removal. If it's regional logistics
infrastructure — which the seller-origin breakdown supports more strongly —
the fix looks different: a regional carrier renegotiation, a
Nordeste-specific fulfillment/cross-dock hub, or adjusted delivery-estimate
buffers specifically for that region so customer expectations match the
reality of reaching it. See `docs/recommendations.md` for how this is framed
as an action, and `docs/scenario_analysis.md` for a quantified estimate of
what closing part of this gap could be worth.
