"""Draw the Assignment 6 figures: architecture, conceptual model, physical star schema.

    python design/diagrams.py --out output
"""
import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyBboxPatch  # noqa: E402

NAVY = "#1F3A5F"
FILL = {"source": "#E8EEF6", "ingest": "#F3F0E4", "lake": "#E4F1E8", "serve": "#F6E7E7",
        "consume": "#EFE7F5", "gov": "#EEEEEE", "fact": "#FFF4D6", "dim": "#E8EEF6", "conf": "#E4F1E8"}


def box(ax, x, y, w, h, title, body="", kind="source", dashed=False):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.3,rounding_size=0.8",
                                fc=FILL[kind], ec=NAVY, lw=1.2, ls="--" if dashed else "-"))
    ax.text(x + w / 2, y + h - 1.4, title, ha="center", va="top", fontsize=9, weight="bold", color=NAVY)
    if body:
        ax.text(x + w / 2, y + h - 4.0, body, ha="center", va="top", fontsize=7.5, linespacing=1.35)


def arrow(ax, x1, y1, x2, y2, label=""):
    ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle="-|>", color=NAVY, lw=1.2, shrinkA=0, shrinkB=0))
    if label:
        ax.text((x1 + x2) / 2 + 0.6, (y1 + y2) / 2, label, fontsize=7, color="#444444", style="italic")


def architecture(path):
    fig, ax = plt.subplots(figsize=(13, 8))
    ax.set_xlim(0, 100); ax.set_ylim(0, 62); ax.axis("off")
    for x, label in [(3, "SOURCES"), (24, "INGEST & ORCHESTRATE"), (42, "DATA LAKE (S3)"),
                     (66, "SERVING"), (84, "CONSUMERS")]:
        ax.text(x, 60.5, label, fontsize=8.5, weight="bold", color="#666666")

    box(ax, 2, 42, 19, 12, "Olist e-commerce", "9 CSV tables\n99k orders, 2016-2018\n(Kaggle)", "source")
    box(ax, 2, 27, 19, 12, "UCI Online Retail", "CSV, 541,909 lines\nUK retailer, 2010-2011\n(UCI)", "source")
    box(ax, 2, 12, 19, 12, "Future order events", "API / stream (optional)\nnot in scope yet", "source", dashed=True)

    box(ax, 24, 36, 15, 14, "Batch ingestion", "Glue / Python loader\nschema check\nfile checksum", "ingest")
    box(ax, 24, 16, 15, 14, "Orchestration", "AWS Data Pipeline\nschedule, retries,\nSNS alert on failure", "ingest")

    box(ax, 42, 42, 20, 12, "Bronze (raw)", "as received, unchanged\npartitioned by load date", "lake")
    box(ax, 42, 27, 20, 12, "Silver (clean 3NF)", "typed, deduplicated,\nDQ rules, quarantine", "lake")
    box(ax, 42, 12, 20, 12, "Gold (star schema)", "conformed dims,\nfacts for analysis", "lake")

    box(ax, 66, 27, 15, 27, "Analytics warehouse", "Redshift or\nPostgreSQL\n\nstar schema\n(physical.sql)\n\nrow-level security\nby source system", "serve")

    box(ax, 84, 42, 15, 12, "BI dashboards", "KPIs, trends,\ndelivery times", "consume")
    box(ax, 84, 27, 15, 12, "SQL analysts", "ad hoc queries\nvia warehouse", "consume")
    box(ax, 84, 12, 15, 12, "ML models", "classification,\nclustering (A2-A4)", "consume")

    box(ax, 2, 1, 97, 7, "Governance (cross-cutting)",
        "data catalog and lineage  |  DQ checks and metadata (Assignment 5)  |  IAM roles, KMS encryption at rest and in transit  |  PII minimisation",
        "gov")

    arrow(ax, 21.5, 48, 24, 43); arrow(ax, 21.5, 33, 24, 40)
    arrow(ax, 21.5, 18, 24, 22, "")
    arrow(ax, 39, 43, 42, 48, ""); arrow(ax, 39, 43, 42, 33, "")
    arrow(ax, 52, 42, 52, 39); arrow(ax, 52, 27, 52, 24)
    arrow(ax, 62, 18, 66, 33, "load"); arrow(ax, 62, 33, 66, 36)
    arrow(ax, 81, 36, 84, 48); arrow(ax, 81, 36, 84, 33); arrow(ax, 81, 33, 84, 18)
    arrow(ax, 39, 19, 42, 18, "")
    ax.set_title("Figure 1. Enterprise data architecture (batch, medallion layers)", fontsize=11, loc="left", color=NAVY)
    fig.savefig(path, dpi=150, bbox_inches="tight"); plt.close(fig)


def conceptual(path):
    fig, ax = plt.subplots(figsize=(11, 7))
    ax.set_xlim(0, 100); ax.set_ylim(0, 70); ax.axis("off")
    ents = {
        "Customer": (4, 44, 16, 9), "Order": (30, 44, 16, 9), "Order item": (56, 44, 16, 9),
        "Seller": (82, 44, 14, 9), "Product": (56, 22, 16, 9), "Payment": (30, 22, 16, 9),
        "Review": (30, 58, 16, 9), "Location": (4, 22, 16, 9),
    }
    for name, (x, y, w, h) in ents.items():
        box(ax, x, y, w, h, name, "", "conf")

    def mid(name, side):
        x, y, w, h = ents[name]
        return {"r": (x + w + 0.3, y + h / 2), "l": (x - 0.3, y + h / 2),
                "t": (x + w / 2, y + h + 0.3), "b": (x + w / 2, y - 0.3)}[side]

    def rel(a, sa, b, sb, text):
        (x1, y1), (x2, y2) = mid(a, sa), mid(b, sb)
        ax.plot([x1, x2], [y1, y2], color=NAVY, lw=1.2)
        ax.text((x1 + x2) / 2, (y1 + y2) / 2 + 1.2, text, fontsize=7.5, ha="center", style="italic")

    # Cardinalities are in models/conceptual.md; labels here stay short so they fit the gaps.
    rel("Customer", "r", "Order", "l", "places")
    rel("Order", "r", "Order item", "l", "contains")
    rel("Order item", "r", "Seller", "l", "supplied by")
    rel("Order item", "b", "Product", "t", "refers to")
    rel("Order", "b", "Payment", "t", "paid by")
    rel("Order", "t", "Review", "b", "reviewed in")
    rel("Customer", "b", "Location", "t", "located at")
    # Seller to Location is routed along the bottom so it does not cross the other boxes.
    ax.plot([89, 89, 18, 18], [44, 16, 16, 21.7], color=NAVY, lw=1.2)
    ax.text(54, 17.2, "located at", fontsize=7.5, ha="center", style="italic")

    ax.text(4, 4, "Retail mapping: Invoice = Order, Invoice line = Order item, StockCode = Product.\n"
                  "Retail has no Seller, Payment or Review, so those entities are empty for that source.",
            fontsize=8, color="#444444", va="bottom")
    ax.set_title("Figure 2. Conceptual model", fontsize=11, loc="left", color=NAVY)
    fig.savefig(path, dpi=150, bbox_inches="tight"); plt.close(fig)


def star(path):
    fig, ax = plt.subplots(figsize=(13, 9.5))
    ax.set_xlim(0, 100); ax.set_ylim(0, 92); ax.axis("off")
    box(ax, 2, 60, 22, 16, "dim_date", "date_key, full_date\nyear, quarter, month, day\nday_of_week, is_weekend", "conf")
    box(ax, 2, 42, 22, 14, "dim_customer", "customer_key, source_system\nsource_customer_id\nzip_code_prefix, country", "dim")
    box(ax, 2, 20, 22, 16, "dim_product", "product_key, source_system\nsource_product_id, description\ncategory_en, dimensions", "dim")
    box(ax, 76, 60, 22, 16, "dim_location", "zip_code_prefix (PK)\ncity, state, country_code\nlatitude, longitude", "conf")
    box(ax, 76, 42, 22, 14, "dim_seller", "seller_key, source_seller_id\nzip_code_prefix", "dim")

    box(ax, 30, 40, 38, 20, "fact_order_item", "order_item_key, order_id\norder_item_seq\ncustomer_key, product_key, seller_key\npurchase_date_key, delivered_date_key\nprice, freight_value, delivery_days", "fact")
    box(ax, 30, 20, 38, 14, "fact_payment", "order_id, payment_seq (PK)\npurchase_date_key, payment_type\npayment_installments, payment_value", "fact")
    box(ax, 30, 4, 38, 12, "fact_review", "review_id (PK), order_id\ncustomer_key, creation_date_key\nreview_score, has_comment", "fact")
    box(ax, 30, 70, 38, 19, "fact_retail_line", "line_key, invoice_no, line_no\ncustomer_key (nullable), product_key\ninvoice_date_key, country\nquantity, unit_price, line_amount, is_cancellation", "fact")

    # Foreign-key arrows only: dimension -> fact, and fact -> fact via order_id. Column names are in the boxes.
    arrow(ax, 24.3, 66, 30, 56)                  # dim_date -> fact_order_item
    arrow(ax, 24.3, 49, 30, 49)                  # dim_customer -> fact_order_item
    arrow(ax, 24.3, 28, 30, 42)                  # dim_product -> fact_order_item
    arrow(ax, 76, 49, 68, 49)                    # dim_seller -> fact_order_item
    arrow(ax, 87, 56, 87, 60)                    # dim_seller -> dim_location (zip_code_prefix)
    arrow(ax, 24.3, 74, 30, 80)                  # dim_date -> fact_retail_line
    arrow(ax, 24.3, 53, 30, 74)                  # dim_customer -> fact_retail_line
    arrow(ax, 24.3, 34, 30, 76)                  # dim_product -> fact_retail_line
    arrow(ax, 49, 40, 49, 34, "order_id")        # fact_order_item -> fact_payment
    arrow(ax, 49, 20, 49, 16, "order_id")        # fact_payment -> fact_review
    ax.text(50, 90.5, "Conformed dims (shared): dim_date, dim_location.  Source-specific: dim_customer, dim_product.",
            ha="center", fontsize=8, color="#444444")
    ax.set_title("Figure 3. Physical model: gold star schema (see models/physical.sql)", fontsize=11, loc="left", color=NAVY)
    fig.savefig(path, dpi=150, bbox_inches="tight"); plt.close(fig)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="output")
    args = parser.parse_args()
    figs = Path(args.out) / "figures"
    figs.mkdir(parents=True, exist_ok=True)
    architecture(figs / "01_architecture.png")
    conceptual(figs / "02_conceptual.png")
    star(figs / "03_star_schema.png")
    print("wrote", sorted(p.name for p in figs.glob("*.png")))


if __name__ == "__main__":
    main()
