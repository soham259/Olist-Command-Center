-- Business findings layer (schema: analytics) — ADDED DURING THE 2026-10 AUDIT
--
-- Why this file exists: the headline findings in README.md, docs/ and the
-- business-case document (Nordeste late-delivery gap, the seller revenue x
-- performance quadrant, customer spend tiers) were reported in the docs but
-- the SQL that produced them was not in the repository. This file implements
-- each documented methodology as a VIEW, so that:
--   * the pipeline builds them on every run (run after 06_star_schema.sql,
--     because 06 drops and recreates the analytics schema);
--   * tests/test_business_findings.py checks them against the live database;
--   * every figure quoted in the docs traces to exactly one query.
--
-- Shared definitions (from docs/kpi_dictionary.md):
--   Revenue   = SUM(order_items.price) on order_status = 'delivered'
--   Late      = delivered order, non-null delivery date, and
--               order_delivered_customer_date > order_estimated_delivery_date
--               (timestamp comparison; the estimate is stored at 00:00, so a
--               delivery during the estimated day itself counts as late —
--               see docs/kpi_dictionary.md, "On-Time Delivery Rate")
--   Review    = order-level average of review_score (handles multi-review orders)
--
-- Read-only with respect to raw data: views only, nothing is modified.

-- ============================================================
-- 1. Regional late-delivery rates (Nordeste vs platform)
-- Grain: one row per customer state. Customer state is taken from
-- raw.customers (the state attached to THAT order), not dim_customer
-- (which keeps one modal state per person).
-- ============================================================
-- State -> IBGE macro-region lookup (27 federative units). Defined once and
-- reused by every regional view and by the report.
CREATE OR REPLACE VIEW analytics.v_state_region AS
SELECT state, region FROM (VALUES
    ('MA','Nordeste'),('PI','Nordeste'),('CE','Nordeste'),('RN','Nordeste'),('PB','Nordeste'),
    ('PE','Nordeste'),('AL','Nordeste'),('SE','Nordeste'),('BA','Nordeste'),
    ('AC','Norte'),('AM','Norte'),('AP','Norte'),('PA','Norte'),('RO','Norte'),('RR','Norte'),('TO','Norte'),
    ('DF','Centro-Oeste'),('GO','Centro-Oeste'),('MT','Centro-Oeste'),('MS','Centro-Oeste'),
    ('ES','Sudeste'),('MG','Sudeste'),('RJ','Sudeste'),('SP','Sudeste'),
    ('PR','Sul'),('RS','Sul'),('SC','Sul')
) AS t(state, region);

CREATE OR REPLACE VIEW analytics.v_state_late_rate AS
WITH delivered AS (
    SELECT
        c.customer_state,
        (o.order_delivered_customer_date > o.order_estimated_delivery_date) AS is_late
    FROM raw.orders o
    JOIN raw.customers c ON o.customer_id = c.customer_id
    WHERE o.order_status = 'delivered'
      AND o.order_delivered_customer_date IS NOT NULL
)
SELECT
    d.customer_state,
    sr.region,
    COUNT(*) AS delivered_orders,
    COUNT(*) FILTER (WHERE d.is_late) AS late_orders,
    ROUND(100.0 * COUNT(*) FILTER (WHERE d.is_late) / COUNT(*), 2) AS late_pct
FROM delivered d
LEFT JOIN analytics.v_state_region sr ON sr.state = d.customer_state
GROUP BY d.customer_state, sr.region;

-- Region-level summary, with BOTH comparison baselines stated explicitly:
--   ratio_vs_platform : region rate / platform rate (platform INCLUDES the region)
--   ratio_vs_rest     : region rate / rate of all OTHER regions combined
CREATE OR REPLACE VIEW analytics.v_region_late_rate AS
WITH r AS (
    SELECT region, SUM(delivered_orders) AS n, SUM(late_orders) AS late
    FROM analytics.v_state_late_rate GROUP BY region
),
p AS (SELECT SUM(n) AS n, SUM(late) AS late FROM r)
SELECT
    r.region,
    r.n AS delivered_orders,
    r.late AS late_orders,
    ROUND(100.0 * r.late / r.n, 2) AS late_pct,
    ROUND(100.0 * p.late / p.n, 2) AS platform_late_pct,
    ROUND((r.late::numeric / r.n) / (p.late::numeric / p.n), 2) AS ratio_vs_platform,
    ROUND((r.late::numeric / r.n) / ((p.late - r.late)::numeric / (p.n - r.n)), 2) AS ratio_vs_rest
FROM r CROSS JOIN p;

-- ============================================================
-- 2. Seller scorecard and revenue x performance quadrant
-- Methodology (docs/seller_and_category_analysis.md):
--   * volume floor: >= 20 orders
--   * performance score = 0.5 * on_time_rate + 0.5 * (avg_review / 5)
--   * quadrant = median split on revenue and on performance score,
--     among qualifying sellers only
-- Grain of v_seller_scorecard: one row per seller.
-- An order can contain items from several sellers (1.3% of orders); each
-- seller is credited only with its OWN item prices, so revenue is never
-- double-counted, while that order's on-time flag/review is attributed to
-- every seller on it (documented limitation).
-- ============================================================
CREATE OR REPLACE VIEW analytics.v_seller_scorecard AS
WITH seller_order AS (
    SELECT
        oi.seller_id,
        o.order_id,
        o.order_status,
        SUM(oi.price) AS seller_item_revenue
    FROM raw.order_items oi
    JOIN raw.orders o ON oi.order_id = o.order_id
    GROUP BY oi.seller_id, o.order_id, o.order_status
)
SELECT
    so.seller_id,
    COUNT(*) AS orders_all_status,
    COUNT(*) FILTER (WHERE so.order_status = 'delivered') AS orders_delivered,
    SUM(so.seller_item_revenue) FILTER (WHERE so.order_status = 'delivered') AS revenue_delivered,
    SUM(so.seller_item_revenue) AS revenue_all_status,
    100.0 * AVG(fo.is_on_time::int) FILTER (WHERE fo.is_on_time IS NOT NULL) AS on_time_pct,
    AVG(fo.review_score) FILTER (WHERE so.order_status = 'delivered') AS avg_review
FROM seller_order so
JOIN analytics.fact_orders fo ON so.order_id = fo.order_id
GROUP BY so.seller_id;

-- Two variants, labelled in the `basis` column:
--   'kpi_consistent' (PRIMARY): floor on delivered orders, revenue on delivered
--       orders — consistent with the KPI dictionary's Revenue definition.
--   'as_originally_documented' (SENSITIVITY): floor on orders of any status
--       and revenue summed over all statuses. This is the only variant found
--       during the audit that reproduces the documented intermediate figures
--       exactly (818 qualifying sellers, median revenue R$6,408), which shows
--       the original analysis did not apply the delivered-only filter here.
CREATE OR REPLACE VIEW analytics.v_seller_quadrant AS
WITH base AS (
    SELECT 'kpi_consistent' AS basis, seller_id, revenue_delivered AS revenue,
           on_time_pct, avg_review
    FROM analytics.v_seller_scorecard WHERE orders_delivered >= 20
    UNION ALL
    SELECT 'as_originally_documented', seller_id, revenue_all_status,
           on_time_pct, avg_review
    FROM analytics.v_seller_scorecard WHERE orders_all_status >= 20
),
scored AS (
    SELECT *, 0.5 * on_time_pct / 100 + 0.5 * avg_review / 5 AS performance_score
    FROM base
    WHERE on_time_pct IS NOT NULL AND avg_review IS NOT NULL
),
medians AS (
    SELECT basis,
           PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY revenue) AS median_revenue,
           PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY performance_score) AS median_performance
    FROM scored GROUP BY basis
)
SELECT
    s.basis, s.seller_id, s.revenue, s.on_time_pct, s.avg_review, s.performance_score,
    m.median_revenue, m.median_performance,
    CASE WHEN s.revenue >= m.median_revenue THEN 'High revenue' ELSE 'Low revenue' END
      || ', ' ||
    CASE WHEN s.performance_score >= m.median_performance THEN 'high performance' ELSE 'low performance' END
      AS quadrant
FROM scored s JOIN medians m ON s.basis = m.basis;

CREATE OR REPLACE VIEW analytics.v_seller_quadrant_summary AS
SELECT
    basis, quadrant,
    COUNT(*) AS sellers,
    ROUND(SUM(revenue), 2) AS total_revenue,
    ROUND(AVG(on_time_pct), 1) AS avg_on_time_pct,
    ROUND(AVG(avg_review), 2) AS avg_review,
    ROUND(MAX(median_revenue)::numeric, 2) AS median_revenue_threshold
FROM analytics.v_seller_quadrant
GROUP BY basis, quadrant;

-- ============================================================
-- 3. Customer spend tiers and repeat-purchase rate
-- Grain: one row per PERSON (customer_unique_id), delivered orders only.
-- Thresholds from docs/customer_analysis.md: high >= R$420 (≈ the 95th
-- percentile of lifetime spend, R$419.81), mid R$90–420, low < R$90.
-- Repeat customer = 2+ distinct delivered orders.
--
-- IMPORTANT CAVEAT (found during the audit): tiers are based on LIFETIME
-- (summed) spend, so customers with several orders mechanically accumulate
-- higher spend. v_repeat_by_first_order_tier re-cuts the same customers by the
-- value of their FIRST order to show how much of the gradient is mechanical.
-- ============================================================
CREATE OR REPLACE VIEW analytics.v_customer_spend AS
SELECT
    c.customer_unique_id,
    COUNT(DISTINCT o.order_id) AS delivered_orders,
    SUM(oi.price) AS lifetime_spend
FROM raw.orders o
JOIN raw.customers c ON o.customer_id = c.customer_id
JOIN raw.order_items oi ON o.order_id = oi.order_id
WHERE o.order_status = 'delivered'
GROUP BY c.customer_unique_id;

CREATE OR REPLACE VIEW analytics.v_customer_spend_tier AS
WITH t AS (
    SELECT *,
        CASE WHEN lifetime_spend >= 420 THEN '1_high_top5pct'
             WHEN lifetime_spend >= 90  THEN '2_mid'
             ELSE '3_low' END AS spend_tier
    FROM analytics.v_customer_spend
)
SELECT
    spend_tier,
    COUNT(*) AS customers,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1) AS pct_customers,
    ROUND(SUM(lifetime_spend), 2) AS revenue,
    ROUND(100.0 * SUM(lifetime_spend) / SUM(SUM(lifetime_spend)) OVER (), 1) AS pct_revenue,
    COUNT(*) FILTER (WHERE delivered_orders > 1) AS repeat_customers,
    ROUND(100.0 * COUNT(*) FILTER (WHERE delivered_orders > 1) / COUNT(*), 2) AS repeat_rate_pct
FROM t
GROUP BY spend_tier;

CREATE OR REPLACE VIEW analytics.v_repeat_by_first_order_tier AS
WITH person_orders AS (
    SELECT c.customer_unique_id, o.order_id, o.order_purchase_timestamp,
           SUM(oi.price) AS order_value
    FROM raw.orders o
    JOIN raw.customers c ON o.customer_id = c.customer_id
    JOIN raw.order_items oi ON o.order_id = oi.order_id
    WHERE o.order_status = 'delivered'
    GROUP BY c.customer_unique_id, o.order_id, o.order_purchase_timestamp
),
ranked AS (
    SELECT *,
        COUNT(*) OVER (PARTITION BY customer_unique_id) AS n_orders,
        ROW_NUMBER() OVER (PARTITION BY customer_unique_id
                           ORDER BY order_purchase_timestamp, order_id) AS rn
    FROM person_orders
)
SELECT
    CASE WHEN order_value >= 420 THEN '1_first_order_ge_420'
         WHEN order_value >= 90  THEN '2_first_order_90_420'
         ELSE '3_first_order_lt_90' END AS first_order_tier,
    COUNT(*) AS customers,
    ROUND(100.0 * COUNT(*) FILTER (WHERE n_orders > 1) / COUNT(*), 2) AS repeat_rate_pct
FROM ranked
WHERE rn = 1
GROUP BY 1;

-- ============================================================
-- 4. Row-count inventory (what "rows processed" actually means)
-- ============================================================
CREATE OR REPLACE VIEW analytics.v_row_inventory AS
SELECT 'raw' AS layer, 'customers' AS table_name, COUNT(*) AS row_count FROM raw.customers
UNION ALL SELECT 'raw', 'orders', COUNT(*) FROM raw.orders
UNION ALL SELECT 'raw', 'order_items', COUNT(*) FROM raw.order_items
UNION ALL SELECT 'raw', 'payments', COUNT(*) FROM raw.payments
UNION ALL SELECT 'raw', 'reviews', COUNT(*) FROM raw.reviews
UNION ALL SELECT 'raw', 'products', COUNT(*) FROM raw.products
UNION ALL SELECT 'raw', 'sellers', COUNT(*) FROM raw.sellers
UNION ALL SELECT 'raw', 'geolocation', COUNT(*) FROM raw.geolocation
UNION ALL SELECT 'raw', 'category_translation', COUNT(*) FROM raw.category_translation
UNION ALL SELECT 'analytics', 'dim_date', COUNT(*) FROM analytics.dim_date
UNION ALL SELECT 'analytics', 'dim_customer', COUNT(*) FROM analytics.dim_customer
UNION ALL SELECT 'analytics', 'dim_product', COUNT(*) FROM analytics.dim_product
UNION ALL SELECT 'analytics', 'dim_seller', COUNT(*) FROM analytics.dim_seller
UNION ALL SELECT 'analytics', 'dim_geography', COUNT(*) FROM analytics.dim_geography
UNION ALL SELECT 'analytics', 'fact_order_items', COUNT(*) FROM analytics.fact_order_items
UNION ALL SELECT 'analytics', 'fact_orders', COUNT(*) FROM analytics.fact_orders
UNION ALL SELECT 'analytics', 'fact_payments', COUNT(*) FROM analytics.fact_payments;
