"""Extract: read the UCI Online Retail workbook, assign a stable line_id, and land it as CSV.

    python -m pipeline.extract --xlsx data/online_retail.xlsx --out s3_local/raw/day1/online_retail.csv
    python -m pipeline.extract ... --bucket <bucket> --key raw/day1/online_retail.csv   # also uploads to S3

line_id is assigned here, once, from the source row order. (InvoiceNo, StockCode) is not unique in the source
(about 5,200 keys repeat), so this id is the business key that CDC matches on. Later updates keep it.
"""
import argparse
from pathlib import Path

import pandas as pd

RAW_COLUMNS = ["InvoiceNo", "StockCode", "Description", "Quantity", "InvoiceDate", "UnitPrice", "CustomerID", "Country"]


def add_line_id(df):
    occ = df.groupby(["InvoiceNo", "StockCode"]).cumcount() + 1
    out = df.copy()
    out["line_id"] = out["InvoiceNo"].astype(str) + "-" + out["StockCode"].astype(str) + "-" + occ.astype(str)
    return out


def xlsx_to_raw_csv(xlsx, out_csv):
    df = pd.read_excel(xlsx, dtype={"InvoiceNo": str, "StockCode": str, "CustomerID": str})
    df = add_line_id(df[RAW_COLUMNS])
    out_csv = Path(out_csv)
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_csv, index=False)
    return df


def upload(local_path, bucket, key):
    import boto3  # imported here so local runs do not need AWS packages

    boto3.client("s3").upload_file(str(local_path), bucket, key)
    return f"s3://{bucket}/{key}"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--xlsx", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--bucket")
    p.add_argument("--key")
    a = p.parse_args()
    df = xlsx_to_raw_csv(a.xlsx, a.out)
    print(f"landed {len(df)} rows -> {a.out}")
    if a.bucket:
        print("uploaded", upload(a.out, a.bucket, a.key))


if __name__ == "__main__":
    main()
