"""Amazon Kinesis helpers: create the stream, publish events, and read them back into a local folder.

NOT RUN in this project: running it needs an AWS account with credentials and creates billable
resources (a Kinesis shard costs money per hour). The local pipeline (producer.py -> local folder ->
Spark) is the tested path. Enable this path with `run_pipeline.py --mode aws`.

Credentials come from the standard AWS chain (AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY, or `aws configure`).
"""
import json
import time

import boto3


def client(region: str):
    return boto3.client("kinesis", region_name=region)


def ensure_stream(kin, name: str, shards: int = 1):
    """Create the stream if it does not exist, and wait until it is ACTIVE."""
    try:
        kin.describe_stream_summary(StreamName=name)
        return
    except kin.exceptions.ResourceNotFoundException:
        pass
    kin.create_stream(StreamName=name, ShardCount=shards)
    kin.get_waiter("stream_exists").wait(StreamName=name)


def put_events(kin, name: str, events: list[dict]):
    """Publish events. PutRecords accepts at most 500 records per call."""
    for i in range(0, len(events), 500):
        chunk = events[i:i + 500]
        resp = kin.put_records(StreamName=name, Records=[
            {"Data": json.dumps(e).encode("utf-8"), "PartitionKey": e["date"]} for e in chunk])
        if resp["FailedRecordCount"]:
            raise RuntimeError(f"{resp['FailedRecordCount']} records failed to publish")


def consume(kin, name: str, on_records, idle_seconds: float = 30.0):
    """Read every shard from the oldest record. Calls on_records(list_of_events) for each batch read.
    Stops after `idle_seconds` with no new records."""
    shards = kin.list_shards(StreamName=name)["Shards"]
    iterators = {s["ShardId"]: kin.get_shard_iterator(
        StreamName=name, ShardId=s["ShardId"], ShardIteratorType="TRIM_HORIZON")["ShardIterator"]
        for s in shards}
    last_data = time.time()
    while time.time() - last_data < idle_seconds:
        got = []
        for sid, it in list(iterators.items()):
            if it is None:
                continue
            resp = kin.get_records(ShardIterator=it, Limit=1000)
            iterators[sid] = resp.get("NextShardIterator")
            got += [json.loads(r["Data"]) for r in resp["Records"]]
        if got:
            on_records(got)
            last_data = time.time()
        else:
            time.sleep(1.0)
