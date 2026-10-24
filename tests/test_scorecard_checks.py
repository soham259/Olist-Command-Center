"""
Scorecard regression tests — ADDED DURING THE 2026-10 AUDIT.

Before this file, 9 of the 14 data-quality checks in docs/data_quality.md
were only printed by the scorecard (sql/07) and had no automated assertion.
Each test below pins one of them at the value found in the supplied files,
so a future data refresh that changes it fails loudly instead of the docs
silently going stale. Kept separate from tests/test_data_quality.py (the
original 37-test suite).

Requires the pipeline to have been run (scripts/run_pipeline.py).
"""
import pytest
from sqlalchemy import create_engine, text

from config import DB_URL

pytestmark = pytest.mark.db  # every test here queries the live database


@pytest.fixture(scope="module")
def engine():
    eng = create_engine(DB_URL)
    yield eng
    eng.dispose()


def scalar(engine, sql):
    with engine.connect() as conn:
        return conn.execute(text(sql)).scalar()


# (scorecard issue #, check name, SQL, expected) — numbering as in docs/audit_report.md §8
SCORECARD_CHECKS = {
    "03_orders_with_no_items": (
        "SELECT COUNT(*) FROM raw.orders o LEFT JOIN raw.order_items oi ON o.order_id = oi.order_id "
        "WHERE oi.order_id IS NULL", 775),
    "05_delivered_before_carrier_handoff": (
        "SELECT COUNT(*) FROM raw.orders WHERE order_delivered_customer_date < order_delivered_carrier_date", 23),
    "07_delivered_status_null_delivery_date": (
        "SELECT COUNT(*) FROM raw.orders WHERE order_status = 'delivered' "
        "AND order_delivered_customer_date IS NULL", 8),
    "08_canceled_with_delivery_date": (
        "SELECT COUNT(*) FROM raw.orders WHERE order_status = 'canceled' "
        "AND order_delivered_customer_date IS NOT NULL", 6),
    "09_zero_value_payments": (
        "SELECT COUNT(*) FROM raw.payments WHERE payment_value = 0", 9),
    "10_payment_vs_item_total_mismatch_over_1": (
        """WITH i AS (SELECT order_id, SUM(price + freight_value) AS t FROM raw.order_items GROUP BY order_id),
                p AS (SELECT order_id, SUM(payment_value) AS t FROM raw.payments GROUP BY order_id)
           SELECT COUNT(*) FROM i JOIN p ON i.order_id = p.order_id WHERE ABS(i.t - p.t) > 1""", 249),
    "12_geolocation_full_row_duplicates": (
        "SELECT COUNT(*) - (SELECT COUNT(*) FROM (SELECT DISTINCT * FROM raw.geolocation) d) FROM raw.geolocation",
        261831),
    "13_missing_delivery_date": (
        "SELECT COUNT(*) FROM raw.orders WHERE order_delivered_customer_date IS NULL", 2965),
    "14_missing_review_comment": (
        "SELECT COUNT(*) FROM raw.reviews WHERE review_comment_message IS NULL", 58247),
}


@pytest.mark.parametrize("name", SCORECARD_CHECKS.keys())
def test_scorecard_check_count(engine, name):
    sql, expected = SCORECARD_CHECKS[name]
    actual = scalar(engine, sql)
    assert actual == expected, f"{name}: expected {expected}, got {actual} — re-investigate and update docs"


def test_geolocation_deduplicates_to_one_row_per_prefix(engine):
    """Handling decision for issue #12: dim_geography has exactly one row per raw zip prefix."""
    prefixes = scalar(engine, "SELECT COUNT(DISTINCT geolocation_zip_code_prefix) FROM raw.geolocation")
    dim_rows = scalar(engine, "SELECT COUNT(*) FROM analytics.dim_geography")
    assert dim_rows == prefixes == 19015


def test_item_less_orders_excluded_from_revenue(engine):
    """Handling decision for issue #3: no order without items carries revenue in fact_orders."""
    assert scalar(engine, "SELECT COUNT(*) FROM analytics.fact_orders WHERE n_items = 0 AND item_revenue <> 0") == 0


def test_null_delivery_date_orders_excluded_from_on_time(engine):
    """Handling decision for issue #7: the 8 'delivered' orders without a date have is_on_time NULL."""
    assert scalar(engine, """
        SELECT COUNT(*) FROM analytics.fact_orders fo JOIN raw.orders o ON fo.order_id = o.order_id
        WHERE o.order_status = 'delivered' AND o.order_delivered_customer_date IS NULL
          AND fo.is_on_time IS NOT NULL""") == 0
