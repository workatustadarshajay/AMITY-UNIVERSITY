"""Build the Assignment 4 PDF report from the outputs.

    python report.py --out output
Uses comparison.json when a real-time run has produced it; otherwise states that the real-time part was not run.
"""
import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
from reportlab.lib import colors  # noqa: E402
from reportlab.lib.pagesizes import A4  # noqa: E402
from reportlab.lib.styles import getSampleStyleSheet  # noqa: E402
from reportlab.lib.units import cm  # noqa: E402
from reportlab.lib.utils import ImageReader  # noqa: E402
from reportlab.platypus import Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle  # noqa: E402

styles = getSampleStyleSheet()
H1, H2, BODY = styles["Heading1"], styles["Heading2"], styles["BodyText"]


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


def read_part_dir(path: Path) -> pd.DataFrame:
    return pd.concat([pd.read_json(p, lines=True) for p in sorted(path.glob("part-*.json"))], ignore_index=True)


def make_figures(out: Path, ev: pd.DataFrame, monthly: pd.DataFrame):
    fig_dir = out / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)
    ev = ev.assign(date=pd.to_datetime(ev["date"])).sort_values("date")

    fig, ax = plt.subplots(figsize=(11, 4.5))
    ax.plot(ev["date"], ev["close"], lw=0.6, color="#4C72B0", label="VIX close")
    ax.axhline(30, color="#C44E52", ls="--", lw=0.8, label="stress level (30)")
    ax.axhline(20, color="#DD8452", ls="--", lw=0.8, label="elevated level (20)")
    al = ev[ev["alert"]]
    ax.scatter(al["date"], al["close"], s=6, color="#C44E52", zorder=3, label="stress alert days")
    ax.set_ylabel("VIX close")
    ax.set_title("VIX daily close, 1990 to 2026, with stress alerts (batch pipeline output)")
    ax.legend(loc="upper right", fontsize=8)
    fig.tight_layout()
    fig.savefig(fig_dir / "01_vix_alerts.png", dpi=130)
    plt.close(fig)

    yearly = ev.assign(year=ev["date"].dt.year).groupby("year")["alert"].sum()
    fig, ax = plt.subplots(figsize=(11, 4))
    ax.bar(yearly.index, yearly.values, color="#C44E52")
    ax.set_ylabel("Stress alert days")
    ax.set_xlabel("Year")
    ax.set_title("Stress alert days per year")
    fig.tight_layout()
    fig.savefig(fig_dir / "02_alert_days_per_year.png", dpi=130)
    plt.close(fig)

    counts = ev["regime"].value_counts().reindex(["calm", "elevated", "stress"]).fillna(0)
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.bar(counts.index, counts.values, color=["#55A868", "#DD8452", "#C44E52"])
    ax.set_ylabel("Trading days")
    ax.set_title("Days in each volatility regime (batch)")
    fig.tight_layout()
    fig.savefig(fig_dir / "03_regimes.png", dpi=130)
    plt.close(fig)
    return counts, yearly


def main(out: str):
    out = Path(out)
    m = json.loads((out / "metrics.json").read_text(encoding="utf-8"))
    ev = read_part_dir(out / "batch_events")
    monthly = read_part_dir(out / "batch_monthly")
    comparison_path = out / "comparison.json"
    comparison = json.loads(comparison_path.read_text(encoding="utf-8")) if comparison_path.exists() else None
    counts, yearly = make_figures(out, ev, monthly)
    figs = out / "figures"

    s = []
    s.append(Paragraph("Real-time Data Processing: Amazon Kinesis and Spark Streaming vs Batch", H1))
    s.append(Paragraph("Assignment No. 4", BODY))
    s.append(Spacer(1, 0.3 * cm))

    s.append(Paragraph("1. Concepts", H2))
    s.append(Paragraph(
        "<b>Batch processing</b> collects data over a period, then processes the whole set in one run. "
        "Results are available when the run finishes, usually on a schedule (hourly or daily). It favours "
        "throughput and simple, repeatable jobs over the full data set.", BODY))
    s.append(Paragraph(
        "<b>Real-time (stream) processing</b> handles each event or small micro-batch as it arrives. Results are "
        "available within seconds, and the job runs continuously. It favours latency, at the cost of more complex "
        "state handling, ordering and failure recovery.", BODY))
    s.append(table([
        ["Aspect", "Batch", "Real-time (stream)"],
        ["Data", "Bounded: a full file or table", "Unbounded: events as they arrive"],
        ["Result latency", "Minutes to hours (schedule)", "Milliseconds to seconds"],
        ["Typical job", "Full recompute, simple to reason about", "Incremental, stateful, windowed"],
        ["Failure handling", "Re-run the job", "Checkpoints and exactly-once sinks, more care needed"],
        ["Cost pattern", "Compute in bursts", "Always-on compute"],
    ], widths=[3.5 * cm, 6.2 * cm, 6.5 * cm]))
    s.append(Spacer(1, 0.2 * cm))

    s.append(Paragraph("2. Advantages and popular tools", H2))
    s.append(table([
        ["Approach", "Key advantages", "Popular tools"],
        ["Batch", "Simple, cheap per record, easy to rerun and audit, handles large history",
         "Apache Spark (batch), Hadoop MapReduce, Hive, AWS Glue (batch ETL), Apache Airflow (scheduling)"],
        ["Real-time", "Low latency, alerts and decisions while data is still fresh, continuous monitoring",
         "Amazon Kinesis Data Streams, Apache Kafka, Apache Flink, Spark Structured Streaming, Apache Storm"],
    ], widths=[2.5 * cm, 7 * cm, 6.7 * cm]))
    s.append(Spacer(1, 0.2 * cm))

    s.append(Paragraph("3. Practical use cases for real-time processing", H2))
    for t in [
        "<b>Market stress alerts (this assignment).</b> Flag days when the VIX volatility index crosses a "
        "threshold, so a risk team can react the same day instead of at the next batch run.",
        "<b>Card fraud detection.</b> Score each transaction as it happens and block suspicious ones before "
        "authorisation completes. A nightly batch would detect fraud too late.",
        "<b>Industrial IoT monitoring.</b> Detect a sensor reading outside its normal range in seconds, so a "
        "machine can be stopped before damage occurs.",
    ]:
        s.append(Paragraph("- " + t, BODY))

    s.append(Paragraph("4. Pipeline design", H2))
    s.append(Paragraph(
        "Data: DataHub finance-vix daily file, 9,278 trading days from 2 January 1990 to 22 September 2026 "
        "(columns DATE, OPEN, HIGH, LOW, CLOSE). Both pipelines use the same enrichment and aggregation code "
        "(<font face='Courier'>common.py</font>), so differences in their output can only come from how the data "
        "arrives.", BODY))
    s.append(Paragraph(
        "<b>Real-time path (AWS design):</b> producer → Amazon Kinesis Data Streams (one shard) → consumer → "
        "Spark Structured Streaming (two queries: per-event enrichment in append mode, calendar-month aggregates in "
        "update mode). The local stand-in sends the same events from the producer over a TCP socket to Spark.", BODY))
    s.append(Paragraph(
        "<b>Batch path:</b> read the whole CSV once, enrich, and aggregate by calendar month.", BODY))

    s.append(Paragraph("5. What ran, and what did not", H2))
    s.append(table([
        ["Component", "Status on this machine"],
        ["Batch pipeline (Spark, whole file)", f"Ran: {m['batch']['rows']:,} rows in {m['batch']['wall_seconds']} s "
                                              f"(Spark {m['spark_version']}, Java {m['java_version']})"],
        ["Shared logic and tests", "Ran: 4 checks pass (regimes, monthly aggregates, loader, socket sink)"],
        ["Real-time pipeline (Structured Streaming)",
         "Not run here. Spark's streaming checkpoints need Hadoop native Windows binaries (winutils.exe), which "
         "the network proxy blocks. The code is ready to run on Linux or in Google Colab."],
        ["Amazon Kinesis ingestion", "Not run. Needs an AWS account and credentials; a Kinesis shard incurs hourly "
                                     "charges. Code provided in kinesis_io.py."],
        ["Real-time vs batch comparison",
         "Ready (compare.py), waiting for a streaming run" if comparison is None else "Run; see section 6"],
    ], widths=[5.5 * cm, 11.2 * cm]))
    s.append(Spacer(1, 0.2 * cm))

    s.append(Paragraph("6. Results", H2))
    s.append(Paragraph("<b>Batch results</b> (produced by Spark on the whole file):", BODY))
    rows = [["Regime", "Trading days", "Share"]] + [
        [r, int(counts[r]), f"{counts[r] / counts.sum():.1%}"] for r in counts.index]
    s.append(table(rows, widths=[4 * cm, 4 * cm, 4 * cm]))
    s.append(Spacer(1, 0.2 * cm))
    total_alerts = int(ev["alert"].sum())
    s.append(Paragraph(
        f"Stress alert days (VIX close at or above 30): {total_alerts}. The highest-alert years are "
        f"{', '.join(str(y) for y in yearly.sort_values(ascending=False).head(3).index)}. "
        f"The most recent month in the file is {monthly['month'].max()[:7]}.", BODY))
    s.append(fig(figs / "01_vix_alerts.png"))
    s.append(fig(figs / "02_alert_days_per_year.png"))
    s.append(fig(figs / "03_regimes.png", width=10 * cm))

    s.append(Paragraph("<b>Real-time vs batch comparison:</b>", BODY))
    if comparison is None:
        s.append(Paragraph(
            "No streaming run is included, so the comparison is not reported yet. The table below lists what "
            "will be measured and where the batch side stands.", BODY))
        s.append(table([
            ["Measure", "Batch", "Real-time"],
            ["Wall time for the whole file", f"{m['batch']['wall_seconds']} s", "not measured"],
            ["Result latency per event", "set by the schedule (not measured)", "not measured"],
            ["Per-event results identical to batch", "reference", "not measured"],
            ["Monthly results identical to batch", "reference", "not measured"],
        ], widths=[6 * cm, 5 * cm, 5.7 * cm]))
    else:
        ev_c = comparison["events"]
        mo_c = comparison["monthly"]
        lat = comparison["latency_seconds"]
        s.append(table([
            ["Measure", "Result"],
            ["Per-event results identical", str(ev_c["identical_per_event_results"])],
            ["Monthly results identical", str(mo_c["identical_monthly_results"])],
            ["Stream latency p50 / p95 (s)", f"{lat['p50']} / {lat['p95']}"],
            ["Stream end-to-end (s)", str(comparison["stream"]["end_to_end_seconds"])],
            ["Batch wall time (s)", str(comparison["batch"]["wall_seconds"])],
        ], widths=[7 * cm, 9.7 * cm]))

    s.append(Paragraph("7. Limitations", H2))
    for t in [
        "The VIX file is a daily series: it is not a true high-frequency feed, so latency is measured on replayed events.",
        "Spark's socket source, used for the local stand-in, is intended for testing and is not fault-tolerant.",
        "The Kinesis code was not run; its behaviour against AWS is untested in this project.",
        "The real-time comparison requires a streaming run, which is not included in this report yet.",
    ]:
        s.append(Paragraph("- " + t, BODY))

    s.append(Paragraph("8. References", H2))
    for t in [
        "DataHub, Finance VIX daily data: https://datahub.io/core/finance-vix",
        "Cboe, VIX volatility index: https://www.cboe.com/tradable_products/vix/",
        "AWS, Amazon Kinesis Data Streams developer guide: https://docs.aws.amazon.com/streams/latest/dev/introduction.html",
        "Apache Spark, Structured Streaming programming guide: https://spark.apache.org/docs/latest/structured-streaming-programming-guide.html",
    ]:
        s.append(Paragraph("- " + t, BODY))

    doc = SimpleDocTemplate(str(out / "Assignment4_Report.pdf"), pagesize=A4,
                            leftMargin=2 * cm, rightMargin=2 * cm, topMargin=2 * cm, bottomMargin=2 * cm,
                            title="Assignment 4 Report")
    doc.build(s)
    print("wrote", out / "Assignment4_Report.pdf")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="output")
    main(ap.parse_args().out)
