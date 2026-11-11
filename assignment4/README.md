# Assignment 4: Real-time Data Processing (Kinesis + Spark Streaming) vs Batch

A real-time pipeline and a batch pipeline over the same data (DataHub finance-vix daily file, VIX index),
with a comparison of their results.

## Status

| Part | Status |
|---|---|
| Batch pipeline (Spark, whole file) | Runs and is tested |
| Shared logic (`common.py`) and tests | Runs and is tested (4 checks) |
| Real-time pipeline (Spark Structured Streaming, local socket stand-in) | Code written; **not yet run** here. See "Running the streaming pipeline" |
| Amazon Kinesis ingestion (`kinesis_io.py`, `--mode aws`) | Code written; **not run** (needs AWS account and credentials) |
| Real-time vs batch comparison (`compare.py`) | Code written; needs a streaming run |

## Layout

| Path | What it is |
|---|---|
| `common.py` | Shared enrichment (regimes, alerts, range) and monthly aggregation, used by both pipelines |
| `producer.py` | Replays the VIX history as micro-batches over a TCP socket |
| `kinesis_io.py` | Amazon Kinesis helpers: create stream, publish events, consume events (not run here) |
| `jobs.py` | Streaming job (two queries) and batch job |
| `run_pipeline.py` | Runs everything: `--mode local` (default), `--mode aws`, or `--batch-only` |
| `compare.py` | Checks that streaming and batch results match, measures latency, draws figures |
| `report.py` | Builds `output/Assignment4_Report.pdf` |
| `tests/test_pipeline.py` | Checks on regimes, monthly aggregates, loader, socket sink |
| `data/vix-daily.csv` | DataHub VIX file (not in git; see Setup) |

## Setup

1. Java 17 or 21 is recommended for Spark 4.x. This project was run with OpenJDK 22.0.2 for the batch pipeline.
   Set `JAVA_HOME` to the JDK folder, for example:
   - Git Bash: `export JAVA_HOME="/c/Program Files/OpenLogic/jre-22.0.2.9-hotspot"`
   - PowerShell: `$env:JAVA_HOME = "C:\Program Files\OpenLogic\jre-22.0.2.9-hotspot"`
2. Python 3.10 or newer:

```bash
cd assignment4
pip install -r requirements.txt
```

3. Data: download https://datahub.io/core/finance-vix/r/vix-daily.csv and save it as `data/vix-daily.csv`.

## Run

```bash
python -m pytest tests                       # checks (about 20 seconds)
python run_pipeline.py --batch-only          # batch pipeline only; runs on Windows
```

### Running the streaming pipeline

The real-time pipeline uses Spark Structured Streaming. On Windows, Spark's streaming checkpoints need
Hadoop native binaries (`winutils.exe` and `hadoop.dll`). Without them the query fails with
`UnsatisfiedLinkError: NativeIO$Windows.access0`. On Linux (or in Google Colab) this is not needed:

```bash
python run_pipeline.py                       # local mode: producer -> socket -> Spark Streaming -> compare
```

This writes `output/stream_events/`, `output/stream_monthly/`, `output/comparison.json` and figures. Then:

```bash
python report.py --out output
```

### AWS mode (not run in this project)

```bash
export AWS_ACCESS_KEY_ID=...  AWS_SECRET_ACCESS_KEY=...   # or: aws configure
python run_pipeline.py --mode aws --stream-name vix-stream --region us-east-1
```

This creates a Kinesis data stream (one shard, billed per hour while it exists), publishes the events with
`PutRecords`, reads them back with a consumer, and feeds them into the same Spark job. Delete the stream
afterwards to stop charges:

```bash
aws kinesis delete-stream --stream-name vix-stream --region us-east-1
```

## How the comparison works

- **Per-event results**: each day is enriched by both pipelines. `compare.py` checks the regime, the alert flag,
  the close price and the range percentage are the same for every date.
- **Monthly results**: the streaming job re-emits a month each time it changes. The last emission per month is
  compared with the batch result for that month.
- **Latency**: for each event, the time from the producer's ingest timestamp to the time Spark processed its
  micro-batch.
- **Time to result**: the batch job's wall time, and the streaming end-to-end time (first event sent to last result).

## Notes

- The producer replays a daily file. The "live" feed is simulated by pausing between micro-batches.
- Spark's socket source is meant for testing. It is not fault-tolerant, so use Kinesis or Kafka for production.
- Results are written as JSON lines, one file per micro-batch, from `toPandas()`. That avoids Spark's Hadoop file committer,
  which also needs the Windows binaries.
