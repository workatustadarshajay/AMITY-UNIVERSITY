-- Redshift schema for the Online Retail pipeline.
-- raw_line   : line-level current state, maintained by CDC (MERGE in 03_cdc_merge.sql)
-- clean_line : output of the Glue ETL job, loaded by COPY (02_copy_from_s3.sql)
-- stg_cdc    : change set staged from S3 before the MERGE

CREATE TABLE IF NOT EXISTS raw_line (
    line_id      VARCHAR(64)   NOT NULL,    -- business key, assigned once at extract
    invoice_no   VARCHAR(16)   NOT NULL,
    stock_code   VARCHAR(32)   NOT NULL,
    description  VARCHAR(256),
    quantity     INTEGER       NOT NULL,
    invoice_date TIMESTAMP     NOT NULL,
    unit_price   DECIMAL(12,2) NOT NULL,
    customer_id  VARCHAR(16),               -- NULL for guest checkouts
    country      VARCHAR(64)
)
DISTKEY (invoice_no)
SORTKEY (invoice_date);

CREATE TABLE IF NOT EXISTS clean_line (
    line_id                  VARCHAR(64)   NOT NULL,
    invoice_no               VARCHAR(16)   NOT NULL,
    stock_code               VARCHAR(32)   NOT NULL,
    description              VARCHAR(256)  NOT NULL,
    quantity                 INTEGER       NOT NULL,
    invoice_date             TIMESTAMP     NOT NULL,
    unit_price               DECIMAL(12,2) NOT NULL,
    customer_id              VARCHAR(16),
    country                  VARCHAR(64),
    line_amount              DECIMAL(14,2) NOT NULL,
    invoice_month            CHAR(7)       NOT NULL,
    flag_missing_description BOOLEAN       NOT NULL,
    flag_missing_customer    BOOLEAN       NOT NULL,
    outlier_quantity         BOOLEAN       NOT NULL,
    outlier_price            BOOLEAN       NOT NULL
)
DISTKEY (invoice_no)
SORTKEY (invoice_date);

CREATE TABLE IF NOT EXISTS stg_cdc (
    line_id      VARCHAR(64)   NOT NULL,
    op           CHAR(1)       NOT NULL,    -- I = insert, U = update, D = delete
    invoice_no   VARCHAR(16),
    stock_code   VARCHAR(32),
    description  VARCHAR(256),
    quantity     INTEGER,
    invoice_date TIMESTAMP,
    unit_price   DECIMAL(12,2),
    customer_id  VARCHAR(16),
    country      VARCHAR(64)
);
