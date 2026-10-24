"""
Schema verification for the raw Olist CSV files.

For each file, reports:
- shape (rows, columns)
- column names and inferred dtypes
- null counts per column
- duplicate row count
- duplicate count on likely primary key column(s)
- min/max on date-like columns

Also checks each file against the expected column list and row count, and
exits with code 1 (after printing every problem) if anything is off — so it
can be used as a real pre-flight check, not just a printout.

Run with: python scripts/verify_schema.py
"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import EXPECTED_ROW_COUNTS, RAW_DIR  # noqa: E402

# Columns each file must contain (the raw DDL in sql/01_raw_schema.sql
# depends on exactly these names, including the source typo "lenght").
EXPECTED_COLUMNS = {
    "olist_customers_dataset.csv": ["customer_id", "customer_unique_id", "customer_zip_code_prefix", "customer_city", "customer_state"],
    "olist_orders_dataset.csv": ["order_id", "customer_id", "order_status", "order_purchase_timestamp", "order_approved_at",
                                 "order_delivered_carrier_date", "order_delivered_customer_date", "order_estimated_delivery_date"],
    "olist_order_items_dataset.csv": ["order_id", "order_item_id", "product_id", "seller_id", "shipping_limit_date", "price", "freight_value"],
    "olist_order_payments_dataset.csv": ["order_id", "payment_sequential", "payment_type", "payment_installments", "payment_value"],
    "olist_order_reviews_dataset.csv": ["review_id", "order_id", "review_score", "review_comment_title", "review_comment_message",
                                        "review_creation_date", "review_answer_timestamp"],
    "olist_products_dataset.csv": ["product_id", "product_category_name", "product_name_lenght", "product_description_lenght",
                                   "product_photos_qty", "product_weight_g", "product_length_cm", "product_height_cm", "product_width_cm"],
    "olist_sellers_dataset.csv": ["seller_id", "seller_zip_code_prefix", "seller_city", "seller_state"],
    "olist_geolocation_dataset.csv": ["geolocation_zip_code_prefix", "geolocation_lat", "geolocation_lng", "geolocation_city", "geolocation_state"],
    "product_category_name_translation.csv": ["product_category_name", "product_category_name_english"],
}
problems = []

FILES = {
    "customers": ("olist_customers_dataset.csv", "customer_id"),
    "orders": ("olist_orders_dataset.csv", "order_id"),
    "order_items": ("olist_order_items_dataset.csv", ["order_id", "order_item_id"]),
    "payments": ("olist_order_payments_dataset.csv", ["order_id", "payment_sequential"]),
    "reviews": ("olist_order_reviews_dataset.csv", "review_id"),
    "products": ("olist_products_dataset.csv", "product_id"),
    "sellers": ("olist_sellers_dataset.csv", "seller_id"),
    "geolocation": ("olist_geolocation_dataset.csv", None),
    "category_translation": ("product_category_name_translation.csv", "product_category_name"),
}

DATE_HINT_COLS = ["date", "timestamp", "_at"]

print(f"Raw data folder: {RAW_DIR}")
for label, (fname, pk) in FILES.items():
    path = RAW_DIR / fname
    if not path.exists():
        print(f"MISSING FILE: {path}")
        problems.append(f"missing file {fname}")
        continue
    df = pd.read_csv(path, encoding="utf-8")
    print("=" * 90)
    print(f"TABLE: {label}  ({fname})")
    print(f"Shape: {df.shape[0]:,} rows x {df.shape[1]} columns")
    expected_rows = EXPECTED_ROW_COUNTS[fname]
    if len(df) != expected_rows:
        problems.append(f"{fname}: {len(df):,} rows, expected {expected_rows:,}")
        print(f"ROW COUNT MISMATCH: expected {expected_rows:,}")
    missing_cols = [c for c in EXPECTED_COLUMNS[fname] if c not in df.columns]
    extra_cols = [c for c in df.columns if c not in EXPECTED_COLUMNS[fname]]
    if missing_cols or extra_cols:
        problems.append(f"{fname}: missing columns {missing_cols}, unexpected columns {extra_cols}")
        print(f"COLUMN MISMATCH: missing={missing_cols} unexpected={extra_cols}")
    print("-" * 90)
    print(f"{'column':35s} {'dtype':12s} {'nulls':>10s} {'null %':>8s}")
    for col in df.columns:
        n_null = df[col].isna().sum()
        pct = 100 * n_null / len(df) if len(df) else 0
        print(f"{col:35s} {str(df[col].dtype):12s} {n_null:>10,} {pct:>7.2f}%")

    # duplicate full rows
    dup_rows = df.duplicated().sum()
    print(f"\nFully duplicate rows: {dup_rows:,}")

    # candidate PK duplicate check
    if pk is not None:
        if isinstance(pk, list):
            dup_pk = df.duplicated(subset=pk).sum()
            print(f"Duplicate rows on candidate key {pk}: {dup_pk:,}")
        else:
            dup_pk = df.duplicated(subset=[pk]).sum()
            n_unique = df[pk].nunique()
            print(f"Duplicate rows on candidate key '{pk}': {dup_pk:,}  |  unique values: {n_unique:,} / {len(df):,} rows")
    else:
        print("No single candidate primary key expected for this table (composite/grain TBD).")

    # date-like columns: report min/max to catch anomalies later
    date_cols = [c for c in df.columns if any(h in c.lower() for h in DATE_HINT_COLS)]
    if date_cols:
        print(f"\nDate-like columns detected: {date_cols}")
        for c in date_cols:
            try:
                parsed = pd.to_datetime(df[c], errors="coerce")
                print(f"  {c}: min={parsed.min()}  max={parsed.max()}  unparseable={parsed.isna().sum() - df[c].isna().sum()}")
            except Exception as e:
                print(f"  {c}: could not parse ({e})")
    print()

print("=" * 90)
if problems:
    print(f"SCHEMA CHECK FAILED — {len(problems)} problem(s):")
    for p in problems:
        print(f"  - {p}")
    sys.exit(1)
print("SCHEMA CHECK PASSED: all 9 files present, expected columns and row counts match.")
