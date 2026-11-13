-- Exploration queries on clean_line. Each block is one result table used in the report.

-- E1. Headline numbers
SELECT COUNT(DISTINCT invoice_no)  AS invoices,
       COUNT(DISTINCT customer_id) AS known_customers,
       COUNT(DISTINCT stock_code)  AS products,
       COUNT(DISTINCT country)     AS countries,
       ROUND(SUM(line_amount), 2)  AS revenue_gbp,
       ROUND(100.0 * SUM(CASE WHEN flag_missing_customer THEN 1 ELSE 0 END) / COUNT(*), 1) AS pct_lines_no_customer
  FROM clean_line;

-- E2. Monthly revenue and invoices
SELECT invoice_month,
       ROUND(SUM(line_amount), 2)  AS revenue_gbp,
       COUNT(DISTINCT invoice_no)  AS invoices
  FROM clean_line
 GROUP BY invoice_month
 ORDER BY invoice_month;

-- E3. Top 10 countries by revenue
SELECT country,
       ROUND(SUM(line_amount), 2)  AS revenue_gbp,
       COUNT(DISTINCT invoice_no)  AS invoices
  FROM clean_line
 GROUP BY country
 ORDER BY revenue_gbp DESC
 LIMIT 10;

-- E4. Top 10 products by revenue (name: smallest non-placeholder description)
SELECT stock_code,
       MIN(CASE WHEN description <> 'UNKNOWN' THEN description END) AS product_name,
       SUM(quantity)               AS units,
       ROUND(SUM(line_amount), 2)  AS revenue_gbp
  FROM clean_line
 GROUP BY stock_code
 ORDER BY revenue_gbp DESC
 LIMIT 10;

-- E5. Basket size: distinct products per invoice
SELECT CASE WHEN n <= 5 THEN '01-05' WHEN n <= 10 THEN '06-10' WHEN n <= 20 THEN '11-20'
            WHEN n <= 50 THEN '21-50' ELSE '51+' END AS basket_products,
       COUNT(*) AS invoices
  FROM (SELECT invoice_no, COUNT(DISTINCT stock_code) AS n FROM clean_line GROUP BY invoice_no) b
 GROUP BY 1
 ORDER BY 1;

-- E6. Weekday and hour of purchase (lines)
SELECT EXTRACT(DOW FROM invoice_date)  AS weekday_0_sun,
       EXTRACT(HOUR FROM invoice_date) AS hour_of_day,
       COUNT(*) AS lines
  FROM clean_line
 GROUP BY 1, 2
 ORDER BY 1, 2;

-- E7. Outlier flags (flagged, not removed)
SELECT SUM(CASE WHEN outlier_quantity THEN 1 ELSE 0 END) AS outlier_quantity_lines,
       SUM(CASE WHEN outlier_price    THEN 1 ELSE 0 END) AS outlier_price_lines,
       COUNT(*)                                          AS lines
  FROM clean_line;
