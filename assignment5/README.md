# Assignment 5: Data Governance (UCI Adult)

Data governance for the UCI Adult census dataset: metadata management, data quality assessment and improvement,
privacy and security measures, and an orchestrated pipeline with an AWS Data Pipeline definition.

## Status

| Part | Status |
|---|---|
| Metadata (data dictionary, dataset metadata, lineage with checksum) | Built and run |
| Data quality profile, fixes, before/after counts | Built and run |
| Privacy: classification, k-anonymity, generalisation, suppression, minimisation | Built and run |
| Orchestration: local ordered-steps pipeline | Built and run |
| AWS Data Pipeline definition (`aws/datapipeline_definition.json`) | Written, **not deployed** (no AWS account or credits) |
| Access roles, encryption, alerting | Designed in the report; not applied to any AWS account |
| Screenshots | Not included (no AWS console used) |

## Layout

| Path | What it is |
|---|---|
| `governance.py` | Data dictionary, quality rules, cleaning fixes, privacy protection |
| `pipeline.py` | Runs the steps in order: ingest, profile, clean, profile, protect, publish |
| `aws/datapipeline_definition.json` | AWS Data Pipeline definition of the same steps (not deployed) |
| `report.py` | Builds `output/Assignment5_Report.pdf` |
| `tests/test_governance.py` | Checks for rules, cleaning, quarantine and k-anonymity |
| `output/metadata/` | `data_dictionary.csv`, `dataset_metadata.json` |
| `output/quality/` | `quality_before_after.csv`, `quality_actions.json`, `quarantine.csv` (if any) |
| `output/privacy/` | `privacy_metrics.json` |
| `output/protected/` | `adult_protected.csv` (published file; not committed to git) |
| `output/logs/pipeline.log`, `output/run_summary.json` | Step-by-step run log and status |

## Setup

```bash
cd assignment5
pip install -r requirements.txt
```

Data: download the UCI Adult file from https://archive.ics.uci.edu/static/public/2/data.csv and save it as
`data/adult.csv` (48,842 rows with a header). The data is not stored in this repository.

## Run

```bash
python -m pytest tests                                  # checks
python pipeline.py --raw data/adult.csv --out output    # governance pipeline
python report.py --out output                           # PDF report
```

The pipeline takes about one second.

## Key results

- **Missing values:** the file uses three markers: `?` (UCI convention), the text `NaN`, and empty cells. All three are
  recognised. Rows are kept with the value `Unknown` in workclass, occupation and native-country.
- **Labels:** the test split uses `<=50K.` and `>50K.` with a trailing period. The period is removed.
- **Duplicates:** exact duplicates are removed after labels and markers are normalised.
- **Out-of-range values:** none were found, but the rules run and any failing row goes to `quarantine.csv`.
- **Privacy:** the published file has k-anonymity k ≥ 5 on the quasi-identifiers. Age is generalised to 10-year
  bands, and native country to United-States or Non-US. Groups still smaller than 5 are suppressed.
- **Minimisation:** `education` (duplicate of `education-num`) and `fnlwgt` (sampling weight) are not published.

## AWS Data Pipeline (not deployed)

`aws/datapipeline_definition.json` contains an S3 input node, a ShellCommandActivity on a t2.micro EC2 resource that
runs `pipeline.py`, an S3 output node, pipeline logs, and an SNS failure alarm. Before any deployment:

```bash
aws datapipeline validate-pipeline-definition --pipeline-definition file://aws/datapipeline_definition.json
```

Replace the `<governance-bucket>`, `<region>` and `<account-id>` placeholders first. Check that AWS Data Pipeline is
available to your account. For new work, AWS Step Functions or Amazon MWAA are alternatives.

## Notes

- Owner, retention period and the governance council are placeholders in `dataset_metadata.json`.
- The capital-gain value 99999 (244 rows) is flagged as a possible top-code, not corrected.
- The k threshold (5) and age bands are policy choices in `governance.py`.
