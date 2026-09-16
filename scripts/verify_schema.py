"""
Schema verification for the raw Olist CSV files.

For each file, reports:
- shape (rows, columns)
- column names and inferred dtypes
- null counts per column
- duplicate row count
- duplicate count on likely primary key column(s)
- min/max on date-like columns

Run with: python3 scripts/verify_schema.py
"""
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = PROJECT_ROOT / "raw_data"

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

for label, (fname, pk) in FILES.items():
    path = RAW_DIR / fname
    df = pd.read_csv(path)
    print("=" * 90)
    print(f"TABLE: {label}  ({fname})")
    print(f"Shape: {df.shape[0]:,} rows x {df.shape[1]} columns")
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
