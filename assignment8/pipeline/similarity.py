"""Similarity and dissimilarity between products, from the baskets they appear in.

Each product is the set of invoices it appears in. For products A and B:
    jaccard(A, B)     = |A & B| / |A | B|      (overlap relative to everything either product touches)
    cosine(A, B)      = |A & B| / sqrt(|A| |B|) (overlap, less sensitive to very popular products)
    dissimilarity     = 1 - jaccard              (a distance: 0 = same baskets, 1 = never together)
"""
from itertools import combinations
from math import sqrt

import pandas as pd


def product_baskets(baskets):
    idx = {}
    for bid, items in enumerate(baskets):
        for it in items:
            idx.setdefault(it, set()).add(bid)
    return idx


def pair_table(idx, items):
    rows = []
    for a, b in combinations(sorted(items), 2):
        sa, sb = idx[a], idx[b]
        both = len(sa & sb)
        union = len(sa | sb)
        rows.append({
            "item_a": a, "item_b": b, "co_occurrences": both,
            "jaccard": both / union if union else 0.0,
            "cosine": both / sqrt(len(sa) * len(sb)) if sa and sb else 0.0,
        })
    df = pd.DataFrame(rows)
    df["dissimilarity"] = 1 - df["jaccard"]
    return df.sort_values("jaccard", ascending=False).reset_index(drop=True)
