"""Checks for the Assignment 6 models.

    python -m pytest tests

Runs models/physical.sql in SQLite with foreign keys on, loads a small sample, checks that
constraints reject bad rows, runs a star-schema query, and checks the logical model CSV.
"""
import csv
import sqlite3
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DDL = (ROOT / "models" / "physical.sql").read_text(encoding="utf-8")
LOGICAL = ROOT / "models" / "logical_model.csv"


@pytest.fixture()
def db():
    con = sqlite3.connect(":memory:")
    con.execute("PRAGMA foreign_keys = ON")
    con.executescript(DDL)
    con.executescript("""
        INSERT INTO dim_date VALUES (20171015, '2017-10-15', 2017, 4, 10, 15, 7, 1),
                                    (20171020, '2017-10-20', 2017, 4, 10, 20, 5, 0);
        INSERT INTO dim_location VALUES ('01001', 'sao paulo', 'SP', 'BR', -23.55, -46.63);
        INSERT INTO dim_customer (customer_key, source_system, source_customer_id, zip_code_prefix, country)
             VALUES (1, 'olist', 'cust-A', '01001', NULL),
                    (2, 'uci_retail', '17850', NULL, 'United Kingdom');
        INSERT INTO dim_product (product_key, source_system, source_product_id, category_en, weight_g)
             VALUES (10, 'olist', 'prod-1', 'toys', 500),
                    (20, 'uci_retail', '85123A', NULL, NULL);
        INSERT INTO dim_seller (seller_key, source_seller_id, zip_code_prefix) VALUES (100, 'sell-1', '01001');
        INSERT INTO fact_order_item (order_item_key, order_id, order_item_seq, customer_key, product_key,
                                     seller_key, purchase_date_key, delivered_date_key, order_status,
                                     price, freight_value, delivery_days)
             VALUES (1, 'ord-1', 1, 1, 10, 100, 20171015, 20171020, 'delivered', 80.0, 12.5, 5),
                    (2, 'ord-2', 1, 1, 10, 100, 20171015, NULL, 'shipped', 40.0, 7.5, NULL);
        INSERT INTO fact_retail_line (line_key, invoice_no, line_no, customer_key, product_key,
                                      invoice_date_key, country, quantity, unit_price, line_amount, is_cancellation)
             VALUES (1, '536365', 1, 2, 20, 20171015, 'United Kingdom', 6, 2.55, 15.3, 0),
                    (2, 'C536379', 1, NULL, 20, 20171015, 'United Kingdom', -1, 2.55, -2.55, 1);
    """)
    yield con
    con.close()


def test_ddl_creates_all_tables_and_no_foreign_key_violations(db):
    tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert tables == {"dim_date", "dim_location", "dim_customer", "dim_product", "dim_seller",
                      "fact_order_item", "fact_payment", "fact_review", "fact_retail_line"}
    assert db.execute("PRAGMA foreign_key_check").fetchall() == []


def test_constraints_reject_bad_rows(db):
    with pytest.raises(sqlite3.IntegrityError):  # review score outside 1..5
        db.execute("INSERT INTO fact_review VALUES ('r1', 'ord-1', 1, 20171020, 6, 0)")
    with pytest.raises(sqlite3.IntegrityError):  # negative price
        db.execute("INSERT INTO fact_order_item VALUES (9, 'ord-9', 1, 1, 10, 100, 20171015, NULL, 'x', -1, 0, NULL)")
    with pytest.raises(sqlite3.IntegrityError):  # unknown product
        db.execute("INSERT INTO fact_order_item VALUES (9, 'ord-9', 1, 1, 999, 100, 20171015, NULL, 'x', 1, 0, NULL)")
    with pytest.raises(sqlite3.IntegrityError):  # duplicate order line
        db.execute("INSERT INTO fact_order_item VALUES (9, 'ord-1', 1, 1, 10, 100, 20171015, NULL, 'x', 1, 0, NULL)")


def test_star_query_revenue_by_category_and_month(db):
    rows = db.execute("""
        SELECT p.category_en, d.year, d.month, SUM(f.price + f.freight_value) AS revenue, COUNT(*) AS items
          FROM fact_order_item f
          JOIN dim_product p ON p.product_key = f.product_key
          JOIN dim_date d ON d.date_key = f.purchase_date_key
         GROUP BY p.category_en, d.year, d.month
    """).fetchall()
    assert rows == [("toys", 2017, 10, pytest.approx(140.0), 2)]


def test_retail_unknown_customer_is_allowed_and_cancellations_are_flagged(db):
    row = db.execute("""
        SELECT SUM(line_amount), SUM(is_cancellation), SUM(customer_key IS NULL)
          FROM fact_retail_line
    """).fetchone()
    assert row == (pytest.approx(12.75), 1, 1)


def test_logical_model_is_complete():
    with LOGICAL.open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert rows, "logical_model.csv is empty"
    expected = ["entity", "attribute", "key", "logical_type", "nullable", "source", "description"]
    assert list(rows[0].keys()) == expected
    entities = {r["entity"] for r in rows}
    for entity in entities:
        keys = [r["key"] for r in rows if r["entity"] == entity]
        assert "PK" in keys, f"{entity} has no primary key"
    assert {"customer", "orders", "order_item", "product", "seller", "order_payment",
            "order_review", "location", "retail_invoice", "retail_line", "retail_product"} <= entities
