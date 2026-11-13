# Assignment 8: Data Processing with Amazon Services (Online Retail)

End-to-end workflow on the UCI Online Retail data: extract, CDC, cleaning in AWS Glue (PySpark), load into Amazon
Redshift, exploration SQL, Apriori association rules, and product similarity.

## Status

| Part | Built | Run locally | Run on AWS |
|---|---|---|---|
| Extract to S3 (`pipeline/extract.py`) | yes | yes, local S3 mirror (`s3_local/`) | **no** (no AWS account) |
| CDC (`pipeline/cdc.py`, `sql/redshift/03_cdc_merge.sql`) | yes | yes, MERGE in DuckDB; matches day 2 exactly | no |
| Glue ETL (`pipeline/transform.py`, `glue/glue_etl_job.py`, `glue/job_definition.json`) | yes | yes, same functions on local Spark | **no** |
| Redshift DDL, COPY, explore, mining SQL (`sql/redshift/`) | yes | yes, in DuckDB (DISTKEY/SORTKEY removed) | **no** |
| Apriori and similarity (`pipeline/apriori.py`, `pipeline/similarity.py`) | yes | yes | n/a |
| Report (`output/Assignment8_Report.pdf`) | yes | | |

The AWS parts are written to run as they are, but they have not been run on AWS. Replace the `<placeholders>`
first. DuckDB stands in for Redshift in the local run.

## Layout

| Path | What it is |
|---|---|
| `pipeline/extract.py` | xlsx to CSV, stable `line_id`, optional upload to S3 |
| `pipeline/cdc.py` | change set (I/U/D) by `line_id`; apply; day-2 simulation |
| `pipeline/transform.py` | Spark cleaning: types, rejects, duplicates, outlier flags, sampling |
| `pipeline/run_local.py` | runs everything in order, with DuckDB as the warehouse |
| `pipeline/apriori.py`, `pipeline/similarity.py` | Apriori, rules, Jaccard, cosine, dissimilarity |
| `glue/glue_etl_job.py`, `glue/job_definition.json` | Glue entry point and job definition |
| `sql/redshift/01..05_*.sql` | schema, COPY, CDC MERGE, exploration (E1-E7), pair mining |
| `tests/` | 14 tests: CDC round trip, Apriori by hand, Spark rules, saved outputs |
| `report.py` | builds the PDF from `output/` |
| `output/` | results: quality, CDC check, explore tables, rules, similarity, report |

## Setup

```bash
cd assignment8
pip install -r requirements.txt
```

Java 17 or later is needed for PySpark. The Windows machine used for this run had no `winutils`, so Spark writes
were avoided locally: the Spark job returns pandas frames, and the parquet is written with pandas.

Data: download the UCI Online Retail workbook into `data/` (git-ignored). The direct link used:
https://archive.ics.uci.edu/ml/machine-learning-databases/00352/Online%20Retail.xlsx
Save it as `data/online_retail.xlsx`.

## Run (local)

```bash
python -m pipeline.extract --xlsx data/online_retail.xlsx --out s3_local/raw/day1/online_retail.csv
python -m pipeline.cdc --day1 s3_local/raw/day1/online_retail.csv --out s3_local
python -m pipeline.run_local --min-support 0.02      # Glue step, warehouse step, Apriori, similarity
python report.py --out output
python -m pytest tests
```

`run_local` takes about one minute on a laptop. Its checks are written to `output/cdc/cdc_check.json` and
`output/mining/pairs_check.json`.

## Run on AWS (not yet done)

1. Create the bucket and folders: `raw/`, `processed/`, `cdc/`, `glue/`.
2. Upload the day-1 and day-2 CSVs with `pipeline.extract --bucket <bucket> --key raw/day2/online_retail.csv`.
3. Package and upload the Glue library: `zip glue_libs.zip pipeline/__init__.py pipeline/transform.py`, then copy
   it to `s3://<bucket>/glue/`. Upload `glue/glue_etl_job.py` to `s3://<bucket>/glue/`.
4. Create the job: `aws glue create-job --cli-input-json file://glue/job_definition.json`, then run it.
   Job bookmarks are on, so re-runs read only new files.
5. In Redshift, run `sql/redshift/01_schema.sql`, then `02_copy_from_s3.sql` (the COPY statements), then
   `03_cdc_merge.sql` after the change set is staged, then `04_explore.sql` and `05_mining_pairs.sql`.
6. Check: `raw_line` should have 541,909 rows after the merge, and the pair counts from `05_mining_pairs.sql` should
   match `output/mining/sql_pairs.csv`.

## Notes

- **Basket** = invoice. **Item** = stock code. **Line key** = `line_id`, assigned at extraction.
- Stock codes for postage, fees, adjustments and gift vouchers are treated as non-products (`NON_PRODUCT_RE`).
- Outliers are flagged, not removed. The minimum support (2%) and confidence (50%) are set in the SQL and in
  `run_local`, and must be the same in both.
- ANSI SQL mode is switched off in the transform so local Spark matches Glue 4.0.
