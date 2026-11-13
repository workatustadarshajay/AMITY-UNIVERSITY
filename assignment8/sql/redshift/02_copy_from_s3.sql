-- Load the Glue outputs (Parquet) from S3. Replace the bucket and role placeholders before running.
-- Parquet columns are matched by name, which is why the Glue job writes snake_case names.

TRUNCATE clean_line;
COPY clean_line
FROM 's3://<governance-bucket>/processed/online_retail/clean/'
IAM_ROLE 'arn:aws:iam::<account-id>:role/<redshift-copy-role>'
FORMAT AS PARQUET;

-- Change set produced by the CDC step (one row per changed line), then merged in 03_cdc_merge.sql
TRUNCATE stg_cdc;
COPY stg_cdc
FROM 's3://<governance-bucket>/cdc/day2/cdc_ops/'
IAM_ROLE 'arn:aws:iam::<account-id>:role/<redshift-copy-role>'
FORMAT AS PARQUET;
