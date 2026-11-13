"""Turn the World Bank API downloads into one tidy CSV for Tableau, and compute the report figures.

    python prepare_data.py --data data --out output

Input (download with the commands in README.md):
    data/wb_pop_raw.json        SP.POP.TOTL, all countries and aggregates, 1960-2023
    data/wb_countries_raw.json  country metadata (region, income group)
Output:
    output/data/population_country_year.csv   one row per country and year (aggregates removed)
    output/metrics.json                       figures quoted in the report
"""
import argparse
import json
from pathlib import Path

import pandas as pd


def load(data_dir):
    pop = json.loads((data_dir / "wb_pop_raw.json").read_text(encoding="utf-8"))[1]
    meta = json.loads((data_dir / "wb_countries_raw.json").read_text(encoding="utf-8"))[1]
    pop = pd.DataFrame([{
        "iso3": r["countryiso3code"], "year": int(r["date"]), "population": r["value"],
    } for r in pop])
    meta = pd.DataFrame([{
        "iso3": m["id"], "country": m["name"].strip(), "region": m["region"]["value"].strip(),
        "income_group": m["incomeLevel"]["value"].strip(),
    } for m in meta])
    return pop, meta


def tidy(pop, meta):
    # Aggregates such as "World" or "Euro area" have region "Aggregates" in the metadata.
    countries = meta[(meta["region"] != "Aggregates") & (meta["iso3"].str.len() == 3)]
    df = pop.merge(countries, on="iso3", how="inner")
    df = df.dropna(subset=["population"])
    df["population"] = df["population"].astype("int64")
    # Rank of each country within its year (1 = largest), used for the Top 10 filter in Tableau.
    df["pop_rank_in_year"] = df.groupby("year")["population"].rank(ascending=False, method="min").astype(int)
    return df[["country", "iso3", "region", "income_group", "year", "population", "pop_rank_in_year"]].sort_values(
        ["country", "year"]).reset_index(drop=True)


def metrics(df):
    total = df.groupby("year")["population"].sum()
    y0, y1 = int(total.index.min()), int(total.index.max())
    last = df[df["year"] == y1]
    top10 = last.nlargest(10, "population")[["country", "population"]]
    region_y1 = last.groupby("region")["population"].sum().sort_values(ascending=False)
    region_y0 = df[df["year"] == y0].groupby("region")["population"].sum()
    growth = (region_y1 / region_y0 - 1).round(3).sort_values(ascending=False)
    income = last.groupby("income_group")["population"].sum().sort_values(ascending=False)
    # Scatter: each country's 1960 and 2023 population, to show who grew fastest.
    pair = df[df["year"].isin([y0, y1])].pivot_table(index=["country", "region"], columns="year",
                                                       values="population").dropna().reset_index()
    pair["multiple"] = (pair[y1] / pair[y0]).round(2)
    return {
        "first_year": y0, "last_year": y1,
        "world_population_first": int(total[y0]), "world_population_last": int(total[y1]),
        "world_growth_pct": round((total[y1] / total[y0] - 1) * 100, 1),
        "countries": int(last["country"].nunique()),
        "top10_last_year": [{"country": r.country, "population": int(r.population)} for r in top10.itertuples()],
        "region_population_last": {k: int(v) for k, v in region_y1.items()},
        "region_growth_pct": {k: round(v * 100, 1) for k, v in growth.items()},
        "income_population_last": {k: int(v) for k, v in income.items()},
        "fastest_growth_multiple_top5": pair.nlargest(5, "multiple")[["country", "multiple"]]
            .to_dict("records"),
        "countries_with_population_below_1m_last": int((last["population"] < 1_000_000).sum()),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default="data")
    parser.add_argument("--out", default="output")
    args = parser.parse_args()
    data_dir, out = Path(args.data), Path(args.out)
    (out / "data").mkdir(parents=True, exist_ok=True)

    pop, meta = load(data_dir)
    df = tidy(pop, meta)
    df.to_csv(out / "data" / "population_country_year.csv", index=False)
    m = metrics(df)
    (out / "metrics.json").write_text(json.dumps(m, indent=2), encoding="utf-8")
    print(f"rows={len(df)} countries={df['country'].nunique()} years={df['year'].min()}-{df['year'].max()}")


if __name__ == "__main__":
    main()
