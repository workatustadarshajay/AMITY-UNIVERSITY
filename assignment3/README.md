# Assignment 3: In-Memory Computation with Apache Spark

Spark workflow on the UCI Iris dataset: Spark context and session, RDDs and DataFrames, transformations and actions, caching for in-memory computation, data lineage, and the Spark UI.

## Layout

| Path | What it is |
|---|---|
| `iris_spark.py` | The whole workflow: RDD, DataFrame/SQL, caching benchmark, lineage, Spark UI export |
| `report.py` | Builds `output/Assignment3_Report.pdf` from the outputs |
| `tests/test_iris_spark.py` | Checks: RDD counts and averages, DataFrame vs SQL, window results |
| `data/iris.csv` | Iris data (not stored in git; see below) |
| `output/` | Results: `metrics.json`, `lineage.txt`, `figures/`, `spark_ui/`, `run.log`, `tests.log`, `Assignment3_Report.pdf` |

## Setup

1. **Java 17 or 21 is recommended** (Spark 4.x officially supports 17 and 21). This project was run and tested with OpenJDK 22.0.2, which also works. Install a JDK, then set `JAVA_HOME` to its folder.
   - Windows (Git Bash): `export JAVA_HOME="/c/Program Files/OpenLogic/jre-22.0.2.9-hotspot"`
   - Windows (PowerShell): `$env:JAVA_HOME = "C:\Program Files\OpenLogic\jre-22.0.2.9-hotspot"`
   - Check it with `java -version`.
2. Python 3.10 or newer, then:

```bash
cd assignment3
pip install -r requirements.txt
```

3. The dataset: download the Iris CSV from https://archive.ics.uci.edu/static/public/53/data.csv, save it as `data/iris.csv`, and check it has 151 lines (a header plus 150 rows).

The script sets `PYSPARK_PYTHON` to the Python that runs it. This avoids the Windows "Python was not found" error from the Microsoft Store alias.

## Run

```bash
python -m pytest tests                              # checks (about 1 minute)
python iris_spark.py --data data/iris.csv --out output
python report.py --out output
```

Options:
- `--scale N`: replicates the data N times for the caching benchmark (default 2000, so 300,000 rows).
- `--pause`: keeps the Spark UI running until you press Enter. Open the URL printed in the log (usually http://localhost:4040), take screenshots of the Jobs, Stages, Storage and SQL pages, then press Enter.

The full run takes about a minute.

## What the script shows

1. **Spark context**: session setup, configuration, parallelism, and Java/Spark versions.
2. **RDDs**: `textFile`, `filter`, `map`, `mapValues`, `reduceByKey` vs `groupByKey`, `flatMap`, and actions (`count`, `first`, `collect`, `countByKey`, `reduce`).
3. **DataFrames**: explicit schema, `filter`, `withColumn`, `groupBy`/`agg`, window functions, broadcast join, and the same aggregation in Spark SQL.
4. **In-memory computation**: the same aggregation with and without `persist(MEMORY_ONLY)` on 300,000 rows.
5. **Lineage**: RDD `toDebugString()` for each result, and `EXPLAIN EXTENDED` plans for the DataFrame and SQL queries. These are written to `output/lineage.txt`.
6. **Spark UI**: the REST API for jobs, stages, storage, executors and SQL is saved to `output/spark_ui/`.

## Notes

- Iris has only 150 rows, so the caching benchmark replicates it. Timings come from one local machine and vary between runs.
- Spark UI screenshots are not generated automatically. Run with `--pause` and capture them from a browser.
- Titanic and NYC Taxi (Kaggle) were not used. Only the Iris dataset was analysed.
