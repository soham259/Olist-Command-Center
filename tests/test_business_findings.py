"""
Business-finding regression tests — ADDED DURING THE 2026-10 AUDIT.

Kept separate from tests/test_data_quality.py (the original 37-test suite) so
the two can be counted and discussed independently.

These pin the headline findings to the views in sql/08_business_findings.sql,
using values reproduced from the supplied Olist files during the audit. Where
a documented/resume figure could NOT be reproduced exactly, the test pins the
reproduced value and the docstring states the documented figure, so the gap
stays visible rather than being hidden.

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


def one(engine, sql):
    with engine.connect() as conn:
        return conn.execute(text(sql)).one()


def scalar(engine, sql):
    with engine.connect() as conn:
        return conn.execute(text(sql)).scalar()


# ---------------------------------------------------------------- headline
def test_delivered_order_count(engine):
    """'R$13.2M revenue across 96K orders' — the order half."""
    assert scalar(engine, "SELECT COUNT(*) FROM analytics.fact_orders WHERE order_status = 'delivered'") == 96478


def test_total_raw_rows(engine):
    """All 9 raw tables. README/resume say ~1.45M; the supplied files total 1,550,922."""
    assert scalar(engine, "SELECT SUM(row_count) FROM analytics.v_row_inventory WHERE layer = 'raw'") == 1550922


# ---------------------------------------------------------------- Nordeste
def test_platform_late_rate(engine):
    assert float(scalar(engine, "SELECT MAX(platform_late_pct) FROM analytics.v_region_late_rate")) == 8.11


def test_nordeste_region_late_rate(engine):
    """Region as a whole: 14.33% late = 1.77x the platform rate (1.92x the rest of Brazil).
    The '2-3x' figure applies to the worst Nordeste STATES, not the region aggregate."""
    late_pct, ratio_platform, ratio_rest = one(engine, """
        SELECT late_pct, ratio_vs_platform, ratio_vs_rest
        FROM analytics.v_region_late_rate WHERE region = 'Nordeste'""")
    assert float(late_pct) == 14.33
    assert float(ratio_platform) == 1.77
    assert float(ratio_rest) == 1.92


def test_nordeste_states_in_2x_to_3x_band(engine):
    """Exactly two Nordeste states (AL 23.93%, MA 19.67%) sit at 2-3x the platform late rate."""
    states = scalar(engine, """
        SELECT STRING_AGG(customer_state, ',' ORDER BY customer_state)
        FROM analytics.v_state_late_rate
        WHERE region = 'Nordeste' AND late_pct / 8.11 BETWEEN 2 AND 3""")
    assert states == "AL,MA"


def test_alagoas_late_rate(engine):
    assert float(scalar(engine, "SELECT late_pct FROM analytics.v_state_late_rate WHERE customer_state = 'AL'")) == 23.93


# ---------------------------------------------------------------- seller quadrant
def test_seller_quadrant_kpi_consistent(engine):
    """Primary (KPI-consistent, delivered-only) definition: 207 sellers, R$5,403,116.94.
    Documented/resume figure: 212 sellers, R$5,366,989 — computed on the earlier
    100,000-row reviews file with all-status revenue; not exactly reproducible here."""
    sellers, revenue = one(engine, """
        SELECT sellers, total_revenue FROM analytics.v_seller_quadrant_summary
        WHERE basis = 'kpi_consistent' AND quadrant = 'High revenue, low performance'""")
    assert sellers == 207
    assert round(float(revenue), 2) == 5403116.94


def test_seller_quadrant_is_largest_revenue_block(engine):
    """The qualitative finding: high-revenue/low-performance is the biggest revenue quadrant."""
    top = scalar(engine, """
        SELECT quadrant FROM analytics.v_seller_quadrant_summary
        WHERE basis = 'kpi_consistent' ORDER BY total_revenue DESC LIMIT 1""")
    assert top == "High revenue, low performance"


def test_seller_quadrant_documented_population(engine):
    """The documented intermediate figures (818 qualifying sellers, median revenue
    R$6,408) reproduce exactly only under all-status revenue."""
    n, median = one(engine, """
        SELECT COUNT(*), ROUND(MAX(median_revenue)) FROM analytics.v_seller_quadrant
        WHERE basis = 'as_originally_documented'""")
    assert n == 818
    assert int(median) == 6408


# ---------------------------------------------------------------- customer tiers
def test_platform_repeat_rate(engine):
    total, repeaters = one(engine, """
        SELECT COUNT(*), COUNT(*) FILTER (WHERE delivered_orders > 1) FROM analytics.v_customer_spend""")
    assert (total, repeaters) == (93358, 2801)
    assert round(100.0 * repeaters / total, 2) == 3.00


def test_top_spend_tier_repeat_rate(engine):
    customers, repeat_pct = one(engine, """
        SELECT customers, repeat_rate_pct FROM analytics.v_customer_spend_tier WHERE spend_tier = '1_high_top5pct'""")
    assert customers == 4637
    assert float(repeat_pct) == 8.52


def test_first_order_tier_does_not_show_spend_gradient(engine):
    """Guards the audit caveat: by FIRST-order value, high spenders do NOT repeat more
    (2.19% vs 3.19% for the lowest tier). If this ever flips, re-check the caveat in docs."""
    rows = dict(tuple(r) for r in _rows(engine, "SELECT first_order_tier, repeat_rate_pct FROM analytics.v_repeat_by_first_order_tier"))
    assert float(rows["1_first_order_ge_420"]) == 2.19
    assert float(rows["3_first_order_lt_90"]) == 3.19


def _rows(engine, sql):
    with engine.connect() as conn:
        return conn.execute(text(sql)).fetchall()
