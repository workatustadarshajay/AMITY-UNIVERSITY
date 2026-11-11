"""Run every Assignment 2 analysis and write metrics, figures and logs.

    python run.py --data path/to/online_retail.csv --out output
"""
import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

import analysis as A


def main(data: str, out: str):
    out = Path(out)
    fig_dir = out / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)
    metrics = {}

    print("1. Load and clean")
    df = A.load(data)
    metrics["data"] = {"clean_rows": len(df), "customers": int(df.CustomerID.nunique()),
                       "invoices": int(df.InvoiceNo.nunique())}

    print("2. Build customer dataset (features before 2011-10-01, label from after)")
    feats, threshold = A.make_dataset(df)
    metrics["labels"] = {"customers": len(feats), "high_value_threshold": threshold,
                         "high_value_customers": int(feats.high_value.sum())}
    print(f"  {len(feats):,} customers, high-value threshold {threshold:.2f}")

    print("3. Supervised classification")
    cls, curves, importance, info = A.classify(feats)
    metrics["classification"] = {"models": cls, "tree_feature_importance": importance, **info}

    fig, ax = plt.subplots(figsize=(6, 5))
    for name, (fpr, tpr) in curves.items():
        ax.plot(fpr, tpr, label=f"{name} (AUC {cls[name]['roc_auc']:.3f})")
    ax.plot([0, 1], [0, 1], "k--", lw=0.8)
    ax.set_xlabel("False positive rate")
    ax.set_ylabel("True positive rate")
    ax.set_title("ROC: predicting top-quartile future spend")
    ax.legend()
    fig.tight_layout()
    fig.savefig(fig_dir / "01_roc_curves.png", dpi=130)
    plt.close(fig)

    imp = pd.Series(importance).sort_values()
    fig, ax = plt.subplots(figsize=(7, 4.5))
    ax.barh(imp.index, imp.values, color="#4C72B0")
    ax.set_title("Decision tree feature importance")
    fig.tight_layout()
    fig.savefig(fig_dir / "02_tree_feature_importance.png", dpi=130)
    plt.close(fig)

    print("4. K-means and DBSCAN")
    X = A.scaled(feats, A.CLUSTER_FEATURES)
    k_rows, best_k, labels = A.kmeans_select(X)
    db, db_labels = A.dbscan(X)
    metrics["kmeans"] = {"selection": k_rows, "best_k": best_k,
                         "profiles": A.cluster_profiles(feats, labels).reset_index().to_dict("records")}
    metrics["dbscan"] = db
    print(f"  best k={best_k}, DBSCAN clusters={db['clusters']} noise={db['noise_share']:.1%}")

    ks = pd.DataFrame(k_rows)
    fig, ax1 = plt.subplots(figsize=(7, 4.5))
    ax1.plot(ks.k, ks.silhouette, "o-", color="#4C72B0", label="silhouette")
    ax1.set_xlabel("k")
    ax1.set_ylabel("Silhouette (higher is better)", color="#4C72B0")
    ax2 = ax1.twinx()
    ax2.plot(ks.k, ks.inertia, "s--", color="#C44E52", label="inertia")
    ax2.set_ylabel("Inertia (elbow)", color="#C44E52")
    ax1.set_title("K-means: choosing k")
    fig.tight_layout()
    fig.savefig(fig_dir / "03_kmeans_selection.png", dpi=130)
    plt.close(fig)

    pcs = A.PCA(n_components=2, random_state=A.SEED).fit_transform(X)
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5))
    axes[0].scatter(pcs[:, 0], pcs[:, 1], c=labels, cmap="tab10", s=8)
    axes[0].set_title(f"K-means (k={best_k}) on PCA 2D")
    axes[1].scatter(pcs[:, 0], pcs[:, 1], c=db_labels, cmap="tab10", s=8)
    axes[1].set_title(f"DBSCAN on PCA 2D (noise {db['noise_share']:.0%} in grey)")
    axes[1].scatter(pcs[db_labels == -1, 0], pcs[db_labels == -1, 1], c="lightgrey", s=8, zorder=0)
    for ax in axes:
        ax.set_xlabel("PC1")
        ax.set_ylabel("PC2")
    fig.tight_layout()
    fig.savefig(fig_dir / "04_clusters_pca.png", dpi=130)
    plt.close(fig)

    print("5. Streaming clustering (monthly micro-batches)")
    stream = A.stream_cluster(df, k=4)
    metrics["streaming"] = stream.to_dict("records")
    stream.to_csv(out / "streaming_batches.csv", index=False)
    fig, axes = plt.subplots(2, 1, figsize=(10, 6), sharex=True)
    axes[0].plot(stream.month, stream.centroid_shift, "o-", color="#DD8452")
    axes[0].set_ylabel("Centroid shift")
    axes[0].set_title("Streaming k-means: centroid drift per monthly batch")
    axes[1].plot(stream.month, stream.silhouette, "o-", color="#55A868")
    axes[1].set_ylabel("Silhouette (batch)")
    axes[1].tick_params(axis="x", rotation=60)
    fig.tight_layout()
    fig.savefig(fig_dir / "05_streaming_drift.png", dpi=130)
    plt.close(fig)

    print("6. Feature extraction and subspace clustering")
    sub = A.subspace(feats, best_k)
    metrics["subspace"] = {k: v for k, v in sub.items() if k not in ("pc2d", "labels_pca", "pca_loadings")}
    metrics["subspace"]["pca_loadings"] = sub["pca_loadings"].to_dict()
    print(f"  PCA components={sub['pca_components']} silhouette full={sub['silhouette_full_space']:.3f} "
          f"pca={sub['silhouette_pca_space']:.3f}")
    pr = pd.DataFrame(sub["pair_ranking"])
    fig, ax = plt.subplots(figsize=(9, 6))
    ax.barh(pr["subspace"][::-1], pr["silhouette"][::-1], color="#8172B2")
    ax.set_xlabel("Silhouette in the 2-feature subspace")
    ax.set_title("Subspace search: which feature pairs separate customers best")
    fig.tight_layout()
    fig.savefig(fig_dir / "06_subspace_ranking.png", dpi=130)
    plt.close(fig)

    print("7. Collaborative filtering")
    cf = A.collaborative_filter(df)
    metrics["collaborative_filtering"] = cf
    labels_cf = ["precision@5", "recall@5", "hit rate"]
    cf_vals = [cf["item_knn_cosine"]["precision_at_n"], cf["item_knn_cosine"]["recall_at_n"],
               cf["item_knn_cosine"]["hit_rate"]]
    pop_vals = [cf["popularity_baseline"]["precision_at_n"], cf["popularity_baseline"]["recall_at_n"],
                cf["popularity_baseline"]["hit_rate"]]
    xs = np.arange(len(labels_cf))
    fig, ax = plt.subplots(figsize=(7, 4.5))
    ax.bar(xs - 0.2, cf_vals, 0.4, label="item-item cosine", color="#4C72B0")
    ax.bar(xs + 0.2, pop_vals, 0.4, label="popularity", color="#BBBBBB")
    ax.set_xticks(xs, labels_cf)
    ax.legend()
    ax.set_title("Recommendations on post-cutoff purchases")
    fig.tight_layout()
    fig.savefig(fig_dir / "07_cf_comparison.png", dpi=130)
    plt.close(fig)

    (out / "metrics.json").write_text(json.dumps(metrics, indent=2, default=float), encoding="utf-8")
    print(f"Done. Metrics: {out / 'metrics.json'}  Figures: {fig_dir}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/online_retail.csv")
    ap.add_argument("--out", default="output")
    a = ap.parse_args()
    main(a.data, a.out)
