"""Checks for the Tableau workbook and its data.

    python -m pytest tests

Checks the .twb is well-formed XML, every field a worksheet uses is defined, the packaged CSV matches
the workbook's columns, and the Top 10 filter selects exactly 10 countries in the latest year.
"""
import json
import re
import zipfile
import xml.dom.minidom
from pathlib import Path

import pandas as pd
import pytest

OUT = Path(__file__).resolve().parents[1] / "output"
TWB = OUT / "Population_BI.twb"
TWBX = OUT / "Population_BI.twbx"
CSV = OUT / "data" / "population_country_year.csv"


@pytest.fixture(scope="module")
def xml_text():
    return TWB.read_text(encoding="utf-8")


def test_twb_is_well_formed_and_has_four_worksheets_and_a_dashboard(xml_text):
    xml.dom.minidom.parseString(xml_text.encode("utf-8"))
    assert xml_text.count("<worksheet ") == 4
    assert xml_text.count("<dashboard ") == 1


def test_twbx_packages_workbook_and_csv():
    with zipfile.ZipFile(TWBX) as z:
        assert set(z.namelist()) == {"Population_BI.twb", "Data/population_country_year.csv"}


def test_every_field_used_is_defined(xml_text):
    defined = set(re.findall(r"<column [^>]*name='\[([^\]]+)\]'", xml_text))
    used = set(re.findall(r"\[population_country_year\]\.\[(?:none|sum|yr|usr):([^:\]]+)", xml_text))
    used |= set(re.findall(r"\[population_country_year\]\.\[([a-z_]+)\]", xml_text))
    missing = {u for u in used if u not in defined and u not in {"sum:population:qk"}}
    # Underlying names: the CSV columns plus the calculated fields.
    for name in ["country", "iso3", "region", "income_group", "year", "population", "pop_rank_in_year"]:
        assert name in defined
    assert not [m for m in missing if m.lower() not in {d.lower() for d in defined}], missing


def test_csv_matches_workbook_columns_and_top10_rule():
    df = pd.read_csv(CSV)
    assert list(df.columns) == ["country", "iso3", "region", "income_group", "year", "population", "pop_rank_in_year"]
    latest = int(df["year"].max())
    top10 = df[(df["year"] == latest) & (df["pop_rank_in_year"] <= 10)]
    assert len(top10) == 10
    assert top10.sort_values("population", ascending=False)["country"].iloc[0] == "India"
    metrics = json.loads((OUT / "metrics.json").read_text(encoding="utf-8"))
    assert metrics["top10_last_year"][0]["country"] == "India"


def test_no_aggregates_in_data():
    df = pd.read_csv(CSV)
    assert not df["region"].str.contains("Aggregates").any()
    assert not df["country"].isin(["World", "Euro area"]).any()
