"""Assignment 2: classification, clustering, streaming clustering, subspace clustering,
and collaborative filtering on the UCI Online Retail data.

Time split: features use transactions before CUTOFF; labels and test sets use transactions from CUTOFF on.
This avoids leakage between what the models see and what they predict.
"""
from itertools import combinations

import numpy as np
import pandas as pd
from sklearn.cluster import DBSCAN, KMeans, MiniBatchKMeans
from sklearn.decomposition import PCA
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (accuracy_score, confusion_matrix, davies_bouldin_score, f1_score,
                             precision_score, recall_score, roc_auc_score, roc_curve, silhouette_score)
from sklearn.model_selection import train_test_split
from sklearn.neighbors import NearestNeighbors
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.tree import DecisionTreeClassifier

from clean import clean

CUTOFF = pd.Timestamp("2011-10-01")
SEED = 42
CLASS_FEATURES = ["recency_days", "frequency", "monetary", "avg_order_value",
                  "distinct_products", "avg_units_per_line", "active_months", "tenure_days"]
CLUSTER_FEATURES = ["recency_days", "frequency", "monetary", "avg_order_value", "distinct_products"]


def load(path, log=print):
    raw = pd.read_csv(path, encoding="ISO-8859-1", parse_dates=["InvoiceDate"])
    return clean(raw, log=log)


def customer_features(df: pd.DataFrame, end: pd.Timestamp) -> pd.DataFrame:
    """Per-customer behaviour from transactions before `end`."""
    d = df[df.InvoiceDate < end]
    g = d.groupby("CustomerID")
    orders = g.InvoiceNo.nunique()
    spend = g.LineTotal.sum()
    return pd.DataFrame({
        "recency_days": (end - g.InvoiceDate.max()).dt.days,
        "frequency": orders,
        "monetary": spend,
        "avg_order_value": spend / orders,
        "distinct_products": g.StockCode.nunique(),
        "avg_units_per_line": g.Quantity.mean(),
        "active_months": g.InvoiceDate.agg(lambda s: s.dt.to_period("M").nunique()),
        "tenure_days": (g.InvoiceDate.max() - g.InvoiceDate.min()).dt.days,
    })


def make_dataset(df: pd.DataFrame):
    """Features before CUTOFF; label = in the top quartile of spend after CUTOFF."""
    feats = customer_features(df, CUTOFF)
    future = df[df.InvoiceDate >= CUTOFF].groupby("CustomerID").LineTotal.sum()
    feats["future_spend"] = future.reindex(feats.index).fillna(0.0)
    threshold = float(feats.future_spend.quantile(0.75))
    feats["high_value"] = (feats.future_spend >= threshold).astype(int)
    return feats, threshold


# ---------- 1. Supervised classification ----------

def classify(feats: pd.DataFrame, log=print):
    X, y = feats[CLASS_FEATURES], feats["high_value"]
    Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.3, stratify=y, random_state=SEED)
    models = {
        "logistic_regression": make_pipeline(StandardScaler(),
                                             LogisticRegression(max_iter=2000, class_weight="balanced")),
        "decision_tree": DecisionTreeClassifier(max_depth=5, class_weight="balanced", random_state=SEED),
    }
    results, curves = {}, {}
    for name, model in models.items():
        model.fit(Xtr, ytr)
        pred = model.predict(Xte)
        proba = model.predict_proba(Xte)[:, 1]
        results[name] = {
            "accuracy": float(accuracy_score(yte, pred)),
            "precision": float(precision_score(yte, pred, zero_division=0)),
            "recall": float(recall_score(yte, pred, zero_division=0)),
            "f1": float(f1_score(yte, pred, zero_division=0)),
            "roc_auc": float(roc_auc_score(yte, proba)),
            "confusion_matrix": confusion_matrix(yte, pred).tolist(),
        }
        fpr, tpr, _ = roc_curve(yte, proba)
        curves[name] = (fpr, tpr)
        log(f"  {name}: " + ", ".join(f"{k}={v:.3f}" for k, v in results[name].items() if k != "confusion_matrix"))
    importance = dict(zip(CLASS_FEATURES, map(float, models["decision_tree"].feature_importances_)))
    info = {"train_size": len(ytr), "test_size": len(yte), "positive_rate": float(y.mean())}
    return results, curves, importance, info


# ---------- 2. Unsupervised clustering ----------

def scaled(feats: pd.DataFrame, cols) -> np.ndarray:
    return StandardScaler().fit_transform(np.log1p(feats[cols].clip(lower=0)))


def kmeans_select(X: np.ndarray, ks=range(2, 9)):
    rows = []
    for k in ks:
        km = KMeans(n_clusters=k, n_init=10, random_state=SEED).fit(X)
        rows.append({
            "k": k,
            "inertia": float(km.inertia_),
            "silhouette": float(silhouette_score(X, km.labels_, sample_size=2000, random_state=SEED)),
            "davies_bouldin": float(davies_bouldin_score(X, km.labels_)),
        })
    best = max(rows, key=lambda r: r["silhouette"])
    labels = KMeans(n_clusters=best["k"], n_init=10, random_state=SEED).fit_predict(X)
    return rows, best["k"], labels


def dbscan(X: np.ndarray, min_samples: int = 5):
    dist, _ = NearestNeighbors(n_neighbors=min_samples).fit(X).kneighbors(X)
    eps = float(np.percentile(dist[:, -1], 90))  # k-distance heuristic
    labels = DBSCAN(eps=eps, min_samples=min_samples).fit_predict(X)
    mask = labels != -1
    n_clusters = len(set(labels[mask]))
    sil = float(silhouette_score(X[mask], labels[mask])) if n_clusters > 1 else float("nan")
    return {"eps": eps, "min_samples": min_samples, "clusters": n_clusters,
            "noise_share": float((~mask).mean()), "silhouette_non_noise": sil}, labels


def cluster_profiles(feats: pd.DataFrame, labels) -> pd.DataFrame:
    prof = feats[CLUSTER_FEATURES + ["future_spend"]].groupby(labels).median()
    prof.insert(0, "customers", pd.Series(labels).value_counts().sort_index().values)
    return prof.round(2)


# ---------- 3. Streaming clustering (micro-batch approximation) ----------

def invoice_features(df: pd.DataFrame) -> pd.DataFrame:
    g = df.groupby("InvoiceNo")
    inv = pd.DataFrame({
        "ts": g.InvoiceDate.min(),
        "n_products": g.StockCode.nunique(),
        "n_units": g.Quantity.sum(),
        "total": g.LineTotal.sum(),
    })
    inv["month"] = inv.ts.dt.to_period("M").astype(str)
    return inv.sort_values("ts")


def stream_cluster(df: pd.DataFrame, k: int = 4, log=print):
    """Invoices arrive month by month. MiniBatchKMeans is updated with partial_fit on each batch,
    and centroid drift and silhouette are recorded per batch. This is incremental k-means,
    not CluStream or StreamKM++."""
    inv = invoice_features(df)
    cols = ["n_products", "n_units", "total"]
    scaler = StandardScaler()
    model = MiniBatchKMeans(n_clusters=k, random_state=SEED, batch_size=512, n_init=3)
    rows, prev = [], None
    for i, (month, batch) in enumerate(inv.groupby("month")):
        X = np.log1p(batch[cols].to_numpy(float))
        if i == 0:
            scaler.fit(X)  # scaler fixed on the first batch
        Xs = scaler.transform(X)
        model.partial_fit(Xs)
        labels = model.predict(Xs)
        centers = model.cluster_centers_.copy()
        shift = float(np.linalg.norm(centers - prev, axis=1).mean()) if prev is not None else 0.0
        prev = centers
        sil = (float(silhouette_score(Xs, labels, sample_size=min(2000, len(Xs)), random_state=SEED))
               if len(set(labels)) > 1 else float("nan"))
        rows.append({"month": month, "invoices": len(batch), "centroid_shift": shift, "silhouette": sil})
    log(f"  {len(rows)} monthly batches, {len(inv):,} invoices")
    return pd.DataFrame(rows)


# ---------- 4. Feature extraction and subspace clustering ----------

def subspace(feats: pd.DataFrame, k: int, variance: float = 0.9):
    """(a) PCA subspace that keeps `variance` of the variance, clustered with k-means.
    (b) Exhaustive search over all 2-feature subspaces, ranked by silhouette."""
    X = scaled(feats, CLUSTER_FEATURES)
    pca_full = PCA().fit(X)
    cum = np.cumsum(pca_full.explained_variance_ratio_)
    n = int(np.searchsorted(cum, variance) + 1)
    pca = PCA(n_components=n, random_state=SEED)
    Xp = pca.fit_transform(X)

    def sil(Z, lab):
        return float(silhouette_score(Z, lab, sample_size=2000, random_state=SEED))

    lab_full = KMeans(k, n_init=10, random_state=SEED).fit_predict(X)
    lab_pca = KMeans(k, n_init=10, random_state=SEED).fit_predict(Xp)
    pairs = []
    for a, b in combinations(range(len(CLUSTER_FEATURES)), 2):
        Z = X[:, [a, b]]
        lab = KMeans(k, n_init=10, random_state=SEED).fit_predict(Z)
        pairs.append({"subspace": f"{CLUSTER_FEATURES[a]} + {CLUSTER_FEATURES[b]}", "silhouette": sil(Z, lab)})
    pairs.sort(key=lambda r: -r["silhouette"])
    return {
        "pca_components": n,
        "pca_explained_cumulative": cum.tolist(),
        "pca_loadings": pd.DataFrame(pca.components_, columns=CLUSTER_FEATURES,
                                     index=[f"PC{i + 1}" for i in range(n)]).round(3),
        "silhouette_full_space": sil(X, lab_full),
        "silhouette_pca_space": sil(Xp, lab_pca),
        "pair_ranking": pairs,
        "pc2d": Xp[:, :2],
        "labels_pca": lab_pca,
    }


# ---------- 5. Collaborative filtering ----------

def collaborative_filter(df: pd.DataFrame, top_items: int = 500, top_n: int = 5, max_users: int = 1000,
                         log=print):
    """Item-item cosine similarity on purchases before CUTOFF. Recommend top_n unseen products to each
    customer and check against products they bought after CUTOFF. Compared with a popularity baseline."""
    train = df[df.InvoiceDate < CUTOFF]
    test = df[df.InvoiceDate >= CUTOFF]
    items = pd.Index(train.StockCode.value_counts().head(top_items).index)
    tr = train[train.StockCode.isin(items)]
    M = pd.crosstab(tr.CustomerID, tr.StockCode).reindex(columns=items, fill_value=0)
    B = (M.to_numpy() > 0).astype(float)

    norms = np.linalg.norm(B, axis=0)
    norms[norms == 0] = 1
    Bn = B / norms
    S = Bn.T @ Bn
    np.fill_diagonal(S, 0)

    te = test[test.StockCode.isin(items) & test.CustomerID.isin(M.index)]
    rel = te.groupby("CustomerID").StockCode.agg(set).to_dict()
    eval_users = [u for u in M.index if u in rel][:max_users]
    idx = [M.index.get_loc(u) for u in eval_users]
    U = B[idx]
    truth = [rel[u] for u in eval_users]

    pop = np.tile(B.sum(axis=0), (len(idx), 1))
    cf = U @ S
    cf[U > 0] = -1  # never recommend what the customer already bought
    pop[U > 0] = -1

    def evaluate(scores):
        hits = []
        precisions, recalls = [], []
        for r, t in enumerate(truth):
            top = items[np.argsort(-scores[r])[:top_n]]
            h = len(set(top) & t)
            hits.append(h)
            precisions.append(h / top_n)
            recalls.append(h / len(t))
        return {"precision_at_n": float(np.mean(precisions)), "recall_at_n": float(np.mean(recalls)),
                "hit_rate": float(np.mean([h > 0 for h in hits]))}

    desc = df.drop_duplicates("StockCode").set_index("StockCode").Description
    examples = []
    for r in range(min(3, len(idx))):
        top = items[np.argsort(-cf[r])[:top_n]]
        examples.append({"customer": eval_users[r],
                         "bought_before": [desc.get(s, s) for s in M.columns[U[r] > 0][:5]],
                         "recommended": [desc.get(s, s) for s in top]})
    result = {"users_evaluated": len(eval_users), "items": int(len(items)), "top_n": top_n,
              "item_knn_cosine": evaluate(cf), "popularity_baseline": evaluate(pop), "examples": examples}
    log(f"  users={len(eval_users)} CF={result['item_knn_cosine']} POP={result['popularity_baseline']}")
    return result
