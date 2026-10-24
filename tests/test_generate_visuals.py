"""
Tests for scripts/generate_visuals.py.

Unit tests (no database needed): confidence intervals, data-quality status
rules, configuration errors, and an unreachable server.
Integration test (marked `db`, needs the pipeline to have been run): builds
the full report into a temporary folder and checks its numbers against the
verified figures in docs/audit_report.md.

    pytest tests/test_generate_visuals.py -m "not db"   # no PostgreSQL needed
"""
import math

import pandas as pd
import pytest

import config
import generate_visuals as gv


# ------------------------------------------------------------------ unit: statistics
def test_wilson_interval_known_value():
    lo, hi = gv.wilson(50, 100)
    assert round(lo, 1) == 40.4 and round(hi, 1) == 59.6


def test_wilson_interval_handles_zero_and_extremes():
    assert all(math.isnan(x) for x in gv.wilson(0, 0))
    lo, hi = gv.wilson(0, 40)
    assert lo == 0.0 and 0 < hi < 15          # never negative, still uncertain
    lo, hi = gv.wilson(40, 40)
    assert hi == 100.0 and lo > 85


def test_add_rates_flags_small_samples():
    df = pd.DataFrame({"late": [24, 1300], "n": [99, 9044]})
    out = gv.add_rates(df, "late", "n", min_n=100)
    assert out["small_sample"].tolist() == [True, False]
    assert round(out["late_pct"].iloc[1], 2) == 14.37
    assert (out["ci_low"] < out["late_pct"]).all() and (out["late_pct"] < out["ci_high"]).all()


# ------------------------------------------------------------------ unit: data-quality rules
@pytest.mark.parametrize("check_id,observed,expected", [
    ("ri_orders_customer", 0, "PASS"),          # must be zero
    ("ri_orders_customer", 3, "FAIL"),
    ("dup_review_id", 814, "WARN"),             # documented exception, unchanged
    ("dup_review_id", 827, "FAIL"),             # documented exception that drifted
    ("na_review_comment", 58247, "PASS"),       # expected business behaviour
    ("na_review_comment", 60000, "WARN"),
    ("rec_revenue_item_vs_order", 0.004, "PASS"),  # within one cent
    ("rec_revenue_item_vs_order", 0.02, "FAIL"),
    ("not_a_known_check", 1, "WARN"),
    ("ri_items_order", None, "FAIL"),
])
def test_dq_status(check_id, observed, expected):
    assert gv.dq_status(check_id, observed)[0] == expected


def test_every_check_in_the_sql_view_has_a_rule():
    sql = (config.SQL_DIR / "09_reporting_views.sql").read_text(encoding="utf-8")
    ids = {line.split("'")[1] for line in sql.splitlines() if "SELECT '" in line and "AS check_id" in line or
           line.strip().startswith("UNION ALL SELECT '")}
    assert ids and ids <= set(gv.DQ_RULES), f"checks without a rule: {ids - set(gv.DQ_RULES)}"


# ------------------------------------------------------------------ unit: configuration and connection errors
@pytest.mark.parametrize("url,fragment", [
    ("not a url", "not a valid connection string"),
    ("sqlite:///olist.db", "must point to a PostgreSQL database"),
    ("postgresql+psycopg2://postgres:YOUR_PASSWORD@localhost:5432/olist", "placeholder"),
])
def test_bad_configuration_gives_useful_error(url, fragment):
    with pytest.raises(gv.ReportError, match=fragment):
        gv.connect(url)


def test_unreachable_database_exits_1_with_message(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(config, "DB_URL", "postgresql+psycopg2://postgres:secret-pw@127.0.0.1:1/olist")
    assert gv.main(["--out", str(tmp_path)]) == 1
    err = capsys.readouterr().err
    assert "Could not connect to PostgreSQL" in err
    assert "secret-pw" not in err               # password never printed


# ------------------------------------------------------------------ integration
@pytest.mark.db
def test_full_report_matches_verified_figures(tmp_path):
    assert gv.main(["--out", str(tmp_path)]) == 0
    assert len(list((tmp_path / "charts").glob("*.png"))) == 15
    assert len(list((tmp_path / "tables").glob("*.csv"))) == 14
    html = (tmp_path / "report.html").read_text(encoding="utf-8")
    assert "data:image/png;base64," in html

    kpi = pd.read_csv(tmp_path / "tables" / "01_kpi_summary.csv").set_index("kpi")["value"]
    assert kpi["Delivered item revenue (R$)"] == 13221498.11
    assert kpi["Delivered orders"] == 96478
    assert kpi["Late-delivery rate (%)"] == 8.11
    assert kpi["Repeat-purchase rate (%)"] == 3.00
    assert kpi["Raw source rows"] == 1550922

    region = pd.read_csv(tmp_path / "tables" / "03_region_delivery.csv").set_index("region")
    assert round(region.loc["Nordeste", "late_pct"], 2) == 14.33
    assert region.loc["Nordeste", "ratio_vs_platform"] == 1.77

    quad = pd.read_csv(tmp_path / "tables" / "06_seller_quadrant_summary.csv").set_index("quadrant")
    assert quad.loc["High revenue, low performance", "sellers"] == 207
    assert len(pd.read_csv(tmp_path / "tables" / "07_coaching_candidates.csv")) == 207

    tiers = pd.read_csv(tmp_path / "tables" / "09_customer_spend_tiers.csv").set_index("spend_tier")
    assert tiers.loc["1_high_top5pct", "repeat_rate_pct"] == 8.52

    dq = pd.read_csv(tmp_path / "tables" / "13_data_quality_checks.csv")
    assert (dq["status"] != "FAIL").all()

    # no credentials anywhere in the outputs
    password = config.DB_URL.split("://", 1)[1].split("@", 1)[0].split(":", 1)[-1]
    for f in [tmp_path / "report.html", *(tmp_path / "tables").glob("*.csv")]:
        assert password not in f.read_text(encoding="utf-8") or len(password) < 4
