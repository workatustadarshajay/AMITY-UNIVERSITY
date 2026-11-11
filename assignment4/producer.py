"""Replays the VIX daily history as a live event stream.

Each event is one trading day, sent in micro-batches with a pause between them, so the data arrives
over time like a live feed.

Local mode: SocketSink opens a TCP port; Spark Structured Streaming reads it with the `socket` source.
AWS mode:   events are put on an Amazon Kinesis stream (kinesis_io.py); a consumer reads them back and
            forwards them through the same SocketSink. The AWS path is not run in this project.
"""
import argparse
import csv
import json
import socket
import time
from pathlib import Path


def load_events(csv_path: Path, limit: int | None = None):
    """Read the DataHub VIX file (DATE, OPEN, HIGH, LOW, CLOSE) into event dicts, oldest first."""
    rows = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rows.append({"date": r["DATE"], "open": float(r["OPEN"]), "high": float(r["HIGH"]),
                         "low": float(r["LOW"]), "close": float(r["CLOSE"])})
    rows.sort(key=lambda e: e["date"])
    return rows[:limit] if limit else rows


class SocketSink:
    """Newline-delimited JSON over TCP. The listening socket accepts the connection that Spark opens."""

    def __init__(self, port: int, host: str = "127.0.0.1"):
        self.srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.srv.bind((host, port))
        self.srv.listen(1)
        self.conn = None

    def wait_for_spark(self):
        self.conn, _ = self.srv.accept()

    def send(self, events: list[dict]):
        now = time.time()
        payload = "".join(json.dumps({**e, "ingest_epoch": now}) + "\n" for e in events)
        self.conn.sendall(payload.encode("utf-8"))

    def close(self):
        if self.conn is not None:
            self.conn.close()
        self.srv.close()


def replay(events, send_batch, batch_size: int = 100, pause: float = 0.1, log=print):
    """Send events in micro-batches. send_batch(batch_events) does the delivery."""
    n_batches = 0
    for i in range(0, len(events), batch_size):
        send_batch(events[i:i + batch_size])
        n_batches += 1
        time.sleep(pause)
    log(f"  producer sent {len(events)} events in {n_batches} micro-batches")
    return n_batches


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default="data/vix-daily.csv")
    ap.add_argument("--port", type=int, default=9999)
    ap.add_argument("--batch-size", type=int, default=100)
    ap.add_argument("--pause", type=float, default=0.1)
    a = ap.parse_args()
    sink = SocketSink(a.port)
    print(f"listening on 127.0.0.1:{a.port}; start the Spark job now")
    sink.wait_for_spark()
    replay(load_events(Path(a.csv)), sink.send, a.batch_size, a.pause)
    sink.close()
