"""Checks for the Spark workflow.   python -m pytest tests   (from assignment3/; needs Java and data/iris.csv)"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("PYSPARK_PYTHON", sys.executable)
os.environ.setdefault("PYSPARK_DRIVER_PYTHON", sys.executable)

import iris_spark as I  # noqa: E402

DATA = ROOT / "data" / "iris.csv"


def _spark():
    return I.get_spark("local[2]")


def test_rdd_counts_and_averages():
    spark = _spark()
    try:
        m, lineage, _ = I.rdd_section(spark, DATA, log=lambda *_: None)
        assert m["rows"] == 150
        assert m["count_by_species"] == {"Iris-setosa": 50, "Iris-versicolor": 50, "Iris-virginica": 50}
        assert abs(m["avg_petal_length_by_species"]["Iris-setosa"] - 1.464) < 1e-3
        assert m["groupByKey_matches_reduceByKey"]
        assert "reduceByKey" in lineage["reduceByKey_lineage"]
    finally:
        spark.stop()


def test_dataframe_filter_and_sql_agree():
    spark = _spark()
    try:
        m, lineage = I.dataframe_section(spark, DATA, log=lambda *_: None)
        assert 0 < m["rows_after_filter"] < 150  # the sepal_length >= 5.0 filter removes some rows
        sql_avgs = {r["species"]: r["avg_petal_length"] for r in m["sql_result"]}
        api_avgs = {r["species"]: r["avg_petal_length"] for r in m["summary"]}  # DataFrame API path
        assert sql_avgs == api_avgs
        assert abs(sql_avgs["Iris-virginica"] - 5.552) < 1e-3
        assert all(r["rank"] <= 3 for r in m["top3_by_sepal_length"])
        assert len(m["top3_by_sepal_length"]) == 9
        assert "Exchange" in lineage["dataframe_aggregation_plan"] or "Aggregate" in lineage["dataframe_aggregation_plan"]
    finally:
        spark.stop()


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
