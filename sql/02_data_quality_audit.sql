-- Data Quality Audit — read-only checks against the raw layer
-- All checks are read-only investigations against the raw layer.
-- Nothing is deleted or modified here — findings are documented in
-- docs/data_quality.md with an explicit retain/exclude/
-- transform/flag decision per issue.

-- ============================================================
-- SECTION A: Referential integrity (orphan checks)
-- ============================================================

-- A1. orders -> customers : does every order have a valid customer?
SELECT 'orders_missing_customer' AS check_name, COUNT(*) AS orphan_rows
FROM raw.orders o
LEFT JOIN raw.customers c ON o.customer_id = c.customer_id
WHERE c.customer_id IS NULL;

-- A2. order_items -> orders : does every order_item belong to a real order?
SELECT 'order_items_missing_order' AS check_name, COUNT(*) AS orphan_rows
FROM raw.order_items oi
LEFT JOIN raw.orders o ON oi.order_id = o.order_id
WHERE o.order_id IS NULL;

-- A3. order_items -> products
SELECT 'order_items_missing_product' AS check_name, COUNT(*) AS orphan_rows
FROM raw.order_items oi
LEFT JOIN raw.products p ON oi.product_id = p.product_id
WHERE p.product_id IS NULL;

-- A4. order_items -> sellers
SELECT 'order_items_missing_seller' AS check_name, COUNT(*) AS orphan_rows
FROM raw.order_items oi
LEFT JOIN raw.sellers s ON oi.seller_id = s.seller_id
WHERE s.seller_id IS NULL;

-- A5. payments -> orders
SELECT 'payments_missing_order' AS check_name, COUNT(*) AS orphan_rows
FROM raw.payments p
LEFT JOIN raw.orders o ON p.order_id = o.order_id
WHERE o.order_id IS NULL;

-- A6. reviews -> orders
SELECT 'reviews_missing_order' AS check_name, COUNT(*) AS orphan_rows
FROM raw.reviews r
LEFT JOIN raw.orders o ON r.order_id = o.order_id
WHERE o.order_id IS NULL;

-- A7. products -> category_translation (does every non-null category have a translation?)
SELECT 'products_missing_category_translation' AS check_name, COUNT(*) AS orphan_rows
FROM raw.products p
LEFT JOIN raw.category_translation ct ON p.product_category_name = ct.product_category_name
WHERE p.product_category_name IS NOT NULL AND ct.product_category_name IS NULL;

-- A8. Do all orders have at least one order_item? (the reverse direction of A2)
SELECT 'orders_with_no_items' AS check_name, COUNT(*) AS orphan_rows
FROM raw.orders o
LEFT JOIN raw.order_items oi ON o.order_id = oi.order_id
WHERE oi.order_id IS NULL;

-- A9. Do all orders have at least one payment record?
SELECT 'orders_with_no_payment' AS check_name, COUNT(*) AS orphan_rows
FROM raw.orders o
LEFT JOIN raw.payments p ON o.order_id = p.order_id
WHERE p.order_id IS NULL;

-- ============================================================
-- SECTION B: Date anomalies
-- ============================================================

-- B1. Delivered to customer before the order was purchased (impossible)
SELECT 'delivered_before_purchase' AS check_name, COUNT(*) AS bad_rows
FROM raw.orders
WHERE order_delivered_customer_date < order_purchase_timestamp;

-- B2. Approved before purchase (impossible)
SELECT 'approved_before_purchase' AS check_name, COUNT(*) AS bad_rows
FROM raw.orders
WHERE order_approved_at < order_purchase_timestamp;

-- B3. Estimated delivery date before purchase date (would be a nonsensical promise)
SELECT 'estimated_delivery_before_purchase' AS check_name, COUNT(*) AS bad_rows
FROM raw.orders
WHERE order_estimated_delivery_date < order_purchase_timestamp;

-- B4. Delivered to customer before handed to carrier (impossible sequence)
SELECT 'delivered_customer_before_carrier' AS check_name, COUNT(*) AS bad_rows
FROM raw.orders
WHERE order_delivered_customer_date < order_delivered_carrier_date;

-- B5. Carrier handoff before order approval (impossible sequence)
SELECT 'carrier_before_approved' AS check_name, COUNT(*) AS bad_rows
FROM raw.orders
WHERE order_delivered_carrier_date < order_approved_at;

-- B6. Distribution of delivery duration (days) for delivered orders — look for extreme outliers
SELECT
    MIN(EXTRACT(DAY FROM (order_delivered_customer_date - order_purchase_timestamp))) AS min_days,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY EXTRACT(DAY FROM (order_delivered_customer_date - order_purchase_timestamp))) AS median_days,
    AVG(EXTRACT(DAY FROM (order_delivered_customer_date - order_purchase_timestamp))) AS avg_days,
    PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY EXTRACT(DAY FROM (order_delivered_customer_date - order_purchase_timestamp))) AS p99_days,
    MAX(EXTRACT(DAY FROM (order_delivered_customer_date - order_purchase_timestamp))) AS max_days
FROM raw.orders
WHERE order_status = 'delivered' AND order_delivered_customer_date IS NOT NULL;

-- B7. Delivered orders with NULL delivered_customer_date (status/data mismatch)
SELECT 'delivered_status_but_no_delivery_date' AS check_name, COUNT(*) AS bad_rows
FROM raw.orders
WHERE order_status = 'delivered' AND order_delivered_customer_date IS NULL;

-- B8. Non-delivered orders that DO have a delivered_customer_date (status/data mismatch)
SELECT 'non_delivered_status_but_has_delivery_date' AS check_name, order_status, COUNT(*) AS bad_rows
FROM raw.orders
WHERE order_status != 'delivered' AND order_delivered_customer_date IS NOT NULL
GROUP BY order_status
ORDER BY bad_rows DESC;

-- ============================================================
-- SECTION C: Payment anomalies
-- ============================================================

-- C1. Zero-value payments
SELECT 'zero_value_payments' AS check_name, COUNT(*) AS bad_rows
FROM raw.payments
WHERE payment_value = 0;

-- C2. Zero installments (should be at least 1)
SELECT 'zero_installments' AS check_name, COUNT(*) AS bad_rows
FROM raw.payments
WHERE payment_installments = 0;

-- C3. Very high installment counts (distribution check, not a hard threshold)
SELECT payment_installments, COUNT(*) AS n
FROM raw.payments
GROUP BY payment_installments
ORDER BY payment_installments DESC
LIMIT 10;

-- C4. payment_type distribution
SELECT payment_type, COUNT(*) AS n, ROUND(100.0*COUNT(*)/SUM(COUNT(*)) OVER (), 2) AS pct
FROM raw.payments
GROUP BY payment_type
ORDER BY n DESC;

-- C5. Orders with multiple payment rows (installments/split payments — expected, but quantify it)
SELECT payments_per_order, COUNT(*) AS n_orders
FROM (
    SELECT order_id, COUNT(*) AS payments_per_order
    FROM raw.payments
    GROUP BY order_id
) t
GROUP BY payments_per_order
ORDER BY payments_per_order;

-- C6. Reconciliation: does SUM(payment_value) per order roughly match SUM(price+freight) per order?
-- Large mismatches could indicate vouchers/credits, partial payments, or data issues.
WITH item_totals AS (
    SELECT order_id, SUM(price + freight_value) AS items_total
    FROM raw.order_items
    GROUP BY order_id
),
payment_totals AS (
    SELECT order_id, SUM(payment_value) AS payments_total
    FROM raw.payments
    GROUP BY order_id
)
SELECT
    COUNT(*) AS orders_compared,
    COUNT(*) FILTER (WHERE ABS(i.items_total - p.payments_total) < 0.01) AS exact_match,
    COUNT(*) FILTER (WHERE ABS(i.items_total - p.payments_total) BETWEEN 0.01 AND 1.00) AS small_diff_under_1,
    COUNT(*) FILTER (WHERE ABS(i.items_total - p.payments_total) > 1.00) AS large_diff_over_1
FROM item_totals i
JOIN payment_totals p ON i.order_id = p.order_id;

-- C7. Show the worst mismatches for manual inspection
WITH item_totals AS (
    SELECT order_id, SUM(price + freight_value) AS items_total
    FROM raw.order_items
    GROUP BY order_id
),
payment_totals AS (
    SELECT order_id, SUM(payment_value) AS payments_total
    FROM raw.payments
    GROUP BY order_id
)
SELECT i.order_id, i.items_total, p.payments_total,
       ROUND((p.payments_total - i.items_total)::numeric, 2) AS diff
FROM item_totals i
JOIN payment_totals p ON i.order_id = p.order_id
ORDER BY ABS(p.payments_total - i.items_total) DESC
LIMIT 10;

-- ============================================================
-- SECTION D: Duplicate checks beyond primary keys
-- ============================================================

-- D1. customer_unique_id appearing multiple times (repeat customers, not an error — quantify)
SELECT n_orders_per_customer, COUNT(*) AS n_customers
FROM (
    SELECT customer_unique_id, COUNT(*) AS n_orders_per_customer
    FROM raw.customers
    GROUP BY customer_unique_id
) t
GROUP BY n_orders_per_customer
ORDER BY n_orders_per_customer;

-- D2. review_id reused across different orders (confirmed in the data dictionary work — quantify precisely here)
SELECT review_id, COUNT(DISTINCT order_id) AS distinct_orders
FROM raw.reviews
GROUP BY review_id
HAVING COUNT(DISTINCT order_id) > 1
ORDER BY distinct_orders DESC
LIMIT 5;
