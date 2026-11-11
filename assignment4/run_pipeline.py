"""Run the real-time pipeline and the batch pipeline on the same VIX data, then compare them.

    python run_pipeline.py                 # local mode (no AWS): producer -> socket -> Spark Structured Streaming
    python run_pipeline.py --mode aws --stream-name vix-stream --region us-east-1   # needs AWS (not run here)
"""
import argparse
import json
import os
import shutil
import sys
import threading
import time
from pathlib import Path

os.environ.setdefault("PYSPARK_PYTHON", sys.executable)
os.environ.setdefault("PYSPARK_DRIVER_PYTHON", sys.executable)

from pyspark.sql import SparkSession  # noqa: E402

import compare  # noqa: E402
import producer  # noqa: E402
from jobs import run_batch, start_stream, stop_stream  # noqa: E402


def get_spark():
    spark = (SparkSession.builder.master("local[*]").appName("VIX-RealTime-vs-Batch")
             .config("spark.sql.shuffle.partitions", "4")
             .getOrCreate())
    spark.sparkContext.setLogLevel("WARN")
    return spark


def run_batch_only(csv_path: Path, out: Path):
    """Batch pipeline alone (no streaming, no AWS). Used when Spark streaming cannot run on this machine."""
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    spark = get_spark()
    metrics = {"mode": "batch-only", "spark_version": spark.version,
               "java_version": spark.sparkContext._jvm.System.getProperty("java.version")}
    metrics["batch"] = run_batch(spark, csv_path, out)
    (out / "metrics.json").write_text(json.dumps(metrics, indent=2, default=str), encoding="utf-8")
    spark.stop()


def run(mode: str, csv_path: Path, out: Path, work: Path, port: int, batch_size: int, pause: float,
        stream_name: str | None, region: str | None):
    for d in (out, work):
        if d.exists():
            shutil.rmtree(d)
    out.mkdir(parents=True)
    work.mkdir(parents=True)
    events = producer.load_events(csv_path)
    metrics = {"mode": mode, "events": len(events), "batch_size": batch_size, "pause_seconds": pause,
               "socket_port": port}

    print(f"1. Start Spark and streaming queries ({mode} mode)")
    spark = get_spark()
    metrics["spark_version"] = spark.version
    metrics["java_version"] = spark.sparkContext._jvm.System.getProperty("java.version")
    sink = producer.SocketSink(port)                       # listening; Spark connects when the query starts
    q_events, q_monthly = start_stream(spark, port, out, work)
    sink.wait_for_spark()

    print("2. Produce the live stream")
    t_stream = time.time()
    if mode == "local":
        producer.replay(events, sink.send, batch_size, pause, log=print)
    else:  # aws: events -> Kinesis -> consumer -> socket
        import kinesis_io
        kin = kinesis_io.client(region)
        kinesis_io.ensure_stream(kin, stream_name)
        consumer = threading.Thread(target=kinesis_io.consume, args=(kin, stream_name, sink.send, 30.0))
        consumer.start()
        producer.replay(events, lambda b: kinesis_io.put_events(kin, stream_name, b), batch_size, pause,
                        log=print)
        consumer.join()

    print("3. Wait for the streaming queries to finish")
    progress = stop_stream(q_events, q_monthly)
    sink.close()
    metrics["stream_wall_seconds"] = round(time.time() - t_stream, 3)
    metrics["stream_micro_batches"] = len(progress)
    metrics["stream_progress"] = progress

    print("4. Batch pipeline on the same file")
    metrics["batch"] = run_batch(spark, csv_path, out)

    (out / "metrics.json").write_text(json.dumps(metrics, indent=2, default=str), encoding="utf-8")
    spark.stop()

    print("5. Compare real-time and batch results")
    compare.main(out)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["local", "aws"], default="local")
    ap.add_argument("--csv", default="data/vix-daily.csv")
    ap.add_argument("--out", default="output")
    ap.add_argument("--work", default="work")
    ap.add_argument("--port", type=int, default=9999)
    ap.add_argument("--batch-size", type=int, default=100)
    ap.add_argument("--pause", type=float, default=0.1)
    ap.add_argument("--stream-name", default="vix-stream")
    ap.add_argument("--region", default="us-east-1")
    ap.add_argument("--batch-only", action="store_true", help="run only the batch pipeline")
    a = ap.parse_args()
    if a.batch_only:
        run_batch_only(Path(a.csv), Path(a.out))
    else:
        run(a.mode, Path(a.csv), Path(a.out), Path(a.work), a.port, a.batch_size, a.pause, a.stream_name,
            a.region)
