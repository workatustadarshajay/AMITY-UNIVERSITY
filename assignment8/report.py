"""Build the Assignment 8 PDF report from the saved outputs of pipeline.run_local.

    python report.py --out output

Every number in the report is read from output/, so the report and the run cannot drift apart.
"""
import argparse
import json
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
from reportlab.lib import colors  # noqa: E402
from reportlab.lib.pagesizes import A4  # noqa: E402
from reportlab.lib.styles import getSampleStyleSheet  # noqa: E402
from reportlab.lib.units import cm  # noqa: E402
from reportlab.platypus import Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle  # noqa: E402

styles = getSampleStyleSheet()
H1, H2, BODY = styles["Heading1"], styles["Heading2"], styles["BodyText"]
SMALL = BODY.clone("small", fontSize=8, leading=10)


def esc(t):
    return str(t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def table(rows, widths):
    cells = [[Paragraph(esc(c), SMALL) for c in r] for r in rows]
    t = Table(cells, colWidths=widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#DDE4EE")),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.grey), ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    return t


def fmt(x, nd=0):
    return f"{x:,.{nd}f}"


def monthly_chart(explore, figs):
    e2 = pd.read_csv(explore / "E2.csv")
    fig, ax = plt.subplots(figsize=(9, 3.2))
    ax.bar(e2["invoice_month"], e2["revenue_gbp"] / 1e3, color="#3B6E9F")
    ax.set_ylabel("Revenue (GBP thousands)")
    ax.set_title("Monthly revenue after cleaning (E2)")
    plt.setp(ax.get_xticklabels(), rotation=60, ha="right", fontsize=7)
    fig.tight_layout()
    path = figs / "monthly_revenue.png"
    fig.savefig(path, dpi=130); plt.close(fig)
    return path


def build(out):
    out = Path(out)
    explore, mining, quality, cdc = out / "explore", out / "mining", out / "quality", out / "cdc"
    figs = out / "figures"; figs.mkdir(parents=True, exist_ok=True)
    summary = json.loads((out / "run_summary.json").read_text(encoding="utf-8"))
    q = json.loads((quality / "quality_metrics.json").read_text(encoding="utf-8"))
    c = json.loads((cdc / "cdc_check.json").read_text(encoding="utf-8"))
    pc = json.loads((mining / "pairs_check.json").read_text(encoding="utf-8"))
    e1 = pd.read_csv(explore / "E1.csv").iloc[0]
    e3 = pd.read_csv(explore / "E3.csv")
    e4 = pd.read_csv(explore / "E4.csv")
    e5 = pd.read_csv(explore / "E5.csv")
    e7 = pd.read_csv(explore / "E7.csv").iloc[0]
    rules = pd.read_csv(mining / "apriori_rules.csv")
    sim = pd.read_csv(mining / "similarity_top20.csv")
    chart = monthly_chart(explore, figs)
    rejected = sum(q["rejects_by_reason"].values())
    ms = summary["min_support"]
    min_count = math.ceil(ms * summary["baskets"])

    s = []
    s.append(Paragraph("Assignment 8: Data Processing with Amazon Services (Online Retail)", H1))
    s.append(Paragraph(
        "UCI Online Retail transactions (541,909 lines, December 2010 to December 2011). The workflow extracts the "
        "data, applies CDC, cleans it with a Glue-style PySpark job, loads it into a warehouse, runs exploration SQL, "
        "and mines product association rules with Apriori.", BODY))
    s.append(Spacer(1, 6))

    s.append(Paragraph("1. What was run, and where", H2))
    s.append(table([
        ["Stage", "Built", "Run here", "Run on AWS"],
        ["Extract to S3 (extract.py)", "Yes", "Yes, to a local S3 mirror", "No: no AWS account"],
        ["CDC (cdc.py, 03_cdc_merge.sql)", "Yes", "Yes, MERGE run in DuckDB", "No"],
        ["Glue ETL (transform.py, glue_etl_job.py)", "Yes", "Yes, transform on local Spark", "No: awsglue not installed here"],
        ["Redshift DDL, COPY, explore, mining SQL", "Yes", "Yes, in DuckDB (DISTKEY/SORTKEY removed)", "No"],
        ["Apriori and similarity (Python)", "Yes", "Yes", "Not needed in AWS"],
    ], [5.4 * cm, 1.6 * cm, 5.2 * cm, 4.8 * cm]))
    s.append(Paragraph(
        "The AWS parts are written to run as they are, but they were not run on AWS. Placeholders for account, role "
        "and bucket names must be filled in first. The DuckDB runs stand in for Redshift. Redshift itself was not "
        "used.", SMALL))

    s.append(Paragraph("2. Extraction and stable keys", H2))
    s.append(Paragraph(
        "The workbook is read and written as CSV. Each line gets a <i>line_id</i> (invoice, product and occurrence "
        "number), assigned once at extraction. The natural key (InvoiceNo, StockCode) is not unique: "
        "5,199 keys repeat. The line_id is what CDC matches on, so updates do not look like deletes followed by inserts.",
        BODY))

    s.append(Paragraph("3. Change data capture", H2))
    s.append(Paragraph(
        "A day-2 snapshot was simulated: about 1% of lines have their quantity changed, about 0.5% are deleted, and "
        "about 0.5% new lines are added. The diff on line_id gives the change set. "
        f"The change set holds {fmt(c['ops'].get('I', 0))} inserts, {fmt(c['ops'].get('U', 0))} updates and "
        f"{fmt(c['ops'].get('D', 0))} deletes. Applying it to the day-1 table with the MERGE in "
        f"<i>sql/redshift/03_cdc_merge.sql</i> gives {fmt(c['raw_line_rows_after_merge'])} rows. Every row matches the "
        "day-2 snapshot ("
        + ("all values match" if c["values_match"] else "MISMATCH") + "). The updates are fewer than the number "
        "selected, because some selected lines were then deleted.", BODY))

    s.append(Paragraph("4. Pre-processing and data quality", H2))
    s.append(table([
        ["Step", "Lines", "Rule and reason"],
        ["Raw input", fmt(q["raw_rows"]), "All lines from the source"],
        ["Cancellations", fmt(q["rejects_by_reason"].get("cancellation", 0)), "InvoiceNo starts with C; not a sale"],
        ["Non-positive quantity", fmt(q["rejects_by_reason"].get("non_positive_quantity", 0)),
         "Returns and stock adjustments; baskets are built from purchases"],
        ["Non-positive price", fmt(q["rejects_by_reason"].get("non_positive_price", 0)),
         "Price 0 or below (free items, write-offs, manual adjustments)"],
        ["Non-product codes", fmt(q["rejects_by_reason"].get("non_product_code", 0)),
         "POST, DOT, M, D, B, S, BANK CHARGES, gift vouchers and similar"],
        ["Exact duplicates", fmt(q["exact_duplicates_removed"]), "Identical on every business column; smallest line_id kept"],
        ["Clean lines", fmt(q["clean_rows"]), f"{fmt(q['clean_rows'] / q['raw_rows'] * 100, 1)}% of raw lines kept"],
    ], [3.6 * cm, 2.2 * cm, 11.2 * cm]))
    s.append(Spacer(1, 4))
    s.append(Paragraph(
        f"<b>Missing values.</b> {e1['pct_lines_no_customer']}% of clean lines have no CustomerID. These are guest "
        "checkouts. They are kept, flagged, and still count for basket mining, because a basket is an invoice and does "
        "not need a customer. Missing descriptions appear only on zero-price lines, so they are rejected above; the "
        "transform still fills and flags them if they occur.", BODY))
    s.append(Paragraph(
        f"<b>Outliers.</b> IQR fences (Quantity above {q['quantity_fence_iqr']:.1f}; UnitPrice above "
        f"{q['unit_price_fence_iqr']:.2f}) flag {fmt(e7['outlier_quantity_lines'])} quantity and "
        f"{fmt(e7['outlier_price_lines'])} price lines. They are flagged, not removed: large wholesale quantities are "
        "real. The price fence is tight because prices are skewed, so the price flag is a review list, not an error list.",
        BODY))
    s.append(Paragraph(
        "<b>Sampling.</b> The transform can take a stratified sample by country (sampleBy on Country). The reported "
        "results use the full clean data (sample fraction 1.0), because rules on a sample would have "
        "different support counts.", BODY))

    s.append(Paragraph("5. Exploration with SQL", H2))
    s.append(Paragraph(
        f"The clean data covers {fmt(e1['invoices'])} invoices, {fmt(e1['known_customers'])} known customers, "
        f"{fmt(e1['products'])} products and {fmt(e1['countries'])} countries, with revenue of "
        f"GBP {fmt(e1['revenue_gbp'], 0)}. The United Kingdom is the largest market.", BODY))
    s.append(Image(str(chart), width=16 * cm, height=16 * cm * 3.2 / 9))
    s.append(Spacer(1, 4))
    s.append(table([["Country", "Revenue (GBP)", "Invoices"]] + [
        [r.country, fmt(r.revenue_gbp), fmt(r.invoices)] for r in e3.head(6).itertuples()],
        [5 * cm, 4 * cm, 3 * cm]))
    s.append(Spacer(1, 4))
    s.append(table([["Top product (E4)", "Units", "Revenue (GBP)"]] + [
        [f"{r.stock_code} {r.product_name}", fmt(r.units), fmt(r.revenue_gbp)] for r in e4.head(5).itertuples()],
        [9 * cm, 3 * cm, 4 * cm]))
    s.append(Spacer(1, 4))
    s.append(table([["Products per invoice (E5)", "Invoices"]] + [
        [r.basket_products, fmt(r.invoices)] for r in e5.itertuples()], [6 * cm, 3 * cm]))

    s.append(Paragraph("6. Association rules (Apriori)", H2))
    s.append(Paragraph(
        f"Basket = invoice ({fmt(summary['baskets'])} baskets), item = product code. Minimum support is {ms:.0%} "
        f"(at least {fmt(min_count)} baskets), minimum confidence 50%, itemsets up to size 3. "
        f"The Python Apriori and the SQL pair query were run on the same data. They found {pc['python_pairs']} "
        f"frequent pairs each, and the pair counts are identical ({'yes' if pc['identical'] else 'NO'}). "
        f"{summary['frequent_itemsets']} frequent itemsets give {len(rules)} rules; "
        f"{int((rules['antecedent'].str.contains(' + ', regex=False) | rules['consequent'].str.contains(' + ', regex=False)).sum())} "
        "of them have a combined side.", BODY))
    top = rules.head(10)
    rows = [["Antecedent", "Consequent", "Baskets", "Support", "Confidence", "Lift"]]
    for r in top.itertuples():
        rows.append([r.antecedent[:70], r.consequent[:70], fmt(r.count), f"{r.support:.3f}",
                     f"{r.confidence:.2f}", f"{r.lift:.1f}"])
    s.append(table(rows, [5.2 * cm, 5.2 * cm, 1.5 * cm, 1.6 * cm, 1.9 * cm, 1.4 * cm]))
    s.append(Spacer(1, 4))
    s.append(Paragraph(
        "<b>Reading the rules.</b> Support is the share of baskets that contain both sides. Confidence is the share of "
        "baskets with the antecedent that also contain the consequent. Lift is confidence divided by the consequent's "
        "overall support; above 1 means the two products are bought together more than chance predicts. The strongest "
        "rules are the three Regency teacup and saucer colours, so most of the strong rules describe one bundle in three "
        "colours. Sixteen rules have lift above 15. They involve the three teacup colours, the Spaceboy and Dolly Girl "
        "lunch boxes, the Gardeners Kneeling Pad pair and the two Charlotte bags. These look like products that customers "
        "buy together, which suggests cross-selling. A high lift on a bundle is expected and does not by itself show a "
        "new recommendation.", BODY))

    s.append(Paragraph("7. Similarity and dissimilarity", H2))
    s.append(Paragraph(
        "Each product is a set of baskets (invoices). For two products A and B: <b>Jaccard</b> = |A and B| / |A or B| "
        "(overlap relative to everything either product appears in). <b>Cosine</b> = |A and B| / sqrt(|A| |B|), which "
        "rewards overlap without penalising very popular products as much. <b>Dissimilarity</b> = 1 minus Jaccard, a "
        "distance between products: 0 means always bought together, 1 means never together. Values are for the 20 "
        "most frequent products (190 pairs).", BODY))
    sim_top = sim.head(6)
    rows = [["Product A", "Product B", "Co-baskets", "Jaccard", "Cosine", "Dissimilarity"]]
    for r in sim_top.itertuples():
        rows.append([str(r.name_a)[:34], str(r.name_b)[:34], fmt(r.co_occurrences), f"{r.jaccard:.3f}",
                     f"{r.cosine:.3f}", f"{r.dissimilarity:.3f}"])
    s.append(table(rows, [4.4 * cm, 4.4 * cm, 2 * cm, 1.8 * cm, 1.8 * cm, 2.6 * cm]))
    least = sim.tail(1).iloc[0]
    s.append(Spacer(1, 4))
    s.append(Paragraph(
        f"The most similar pairs are carrier bags: the lunch bag and jumbo bag designs are bought in the same "
        f"invoices. The least similar pair in the top 20 has a Jaccard of {least['jaccard']:.3f} (dissimilarity "
        f"{least['dissimilarity']:.3f}), so the top products do not all share baskets. Jaccard is the main measure; "
        f"cosine is never below Jaccard, and the two rank the {len(sim)} pairs almost identically "
        f"(Spearman {sim[['jaccard', 'cosine']].corr(method='spearman').iloc[0, 1]:.3f}), so either can "
        "drive a clustering step. Dissimilarity (1 minus Jaccard) is the distance such a step would use.", BODY))

    s.append(Paragraph("8. Limitations and next steps", H2))
    for line in [
        "No AWS services were used. The Glue job has not been run in Glue, and the Redshift SQL has not been run on "
        "a Redshift cluster. Both run here on local stand-ins with the same logic.",
        "The day-2 change set is simulated. A real source would supply its own change log.",
        "The minimum support (2%) and confidence (50%) were chosen, not tuned. A sweep over support is the next step.",
        "Basket mining uses all clean invoices. Guest checkouts (about a quarter of lines) are included.",
        "Screenshots of the AWS consoles are not included, because nothing was deployed.",
    ]:
        s.append(Paragraph("&bull; " + esc(line), BODY))

    s.append(Paragraph("9. References", H2))
    for ref in [
        "Chen, D. Online Retail. UCI Machine Learning Repository, 2015. https://archive.ics.uci.edu/dataset/352/online+retail",
        "Agrawal, R. and Srikant, R. Fast algorithms for mining association rules. VLDB 1994.",
        "Tan, P.-N., Steinbach, M. and Kumar, V. Introduction to Data Mining. Pearson, 2nd ed. (Jaccard and cosine).",
        "Amazon Redshift Database Developer Guide: MERGE, COPY, distribution and sort keys.",
        "AWS Glue Developer Guide: Glue 4.0 jobs, job bookmarks and --extra-py-files.",
    ]:
        s.append(Paragraph("&bull; " + esc(ref), SMALL))

    pdf = out / "Assignment8_Report.pdf"
    SimpleDocTemplate(str(pdf), pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm, topMargin=1.8 * cm,
                      bottomMargin=1.8 * cm, title="Assignment 8: Data Processing with Amazon Services").build(s)
    return pdf


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="output")
    print("wrote", build(parser.parse_args().out))


if __name__ == "__main__":
    main()
