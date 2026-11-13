-- Assignment 6: physical model (gold layer, star schema)
--
-- Written in portable SQL so that tests/test_models.py can run it in SQLite.
-- Target platform: Amazon Redshift (or PostgreSQL). Redshift tuning notes are in
-- comments: DISTKEY / SORTKEY are shown as comments because SQLite does not accept them.
--
-- Conformed (shared) dimensions: dim_date, dim_location.
-- Source-specific dimensions: dim_customer, dim_product, dim_seller (keys do not match across sources).
-- Facts: fact_order_item, fact_payment, fact_review (Olist); fact_retail_line (UCI Online Retail).

CREATE TABLE dim_date (
    date_key      INTEGER PRIMARY KEY,           -- yyyymmdd, e.g. 20171015
    full_date     TEXT    NOT NULL UNIQUE,       -- ISO-8601 date
    year          INTEGER NOT NULL,
    quarter       INTEGER NOT NULL CHECK (quarter BETWEEN 1 AND 4),
    month         INTEGER NOT NULL CHECK (month BETWEEN 1 AND 12),
    day           INTEGER NOT NULL CHECK (day BETWEEN 1 AND 31),
    day_of_week   INTEGER NOT NULL CHECK (day_of_week BETWEEN 1 AND 7),  -- 1 = Monday
    is_weekend    INTEGER NOT NULL CHECK (is_weekend IN (0, 1))
);  -- Redshift: DISTSTYLE ALL (small table), SORTKEY (full_date)

CREATE TABLE dim_location (
    zip_code_prefix TEXT PRIMARY KEY,            -- first 5 digits of the Brazilian CEP
    city            TEXT,
    state           TEXT,                        -- 2-letter UF
    country_code    TEXT NOT NULL DEFAULT 'BR',
    latitude        REAL,                        -- mean of the source geolocation points
    longitude       REAL
);  -- Redshift: DISTSTYLE ALL

CREATE TABLE dim_customer (
    customer_key        INTEGER PRIMARY KEY,     -- surrogate key
    source_system       TEXT    NOT NULL CHECK (source_system IN ('olist', 'uci_retail')),
    source_customer_id  TEXT    NOT NULL,        -- Olist customer_unique_id, or UCI CustomerID
    zip_code_prefix     TEXT REFERENCES dim_location (zip_code_prefix),  -- Olist only
    country             TEXT,                    -- UCI only (invoice country)
    UNIQUE (source_system, source_customer_id)
);  -- Redshift: DISTKEY (customer_key), SORTKEY (source_system, source_customer_id)

CREATE TABLE dim_product (
    product_key        INTEGER PRIMARY KEY,
    source_system      TEXT NOT NULL CHECK (source_system IN ('olist', 'uci_retail')),
    source_product_id  TEXT NOT NULL,            -- Olist product_id, or UCI StockCode
    description        TEXT,                     -- UCI Description; Olist left NULL
    category_en        TEXT,                     -- Olist category, translated to English
    weight_g           REAL,
    length_cm          REAL,
    height_cm          REAL,
    width_cm           REAL,
    UNIQUE (source_system, source_product_id)
);  -- Redshift: DISTKEY (product_key)

CREATE TABLE dim_seller (
    seller_key        INTEGER PRIMARY KEY,
    source_seller_id  TEXT NOT NULL UNIQUE,      -- Olist seller_id
    zip_code_prefix   TEXT REFERENCES dim_location (zip_code_prefix)
);  -- Redshift: DISTKEY (seller_key)

CREATE TABLE fact_order_item (
    order_item_key       INTEGER PRIMARY KEY,
    order_id             TEXT    NOT NULL,       -- degenerate dimension
    order_item_seq       INTEGER NOT NULL,       -- order_item_id in Olist
    customer_key         INTEGER NOT NULL REFERENCES dim_customer (customer_key),
    product_key          INTEGER NOT NULL REFERENCES dim_product (product_key),
    seller_key           INTEGER NOT NULL REFERENCES dim_seller (seller_key),
    purchase_date_key    INTEGER NOT NULL REFERENCES dim_date (date_key),
    delivered_date_key   INTEGER REFERENCES dim_date (date_key),   -- NULL if not delivered
    order_status         TEXT    NOT NULL,
    price                REAL    NOT NULL CHECK (price >= 0),
    freight_value        REAL    NOT NULL CHECK (freight_value >= 0),
    delivery_days        INTEGER,                -- NULL if not delivered
    UNIQUE (order_id, order_item_seq)
);  -- Redshift: DISTKEY (order_id), SORTKEY (purchase_date_key)

CREATE TABLE fact_payment (
    order_id             TEXT    NOT NULL,
    payment_seq          INTEGER NOT NULL,
    purchase_date_key    INTEGER NOT NULL REFERENCES dim_date (date_key),
    payment_type         TEXT    NOT NULL,       -- credit_card, boleto, voucher, debit_card, not_defined
    payment_installments INTEGER NOT NULL CHECK (payment_installments >= 0),
    payment_value        REAL    NOT NULL CHECK (payment_value >= 0),
    PRIMARY KEY (order_id, payment_seq)
);  -- Redshift: DISTKEY (order_id)

CREATE TABLE fact_review (
    review_id            TEXT    PRIMARY KEY,
    order_id             TEXT    NOT NULL,
    customer_key         INTEGER NOT NULL REFERENCES dim_customer (customer_key),
    creation_date_key    INTEGER NOT NULL REFERENCES dim_date (date_key),
    review_score         INTEGER NOT NULL CHECK (review_score BETWEEN 1 AND 5),
    has_comment          INTEGER NOT NULL CHECK (has_comment IN (0, 1))
    -- Free-text review message is deliberately not loaded (may contain personal data).
);  -- Redshift: DISTKEY (order_id)

CREATE TABLE fact_retail_line (
    line_key          INTEGER PRIMARY KEY,
    invoice_no        TEXT    NOT NULL,          -- degenerate dimension
    line_no           INTEGER NOT NULL,
    customer_key      INTEGER REFERENCES dim_customer (customer_key),  -- NULL when CustomerID is missing
    product_key       INTEGER NOT NULL REFERENCES dim_product (product_key),
    invoice_date_key  INTEGER NOT NULL REFERENCES dim_date (date_key),
    country           TEXT,
    quantity          INTEGER NOT NULL,          -- negative for returns
    unit_price        REAL    NOT NULL CHECK (unit_price >= 0),
    line_amount       REAL    NOT NULL,          -- quantity * unit_price
    is_cancellation   INTEGER NOT NULL CHECK (is_cancellation IN (0, 1)),  -- invoice starts with 'C'
    UNIQUE (invoice_no, line_no)
);  -- Redshift: DISTKEY (invoice_no), SORTKEY (invoice_date_key)
