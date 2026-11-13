"""Apriori frequent itemsets and association rules, written out explicitly.

    frequent_itemsets(baskets, min_support, max_len) -> {frozenset(items): count}
    association_rules(itemsets, n_baskets, min_confidence) -> DataFrame

Support = count / n_baskets. Confidence(A -> B) = support(A and B) / support(A).
Lift(A -> B) = confidence(A -> B) / support(B). Lift above 1 means A and B occur together more often than
independence would predict.
"""
import math
from collections import Counter
from itertools import combinations

import pandas as pd


def frequent_itemsets(baskets, min_support, max_len=3):
    n = len(baskets)
    min_count = math.ceil(min_support * n)
    item_counts = Counter(i for b in baskets for i in b)
    level = {frozenset([i]): c for i, c in item_counts.items() if c >= min_count}
    result = dict(level)
    frequent_items = {next(iter(s)) for s in level}

    k = 2
    while level and k <= max_len:
        prev = {tuple(sorted(s)) for s in level}
        cands = set()
        ordered = sorted(prev)
        for a, b in combinations(ordered, 2):
            if a[:-1] == b[:-1]:
                c = a + (b[-1],)
                # Prune: every (k-1)-subset of a candidate must itself be frequent.
                if all(sub in prev for sub in combinations(c, k - 1)):
                    cands.add(c)
        if not cands:
            break
        counts = Counter()
        for b in baskets:
            items = sorted(i for i in b if i in frequent_items)
            if len(items) < k:
                continue
            for combo in combinations(items, k):
                if combo in cands:
                    counts[combo] += 1
        level = {frozenset(c): cnt for c, cnt in counts.items() if cnt >= min_count}
        result.update(level)
        k += 1
    return result


def association_rules(itemsets, n_baskets, min_confidence=0.5):
    rows = []
    for itemset, cnt in itemsets.items():
        if len(itemset) < 2:
            continue
        items = sorted(itemset)
        for r in range(1, len(items)):
            for ante in combinations(items, r):
                ante_f = frozenset(ante)
                cons_f = itemset - ante_f
                conf = cnt / itemsets[ante_f]
                if conf < min_confidence:
                    continue
                lift = conf / (itemsets[cons_f] / n_baskets)
                rows.append({
                    "antecedent": sorted(ante_f), "consequent": sorted(cons_f),
                    "count": cnt, "support": cnt / n_baskets,
                    "confidence": conf, "lift": lift,
                })
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["antecedent"] = df["antecedent"].map(lambda x: " + ".join(x))
    df["consequent"] = df["consequent"].map(lambda x: " + ".join(x))
    return df.sort_values(["lift", "confidence"], ascending=False).reset_index(drop=True)
