"""
CSV -> PostgreSQL raw layer ingestion.

Rerunnable: truncates each raw table before reloading. Reports row counts
loaded per table and compares against source CSV row counts as a basic
validation check.

This is a standalone version of Step 2 of scripts/run_pipeline.py, kept
separate for cases where you want to (re)load the raw layer without running
the full pipeline (constraints, quality gate, star schema).
"""
import os
import sys
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = PROJECT_ROOT / "raw_data"

DB_URL = os.environ.get(
    "OLIST_DB_URL", "postgresql+psycopg2://postgres:postgres@localhost:5432/olist"
)

TABLE_MAP = [
    # (csv filename, target table, date columns to parse)
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


def main():
    engine = create_engine(DB_URL)
    results = []

    with engine.begin() as conn:
        for csv_file, table, date_cols in TABLE_MAP:
            path = RAW_DIR / csv_file
            df = pd.read_csv(path, parse_dates=date_cols)
            source_rows = len(df)

            schema, tbl = table.split(".")
            conn.execute(text(f"TRUNCATE TABLE {table}"))
            df.to_sql(tbl, con=conn, schema=schema, if_exists="append", index=False, method="multi", chunksize=5000)

            loaded_rows = conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()
            status = "OK" if loaded_rows == source_rows else "MISMATCH"
            results.append((table, source_rows, loaded_rows, status))
            print(f"{table:28s} source={source_rows:>9,}  loaded={loaded_rows:>9,}  [{status}]")

    print()
    mismatches = [r for r in results if r[3] == "MISMATCH"]
    if mismatches:
        print(f"WARNING: {len(mismatches)} table(s) had row-count mismatches.")
        sys.exit(1)
    else:
        print("All tables loaded with row counts matching source CSVs.")


if __name__ == "__main__":
    main()
