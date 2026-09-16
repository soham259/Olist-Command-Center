-- Foreign keys and indexes for the raw layer
-- Adds FK constraints and indexes to the raw layer now that the data-quality audit confirmed
-- referential integrity holds for every relationship EXCEPT products -> category_translation
-- (13 products reference 2 category names that have no translation row — see decision below).

-- ============================================================
-- Foreign keys (all confirmed zero-orphan in the data-quality audit — safe to enforce)
-- ============================================================

ALTER TABLE raw.orders
    ADD CONSTRAINT fk_orders_customer
    FOREIGN KEY (customer_id) REFERENCES raw.customers(customer_id);

ALTER TABLE raw.order_items
    ADD CONSTRAINT fk_order_items_order
    FOREIGN KEY (order_id) REFERENCES raw.orders(order_id);

ALTER TABLE raw.order_items
    ADD CONSTRAINT fk_order_items_product
    FOREIGN KEY (product_id) REFERENCES raw.products(product_id);

ALTER TABLE raw.order_items
    ADD CONSTRAINT fk_order_items_seller
    FOREIGN KEY (seller_id) REFERENCES raw.sellers(seller_id);

ALTER TABLE raw.payments
    ADD CONSTRAINT fk_payments_order
    FOREIGN KEY (order_id) REFERENCES raw.orders(order_id);

ALTER TABLE raw.reviews
    ADD CONSTRAINT fk_reviews_order
    FOREIGN KEY (order_id) REFERENCES raw.orders(order_id);

-- ============================================================
-- products -> category_translation: NOT enforced as a hard FK.
--
-- Decision (documented in the data-quality audit & repeated here for anyone reading the DDL
-- in isolation): 13 products reference 2 category names
-- ('portateis_cozinha_e_preparadores_de_alimentos', 'pc_gamer') that have no
-- row in category_translation. Adding a hard FK here would either:
--   (a) fail immediately on this DDL, or
--   (b) require deleting/nulling 13 real product rows to satisfy it.
-- Neither is acceptable at the raw layer, which mirrors source data as-is.
-- The gap is instead handled downstream: the analytics layer will COALESCE
-- to the original Portuguese name when no English translation exists, so
-- these 13 products remain visible in category-level reporting.
-- ============================================================

-- ============================================================
-- Indexes on FK columns (Postgres does NOT auto-index FK columns,
-- only the referenced primary key side)
-- ============================================================

CREATE INDEX idx_orders_customer_id ON raw.orders(customer_id);
CREATE INDEX idx_order_items_order_id ON raw.order_items(order_id);
CREATE INDEX idx_order_items_product_id ON raw.order_items(product_id);
CREATE INDEX idx_order_items_seller_id ON raw.order_items(seller_id);
CREATE INDEX idx_payments_order_id ON raw.payments(order_id);
CREATE INDEX idx_reviews_order_id ON raw.reviews(order_id);

-- Supporting indexes for known high-frequency analytical access patterns
-- (time-series revenue/order queries, state-level rollups)
CREATE INDEX idx_orders_purchase_timestamp ON raw.orders(order_purchase_timestamp);
CREATE INDEX idx_orders_status ON raw.orders(order_status);
CREATE INDEX idx_customers_state ON raw.customers(customer_state);
CREATE INDEX idx_sellers_state ON raw.sellers(seller_state);
CREATE INDEX idx_products_category ON raw.products(product_category_name);
CREATE INDEX idx_geolocation_zip ON raw.geolocation(geolocation_zip_code_prefix);
