-- Reporting layer (schema: analytics)
--
-- Views read by scripts/generate_visuals.py (the charts, tables and HTML
-- report). The report queries ONLY the analytics schema, and every metric it
-- shows is either one of these views or a plain aggregation of them, so no
-- business metric is calculated twice in two different ways:
--   * late / on-time  -> analytics.fact_orders.is_on_time (same rule as the
--                        KPI dictionary, v_state_late_rate, v_region_late_rate)
--   * revenue         -> analytics.fact_orders.item_revenue / fact_order_items.price
--   * review score    -> analytics.fact_orders.review_score (order-level average)
--   * seller quadrant -> analytics.v_seller_quadrant (basis = 'kpi_consistent')
--   * customer tiers  -> analytics.v_customer_spend_tier / v_repeat_by_first_order_tier
--
-- Must run after 08_business_findings.sql (it reuses v_state_region,
-- v_seller_scorecard and v_seller_quadrant). Views only, plus one small
-- metadata table (pipeline_run_info); nothing in raw is modified.

-- ============================================================
-- 1. Order-level delivery and revenue detail
-- Grain: one row per order (all 99,441 orders; filter on is_delivered).
-- customer_state = the state on THAT order (raw.customers), as in
-- v_state_late_rate, so regional figures in the report reconcile with it.
-- is_late is NULL unless the order is delivered with a delivery date
-- (the KPI dictionary's eligible population).
-- ============================================================
CREATE OR REPLACE VIEW analytics.v_order_delivery AS
SELECT
    fo.order_id,
    fo.order_status,
    o.order_purchase_timestamp::date                      AS purchase_date,
    DATE_TRUNC('month', o.order_purchase_timestamp)::date AS purchase_month,
    c.customer_state,
    sr.region,
    fo.is_delivered,
    fo.is_on_time IS NOT NULL                             AS has_delivery_date,
    NOT fo.is_on_time                                     AS is_late,
    fo.n_items,
    fo.item_revenue,
    fo.freight_revenue,
    fo.review_score,
    ROUND((EXTRACT(EPOCH FROM (o.order_delivered_customer_date - o.order_purchase_timestamp)) / 86400)::numeric, 2)
                                                          AS actual_delivery_days,
    ROUND((EXTRACT(EPOCH FROM (o.order_estimated_delivery_date - o.order_purchase_timestamp)) / 86400)::numeric, 2)
                                                          AS estimated_delivery_days,
    fo.delay_days
FROM analytics.fact_orders fo
JOIN raw.orders o     ON o.order_id = fo.order_id
JOIN raw.customers c  ON c.customer_id = o.customer_id
LEFT JOIN analytics.v_state_region sr ON sr.state = c.customer_state;

-- ============================================================
-- 2. Order x category lines (for category analysis with filters)
-- Grain: one row per (order, category). An order containing two categories
-- appears once under each, with only that category's items' price/freight,
-- so summing revenue across categories never double counts.
-- ============================================================
CREATE OR REPLACE VIEW analytics.v_order_category_lines AS
SELECT
    foi.order_id,
    dp.category_name_en       AS category,
    COUNT(*)                  AS items,
    SUM(foi.price)            AS revenue,
    SUM(foi.freight_value)    AS freight
FROM analytics.fact_order_items foi
JOIN analytics.dim_product dp ON dp.product_key = foi.product_key
GROUP BY foi.order_id, dp.category_name_en;

-- ============================================================
-- 3. Seller view for reporting
-- Grain: one row per seller (all 3,095). quadrant comes from
-- v_seller_quadrant on the KPI-consistent basis; sellers below the
-- 20-delivered-order volume floor are labelled rather than dropped.
-- ============================================================
CREATE OR REPLACE VIEW analytics.v_seller_report AS
SELECT
    ds.seller_id,
    ds.seller_state,
    sr.region                                    AS seller_region,
    COALESCE(sc.orders_delivered, 0)             AS orders_delivered,
    COALESCE(sc.orders_all_status, 0)            AS orders_all_status,
    COALESCE(sc.revenue_delivered, 0)            AS revenue_delivered,
    sc.on_time_pct,
    sc.avg_review,
    q.performance_score,
    q.median_revenue,
    q.median_performance,
    COALESCE(q.quadrant,
             CASE WHEN COALESCE(sc.orders_delivered, 0) < 20
                  THEN 'Below volume floor (<20 delivered orders)'
                  ELSE 'Not classified (missing on-time or review data)' END) AS quadrant
FROM analytics.dim_seller ds
LEFT JOIN analytics.v_seller_scorecard sc ON sc.seller_id = ds.seller_id
LEFT JOIN analytics.v_seller_quadrant q   ON q.seller_id = ds.seller_id AND q.basis = 'kpi_consistent'
LEFT JOIN analytics.v_state_region sr     ON sr.state = ds.seller_state;

-- ============================================================
-- 4. Data-quality and pipeline-health checks
-- One row per check with its OBSERVED value only. Pass / warning / fail
-- status is decided in scripts/generate_visuals.py (DQ_RULES) against the
-- documented baselines (docs/data_quality.md), so the view stays a plain
-- measurement.
-- ============================================================
CREATE OR REPLACE VIEW analytics.v_data_quality_checks AS
SELECT * FROM (
    -- Referential integrity
    SELECT 'ri_orders_customer' AS check_id, 'Referential integrity' AS category, 'Orders without a customer' AS check_name,
        (SELECT COUNT(*) FROM raw.orders o LEFT JOIN raw.customers c ON o.customer_id = c.customer_id WHERE c.customer_id IS NULL)::numeric AS observed
    UNION ALL SELECT 'ri_items_order', 'Referential integrity', 'Order items without an order',
        (SELECT COUNT(*) FROM raw.order_items oi LEFT JOIN raw.orders o ON oi.order_id = o.order_id WHERE o.order_id IS NULL)
    UNION ALL SELECT 'ri_items_product', 'Referential integrity', 'Order items without a product',
        (SELECT COUNT(*) FROM raw.order_items oi LEFT JOIN raw.products p ON oi.product_id = p.product_id WHERE p.product_id IS NULL)
    UNION ALL SELECT 'ri_items_seller', 'Referential integrity', 'Order items without a seller',
        (SELECT COUNT(*) FROM raw.order_items oi LEFT JOIN raw.sellers s ON oi.seller_id = s.seller_id WHERE s.seller_id IS NULL)
    UNION ALL SELECT 'ri_payments_order', 'Referential integrity', 'Payments without an order',
        (SELECT COUNT(*) FROM raw.payments p LEFT JOIN raw.orders o ON p.order_id = o.order_id WHERE o.order_id IS NULL)
    UNION ALL SELECT 'ri_reviews_order', 'Referential integrity', 'Reviews without an order',
        (SELECT COUNT(*) FROM raw.reviews r LEFT JOIN raw.orders o ON r.order_id = o.order_id WHERE o.order_id IS NULL)
    UNION ALL SELECT 'ri_category_translation', 'Referential integrity', 'Products with an untranslated category',
        (SELECT COUNT(*) FROM raw.products p LEFT JOIN raw.category_translation ct ON p.product_category_name = ct.product_category_name
         WHERE p.product_category_name IS NOT NULL AND ct.product_category_name IS NULL)
    UNION ALL SELECT 'ri_orders_no_items', 'Referential integrity', 'Orders with no items',
        (SELECT COUNT(*) FROM raw.orders o LEFT JOIN raw.order_items oi ON o.order_id = oi.order_id WHERE oi.order_id IS NULL)
    UNION ALL SELECT 'ri_orders_no_payment', 'Referential integrity', 'Orders with no payment row',
        (SELECT COUNT(*) FROM raw.orders o LEFT JOIN raw.payments p ON o.order_id = p.order_id WHERE p.order_id IS NULL)
    -- Duplicates
    UNION ALL SELECT 'dup_order_id', 'Duplicates', 'Duplicate order_id',
        (SELECT COUNT(*) - COUNT(DISTINCT order_id) FROM raw.orders)
    UNION ALL SELECT 'dup_customer_id', 'Duplicates', 'Duplicate customer_id',
        (SELECT COUNT(*) - COUNT(DISTINCT customer_id) FROM raw.customers)
    UNION ALL SELECT 'dup_product_id', 'Duplicates', 'Duplicate product_id',
        (SELECT COUNT(*) - COUNT(DISTINCT product_id) FROM raw.products)
    UNION ALL SELECT 'dup_review_id', 'Duplicates', 'review_id reused across orders (surplus rows)',
        (SELECT COUNT(*) - COUNT(DISTINCT review_id) FROM raw.reviews)
    UNION ALL SELECT 'dup_geolocation_rows', 'Duplicates', 'Geolocation full-row duplicates',
        (SELECT COUNT(*) - (SELECT COUNT(*) FROM (SELECT DISTINCT * FROM raw.geolocation) d) FROM raw.geolocation)
    -- Missing values
    UNION ALL SELECT 'na_delivered_no_date', 'Missing values', '"Delivered" orders with no delivery date',
        (SELECT COUNT(*) FROM raw.orders WHERE order_status = 'delivered' AND order_delivered_customer_date IS NULL)
    UNION ALL SELECT 'na_delivery_date', 'Missing values', 'Orders with no delivery date (all statuses)',
        (SELECT COUNT(*) FROM raw.orders WHERE order_delivered_customer_date IS NULL)
    UNION ALL SELECT 'na_product_category', 'Missing values', 'Products with no category',
        (SELECT COUNT(*) FROM raw.products WHERE product_category_name IS NULL)
    UNION ALL SELECT 'na_review_comment', 'Missing values', 'Reviews with no comment text',
        (SELECT COUNT(*) FROM raw.reviews WHERE review_comment_message IS NULL)
    -- Date sequencing
    UNION ALL SELECT 'dt_delivered_before_purchase', 'Date sequencing', 'Delivered before purchase',
        (SELECT COUNT(*) FROM raw.orders WHERE order_delivered_customer_date < order_purchase_timestamp)
    UNION ALL SELECT 'dt_approved_before_purchase', 'Date sequencing', 'Approved before purchase',
        (SELECT COUNT(*) FROM raw.orders WHERE order_approved_at < order_purchase_timestamp)
    UNION ALL SELECT 'dt_delivered_before_carrier', 'Date sequencing', 'Delivered before carrier handoff',
        (SELECT COUNT(*) FROM raw.orders WHERE order_delivered_customer_date < order_delivered_carrier_date)
    UNION ALL SELECT 'dt_carrier_before_approval', 'Date sequencing', 'Carrier handoff before approval',
        (SELECT COUNT(*) FROM raw.orders WHERE order_delivered_carrier_date < order_approved_at)
    UNION ALL SELECT 'dt_canceled_with_delivery', 'Date sequencing', 'Canceled orders with a delivery date',
        (SELECT COUNT(*) FROM raw.orders WHERE order_status = 'canceled' AND order_delivered_customer_date IS NOT NULL)
    -- Payments
    UNION ALL SELECT 'pay_zero_value', 'Payments', 'Zero-value payment rows',
        (SELECT COUNT(*) FROM raw.payments WHERE payment_value = 0)
    UNION ALL SELECT 'pay_item_mismatch', 'Payments', 'Orders where payments differ from items + freight by > R$1',
        (SELECT COUNT(*) FROM (
            SELECT i.order_id FROM
                (SELECT order_id, SUM(price + freight_value) AS t FROM raw.order_items GROUP BY order_id) i
            JOIN (SELECT order_id, SUM(payment_value) AS t FROM raw.payments GROUP BY order_id) p
              ON i.order_id = p.order_id
            WHERE ABS(i.t - p.t) > 1) m)
    -- Reconciliation (observed = absolute difference in R$)
    UNION ALL SELECT 'rec_revenue_item_vs_order', 'Reconciliation', 'Delivered revenue: item grain vs order grain (R$ difference)',
        (SELECT ABS(
            (SELECT COALESCE(SUM(foi.price), 0) FROM analytics.fact_order_items foi
               JOIN analytics.fact_orders fo ON fo.order_id = foi.order_id WHERE fo.order_status = 'delivered')
          - (SELECT COALESCE(SUM(item_revenue), 0) FROM analytics.fact_orders WHERE order_status = 'delivered')))
    UNION ALL SELECT 'rec_payments_star_vs_raw', 'Reconciliation', 'Payments: fact_payments vs raw.payments (R$ difference)',
        (SELECT ABS((SELECT COALESCE(SUM(payment_value), 0) FROM analytics.fact_payments)
                  - (SELECT COALESCE(SUM(payment_value), 0) FROM raw.payments)))
) checks;

-- ============================================================
-- 5. Build metadata
-- Written by scripts/run_pipeline.py: built_at when this file runs,
-- reconciliation_passed after step 5's reconciliation, completed_at when
-- the whole pipeline finishes. The report shows it and warns when a run
-- did not complete.
-- (The analytics schema is rebuilt by 06 on every run, so this always
-- describes the most recent build.)
-- ============================================================
CREATE TABLE analytics.pipeline_run_info (
    built_at               TIMESTAMPTZ NOT NULL,
    reconciliation_passed  BOOLEAN NOT NULL DEFAULT FALSE,
    completed_at           TIMESTAMPTZ
);
INSERT INTO analytics.pipeline_run_info (built_at) VALUES (NOW());
