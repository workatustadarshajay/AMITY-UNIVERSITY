"""Spark cleaning rules on a small hand-made frame (run: python -m pytest tests)."""
import csv

import pytest

pyspark = pytest.importorskip("pyspark")
from pyspark.sql import SparkSession  # noqa: E402

from pipeline.transform import build_clean, to_warehouse_names  # noqa: E402

COLS = ["line_id", "InvoiceNo", "StockCode", "Description", "Quantity", "InvoiceDate", "UnitPrice", "CustomerID",
        "Country"]


@pytest.fixture(scope="module")
def spark():
    s = (SparkSession.builder.master("local[1]").appName("test")
         .config("spark.ui.enabled", "false").config("spark.sql.shuffle.partitions", "2").getOrCreate())
    s.sparkContext.setLogLevel("ERROR")
    yield s
    s.stop()


def _raw(spark, tmp_path):
    rows = [
        ("1-A-1", "100", "A", "ITEM A", "2", "2010-12-01 08:00:00", "2.50", "17850.0", "UK"),
        ("1-A-2", "100", "A", "ITEM A", "2", "2010-12-01 08:00:00", "2.50", "17850.0", "UK"),   # exact dup of line 1
        ("2-F-1", "101", "F", "", "1", "12/1/2010 9:30", "1.00", "", "UK"),   # missing desc & customer; "B" would be a non-product code                    # missing desc & customer
        ("3-C-1", "C102", "C", "ITEM C", "-1", "2010-12-01 10:00:00", "1.00", "17850.0", "UK"),  # cancellation
        ("4-POST-1", "103", "POST", "POSTAGE", "1", "2010-12-01 10:00:00", "18.00", "17850.0", "UK"),  # postage
        ("5-D-1", "104", "D", "DISCOUNT", "1", "2010-12-01 10:00:00", "-5.00", "17850.0", "UK"),  # non-positive
        ("6-E-1", "105", "E", "ITEM E", "1", "2010-12-01 10:00:00", "0.00", "17850.0", "UK"),   # free item
    ]
    # Read from a CSV file, as the Glue job does, so the test does not depend on Python workers.
    path = tmp_path / "raw.csv"
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(COLS)
        w.writerows(rows)
    return spark.read.option("header", True).csv(str(path))


def test_reject_reasons_and_counts(spark, tmp_path):
    clean, rejects, m = build_clean(_raw(spark, tmp_path))
    assert m["raw_rows"] == 7
    assert m["rejects_by_reason"] == {"cancellation": 1, "non_product_code": 1, "non_positive_price": 2}
    # the duplicate pair collapses to one line; the missing-description line has price 1.00 so it is kept
    assert m["exact_duplicates_removed"] == 1
    assert m["clean_rows"] == 2


def test_missing_customer_is_flagged_not_dropped(spark, tmp_path):
    clean, _, _ = build_clean(_raw(spark, tmp_path))
    row = clean.filter("InvoiceNo = '101'").collect()[0]
    assert row["flag_missing_customer"] is True
    assert row["Description"] == "UNKNOWN"          # missing description is filled, and flagged


def test_warehouse_names_are_snake_case(spark, tmp_path):
    clean, _, _ = build_clean(_raw(spark, tmp_path))
    names = to_warehouse_names(clean).columns
    assert "invoice_no" in names and "stock_code" in names and "InvoiceNo" not in names
