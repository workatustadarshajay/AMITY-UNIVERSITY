"""Checks for the pipeline.   python -m pytest tests   (from assignment4/; needs Java and PySpark)"""
import json
import os
import socket
import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("PYSPARK_PYTHON", sys.executable)
os.environ.setdefault("PYSPARK_DRIVER_PYTHON", sys.executable)

import producer  # noqa: E402
from common import enrich, monthly  # noqa: E402


def _spark():
    from pyspark.sql import SparkSession
    s = SparkSession.builder.master("local[2]").appName("tests").getOrCreate()
    s.sparkContext.setLogLevel("ERROR")
    return s


def test_regimes_and_alerts():
    spark = _spark()
    try:
        from pyspark.sql import Row
        df = spark.createDataFrame([
            Row(date="2020-01-02", open=1.0, high=12.0, low=10.0, close=11.0, ingest_epoch=0.0),
            Row(date="2020-01-03", open=1.0, high=26.0, low=24.0, close=25.0, ingest_epoch=0.0),
            Row(date="2020-01-06", open=1.0, high=36.0, low=34.0, close=35.0, ingest_epoch=0.0),
        ])
        got = {r["date"]: (r["regime"], r["alert"]) for r in enrich(df).collect()}
        assert got["2020-01-02"] == ("calm", False)
        assert got["2020-01-03"] == ("elevated", False)
        assert got["2020-01-06"] == ("stress", True)
    finally:
        spark.stop()


def test_monthly_aggregates_are_calendar_months():
    spark = _spark()
    try:
        from pyspark.sql import Row
        df = spark.createDataFrame([
            Row(date="2020-01-02", open=1.0, high=2.0, low=1.0, close=10.0, ingest_epoch=0.0),
            Row(date="2020-01-03", open=1.0, high=2.0, low=1.0, close=20.0, ingest_epoch=0.0),
            Row(date="2020-02-03", open=1.0, high=2.0, low=1.0, close=40.0, ingest_epoch=0.0),
        ])
        rows = {str(r["month"])[:10]: r for r in monthly(enrich(df)).collect()}
        assert rows["2020-01-01"]["days"] == 2
        assert rows["2020-01-01"]["avg_close"] == 15.0
        assert rows["2020-02-01"]["alert_days"] == 1
    finally:
        spark.stop()


def test_load_events_sorted_and_typed():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "vix.csv"
        p.write_text("DATE,OPEN,HIGH,LOW,CLOSE\n2020-01-03,1,2,0.5,1.5\n2020-01-02,1,2,0.5,1.25\n", encoding="utf-8")
        ev = producer.load_events(p)
        assert [e["date"] for e in ev] == ["2020-01-02", "2020-01-03"]
        assert ev[0]["close"] == 1.25


def test_socket_sink_sends_ndjson_with_ingest_time():
    sink = producer.SocketSink(port=0)
    port = sink.srv.getsockname()[1]
    received = []

    def client():
        c = socket.create_connection(("127.0.0.1", port))
        buf = b""
        while buf.count(b"\n") < 2:
            buf += c.recv(4096)
        received.extend(buf.decode().splitlines())
        c.close()

    t = threading.Thread(target=client)
    t.start()
    sink.wait_for_spark()
    sink.send([{"date": "2020-01-02", "close": 1.0}, {"date": "2020-01-03", "close": 2.0}])
    t.join(timeout=10)
    sink.close()
    rows = [json.loads(line) for line in received]
    assert [r["date"] for r in rows] == ["2020-01-02", "2020-01-03"]
    assert all("ingest_epoch" in r for r in rows)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
