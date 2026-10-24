-- Raw layer DDL
-- Design decisions:
--  - No FK constraints enforced yet at raw layer (raw layer mirrors source as-is;
--    referential integrity is INVESTIGATED in the data-quality audit, ENFORCED in the
--    relational model's constraints file).
--  - review_id is NOT declared as a primary key here: verified during data-dictionary
--    work that the
--    same review_id can appear against multiple order_ids (in the supplied
--    99,224-row reviews file: 789 review_ids reused, 814 surplus rows; the
--    earlier 100,000-row revision of the file had 827). Natural key for
--    reviews is (review_id, order_id).
--  - geolocation has no natural primary key at raw grain; loaded as-is including
--    duplicates (261,831 fully duplicate rows found) - deduplication is a
--    transformation decision, not a raw-load decision.
--  - Original Olist column names preserved exactly, including the source typo
--    "lenght" in product_name_lenght / product_description_lenght.

DROP SCHEMA IF EXISTS raw CASCADE;
CREATE SCHEMA raw;

CREATE TABLE raw.customers (
    customer_id                VARCHAR(32) PRIMARY KEY,
    customer_unique_id         VARCHAR(32) NOT NULL,
    customer_zip_code_prefix   INTEGER NOT NULL,
    customer_city               VARCHAR(100) NOT NULL,
    customer_state               VARCHAR(2) NOT NULL
);

CREATE TABLE raw.orders (
    order_id                        VARCHAR(32) PRIMARY KEY,
    customer_id                     VARCHAR(32) NOT NULL,
    order_status                    VARCHAR(20) NOT NULL,
    order_purchase_timestamp        TIMESTAMP NOT NULL,
    order_approved_at               TIMESTAMP,
    order_delivered_carrier_date    TIMESTAMP,
    order_delivered_customer_date   TIMESTAMP,
    order_estimated_delivery_date   TIMESTAMP NOT NULL
);

CREATE TABLE raw.order_items (
    order_id         VARCHAR(32) NOT NULL,
    order_item_id    INTEGER NOT NULL,
    product_id       VARCHAR(32) NOT NULL,
    seller_id        VARCHAR(32) NOT NULL,
    shipping_limit_date TIMESTAMP NOT NULL,   -- present in the source CSV; was missing from this DDL, which made the load fail
    price             NUMERIC(12,2) NOT NULL,
    freight_value      NUMERIC(12,2) NOT NULL,
    PRIMARY KEY (order_id, order_item_id)
);

CREATE TABLE raw.payments (
    order_id               VARCHAR(32) NOT NULL,
    payment_sequential     INTEGER NOT NULL,
    payment_type           VARCHAR(20) NOT NULL,
    payment_installments   INTEGER NOT NULL,
    payment_value          NUMERIC(12,2) NOT NULL,
    PRIMARY KEY (order_id, payment_sequential)
);

CREATE TABLE raw.reviews (
    review_id                  VARCHAR(32) NOT NULL,
    order_id                   VARCHAR(32) NOT NULL,
    review_score                INTEGER NOT NULL,
    review_comment_title        TEXT,
    review_comment_message      TEXT,
    review_creation_date        TIMESTAMP NOT NULL,
    review_answer_timestamp     TIMESTAMP NOT NULL,
    PRIMARY KEY (review_id, order_id)
);

CREATE TABLE raw.products (
    product_id                    VARCHAR(32) PRIMARY KEY,
    product_category_name          VARCHAR(60),
    product_name_lenght             NUMERIC,
    product_description_lenght       NUMERIC,
    product_photos_qty                NUMERIC,
    product_weight_g                   NUMERIC,
    product_length_cm                   NUMERIC,
    product_height_cm                    NUMERIC,
    product_width_cm                      NUMERIC
);

CREATE TABLE raw.sellers (
    seller_id                  VARCHAR(32) PRIMARY KEY,
    seller_zip_code_prefix     INTEGER NOT NULL,
    seller_city                 VARCHAR(100) NOT NULL,
    seller_state                 VARCHAR(2) NOT NULL
);

CREATE TABLE raw.geolocation (
    geolocation_zip_code_prefix   INTEGER NOT NULL,
    geolocation_lat                 DOUBLE PRECISION NOT NULL,  -- audit fix: was NUMERIC(10,7), which rounded source
    geolocation_lng                  DOUBLE PRECISION NOT NULL,  -- coordinates and created 32 extra "duplicate" rows
    geolocation_city                  VARCHAR(100) NOT NULL,
    geolocation_state                  VARCHAR(2) NOT NULL
);

CREATE TABLE raw.category_translation (
    product_category_name          VARCHAR(60) PRIMARY KEY,
    product_category_name_english  VARCHAR(60) NOT NULL
);
