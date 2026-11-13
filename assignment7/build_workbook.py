"""Write the Tableau workbook (.twb) and package it with its data (.twbx).

    python build_workbook.py --out output

The workbook connects to output/data/population_country_year.csv (a text-file connection).
It has four worksheets and one dashboard:
  1. Population trend by region          (line, year x total population, coloured by region)
  2. Top 10 countries, latest year       (bar, sorted descending, Top 10 filter on rank)
  3. Population 1960 vs latest           (scatter, one point per country, log-free, coloured by region)
  4. Population by income group, latest  (bar, sorted descending)
Dashboard: all four, with a Region filter and a Year filter shared across sheets.

Written by hand as Tableau XML. It is well-formed XML checked by tests/test_workbook.py, but it has
NOT been opened in Tableau Desktop here, so see docs/connection_guide.md for the fallback steps.
"""
import argparse
import json
import zipfile
from pathlib import Path
from xml.sax.saxutils import quoteattr

import pandas as pd

def col(name, datatype, role, typ, caption=None):
    cap = f" caption={quoteattr(caption)}" if caption else ""
    return f"<column datatype='{datatype}' name='[{name}]' role='{role}' type='{typ}'{cap} />"


def calc(name, datatype, role, typ, formula, caption):
    return (f"<column datatype='{datatype}' name='[{name}]' role='{role}' type='{typ}' caption={quoteattr(caption)}>"
            f"<calculation class='tableau' formula={quoteattr(formula)} /></column>")


def ds_column(name):
    return f"[population_country_year].[{name}]"


def sheet(name, rows, cols, mark, filters, encodings, sort=None):
    filt = "".join(filters)
    sort_xml = (f"<sort column={quoteattr(sort[0])} direction='DESC' using={quoteattr(sort[1])} />"
                if sort else "")
    enc = "".join(encodings)
    return f"""<worksheet name={quoteattr(name)}>
  <table>
    <view>{filt}</view>
    <panes><pane><view /><mark class='{mark}' /><encodings>{enc}</encodings></pane></panes>
    <rows>{rows}</rows>
    <cols>{cols}</cols>
    {sort_xml}
  </table>
</worksheet>"""


def year_filter(lo, hi):
    return (f"<filter class='quantitative' column={quoteattr(ds_column('year'))} "
            f"included-values='in-range' min='{lo}' max='{hi}' />")


def build_twb(latest, first, csv_name):
    ds = "population_country_year"
    columns = [
        col("country", "string", "dimension", "nominal"),
        col("iso3", "string", "dimension", "nominal"),
        col("region", "string", "dimension", "nominal"),
        col("income_group", "string", "dimension", "nominal"),
        col("year", "integer", "dimension", "ordinal"),
        col("population", "integer", "measure", "quantitative"),
        col("pop_rank_in_year", "integer", "measure", "quantitative"),
        calc("Pop first year", "integer", "measure", "quantitative",
             f"IF [year] = {first} THEN [population] END", f"Population {first}"),
        calc("Pop latest year", "integer", "measure", "quantitative",
             f"IF [year] = {latest} THEN [population] END", f"Population {latest}"),
        calc("Population (millions)", "real", "measure", "quantitative", "[population] / 1000000",
             "Population (millions)"),
    ]
    cols_xml = "\n".join(columns)
    sum_pop = f"SUM({ds_column('population')})"
    r_region = ds_column("region")
    r_year = ds_column("year")

    s1 = sheet("Population trend by region",
               rows=f"[{ds}].[sum:population:qk]",
               cols=f"[{ds}].[yr:year:ok]",
               mark="Line",
               filters=[year_filter(first, latest)],
               encodings=[f"<color column='{r_region}' />"])
    s2 = sheet("Top 10 countries, latest year",
               rows=f"[{ds}].[none:country:nk]",
               cols=f"[{ds}].[sum:population:qk]",
               mark="Bar",
               filters=[
                   f"<filter class='quantitative' column={quoteattr(ds_column('year'))} "
                   f"included-values='in-range' min='{latest}' max='{latest}' />",
                   f"<filter class='quantitative' column={quoteattr(ds_column('pop_rank_in_year'))} "
                   f"included-values='in-range' min='1' max='10' />",
               ],
               encodings=[f"<color column='{r_region}' />"],
               sort=(f"[{ds}].[sum:population:qk]", f"[{ds}].[sum:population:qk]"))
    s3 = sheet("Population 1960 vs latest",
               rows=f"[{ds}].[sum:Pop latest year:qk]",
               cols=f"[{ds}].[sum:Pop first year:qk]",
               mark="Circle",
               filters=[],
               encodings=[f"<color column='{r_region}' />",
                          f"<detail column='{ds_column('country')}' />"])
    s4 = sheet("Population by income group, latest",
               rows=f"[{ds}].[none:income_group:nk]",
               cols=f"[{ds}].[sum:population:qk]",
               mark="Bar",
               filters=[f"<filter class='quantitative' column={quoteattr(ds_column('year'))} "
                        f"included-values='in-range' min='{latest}' max='{latest}' />"],
               encodings=[])

    dashboard = f"""<dashboard name='Population dashboard'>
  <size maxheight='800' maxwidth='1200' minheight='800' minwidth='1200' />
  <zones>
    <zone h='100000' id='1' type-v='layout-basic' w='100000' x='0' y='0'>
      <zone h='50000' id='2' name='Population trend by region' w='100000' x='0' y='0' />
      <zone h='50000' id='3' name='Top 10 countries, latest year' w='50000' x='0' y='50000' />
      <zone h='50000' id='4' name='Population 1960 vs latest' w='50000' x='50000' y='50000' />
    </zone>
  </zones>
</dashboard>"""

    twb = f"""<?xml version='1.0' encoding='utf-8' ?>
<workbook version='18.1' xmlns:user='http://www.tableausoftware.com/xml/user'>
  <datasources>
    <datasource name='{ds}' caption='World Bank population by country and year' inline='true' version='18.1'>
      <connection class='textscan' directory='Data' filename={quoteattr(csv_name)} password='' server=''>
        <relation name='{csv_name.rsplit('.', 1)[0]}' table='[{csv_name}]' type='table' />
      </connection>
      <aliases enabled='no' />
{cols_xml}
    </datasource>
  </datasources>
  <worksheets>
{s1}
{s2}
{s3}
{s4}
  </worksheets>
  <dashboards>
{dashboard}
  </dashboards>
  <windows source='worksheets'>
    <window class='worksheet' name='Population trend by region' />
  </windows>
</workbook>
"""
    return twb


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="output")
    args = parser.parse_args()
    out = Path(args.out)
    m = json.loads((out / "metrics.json").read_text(encoding="utf-8"))
    first, latest = m["first_year"], m["last_year"]

    csv_name = "population_country_year.csv"
    csv_path = out / "data" / csv_name
    assert csv_path.exists(), "run prepare_data.py first"
    pd.read_csv(csv_path)  # confirms the CSV parses before it is packaged

    twb_text = build_twb(latest, first, csv_name)
    twb_path = out / "Population_BI.twb"
    twb_path.write_text(twb_text, encoding="utf-8")

    twbx_path = out / "Population_BI.twbx"
    with zipfile.ZipFile(twbx_path, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(twb_path, "Population_BI.twb")
        z.write(csv_path, f"Data/{csv_name}")
    print("wrote", twb_path, "and", twbx_path)


if __name__ == "__main__":
    main()
