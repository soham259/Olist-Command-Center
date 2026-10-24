"""
Data-quality and reconciliation test suite.

Covers data loading, referential integrity, revenue reconciliation, published
KPI cross-checks, date anomalies, duplicate business keys, and star-schema
grain — going beyond Step 4 of scripts/run_pipeline.py (which only covers a
4-check FK subset as a fast regression gate on every pipeline run).

Requires a PostgreSQL database with the pipeline already run (see
scripts/run_pipeline.py) — these tests query the live database, not the
raw CSVs directly.

Run with: pytest tests/test_data_quality.py -v

Connection string: see scripts/config.py (OLIST_DB_URL env var or .env file).
"""
import pytest
from sqlalchemy import create_engine, text

from config import DB_URL, EXPECTED_RAW_TABLE_COUNTS

pytestmark = pytest.mark.db  # every test here queries the live database


@pytest.fixture(scope="module")
def engine():
    eng = create_engine(DB_URL)
    yield eng
    eng.dispose()


def scalar(engine, sql):
    with engine.connect() as conn:
        return conn.execute(text(sql)).scalar()


# ============================================================
# 1. DATA LOADING — row counts match known source counts exactly
# ============================================================

# Single source of truth: scripts/config.py (EXPECTED_ROW_COUNTS manifest).
EXPECTED_RAW_COUNTS = EXPECTED_RAW_TABLE_COUNTS

@pytest.mark.parametrize("table,expected", EXPECTED_RAW_COUNTS.items())
def test_raw_row_counts(engine, table, expected):
    actual = scalar(engine, f"SELECT COUNT(*) FROM {table}")
    assert actual == expected, f"{table}: expected {expected}, got {actual}"


# ============================================================
# 2. REFERENTIAL INTEGRITY — zero orphans on every enforced FK
# ============================================================

FK_CHECKS = {
    "orders_missing_customer": "SELECT COUNT(*) FROM raw.orders o LEFT JOIN raw.customers c ON o.customer_id=c.customer_id WHERE c.customer_id IS NULL",
    "order_items_missing_order": "SELECT COUNT(*) FROM raw.order_items oi LEFT JOIN raw.orders o ON oi.order_id=o.order_id WHERE o.order_id IS NULL",
    "order_items_missing_product": "SELECT COUNT(*) FROM raw.order_items oi LEFT JOIN raw.products p ON oi.product_id=p.product_id WHERE p.product_id IS NULL",
    "order_items_missing_seller": "SELECT COUNT(*) FROM raw.order_items oi LEFT JOIN raw.sellers s ON oi.seller_id=s.seller_id WHERE s.seller_id IS NULL",
    "payments_missing_order": "SELECT COUNT(*) FROM raw.payments p LEFT JOIN raw.orders o ON p.order_id=o.order_id WHERE o.order_id IS NULL",
    "reviews_missing_order": "SELECT COUNT(*) FROM raw.reviews r LEFT JOIN raw.orders o ON r.order_id=o.order_id WHERE o.order_id IS NULL",
}

@pytest.mark.parametrize("name,sql", FK_CHECKS.items())
def test_referential_integrity(engine, name, sql):
    orphans = scalar(engine, sql)
    assert orphans == 0, f"{name}: found {orphans} orphan rows (expected 0)"


def test_known_category_translation_gap(engine):
    """This ONE relationship is deliberately not a hard FK (see docs/data_model.md).
    Test pins the known gap at exactly 13 rows / 2 categories — a regression
    check that this specific known issue hasn't grown, not a pass/fail gate."""
    orphans = scalar(engine, """
        SELECT COUNT(*) FROM raw.products p
        LEFT JOIN raw.category_translation ct ON p.product_category_name = ct.product_category_name
        WHERE p.product_category_name IS NOT NULL AND ct.product_category_name IS NULL
    """)
    assert orphans == 13, f"Expected the known 13-row category translation gap, found {orphans}"


# ============================================================
# 3. REVENUE RECONCILIATION — must match to the cent across paths
# ============================================================

def test_revenue_reconciles_item_grain_vs_order_grain(engine):
    item_grain = scalar(engine, """
        SELECT SUM(foi.price) FROM analytics.fact_order_items foi
        JOIN analytics.fact_orders fo ON foi.order_id = fo.order_id
        WHERE fo.order_status = 'delivered'
    """)
    order_grain = scalar(engine, "SELECT SUM(item_revenue) FROM analytics.fact_orders WHERE order_status='delivered'")
    assert round(float(item_grain), 2) == round(float(order_grain), 2)


def test_revenue_matches_kpi_dictionary(engine):
    """Pins the KPI dictionary's published figure (docs/kpi_dictionary.md) as a regression check."""
    revenue = scalar(engine, "SELECT SUM(item_revenue) FROM analytics.fact_orders WHERE order_status='delivered'")
    assert round(float(revenue), 2) == 13221498.11


def test_payments_reconcile_star_vs_raw(engine):
    star = scalar(engine, "SELECT SUM(payment_value) FROM analytics.fact_payments")
    raw = scalar(engine, "SELECT SUM(payment_value) FROM raw.payments")
    assert round(float(star), 2) == round(float(raw), 2)


# ============================================================
# 4. DASHBOARD KPI CROSS-CHECKS — re-derive fresh, compare to published figures
# ============================================================

def test_aov_matches_published_figure(engine):
    row = None
    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT ROUND(SUM(item_revenue)/COUNT(*), 2) FROM analytics.fact_orders WHERE order_status='delivered'
        """)).scalar()
    assert float(row) == 137.04


def test_on_time_rate_matches_published_figure(engine):
    pct = scalar(engine, """
        SELECT ROUND(100.0*COUNT(*) FILTER (WHERE is_on_time=TRUE)/COUNT(*) FILTER (WHERE is_on_time IS NOT NULL), 2)
        FROM analytics.fact_orders WHERE order_status='delivered'
    """)
    assert float(pct) == 91.89


def test_repeat_purchase_rate_matches_published_figure(engine):
    pct = scalar(engine, """
        WITH cust AS (
            SELECT customer_key, COUNT(*) n FROM analytics.fact_orders WHERE order_status='delivered' GROUP BY customer_key
        )
        SELECT ROUND(100.0*COUNT(*) FILTER (WHERE n>1)/COUNT(*), 2) FROM cust
    """)
    assert float(pct) == 3.00


# ============================================================
# 5. DATE ANOMALIES — impossible sequences must stay at zero;
#    known/accepted anomalies are pinned at their documented counts
# ============================================================

def test_no_delivery_before_purchase(engine):
    assert scalar(engine, "SELECT COUNT(*) FROM raw.orders WHERE order_delivered_customer_date < order_purchase_timestamp") == 0

def test_no_approval_before_purchase(engine):
    assert scalar(engine, "SELECT COUNT(*) FROM raw.orders WHERE order_approved_at < order_purchase_timestamp") == 0

def test_no_estimated_delivery_before_purchase(engine):
    assert scalar(engine, "SELECT COUNT(*) FROM raw.orders WHERE order_estimated_delivery_date < order_purchase_timestamp") == 0

def test_known_carrier_before_approval_anomaly_count(engine):
    """Documented in docs/data_quality.md as a legitimate process-change pattern (concentrated
    post-April 2018), not a data error — pinned here so any FUTURE change to this
    count gets caught and re-investigated rather than silently drifting."""
    count = scalar(engine, "SELECT COUNT(*) FROM raw.orders WHERE order_delivered_carrier_date < order_approved_at")
    assert count == 1359


# ============================================================
# 6. DUPLICATE BUSINESS KEYS
# ============================================================

def test_order_id_is_unique(engine):
    dupes = scalar(engine, "SELECT COUNT(*) - COUNT(DISTINCT order_id) FROM raw.orders")
    assert dupes == 0

def test_customer_id_is_unique(engine):
    dupes = scalar(engine, "SELECT COUNT(*) - COUNT(DISTINCT customer_id) FROM raw.customers")
    assert dupes == 0

def test_product_id_is_unique(engine):
    dupes = scalar(engine, "SELECT COUNT(*) - COUNT(DISTINCT product_id) FROM raw.products")
    assert dupes == 0

def test_review_id_is_KNOWN_not_unique(engine):
    """This is an intentional negative test: review_id is documented (docs/data_dictionary.md)
    as NOT a valid standalone key. Asserting the exact known duplication count
    protects against silently forgetting this and joining on review_id alone
    somewhere in the future."""
    total = scalar(engine, "SELECT COUNT(*) FROM raw.reviews")
    distinct = scalar(engine, "SELECT COUNT(DISTINCT review_id) FROM raw.reviews")
    # 814 surplus rows in the supplied 99,224-row reviews file (audit-verified).
    # The original pin of 827 came from the earlier 100,000-row revision of
    # this file; see the EXPECTED_ROW_COUNTS note in scripts/config.py.
    assert total - distinct == 814, "The known review_id duplication count has changed — re-investigate"


# ============================================================
# 7. STAR SCHEMA GRAIN — fact tables preserve intended grain,
#    dimension joins do not introduce fan-out
# ============================================================

def test_fact_order_items_grain_matches_source(engine):
    assert scalar(engine, "SELECT COUNT(*) FROM analytics.fact_order_items") == 112650

def test_fact_orders_grain_matches_source(engine):
    assert scalar(engine, "SELECT COUNT(*) FROM analytics.fact_orders") == 99441

def test_fact_payments_grain_matches_source(engine):
    assert scalar(engine, "SELECT COUNT(*) FROM analytics.fact_payments") == 103886

def test_dimension_joins_do_not_fan_out_fact_order_items(engine):
    """The critical grain-preservation test: joining fact_order_items to ALL
    of its dimensions simultaneously must not change the row count. If any
    dimension had a duplicate natural key (e.g. dim_product.product_id not
    unique), this join would silently multiply rows — this test would catch it."""
    joined_count = scalar(engine, """
        SELECT COUNT(*) FROM analytics.fact_order_items foi
        JOIN analytics.dim_product dp ON foi.product_key = dp.product_key
        JOIN analytics.dim_seller ds ON foi.seller_key = ds.seller_key
        JOIN analytics.dim_customer dc ON foi.customer_key = dc.customer_key
        JOIN analytics.dim_date dd ON foi.date_key = dd.date_key
    """)
    assert joined_count == 112650, f"Dimension join fan-out detected: {joined_count} rows, expected 112650"

def test_dim_product_key_is_unique(engine):
    dupes = scalar(engine, "SELECT COUNT(*) - COUNT(DISTINCT product_key) FROM analytics.dim_product")
    assert dupes == 0

def test_dim_customer_key_is_unique(engine):
    dupes = scalar(engine, "SELECT COUNT(*) - COUNT(DISTINCT customer_key) FROM analytics.dim_customer")
    assert dupes == 0

def test_dim_customer_natural_key_is_unique(engine):
    """dim_customer's natural key (customer_unique_id) must also be unique —
    this is the deduplication guarantee from the star-schema design (docs/data_model.md), tested directly."""
    dupes = scalar(engine, "SELECT COUNT(*) - COUNT(DISTINCT customer_unique_id) FROM analytics.dim_customer")
    assert dupes == 0
