# Assignment 7: Business Intelligence and Data Visualisation (Tableau)

Tableau workbook on the World Bank population dataset (1960 to 2023, 217 countries and territories): four worksheets
and one dashboard, a report on BI benefits and findings, and a connection guide.

## Status

| Part | Status |
|---|---|
| BI benefits summary (`output/Assignment7_Report.pdf`, section 1) | Written from web search results |
| Data preparation and metrics (`prepare_data.py`, `output/metrics.json`) | Built and run |
| Tableau workbook (`output/Population_BI.twbx`, `Population_BI.twb`) | Written by hand as Tableau XML; **not opened in Tableau Desktop** |
| Connection guide (`docs/connection_guide.md`) | Route A (CSV) written and matched to the workbook; Route B (Redshift) written, **not run** |
| Screenshots of Tableau | **Not included.** Tableau is not installed on the build machine. |
| Presentation | Not made separately. The PDF report covers the same ground. |

## Layout

| Path | What it is |
|---|---|
| `prepare_data.py` | Turns the World Bank downloads into one tidy CSV and computes the report figures |
| `build_workbook.py` | Writes `Population_BI.twb` and packages it with the CSV as `Population_BI.twbx` |
| `report.py` | Builds `output/Assignment7_Report.pdf` and the chart previews |
| `docs/connection_guide.md` | Step-by-step connection (CSV and Redshift), worksheet table, rebuild steps |
| `tests/test_workbook.py` | Checks the XML, the packaged files, field references and the Top 10 rule |
| `output/data/population_country_year.csv` | The tidy dataset (committed; small) |

## Run

```bash
cd assignment7
pip install pandas matplotlib reportlab pytest
# download the two World Bank files into data/ (commands in docs/connection_guide.md, section 1)
python prepare_data.py --data data --out output
python build_workbook.py --out output
python report.py --out output
python -m pytest tests
```

Data source: World Bank Open Data (SP.POP.TOTL and the country metadata API). No login needed.
