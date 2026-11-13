"""CDC: the diff and apply must round-trip, and nulls must compare equal (run: python -m pytest tests)."""
import pandas as pd

from pipeline.cdc import PAYLOAD, apply_ops, diff, simulate_changes


def _base():
    return pd.DataFrame({
        "line_id": ["1-A-1", "1-B-1", "2-A-1", "3-C-1"],
        "InvoiceNo": ["1", "1", "2", "3"], "StockCode": ["A", "B", "A", "C"],
        "Description": ["x", None, "x", "z"], "Quantity": [1, 2, 3, 4],
        "InvoiceDate": ["2010-12-01 08:00:00"] * 4, "UnitPrice": ["1.00", "2.00", "1.00", "3.00"],
        "CustomerID": ["100", None, "100", "300"], "Country": ["UK", "UK", "UK", "FR"],
    })


def test_unchanged_snapshot_gives_no_ops_even_with_nulls():
    b = _base()
    ops = diff(b, b.copy())
    assert ops.empty


def test_update_insert_delete_are_detected_and_applied():
    old = _base()
    new = old.copy()
    new.loc[0, "Quantity"] = 9                       # update
    new = new.drop(index=2)                          # delete 2-A-1
    extra = old.iloc[[3]].copy()
    extra["line_id"] = "9-C-1"; extra["InvoiceNo"] = "9"   # insert
    new = pd.concat([new, extra], ignore_index=True)

    ops = diff(old, new)
    assert dict(ops["op"].value_counts()) == {"U": 1, "D": 1, "I": 1}
    got = apply_ops(old, ops)
    exp = new.sort_values("line_id").reset_index(drop=True)
    cols = ["line_id"] + PAYLOAD
    assert got[cols].fillna("<N>").astype(str).equals(exp[cols].fillna("<N>").astype(str))


def test_simulated_changes_round_trip():
    old = _base()
    new = simulate_changes(old, seed=1, update_frac=0.5, delete_frac=0.25, insert_frac=0.25)
    ops = diff(old, new)
    assert set(ops["op"]) == {"U", "D", "I"}
    got = apply_ops(old, ops)
    exp = new.sort_values("line_id").reset_index(drop=True)
    cols = ["line_id"] + PAYLOAD
    assert got[cols].fillna("<N>").astype(str).equals(exp[cols].fillna("<N>").astype(str))
