"""Build the Assignment 7 PDF report and chart previews.

    python report.py --out output

The previews are matplotlib drawings of the four worksheets, so the report can show the charts before the
workbook is opened in Tableau. They are not Tableau screenshots.
"""
import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
from reportlab.lib import colors  # noqa: E402
from reportlab.lib.pagesizes import A4  # noqa: E402
from reportlab.lib.styles import getSampleStyleSheet  # noqa: E402
from reportlab.lib.units import cm  # noqa: E402
from reportlab.platypus import Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle  # noqa: E402

styles = getSampleStyleSheet()
H1, H2, BODY = styles["Heading1"], styles["Heading2"], styles["BodyText"]
SMALL = BODY.clone("small", fontSize=8, leading=10)


def esc(t):
    return str(t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def table(rows, widths):
    cells = [[Paragraph(esc(c), SMALL) for c in r] for r in rows]
    t = Table(cells, colWidths=widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#DDE4EE")),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.grey), ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    return t


def preview_charts(df, m, figs):
    first, last = m["first_year"], m["last_year"]
    fig, axes = plt.subplots(2, 2, figsize=(13, 9))
    # 1. Line: total population by region over time.
    ax = axes[0, 0]
    by = df.groupby(["year", "region"])["population"].sum().unstack()
    for region in by.columns:
        ax.plot(by.index, by[region] / 1e9, label=region.replace(" & ", " & "), lw=1.6)
    ax.set_title("1. Population trend by region (billions)")
    ax.set_xlabel("Year"); ax.set_ylabel("Population (bn)")
    ax.legend(fontsize=6.5, loc="upper left")
    # 2. Bar: top 10 countries, latest year, sorted descending.
    ax = axes[0, 1]
    top = df[(df["year"] == last) & (df["pop_rank_in_year"] <= 10)].sort_values("population")
    ax.barh(top["country"], top["population"] / 1e6, color="#3B6E9F")
    ax.set_title(f"2. Top 10 countries, {last} (millions)")
    ax.set_xlabel("Population (m)")
    # 3. Scatter: 1960 vs latest per country, coloured by region.
    ax = axes[1, 0]
    pair = df[df["year"].isin([first, last])].pivot_table(index=["country", "region"], columns="year",
                                                            values="population").dropna().reset_index()
    for region, g in pair.groupby("region"):
        ax.scatter(g[first] / 1e6, g[last] / 1e6, s=14, label=region, alpha=0.8)
    lim = max(pair[first].max(), pair[last].max()) / 1e6 * 1.05
    ax.plot([0, lim], [0, lim], color="grey", lw=0.8, ls="--")
    ax.set_xscale("log"); ax.set_yscale("log")
    ax.set_title(f"3. Population {first} vs {last}, per country (log scale, millions)")
    ax.set_xlabel(f"{first} (m)"); ax.set_ylabel(f"{last} (m)")
    # 4. Bar: population by income group, latest year.
    ax = axes[1, 1]
    inc = pd.Series(m["income_population_last"]).sort_values()
    ax.barh(inc.index, inc.values / 1e9, color="#6B8E4E")
    ax.set_title(f"4. Population by income group, {last} (billions)")
    ax.set_xlabel("Population (bn)")
    fig.tight_layout()
    path = figs / "preview_worksheets.png"
    fig.savefig(path, dpi=130); plt.close(fig)
    return path


def build(out):
    out = Path(out)
    figs = out / "figures"; figs.mkdir(parents=True, exist_ok=True)
    m = json.loads((out / "metrics.json").read_text(encoding="utf-8"))
    df = pd.read_csv(out / "data" / "population_country_year.csv")
    preview = preview_charts(df, m, figs)
    first, last = m["first_year"], m["last_year"]
    rg = m["region_growth_pct"]
    top = m["top10_last_year"]

    story = [Paragraph("Assignment 7: Business Intelligence and Data Visualisation with Tableau", H1),
             Paragraph("Dataset: World Bank population by country and year (SP.POP.TOTL, "
                       f"{first} to {last}). Workbook: Population_BI.twbx.", BODY), Spacer(1, 6)]

    story.append(Paragraph("1. Benefits of Business Intelligence", H2))
    for line in [
        "<b>Faster, better decisions.</b> A 2024 study of BI adoption reports better decision speed, accuracy and "
        "competitiveness (SAGE Open, doi:10.1177/02663821241289809).",
        "<b>One version of the truth.</b> Dashboards read from one governed source, so departments stop arguing "
        "over conflicting spreadsheets (BARC, benefits of BI).",
        "<b>Operational efficiency.</b> Reports that took days can be refreshed on demand, and staff spend less time "
        "assembling data (BARC; Park University).",
        "<b>Better customer and market insight.</b> Segmentation and trend views show where demand is growing "
        "(Databricks, 'How Business Intelligence Drives Smart Decision-Making', 2025).",
        "<b>Data quality and accountability.</b> Shared definitions and visible metrics make errors easier to "
        "spot and owners easier to name (BARC).",
    ]:
        story.append(Paragraph("&bull; " + line, BODY))
    story.append(Paragraph("Sources were found by web search. The summaries are from search results and "
                           "were not checked against each full article.", SMALL))

    story.append(Paragraph("2. Setup and data connection", H2))
    story.append(Paragraph(
        "Tableau Desktop is not installed on the build machine, and no Redshift cluster is available. The data "
        "was therefore connected as a text file (Route A), packaged in the .twbx with the CSV. The Redshift route "
        "(Route B: COPY from S3, then a Tableau Redshift connection on port 5439 with SSL) is written out in "
        "<i>docs/connection_guide.md</i> but was not run. The CSV has 13,858 rows: 217 countries and territories, "
        "1960 to 2023. The 79 World Bank aggregates (World, regions, income groups) are removed using the country "
        "metadata.", BODY))

    story.append(Paragraph("3. Worksheets, operators, functions, sorting and filtering", H2))
    rows = [["Worksheet", "Chart", "Operations"],
            ["Population trend by region", "Line", "Year range filter; SUM(population); colour by region"],
            ["Top 10 countries, latest year", "Bar, sorted", "Filter year = 2023 and pop_rank_in_year 1 to 10; "
                                                              "sort by population, descending"],
            ["Population 1960 vs latest", "Scatter", "Calculated fields IF year = 1960 / 2023 THEN population END; "
                                                    "detail on country"],
            ["Population by income group, latest", "Bar, sorted", "Filter year = 2023; sort descending"],
            ["Population dashboard", "4 sheets", "Shared region and year filters"]]
    story.append(table(rows, [5 * cm, 3 * cm, 9 * cm]))
    story.append(Paragraph("Rank within each year is computed in the data preparation step, so the Top 10 filter does "
                           "not depend on a table calculation.", SMALL))

    story.append(PageBreak())
    story.append(Paragraph("4. Charts and insights", H2))
    story.append(Image(str(preview), width=17 * cm, height=17 * cm * 9 / 13))
    story.append(Paragraph("Preview drawn with matplotlib from the same data; not a Tableau screenshot.", SMALL))
    story.append(Spacer(1, 6))
    insights = [
        f"World population rose from {m['world_population_first'] / 1e9:.2f} billion in {first} to "
        f"{m['world_population_last'] / 1e9:.2f} billion in {last}, an increase of {m['world_growth_pct']:.0f}%.",
        f"Growth was uneven. Sub-Saharan Africa grew {rg['Sub-Saharan Africa']:.0f}% and the Middle East and North "
        f"Africa group {rg['Middle East, North Africa, Afghanistan & Pakistan']:.0f}%, while Europe and Central Asia "
        f"grew {rg['Europe & Central Asia']:.0f}%. The line chart shows the regions on separate paths over the whole period.",
        f"In {last}, {top[0]['country']} ({top[0]['population'] / 1e9:.2f} bn) and {top[1]['country']} "
        f"({top[1]['population'] / 1e9:.2f} bn) were the two largest countries. The next are the United States "
        f"({top[2]['population'] / 1e6:.0f} m) and Indonesia ({top[3]['population'] / 1e6:.0f} m).",
        f"Upper middle income countries held {m['income_population_last']['Upper middle income'] / 1e9:.2f} bn people, "
        f"more than the high income group at {m['income_population_last']['High income'] / 1e9:.2f} bn.",
        "The scatter plot points above the dashed line grew. The steepest multiples are in small states such as the "
        "United Arab Emirates and Qatar, where a small 1960 base inflates the ratio. Read these with the absolute "
        "values, not the ratio alone.",
    ]
    for i in insights:
        story.append(Paragraph("&bull; " + esc(i), BODY))

    story.append(Paragraph("5. Limitations", H2))
    for line in [
        "The workbook was written by hand as Tableau XML and has not been opened in Tableau Desktop. Section 6 of "
        "docs/connection_guide.md gives the rebuild steps if it fails.",
        "The Redshift route was not run. The CSV route is the one that was tested.",
        "Screenshots of the connection steps and the Tableau charts are still to be added after the workbook opens.",
        "The presentation is this report. No separate slide deck was made.",
    ]:
        story.append(Paragraph("&bull; " + esc(line), BODY))

    story.append(Paragraph("6. References", H2))
    for ref in [
        "World Bank Open Data, Population, total (SP.POP.TOTL). https://data.worldbank.org/indicator/SP.POP.TOTL",
        "World Bank Countries and Regions API. https://api.worldbank.org/v2/country",
        "BARC. The Benefits of Business Intelligence. https://barc.com/benefits-business-intelligence/",
        "SAGE Open (2024). The impact of business intelligence on promoting decision-making. doi:10.1177/02663821241289809",
        "Databricks (2025). How Business Intelligence Drives Smart Decision-Making. https://www.databricks.com/blog/how-business-intelligence-drives-smart-decision-making",
        "Harvard Business School Online. The Advantages of Data-Driven Decision-Making. https://online.hbs.edu/blog/post/data-driven-decision-making",
        "Tableau Help: connecting to text files and to Amazon Redshift (Tableau documentation).",
    ]:
        story.append(Paragraph("&bull; " + esc(ref), SMALL))

    pdf = out / "Assignment7_Report.pdf"
    SimpleDocTemplate(str(pdf), pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm, topMargin=1.8 * cm,
                      bottomMargin=1.8 * cm, title="Assignment 7: BI and Data Visualisation").build(story)
    return pdf


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="output")
    print("wrote", build(parser.parse_args().out))


if __name__ == "__main__":
    main()
