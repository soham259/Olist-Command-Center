-- SQL analysis: foundational queries (filtering, CASE, GROUP BY, JOIN)
-- Every query answers a specific business question from the business/data design.
--
-- WORKING REVENUE DEFINITION FOR THIS PHASE (provisional — finalized in the KPI dictionary):
-- revenue = SUM(order_items.price), freight tracked separately.
-- Rationale: item-grain data has NO fan-out risk (verified 1 row per order_item,
-- clean PK). payment_value was deliberately avoided here because the relational model design confirmed
-- 2,961 orders have multiple payment rows — joining item-grain data to payments
-- would inflate revenue on those orders. This choice will be revisited and
-- formally justified in the KPI dictionary, not assumed permanently from here.
--
-- ORDER STATUS FILTER: unless otherwise noted, revenue queries use orders with
-- order_status = 'delivered' — the data-quality audit found 775 orders (mostly 'unavailable'/
-- 'canceled') have zero order_items, so counting them would add order_count
-- without revenue, understating AOV. Using an INNER JOIN to order_items
-- naturally excludes them; the status filter is an extra explicit safeguard.

-- ============================================================
-- Q1. What is total revenue, and how many orders does it represent?
-- Business question: "How much revenue is being generated?"
-- Tables: orders, order_items
-- Join logic: INNER JOIN (deliberately, not LEFT) — an order with no items
--             contributes nothing to revenue, so it should not appear at all,
--             not appear with a NULL revenue.
-- ============================================================
SELECT
    COUNT(DISTINCT o.order_id) AS delivered_orders,
    SUM(oi.price) AS total_item_revenue,
    SUM(oi.freight_value) AS total_freight,
    ROUND(SUM(oi.price) / COUNT(DISTINCT o.order_id), 2) AS avg_order_value
FROM raw.orders o
JOIN raw.order_items oi ON o.order_id = oi.order_id
WHERE o.order_status = 'delivered';

-- ============================================================
-- Q2. How is revenue changing month over month?
-- Business question: "How is revenue changing over time?"
-- Tables: orders, order_items
-- Join logic: same INNER JOIN as Q1.
-- Technique: DATE_TRUNC to bucket by month; GROUP BY the bucketed date.
-- What could go wrong: using order_delivered_customer_date instead of
--   order_purchase_timestamp would shift revenue into the wrong month for any
--   order that took multiple weeks to deliver — revenue should be recognized
--   at the point of purchase/commitment, not fulfillment.
-- ============================================================
SELECT
    DATE_TRUNC('month', o.order_purchase_timestamp)::date AS month,
    COUNT(DISTINCT o.order_id) AS orders,
    SUM(oi.price) AS revenue
FROM raw.orders o
JOIN raw.order_items oi ON o.order_id = oi.order_id
WHERE o.order_status = 'delivered'
GROUP BY 1
ORDER BY 1;

-- ============================================================
-- Q3. Which product categories generate the most revenue?
-- Business question: "Which categories generate the most revenue?"
-- Tables: orders, order_items, products, category_translation
-- Join logic: order_items -> products is INNER (every item has a product,
--   confirmed zero orphans in the data-quality audit). products -> category_translation is
--   LEFT JOIN deliberately, because the data-quality audit/3 found 2 categories (13 products)
--   have no translation row — a LEFT JOIN keeps that revenue visible under
--   the original Portuguese name via COALESCE, instead of silently dropping it.
-- ============================================================
SELECT
    COALESCE(ct.product_category_name_english, p.product_category_name, 'unknown') AS category,
    COUNT(DISTINCT o.order_id) AS orders,
    SUM(oi.price) AS revenue,
    ROUND(100.0 * SUM(oi.price) / SUM(SUM(oi.price)) OVER (), 2) AS pct_of_total_revenue
FROM raw.orders o
JOIN raw.order_items oi ON o.order_id = oi.order_id
JOIN raw.products p ON oi.product_id = p.product_id
LEFT JOIN raw.category_translation ct ON p.product_category_name = ct.product_category_name
WHERE o.order_status = 'delivered'
GROUP BY 1
ORDER BY revenue DESC
LIMIT 15;

-- ============================================================
-- Q4. Which states generate the most revenue, and what's the AOV in each?
-- Business question: "Which states generate the most revenue?" + AOV
-- Tables: orders, order_items, customers
-- Join logic: orders -> customers INNER (the relational model design confirmed 0 orphans, and
--   every order needs exactly one customer for state attribution).
-- ============================================================
SELECT
    c.customer_state,
    COUNT(DISTINCT o.order_id) AS orders,
    SUM(oi.price) AS revenue,
    ROUND(SUM(oi.price) / COUNT(DISTINCT o.order_id), 2) AS avg_order_value
FROM raw.orders o
JOIN raw.order_items oi ON o.order_id = oi.order_id
JOIN raw.customers c ON o.customer_id = c.customer_id
WHERE o.order_status = 'delivered'
GROUP BY 1
ORDER BY revenue DESC;

-- ============================================================
-- Q5. What percentage of orders arrive on time vs late?
-- Business question: "What percentage of orders arrive late?"
-- Tables: orders
-- Technique: CASE expression to classify each order, then aggregate.
-- Filter: only 'delivered' orders WITH a non-null delivery date — the data-quality audit
--   found 8 'delivered' orders with a null delivery date; including them
--   would either error on the comparison or need an arbitrary default.
-- What could cause an incorrect result: including non-delivered orders would
--   conflate "still in transit" with "definitively late," overstating the
--   late-delivery rate.
-- ============================================================
SELECT
    CASE
        WHEN order_delivered_customer_date <= order_estimated_delivery_date THEN 'on_time'
        ELSE 'late'
    END AS delivery_status,
    COUNT(*) AS orders,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) AS pct
FROM raw.orders
WHERE order_status = 'delivered'
  AND order_delivered_customer_date IS NOT NULL
GROUP BY 1;

-- ============================================================
-- Q6. What does the full order_status breakdown look like, and what
--     share of orders never resulted in a completed sale?
-- Business question: cancellation-rate foundation ("What is the cancellation rate?")
-- Tables: orders
-- Technique: CASE to bucket statuses into a simpler business-friendly group.
-- ============================================================
SELECT
    CASE
        WHEN order_status = 'delivered' THEN 'completed'
        WHEN order_status IN ('canceled', 'unavailable') THEN 'failed'
        ELSE 'in_progress'
    END AS status_group,
    order_status,
    COUNT(*) AS orders,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) AS pct_of_all_orders
FROM raw.orders
GROUP BY 1, 2
ORDER BY 1, orders DESC;

-- ============================================================
-- Q7. Which categories have a meaningful order volume AND a below-average
--     review score? (Not just "worst average" on categories with 2 orders.)
-- Business question: "Which categories have poor reviews?"
-- Tables: orders, order_items, products, category_translation, reviews
-- Join logic: reviews LEFT JOIN'd — an order can have zero reviews and should
--   still count toward revenue/volume elsewhere, but for THIS query we only
--   care about orders that DO have a review, so effectively behaves as inner
--   for review_score itself. Deduplicated to order grain first via subquery to
--   avoid the reviews fan-out risk (some orders have 2-3 reviews) inflating
--   order_items row counts if joined directly at item grain.
-- Technique: HAVING filters on the aggregate (avg score, order count) — could
--   not be expressed with WHERE since it depends on a GROUP BY result.
-- ============================================================
WITH order_review AS (
    -- one row per order: average their (rare) multiple review scores first,
    -- so a 3-review order doesn't count 3x in category-level review stats
    SELECT order_id, AVG(review_score) AS order_review_score
    FROM raw.reviews
    GROUP BY order_id
),
category_orders AS (
    SELECT DISTINCT o.order_id, oi.product_id
    FROM raw.orders o
    JOIN raw.order_items oi ON o.order_id = oi.order_id
    WHERE o.order_status = 'delivered'
)
SELECT
    COALESCE(ct.product_category_name_english, p.product_category_name, 'unknown') AS category,
    COUNT(DISTINCT co.order_id) AS orders_with_review,
    ROUND(AVG(orv.order_review_score), 2) AS avg_review_score
FROM category_orders co
JOIN raw.products p ON co.product_id = p.product_id
LEFT JOIN raw.category_translation ct ON p.product_category_name = ct.product_category_name
JOIN order_review orv ON co.order_id = orv.order_id
GROUP BY 1
HAVING COUNT(DISTINCT co.order_id) >= 50  -- meaningful sample size
   AND AVG(orv.order_review_score) < 4.0  -- below-average threshold
ORDER BY avg_review_score ASC;

-- ============================================================
-- Q8. What does repeat purchasing look like?
-- Business question: "What does repeat purchasing look like?"
-- Tables: customers, orders
-- Join logic: customers -> orders via customer_unique_id grouping (NOT
--   customer_id — the data dictionary work/3 confirmed customer_id is 1:1 with orders and
--   would make every customer look like a "1-time buyer").
-- Technique: GROUP BY + HAVING to isolate repeat customers specifically.
-- ============================================================
SELECT
    CASE WHEN order_count = 1 THEN 'one_time' ELSE 'repeat' END AS customer_type,
    COUNT(*) AS customers,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) AS pct
FROM (
    SELECT c.customer_unique_id, COUNT(DISTINCT o.order_id) AS order_count
    FROM raw.customers c
    JOIN raw.orders o ON c.customer_id = o.customer_id
    WHERE o.order_status = 'delivered'
    GROUP BY c.customer_unique_id
) t
GROUP BY 1;
