# Assignment 6: Enterprise Data Architecture and Modelling

Architecture and conceptual, logical and physical data models for a marketplace (Olist, Brazilian e-commerce)
and an online retailer (UCI Online Retail), with a short design report.

## Status

| Part | Status |
|---|---|
| Enterprise architecture diagram (Figure 1) | Built |
| Conceptual model (Figure 2 and `models/conceptual.md`) | Built |
| Logical model (`models/logical_model.csv`, silver, 3NF) | Built |
| Physical model (`models/physical.sql`, gold star schema; Figure 3) | Built, tested in SQLite (not run on Redshift) |
| Design documentation and references (`output/Assignment6_Report.pdf`) | Built |
| Datasets loaded and profiled | **Not done.** The CSV files are not in this repo. Counts in the report come from the dataset descriptions. |

## Layout

| Path | What it is |
|---|---|
| `design/diagrams.py` | Draws Figures 1-3 into `output/figures/` |
| `models/conceptual.md` | Business entities, mapping across both datasets, relationships and cardinalities |
| `models/logical_model.csv` | Entities, attributes, keys, types, source, description |
| `models/physical.sql` | Gold star schema DDL (portable SQL; Redshift tuning notes in comments) |
| `tests/test_models.py` | Loads the DDL into SQLite, checks constraints, a star query, and the logical CSV |
| `report.py` | Builds `output/Assignment6_Report.pdf` |

## Run

```bash
cd assignment6
pip install -r requirements.txt
python -m pytest tests                 # model checks
python design/diagrams.py --out output # figures
python report.py --out output          # PDF report
```

## Datasets

- Olist Brazilian E-Commerce Public Dataset (Kaggle): https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce
- UCI Online Retail: https://archive.ics.uci.edu/dataset/352/online+retail

Download the files into `data/` (git-ignored). The models do not depend on the data files yet.
