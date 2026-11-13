"""Build the Assignment 6 PDF: design documentation with the architecture and model figures.

    python report.py --out output
"""
import argparse
import csv
import sqlite3
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

ROOT = Path(__file__).resolve().parent
styles = getSampleStyleSheet()
H1, H2, BODY = styles["Heading1"], styles["Heading2"], styles["BodyText"]
SMALL = BODY.clone("small", fontSize=8, leading=10)


def esc(text):
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def table(rows, widths):
    cells = [[Paragraph(esc(str(c)), SMALL) for c in r] for r in rows]
    t = Table(cells, colWidths=widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#DDE4EE")),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]))
    return t


def physical_tables(ddl_path):
    """Table names and column counts, read from the DDL by SQLite itself."""
    ddl = ddl_path.read_text(encoding="utf-8")
    con = sqlite3.connect(":memory:")
    con.executescript(ddl)
    out = []
    for (name,) in con.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"):
        cols = con.execute(f"PRAGMA table_info({name})").fetchall()
        out.append((name, len(cols)))
    con.close()
    return out


def logical_summary(csv_path):
    with csv_path.open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    summary = {}
    for r in rows:
        s = summary.setdefault(r["entity"], {"attrs": 0, "pk": [], "source": r["source"]})
        s["attrs"] += 1
        if r["key"] == "PK":
            s["pk"].append(r["attribute"])
    return summary


def build(out_dir):
    out_dir = Path(out_dir)
    figs = out_dir / "figures"
    pdf_path = out_dir / "Assignment6_Report.pdf"
    story = []

    story.append(Paragraph("Assignment 6: Enterprise Data Architecture and Modelling", H1))
    story.append(Paragraph(
        "Scenario: a marketplace and an online retailer that need one analytics platform for sales, delivery "
        "and customer reporting. Datasets: Olist Brazilian e-commerce (Kaggle) and UCI Online Retail.", BODY))
    story.append(Spacer(1, 6))

    story.append(Paragraph("1. Characteristics of the modern architecture applied here", H2))
    for line in [
        "<b>Separate storage and compute.</b> Raw and curated data sit in object storage (S3); a warehouse "
        "serves queries. Each can scale on its own.",
        "<b>Layered (medallion) processing.</b> Bronze keeps the data as received, silver holds clean and "
        "typed data, gold holds the analysis model. Any layer can be rebuilt from the one before it.",
        "<b>Mixed sources in one model.</b> The two datasets have different keys and coverage, so they share "
        "date and location but keep their own customer and product dimensions.",
        "<b>Governance built in.</b> Catalog, lineage, data-quality checks and access control (Assignment 5) "
        "are part of the design, not added later.",
        "<b>Open for new sources.</b> A streaming or API source can be added at ingestion without changing gold "
        "tables.",
    ]:
        story.append(Paragraph("&bull; " + line, BODY))

    story.append(Paragraph("2. Enterprise data architecture", H2))
    story.append(Paragraph(
        "Figure 1 shows the flow. Batch loaders copy the CSV files into bronze, with a schema check and file "
        "checksum. AWS Data Pipeline schedules the steps and sends an alert on failure. Silver applies the "
        "data-quality rules from Assignment 5 and quarantines bad rows. Gold builds the star schema, which is "
        "loaded into the warehouse for BI, SQL and model training. A streaming source is shown dashed because it "
        "is not in scope.", BODY))
    story.append(PageBreak())
    story.append(Image(str(figs / "01_architecture.png"), width=17 * cm, height=17 * cm * 0.62))

    story.append(Paragraph("3. Data models", H2))
    story.append(Paragraph(
        "<b>Conceptual.</b> Eight business concepts: Customer, Order, Order item, Product, Seller, Payment, Review "
        "and Location (Figure 2). The retail data maps Invoice to Order and StockCode to Product. It has no "
        "Seller, Payment or Review, so those are empty for that source. Full relationships and cardinalities are "
        "in <i>models/conceptual.md</i>.", BODY))
    story.append(Spacer(1, 4))
    story.append(Image(str(figs / "02_conceptual.png"), width=15 * cm, height=15 * cm * 0.64))

    logical = logical_summary(ROOT / "models" / "logical_model.csv")
    rows = [["Logical entity (silver, 3NF)", "Source", "Primary key", "Attributes"]]
    for name, s in logical.items():
        rows.append([name, s["source"], ", ".join(s["pk"]), s["attrs"]])
    story.append(Paragraph(
        "<b>Logical.</b> Normalised to third normal form in silver, with attributes, keys, nullability and "
        "descriptions in <i>models/logical_model.csv</i>. Summary:", BODY))
    story.append(Spacer(1, 3))
    story.append(table(rows, [4.5 * cm, 2.2 * cm, 6.3 * cm, 2.6 * cm]))

    story.append(PageBreak())
    story.append(Paragraph(
        "<b>Physical.</b> Gold is a star schema on Redshift, written as portable SQL in <i>models/physical.sql</i> "
        "and tested in SQLite (Figure 3). Redshift distribution and sort keys are noted in comments.", BODY))
    story.append(Spacer(1, 3))
    story.append(Image(str(figs / "03_star_schema.png"), width=16.5 * cm, height=16.5 * cm * 0.73))
    story.append(Spacer(1, 4))
    phys = physical_tables(ROOT / "models" / "physical.sql")
    rows = [["Physical table", "Columns", "Role"]]
    for name, n in phys:
        rows.append([name, n, "dimension" if name.startswith("dim_") else "fact"])
    story.append(table(rows, [5.5 * cm, 2.5 * cm, 3 * cm]))

    story.append(PageBreak())
    story.append(Paragraph("4. Key design decisions and rationale", H2))
    decisions = [
        ["Decision", "Rationale"],
        ["Bronze, silver and gold layers",
         "Raw data is kept, so any later fix can be replayed. Each layer has one job, which makes lineage easy to follow."],
        ["Silver in 3NF, gold as a star",
         "3NF keeps each fact stored once and makes integrity checks simple. A star lets BI tools write short, fast queries."],
        ["Conformed date and location; source-specific customer and product",
         "Dates and places mean the same thing in both datasets. Olist and UCI product codes do not match, so forcing one "
         "dimension would give false matches."],
        ["Olist customer key = customer_unique_id",
         "The order-level customer_id changes for each order. The unique id identifies the person across orders."],
        ["Fact grains: order item, payment, review",
         "Revenue is measured per item. Payments are many per order and reviews are zero or one per order, so each "
         "gets its own fact. This avoids double-counting order totals."],
        ["Nullable customer_key in fact_retail_line",
         "A large share of UCI rows have no CustomerID. Dropping them would understate revenue, so the rows are kept "
         "and reported as unknown customer."],
        ["Cancellations and returns kept, flagged",
         "Negative quantities and cancelled invoices (C prefix) are flagged, not deleted, so net sales can be "
         "reconciled."],
        ["Review text excluded from gold",
         "Free text can hold personal data. Minimisation keeps it in silver, under access control, and out of the "
         "analytics layer."],
        ["Surrogate integer keys, source ids kept",
         "Stable keys across source changes, while the original ids stay for tracing back to bronze."],
        ["Distribution keys on order_id; small dims replicated",
         "Order items, payments and reviews join locally on Redshift. Small date and location tables are copied to "
         "every node."],
        ["Batch ingestion now; streaming left as an extension",
         "The two datasets are historical files loaded in batches. A stream can be added at ingestion without changing gold."],
    ]
    story.append(table(decisions, [5.2 * cm, 11.8 * cm]))

    story.append(Paragraph("5. Limitations", H2))
    for line in [
        "The design was built from each dataset's documented schema. The CSV files were not loaded into this "
        "environment, so row counts and null rates are taken from the dataset descriptions, not measured.",
        "The DDL was run in SQLite, not on Redshift. Platform-specific types and distribution keys are untested.",
        "No AWS resources were created, so there are no console screenshots of the security settings.",
    ]:
        story.append(Paragraph("&bull; " + line, BODY))

    story.append(Paragraph("6. References", H2))
    for ref in [
        "Olist, Brazilian E-Commerce Public Dataset. Kaggle. https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce",
        "Chen, D. Online Retail. UCI Machine Learning Repository. https://archive.ics.uci.edu/dataset/352/online+retail",
        "Kimball, R. and Ross, M. The Data Warehouse Toolkit, 3rd ed. Wiley, 2013 (star schema and grain).",
        "AWS. Well-Architected Framework, Data Analytics Lens. https://docs.aws.amazon.com/wellarchitected/latest/analytics-lens/",
        "Amazon Redshift Database Developer Guide: distribution styles and sort keys.",
    ]:
        story.append(Paragraph("&bull; " + esc(ref), SMALL))

    doc = SimpleDocTemplate(str(pdf_path), pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm,
                            topMargin=1.8 * cm, bottomMargin=1.8 * cm,
                            title="Assignment 6: Enterprise Data Architecture and Modelling")
    doc.build(story)
    return pdf_path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="output")
    args = parser.parse_args()
    print("wrote", build(args.out))


if __name__ == "__main__":
    main()
