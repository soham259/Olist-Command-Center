# Olist Command Center

An end-to-end SQL/Python analytics project on the Olist Brazilian e-commerce
dataset: order, seller, customer, product, payment, review, and logistics
data for a multi-seller marketplace, taken from raw CSVs through a
reproducible ETL pipeline into a dimensional star schema, then analyzed for
revenue performance, delivery reliability, seller/category performance,
customer behavior, and regional logistics root causes.

## What this project does

- Loads and validates 9 raw Olist CSVs (~1.45M rows combined) into PostgreSQL
- Audits data quality across referential integrity, date sequencing, payment
  reconciliation, and duplicate keys — 14 distinct issues found, each
  classified and given an explicit handling decision
- Builds a dimensional star schema (3 fact tables, 5 dimensions) with
  validated grain and reconciled measures
- Answers a defined set of business questions in SQL (foundational + window
  functions), with every KPI formally defined once and used consistently
  everywhere
- Segments sellers into a revenue × performance quadrant, and customers by
  spend tier
- Investigates a regional logistics pattern down to a supported conclusion
  (not just an observation)
- Runs two explicit, clearly-labeled what-if scenarios
- Ships 37 automated regression tests pinning every published figure

## Key findings

- **R$13.2M in revenue** across 96,478 delivered orders, AOV R$137.04, steady
  growth from late 2016 through mid-2018 (dataset ends October 2018)
- **91.89% on-time delivery** platform-wide, but Nordeste-region states run
  2-3x the platform's late rate — traced to a regional logistics pattern that
  holds across every seller-origin state examined, not one bad seller or
  category (`docs/root_cause_analysis.md`)
- **212 sellers generate R$5.37M in revenue while performing below the
  platform median** on both on-time delivery and review score — the single
  largest revenue block on the platform, and a retention/coaching
  opportunity rather than a removal case (`docs/seller_and_category_analysis.md`)
- **Repeat-purchase rate is 3.00% platform-wide but 8.52% in the top 5% spend
  tier** — a real segmentation signal, unlike geography, which barely varies
  (`docs/customer_analysis.md`)

Full findings, formulas, and evidence: see `docs/`.

## Data

Source: Olist Brazilian E-Commerce Public Dataset (originally published on
Kaggle by Olist). Raw CSVs are **not committed to this repository** —
redistribution rights aren't clearly established, so `raw_data/*.csv` is
gitignored. See `data/README.md` for exact filenames, expected row counts,
and how to obtain the dataset yourself.

## Data grain

- One row per order item (`fact_order_items`) — the finest usable grain for
  revenue, since orders can have multiple items
- One row per order (`fact_orders`) — carries pre-aggregated measures
  (revenue, freight, payment total, review score, on-time flag) so
  downstream reporting doesn't have to re-derive them via risky joins
- One row per payment record (`fact_payments`) — separate from `fact_orders`
  because ~3% of orders have multiple payment rows (installment splits),
  which would silently inflate revenue if joined to items directly

Full relational and dimensional model, with the fan-out risk demonstrated
concretely: `docs/data_model.md`.

## Technical stack

- **PostgreSQL** — raw and analytics (star schema) layers
- **Python** (pandas, SQLAlchemy, psycopg2) — ingestion and pipeline
  orchestration
- **SQL** — all analysis, from foundational joins/aggregates through window
  functions
- **pytest** — 37 automated regression tests against the live database
- **Node.js** (`docx` package) — generates the business-case Word document
  from `business_case/build_business_case.js`

No dbt, no BI dashboard tool. Both were deliberate scope decisions, not
gaps — see `docs/methodology.md`.

## Repository structure

```
olist-command-center/
├── README.md
├── requirements.txt          # pandas, sqlalchemy, psycopg2-binary
├── requirements-dev.txt      # + pytest
├── .env.example               # OLIST_DB_URL override
├── .gitignore
│
├── data/
│   └── README.md              # dataset provenance, expected files, how to obtain
├── raw_data/                  # place the 9 source CSVs here (gitignored)
│
├── docs/
│   ├── methodology.md
│   ├── data_dictionary.md
│   ├── data_quality.md
│   ├── data_model.md
│   ├── sql_analysis.md
│   ├── kpi_dictionary.md
│   ├── etl_pipeline.md
│   ├── customer_analysis.md
│   ├── seller_and_category_analysis.md
│   ├── logistics_analysis.md
│   ├── root_cause_analysis.md
│   ├── scenario_analysis.md
│   ├── recommendations.md
│   ├── testing.md
│   └── assumptions_and_limitations.md
│
├── sql/
│   ├── 01_raw_schema.sql
│   ├── 02_data_quality_audit.sql
│   ├── 03_constraints_and_indexes.sql
│   ├── 04_sql_foundation.sql
│   ├── 05_advanced_sql.sql
│   ├── 06_star_schema.sql
│   └── 07_data_quality_scorecard.sql
│
├── scripts/
│   ├── ingest_raw.py
│   ├── run_pipeline.py        # end-to-end: validate -> load -> constrain -> gate -> build -> export
│   └── verify_schema.py
│
├── tests/
│   └── test_data_quality.py   # 37 tests, requires a live database (see docs/testing.md)
│
├── business_case/
│   ├── build_business_case.js
│   ├── package.json
│   └── Business_Recommendations.docx
│
└── logs/                      # pipeline run logs (gitignored contents)
```

## Reproducing this analysis

```bash
# 1. Clone and set up a virtual environment
git clone <this-repo>
cd olist-command-center
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt

# 2. Start PostgreSQL and create the database
createdb olist

# 3. Get the dataset (see data/README.md) and place the 9 CSVs in raw_data/

# 4. (Optional) sanity-check the raw files
python3 scripts/verify_schema.py

# 5. Run the full pipeline: load -> constrain -> quality gate -> star schema -> CSV export
python3 scripts/run_pipeline.py

# 6. Run the test suite
pytest tests/test_data_quality.py -v
```

If your local PostgreSQL setup differs from
`postgresql+psycopg2://postgres:YOUR_PASSWORD@localhost:5433/olist`, copy
`.env.example` to `.env` and set `OLIST_DB_URL`, then `export $(cat .env)`
before running the commands above.

**Note on verification:** the pipeline and test suite require a live
PostgreSQL instance and were not executed end-to-end in the environment used
to prepare this repository. All SQL was reviewed for correctness and every
figure in `docs/` was computed and cross-checked against at least one
independent calculation path (see `docs/kpi_dictionary.md` and
`docs/testing.md` for specifics), but "computed and verified via multiple
paths" is not the same claim as "this exact pipeline was run end-to-end
here" — see `docs/testing.md` for exactly what to check locally.

## Limitations

This project reports associations (e.g., late delivery ↔ lower review
scores, regional logistics patterns) as associations, not proven causes, and
makes no revenue-impact or ROI claims the data can't support. See
`docs/assumptions_and_limitations.md` for the full list, including data
gaps, scope boundaries, and known edge cases.
