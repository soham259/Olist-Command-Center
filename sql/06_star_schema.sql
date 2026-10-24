-- Dimensional star schema (schema: analytics)
--
-- GRAIN DECISIONS (made explicit before any table is created):
--
-- fact_order_items : one row per order item (product line). Grain =
--   (order_id, order_item_id). This is the ONLY fact joined to dim_product
--   and dim_seller — supports revenue-by-category/product/seller.
--
-- fact_orders : one row per order. Grain = order_id. Carries PRE-AGGREGATED
--   measures (item revenue, freight, payment total, review score, delay,
--   on-time flag) computed once here so that downstream reporting never has
--   to re-derive them by joining to payments or reviews at query time — which
--   is exactly where the fan-out risk (see the relational model design) would
--   otherwise resurface in any BI tool built on top of this schema.
--
-- fact_payments : one row per payment record. Grain = (order_id,
--   payment_sequential). Kept SEPARATE from fact_order_items specifically
--   because the relational model design confirmed 2,961 orders have multiple payment rows —
--   joining this to item-grain data would fan out revenue. It is used only
--   for payment-method-mix analysis, sliced by its own date_key (copied from
--   the order's purchase date, since payments have no date field of their
--   own in this dataset) — never joined directly to fact_order_items.
--
-- fact_reviews : DELIBERATELY NOT created as a separate star-schema fact.
--   the KPI dictionary already resolved review scoring to one number per order
--   (AVG across an order's review rows), and that number lives in
--   fact_orders.review_score. A standalone fact_reviews table would only
--   be justified by a genuine need to analyze review TEXT or individual
--   review timestamps, which no business question from the business/data design asks for.
--   Adding it now would be exactly the kind of "add a table because the
--   phase mentions it" the project rules warn against. raw.reviews remains
--   available if that need arises later.

DROP SCHEMA IF EXISTS analytics CASCADE;
CREATE SCHEMA analytics;

-- ============================================================
-- DIMENSIONS
-- ============================================================

-- dim_date: standard calendar dimension, generated (not sourced from raw data)
CREATE TABLE analytics.dim_date (
    date_key        INTEGER PRIMARY KEY,        -- YYYYMMDD
    full_date       DATE NOT NULL UNIQUE,
    year            INTEGER NOT NULL,
    quarter         INTEGER NOT NULL,
    month           INTEGER NOT NULL,
    month_name      VARCHAR(10) NOT NULL,
    day             INTEGER NOT NULL,
    day_of_week     INTEGER NOT NULL,            -- 0=Sunday
    day_name        VARCHAR(10) NOT NULL,
    is_weekend      BOOLEAN NOT NULL
);

INSERT INTO analytics.dim_date
SELECT
    TO_CHAR(d, 'YYYYMMDD')::INTEGER,
    d::date,
    EXTRACT(YEAR FROM d)::INTEGER,
    EXTRACT(QUARTER FROM d)::INTEGER,
    EXTRACT(MONTH FROM d)::INTEGER,
    TO_CHAR(d, 'Month'),
    EXTRACT(DAY FROM d)::INTEGER,
    EXTRACT(DOW FROM d)::INTEGER,
    TO_CHAR(d, 'Day'),
    EXTRACT(DOW FROM d) IN (0,6)
FROM generate_series('2016-01-01'::date, '2018-12-31'::date, '1 day') d;

-- dim_customer: grain = one row per PERSON (customer_unique_id), not per
-- customer_id. the data dictionary work/3 confirmed customer_id is 1:1 with orders, so using
-- it as the dimension grain would make repeat-customer analysis impossible
-- in the BI layer. 39 customer_unique_id values span more than one state
-- (verified negligible: 38 span 2 states, 1 spans 3) — resolved by taking
-- the most frequently occurring state/city for that person, tie-broken by
-- customer_id for determinism.
CREATE TABLE analytics.dim_customer (
    customer_key            SERIAL PRIMARY KEY,
    customer_unique_id      VARCHAR(32) NOT NULL UNIQUE,
    customer_state          VARCHAR(2) NOT NULL,
    customer_city           VARCHAR(100) NOT NULL,
    customer_zip_code_prefix INTEGER NOT NULL
);

INSERT INTO analytics.dim_customer (customer_unique_id, customer_state, customer_city, customer_zip_code_prefix)
SELECT DISTINCT ON (customer_unique_id)
    customer_unique_id, customer_state, customer_city, customer_zip_code_prefix
FROM (
    SELECT
        customer_unique_id, customer_state, customer_city, customer_zip_code_prefix,
        COUNT(*) OVER (PARTITION BY customer_unique_id, customer_state) AS state_freq,
        customer_id
    FROM raw.customers
) t
ORDER BY customer_unique_id, state_freq DESC, customer_id;

-- dim_product: grain = one row per product_id. Category translated with
-- COALESCE for the 13 products (2 categories) with no translation row,
-- per the the data-quality audit/3 decision — they must NOT disappear from the dimension.
CREATE TABLE analytics.dim_product (
    product_key         SERIAL PRIMARY KEY,
    product_id           VARCHAR(32) NOT NULL UNIQUE,
    category_name_pt      VARCHAR(60),
    category_name_en       VARCHAR(60),
    product_weight_g        NUMERIC,
    product_length_cm        NUMERIC,
    product_height_cm         NUMERIC,
    product_width_cm           NUMERIC
);

INSERT INTO analytics.dim_product
    (product_id, category_name_pt, category_name_en, product_weight_g, product_length_cm, product_height_cm, product_width_cm)
SELECT
    p.product_id,
    p.product_category_name,
    COALESCE(ct.product_category_name_english, p.product_category_name, 'unknown'),
    p.product_weight_g, p.product_length_cm, p.product_height_cm, p.product_width_cm
FROM raw.products p
LEFT JOIN raw.category_translation ct ON p.product_category_name = ct.product_category_name;

-- dim_seller: grain = one row per seller_id.
CREATE TABLE analytics.dim_seller (
    seller_key         SERIAL PRIMARY KEY,
    seller_id           VARCHAR(32) NOT NULL UNIQUE,
    seller_state          VARCHAR(2) NOT NULL,
    seller_city             VARCHAR(100) NOT NULL,
    seller_zip_code_prefix   INTEGER NOT NULL
);

INSERT INTO analytics.dim_seller (seller_id, seller_state, seller_city, seller_zip_code_prefix)
SELECT seller_id, seller_state, seller_city, seller_zip_code_prefix
FROM raw.sellers;

-- dim_geography: grain = one row per zip_code_prefix (NOT the raw
-- geolocation grain, which has no natural key and 261,831 duplicate rows
-- per the data-quality audit). City name is highly inconsistent within a zip prefix (up to
-- 5 distinct spellings observed) — resolved by taking the most frequent
-- city string per prefix; lat/lng resolved by averaging all points for
-- that prefix (an approximation — this dimension supports state/city-level
-- rollups, not precise mapping of individual addresses).
CREATE TABLE analytics.dim_geography (
    geo_key                 SERIAL PRIMARY KEY,
    zip_code_prefix          INTEGER NOT NULL UNIQUE,
    city                       VARCHAR(100) NOT NULL,
    state                       VARCHAR(2) NOT NULL,
    latitude                    NUMERIC(10,7),
    longitude                    NUMERIC(10,7)
);

INSERT INTO analytics.dim_geography (zip_code_prefix, city, state, latitude, longitude)
SELECT DISTINCT ON (g.geolocation_zip_code_prefix)
    g.geolocation_zip_code_prefix,
    g.geolocation_city,
    g.geolocation_state,
    avg_coords.avg_lat,
    avg_coords.avg_lng
FROM raw.geolocation g
JOIN (
    SELECT geolocation_zip_code_prefix, AVG(geolocation_lat) AS avg_lat, AVG(geolocation_lng) AS avg_lng
    FROM raw.geolocation GROUP BY geolocation_zip_code_prefix
) avg_coords ON g.geolocation_zip_code_prefix = avg_coords.geolocation_zip_code_prefix
JOIN (
    SELECT geolocation_zip_code_prefix, geolocation_city, geolocation_state, COUNT(*) AS freq
    FROM raw.geolocation
    GROUP BY geolocation_zip_code_prefix, geolocation_city, geolocation_state
) city_freq ON g.geolocation_zip_code_prefix = city_freq.geolocation_zip_code_prefix
           AND g.geolocation_city = city_freq.geolocation_city
           AND g.geolocation_state = city_freq.geolocation_state
ORDER BY g.geolocation_zip_code_prefix, city_freq.freq DESC, g.geolocation_city, g.geolocation_state;
-- (Audit fix: the last two ORDER BY keys break ties between equally frequent
-- city spellings deterministically; without them DISTINCT ON could pick a
-- different spelling on different runs.)

-- ============================================================
-- FACTS
-- ============================================================

-- fact_order_items: grain = one row per order item. The revenue/category/
-- seller/product workhorse fact.
CREATE TABLE analytics.fact_order_items (
    order_id        VARCHAR(32) NOT NULL,
    order_item_id    INTEGER NOT NULL,
    product_key       INTEGER NOT NULL REFERENCES analytics.dim_product(product_key),
    seller_key          INTEGER NOT NULL REFERENCES analytics.dim_seller(seller_key),
    customer_key           INTEGER NOT NULL REFERENCES analytics.dim_customer(customer_key),
    date_key                 INTEGER NOT NULL REFERENCES analytics.dim_date(date_key),
    price                       NUMERIC(12,2) NOT NULL,
    freight_value                 NUMERIC(12,2) NOT NULL,
    PRIMARY KEY (order_id, order_item_id)
);

INSERT INTO analytics.fact_order_items
SELECT
    oi.order_id, oi.order_item_id,
    dp.product_key, ds.seller_key, dc.customer_key,
    TO_CHAR(o.order_purchase_timestamp, 'YYYYMMDD')::INTEGER,
    oi.price, oi.freight_value
FROM raw.order_items oi
JOIN raw.orders o ON oi.order_id = o.order_id
JOIN raw.customers rc ON o.customer_id = rc.customer_id
JOIN analytics.dim_customer dc ON rc.customer_unique_id = dc.customer_unique_id
JOIN analytics.dim_product dp ON oi.product_id = dp.product_id
JOIN analytics.dim_seller ds ON oi.seller_id = ds.seller_id;

-- fact_orders: grain = one row per order. Pre-aggregated measures so BI-layer
-- measures don't need to re-derive them via risky joins.
CREATE TABLE analytics.fact_orders (
    order_id            VARCHAR(32) PRIMARY KEY,
    customer_key           INTEGER NOT NULL REFERENCES analytics.dim_customer(customer_key),
    date_key                  INTEGER NOT NULL REFERENCES analytics.dim_date(date_key),
    order_status                VARCHAR(20) NOT NULL,
    n_items                       INTEGER NOT NULL,
    item_revenue                    NUMERIC(12,2) NOT NULL,
    freight_revenue                    NUMERIC(12,2) NOT NULL,
    payment_value                         NUMERIC(12,2),
    review_score                            NUMERIC(3,2),
    is_delivered                              BOOLEAN NOT NULL,
    is_on_time                                  BOOLEAN,
    delay_days                                    NUMERIC
);

INSERT INTO analytics.fact_orders
WITH item_agg AS (
    SELECT order_id, COUNT(*) AS n_items, SUM(price) AS item_revenue, SUM(freight_value) AS freight_revenue
    FROM raw.order_items GROUP BY order_id
),
payment_agg AS (
    SELECT order_id, SUM(payment_value) AS payment_value FROM raw.payments GROUP BY order_id
),
review_agg AS (
    SELECT order_id, AVG(review_score) AS review_score FROM raw.reviews GROUP BY order_id
)
SELECT
    o.order_id,
    dc.customer_key,
    TO_CHAR(o.order_purchase_timestamp, 'YYYYMMDD')::INTEGER,
    o.order_status,
    COALESCE(ia.n_items, 0),
    COALESCE(ia.item_revenue, 0),
    COALESCE(ia.freight_revenue, 0),
    pa.payment_value,
    ra.review_score,
    o.order_status = 'delivered',
    CASE WHEN o.order_status = 'delivered' AND o.order_delivered_customer_date IS NOT NULL
         THEN o.order_delivered_customer_date <= o.order_estimated_delivery_date END,
    CASE WHEN o.order_status = 'delivered' AND o.order_delivered_customer_date IS NOT NULL
         THEN ROUND((EXTRACT(EPOCH FROM (o.order_delivered_customer_date - o.order_estimated_delivery_date)) / 86400)::numeric, 2) END
    -- delay_days = fractional days late (+) / early (-). Audit fix: previously
    -- EXTRACT(DAY FROM interval), which truncates toward zero, so an order
    -- delivered 15 hours after its estimate was flagged late (is_on_time = FALSE)
    -- yet showed delay_days = 0.
FROM raw.orders o
JOIN raw.customers rc ON o.customer_id = rc.customer_id
JOIN analytics.dim_customer dc ON rc.customer_unique_id = dc.customer_unique_id
LEFT JOIN item_agg ia ON o.order_id = ia.order_id
LEFT JOIN payment_agg pa ON o.order_id = pa.order_id
LEFT JOIN review_agg ra ON o.order_id = ra.order_id;

-- fact_payments: grain = one row per payment record. date_key is copied
-- from the parent order's purchase date (payments have no date of their
-- own in this dataset) so it can be sliced by dim_date directly, without
-- forcing a snowflake join through fact_orders every time.
CREATE TABLE analytics.fact_payments (
    order_id             VARCHAR(32) NOT NULL,
    payment_sequential     INTEGER NOT NULL,
    date_key                  INTEGER NOT NULL REFERENCES analytics.dim_date(date_key),
    payment_type                  VARCHAR(20) NOT NULL,
    payment_installments             INTEGER NOT NULL,
    payment_value                       NUMERIC(12,2) NOT NULL,
    PRIMARY KEY (order_id, payment_sequential)
);

INSERT INTO analytics.fact_payments
SELECT
    p.order_id, p.payment_sequential,
    TO_CHAR(o.order_purchase_timestamp, 'YYYYMMDD')::INTEGER,
    p.payment_type, p.payment_installments, p.payment_value
FROM raw.payments p
JOIN raw.orders o ON p.order_id = o.order_id;

-- Supporting indexes on the star schema's FK columns
CREATE INDEX idx_foi_product ON analytics.fact_order_items(product_key);
CREATE INDEX idx_foi_seller ON analytics.fact_order_items(seller_key);
CREATE INDEX idx_foi_customer ON analytics.fact_order_items(customer_key);
CREATE INDEX idx_foi_date ON analytics.fact_order_items(date_key);
CREATE INDEX idx_fo_customer ON analytics.fact_orders(customer_key);
CREATE INDEX idx_fo_date ON analytics.fact_orders(date_key);
CREATE INDEX idx_fp_date ON analytics.fact_payments(date_key);
