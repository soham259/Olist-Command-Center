# Assumptions and Limitations

## Key methodological assumptions

| Assumption | Where it's used | Why |
|---|---|---|
| Revenue = item price only, excluding freight and excluding `payment_value` | All revenue KPIs | Attributable at item grain, no fan-out risk; documented gap vs. payment_value is 0.018% (`docs/kpi_dictionary.md`) |
| Only `delivered` orders count toward revenue and delivery KPIs | Revenue, AOV, on-time rate, delay | An order still in transit or canceled has no realized outcome to measure yet |
| `customer_unique_id`, not `customer_id`, defines "a customer" | Repeat-purchase rate, customer segmentation | `customer_id` is 1:1 with orders by construction (`docs/data_dictionary.md`) |
| A seller needs ≥20 orders to be included in performance segmentation | Seller quadrant analysis | Prevents a seller with 1-2 orders and one bad review from distorting a ranking meant to reflect sustained performance |
| A state needs ≥30 delivered orders to appear in state-level late-rate rankings | Logistics state comparisons | Same rationale — small-sample states would otherwise produce noisy, unstable rankings |
| Order-level review score = average of all reviews tied to that order | Review score KPI, category/seller review averages | Handles the 547 orders with 2-3 review rows without double-counting them |
| Median revenue × median performance score defines the seller quadrant split | Seller segmentation | Relative to this platform's actual seller base, not an arbitrary fixed threshold |
| Scenario analysis assumes *partial* (not full) improvement toward a benchmark | Both scenarios in `docs/scenario_analysis.md` | A conservative planning assumption — full parity with a benchmark segment isn't a realistic default to assume |

## Limitations

- **No cost or financial-impact data.** The dataset has no seller cost
  structure, no logistics contract pricing, and no marketing/program cost
  data. Recommendations describe *where* revenue and risk are concentrated,
  not a projected ROI — because this dataset cannot support a defensible ROI
  number.
- **Correlational, not causal, findings throughout.** The late-delivery →
  low-review-score relationship, the regional logistics pattern, and the
  value-tier → repeat-purchase relationship are all associations observed in
  historical data. None of them are established as causal — each caveat is
  repeated in its own analysis document rather than assumed away.
- **No dashboard or BI tool is included in this repository.** The analytics
  star schema and the CSV export step in `scripts/run_pipeline.py` are built
  to support one, but building a dashboard was out of scope for this project.
- **Geolocation is approximate.** `dim_geography` is deduplicated to one
  row per zip-code prefix (most-frequent city/state, averaged lat/lng) — see
  `docs/data_model.md`. It supports state/region-level analysis, not precise
  individual-address mapping.
- **A small number of orders (≈31, ~0.03%) are excluded from delivery-timing
  metrics** due to internally inconsistent dates (`docs/data_quality.md`).
  Immaterial to headline figures, but not zero.
- **`order_approved_at` is not a reliable sequencing anchor after April
  2018** — 1,359 orders show carrier handoff before formal approval,
  concentrated from that point onward, consistent with a legitimate
  process/systems change rather than data corruption, but it means this
  field shouldn't be used for leg-level timing analysis in that period.
- **The dataset window is roughly September 2016 to October 2018.** Data
  density drops sharply after August 2018 — this is a dataset boundary, not
  a business decline, and any trend analysis near the end of the window
  should account for that.
- **Multi-seller orders (1.3% of orders with items) introduce minor noise
  into per-seller order-status attribution** in the seller scorecard — an
  order involving 2+ sellers has its single `order_status` attributed to all
  of them, which is a simplification stated explicitly in
  `docs/seller_and_category_analysis.md` rather than glossed over.
- **Dataset revision.** The reviews file has been published in two
  revisions (100,000 and 99,224 rows). This project is validated against the
  99,224-row file; figures that depend on review scores (seller performance
  scores, category review averages) differ slightly from the original
  analysis, which used the 100,000-row revision. See `docs/audit_report.md`.
- **Strict on-time rule.** Deliveries during the estimated day count as late
  (the estimate is stored at midnight) — see `docs/kpi_dictionary.md`.
- **Lifetime-spend tiers are partly circular for repeat-rate analysis.**
  Repeat customers accumulate higher lifetime spend by definition; see the
  first-order-value check in `docs/customer_analysis.md`.
- **Execution status.** The pipeline and all three test files were executed
  end-to-end on PostgreSQL 16 during the 2026-10 audit (81 of 81 tests
  passed; see `docs/testing.md`). They have not yet been run on Windows.
