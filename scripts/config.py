"""
Shared configuration for the pipeline, the standalone ingestion script, and
the test suite — defined ONCE here so the three can never disagree again
(previously the DB URL, port, and expected row counts were copy-pasted into
three files and had drifted apart).

Database connection
-------------------
Resolution order for the connection string:
  1. The OLIST_DB_URL environment variable, if set.
  2. OLIST_DB_URL in a `.env` file at the project root, if present
     (parsed here with a tiny built-in reader — no extra dependency, and it
     works the same on Windows, macOS, and Linux).
  3. DEFAULT_DB_URL below (PostgreSQL's standard port, 5432).

Raw data location
-----------------
All 9 source CSVs live in <project root>/raw_data/ (override with
OLIST_RAW_DIR if you keep them elsewhere).
"""
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SQL_DIR = PROJECT_ROOT / "sql"
LOG_DIR = PROJECT_ROOT / "logs"
EXPORT_DIR = PROJECT_ROOT / "data_export"

DEFAULT_DB_URL = "postgresql+psycopg2://postgres:postgres@localhost:5432/olist"


def _read_dotenv(path: Path) -> dict:
    """Minimal KEY=VALUE reader. Ignores blank lines and # comments."""
    values = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


_dotenv = _read_dotenv(PROJECT_ROOT / ".env")

DB_URL = os.environ.get("OLIST_DB_URL") or _dotenv.get("OLIST_DB_URL") or DEFAULT_DB_URL
RAW_DIR = Path(os.environ.get("OLIST_RAW_DIR") or _dotenv.get("OLIST_RAW_DIR") or PROJECT_ROOT / "raw_data")


def masked_db_url(url: str = DB_URL) -> str:
    """The connection string with the password hidden, safe to print/log."""
    try:
        from sqlalchemy.engine import make_url
        return make_url(url).render_as_string(hide_password=True)
    except Exception:
        return "<unparseable OLIST_DB_URL>"


# ---------------------------------------------------------------------------
# Source-file manifest: the exact row counts of the 9 CSVs this project is
# validated against (parsed rows, header excluded — NOT `wc -l` line counts,
# which over-count files with embedded newlines in quoted text).
#
# olist_order_reviews_dataset.csv: 99,224 rows. The Olist dataset has been
# published in more than one revision; an earlier revision of the reviews file
# had 100,000 rows, and this repository's original documentation and tests
# were written against that revision. The other 8 files are identical in row
# count across revisions. The pipeline validates against the files actually
# supplied (99,224) rather than a figure the data can't reproduce.
# ---------------------------------------------------------------------------
EXPECTED_ROW_COUNTS = {
    "olist_customers_dataset.csv": 99441,
    "olist_orders_dataset.csv": 99441,
    "olist_order_items_dataset.csv": 112650,
    "olist_order_payments_dataset.csv": 103886,
    "olist_order_reviews_dataset.csv": 99224,
    "olist_products_dataset.csv": 32951,
    "olist_sellers_dataset.csv": 3095,
    "olist_geolocation_dataset.csv": 1000163,
    "product_category_name_translation.csv": 71,
}

# (csv filename, target table, timestamp columns to parse)
TABLE_MAP = [
    ("olist_customers_dataset.csv", "raw.customers", []),
    ("olist_orders_dataset.csv", "raw.orders",
     ["order_purchase_timestamp", "order_approved_at",
      "order_delivered_carrier_date", "order_delivered_customer_date",
      "order_estimated_delivery_date"]),
    ("olist_order_items_dataset.csv", "raw.order_items", ["shipping_limit_date"]),
    ("olist_order_payments_dataset.csv", "raw.payments", []),
    ("olist_order_reviews_dataset.csv", "raw.reviews",
     ["review_creation_date", "review_answer_timestamp"]),
    ("olist_products_dataset.csv", "raw.products", []),
    ("olist_sellers_dataset.csv", "raw.sellers", []),
    ("olist_geolocation_dataset.csv", "raw.geolocation", []),
    ("product_category_name_translation.csv", "raw.category_translation", []),
]

EXPECTED_RAW_TABLE_COUNTS = {
    table: EXPECTED_ROW_COUNTS[csv] for csv, table, _ in TABLE_MAP
}

ANALYTICS_TABLES = [
    "dim_date", "dim_customer", "dim_product", "dim_seller", "dim_geography",
    "fact_order_items", "fact_orders", "fact_payments",
]
