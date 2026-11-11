"""Assignment 3: in-memory computation with Apache Spark on the UCI Iris dataset.

Covers: Spark context and session setup, RDDs and DataFrames, transformations and actions,
caching (in-memory computation), data lineage (RDD debug strings and query plans), and an
export of the Spark UI REST API (jobs, stages, storage, SQL).

    python iris_spark.py --data data/iris.csv --out output [--scale 2000] [--pause]
"""
import argparse
import json
import os
import statistics
import sys
import time
import urllib.request
from pathlib import Path

# Spark workers must use the same Python as this script (Windows often has no bare `python` on PATH).
os.environ.setdefault("PYSPARK_PYTHON", sys.executable)
os.environ.setdefault("PYSPARK_DRIVER_PYTHON", sys.executable)

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from pyspark import StorageLevel  # noqa: E402
from pyspark.sql import SparkSession, Window, functions as F  # noqa: E402
from pyspark.sql.types import DoubleType, StringType, StructField, StructType  # noqa: E402

FEATURES = ["sepal_length", "sepal_width", "petal_length", "petal_width"]
COLUMNS = FEATURES + ["species"]
SPECIES_INFO = {
    "Iris-setosa": "Small flowers, easiest to separate",
    "Iris-versicolor": "Medium flowers, overlaps with virginica",
    "Iris-virginica": "Largest flowers",
}


def get_spark(master: str = "local[*]") -> SparkSession:
    spark = (SparkSession.builder.master(master)
             .appName("Iris-InMemory")
             .config("spark.sql.shuffle.partitions", "8")
             .getOrCreate())
    spark.sparkContext.setLogLevel("WARN")
    return spark


def timed(fn, repeats: int = 3) -> float:
    """Median wall-clock seconds over `repeats` runs."""
    times = []
    for _ in range(repeats):
        t = time.perf_counter()
        fn()
        times.append(time.perf_counter() - t)
    return statistics.median(times)


# ---------- 1. RDDs: transformations and actions ----------

def rdd_section(spark: SparkSession, path: Path, log=print):
    sc = spark.sparkContext
    m = {}
    raw = sc.textFile(str(path))                                   # transformation chain starts; lazy
    header = raw.first()                                           # action: reads only the first line
    rows = raw.filter(lambda line: line != header)                 # transformation: drop header
    recs = (rows.map(lambda line: line.split(","))                 # transformation: split fields
                .map(lambda r: (r[4], [float(x) for x in r[:4]])))  # transformation: (species, features)
    m["partitions"] = raw.getNumPartitions()
    m["rows"] = recs.count()                                       # action: runs the whole chain
    m["first_record"] = recs.first()                               # action

    # reduceByKey: map-side combine, then one shuffle
    sums = (recs.mapValues(lambda f: (f[2], 1))
                .reduceByKey(lambda a, b: (a[0] + b[0], a[1] + b[1])))
    m["avg_petal_length_by_species"] = {k: round(s / c, 3) for k, (s, c) in sums.collect()}  # action
    m["count_by_species"] = dict(recs.countByKey())                 # action

    # groupByKey gives the same answer but moves every value across the network: compare the plans
    grouped = recs.mapValues(lambda f: f[2]).groupByKey().mapValues(lambda vs: round(sum(vs) / len(vs), 3))
    m["groupByKey_matches_reduceByKey"] = dict(grouped.collect()) == m["avg_petal_length_by_species"]

    # flatMap + reduceByKey: maximum of each feature across all flowers
    maxes = (recs.flatMap(lambda kv: [(i, v) for i, v in enumerate(kv[1])])
                 .reduceByKey(max).sortByKey().collect())          # actions
    m["max_per_feature"] = {FEATURES[i]: v for i, v in maxes}

    # aggregate: one value per partition, merged by the driver
    m["sum_sepal_length"] = recs.map(lambda kv: kv[1][0]).reduce(lambda a, b: a + b)  # action

    lineage = {
        "reduceByKey_lineage": sums.toDebugString(),
        "groupByKey_lineage": grouped.toDebugString(),
    }
    lineage = {k: (v.decode() if isinstance(v, bytes) else v) for k, v in lineage.items()}
    log(f"  RDD: {m['rows']} rows, {m['partitions']} partitions, averages {m['avg_petal_length_by_species']}")
    return m, lineage, sums


# ---------- 2. DataFrames and Spark SQL ----------

def dataframe_section(spark: SparkSession, path: Path, log=print):
    schema = StructType([StructField(c, DoubleType() if c in FEATURES else StringType(), True)
                         for c in COLUMNS])
    # header is read as a data row and removed, because the file's header names differ from ours
    df = (spark.read.option("header", "false").schema(schema).csv(str(path))  # lazy
          .filter(F.col("species") != "class"))
    m = {"schema": df.schema.simpleString()}

    # derived column (narrow transformation) and a filter
    enriched = (df.withColumn("petal_ratio", F.round(F.col("petal_length") / F.col("petal_width"), 3))
                  .filter(F.col("sepal_length") >= 5.0))
    m["rows_after_filter"] = enriched.count()                                 # action

    # group and aggregate (wide transformation: shuffle)
    summary = (df.groupBy("species")
                 .agg(F.count("*").alias("n"),
                      *[F.round(F.avg(c), 3).alias(f"avg_{c}") for c in FEATURES],
                      F.round(F.stddev("petal_length"), 3).alias("stddev_petal_length"))
                 .orderBy("species"))
    m["summary"] = [r.asDict() for r in summary.collect()]                    # action

    # window function: top 3 flowers by sepal length inside each species
    w = Window.partitionBy("species").orderBy(F.desc("sepal_length"))
    top3 = (df.withColumn("rank", F.row_number().over(w))
              .filter(F.col("rank") <= 3).orderBy("species", "rank"))
    m["top3_by_sepal_length"] = [r.asDict() for r in top3.collect()]

    # join with a small lookup table (broadcast, because the lookup is tiny)
    lookup = spark.createDataFrame(list(SPECIES_INFO.items()), ["species", "description"])
    joined = summary.join(F.broadcast(lookup), "species").select("species", "n", "description")
    m["joined"] = [r.asDict() for r in joined.collect()]

    # the same aggregation through Spark SQL, which shares the same optimizer
    df.createOrReplaceTempView("iris")
    sql = ("SELECT species, ROUND(AVG(petal_length), 3) AS avg_petal_length "
           "FROM iris GROUP BY species ORDER BY species")
    m["sql_result"] = [r.asDict() for r in spark.sql(sql).collect()]

    lineage = {
        "dataframe_aggregation_plan": spark.sql("EXPLAIN EXTENDED " + sql).first()[0],
        "window_query_plan": spark.sql(
            "EXPLAIN EXTENDED SELECT species, sepal_length, "
            "ROW_NUMBER() OVER (PARTITION BY species ORDER BY sepal_length DESC) AS rank FROM iris"
        ).first()[0],
    }
    log(f"  DataFrame: schema {m['schema']}, filter kept {m['rows_after_filter']} rows")
    return m, lineage


# ---------- 3. In-memory computation: cache vs recompute ----------

def in_memory_section(spark: SparkSession, path: Path, scale: int, log=print):
    """Iris has only 150 rows, so the benefit of caching cannot be seen at that size. The data is
    therefore replicated `scale` times (cross join) and aggregated with and without cache()."""
    schema = StructType([StructField(c, DoubleType() if c in FEATURES else StringType(), True)
                         for c in COLUMNS])

    def build():
        base = (spark.read.option("header", "false").schema(schema).csv(str(path))
                .filter(F.col("species") != "class"))
        return base.crossJoin(spark.range(scale).withColumnRenamed("id", "replica"))

    query = lambda d: d.groupBy("species").agg(F.avg("petal_length"), F.avg("sepal_width")).collect()

    big = build()
    m = {"rows": 150 * scale, "storage_level_before_cache": str(big.storageLevel)}
    m["recompute_seconds"] = timed(lambda: query(build()))  # re-reads the CSV every time

    big = build().persist(StorageLevel.MEMORY_ONLY)
    big.count()                                             # materialise the cache once
    m["storage_level_after_cache"] = str(big.storageLevel)
    m["cached_seconds"] = timed(lambda: query(big))
    m["speedup"] = round(m["recompute_seconds"] / m["cached_seconds"], 2)
    log(f"  in-memory: recompute {m['recompute_seconds']:.3f}s, cached {m['cached_seconds']:.3f}s "
        f"({m['speedup']}x) on {m['rows']:,} rows")
    return m, big  # caller releases the cache after the UI export, so the UI still shows it


# ---------- 4. Spark UI export ----------

def export_ui(spark: SparkSession, out: Path, log=print):
    """Save the Spark UI REST API (jobs, stages, storage, executors, SQL) while the application runs."""
    ui = spark.sparkContext.uiWebUrl
    ui_dir = out / "spark_ui"
    ui_dir.mkdir(parents=True, exist_ok=True)
    try:
        app_id = json.load(urllib.request.urlopen(f"{ui}/api/v1/applications", timeout=10))[0]["id"]
    except Exception as e:  # UI may be disabled
        log(f"  Spark UI not reachable: {e}")
        return None
    base = f"{ui}/api/v1/applications/{app_id}"
    saved = {}
    for name in ["jobs", "stages", "storage/rdd", "executors", "sql"]:
        try:
            data = json.load(urllib.request.urlopen(f"{base}/{name}", timeout=10))
            fname = ui_dir / (name.replace("/", "_") + ".json")
            fname.write_text(json.dumps(data, indent=2), encoding="utf-8")
            saved[name] = len(data) if isinstance(data, list) else "ok"
        except Exception as e:
            saved[name] = f"error: {e}"
    log(f"  Spark UI at {ui}; exported {saved}")
    return {"ui_url": ui, "app_id": app_id, "exported": saved}


# ---------- figures ----------

def figures(m, rdd_m, out: Path):
    fig_dir = out / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)

    avg = rdd_m["avg_petal_length_by_species"]
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.bar(list(avg), list(avg.values()), color=["#4C72B0", "#55A868", "#C44E52"])
    ax.set_ylabel("Average petal length (cm)")
    ax.set_title("RDD reduceByKey: average petal length per species")
    fig.tight_layout()
    fig.savefig(fig_dir / "01_rdd_species_averages.png", dpi=130)
    plt.close(fig)

    im = m["in_memory"]
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.bar(["recompute from CSV", "cached in memory"], [im["recompute_seconds"], im["cached_seconds"]],
           color=["#BBBBBB", "#4C72B0"])
    ax.set_ylabel("Median seconds per aggregation")
    ax.set_title(f"In-memory computation ({im['rows']:,} rows)")
    fig.tight_layout()
    fig.savefig(fig_dir / "02_cache_vs_recompute.png", dpi=130)
    plt.close(fig)

    # lineage diagram: the logical sequence behind the RDD result
    steps = [("textFile", "source"), ("filter", "transform"), ("map (split)", "transform"),
             ("map (key, value)", "transform"), ("mapValues", "transform"),
             ("reduceByKey", "shuffle"), ("collect", "action")]
    colors = {"source": "#DDE4EE", "transform": "#FFFFFF", "shuffle": "#F6D6A8", "action": "#B9E0B0"}
    fig, ax = plt.subplots(figsize=(12, 2.4))
    ax.set_xlim(0, len(steps) * 1.7)
    ax.set_ylim(0, 1)
    ax.axis("off")
    for i, (name, kind) in enumerate(steps):
        x = i * 1.7 + 0.1
        ax.add_patch(plt.Rectangle((x, 0.3), 1.45, 0.4, fc=colors[kind], ec="black"))
        ax.text(x + 0.72, 0.5, name, ha="center", va="center", fontsize=9)
        ax.text(x + 0.72, 0.15, kind, ha="center", va="center", fontsize=7, color="#555555")
        if i < len(steps) - 1:
            ax.annotate("", xy=(x + 1.7, 0.5), xytext=(x + 1.5, 0.5),
                        arrowprops=dict(arrowstyle="->"))
    ax.set_title("Lineage of the RDD result (read from the source, one shuffle, then the action)")
    fig.tight_layout()
    fig.savefig(fig_dir / "03_lineage_diagram.png", dpi=130)
    plt.close(fig)


def main(data: str, out: str, scale: int, pause: bool):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    path = Path(data)

    print("1. Start Spark")
    spark = get_spark()
    sc = spark.sparkContext
    metrics = {"spark_version": spark.version, "master": sc.master,
               "java_version": sc._jvm.System.getProperty("java.version"),
               "python_version": sys.version.split()[0], "default_parallelism": sc.defaultParallelism}
    print(f"  Spark {spark.version} on Java {metrics['java_version']}, parallelism {sc.defaultParallelism}")

    print("2. RDD transformations and actions")
    rdd_m, rdd_lineage, _ = rdd_section(spark, path)
    metrics["rdd"] = rdd_m

    print("3. DataFrames and Spark SQL")
    df_m, df_lineage = dataframe_section(spark, path)
    metrics["dataframe"] = df_m

    print("4. In-memory computation")
    metrics["in_memory"], cached_df = in_memory_section(spark, path, scale)

    print("5. Spark UI export")
    metrics["spark_ui"] = export_ui(spark, out)
    cached_df.unpersist()

    (out / "metrics.json").write_text(json.dumps(metrics, indent=2, default=str), encoding="utf-8")
    lineage_text = []
    for title, text in {**{"RDD: " + k: v for k, v in rdd_lineage.items()},
                        **{"DataFrame: " + k: v for k, v in df_lineage.items()}}.items():
        lineage_text.append(f"===== {title} =====\n{text}\n")
    (out / "lineage.txt").write_text("\n".join(lineage_text), encoding="utf-8")

    figures(metrics, rdd_m, out)
    print(f"Done. Metrics: {out / 'metrics.json'}  Lineage: {out / 'lineage.txt'}")

    if pause and metrics["spark_ui"]:
        input(f"Spark UI is at {metrics['spark_ui']['ui_url']} - take screenshots, then press Enter to stop Spark... ")
    spark.stop()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/iris.csv")
    ap.add_argument("--out", default="output")
    ap.add_argument("--scale", type=int, default=2000, help="replication factor for the caching benchmark")
    ap.add_argument("--pause", action="store_true", help="keep Spark UI alive until Enter is pressed")
    a = ap.parse_args()
    main(a.data, a.out, a.scale, a.pause)
