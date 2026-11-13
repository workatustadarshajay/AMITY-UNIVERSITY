"""Apriori on a toy example worked out by hand (run: python -m pytest tests)."""
import pytest

from pipeline.apriori import association_rules, frequent_itemsets
from pipeline.similarity import pair_table, product_baskets

BASKETS = [frozenset(x) for x in [["a", "b", "c"], ["a", "b"], ["a", "c"], ["b", "c", "d"], ["a", "b", "c", "d"]]]


def test_itemset_counts_match_hand_count():
    fi = frequent_itemsets(BASKETS, min_support=0.4, max_len=3)  # threshold: 2 of 5 baskets
    assert fi[frozenset("ab")] == 3
    assert fi[frozenset("abc")] == 2
    assert frozenset("ad") not in fi        # only basket 5
    assert fi[frozenset("bcd")] == 2


def test_rule_confidence_and_lift():
    fi = frequent_itemsets(BASKETS, min_support=0.4, max_len=3)
    rules = association_rules(fi, len(BASKETS), min_confidence=0.5)
    row = rules[(rules.antecedent == "d") & (rules.consequent == "b + c")].iloc[0]
    assert row["confidence"] == pytest.approx(1.0)           # d appears in 2 baskets, both have b and c
    assert row["lift"] == pytest.approx(1.0 / (3 / 5))       # support(b+c) = 3/5


def test_min_confidence_filters_rules():
    fi = frequent_itemsets(BASKETS, min_support=0.4, max_len=2)
    rules = association_rules(fi, len(BASKETS), min_confidence=0.9)
    assert (rules["confidence"] >= 0.9).all()


def test_similarity_jaccard_and_dissimilarity():
    idx = product_baskets(BASKETS)
    t = pair_table(idx, ["a", "d"])
    row = t.iloc[0]
    # a is in baskets {0,1,2,4}; d in {3,4}; both: {4}; union: {0,1,2,3,4}
    assert row["co_occurrences"] == 1
    assert row["jaccard"] == pytest.approx(1 / 5)
    assert row["dissimilarity"] == pytest.approx(4 / 5)
