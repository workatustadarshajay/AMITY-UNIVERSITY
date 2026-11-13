"""Change data capture between two snapshots of the raw table, keyed on line_id.

    diff(old, new)  -> ops table with op in {I, U, D} (one row per changed line)
    apply_ops(old, ops) -> the new snapshot, which the Redshift MERGE reproduces

simulate_changes() stands in for a source system's day-2 changes: some lines are updated, some are
deleted, and some new lines are inserted. Only the simulation is synthetic; the diff and apply are the real logic.
"""
import argparse
from pathlib import Path

import numpy as np
import pandas as pd

PAYLOAD = ["InvoiceNo", "StockCode", "Description", "Quantity", "InvoiceDate", "UnitPrice", "CustomerID", "Country"]


def simulate_changes(base, seed=7, update_frac=0.01, delete_frac=0.005, insert_frac=0.005):
    rng = np.random.default_rng(seed)
    n = len(base)
    new = base.copy()

    upd_idx = rng.choice(n, size=int(n * update_frac), replace=False)
    new.loc[new.index[upd_idx], "Quantity"] = new["Quantity"].iloc[upd_idx].values + 1

    del_idx = rng.choice(n, size=int(n * delete_frac), replace=False)
    new = new.drop(new.index[del_idx])

    k = int(n * insert_frac)
    src = base.sample(n=k, random_state=seed).copy()
    src["InvoiceNo"] = [f"A{900000 + i:06d}" for i in range(k)]   # new invoice numbers, not cancellations
    src["line_id"] = src["InvoiceNo"] + "-" + src["StockCode"] + "-1"
    return pd.concat([new, src], ignore_index=True)


def _norm(s):
    """Text form of a column, with nulls made explicit so that null equals null."""
    return s.map(lambda v: "<NULL>" if pd.isna(v) else str(v))


def _same(a, b):
    return _norm(a).eq(_norm(b))


def diff(old, new):
    m = old.merge(new, on="line_id", how="outer", suffixes=("_o", "_n"), indicator=True)
    ins = m[m["_merge"] == "right_only"]
    dele = m[m["_merge"] == "left_only"]
    both = m[m["_merge"] == "both"]
    changed = np.zeros(len(both), dtype=bool)
    for c in PAYLOAD:
        changed |= ~_same(both[f"{c}_o"], both[f"{c}_n"]).values
    upd = both[changed]

    def pick(frame, op, cols_src):
        out = pd.DataFrame({"line_id": frame["line_id"], "op": op})
        for c in PAYLOAD:
            out[c] = frame[f"{c}_n"] if cols_src == "n" else frame[f"{c}_o"]
        out["Quantity"] = out["Quantity"].astype("int64")  # outer merge can turn it into float
        return out

    ops = pd.concat([pick(ins, "I", "n"), pick(upd, "U", "n"), pick(dele, "D", "o")], ignore_index=True)
    return ops.sort_values(["op", "line_id"]).reset_index(drop=True)


def apply_ops(old, ops):
    """Set-based apply: drop deleted and updated lines, then add the I and U rows back."""
    deletes = set(ops.loc[ops["op"] == "D", "line_id"])
    upserts = ops[ops["op"] != "D"][["line_id"] + PAYLOAD]
    keep = old[~old["line_id"].isin(deletes | set(upserts["line_id"]))][["line_id"] + PAYLOAD]
    out = pd.concat([keep, upserts], ignore_index=True)
    return out.sort_values("line_id").reset_index(drop=True)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--day1", required=True, help="raw CSV for day 1 (from extract)")
    p.add_argument("--out", default="s3_local")
    p.add_argument("--seed", type=int, default=7)
    a = p.parse_args()
    base = pd.read_csv(a.day1, dtype=str)
    base["Quantity"] = base["Quantity"].astype(int)
    new = simulate_changes(base, seed=a.seed)
    ops = diff(base, new)
    out = Path(a.out)
    (out / "raw" / "day2").mkdir(parents=True, exist_ok=True)
    (out / "cdc" / "day2").mkdir(parents=True, exist_ok=True)
    new.to_csv(out / "raw" / "day2" / "online_retail.csv", index=False)
    ops.to_csv(out / "cdc" / "day2" / "cdc_ops.csv", index=False)
    print(ops["op"].value_counts().to_dict())


if __name__ == "__main__":
    main()
