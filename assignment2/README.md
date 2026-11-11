# Assignment 2: Classification and Clustering of Big Data

Source code, results and report for Assignment 2 on the UCI Online Retail dataset.

It covers:
1. **Supervised classification**: logistic regression and decision tree to predict high-value customers.
2. **Unsupervised clustering**: K-means (k chosen by silhouette) and DBSCAN on customer behaviour.
3. **Streaming clustering**: incremental mini-batch k-means over monthly batches of invoices.
4. **Feature extraction and subspace clustering**: PCA subspace, plus a search over all two-feature subspaces.
5. **Collaborative filtering**: item-item cosine recommendations, compared with a popularity baseline.

## Layout

| Path | What it is |
|---|---|
| `analysis.py` | All methods: features, classification, clustering, streaming, subspace, CF |
| `run.py` | Runs everything, writes `output/metrics.json`, `output/figures/*.png`, `output/streaming_batches.csv` |
| `report.py` | Builds `output/Assignment2_Report.pdf` from the metrics and figures |
| `clean.py` | Cleaning rules (same as Assignment 1) |
| `tests/test_assignment2.py` | Checks on small synthetic data |
| `output/` | Results from the run: metrics, figures, logs, report |

## Setup

Python 3.10 or newer.

```bash
cd assignment2
pip install -r requirements.txt
```

## Data

Download the Online Retail dataset (CSV) from the UCI repository and save it as `data/online_retail.csv` in the project root:

https://archive.ics.uci.edu/dataset/352/online+retail

The data is not stored in this repository.

## Run

```bash
python -m pytest tests          # checks (or: python tests/test_assignment2.py)
python run.py --data ../data/online_retail.csv --out output
python report.py --out output
```

The full run takes about 10 seconds on a laptop.

## Method notes

- **Time split.** Features use transactions before 1 Oct 2011. The label, the high-value customer flag, uses spend after that date. This prevents leakage.
- **Label.** High value means spend after the cutoff is in the top quartile of all customers.
- **K-means.** k is chosen by silhouette score over k = 2 to 8.
- **DBSCAN.** `eps` is set at the 90th percentile of 5-nearest-neighbour distances. About 10% of points are noise by design.
- **Streaming.** This is incremental mini-batch k-means (`MiniBatchKMeans.partial_fit`), not CluStream or StreamKM++. The scaler is fixed on the first batch.
- **Subspace.** PCA keeps 90% of the variance. The two-feature search ranks every pair of features by silhouette. This is not a dedicated subspace algorithm such as CLIQUE or PROCLUS.
- **Collaborative filtering.** Item-item cosine similarity on the top 500 products, evaluated with precision@5, recall@5 and hit rate against a popularity baseline.

## Results

See `output/Assignment2_Report.pdf`, or `output/metrics.json` for the raw numbers.

## Not included

- The Kaggle datasets from the brief. Only the UCI Online Retail data was analysed.
- Presentation slides.
