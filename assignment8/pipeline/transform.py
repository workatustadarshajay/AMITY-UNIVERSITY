"""Transform: the cleaning logic as PySpark DataFrame functions.

The same functions run inside the AWS Glue job (glue/glue_etl_job.py) and in the local run
(pipeline/run_local.py). Only the read and write steps differ.

Steps: standardise types -> fill missing descriptions -> tag rejects (cancellations, non-positive
quantity or price, non-product codes) -> drop exact duplicates -> flag outliers with IQR fences ->
optional stratified sample by country.
"""
import json

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F

PAYLOAD = ["InvoiceNo", "StockCode", "Description", "Quantity", "InvoiceDate", "UnitPrice", "CustomerID", "Country"]

# Stock codes that are postage, fees, adjustments or test entries rather than products.
NON_PRODUCT_RE = r"(?i)^(POST|D|M|BANK CHARGES|PADS|DOT|CRUK|C2|AMAZONFEE|B|S|ADJUST2?|TEST\d+|GIFT_\d{4}_\d+)$"


def read_raw(spark: SparkSession, path: str) -> DataFrame:
    return spark.read.option("header", True).option("inferSchema", False).csv(path)


def standardise(df: DataFrame) -> DataFrame:
    ts = F.coalesce(F.to_timestamp("InvoiceDate", "yyyy-MM-dd HH:mm:ss"),
                    F.to_timestamp("InvoiceDate", "M/d/yyyy H:mm"))
    customer = F.regexp_replace(F.trim("CustomerID"), r"\.0$", "")
    return (df
            .withColumn("line_id", F.trim("line_id"))
            .withColumn("InvoiceNo", F.trim("InvoiceNo"))
            .withColumn("StockCode", F.upper(F.trim("StockCode")))
            .withColumn("Description", F.trim("Description"))
            .withColumn("Quantity", F.col("Quantity").cast("int"))
            .withColumn("UnitPrice", F.col("UnitPrice").cast("double"))
            .withColumn("InvoiceDate", ts)
            .withColumn("CustomerID", F.when(customer == "", None).otherwise(customer))
            .withColumn("Country", F.trim("Country")))


def fill_missing(df: DataFrame) -> DataFrame:
    return (df
            .withColumn("flag_missing_description", F.col("Description").isNull() | (F.col("Description") == ""))
            .withColumn("Description", F.when(F.col("flag_missing_description"), F.lit("UNKNOWN"))
                        .otherwise(F.col("Description")))
            .withColumn("flag_missing_customer", F.col("CustomerID").isNull()))


def tag_rejects(df: DataFrame) -> DataFrame:
    reason = (F.when(F.col("InvoiceNo").startswith("C"), F.lit("cancellation"))
              .when(F.col("Quantity") <= 0, F.lit("non_positive_quantity"))
              .when(F.col("UnitPrice") <= 0, F.lit("non_positive_price"))
              .when(F.col("StockCode").rlike(NON_PRODUCT_RE), F.lit("non_product_code")))
    return df.withColumn("reject_reason", reason)


def dedupe(df: DataFrame) -> DataFrame:
    """Exact duplicates on every business column; the smallest line_id is kept, so the result is deterministic."""
    return (df.groupBy(*PAYLOAD)
            .agg(F.min("line_id").alias("line_id"),
                 F.max("flag_missing_description").alias("flag_missing_description"),
                 F.max("flag_missing_customer").alias("flag_missing_customer")))


def flag_outliers(df: DataFrame):
    """IQR fences on Quantity and UnitPrice. Outliers are flagged, not removed: wholesale orders are real."""
    q_qty, q_px = df.approxQuantile(["Quantity", "UnitPrice"], [0.25, 0.75], 0.001)
    fence_qty = q_qty[1] + 1.5 * (q_qty[1] - q_qty[0])
    fence_px = q_px[1] + 1.5 * (q_px[1] - q_px[0])
    out = (df
           .withColumn("outlier_quantity", F.col("Quantity") > F.lit(fence_qty))
           .withColumn("outlier_price", F.col("UnitPrice") > F.lit(fence_px))
           .withColumn("line_amount", F.col("Quantity") * F.col("UnitPrice"))
           .withColumn("invoice_month", F.date_format("InvoiceDate", "yyyy-MM")))
    return out, {"quantity_fence_iqr": fence_qty, "unit_price_fence_iqr": fence_px}


def sample_by_country(df: DataFrame, fraction: float, seed: int) -> DataFrame:
    if fraction >= 1.0:
        return df
    countries = [r[0] for r in df.select("Country").distinct().collect()]
    return df.sampleBy("Country", {c: fraction for c in countries}, seed)


def build_clean(raw: DataFrame, sample_fraction: float = 1.0, seed: int = 42):
    """Return (clean, rejects, metrics). clean has one row per kept line; rejects has one row per dropped line."""
    # AWS Glue 4.0 (Spark 3.3) runs with ANSI SQL mode off, so a date that does not match the first format
    # returns NULL and the fallback format is tried. Spark 4 turns ANSI on by default, so set it off here
    # to behave the same locally.
    raw.sparkSession.conf.set("spark.sql.ansi.enabled", "false")
    metrics = {"raw_rows": raw.count()}
    df = fill_missing(standardise(raw))
    tagged = tag_rejects(df).cache()

    rejects = tagged.filter(F.col("reject_reason").isNotNull())
    metrics["rejects_by_reason"] = {r["reject_reason"]: r["count"] for r in
                                    rejects.groupBy("reject_reason").count().collect()}
    kept = tagged.filter(F.col("reject_reason").isNull()).drop("reject_reason")
    metrics["kept_before_dedupe"] = kept.count()

    deduped = dedupe(kept)
    metrics["exact_duplicates_removed"] = metrics["kept_before_dedupe"] - deduped.count()
    flagged, fences = flag_outliers(deduped)
    metrics.update(fences)
    flagged = flagged.cache()
    metrics["clean_rows"] = flagged.count()
    metrics["outlier_quantity_rows"] = flagged.filter("outlier_quantity").count()
    metrics["outlier_price_rows"] = flagged.filter("outlier_price").count()
    metrics["missing_customer_rows"] = flagged.filter("flag_missing_customer").count()
    metrics["missing_description_rows"] = flagged.filter("flag_missing_description").count()

    clean = sample_by_country(flagged, sample_fraction, seed)
    metrics["sample_fraction"] = sample_fraction
    metrics["sampled_rows"] = clean.count()
    return clean, rejects, metrics


WAREHOUSE_NAMES = {
    "line_id": "line_id", "InvoiceNo": "invoice_no", "StockCode": "stock_code", "Description": "description",
    "Quantity": "quantity", "InvoiceDate": "invoice_date", "UnitPrice": "unit_price", "CustomerID": "customer_id",
    "Country": "country", "flag_missing_description": "flag_missing_description",
    "flag_missing_customer": "flag_missing_customer", "outlier_quantity": "outlier_quantity",
    "outlier_price": "outlier_price", "line_amount": "line_amount", "invoice_month": "invoice_month",
    "reject_reason": "reject_reason",
}


def to_warehouse_names(df: DataFrame) -> DataFrame:
    """snake_case names, so Redshift COPY from Parquet matches columns by name."""
    keep = [c for c in df.columns if c in WAREHOUSE_NAMES]
    return df.select([F.col(c).alias(WAREHOUSE_NAMES[c]) for c in keep])


def run_pipeline(spark: SparkSession, raw_path: str, out_path: str, rejects_path: str, metrics_path: str,
                 sample_fraction: float = 1.0, seed: int = 42) -> dict:
    """Glue entry: read raw, write clean and rejects as Parquet and the metrics as one JSON file."""
    clean, rejects, metrics = build_clean(read_raw(spark, raw_path), sample_fraction, seed)
    to_warehouse_names(clean).write.mode("overwrite").parquet(out_path)
    to_warehouse_names(rejects).write.mode("overwrite").parquet(rejects_path)
    spark.sparkContext.parallelize([json.dumps(metrics, default=str)], 1).saveAsTextFile(metrics_path)
    return metrics
