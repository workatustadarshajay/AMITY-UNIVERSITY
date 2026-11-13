-- CDC apply: bring raw_line to the source state using the staged change set.
-- One row per line_id in stg_cdc, so each key matches at most once.

MERGE INTO raw_line
USING stg_cdc s
ON raw_line.line_id = s.line_id
WHEN MATCHED AND s.op = 'D' THEN DELETE
WHEN MATCHED AND s.op = 'U' THEN UPDATE SET
    invoice_no = s.invoice_no, stock_code = s.stock_code, description = s.description,
    quantity = s.quantity, invoice_date = s.invoice_date, unit_price = s.unit_price,
    customer_id = s.customer_id, country = s.country
WHEN NOT MATCHED AND s.op = 'I' THEN INSERT
    (line_id, invoice_no, stock_code, description, quantity, invoice_date, unit_price, customer_id, country)
    VALUES (s.line_id, s.invoice_no, s.stock_code, s.description, s.quantity, s.invoice_date,
            s.unit_price, s.customer_id, s.country);
