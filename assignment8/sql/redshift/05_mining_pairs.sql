-- Association rules for product pairs (Apriori level 2), computed in SQL.
-- Basket = invoice. Item = stock_code. Support = baskets containing the itemset / all baskets.
-- The threshold is set in the params CTE. pipeline/run_local.py runs the Python Apriori on the same data
-- with the same threshold and checks that the two outputs agree.

WITH params AS (
    SELECT 0.02 AS min_support
),
baskets AS (                                   -- distinct (basket, item) pairs
    SELECT DISTINCT invoice_no, stock_code FROM clean_line
),
n AS (
    SELECT COUNT(DISTINCT invoice_no) AS n_baskets FROM clean_line
),
item_count AS (
    SELECT stock_code, COUNT(*) AS cnt FROM baskets GROUP BY stock_code
),
pair_count AS (
    SELECT a.stock_code AS item_a, b.stock_code AS item_b, COUNT(*) AS cnt
      FROM baskets a
      JOIN baskets b ON a.invoice_no = b.invoice_no AND a.stock_code < b.stock_code
     GROUP BY a.stock_code, b.stock_code
),
frequent_pairs AS (
    SELECT p.item_a, p.item_b, p.cnt
      FROM pair_count p
      CROSS JOIN params
      CROSS JOIN n
     WHERE p.cnt >= CEIL(params.min_support * n.n_baskets)
)
SELECT fp.item_a,
       fp.item_b,
       fp.cnt                                                     AS pair_count,
       ROUND(1.0 * fp.cnt / n.n_baskets, 4)                       AS support,
       ROUND(1.0 * fp.cnt / ia.cnt, 4)                            AS confidence_a_to_b,
       ROUND(1.0 * fp.cnt / ib.cnt, 4)                            AS confidence_b_to_a,
       ROUND((1.0 * fp.cnt * n.n_baskets) / (ia.cnt * ib.cnt), 4) AS lift
  FROM frequent_pairs fp
  JOIN item_count ia ON ia.stock_code = fp.item_a
  JOIN item_count ib ON ib.stock_code = fp.item_b
  CROSS JOIN n
 ORDER BY lift DESC, pair_count DESC;
