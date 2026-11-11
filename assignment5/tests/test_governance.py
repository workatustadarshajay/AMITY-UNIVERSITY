"""Checks for the governance rules.   python -m pytest tests   (from assignment5/)"""
import sys
import tempfile
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import governance as G  # noqa: E402

HEADER = ("age,workclass,fnlwgt,education,education-num,marital-status,occupation,relationship,race,sex,"
          "capital-gain,capital-loss,hours-per-week,native-country,income")


def _csv(rows):
    d = tempfile.mkdtemp()
    p = Path(d) / "adult.csv"
    p.write_text("\n".join([HEADER] + rows) + "\n", encoding="utf-8")
    return p


def _row(age=39, workclass="?", occupation="?", country="United-States", income="<=50K", sex="Male", hours=40):
    return (f"{age},{workclass},77516,Bachelors,13,Never-married,{occupation},Not-in-family,White,{sex},"
            f"0,0,{hours},{country},{income}")


def test_load_treats_question_mark_and_empty_as_missing():
    raw = G.load(_csv([_row(workclass="?"), _row(workclass="State-gov", occupation="")]))
    assert raw["workclass"].isna().sum() == 1
    assert raw["occupation"].isna().sum() == 2


def test_quality_rules_count_known_issues():
    raw = G.load(_csv([_row(income="<=50K."), _row(income="<=50K."), _row(income=">50K")]))
    before = G.quality_rules(raw)
    assert before["missing_workclass"] == 3
    assert before["income_trailing_period"] == 2
    assert before["exact_duplicate_rows"] == 1  # the two identical '<=50K.' rows


def test_clean_fixes_labels_missing_and_duplicates():
    raw = G.load(_csv([_row(income="<=50K."), _row(income="<=50K"), _row(income=">50K.")]))
    clean, actions, quarantine = G.clean(raw)
    after = G.quality_rules(clean)
    assert after["income_trailing_period"] == 0
    assert after["missing_workclass"] == 0
    assert after["exact_duplicate_rows"] == 0  # the two '<=50K' rows become duplicates once labels match
    assert set(clean["income"]) == {"<=50K", ">50K"}
    assert len(clean) == 2
    assert clean.loc[0, "workclass"] == "Unknown"
    assert len(quarantine) == 0


def test_out_of_range_rows_are_quarantined_not_changed():
    raw = G.load(_csv([_row(age=150), _row(age=30)]))
    clean, _, quarantine = G.clean(raw)
    assert len(quarantine) == 1 and quarantine.iloc[0]["age"] == 150
    assert len(clean) == 1 and clean.iloc[0]["age"] == 30


def test_protect_guarantees_k_anonymity_on_published_columns():
    rows = [_row(age=20 + (i % 3), country="Mexico", occupation="Sales", hours=20 + i) for i in range(4)]  # tiny group
    # ten distinct people in one group (hours differ, so they are not exact duplicates)
    rows += [_row(age=40, country="United-States", occupation="Exec-managerial", hours=30 + i) for i in range(10)]
    raw = G.load(_csv(rows))
    clean, _, _ = G.clean(raw)
    protected, metrics = G.protect(clean)
    assert metrics["after_suppression"]["k_min"] >= G.K_THRESHOLD
    assert metrics["rows_suppressed"] >= 4
    assert set(protected["native_region"]) <= {"United-States", "Non-US"}
    assert "age" not in protected.columns and "native-country" not in protected.columns
    assert "education" not in protected.columns and "fnlwgt" not in protected.columns


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
