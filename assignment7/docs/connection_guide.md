# Connection guide: from the World Bank data to Tableau

This guide covers how the data is prepared, and how to connect Tableau to it. Two routes are given.

- **Route A (used for the submitted workbook):** a text-file connection to the CSV, packaged in the `.twbx`.
- **Route B (Redshift, the preferred route in the brief):** load the same CSV into Amazon Redshift and connect
  Tableau to the cluster. This was **not run**, because no cluster was available. The steps are written from the
  Tableau and Redshift documentation.

## 1. Get the source data

Both files come from the World Bank API, which needs no login.

```bash
curl -o data/wb_pop_raw.json "https://api.worldbank.org/v2/country/all/indicator/SP.POP.TOTL?format=json&per_page=20000&date=1960:2023"
curl -o data/wb_countries_raw.json "https://api.worldbank.org/v2/country?format=json&per_page=400"
```

- Indicator `SP.POP.TOTL`: total population, 1960 to 2023.
- Country metadata: region and income group for each country. This is where aggregates (World, Euro area and so on)
  are identified and removed.

## 2. Build the tidy CSV

```bash
python prepare_data.py --data data --out output
```

Output: `output/data/population_country_year.csv`, 13,858 rows (217 countries, 1960 to 2023), columns:

| Column | Meaning |
|---|---|
| `country`, `iso3` | Country name and ISO 3166 code |
| `region`, `income_group` | World Bank classification |
| `year` | Calendar year |
| `population` | Total population |
| `pop_rank_in_year` | Rank of the country in that year (1 = largest). Used for the Top 10 filter. |

## 3. Route A: connect Tableau to the CSV

1. Open Tableau Desktop. Under **Connect**, choose **Text file**.
2. Browse to `output/data/population_country_year.csv` (or open `output/Population_BI.twbx`, which already has the file inside).
3. On the **Data Source** tab, check the data types:
   - `year`: Number (whole) → change to **Date > Year** if you want date behaviour, or keep as a number for the
     line chart axis.
   - `population`, `pop_rank_in_year`: Number (whole).
   - `country`, `iso3`, `region`, `income_group`: String.
4. Go to a new worksheet. The fields appear in the Data pane.
5. Create the calculated fields used in the workbook:
   - `Pop first year`: `IF [year] = 1960 THEN [population] END`
   - `Pop latest year`: `IF [year] = 2023 THEN [population] END`
   - `Population (millions)`: `[population] / 1000000`

## 4. Route B: Amazon Redshift (not run here)

### 4a. Load the CSV into Redshift

```sql
CREATE TABLE population_country_year (
    country        VARCHAR(128),
    iso3           CHAR(3)       NOT NULL,
    region         VARCHAR(128),
    income_group   VARCHAR(64),
    year           INTEGER       NOT NULL,
    population     BIGINT        NOT NULL,
    pop_rank_in_year INTEGER     NOT NULL,
    PRIMARY KEY (iso3, year)
)
DISTSTYLE ALL      -- small table (~14k rows): copy to every node
SORTKEY (year);

-- Upload the CSV to S3 first, then (IAM role name and bucket are placeholders):
COPY population_country_year
FROM 's3://<your-bucket>/population_country_year.csv'
IAM_ROLE 'arn:aws:iam::<account-id>:role/<redshift-copy-role>'
FORMAT AS CSV IGNOREHEADER 1;
```

Check the load:

```sql
SELECT COUNT(*) FROM population_country_year;               -- expect 13858
SELECT year, SUM(population) FROM population_country_year
 WHERE year IN (1960, 2023) GROUP BY year ORDER BY year;     -- expect 3,010,810,885 and 8,039,550,134
```

### 4b. Connect Tableau

1. **Connect > To a Server > Amazon Redshift**.
2. Server: the cluster endpoint, for example `<cluster>.<id>.<region>.redshift.amazonaws.com`.
3. Port: `5439`. Database: your database name.
4. Authentication: username and password of a database user with read access. Tick **Require SSL**.
5. Choose the schema, then drag `population_country_year` onto the canvas.

Use a read-only user for Tableau. Do not put credentials in the workbook: choose **Prompt user** or let
Tableau save them only to the local machine.

## 5. Worksheets and filters in the workbook

| Worksheet | Chart | Operations used |
|---|---|---|
| Population trend by region | Line: `year` on columns, `SUM(population)` on rows, colour by `region` | Year range filter (1960 to 2023); calculated sum |
| Top 10 countries, latest year | Horizontal bar, sorted by population descending | Filter `year` = 2023 **and** `pop_rank_in_year` between 1 and 10 |
| Population 1960 vs latest | Scatter: 1960 on x, 2023 on y, one point per country, colour by `region` | Calculated fields `Pop first year`, `Pop latest year`; detail on `country` |
| Population by income group, latest | Bar sorted descending | Filter `year` = 2023 |

Dashboard "Population dashboard": all four sheets, with `region` and `year` filters applied across them.

## 6. If the workbook does not open cleanly

The `.twb` was written by hand as Tableau XML and has not been opened in Tableau Desktop. If Tableau reports an
error:

1. Open `Population_BI.twbx` and check the **Data Source** tab. Re-point the connection to the CSV if the path is wrong.
2. Build the four worksheets from the table in section 5. The calculated fields are in section 3.
3. Save as a new `.twbx` once it works, and replace the file in `output/`.

Screenshots of the connection steps and the four charts are to be added after the workbook is opened in Tableau.
