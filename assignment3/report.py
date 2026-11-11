"""Build the Assignment 3 PDF report from output/metrics.json, output/lineage.txt and output/figures.

    python report.py --out output
"""
import argparse
import json
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import Image, PageBreak, Paragraph, Preformatted, SimpleDocTemplate, Spacer, Table, TableStyle

styles = getSampleStyleSheet()
H1, H2, BODY = styles["Heading1"], styles["Heading2"], styles["BodyText"]
MONO = styles["Code"]


def table(rows, widths=None):
    t = Table(rows, colWidths=widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#DDE4EE")),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    return t


def fig(path: Path, width=16 * cm):
    w, h = ImageReader(str(path)).getSize()
    return Image(str(path), width=width, height=width * h / w)


def code_block(text: str, max_lines: int = 40):
    lines = text.splitlines()[:max_lines]
    return Preformatted("\n".join(line[:110] for line in lines), MONO)


def main(out: str):
    out = Path(out)
    m = json.loads((out / "metrics.json").read_text(encoding="utf-8"))
    lineage = (out / "lineage.txt").read_text(encoding="utf-8")
    figs = out / "figures"
    rdd, df, im = m["rdd"], m["dataframe"], m["in_memory"]
    ui = m.get("spark_ui") or {}

    s = []
    s.append(Paragraph("In-Memory Computation with Apache Spark: Iris Dataset", H1))
    s.append(Paragraph("Assignment No. 3", BODY))
    s.append(Spacer(1, 0.3 * cm))

    s.append(Paragraph("1. Environment", H2))
    s.append(table([
        ["Item", "Value"],
        ["Apache Spark", m["spark_version"]],
        ["Master", m["master"]],
        ["Java", m["java_version"]],
        ["Python", m["python_version"]],
        ["Default parallelism", str(m["default_parallelism"])],
        ["Dataset", "UCI Iris, 150 rows, 4 features, 3 classes"],
    ], widths=[5 * cm, 11 * cm]))
    s.append(Spacer(1, 0.2 * cm))
    s.append(Paragraph(
        "All code in this report was executed locally on a Windows 11 machine. The Spark context runs in "
        "local mode, with all executors inside one JVM. Local mode shows how Spark behaves, but it does not "
        "measure cluster performance.", BODY))

    s.append(Paragraph("2. Spark context and RDDs", H2))
    s.append(Paragraph(
        f"<font face='Courier'>SparkSession</font> wraps the <font face='Courier'>SparkContext</font>. The file is "
        f"read with <font face='Courier'>textFile</font>, which creates an RDD with {rdd['partitions']} partitions. "
        f"Nothing is read until the first action runs. The pipeline has {rdd['rows']} records. "
        "Transformations (map, filter, mapValues, flatMap) build the plan; actions (count, first, collect, "
        "countByKey, reduce) run it.", BODY))
    rows = [["Operation", "Type", "Result"],
            ["filter (drop header)", "transformation", "lazy"],
            ["map (split fields)", "transformation", "lazy"],
            ["map (species, features)", "transformation", "lazy"],
            ["count()", "action", str(rdd["rows"])],
            ["first()", "action", str(rdd["first_record"][0]) + ", " + ", ".join(str(x) for x in rdd["first_record"][1])],
            ["reduceByKey (average petal length)", "transformation + action", "see table below"],
            ["countByKey()", "action", str(rdd["count_by_species"])],
            ["flatMap + reduceByKey + sortByKey", "transformations + action", "per-feature maximum"],
            ["reduce (sum of sepal length)", "action", f"{rdd['sum_sepal_length']:.1f}"]]
    s.append(table(rows, widths=[6.2 * cm, 4.6 * cm, 5.2 * cm]))
    s.append(Spacer(1, 0.2 * cm))
    avg_rows = [["Species", "Average petal length (cm)"]] + [
        [k, f"{v:.3f}"] for k, v in rdd["avg_petal_length_by_species"].items()]
    s.append(table(avg_rows, widths=[6 * cm, 6 * cm]))
    s.append(Paragraph(
        f"Max per feature: {', '.join(f'{k} {v:.1f}' for k, v in rdd['max_per_feature'].items())}. "
        f"groupByKey gives the same averages as reduceByKey: <b>{rdd['groupByKey_matches_reduceByKey']}</b>. "
        "reduceByKey combines values inside each partition before the shuffle, so it moves less data than groupByKey.",
        BODY))
    s.append(fig(figs / "01_rdd_species_averages.png", width=11 * cm))
    s.append(PageBreak())

    s.append(Paragraph("3. DataFrames and Spark SQL", H2))
    s.append(Paragraph(
        f"Schema: <font face='Courier'>{df['schema']}</font>. The file is read with an explicit schema, so types "
        "are not inferred. The filter keeps flowers with sepal length of at least 5.0 cm "
        f"({df['rows_after_filter']} rows). A derived column (petal ratio) is added without a shuffle.", BODY))
    rows = [["Species", "n", "avg sepal length", "avg sepal width", "avg petal length", "avg petal width",
             "stddev petal length"]]
    for r in df["summary"]:
        rows.append([r["species"], r["n"], r["avg_sepal_length"], r["avg_sepal_width"],
                     r["avg_petal_length"], r["avg_petal_width"], r["stddev_petal_length"]])
    s.append(table(rows, widths=[3.2 * cm, 1 * cm, 2.4 * cm, 2.4 * cm, 2.4 * cm, 2.4 * cm, 2.6 * cm]))
    s.append(Spacer(1, 0.2 * cm))
    s.append(Paragraph("Top 3 flowers by sepal length in each species (window function row_number):", BODY))
    rows = [["Species", "Rank", "Sepal length", "Petal length"]] + [
        [r["species"], r["rank"], r["sepal_length"], r["petal_length"]] for r in df["top3_by_sepal_length"]]
    s.append(table(rows, widths=[5 * cm, 2 * cm, 3.5 * cm, 3.5 * cm]))
    s.append(Spacer(1, 0.2 * cm))
    s.append(Paragraph(
        "The join with a small lookup table uses a broadcast hint, so the lookup is copied to each executor "
        "instead of shuffling the large side. The same aggregation in Spark SQL is planned by the same optimizer.",
        BODY))
    s.append(PageBreak())

    s.append(Paragraph("4. In-memory computation", H2))
    s.append(Paragraph(
        "Iris has only 150 rows, too small to show a caching effect. The benchmark replicates the data by a cross "
        f"join with {im['rows'] // 150:,} copies ({im['rows']:,} rows). It runs the same aggregation three times "
        "(median time) in two ways: recomputing from the CSV each time, and reading from a cache that was "
        "materialised once with <font face='Courier'>persist(MEMORY_ONLY)</font>.", BODY))
    s.append(table([
        ["Mode", "Median seconds", "Storage level"],
        ["Recompute from CSV each time", f"{im['recompute_seconds']:.3f}", "none"],
        ["Cached in memory", f"{im['cached_seconds']:.3f}", im["storage_level_after_cache"]],
    ], widths=[6 * cm, 4 * cm, 6 * cm]))
    s.append(Spacer(1, 0.2 * cm))
    s.append(Paragraph(
        f"Speedup {im['speedup']}x in this run. Timings are from a single local machine, so they vary between runs. "
        "With the cache, each query skips re-reading the CSV and rebuilding the cross join. "
        "The cache is only useful when the same data is reused, as in this benchmark.", BODY))
    s.append(fig(figs / "02_cache_vs_recompute.png", width=11 * cm))
    s.append(PageBreak())

    s.append(Paragraph("5. Data lineage", H2))
    s.append(Paragraph(
        "Lineage is the chain of transformations that produces each result. Spark keeps it as an RDD dependency "
        "graph or a logical plan, and uses it to recompute lost partitions. The RDD debug strings below show each "
        "stage. Indentation marks a shuffle boundary. The DataFrame plans show the parsed, analysed, optimised and "
        "physical forms.", BODY))
    s.append(fig(figs / "03_lineage_diagram.png"))
    s.append(Paragraph("Full lineage output (first 40 lines of each section, from lineage.txt):", BODY))
    s.append(code_block(lineage, max_lines=40))
    s.append(PageBreak())

    s.append(Paragraph("6. Spark UI", H2))
    if ui:
        s.append(Paragraph(
            f"The Spark UI was reachable at {ui['ui_url']} during the run. Its REST API was exported to "
            "<font face='Courier'>output/spark_ui/</font>: "
            + ", ".join(f"{k} ({v})" for k, v in ui["exported"].items()) + ". "
            "The storage export shows the cached RDD while it is held in memory. The SQL export lists each query "
            "with its plan.", BODY))
    s.append(Paragraph(
        "Screenshots: the Spark UI pages (Jobs, Stages, Storage, SQL) are shown when the script runs with "
        "<font face='Courier'>--pause</font>. They are not included in this report because they must be taken "
        "from a browser while Spark is running.", BODY))

    s.append(Paragraph("7. Limitations", H2))
    for t in [
        "Local mode runs on one machine. The results show Spark's behaviour, not cluster performance.",
        "Iris is small. The caching benchmark replicates it to make the effect measurable.",
        "Timings come from one run and vary between runs.",
    ]:
        s.append(Paragraph("- " + t, BODY))

    doc = SimpleDocTemplate(str(out / "Assignment3_Report.pdf"), pagesize=A4,
                            leftMargin=2 * cm, rightMargin=2 * cm, topMargin=2 * cm, bottomMargin=2 * cm,
                            title="Assignment 3 Report")
    doc.build(s)
    print("wrote", out / "Assignment3_Report.pdf")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="output")
    main(ap.parse_args().out)
