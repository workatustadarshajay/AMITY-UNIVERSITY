"""Real-time (Structured Streaming) and batch jobs. Both use common.enrich and common.monthly.

Results are written as JSON lines, one part file per micro-batch (stream) or one file (batch).
Results are collected with toPandas() before writing: they are small (one row per day or month),
and this avoids Spark's Hadoop file committer, which needs native Windows binaries.
"""
import time
from pathlib import Path

from pyspark.sql import functions as F

from common import EVENT_SCHEMA, enrich, monthly


def _text_dates(df, cols):
    """Format timestamp columns as yyyy-MM-dd strings so JSON output is plain text."""
    for c in cols:
        df = df.withColumn(c, F.date_format(c, "yyyy-MM-dd"))
    return df


def _write_part(pdf, out_dir: Path, name: str):
    out_dir.mkdir(parents=True, exist_ok=True)
    pdf.to_json(out_dir / name, orient="records", lines=True)


def start_stream(spark, port: int, out_dir: Path, work_dir: Path, trigger_seconds: float = 1.0):
    """Two continuous queries on the same socket input:
      - events:  every event enriched, written as it arrives (append mode)
      - monthly: calendar-month aggregates, re-emitted when a month changes (update mode)
    Returns (events_query, monthly_query)."""
    raw = (spark.readStream.format("socket")
           .option("host", "127.0.0.1").option("port", port).load())
    parsed = raw.select(F.from_json("value", EVENT_SCHEMA).alias("e")).select("e.*")
    ev = enrich(parsed)

    def write_events(df, batch_id):
        now = time.time()
        pdf = (_text_dates(df, ["event_ts"])
               .withColumn("batch_id", F.lit(batch_id))
               .withColumn("processed_epoch", F.lit(now))
               .withColumn("latency_s", F.lit(now) - F.col("ingest_epoch"))
               .toPandas())
        _write_part(pdf, out_dir / "stream_events", f"part-{batch_id:05d}.json")

    def write_monthly(df, batch_id):
        pdf = (_text_dates(df, ["month"]).withColumn("batch_id", F.lit(batch_id)).toPandas())
        _write_part(pdf, out_dir / "stream_monthly", f"part-{batch_id:05d}.json")

    q_events = (ev.writeStream.foreachBatch(write_events)
                .option("checkpointLocation", str(work_dir / "ckpt_events"))
                .trigger(processingTime=f"{trigger_seconds} seconds")
                .start())
    q_monthly = (monthly(ev).writeStream.outputMode("update")
                 .foreachBatch(write_monthly)
                 .option("checkpointLocation", str(work_dir / "ckpt_monthly"))
                 .trigger(processingTime=f"{trigger_seconds} seconds")
                 .start())
    return q_events, q_monthly


def stop_stream(q_events, q_monthly):
    """Wait until all received data is processed, then stop. Returns per-batch progress."""
    q_events.processAllAvailable()
    q_monthly.processAllAvailable()
    progress = [{"batch_id": p.get("batchId"), "input_rows": p.get("numInputRows"),
                 "duration_ms": (p.get("durationMs") or {}).get("triggerExecution")}
                for p in q_events.recentProgress]
    q_events.stop()
    q_monthly.stop()
    return progress


def run_batch(spark, csv_path: Path, out_dir: Path, log=print):
    """Read the whole file once, then compute the same results as the stream."""
    t0 = time.perf_counter()
    raw = (spark.read.option("header", "true").csv(str(csv_path))
           .toDF("date", "open", "high", "low", "close")
           .select("date", *[F.col(c).cast("double").alias(c) for c in ["open", "high", "low", "close"]]))
    ev = enrich(raw)
    pdf_ev = _text_dates(ev, ["event_ts"]).toPandas()
    pdf_m = _text_dates(monthly(ev), ["month"]).toPandas()
    _write_part(pdf_ev, out_dir / "batch_events", "part-00000.json")
    _write_part(pdf_m, out_dir / "batch_monthly", "part-00000.json")
    wall = time.perf_counter() - t0
    log(f"  batch: {len(pdf_ev)} rows in {wall:.2f}s")
    return {"rows": int(len(pdf_ev)), "wall_seconds": round(wall, 3)}
