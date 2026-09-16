"""
Reproducible ETL Pipeline

Runs the full CSV -> raw -> analytics build in one command:

    python3 scripts/run_pipeline.py

Design decision — no dbt:
This is a single, linear pipeline (9 source files -> one raw schema -> one
analytics schema), run by a single person, with no team-collaboration need,
no incremental/streaming requirement, and no multi-environment promotion
workflow. dbt's core value (modular SQL with ref(), automatic dependency
graphs, built-in testing across many models, team-shared documentation site)
mostly pays off once a project has many interdependent models or multiple
contributors. Introducing it here would add real learning/tooling cost
(profiles.yml, a dbt project structure, a separate CLI) without a
corresponding benefit at this project's size. A plain Python orchestrator
over SQL files covers steps, validation, and idempotent re-runs equally well
here.

What this script actually does, step by step:
  1. Validate the 9 raw CSVs are present with the expected row counts
  2. (Re)build the raw schema and load all 9 tables, validating row counts
     against source after load
  3. Apply foreign key constraints and indexes to the raw layer
  4. Run a subset of the data-quality checks as automated assertions (fails
     loudly if a previously-clean relationship becomes dirty on a future
     data refresh — this is the actual reproducibility test)
  5. (Re)build the analytics star schema, validating that fact_order_items
     and fact_orders reconcile to the cent, and that fact_payments matches
     raw.payments to the cent
  6. Export every analytics table to CSV, for use in any downstream
     reporting/BI tool

Logging goes to both console and logs/pipeline_<timestamp>.log.
Exits with a non-zero code and a clear message on any validation failure.

Configuration: set OLIST_DB_URL to override the default local connection
string (postgresql+psycopg2://postgres:postgres@localhost:5432/olist).
"""

import logging
import os
import sys
import time
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = PROJECT_ROOT / "raw_data"
SQL_DIR = PROJECT_ROOT / "sql"
LOG_DIR = PROJECT_ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)
ANALYTICS_EXPORT_DIR = PROJECT_ROOT / "data_export"

ANALYTICS_TABLES = [
    "dim_date", "dim_customer", "dim_product", "dim_seller", "dim_geography",
    "fact_order_items", "fact_orders", "fact_payments",
]

DB_URL = os.environ.get(
    "OLIST_DB_URL", "postgresql+psycopg2://postgres:postgres@localhost:5432/olist"
)

EXPECTED_ROW_COUNTS = {
    "olist_customers_dataset.csv": 99441,
    "olist_orders_dataset.csv": 99441,
    "olist_order_items_dataset.csv": 112650,
    "olist_order_payments_dataset.csv": 103886,
    "olist_order_reviews_dataset.csv": 100000,
    "olist_products_dataset.csv": 32951,
    "olist_sellers_dataset.csv": 3095,
    "olist_geolocation_dataset.csv": 1000163,
    "product_category_name_translation.csv": 71,
}

TABLE_MAP = [
    ("olist_customers_dataset.csv", "raw.customers", []),
    ("olist_orders_dataset.csv", "raw.orders",
     ["order_purchase_timestamp", "order_approved_at",
      "order_delivered_carrier_date", "order_delivered_customer_date",
      "order_estimated_delivery_date"]),
    ("olist_order_items_dataset.csv", "raw.order_items", []),
    ("olist_order_payments_dataset.csv", "raw.payments", []),
    ("olist_order_reviews_dataset.csv", "raw.reviews",
     ["review_creation_date", "review_answer_timestamp"]),
    ("olist_products_dataset.csv", "raw.products", []),
    ("olist_sellers_dataset.csv", "raw.sellers", []),
    ("olist_geolocation_dataset.csv", "raw.geolocation", []),
    ("product_category_name_translation.csv", "raw.category_translation", []),
]


def setup_logging():
    ts = time.strftime("%Y%m%d_%H%M%S")
    log_path = LOG_DIR / f"pipeline_{ts}.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.FileHandler(log_path), logging.StreamHandler(sys.stdout)],
    )
    return logging.getLogger("olist_pipeline")


def run_sql_file(conn, path: Path, log):
    log.info(f"Running SQL file: {path.name}")
    sql_text = path.read_text()
    with conn.cursor() as cur:
        cur.execute(sql_text)
    conn.commit()
    log.info(f"  -> {path.name} completed OK")


def step_validate_source_files(log):
    log.info("STEP 1: Validating source CSV files")
    for fname, expected in EXPECTED_ROW_COUNTS.items():
        path = RAW_DIR / fname
        if not path.exists():
            log.error(f"  MISSING FILE: {fname}")
            raise FileNotFoundError(
                f"Required source file not found: {path}. "
                f"See data/README.md for how to obtain the dataset."
            )
        actual = len(pd.read_csv(path))
        status = "OK" if actual == expected else "MISMATCH"
        log.info(f"  {fname:45s} expected={expected:>9,}  actual={actual:>9,}  [{status}]")
        if actual != expected:
            raise ValueError(
                f"Row count mismatch for {fname}: expected {expected}, got {actual}. "
                f"Pipeline halted — do not proceed on unverified source data."
            )
    log.info("STEP 1 complete: all 9 source files verified.\n")


def step_build_raw_schema(engine, log):
    log.info("STEP 2: Building raw schema and loading tables")
    ddl_path = SQL_DIR / "01_raw_schema.sql"
    raw_conn = engine.raw_connection()
    try:
        run_sql_file(raw_conn, ddl_path, log)
    finally:
        raw_conn.close()

    with engine.begin() as conn:
        for csv_file, table, date_cols in TABLE_MAP:
            df = pd.read_csv(RAW_DIR / csv_file, parse_dates=date_cols)
            source_rows = len(df)
            schema, tbl = table.split(".")
            conn.execute(text(f"TRUNCATE TABLE {table}"))
            df.to_sql(tbl, con=conn, schema=schema, if_exists="append", index=False, method="multi", chunksize=5000)
            loaded_rows = conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()
            if loaded_rows != source_rows:
                raise ValueError(f"Load mismatch for {table}: source={source_rows}, loaded={loaded_rows}")
            log.info(f"  {table:28s} loaded={loaded_rows:>9,} rows [OK]")
    log.info("STEP 2 complete: raw schema loaded and row-count verified.\n")


def step_apply_constraints(engine, log):
    log.info("STEP 3: Applying foreign key constraints and indexes")
    raw_conn = engine.raw_connection()
    try:
        run_sql_file(raw_conn, SQL_DIR / "03_constraints_and_indexes.sql", log)
    finally:
        raw_conn.close()
    log.info("STEP 3 complete: constraints applied without violation "
              "(this itself re-confirms referential integrity on every run).\n")


def step_data_quality_gate(engine, log):
    log.info("STEP 4: Automated data-quality gate (subset of the full audit, as hard assertions)")
    checks = {
        "orders_missing_customer": """
            SELECT COUNT(*) FROM raw.orders o
            LEFT JOIN raw.customers c ON o.customer_id = c.customer_id
            WHERE c.customer_id IS NULL""",
        "order_items_missing_order": """
            SELECT COUNT(*) FROM raw.order_items oi
            LEFT JOIN raw.orders o ON oi.order_id = o.order_id
            WHERE o.order_id IS NULL""",
        "payments_missing_order": """
            SELECT COUNT(*) FROM raw.payments p
            LEFT JOIN raw.orders o ON p.order_id = o.order_id
            WHERE o.order_id IS NULL""",
        "reviews_missing_order": """
            SELECT COUNT(*) FROM raw.reviews r
            LEFT JOIN raw.orders o ON r.order_id = o.order_id
            WHERE o.order_id IS NULL""",
    }
    with engine.connect() as conn:
        for name, sql in checks.items():
            result = conn.execute(text(sql)).scalar()
            status = "PASS" if result == 0 else "FAIL"
            log.info(f"  {name:35s} orphan_rows={result:>6}  [{status}]")
            if result != 0:
                raise AssertionError(
                    f"Data quality gate failed: {name} found {result} orphan rows. "
                    f"This relationship was previously clean — investigate before proceeding."
                )
    log.info("STEP 4 complete: all referential integrity gates passed.\n")


def step_build_star_schema(engine, log):
    log.info("STEP 5: Building analytics star schema")
    raw_conn = engine.raw_connection()
    try:
        run_sql_file(raw_conn, SQL_DIR / "06_star_schema.sql", log)
    finally:
        raw_conn.close()

    log.info("  Running reconciliation validation...")
    with engine.connect() as conn:
        item_rev = conn.execute(text("""
            SELECT SUM(foi.price) FROM analytics.fact_order_items foi
            JOIN analytics.fact_orders fo ON foi.order_id = fo.order_id
            WHERE fo.order_status = 'delivered'
        """)).scalar()
        order_rev = conn.execute(text("""
            SELECT SUM(item_revenue) FROM analytics.fact_orders WHERE order_status = 'delivered'
        """)).scalar()
        if round(float(item_rev), 2) != round(float(order_rev), 2):
            raise AssertionError(
                f"Star schema reconciliation FAILED: fact_order_items revenue "
                f"({item_rev}) != fact_orders revenue ({order_rev})"
            )
        log.info(f"  Revenue reconciliation: fact_order_items={item_rev}  fact_orders={order_rev}  [MATCH]")

        pay_star = conn.execute(text("SELECT SUM(payment_value) FROM analytics.fact_payments")).scalar()
        pay_raw = conn.execute(text("SELECT SUM(payment_value) FROM raw.payments")).scalar()
        if round(float(pay_star), 2) != round(float(pay_raw), 2):
            raise AssertionError(f"Payment reconciliation FAILED: {pay_star} != {pay_raw}")
        log.info(f"  Payment reconciliation: fact_payments={pay_star}  raw.payments={pay_raw}  [MATCH]")

    log.info("STEP 5 complete: star schema built and reconciled.\n")


def step_export_analytics_tables(engine, log):
    """
    STEP 6: export every analytics table to CSV, so the star schema is
    available for further analysis in any spreadsheet or BI tool without
    a live database connection. Re-running this step always reflects the
    latest successful pipeline run.
    """
    log.info("STEP 6: Exporting analytics tables to CSV")
    ANALYTICS_EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    with engine.connect() as conn:
        for table in ANALYTICS_TABLES:
            df = pd.read_sql(text(f"SELECT * FROM analytics.{table}"), conn)
            out_path = ANALYTICS_EXPORT_DIR / f"{table}.csv"
            df.to_csv(out_path, index=False)
            log.info(f"  {table:20s} -> {out_path.relative_to(PROJECT_ROOT)} ({len(df):,} rows)")
    log.info("STEP 6 complete: CSV export refreshed.\n")


def main():
    log = setup_logging()
    start = time.time()
    log.info("=" * 70)
    log.info("Olist Command Center — ETL Pipeline starting")
    log.info("=" * 70)

    try:
        step_validate_source_files(log)
        engine = create_engine(DB_URL)
        step_build_raw_schema(engine, log)
        step_apply_constraints(engine, log)
        step_data_quality_gate(engine, log)
        step_build_star_schema(engine, log)
        step_export_analytics_tables(engine, log)
    except Exception as e:
        log.error(f"PIPELINE FAILED: {e}")
        sys.exit(1)

    elapsed = time.time() - start
    log.info("=" * 70)
    log.info(f"Pipeline completed successfully in {elapsed:.1f} seconds")
    log.info("=" * 70)


if __name__ == "__main__":
    main()
