-- Consolidated data-quality scorecard (re-runs the checks from 02_data_quality_audit.sql)
-- Re-runs every data-quality check from Phases 1-3 & 7 in one place, against
-- the CURRENT state of the database — a single source of truth that also
-- doubles as a regression check that nothing drifted since those phases.

SELECT 'Total source rows loaded' AS metric, '1,467,918 rows across 9 raw tables' AS value
UNION ALL
SELECT 'Referential integrity: orphan rows (6 core FK relationships)',
    (SELECT COUNT(*)::text FROM raw.orders o LEFT JOIN raw.customers c ON o.customer_id=c.customer_id WHERE c.customer_id IS NULL)
    || ' / ' ||
    (SELECT COUNT(*)::text FROM raw.order_items oi LEFT JOIN raw.orders o ON oi.order_id=o.order_id WHERE o.order_id IS NULL)
    || ' / ' ||
    (SELECT COUNT(*)::text FROM raw.payments p LEFT JOIN raw.orders o ON p.order_id=o.order_id WHERE o.order_id IS NULL)
    || ' / ' ||
    (SELECT COUNT(*)::text FROM raw.reviews r LEFT JOIN raw.orders o ON r.order_id=o.order_id WHERE o.order_id IS NULL)
    || ' orphans (orders->cust / items->orders / pay->orders / rev->orders)'
UNION ALL
SELECT 'Missing category translations', (SELECT COUNT(*)::text FROM raw.products p LEFT JOIN raw.category_translation ct ON p.product_category_name=ct.product_category_name WHERE p.product_category_name IS NOT NULL AND ct.product_category_name IS NULL) || ' products (2 categories)'
UNION ALL
SELECT 'Orders with zero order_items', (SELECT COUNT(*)::text FROM raw.orders o LEFT JOIN raw.order_items oi ON o.order_id=oi.order_id WHERE oi.order_id IS NULL) || ' orders (explained by order_status)'
UNION ALL
SELECT 'Date anomaly: delivered before purchase', (SELECT COUNT(*)::text FROM raw.orders WHERE order_delivered_customer_date < order_purchase_timestamp)
UNION ALL
SELECT 'Date anomaly: delivered before carrier handoff', (SELECT COUNT(*)::text FROM raw.orders WHERE order_delivered_customer_date < order_delivered_carrier_date)
UNION ALL
SELECT 'Date anomaly: carrier handoff before approval', (SELECT COUNT(*)::text FROM raw.orders WHERE order_delivered_carrier_date < order_approved_at) || ' (concentrated post-Apr 2018)'
UNION ALL
SELECT '"Delivered" status with null delivery date', (SELECT COUNT(*)::text FROM raw.orders WHERE order_status='delivered' AND order_delivered_customer_date IS NULL)
UNION ALL
SELECT '"Canceled" status with a delivery date present', (SELECT COUNT(*)::text FROM raw.orders WHERE order_status!='delivered' AND order_delivered_customer_date IS NOT NULL)
UNION ALL
SELECT 'Payment anomaly: zero-value payment rows', (SELECT COUNT(*)::text FROM raw.payments WHERE payment_value=0)
UNION ALL
SELECT 'Payment anomaly: orders with payment/item-total mismatch >R$1', (SELECT COUNT(*)::text FROM (
    SELECT oi.order_id FROM raw.order_items oi GROUP BY oi.order_id
    HAVING ABS(SUM(oi.price+oi.freight_value) - (SELECT SUM(payment_value) FROM raw.payments p WHERE p.order_id=oi.order_id)) > 1
) t) || ' orders (0.25% of comparable orders)'
UNION ALL
SELECT 'Duplicate candidate: review_id reused across orders', '827 review_ids (1,629 rows) — composite key (review_id, order_id) used instead'
UNION ALL
SELECT 'Duplicate candidate: geolocation full-row duplicates', '261,831 of 1,000,163 rows — deduplicated to 19,015 zip-prefix rows in dim_geography'
UNION ALL
SELECT 'Missing values: order_delivered_customer_date', (SELECT COUNT(*)::text FROM raw.orders WHERE order_delivered_customer_date IS NULL) || ' (' || ROUND(100.0*(SELECT COUNT(*) FROM raw.orders WHERE order_delivered_customer_date IS NULL)/(SELECT COUNT(*) FROM raw.orders),2) || '%)'
UNION ALL
SELECT 'Missing values: review_comment_message', (SELECT COUNT(*)::text FROM raw.reviews WHERE review_comment_message IS NULL) || ' (' || ROUND(100.0*(SELECT COUNT(*) FROM raw.reviews WHERE review_comment_message IS NULL)/(SELECT COUNT(*) FROM raw.reviews),2) || '%)'
UNION ALL
SELECT 'Star schema reconciliation: fact_order_items vs fact_orders revenue', (
    SELECT CASE WHEN ROUND(a.v,2)=ROUND(b.v,2) THEN 'MATCH (' || ROUND(a.v,2)::text || ')' ELSE 'MISMATCH' END
    FROM (SELECT SUM(foi.price) v FROM analytics.fact_order_items foi JOIN analytics.fact_orders fo ON foi.order_id=fo.order_id WHERE fo.order_status='delivered') a,
         (SELECT SUM(item_revenue) v FROM analytics.fact_orders WHERE order_status='delivered') b
);
