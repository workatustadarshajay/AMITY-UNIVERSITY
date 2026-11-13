"""Checks on the saved outputs of a full run (run python -m pipeline.run_local first).

These are the claims the report makes: the CDC merge reproduces the day-2 snapshot, the SQL and Python
pair counts agree, and the exploration tables exist. Skipped if the run has not been done.
"""
import json
from pathlib import Path

import pytest

OUT = Path(__file__).resolve().parents[1] / "output"
needs_run = pytest.mark.skipif(not (OUT / "run_summary.json").exists(), reason="run pipeline.run_local first")


@needs_run
def test_cdc_merge_reproduces_day2():
    c = json.loads((OUT / "cdc" / "cdc_check.json").read_text(encoding="utf-8"))
    assert c["rows_match"] and c["values_match"]
    assert c["raw_line_rows_after_merge"] == c["day2_rows"] == 541909


@needs_run
def test_sql_pairs_equal_python_pairs():
    p = json.loads((OUT / "mining" / "pairs_check.json").read_text(encoding="utf-8"))
    assert p["identical"] and p["python_pairs"] == p["sql_pairs"] > 0


@needs_run
def test_exploration_tables_exist():
    for e in ["E1", "E2", "E3", "E4", "E5", "E6", "E7"]:
        assert (OUT / "explore" / f"{e}.csv").exists(), e


@needs_run
def test_quality_counts_add_up():
    m = json.loads((OUT / "quality" / "quality_metrics.json").read_text(encoding="utf-8"))
    rejected = sum(m["rejects_by_reason"].values())
    assert m["raw_rows"] == rejected + m["kept_before_dedupe"]
    assert m["kept_before_dedupe"] - m["exact_duplicates_removed"] == m["clean_rows"]
