"""Build the Assignment 2 PDF report from output/metrics.json and output/figures.

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
from reportlab.platypus import Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

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


def f(x, nd=3):
    return "n/a" if x != x else f"{x:.{nd}f}"  # NaN check


def main(out: str):
    out = Path(out)
    m = json.loads((out / "metrics.json").read_text(encoding="utf-8"))
    figs = out / "figures"
    cls = m["classification"]
    km = m["kmeans"]
    db = m["dbscan"]
    sub = m["subspace"]
    cf = m["collaborative_filtering"]
    stream = m["streaming"]

    s = []
    s.append(Paragraph("Classification and Clustering of Big Data: Online Retail Customers", H1))
    s.append(Paragraph("Assignment No. 2", BODY))
    s.append(Spacer(1, 0.3 * cm))

    s.append(Paragraph("1. Execution environment and scope", H2))
    s.append(Paragraph(
        "All code in this report was executed locally on a Windows 11 machine with Python 3.12, pandas, "
        "scikit-learn and matplotlib. The dataset is the UCI Online Retail dataset (541,909 raw rows). "
        "The Kaggle datasets listed in the brief were not used. "
        "Streaming clustering is an incremental mini-batch k-means approximation, and subspace clustering uses "
        "PCA plus an exhaustive two-feature search. Neither is a full CluStream, StreamKM++, CLIQUE or PROCLUS "
        "implementation.", BODY))

    s.append(Paragraph("2. Data and labels", H2))
    s.append(Paragraph(
        f"After cleaning: {m['data']['clean_rows']:,} rows, {m['data']['customers']:,} customers, "
        f"{m['data']['invoices']:,} invoices. Features come from transactions before 1 Oct 2011. The label is "
        f"<i>high value</i>: a customer's spend after 1 Oct 2011 is in the top quartile "
        f"(threshold {m['labels']['high_value_threshold']:.2f}). Using a time split avoids leakage between inputs "
        f"and target. {m['labels']['customers']:,} customers are in the dataset, and "
        f"{m['labels']['high_value_customers']:,} are labelled high value.", BODY))

    s.append(Paragraph("3. Supervised classification", H2))
    rows = [["Model", "Accuracy", "Precision", "Recall", "F1", "ROC AUC"]]
    for name, r in cls["models"].items():
        rows.append([name, f(r["accuracy"]), f(r["precision"]), f(r["recall"]), f(r["f1"]), f(r["roc_auc"])])
    s.append(table(rows, widths=[5 * cm, 2.2 * cm, 2.2 * cm, 2.2 * cm, 2 * cm, 2.4 * cm]))
    s.append(Spacer(1, 0.2 * cm))
    s.append(Paragraph(
        f"Train {cls['train_size']:,}, test {cls['test_size']:,}, positive rate {cls['positive_rate']:.2%}. "
        "Both models use balanced class weights. Logistic regression is the stronger model on AUC and F1. "
        "The decision tree (depth 5) has higher recall but lower precision, and its feature importances show which "
        "behaviours matter most.", BODY))
    s.append(fig(figs / "01_roc_curves.png", width=11 * cm))
    s.append(fig(figs / "02_tree_feature_importance.png", width=12 * cm))
    s.append(PageBreak())

    s.append(Paragraph("4. Unsupervised clustering", H2))
    s.append(Paragraph(
        "Features: recency, frequency, monetary, average order value and distinct products, log-transformed "
        "and standardized. K-means chose k by silhouette score. DBSCAN used eps set at the 90th percentile of "
        "5-nearest-neighbour distances.", BODY))
    rows = [["k", "Inertia", "Silhouette", "Davies-Bouldin"]] + [
        [r["k"], f"{r['inertia']:.0f}", f(r["silhouette"]), f(r["davies_bouldin"])] for r in km["selection"]]
    s.append(table(rows, widths=[2 * cm, 3.5 * cm, 3.5 * cm, 4 * cm]))
    s.append(Spacer(1, 0.2 * cm))
    s.append(Paragraph(
        f"The best silhouette is at k={km['best_k']}. DBSCAN found {db['clusters']} clusters with "
        f"{db['noise_share']:.1%} noise (eps {db['eps']:.3f}, min_samples {db['min_samples']}). "
        "The clusters form a continuum rather than separate groups, so the two-cluster solution is a broad split, "
        "not distinct segments.", BODY))
    prof = km["profiles"]
    rows = [["Cluster", "Customers", "Recency (days)", "Frequency", "Monetary", "Avg order", "Products", "Future spend"]]
    for p in prof:
        rows.append([p["index"] if "index" in p else p.get("CustomerID", ""), int(p["customers"]),
                     f(p["recency_days"], 0), f(p["frequency"], 0), f(p["monetary"], 0),
                     f(p["avg_order_value"], 0), f(p["distinct_products"], 0), f(p["future_spend"], 0)])
    s.append(Paragraph("Cluster profiles (medians):", BODY))
    s.append(table(rows, widths=[1.6 * cm, 2 * cm, 2.4 * cm, 2 * cm, 2.2 * cm, 2 * cm, 2 * cm, 2.4 * cm]))
    s.append(fig(figs / "03_kmeans_selection.png", width=12 * cm))
    s.append(fig(figs / "04_clusters_pca.png"))
    s.append(PageBreak())

    s.append(Paragraph("5. Streaming clustering", H2))
    s.append(Paragraph(
        "Invoices are processed month by month in time order. MiniBatchKMeans (k=4) is updated with partial_fit on "
        "each monthly batch, and centroid drift and silhouette are recorded. The scaler is fixed on the first batch. "
        "This is incremental clustering, not CluStream or StreamKM++.", BODY))
    rows = [["Month", "Invoices", "Centroid shift", "Silhouette"]] + [
        [r["month"], f"{r['invoices']:,}", f(r["centroid_shift"], 4), f(r["silhouette"])] for r in stream]
    s.append(table(rows, widths=[3 * cm, 3 * cm, 4 * cm, 4 * cm]))
    s.append(Spacer(1, 0.2 * cm))
    s.append(fig(figs / "05_streaming_drift.png"))
    s.append(PageBreak())

    s.append(Paragraph("6. Feature extraction and subspace clustering", H2))
    s.append(Paragraph(
        f"PCA keeps 90% of the variance with {sub['pca_components']} components. Silhouette at k={km['best_k']}: "
        f"full feature space {f(sub['silhouette_full_space'])}, PCA subspace {f(sub['silhouette_pca_space'])}. "
        "The PCA subspace is slightly better, meaning a few combined directions carry the separation. "
        "The search over all two-feature subspaces ranks which pairs separate customers best.", BODY))
    rows = [["Subspace (2 features)", "Silhouette"]] + [[r["subspace"], f(r["silhouette"])] for r in sub["pair_ranking"][:10]]
    s.append(table(rows, widths=[9 * cm, 3 * cm]))
    s.append(fig(figs / "06_subspace_ranking.png", width=13 * cm))
    s.append(PageBreak())

    s.append(Paragraph("7. Collaborative filtering", H2))
    s.append(Paragraph(
        f"Item-item cosine similarity on the top {cf['items']} products, using purchases before 1 Oct 2011. "
        f"For {cf['users_evaluated']:,} customers with purchases before and after the cutoff, the top {cf['top_n']} "
        "unseen products are recommended and compared with the products each customer bought later. The popularity "
        "baseline recommends the most-bought products the customer has not yet bought.", BODY))
    rows = [["Method", "Precision@5", "Recall@5", "Hit rate"]]
    for name, key in [("Item-item cosine", "item_knn_cosine"), ("Popularity baseline", "popularity_baseline")]:
        r = cf[key]
        rows.append([name, f(r["precision_at_n"]), f(r["recall_at_n"]), f(r["hit_rate"])])
    s.append(table(rows, widths=[6 * cm, 3.5 * cm, 3.5 * cm, 3 * cm]))
    s.append(Spacer(1, 0.2 * cm))
    s.append(Paragraph("Example recommendations:", BODY))
    for ex in cf["examples"]:
        s.append(Paragraph(f"Customer {ex['customer']}: bought earlier: {', '.join(ex['bought_before'][:3])}. "
                           f"Recommended: {', '.join(ex['recommended'])}.", BODY))
    s.append(fig(figs / "07_cf_comparison.png", width=11 * cm))
    s.append(PageBreak())

    s.append(Paragraph("8. Conclusions and limitations", H2))
    for t in [
        "Logistic regression separates high-value customers reasonably well (AUC shown in section 3).",
        "Clusters are a continuum on these features. K-means at k=2 is a broad split, not a set of distinct segments.",
        "Streaming results are from an incremental approximation. Centroid drift is largest in the first month, "
        "then settles.",
        "Subspace clustering uses PCA and a two-feature search, not a dedicated subspace algorithm.",
        "Collaborative filtering beats the popularity baseline on hit rate and recall. Absolute accuracy is low, "
        "as expected for implicit purchase data.",
        "The Kaggle datasets were not used. Only the UCI Online Retail data was analysed.",
    ]:
        s.append(Paragraph("- " + t, BODY))

    doc = SimpleDocTemplate(str(out / "Assignment2_Report.pdf"), pagesize=A4,
                            leftMargin=2 * cm, rightMargin=2 * cm, topMargin=2 * cm, bottomMargin=2 * cm,
                            title="Assignment 2 Report")
    doc.build(s)
    print("wrote", out / "Assignment2_Report.pdf")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="output")
    main(ap.parse_args().out)
