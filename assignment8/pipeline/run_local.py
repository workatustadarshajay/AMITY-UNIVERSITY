"""Run the whole workflow locally, in the same order as the AWS version.

    python -m pipeline.run_local --min-support 0.02

Stand-ins for AWS (same logic, different place):
    S3 bucket            -> s3_local/ folder
    AWS Glue (PySpark)   -> pipeline.transform.build_clean on local Spark
    Amazon Redshift      -> DuckDB, running the same CDC MERGE, load and mining SQL.
                            DISTKEY and SORTKEY clauses are removed before DuckDB runs the DDL.

Order: Glue clean (day 2) -> warehouse: CDC merge of day 1 + ops, load clean, explore, pair mining
-> Python Apriori and similarity -> outputs in output/.
Run extract and cdc first (see README).
"""
import argparse
import json
import re
import time
from pathlib import Path

import duckdb
import pandas as pd

from pipeline.apriori import association_rules, frequent_itemsets
from pipeline.similarity import pair_table, product_baskets
from pipeline.transform import build_clean, read_raw, to_warehouse_names

ROOT = Path(__file__).resolve().parents[1]
SQL_DIR = ROOT / "sql" / "redshift"
def duck_sql(path):
    """Redshift DDL to DuckDB: remove the DISTKEY and SORTKEY clauses."""
    text = Path(path).read_text(encoding="utf-8")
    text = re.sub(r"DISTKEY \([^)]*\)", "", text)
    return re.sub(r"SORTKEY \([^)]*\)", "", text)


def statements(sql_text):
    """Split a SQL file into (label, statement). The label is the E-number of the block it belongs to."""
    out, label = [], "stmt"
    for block in sql_text.split(";"):
        found = re.findall(r"--\s*(E\d+)\.", block)
        if found:
            label = found[0]
        body = "\n".join(line for line in block.splitlines() if not line.strip().startswith("--")).strip()
        if body:
            out.append((label, body))
    return out


def wh_frame(df, with_op=False):
    """Pandas frame with warehouse column names and types, as loaded into raw_line / stg_cdc."""
    cols = ["line_id"] + (["op"] if with_op else []) + RENAME_WH
    out = pd.DataFrame({"line_id": df["line_id"].astype(str)})
    if with_op:
        out["op"] = df["op"].astype(str)
    out["invoice_no"] = df["InvoiceNo"].astype(str)
    out["stock_code"] = df["StockCode"].astype(str)
    out["description"] = df["Description"]
    out["quantity"] = df["Quantity"].astype("int64")
    out["invoice_date"] = pd.to_datetime(df["InvoiceDate"])
    out["unit_price"] = df["UnitPrice"].astype(float).round(2)
    out["customer_id"] = df["CustomerID"].map(lambda v: None if pd.isna(v) or v == "" else str(v).removesuffix(".0"))
    out["country"] = df["Country"]
    return out[cols]


RENAME_WH = ["invoice_no", "stock_code", "description", "quantity", "invoice_date", "unit_price",
             "customer_id", "country"]


def run_warehouse(s3, out, con, clean_pd, min_support):
    schema = duck_sql(SQL_DIR / "01_schema.sql")
    con.execute(schema)

    # 1. Day-1 state into raw_line (what the warehouse held before the day-2 changes).
    day1 = pd.read_csv(s3 / "raw" / "day1" / "online_retail.csv", dtype=str)
    con.register("day1_df", wh_frame(day1))
    con.execute("INSERT INTO raw_line BY NAME SELECT * FROM day1_df")

    # 2. CDC: stage the ops and run the MERGE from sql/redshift/03_cdc_merge.sql.
    ops = pd.read_csv(s3 / "cdc" / "day2" / "cdc_ops.csv", dtype=str)
    con.register("ops_df", wh_frame(ops, with_op=True))
    con.execute("INSERT INTO stg_cdc BY NAME SELECT * FROM ops_df")
    merge_sql = (SQL_DIR / "03_cdc_merge.sql").read_text(encoding="utf-8")
    con.execute(merge_sql)

    # Check: after the merge, raw_line must equal the day-2 snapshot.
    day2 = pd.read_csv(s3 / "raw" / "day2" / "online_retail.csv", dtype=str)
    expected = wh_frame(day2).sort_values("line_id").reset_index(drop=True)
    got = con.execute("SELECT * FROM raw_line ORDER BY line_id").df()
    cols = [c for c in expected.columns]
    same_rows = len(got) == len(expected)
    same_values = same_rows and got[cols].fillna("<NULL>").astype(str).reset_index(drop=True).equals(
        expected[cols].fillna("<NULL>").astype(str))
    cdc_check = {"ops": ops["op"].value_counts().to_dict(), "raw_line_rows_after_merge": int(len(got)),
                 "day2_rows": int(len(expected)), "rows_match": bool(same_rows), "values_match": bool(same_values)}
    (out / "cdc" / "cdc_check.json").write_text(json.dumps(cdc_check, indent=2), encoding="utf-8")

    # 3. Load the Glue output (the equivalent of COPY ... FORMAT AS PARQUET).
    con.register("clean_df", clean_pd)
    con.execute("INSERT INTO clean_line BY NAME SELECT * FROM clean_df")

    # 4. Exploration: each E-block of 04_explore.sql becomes one CSV.
    for label, body in statements((SQL_DIR / "04_explore.sql").read_text(encoding="utf-8")):
        df = con.execute(body).df()
        df.to_csv(out / "explore" / f"{label}.csv", index=False)

    # 5. Pair mining in SQL, with the same threshold as the Python run.
    mining_sql = (SQL_DIR / "05_mining_pairs.sql").read_text(encoding="utf-8")
    mining_sql = mining_sql.replace("SELECT 0.02 AS min_support", f"SELECT {min_support} AS min_support")
    sql_pairs = con.execute(mining_sql).df()
    sql_pairs.to_csv(out / "mining" / "sql_pairs.csv", index=False)
    return cdc_check, sql_pairs


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--s3", default=str(ROOT / "s3_local"))
    p.add_argument("--out", default=str(ROOT / "output"))
    p.add_argument("--min-support", type=float, default=0.02)
    p.add_argument("--max-len", type=int, default=3)
    p.add_argument("--sample-fraction", type=float, default=1.0)
    p.add_argument("--seed", type=int, default=42)
    a = p.parse_args()
    s3, out = Path(a.s3), Path(a.out)
    for sub in ["explore", "mining", "quality", "cdc"]:
        (out / sub).mkdir(parents=True, exist_ok=True)
    timings = {}

    # ---- Glue step: clean the day-2 snapshot with Spark (same functions as the Glue job) ----
    from pyspark.sql import SparkSession
    spark = (SparkSession.builder.master("local[*]").appName("online-retail-local")
             .config("spark.ui.enabled", "false").config("spark.sql.shuffle.partitions", "8").getOrCreate())
    spark.sparkContext.setLogLevel("ERROR")
    t = time.time()
    raw = read_raw(spark, str(s3 / "raw" / "day2" / "online_retail.csv"))
    clean, rejects, metrics = build_clean(raw, a.sample_fraction, a.seed)
    clean_pd = to_warehouse_names(clean).toPandas()
    rejects_pd = to_warehouse_names(rejects).toPandas()
    spark.stop()
    timings["glue_clean_s"] = round(time.time() - t, 1)
    pdir = s3 / "processed" / "online_retail"
    pdir.mkdir(parents=True, exist_ok=True)
    clean_pd.to_parquet(pdir / "clean.parquet", index=False)
    rejects_pd.to_parquet(pdir / "rejects.parquet", index=False)
    (out / "quality" / "quality_metrics.json").write_text(json.dumps(metrics, indent=2, default=str),
                                                          encoding="utf-8")

    # ---- Warehouse step ----
    t = time.time()
    con = duckdb.connect()
    cdc_check, sql_pairs = run_warehouse(s3, out, con, clean_pd, a.min_support)
    timings["warehouse_s"] = round(time.time() - t, 1)

    # ---- Apriori on the same baskets (invoice -> set of products) ----
    t = time.time()
    baskets_df = con.execute("SELECT DISTINCT invoice_no, stock_code FROM clean_line").df()
    baskets = [frozenset(g) for _, g in baskets_df.groupby("invoice_no")["stock_code"]]
    n = len(baskets)
    itemsets = frequent_itemsets(baskets, a.min_support, max_len=a.max_len)
    rules = association_rules(itemsets, n, min_confidence=0.5)
    timings["apriori_s"] = round(time.time() - t, 1)

    names = clean_pd[clean_pd["description"] != "UNKNOWN"].groupby("stock_code")["description"].min().to_dict()
    names = {k: names.get(k, k) for k in {i for b in baskets for i in b}}
    for col in ["antecedent", "consequent"]:
        rules[col] = rules[col].map(lambda s: " + ".join(f"{x} {names.get(x, '')}".strip() for x in s.split(" + ")))
    rules.to_csv(out / "mining" / "apriori_rules.csv", index=False)
    pd.DataFrame([{"items": " + ".join(sorted(k)), "size": len(k), "count": v, "support": v / n}
                  for k, v in itemsets.items()]).sort_values(["size", "count"], ascending=[True, False]).to_csv(
        out / "mining" / "apriori_itemsets.csv", index=False)

    # Check: Apriori pairs must equal the SQL pairs (same baskets, same threshold).
    py_pairs = {tuple(sorted(k)): v for k, v in itemsets.items() if len(k) == 2}
    sql_map = {tuple(sorted((r.item_a, r.item_b))): r.pair_count for r in sql_pairs.itertuples()}
    pairs_check = {"python_pairs": len(py_pairs), "sql_pairs": len(sql_map),
                   "identical": py_pairs == sql_map}
    (out / "mining" / "pairs_check.json").write_text(json.dumps(pairs_check, indent=2), encoding="utf-8")

    # ---- Similarity between the products with the most baskets ----
    t = time.time()
    counts = {k: v for k, v in itemsets.items() if len(k) == 1}
    top = [next(iter(k)) for k, _ in sorted(counts.items(), key=lambda kv: -kv[1])[:20]]
    idx = product_baskets(baskets)
    sim = pair_table(idx, top)
    sim["name_a"] = sim["item_a"].map(lambda x: names.get(x, x))
    sim["name_b"] = sim["item_b"].map(lambda x: names.get(x, x))
    sim.to_csv(out / "mining" / "similarity_top20.csv", index=False)
    timings["similarity_s"] = round(time.time() - t, 1)

    summary = {"baskets": n, "min_support": a.min_support, "max_len": a.max_len,
               "frequent_itemsets": len(itemsets), "rules_min_conf_0.5": len(rules),
               "glue_metrics": metrics, "cdc": cdc_check, "pairs_check": pairs_check, "timings_s": timings}
    (out / "run_summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(json.dumps({"cdc_values_match": cdc_check["values_match"], "pairs_identical": pairs_check["identical"],
                      "baskets": n, "rules": len(rules), "timings_s": timings}, indent=2))


if __name__ == "__main__":
    main()
