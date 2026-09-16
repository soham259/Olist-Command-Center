-- SQL analysis: CTEs, window functions, ranking
-- CTEs, window functions (RANK/DENSE_RANK/ROW_NUMBER/LAG/LEAD, running sums,
-- rolling averages), and ranking — every query still answers a business question.

-- ============================================================
-- Q1. Month-over-month revenue growth
-- Business question: How is revenue changing over time, expressed as growth rate?
-- Tables: orders, order_items
-- Technique: CTE to compute monthly revenue once (staged, readable), then
--   LAG() to pull the previous month's value into the same row for a
--   percentage-change calculation. LAG is appropriate here (not a self-join)
--   because we need exactly "the row before this one in month order" —
--   a self-join would need an explicit month-arithmetic ON condition and is
--   more error-prone for this pattern.
-- What could cause an incorrect result: the first month has no prior month —
--   LAG returns NULL there, so growth % must be allowed to be NULL, not 0
--   (0% growth would misleadingly imply flat performance for a month that
--   has no valid comparison at all).
-- ============================================================
WITH monthly_revenue AS (
    SELECT
        DATE_TRUNC('month', o.order_purchase_timestamp)::date AS month,
        SUM(oi.price) AS revenue
    FROM raw.orders o
    JOIN raw.order_items oi ON o.order_id = oi.order_id
    WHERE o.order_status = 'delivered'
    GROUP BY 1
)
SELECT
    month,
    revenue,
    LAG(revenue) OVER (ORDER BY month) AS prior_month_revenue,
    ROUND(
        100.0 * (revenue - LAG(revenue) OVER (ORDER BY month))
        / NULLIF(LAG(revenue) OVER (ORDER BY month), 0)
    , 2) AS mom_growth_pct
FROM monthly_revenue
ORDER BY month;

-- ============================================================
-- Q2. Running cumulative revenue
-- Business question: What is Olist's cumulative revenue trajectory?
-- Technique: window SUM() with an ORDER BY (default frame = running total).
-- ============================================================
WITH monthly_revenue AS (
    SELECT
        DATE_TRUNC('month', o.order_purchase_timestamp)::date AS month,
        SUM(oi.price) AS revenue
    FROM raw.orders o
    JOIN raw.order_items oi ON o.order_id = oi.order_id
    WHERE o.order_status = 'delivered'
    GROUP BY 1
)
SELECT
    month,
    revenue,
    SUM(revenue) OVER (ORDER BY month) AS cumulative_revenue
FROM monthly_revenue
ORDER BY month;

-- ============================================================
-- Q3. 3-month rolling average revenue (smooths month-to-month noise)
-- Business question: What's the underlying trend, independent of single-month spikes?
-- Technique: explicit ROWS BETWEEN frame — a rolling window, distinct from
--   Q2's running total (unbounded) and distinct from a simple partition average.
-- ============================================================
WITH monthly_revenue AS (
    SELECT
        DATE_TRUNC('month', o.order_purchase_timestamp)::date AS month,
        SUM(oi.price) AS revenue
    FROM raw.orders o
    JOIN raw.order_items oi ON o.order_id = oi.order_id
    WHERE o.order_status = 'delivered'
    GROUP BY 1
)
SELECT
    month,
    revenue,
    ROUND(AVG(revenue) OVER (ORDER BY month ROWS BETWEEN 2 PRECEDING AND CURRENT ROW), 2) AS rolling_3mo_avg
FROM monthly_revenue
ORDER BY month;

-- ============================================================
-- Q4. Top 10 sellers by revenue — RANK vs DENSE_RANK comparison
-- Business question: Which sellers generate the most revenue?
-- Tables: orders, order_items, sellers
-- Why RANK matters over ROW_NUMBER here: if two sellers tie exactly on
--   revenue, ROW_NUMBER would arbitrarily assign them different positions
--   (e.g. 5 and 6), implying a difference that doesn't exist. RANK correctly
--   gives ties the same rank and skips the next number; DENSE_RANK gives
--   ties the same rank WITHOUT skipping — shown side by side so the
--   difference is visible on real data, not just explained abstractly.
-- ============================================================
WITH seller_revenue AS (
    SELECT
        oi.seller_id,
        s.seller_state,
        COUNT(DISTINCT o.order_id) AS orders,
        SUM(oi.price) AS revenue
    FROM raw.orders o
    JOIN raw.order_items oi ON o.order_id = oi.order_id
    JOIN raw.sellers s ON oi.seller_id = s.seller_id
    WHERE o.order_status = 'delivered'
    GROUP BY 1, 2
)
SELECT
    seller_id,
    seller_state,
    orders,
    revenue,
    RANK() OVER (ORDER BY revenue DESC) AS revenue_rank,
    DENSE_RANK() OVER (ORDER BY revenue DESC) AS revenue_dense_rank
FROM seller_revenue
ORDER BY revenue DESC
LIMIT 10;

-- ============================================================
-- Q5. Top 3 categories by revenue, WITHIN each state
-- Business question: Which categories generate the most revenue, per region?
--   (A single global top-15 list, as in the SQL foundation queries Q3, hides regional variation.)
-- Tables: orders, order_items, products, category_translation, customers
-- Technique: ROW_NUMBER() PARTITION BY state — the canonical "top-N per
--   group" pattern. ROW_NUMBER (not RANK) is intentional here: we want
--   exactly 3 rows per state for a clean dashboard filter, not "3 or more
--   if there's a tie for 3rd place."
-- ============================================================
WITH state_category_revenue AS (
    SELECT
        c.customer_state,
        COALESCE(ct.product_category_name_english, p.product_category_name, 'unknown') AS category,
        SUM(oi.price) AS revenue
    FROM raw.orders o
    JOIN raw.order_items oi ON o.order_id = oi.order_id
    JOIN raw.customers c ON o.customer_id = c.customer_id
    JOIN raw.products p ON oi.product_id = p.product_id
    LEFT JOIN raw.category_translation ct ON p.product_category_name = ct.product_category_name
    WHERE o.order_status = 'delivered'
    GROUP BY 1, 2
),
ranked AS (
    SELECT
        customer_state,
        category,
        revenue,
        ROW_NUMBER() OVER (PARTITION BY customer_state ORDER BY revenue DESC) AS rank_in_state
    FROM state_category_revenue
)
SELECT * FROM ranked
WHERE rank_in_state <= 3
  AND customer_state IN ('SP', 'RJ', 'MG')  -- top 3 states by volume, for readable output
ORDER BY customer_state, rank_in_state;

-- ============================================================
-- Q6. Delivery duration and delay per order, then average delay by state
-- Business question: Which states have the weakest delivery performance?
-- Tables: orders, customers
-- Technique: base calculation in a CTE (delay in days = actual - estimated;
--   positive means late), then aggregated and ranked.
-- Filter: excludes the 8 status/date-mismatch orders from the data-quality audit, and only
--   uses delivered orders with a non-null delivery date, consistent with
--   the SQL foundation queries Q5's on-time/late definition.
-- ============================================================
WITH order_delay AS (
    SELECT
        o.order_id,
        c.customer_state,
        EXTRACT(DAY FROM (o.order_delivered_customer_date - o.order_purchase_timestamp)) AS delivery_duration_days,
        EXTRACT(DAY FROM (o.order_delivered_customer_date - o.order_estimated_delivery_date)) AS delay_days
    FROM raw.orders o
    JOIN raw.customers c ON o.customer_id = c.customer_id
    WHERE o.order_status = 'delivered'
      AND o.order_delivered_customer_date IS NOT NULL
)
SELECT
    customer_state,
    COUNT(*) AS orders,
    ROUND(AVG(delivery_duration_days), 1) AS avg_delivery_days,
    ROUND(AVG(delay_days), 1) AS avg_delay_days,
    ROUND(100.0 * COUNT(*) FILTER (WHERE delay_days > 0) / COUNT(*), 2) AS pct_late,
    RANK() OVER (ORDER BY AVG(delay_days) DESC) AS worst_delay_rank
FROM order_delay
GROUP BY customer_state
HAVING COUNT(*) >= 30  -- exclude tiny-volume states from the ranking to avoid noisy outliers
ORDER BY avg_delay_days DESC
LIMIT 10;

-- ============================================================
-- Q7. Sellers whose average delivery delay is worse than the platform-wide average
-- Business question: Which sellers have weak fulfillment performance?
-- Tables: orders, order_items, sellers
-- Technique: window AVG() OVER () with no PARTITION BY computes a single
--   platform-wide benchmark value on every row simultaneously with the
--   per-seller GROUP BY aggregate — avoids a second query + application-side
--   comparison, and keeps the benchmark and the seller figure atomically
--   consistent (computed from the exact same row set).
-- Minimum volume filter avoids flagging a seller with 1 late order out of 1
--   as "underperforming" — same principle as the SQL foundation queries Q7's HAVING floor.
-- ============================================================
WITH seller_delay AS (
    SELECT
        oi.seller_id,
        o.order_id,
        EXTRACT(DAY FROM (o.order_delivered_customer_date - o.order_estimated_delivery_date)) AS delay_days
    FROM raw.orders o
    JOIN raw.order_items oi ON o.order_id = oi.order_id
    WHERE o.order_status = 'delivered'
      AND o.order_delivered_customer_date IS NOT NULL
),
seller_agg AS (
    SELECT
        seller_id,
        COUNT(DISTINCT order_id) AS orders,
        AVG(delay_days) AS avg_seller_delay
    FROM seller_delay
    GROUP BY seller_id
    HAVING COUNT(DISTINCT order_id) >= 20
)
SELECT
    seller_id,
    orders,
    ROUND(avg_seller_delay, 1) AS avg_seller_delay_days,
    ROUND(AVG(avg_seller_delay) OVER (), 1) AS platform_avg_delay_days
FROM seller_agg
WHERE avg_seller_delay > (SELECT AVG(avg_seller_delay) FROM seller_agg)
ORDER BY avg_seller_delay DESC
LIMIT 10;
