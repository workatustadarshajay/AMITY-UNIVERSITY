"""Cleaning rules for the Online Retail dataset (pandas).

The same rules are implemented in Spark in glue/etl_job.py so the cloud and
local paths produce the same output.
"""
import pandas as pd

PRODUCT_CODE = r"^\d{5}[A-Za-z]{0,2}$"  # real products; drops POST, D, M, BANK CHARGES, gift_..., etc.


def clean(df: pd.DataFrame, log=print) -> pd.DataFrame:
    """Return cleaned transactions. Logs how many rows each rule removed."""
    steps = [
        ("missing CustomerID/Description", lambda d: d.dropna(subset=["CustomerID", "Description"])),
        ("cancellations (InvoiceNo starts with C)", lambda d: d[~d["InvoiceNo"].astype(str).str.startswith("C")]),
        ("non-product StockCode", lambda d: d[d["StockCode"].astype(str).str.match(PRODUCT_CODE)]),
        ("Quantity <= 0 or UnitPrice <= 0", lambda d: d[(d["Quantity"] > 0) & (d["UnitPrice"] > 0)]),
        ("exact duplicate rows", lambda d: d.drop_duplicates()),
    ]
    for name, step in steps:
        before = len(df)
        df = step(df)
        log(f"  removed {before - len(df):>7,} rows: {name}")
    df = df.assign(
        CustomerID=df["CustomerID"].astype(float).astype(int).astype(str),
        Description=df["Description"].str.strip(),
        LineTotal=df["Quantity"] * df["UnitPrice"],
    )
    log(f"  kept {len(df):,} rows")
    return df.reset_index(drop=True)
