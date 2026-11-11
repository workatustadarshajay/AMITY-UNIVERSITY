"""Shared logic for the real-time (Spark Structured Streaming) and batch pipelines.

Both jobs call the same functions, so any difference in their output comes from how the data arrives,
not from different business rules.
"""
from pyspark.sql import functions as F
from pyspark.sql.types import DoubleType, StringType, StructField, StructType

STRESS_LEVEL = 30.0    # VIX at or above this is treated as a stress alert
ELEVATED_LEVEL = 20.0  # VIX at or above this is elevated volatility

# schema of one event as the producer sends it (stream) and of the file rows (batch)
EVENT_SCHEMA = StructType([
    StructField("date", StringType(), False),
    StructField("open", DoubleType(), True),
    StructField("high", DoubleType(), True),
    StructField("low", DoubleType(), True),
    StructField("close", DoubleType(), True),
    StructField("ingest_epoch", DoubleType(), True),  # set by the producer; used for stream latency only
])


def enrich(df):
    """Per-event enrichment. Stateless, so it works record by record and on whole files."""
    return (df
            .withColumn("event_ts", F.to_timestamp("date", "yyyy-MM-dd"))
            .withColumn("regime", F.when(F.col("close") >= STRESS_LEVEL, "stress")
                                   .when(F.col("close") >= ELEVATED_LEVEL, "elevated")
                                   .otherwise("calm"))
            .withColumn("alert", F.col("close") >= STRESS_LEVEL)
            .withColumn("range_pct", F.round((F.col("high") - F.col("low")) / F.col("close") * 100, 4)))


def monthly(df):
    """Calendar-month aggregates. Same groupBy for stream (update mode) and batch."""
    return (df.withColumn("month", F.date_trunc("month", "event_ts"))
              .groupBy("month")
              .agg(F.count("*").alias("days"),
                   F.round(F.avg("close"), 4).alias("avg_close"),
                   F.max("close").alias("max_close"),
                   F.sum(F.col("alert").cast("int")).alias("alert_days")))
    # no orderBy here: sorting a streaming aggregate is not allowed; sort when reading results
