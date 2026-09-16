# Methodology

## Business problem

Olist is a Brazilian marketplace connecting third-party sellers to customers.
Marketplace operators face a recurring tension between revenue growth and
operational reliability: GMV can grow while delivery performance, seller
quality, and customer satisfaction quietly degrade underneath it.

**Problem statement:** Olist's leadership needs a unified view of revenue
performance and logistics reliability across sellers, categories, and states —
to identify where growth is healthy, where operational risk is concentrated,
and what interventions would improve outcomes. That's why this project pairs
commercial performance analysis with operational-risk analysis, rather than
treating them separately.

## Target users

| Persona | Role | What they need |
|---|---|---|
| COO / Ops Director | Owns delivery performance, carrier/seller relationships | Where logistics is failing and what's at stake |
| Head of Marketplace / Category Manager | Owns seller and category portfolio | Which sellers/categories are high-value vs. underperforming |
| Commercial/Finance Analyst | Owns revenue reporting | Revenue trends, AOV, growth, and where it's concentrated |

## Business questions

- **Revenue:** total revenue trend, month-over-month growth, revenue by
  category/state, AOV trend
- **Customers:** repeat purchase rate, order value distribution, geographic
  concentration
- **Logistics:** on-time delivery %, average delay, which states/sellers/
  categories drive late deliveries
- **Sellers:** revenue and fulfillment performance per seller, high-revenue/
  low-performance sellers specifically
- **Products/Categories:** revenue concentration, review scores, delivery
  problems by category
- **Cross-cutting:** is delivery delay associated with lower review scores
  (association, not causation, until investigated further)?

## Approach

```
Olist CSVs (raw_data/)
   -> Python ingestion, schema verification
PostgreSQL raw layer (raw.*)
   -> SQL data-quality audit, then FK constraints/indexes
PostgreSQL analytics/star-schema layer (fact_*, dim_*)
   -> SQL analysis: KPIs, segmentation, root-cause, scenario analysis
   -> Business recommendations, quantified where the data supports it
```

Every step was designed to be checked, not assumed: relationships were
verified with data before being enforced as foreign keys, KPI formulas were
validated against multiple independent computation paths before being
published, and every finding used in a recommendation was corroborated by
more than one query where possible (see `docs/data_quality.md`,
`docs/kpi_dictionary.md`, and `docs/testing.md`).

## A deliberate scope decision: no dbt, no BI tool

This project uses a single Python orchestrator (`scripts/run_pipeline.py`)
over plain SQL files instead of a tool like dbt, and delivers its findings as
markdown documentation, SQL, and a docx business case rather than a live BI
dashboard.

Both were deliberate calls, not gaps filled with something else:

- **dbt** earns its overhead — dependency-graph resolution, a documentation
  site, cross-model testing — once a project has many interdependent models
  or multiple contributors. This is a single, linear pipeline (9 source files
  → one raw schema → one analytics schema) maintained by one person. A plain
  Python script covering validation, logging, and idempotent re-runs achieves
  the same reproducibility goals here without the extra tooling surface.
- **A live BI dashboard tool** was scoped out of this
  project. The analytics star schema (`sql/06_star_schema.sql`) and the CSV
  export step in `scripts/run_pipeline.py` produce exactly the data such a
  tool would need, so building one on top of this project later is
  straightforward — but no dashboard file exists in this repository, and
  nothing here should be read as implying one does.
