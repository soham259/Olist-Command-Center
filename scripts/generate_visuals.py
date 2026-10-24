"""
Olist Command Center — all charts and tables in one script.

Reads the analytics layer built by scripts/run_pipeline.py and writes:

    reports/charts/*.png     15 charts (PNG, 150 dpi)
    reports/tables/*.csv     14 tables
    reports/report.html      one self-contained report (charts + tables
                             embedded; open it by double-clicking)

Run from the project root, after the pipeline:

    python scripts/generate_visuals.py                # writes to reports/
    python scripts/generate_visuals.py --out C:\\tmp\\olist_report

Design rules:
  * Every number comes from the `analytics` schema (views in sql/06, 08, 09).
    No business metric is re-derived here: late = fact_orders.is_on_time rule,
    revenue = item price on delivered orders, review = order-level average,
    seller quadrants = v_seller_quadrant ('kpi_consistent'), customer tiers =
    v_customer_spend_tier. This script only aggregates those and adds 95%
    confidence intervals and small-sample flags.
  * The database session is read-only (default_transaction_read_only=on).
  * The connection string comes from OLIST_DB_URL (environment or .env) via
    scripts/config.py; the password is never printed.

Exit code 0 on success; 1 with a readable message if configuration is wrong,
PostgreSQL is unreachable, or the analytics views are missing.
"""
from __future__ import annotations

import argparse
import base64
import html
import math
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # file output only; no display needed (works headless and on Windows)
import matplotlib.pyplot as plt  # noqa: E402
import matplotlib.ticker as mticker  # noqa: E402
import pandas as pd  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402
from sqlalchemy.exc import ArgumentError, DBAPIError, OperationalError, ProgrammingError  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config  # noqa: E402  (OLIST_DB_URL resolution, source manifest)

# ------------------------------------------------------------------ constants
ACCENT = "#1F4E5F"     # main series
HIGHLIGHT = "#C8553D"  # the group a chart is about (Nordeste, coaching quadrant, ...)
MUTED = "#A9B4BC"
GRID = "#E6EAED"
QUADRANT_COLORS = {
    "High revenue, low performance": HIGHLIGHT,
    "High revenue, high performance": ACCENT,
    "Low revenue, high performance": "#7D9AA8",
    "Low revenue, low performance": "#D9A38F",
}
MIN_SAMPLE = 100  # groups with fewer eligible orders are flagged / faded
NORDESTE = "Nordeste"

# Pass / warning / fail rules for analytics.v_data_quality_checks, against the
# documented baselines in docs/data_quality.md.
#   zero     -> must be 0: PASS, else FAIL
#   known    -> documented exception: WARN if equal to baseline, FAIL if drifted
#   expected -> normal, handled behaviour: PASS if equal to baseline, WARN if drifted
DQ_RULES = {
    "ri_orders_customer": ("zero", 0), "ri_items_order": ("zero", 0), "ri_items_product": ("zero", 0),
    "ri_items_seller": ("zero", 0), "ri_payments_order": ("zero", 0), "ri_reviews_order": ("zero", 0),
    "ri_category_translation": ("known", 13), "ri_orders_no_items": ("expected", 775),
    "ri_orders_no_payment": ("known", 1),
    "dup_order_id": ("zero", 0), "dup_customer_id": ("zero", 0), "dup_product_id": ("zero", 0),
    "dup_review_id": ("known", 814), "dup_geolocation_rows": ("expected", 261831),
    "na_delivered_no_date": ("known", 8), "na_delivery_date": ("expected", 2965),
    "na_product_category": ("expected", 610), "na_review_comment": ("expected", 58247),
    "dt_delivered_before_purchase": ("zero", 0), "dt_approved_before_purchase": ("zero", 0),
    "dt_delivered_before_carrier": ("known", 23), "dt_carrier_before_approval": ("known", 1359),
    "dt_canceled_with_delivery": ("known", 6),
    "pay_zero_value": ("known", 9), "pay_item_mismatch": ("known", 249),
    "rec_revenue_item_vs_order": ("zero", 0), "rec_payments_star_vs_raw": ("zero", 0),
}


class ReportError(Exception):
    """A problem the user can fix (config, connection, missing views)."""


# ------------------------------------------------------------------ database
def connect(url: str):
    try:
        parsed = make_url(url)
    except ArgumentError:
        raise ReportError("OLIST_DB_URL is not a valid connection string. Expected "
                          "postgresql+psycopg2://USER:PASSWORD@HOST:5432/DATABASE") from None
    if parsed.get_backend_name() != "postgresql" or not parsed.database:
        raise ReportError("OLIST_DB_URL must point to a PostgreSQL database, e.g. "
                          "postgresql+psycopg2://postgres:PASSWORD@localhost:5432/olist")
    if parsed.password == "YOUR_PASSWORD":
        raise ReportError("OLIST_DB_URL still contains the placeholder YOUR_PASSWORD from .env.example — "
                          "edit .env and put your PostgreSQL password there.")
    return create_engine(url, connect_args={
        "connect_timeout": 5,
        "options": "-c default_transaction_read_only=on -c statement_timeout=120000",
    })


def q(engine, sql: str, params: dict | None = None) -> pd.DataFrame:
    """Run one read-only SELECT; NUMERIC -> float; friendly errors."""
    try:
        with engine.connect() as conn:
            res = conn.execute(text(sql), params or {})
            df = pd.DataFrame(res.fetchall(), columns=list(res.keys()))
    except OperationalError as e:
        raise ReportError(f"Could not connect to PostgreSQL at {masked(engine.url)}. Is the service running, "
                          f"and are host/port/user/password in .env correct? ({_first_line(e)})") from None
    except ProgrammingError as e:
        raise ReportError("The analytics views are missing or out of date — run "
                          f"`python scripts/run_pipeline.py` first. ({_first_line(e)})") from None
    except DBAPIError as e:
        raise ReportError(f"Query failed: {_first_line(e)}") from None
    for col in df.columns:
        if df[col].map(lambda v: isinstance(v, Decimal)).any():
            df[col] = df[col].astype(float)
    return df


def masked(url) -> str:
    try:
        return make_url(str(url) if not hasattr(url, "render_as_string") else url.render_as_string(False)) \
            .render_as_string(hide_password=True)
    except Exception:
        return "<unparseable URL>"


def _first_line(e: Exception) -> str:
    msg = str(getattr(e, "orig", e) or e).strip()
    return msg.splitlines()[0] if msg else e.__class__.__name__


# ------------------------------------------------------------------ statistics helpers
def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% Wilson interval for a proportion, as percentages."""
    if not n:
        return (math.nan, math.nan)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (100 * max(0.0, c - h), 100 * min(1.0, c + h))


def add_rates(df: pd.DataFrame, k: str, n: str, prefix: str = "late", min_n: int = MIN_SAMPLE) -> pd.DataFrame:
    out = df.copy()
    out[f"{prefix}_pct"] = [100 * a / b if b else math.nan for a, b in zip(out[k], out[n])]
    ci = [wilson(int(a), int(b)) for a, b in zip(out[k], out[n])]
    out["ci_low"] = [c[0] for c in ci]
    out["ci_high"] = [c[1] for c in ci]
    out["small_sample"] = out[n] < min_n
    return out


def dq_status(check_id: str, observed) -> tuple[str, str]:
    rule = DQ_RULES.get(check_id)
    if observed is None or pd.isna(observed):
        return "FAIL", "no value returned"
    if rule is None:
        return "WARN", "no rule defined"
    kind, base = rule
    obs = float(observed)
    if kind == "zero":
        tol = 0.005 if check_id.startswith("rec_") else 0
        return ("PASS", "0 as required") if abs(obs) <= tol else ("FAIL", f"expected 0, found {obs:,.2f}")
    if kind == "known":
        return ("WARN", f"known exception, {base:,} documented") if obs == base else \
               ("FAIL", f"drifted from documented {base:,}")
    return ("PASS", f"expected, {base:,} documented") if obs == base else ("WARN", f"differs from documented {base:,}")


# ------------------------------------------------------------------ chart helpers
def setup_style():
    plt.rcParams.update({
        "figure.dpi": 150, "savefig.dpi": 150, "font.size": 10, "axes.titlesize": 12,
        "axes.titleweight": "bold", "axes.titlelocation": "left", "axes.spines.top": False,
        "axes.spines.right": False, "axes.edgecolor": "#888", "axes.grid": True, "grid.color": GRID,
        "axes.axisbelow": True, "legend.frameon": False, "font.family": "DejaVu Sans",
    })


def brl_axis(ax, axis="y"):
    fmt = mticker.FuncFormatter(lambda v, _: f"R${v / 1e6:.1f}M" if abs(v) >= 1e6 else f"R${v / 1e3:.0f}K")
    (ax.yaxis if axis == "y" else ax.xaxis).set_major_formatter(fmt)


def num(v) -> str:
    """Whole numbers without decimals, others with two (for mixed-value columns)."""
    v = float(v)
    return f"{v:,.0f}" if v == int(v) else f"{v:,.2f}"


def brl(v, dec=0) -> str:
    return "—" if v is None or pd.isna(v) else (f"R${v / 1e6:,.2f}M" if abs(v) >= 1e6 and dec == 0 else f"R${v:,.{dec}f}")


class Report:
    """Collects charts and tables, writes PNG/CSV files and the HTML report."""

    def __init__(self, out: Path):
        self.out = out
        self.charts_dir = out / "charts"
        self.tables_dir = out / "tables"
        self.charts_dir.mkdir(parents=True, exist_ok=True)
        self.tables_dir.mkdir(parents=True, exist_ok=True)
        self.sections: list[tuple[str, list]] = []

    def section(self, title: str, intro: str = ""):
        self.sections.append((title, [("intro", intro)] if intro else []))

    def chart(self, fig, name: str, caption: str):
        path = self.charts_dir / f"{name}.png"
        fig.tight_layout()
        fig.savefig(path, bbox_inches="tight", facecolor="white")
        plt.close(fig)
        self.sections[-1][1].append(("chart", path, caption))
        print(f"  chart  {path.relative_to(self.out)}")

    def table(self, df: pd.DataFrame, name: str, caption: str, fmt: dict | None = None, html_rows: int = 40):
        path = self.tables_dir / f"{name}.csv"
        df.to_csv(path, index=False, encoding="utf-8")
        self.sections[-1][1].append(("table", df, caption, fmt or {}, html_rows, path))
        print(f"  table  {path.relative_to(self.out)}  ({len(df):,} rows)")

    def kpis(self, cards: list[tuple[str, str, str]]):
        self.sections[-1][1].append(("kpis", cards))

    def note(self, text_: str, kind: str = "note"):
        self.sections[-1][1].append(("note", text_, kind))

    def write_html(self, meta: str) -> Path:
        parts = [HTML_HEAD, f"<h1>Olist Command Center — Analytics Report</h1><p class='meta'>{html.escape(meta)}</p>"]
        parts.append("<nav>" + " · ".join(f"<a href='#s{i}'>{html.escape(t)}</a>" for i, (t, _) in enumerate(self.sections)) + "</nav>")
        for i, (title, items) in enumerate(self.sections):
            parts.append(f"<section id='s{i}'><h2>{html.escape(title)}</h2>")
            for item in items:
                kind = item[0]
                if kind == "intro":
                    parts.append(f"<p>{item[1]}</p>")
                elif kind == "note":
                    parts.append(f"<div class='{item[2]}'>{item[1]}</div>")
                elif kind == "kpis":
                    parts.append("<div class='kpis'>" + "".join(
                        f"<div class='kpi'><div class='k-label'>{html.escape(a)}</div><div class='k-value'>{html.escape(b)}</div>"
                        f"<div class='k-sub'>{html.escape(c)}</div></div>" for a, b, c in item[1]) + "</div>")
                elif kind == "chart":
                    b64 = base64.b64encode(item[1].read_bytes()).decode("ascii")
                    parts.append(f"<figure><img src='data:image/png;base64,{b64}' alt='{html.escape(item[2])}'>"
                                 f"<figcaption>{html.escape(item[2])}</figcaption></figure>")
                elif kind == "table":
                    df, caption, fmt, rows, path = item[1], item[2], item[3], item[4], item[5]
                    shown = df.head(rows).copy()
                    for col, f in fmt.items():
                        if col in shown:
                            shown[col] = shown[col].map(
                                lambda v, f=f: "" if pd.isna(v) else (f(v) if callable(f) else f.format(v)))
                    more = f" Showing {rows} of {len(df):,} rows; full table in tables/{path.name}." if len(df) > rows else \
                        f" CSV: tables/{path.name}."
                    table_html = shown.to_html(index=False, border=0, classes="tbl", na_rep="")
                    if "status" in shown.columns:
                        for s in ("PASS", "WARN", "FAIL"):
                            table_html = table_html.replace(f"<td>{s}</td>", f"<td class='st-{s}'>{s}</td>")
                    parts.append(f"<div class='tcap'>{html.escape(caption)}{html.escape(more)}</div>"
                                 f"<div class='twrap'>{table_html}</div>")
            parts.append("</section>")
        parts.append("</body></html>")
        path = self.out / "report.html"
        path.write_text("\n".join(parts), encoding="utf-8")
        return path


HTML_HEAD = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Olist Analytics Report</title>
<style>
body{font-family:Segoe UI,Helvetica,Arial,sans-serif;color:#1C2B33;max-width:1180px;margin:0 auto;padding:24px 20px 80px;line-height:1.45}
h1{font-size:26px;margin:0 0 4px}h2{font-size:20px;border-bottom:2px solid #1F4E5F;padding-bottom:4px;margin-top:44px}
.meta{color:#5b6b75;margin:0 0 12px}nav{font-size:14px;margin-bottom:8px}nav a{color:#1F4E5F;text-decoration:none}
figure{margin:18px 0}figure img{max-width:100%;border:1px solid #E6EAED}figcaption{font-size:13px;color:#5b6b75;margin-top:4px}
.kpis{display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:12px;margin:12px 0}
.kpi{background:#F3F5F6;border-radius:6px;padding:12px 14px}.k-label{font-size:13px;color:#5b6b75}
.k-value{font-size:26px;font-weight:600;color:#1F4E5F}.k-sub{font-size:12px;color:#5b6b75}
.twrap{overflow-x:auto}table.tbl{border-collapse:collapse;font-size:13px;margin:4px 0 18px;width:100%}
.tbl th{background:#1F4E5F;color:#fff;text-align:left;padding:6px 8px;white-space:nowrap}
.tbl td{padding:5px 8px;border-bottom:1px solid #E6EAED;white-space:nowrap}.tbl tr:nth-child(even) td{background:#FAFBFB}
.tcap{font-size:13px;color:#5b6b75;margin-top:14px}.st-PASS{background:#E5F4E4!important}.st-WARN{background:#F9EEDA!important}
.st-FAIL{background:#FBEBEB!important}.note{background:#F3F5F6;border-left:4px solid #1F4E5F;padding:10px 14px;margin:12px 0;font-size:14px}
.caveat{background:#FDF3EC;border-left:4px solid #C8553D;padding:10px 14px;margin:12px 0;font-size:14px}
</style></head><body>"""


# ------------------------------------------------------------------ sections
def overview(engine, rep: Report) -> dict:
    rep.section("1. Executive overview",
                "Headline KPIs over the whole dataset. Definitions: revenue = SUM(item price) on delivered orders "
                "(freight excluded); late = delivered after the estimated date-time, among delivered orders with a "
                "delivery date; review = order-level average; repeat = customers (customer_unique_id) with 2+ "
                "delivered orders.")
    k = q(engine, """
        SELECT COUNT(*) FILTER (WHERE is_delivered) AS delivered_orders,
               SUM(item_revenue) FILTER (WHERE is_delivered) AS revenue,
               SUM(freight_revenue) FILTER (WHERE is_delivered) AS freight,
               COUNT(*) FILTER (WHERE has_delivery_date) AS late_eligible,
               COUNT(*) FILTER (WHERE is_late) AS late_orders,
               AVG(review_score) AS avg_review,
               AVG(review_score) FILTER (WHERE is_late = FALSE) AS review_on_time,
               AVG(review_score) FILTER (WHERE is_late) AS review_late,
               MIN(purchase_date) AS first_purchase, MAX(purchase_date) AS last_purchase,
               COUNT(*) AS all_orders
        FROM analytics.v_order_delivery""").iloc[0]
    c = q(engine, "SELECT COUNT(*) AS customers, COUNT(*) FILTER (WHERE delivered_orders > 1) AS repeaters "
                  "FROM analytics.v_customer_spend").iloc[0]
    s = q(engine, "SELECT COUNT(*) AS sellers, COUNT(*) FILTER (WHERE orders_delivered > 0) AS active "
                  "FROM analytics.v_seller_report").iloc[0]
    rows = q(engine, "SELECT SUM(row_count) AS n FROM analytics.v_row_inventory WHERE layer = 'raw'").iloc[0]["n"]
    late = 100 * k.late_orders / k.late_eligible
    repeat = 100 * c.repeaters / c.customers
    rep.kpis([
        ("Delivered item revenue", brl(k.revenue), f"R${k.revenue:,.2f}; freight R${k.freight / 1e6:.2f}M extra"),
        ("Delivered orders", f"{int(k.delivered_orders):,}", f"AOV R${k.revenue / k.delivered_orders:,.2f}"),
        ("Late-delivery rate", f"{late:.2f}%", f"{int(k.late_orders):,} of {int(k.late_eligible):,} orders"),
        ("Average review score", f"{k.avg_review:.2f} / 5", f"on time {k.review_on_time:.2f} vs late {k.review_late:.2f}"),
        ("Customers", f"{int(c.customers):,}", "people with ≥1 delivered order"),
        ("Repeat-purchase rate", f"{repeat:.2f}%", f"{int(c.repeaters):,} customers with 2+ orders"),
        ("Sellers", f"{int(s.sellers):,}", f"{int(s.active):,} with a delivered sale"),
        ("Raw rows processed", f"{int(rows):,}", "9 source tables"),
    ])
    kpi_table = pd.DataFrame([
        ("Delivered item revenue (R$)", round(k.revenue, 2), "SUM(item price), delivered orders"),
        ("Freight on delivered orders (R$)", round(k.freight, 2), "SUM(freight_value), delivered orders"),
        ("Delivered orders", int(k.delivered_orders), "status = delivered"),
        ("Average order value (R$)", round(k.revenue / k.delivered_orders, 2), "revenue / delivered orders"),
        ("Late-delivery rate (%)", round(late, 2), "late / delivered with a delivery date"),
        ("On-time delivery rate (%)", round(100 - late, 2), "1 − late rate"),
        ("Average review score", round(k.avg_review, 3), "order-level average, orders with a review"),
        ("Customers (people)", int(c.customers), "customer_unique_id with ≥1 delivered order"),
        ("Repeat-purchase rate (%)", round(repeat, 2), "2+ delivered orders / customers"),
        ("Sellers", int(s.sellers), "all sellers"),
        ("Raw source rows", int(rows), "9 raw tables"),
    ], columns=["kpi", "value", "definition"])
    rep.table(kpi_table, "01_kpi_summary", "KPI summary.", {"value": num})

    m = q(engine, """
        SELECT purchase_month,
               COUNT(*) FILTER (WHERE is_delivered) AS delivered_orders,
               COALESCE(SUM(item_revenue) FILTER (WHERE is_delivered), 0) AS revenue,
               COUNT(*) FILTER (WHERE has_delivery_date) AS late_eligible,
               COUNT(*) FILTER (WHERE is_late) AS late_orders
        FROM analytics.v_order_delivery GROUP BY purchase_month ORDER BY purchase_month""")
    m = add_rates(m, "late_orders", "late_eligible")
    m["purchase_month"] = pd.to_datetime(m["purchase_month"])
    fig, ax = plt.subplots(figsize=(11, 4.6))
    ax.bar(m["purchase_month"], m["revenue"], width=24, color=MUTED, label="Delivered item revenue")
    brl_axis(ax)
    ax.set_ylabel("Revenue")
    ax2 = ax.twinx()
    ok = ~m["small_sample"]
    ax2.plot(m.loc[ok, "purchase_month"], m.loc[ok, "late_pct"], color=HIGHLIGHT, marker="o", lw=2, label="Late-delivery rate")
    ax2.set_ylabel("Late %", color=HIGHLIGHT)
    ax2.set_ylim(0, max(25, m.loc[ok, "late_pct"].max() * 1.15))
    ax2.grid(False)
    ax2.spines["right"].set_visible(True)
    peak = m.loc[ok].sort_values("late_pct").iloc[-1]
    ax2.annotate(f"{peak.purchase_month:%b %Y}: {peak.late_pct:.1f}%", (peak.purchase_month, peak.late_pct),
                 xytext=(10, 6), textcoords="offset points", color=HIGHLIGHT, fontsize=9)
    ax.set_title("Monthly delivered revenue and late-delivery rate (by purchase month)")
    h1, l1 = ax.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, loc="upper left")
    ax.xaxis.set_major_formatter(matplotlib.dates.DateFormatter("%b %y"))
    rep.chart(fig, "01_monthly_revenue_late_rate",
              f"Late rate hidden for months with fewer than {MIN_SAMPLE} eligible orders (late 2016, Sep–Oct 2018). "
              "Data thins out after Aug 2018 — a dataset boundary, not a business decline.")
    out = m.assign(purchase_month=m["purchase_month"].dt.strftime("%Y-%m"))
    rep.table(out[["purchase_month", "delivered_orders", "revenue", "late_eligible", "late_orders", "late_pct", "small_sample"]],
              "02_monthly_trend", "Monthly trend.", {"revenue": "{:,.0f}", "late_pct": "{:.2f}"})
    return {"late_pct": late, "first": k.first_purchase, "last": k.last_purchase, "repeat": repeat}


def logistics(engine, rep: Report, platform: float):
    rep.section("2. Logistics and delivery performance",
                "Late-delivery rate by customer geography, with 95% confidence intervals (Wilson) and sample sizes, "
                "so small states are not over-read.")
    reg = q(engine, """
        SELECT r.region, r.delivered_orders AS late_eligible, r.late_orders, r.late_pct AS view_late_pct,
               r.ratio_vs_platform, r.ratio_vs_rest,
               d.avg_actual_days, d.avg_estimated_days
        FROM analytics.v_region_late_rate r
        JOIN (SELECT region, AVG(actual_delivery_days) AS avg_actual_days, AVG(estimated_delivery_days) AS avg_estimated_days
              FROM analytics.v_order_delivery WHERE has_delivery_date GROUP BY region) d ON d.region = r.region""")
    reg = add_rates(reg, "late_orders", "late_eligible").sort_values("late_pct")
    fig, ax = plt.subplots(figsize=(9, 3.8))
    colors = [HIGHLIGHT if r == NORDESTE else ACCENT for r in reg["region"]]
    ax.barh(reg["region"], reg["late_pct"], color=colors,
            xerr=[reg["late_pct"] - reg["ci_low"], reg["ci_high"] - reg["late_pct"]], error_kw=dict(ecolor="#444", lw=1, capsize=3))
    for y, (v, n, ratio) in enumerate(zip(reg["late_pct"], reg["late_eligible"], reg["ratio_vs_platform"])):
        ax.text(reg["ci_high"].iloc[y] + 0.3, y, f"{v:.2f}%  ({ratio:.2f}× platform, n={int(n):,})", va="center", fontsize=9)
    ax.axvline(platform, ls=":", color="#333")
    ax.text(platform, len(reg) - 0.45, f" platform {platform:.2f}%", fontsize=9)
    ax.set_xlim(0, reg["ci_high"].max() * 1.75)
    ax.set_xlabel("Late-delivery rate (%)")
    ax.set_title("Late-delivery rate by customer region")
    rep.chart(fig, "02_late_rate_by_region", "Whiskers = 95% confidence interval. Ratio = region rate ÷ platform rate "
              "(platform includes the region).")
    rep.table(reg.sort_values("late_pct", ascending=False)[
        ["region", "late_eligible", "late_orders", "late_pct", "ci_low", "ci_high", "ratio_vs_platform", "ratio_vs_rest",
         "avg_actual_days", "avg_estimated_days"]], "03_region_delivery", "Delivery performance by region.",
        {"late_pct": "{:.2f}", "ci_low": "{:.2f}", "ci_high": "{:.2f}", "avg_actual_days": "{:.1f}", "avg_estimated_days": "{:.1f}"})

    st = q(engine, """
        SELECT s.customer_state AS state, s.region, s.delivered_orders AS late_eligible, s.late_orders,
               d.avg_actual_days, d.avg_estimated_days, d.avg_delay_days
        FROM analytics.v_state_late_rate s
        JOIN (SELECT customer_state, AVG(actual_delivery_days) AS avg_actual_days,
                     AVG(estimated_delivery_days) AS avg_estimated_days, AVG(delay_days) AS avg_delay_days
              FROM analytics.v_order_delivery WHERE has_delivery_date GROUP BY customer_state) d
          ON d.customer_state = s.customer_state""")
    st = add_rates(st, "late_orders", "late_eligible").sort_values("late_pct")
    fig, ax = plt.subplots(figsize=(10, 8.5))
    colors = [HIGHLIGHT if r == NORDESTE else ACCENT for r in st["region"]]
    alphas = [0.35 if s else 1.0 for s in st["small_sample"]]
    for y, (v, lo, hi, c, a) in enumerate(zip(st["late_pct"], st["ci_low"], st["ci_high"], colors, alphas)):
        ax.barh(y, v, color=c, alpha=a)
        ax.plot([lo, hi], [y, y], color="#555", lw=1, alpha=max(a, 0.6))
    ax.set_yticks(range(len(st)))
    ax.set_yticklabels([f"{s} (n={int(n):,})" for s, n in zip(st["state"], st["late_eligible"])], fontsize=8.5)
    ax.axvline(platform, ls=":", color="#333")
    ax.set_xlabel("Late-delivery rate (%)")
    ax.set_title("Late-delivery rate by customer state")
    ax.legend(handles=[plt.Rectangle((0, 0), 1, 1, color=HIGHLIGHT), plt.Rectangle((0, 0), 1, 1, color=ACCENT),
                       plt.Rectangle((0, 0), 1, 1, color=ACCENT, alpha=0.35), plt.Line2D([], [], ls=":", color="#333")],
              labels=["Nordeste", "Other regions", f"Small sample (n < {MIN_SAMPLE})", f"Platform {platform:.2f}%"],
              loc="lower right")
    rep.chart(fig, "03_late_rate_by_state", "Lines = 95% confidence interval. Faded bars have fewer than "
              f"{MIN_SAMPLE} eligible orders and should not be ranked.")
    above = st[(~st["small_sample"]) & (st["ci_low"] > platform)].sort_values("late_pct", ascending=False)
    rep.note("States whose whole 95% interval sits above the platform rate: " +
             ", ".join(f"<b>{r.state}</b> {r.late_pct:.1f}% (n={int(r.late_eligible):,})" for r in above.itertuples()) + ".")
    rep.table(st.sort_values("late_pct", ascending=False)[
        ["state", "region", "late_eligible", "late_orders", "late_pct", "ci_low", "ci_high", "small_sample",
         "avg_actual_days", "avg_estimated_days", "avg_delay_days"]], "04_state_delivery", "Delivery performance by state.",
        {"late_pct": "{:.2f}", "ci_low": "{:.2f}", "ci_high": "{:.2f}", "avg_actual_days": "{:.1f}",
         "avg_estimated_days": "{:.1f}", "avg_delay_days": "{:.1f}"})

    s2 = st.sort_values("avg_estimated_days")
    fig, ax = plt.subplots(figsize=(10, 8.5))
    for y, r in enumerate(s2.itertuples()):
        ax.plot([r.avg_actual_days, r.avg_estimated_days], [y, y], color="#CCD3D8", lw=3, zorder=1)
    ax.scatter(s2["avg_actual_days"], range(len(s2)), color=[HIGHLIGHT if r == NORDESTE else ACCENT for r in s2["region"]],
               s=40, zorder=2, label="Actual (average)")
    ax.scatter(s2["avg_estimated_days"], range(len(s2)), marker="|", s=160, color="#333", zorder=2, label="Estimated (average)")
    ax.set_yticks(range(len(s2)))
    ax.set_yticklabels(s2["state"], fontsize=8.5)
    ax.set_xlabel("Days from purchase to delivery")
    ax.set_title("Actual vs estimated delivery time by customer state")
    ax.legend(loc="lower right")
    rep.chart(fig, "04_actual_vs_estimated_days", "Gap between dot and tick = average buffer in the estimate. Dots in orange "
              "are Nordeste states. Delivered orders with a delivery date only.")

    dist = q(engine, """
        SELECT GREATEST(LEAST(FLOOR(delay_days)::int, 30), -45) AS bucket, COUNT(*) AS orders
        FROM analytics.v_order_delivery WHERE has_delivery_date GROUP BY 1 ORDER BY 1""")
    fig, ax = plt.subplots(figsize=(10, 3.8))
    ax.bar(dist["bucket"], dist["orders"], width=0.9, color=[HIGHLIGHT if b >= 0 else MUTED for b in dist["bucket"]])
    ax.axvline(-0.05, color="#333", lw=1)
    ax.set_xlabel("Days early (−) / late (+) versus the estimated delivery date")
    ax.set_ylabel("Orders")
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{v:,.0f}"))
    ax.set_title("How far deliveries land from the estimate")
    rep.chart(fig, "05_delay_distribution", "Tails clipped at −45 and +30 days. Most orders arrive well before the "
              "estimate. Bucket 0 = up to one day after the estimate (counted late under the strict rule).")

    origin = q(engine, """
        WITH seller_orders AS (
            SELECT DISTINCT foi.order_id, ds.seller_state
            FROM analytics.fact_order_items foi
            JOIN analytics.dim_seller ds ON ds.seller_key = foi.seller_key)
        SELECT so.seller_state,
               CASE WHEN od.region = 'Nordeste' THEN 'To Nordeste' ELSE 'To rest of Brazil' END AS destination,
               COUNT(*) AS late_eligible, COUNT(*) FILTER (WHERE od.is_late) AS late_orders
        FROM seller_orders so JOIN analytics.v_order_delivery od ON od.order_id = so.order_id
        WHERE od.has_delivery_date
        GROUP BY 1, 2""")
    origin = add_rates(origin, "late_orders", "late_eligible", min_n=30)
    ne = origin[origin["destination"] == "To Nordeste"]
    keep = ne[ne["late_eligible"] >= 30].sort_values("late_eligible", ascending=False)["seller_state"].head(10).tolist()
    pv = origin[origin["seller_state"].isin(keep)].pivot(index="seller_state", columns="destination", values="late_pct").loc[keep]
    nn = origin[origin["seller_state"].isin(keep)].pivot(index="seller_state", columns="destination", values="late_eligible").loc[keep]
    fig, ax = plt.subplots(figsize=(10, 4.2))
    x = range(len(keep))
    ax.bar([i - 0.2 for i in x], pv["To rest of Brazil"], width=0.4, color=MUTED, label="Shipping to rest of Brazil")
    ax.bar([i + 0.2 for i in x], pv["To Nordeste"], width=0.4, color=HIGHLIGHT, label="Shipping to Nordeste")
    for i, s in enumerate(keep):
        ax.text(i + 0.2, pv.loc[s, "To Nordeste"] + 0.4, f"n={int(nn.loc[s, 'To Nordeste']):,}", ha="center", fontsize=7.5)
    ax.set_xticks(list(x))
    ax.set_xticklabels([f"{s}\nsellers" for s in keep], fontsize=8.5)
    ax.set_ylabel("Late %")
    ax.set_title("Same seller states, different destinations: late rate by seller origin")
    ax.legend(loc="upper left")
    rep.chart(fig, "06_seller_origin_to_nordeste", "Seller-origin states with ≥30 delivered orders into Nordeste. An order "
              "with sellers from two states counts under both. Association only: route, carrier and product mix are not controlled.")
    rep.table(origin.sort_values(["destination", "late_eligible"], ascending=[True, False])[
        ["seller_state", "destination", "late_eligible", "late_orders", "late_pct", "ci_low", "ci_high", "small_sample"]],
        "05_seller_origin_by_destination", "Late rate by seller-origin state and destination (small_sample = n < 30).",
        {"late_pct": "{:.2f}", "ci_low": "{:.2f}", "ci_high": "{:.2f}"}, html_rows=30)


def sellers(engine, rep: Report):
    rep.section("3. Seller performance",
                "Sellers with ≥20 delivered orders are scored 0.5 × on-time rate + 0.5 × (average review ÷ 5) and split "
                "at the median of revenue and of score (analytics.v_seller_quadrant, KPI-consistent basis). Medians are "
                "relative to this platform, not absolute quality bars.")
    summ = q(engine, """
        SELECT quadrant, sellers, total_revenue, avg_on_time_pct, avg_review, median_revenue_threshold
        FROM analytics.v_seller_quadrant_summary WHERE basis = 'kpi_consistent' ORDER BY total_revenue DESC""")
    sel = q(engine, """
        SELECT seller_id, seller_state, seller_region, orders_delivered, revenue_delivered, on_time_pct, avg_review,
               performance_score, median_revenue, median_performance, quadrant
        FROM analytics.v_seller_report""")
    qual = sel[sel["median_revenue"].notna()]
    med_rev, med_perf = qual["median_revenue"].iloc[0], qual["median_performance"].iloc[0]

    fig, ax = plt.subplots(figsize=(10, 6))
    for quad, grp in qual.groupby("quadrant"):
        ax.scatter(grp["revenue_delivered"], grp["performance_score"], s=8 + grp["orders_delivered"] / 12,
                   color=QUADRANT_COLORS[quad], alpha=0.65, edgecolor="white", lw=0.4, label=f"{quad} ({len(grp)})")
    ax.set_xscale("log")
    ax.axvline(med_rev, ls=":", color="#333")
    ax.axhline(med_perf, ls=":", color="#333")
    ax.text(med_rev * 1.05, ax.get_ylim()[0] + 0.005, f"median revenue R${med_rev:,.0f}", fontsize=8.5)
    ax.text(qual["revenue_delivered"].min(), med_perf + 0.004, f"median score {med_perf:.3f}", fontsize=8.5)
    ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"R${v / 1e3:,.0f}K" if v >= 1e3 else f"R${v:,.0f}"))
    ax.set_xlabel("Delivered item revenue (log scale)")
    ax.set_ylabel("Performance score (0.5 on-time + 0.5 review/5)")
    ax.set_title(f"Seller revenue × performance quadrants ({len(qual):,} sellers with ≥20 delivered orders)")
    ax.legend(loc="lower left", fontsize=8.5, markerscale=1.5)
    rep.chart(fig, "07_seller_quadrants", "Bubble size = delivered orders. Orange = high revenue, below-median performance.")

    s = summ.sort_values("total_revenue")
    fig, ax = plt.subplots(figsize=(10, 3.6))
    ax.barh(s["quadrant"], s["total_revenue"], color=[QUADRANT_COLORS[x] for x in s["quadrant"]])
    for y, r in enumerate(s.itertuples()):
        ax.text(r.total_revenue, y, f"  {brl(r.total_revenue)} · {int(r.sellers)} sellers · on-time {r.avg_on_time_pct:.1f}% "
                f"· review {r.avg_review:.2f}", va="center", fontsize=9)
    ax.set_xlim(0, s["total_revenue"].max() * 1.9)
    brl_axis(ax, "x")
    ax.set_title("Delivered revenue by seller quadrant")
    rep.chart(fig, "08_revenue_by_quadrant", "The high-revenue, below-median-performance group holds the most revenue — "
              "revenue associated with the group, not revenue at risk or recoverable.")
    rep.table(summ, "06_seller_quadrant_summary", "Seller quadrant summary (KPI-consistent basis).",
              {"total_revenue": "{:,.2f}", "median_revenue_threshold": "{:,.2f}"})

    coach = qual[qual["quadrant"] == "High revenue, low performance"].sort_values("revenue_delivered", ascending=False)
    rep.note("Coaching candidates are a list for a pilot, not a verdict. On orders with several sellers (1.3% of "
             "orders) the order's on-time flag and review are shared by every seller on it.", "caveat")
    rep.table(coach[["seller_id", "seller_state", "orders_delivered", "revenue_delivered", "on_time_pct", "avg_review",
                     "performance_score"]], "07_coaching_candidates",
              f"Coaching candidates: {len(coach)} sellers, {brl(coach['revenue_delivered'].sum())} delivered revenue.",
              {"revenue_delivered": "{:,.0f}", "on_time_pct": "{:.1f}", "avg_review": "{:.2f}", "performance_score": "{:.3f}"},
              html_rows=25)
    by_state = (qual.groupby(["seller_state", "quadrant"]).size().unstack(fill_value=0)
                .assign(total=lambda d: d.sum(axis=1)).sort_values("total", ascending=False).reset_index())
    rep.table(by_state, "08_quadrant_by_seller_state", "Qualifying sellers per quadrant, by seller state.", html_rows=15)


def customers(engine, rep: Report, platform_repeat: float):
    rep.section("4. Customer retention",
                "Customers are people (customer_unique_id). Lifetime-spend tiers: top 5% ≥ R$420 (≈ 95th percentile), "
                "mid R$90–420, low < R$90 of delivered item spend.")
    tiers = q(engine, "SELECT * FROM analytics.v_customer_spend_tier ORDER BY spend_tier")
    first = q(engine, "SELECT * FROM analytics.v_repeat_by_first_order_tier ORDER BY first_order_tier")
    names = {"1_high_top5pct": "Top 5%\n(≥ R$420)", "2_mid": "Mid\n(R$90–420)", "3_low": "Low\n(< R$90)",
             "1_first_order_ge_420": "Top 5%\n(≥ R$420)", "2_first_order_90_420": "Mid\n(R$90–420)",
             "3_first_order_lt_90": "Low\n(< R$90)"}
    t = tiers.assign(label=tiers["spend_tier"].map(names))
    f = first.assign(label=first["first_order_tier"].map(names))

    fig, ax = plt.subplots(figsize=(8, 4))
    x = range(len(t))
    ax.bar([i - 0.2 for i in x], t["pct_customers"], width=0.4, color=MUTED, label="% of customers")
    ax.bar([i + 0.2 for i in x], t["pct_revenue"], width=0.4, color=ACCENT, label="% of revenue")
    for i, (a, b) in enumerate(zip(t["pct_customers"], t["pct_revenue"])):
        ax.text(i - 0.2, a + 1, f"{a:.1f}%", ha="center", fontsize=9)
        ax.text(i + 0.2, b + 1, f"{b:.1f}%", ha="center", fontsize=9)
    ax.set_xticks(list(x))
    ax.set_xticklabels(t["label"])
    ax.set_ylabel("%")
    ax.set_title("Customers and revenue by lifetime-spend tier")
    ax.legend()
    rep.chart(fig, "09_spend_tiers", "The top 5% of customers by lifetime spend account for about 29% of delivered revenue.")

    fig, ax = plt.subplots(figsize=(8, 4))
    ax.bar([i - 0.2 for i in x], t["repeat_rate_pct"], width=0.4, color=MUTED, label="Grouped by lifetime spend (mechanical)")
    ax.bar([i + 0.2 for i in x], f["repeat_rate_pct"], width=0.4, color=ACCENT, label="Grouped by first-order value")
    for i, (a, b) in enumerate(zip(t["repeat_rate_pct"], f["repeat_rate_pct"])):
        ax.text(i - 0.2, a + 0.15, f"{a:.2f}%", ha="center", fontsize=9)
        ax.text(i + 0.2, b + 0.15, f"{b:.2f}%", ha="center", fontsize=9)
    ax.axhline(platform_repeat, ls=":", color="#333")
    ax.text(-0.45, platform_repeat + 0.15, f"platform {platform_repeat:.2f}%", fontsize=8.5, ha="left")
    ax.set_xticks(list(x))
    ax.set_xticklabels(t["label"])
    ax.set_ylabel("Repeat-purchase rate (%)")
    ax.set_title("Repeat rate depends on how customers are grouped")
    ax.legend(loc="upper right", fontsize=8.5)
    rep.chart(fig, "10_repeat_rate_two_segmentations", "Same customers, two groupings. Lifetime spend rises with every "
              "extra order, so repeat buyers land in the top tier by construction.")
    rep.note("Read the lifetime-spend gradient as descriptive, not causal. Grouped by the value of their first order — "
             "before any repeat could happen — high spenders repeat slightly less often than low spenders. Neither view "
             "shows that a retention campaign would work; that needs a controlled test.", "caveat")
    rep.table(tiers, "09_customer_spend_tiers", "Customer lifetime-spend tiers.", {"revenue": "{:,.0f}"})
    rep.table(first, "10_repeat_by_first_order_tier", "Repeat rate by first-order-value tier.")


def categories(engine, rep: Report, platform: float):
    rep.section("5. Product and category analysis",
                "Delivered orders only. An order with items from two categories counts once in each, with only that "
                "category's item price and freight.")
    cat = q(engine, """
        SELECT l.category, COUNT(*) AS orders, SUM(l.items) AS items, SUM(l.revenue) AS revenue, SUM(l.freight) AS freight,
               AVG(od.review_score) AS avg_review, COUNT(od.review_score) AS reviewed_orders,
               COUNT(*) FILTER (WHERE od.has_delivery_date) AS late_eligible,
               COUNT(*) FILTER (WHERE od.is_late) AS late_orders
        FROM analytics.v_order_category_lines l
        JOIN analytics.v_order_delivery od ON od.order_id = l.order_id
        WHERE od.is_delivered
        GROUP BY l.category""")
    cat = add_rates(cat, "late_orders", "late_eligible", min_n=300)
    cat["freight_pct"] = 100 * cat["freight"] / cat["revenue"]
    cat["low_volume"] = cat["orders"] < 300

    top = cat.sort_values("revenue", ascending=False).head(15).sort_values("revenue")
    fig, ax = plt.subplots(figsize=(10, 5.5))
    ax.barh(top["category"], top["revenue"], color=[HIGHLIGHT if c == "office_furniture" else ACCENT for c in top["category"]])
    for y, r in enumerate(top.itertuples()):
        ax.text(r.revenue, y, f"  {brl(r.revenue)} · {int(r.orders):,} orders", va="center", fontsize=8.5)
    ax.set_xlim(0, top["revenue"].max() * 1.45)
    brl_axis(ax, "x")
    ax.set_title("Top 15 categories by delivered item revenue")
    rep.chart(fig, "11_top_categories_revenue", "office_furniture highlighted (see the next chart).")

    big = cat[~cat["low_volume"]]
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.scatter(big["late_pct"], big["avg_review"], s=big["orders"] / 15, alpha=0.55,
               color=[HIGHLIGHT if c == "office_furniture" else ACCENT for c in big["category"]], edgecolor="white")
    for r in big.itertuples():
        if r.category == "office_furniture" or r.orders > 5000 or r.avg_review < 3.9:
            ax.annotate(r.category, (r.late_pct, r.avg_review), xytext=(5, 3), textcoords="offset points", fontsize=8)
    ax.axvline(platform, ls=":", color="#333")
    ax.set_xlabel("Late-delivery rate (%)")
    ax.set_ylabel("Average review score")
    ax.set_title(f"Late rate vs review score by category ({len(big)} categories with ≥ 300 orders)")
    rep.chart(fig, "12_category_late_vs_review", "Bubble size = delivered orders. Dotted line = platform late rate. "
              "Categories with fewer than 300 orders are left out to avoid over-reading noise.")

    fb = cat.sort_values("revenue", ascending=False).head(20).sort_values("freight_pct")
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.barh(fb["category"], fb["freight_pct"], color=[HIGHLIGHT if c == "office_furniture" else MUTED for c in fb["category"]])
    for y, v in enumerate(fb["freight_pct"]):
        ax.text(v, y, f" {v:.1f}%", va="center", fontsize=8.5)
    ax.set_xlabel("Freight as % of item revenue")
    ax.set_title("Freight burden, top 20 categories by revenue")
    rep.chart(fig, "13_freight_share_by_category", "Freight charged to customers relative to item price.")
    rep.table(cat.sort_values("revenue", ascending=False)[
        ["category", "orders", "items", "revenue", "freight", "freight_pct", "avg_review", "late_eligible", "late_orders",
         "late_pct", "ci_low", "ci_high", "low_volume"]], "11_category_performance",
        "Category performance (low_volume = fewer than 300 delivered orders).",
        {"revenue": "{:,.0f}", "freight": "{:,.0f}", "freight_pct": "{:.1f}", "avg_review": "{:.2f}",
         "late_pct": "{:.2f}", "ci_low": "{:.2f}", "ci_high": "{:.2f}"}, html_rows=30)


def payments(engine, rep: Report):
    rep.section("6. Payments", "All payment rows (analytics.fact_payments), all order statuses.")
    pay = q(engine, """
        SELECT payment_type, COUNT(*) AS payment_rows, COUNT(DISTINCT order_id) AS orders,
               SUM(payment_value) AS payment_value, AVG(payment_installments) AS avg_installments
        FROM analytics.fact_payments GROUP BY payment_type ORDER BY payment_value DESC""")
    pay["share_of_value_pct"] = 100 * pay["payment_value"] / pay["payment_value"].sum()
    p = pay.sort_values("payment_value")
    fig, ax = plt.subplots(figsize=(9, 3.2))
    ax.barh(p["payment_type"], p["payment_value"], color=ACCENT)
    for y, r in enumerate(p.itertuples()):
        ax.text(r.payment_value, y, f"  {r.share_of_value_pct:.1f}% · {int(r.payment_rows):,} rows", va="center", fontsize=9)
    ax.set_xlim(0, p["payment_value"].max() * 1.35)
    brl_axis(ax, "x")
    ax.set_title("Payment value by payment type")
    rep.chart(fig, "14_payment_mix", "Payment value includes freight and covers all statuses, so it is larger than "
              "delivered item revenue; it is not used as the revenue KPI.")
    rep.table(pay, "12_payment_mix", "Payment mix.", {"payment_value": "{:,.2f}", "avg_installments": "{:.2f}",
                                                     "share_of_value_pct": "{:.2f}"})


def data_quality(engine, rep: Report):
    rep.section("7. Data quality and pipeline health",
                "Every check is measured live by analytics.v_data_quality_checks and compared with the documented baseline: "
                "PASS = as required, WARN = documented exception that is retained and handled, FAIL = needs investigation.")
    build = q(engine, "SELECT built_at, reconciliation_passed, completed_at FROM analytics.pipeline_run_info").iloc[0]
    checks = q(engine, "SELECT check_id, category, check_name, observed FROM analytics.v_data_quality_checks")
    res = [dq_status(c, o) for c, o in zip(checks["check_id"], checks["observed"])]
    checks["status"] = [r[0] for r in res]
    checks["explanation"] = [r[1] for r in res]
    rows = q(engine, "SELECT layer, table_name, row_count FROM analytics.v_row_inventory")
    rows["expected"] = [config.EXPECTED_RAW_TABLE_COUNTS.get(f"raw.{t}") if layer == "raw" else None
                        for layer, t in zip(rows["layer"], rows["table_name"])]
    rows["status"] = ["PASS" if layer != "raw" else ("PASS" if exp is not None and int(n) == int(exp) else "FAIL")
                      for layer, n, exp in zip(rows["layer"], rows["row_count"], rows["expected"])]
    all_status = pd.Series(list(checks["status"]) + list(rows.loc[rows["layer"] == "raw", "status"]))
    counts = {s: int((all_status == s).sum()) for s in ("PASS", "WARN", "FAIL")}
    rep.kpis([
        ("Checks passed", str(counts["PASS"]), "including 9 source row counts"),
        ("Warnings", str(counts["WARN"]), "documented, handled exceptions"),
        ("Failed", str(counts["FAIL"]), "must be 0 to trust the figures"),
        ("Reconciliation", "Passed" if build.reconciliation_passed else "NOT passed", "revenue and payments to the cent"),
        ("Last build", f"{pd.Timestamp(build.built_at):%Y-%m-%d %H:%M} UTC",
         "pipeline completed" if pd.notna(build.completed_at) else "pipeline did NOT complete"),
    ])

    order = {"FAIL": 0, "WARN": 1, "PASS": 2}
    by_cat = checks.groupby(["category", "status"]).size().unstack(fill_value=0).reindex(columns=["PASS", "WARN", "FAIL"], fill_value=0)
    fig, ax = plt.subplots(figsize=(9, 3.4))
    left = pd.Series(0, index=by_cat.index)
    for s, colr in (("PASS", "#7FB77E"), ("WARN", "#E3B35C"), ("FAIL", HIGHLIGHT)):
        ax.barh(by_cat.index, by_cat[s], left=left, color=colr, label=s)
        left += by_cat[s]
    ax.set_xlabel("Number of checks")
    ax.set_title("Data-quality checks by category and status")
    ax.legend(loc="lower right")
    ax.xaxis.set_major_locator(mticker.MaxNLocator(integer=True))
    rep.chart(fig, "15_data_quality_status", "WARN = known exception documented in docs/data_quality.md and handled downstream.")
    checks["_o"] = checks["status"].map(order)
    rep.table(checks.sort_values(["_o", "category"]).drop(columns="_o"), "13_data_quality_checks",
              "Data-quality checks with status.", {"observed": num})
    rep.table(rows, "14_row_inventory", "Row counts: raw tables vs the source manifest, and analytics tables.",
              {"row_count": "{:,.0f}", "expected": "{:,.0f}"})
    return counts


# ------------------------------------------------------------------ main
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Generate all Olist charts, tables and an HTML report.")
    ap.add_argument("--out", default=str(config.PROJECT_ROOT / "reports"), help="output folder (default: reports/)")
    args = ap.parse_args(argv)
    out = Path(args.out)
    setup_style()
    try:
        engine = connect(config.DB_URL)
        print(f"Reading analytics views from {masked(engine.url)} (read-only)")
        rep = Report(out)
        ov = overview(engine, rep)
        logistics(engine, rep, ov["late_pct"])
        sellers(engine, rep)
        customers(engine, rep, ov["repeat"])
        categories(engine, rep, ov["late_pct"])
        payments(engine, rep)
        counts = data_quality(engine, rep)
        meta = (f"Orders purchased {pd.Timestamp(ov['first']):%d %b %Y} – {pd.Timestamp(ov['last']):%d %b %Y}. "
                f"Generated {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC from the analytics schema "
                "(scripts/generate_visuals.py). Associations only — no causal claims.")
        path = rep.write_html(meta)
        engine.dispose()
    except ReportError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    print(f"\nReport: {path}")
    print(f"Charts: {len(list(rep.charts_dir.glob('*.png')))}   Tables: {len(list(rep.tables_dir.glob('*.csv')))}   "
          f"Data-quality: {counts['PASS']} pass / {counts['WARN']} warn / {counts['FAIL']} fail")
    return 0


if __name__ == "__main__":
    sys.exit(main())
