"""AWS Glue entry point for the Online Retail clean-up job (Glue 4.0, PySpark).

The cleaning logic lives in pipeline/transform.py and is shipped to Glue as glue_libs.zip
(--extra-py-files). This file only reads the job arguments and calls run_pipeline().

Job arguments (see glue/job_definition.json):
    --raw_path          s3://.../raw/day2/online_retail.csv     (CSV from the extract step)
    --processed_base    s3://.../processed/online_retail/        (writes clean/, rejects/, metrics/)
    --sample_fraction   1.0 for the full data, below 1.0 for a stratified sample by country
    --seed              random seed for the sample
"""
import sys

from awsglue.context import GlueContext
from awsglue.job import Job
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext

from pipeline.transform import run_pipeline

args = getResolvedOptions(sys.argv, ["JOB_NAME", "raw_path", "processed_base", "sample_fraction", "seed"])

sc = SparkContext()
glue_context = GlueContext(sc)
spark = glue_context.spark_session
job = Job(glue_context)
job.init(args["JOB_NAME"], args)

base = args["processed_base"].rstrip("/")
metrics = run_pipeline(
    spark,
    raw_path=args["raw_path"],
    out_path=f"{base}/clean/",
    rejects_path=f"{base}/rejects/",
    metrics_path=f"{base}/metrics/",
    sample_fraction=float(args["sample_fraction"]),
    seed=int(args["seed"]),
)
print("online_retail clean job metrics:", metrics)
job.commit()
