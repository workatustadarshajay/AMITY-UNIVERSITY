"""Checks for Assignment 2 logic on small synthetic data.   python -m pytest tests   (run from assignment2/)"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.datasets import make_blobs

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import analysis as A  # noqa: E402


def test_dbscan_finds_two_blobs():
    X, _ = make_blobs(n_samples=300, centers=[[0, 0], [10, 10]], cluster_std=0.5, random_state=0)
    info, labels = A.dbscan(X, min_samples=5)
    assert info["clusters"] == 2
    # eps is the 90th percentile of k-distances, so roughly 10% of points are labelled noise by design
    assert info["noise_share"] < 0.2


def test_kmeans_selection_picks_true_k():
    X, _ = make_blobs(n_samples=400, centers=3, cluster_std=0.4, random_state=1)
    _, best_k, _ = A.kmeans_select(X, ks=range(2, 6))
    assert best_k == 3


def test_collaborative_filter_recommends_co_purchased_item():
    rows = []
    # customers 1-20 buy A and B together before the cutoff; customer 99 buys only A before
    for c in range(1, 21):
        rows += [(f"c{c}", "A", "2011-01-05"), (f"c{c}", "B", "2011-01-05")]
    rows += [("c99", "A", "2011-02-01")]
    # after the cutoff c99 buys B
    rows += [("c99", "B", "2011-11-01")]
    df = pd.DataFrame(rows, columns=["CustomerID", "StockCode", "InvoiceDate"])
    df["InvoiceDate"] = pd.to_datetime(df["InvoiceDate"])
    df["Description"] = df["StockCode"]
    df["InvoiceNo"] = [f"i{i}" for i in range(len(df))]
    df["Quantity"] = 1
    df["UnitPrice"] = 1.0
    df["LineTotal"] = 1.0
    res = A.collaborative_filter(df, top_items=10, top_n=1)
    assert res["users_evaluated"] == 1
    # c99 has only seen A; B is the only unseen item, co-bought with A, and it is what c99 buys later
    assert res["item_knn_cosine"]["hit_rate"] == 1.0
    assert res["examples"][0]["recommended"] == ["B"]


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
