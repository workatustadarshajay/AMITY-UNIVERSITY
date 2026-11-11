"""Data governance for the UCI Adult dataset: metadata, quality rules and fixes, privacy protection.

The same functions are called by pipeline.py, which runs them as ordered steps (see aws/ for the
AWS Data Pipeline definition of the same steps).
"""
import pandas as pd

# ---------- 1. Metadata ----------

DATA_DICTIONARY = [
    {"column": "age", "type": "integer", "description": "Age in years", "role": "feature",
     "sensitivity": "quasi-identifier", "allowed": "17-90", "nullable": False,
     "protected_output": "generalised to 10-year bands (age_band)"},
    {"column": "workclass", "type": "categorical", "description": "Type of employer",
     "role": "feature", "sensitivity": "quasi-identifier", "allowed": "employer categories",
     "nullable": True, "protected_output": "kept; missing values set to Unknown"},
    {"column": "fnlwgt", "type": "integer", "description": "Census sampling weight (describes the sample, not a person)",
     "role": "dropped (data minimisation)", "sensitivity": "non-sensitive", "allowed": "positive integer",
     "nullable": False, "protected_output": "removed: not needed for the governance use case"},
    {"column": "education", "type": "categorical", "description": "Highest education level",
     "role": "dropped (duplicate of education-num)", "sensitivity": "quasi-identifier",
     "allowed": "education levels", "nullable": False, "protected_output": "removed: redundant with education-num"},
    {"column": "education-num", "type": "integer", "description": "Years of education, ordinal 1-16",
     "role": "feature", "sensitivity": "quasi-identifier", "allowed": "1-16", "nullable": False,
     "protected_output": "kept"},
    {"column": "marital-status", "type": "categorical", "description": "Marital status",
     "role": "feature", "sensitivity": "quasi-identifier", "allowed": "marital categories", "nullable": False,
     "protected_output": "kept"},
    {"column": "occupation", "type": "categorical", "description": "Occupation",
     "role": "feature", "sensitivity": "quasi-identifier", "allowed": "occupation categories",
     "nullable": True, "protected_output": "kept; missing values set to Unknown"},
    {"column": "relationship", "type": "categorical", "description": "Family role in household",
     "role": "feature", "sensitivity": "quasi-identifier", "allowed": "relationship categories",
     "nullable": False, "protected_output": "kept"},
    {"column": "race", "type": "categorical", "description": "Race (self-reported)",
     "role": "feature", "sensitivity": "sensitive attribute (special category where GDPR applies)",
     "allowed": "race categories", "nullable": False, "protected_output": "kept; used only inside aggregate analysis"},
    {"column": "sex", "type": "categorical", "description": "Sex (Male or Female)",
     "role": "feature", "sensitivity": "quasi-identifier and sensitive attribute", "allowed": "Male, Female",
     "nullable": False, "protected_output": "kept"},
    {"column": "capital-gain", "type": "integer", "description": "Capital gains in the year (USD)",
     "role": "feature", "sensitivity": "sensitive attribute (financial)", "allowed": ">= 0",
     "nullable": False, "protected_output": "kept; flag added where value is 99999 (top-code)"},
    {"column": "capital-loss", "type": "integer", "description": "Capital losses in the year (USD)",
     "role": "feature", "sensitivity": "sensitive attribute (financial)", "allowed": ">= 0",
     "nullable": False, "protected_output": "kept"},
    {"column": "hours-per-week", "type": "integer", "description": "Usual hours worked per week",
     "role": "feature", "sensitivity": "quasi-identifier", "allowed": "1-99", "nullable": False,
     "protected_output": "kept"},
    {"column": "native-country", "type": "categorical", "description": "Native country",
     "role": "feature", "sensitivity": "quasi-identifier", "allowed": "country names", "nullable": True,
     "protected_output": "generalised to United-States or Non-US (native_region)"},
    {"column": "income", "type": "categorical", "description": "Income above or below 50K USD per year",
     "role": "label", "sensitivity": "sensitive attribute", "allowed": "<=50K, >50K",
     "nullable": False, "protected_output": "kept; trailing period removed"},
]

MISSING_MARKERS = ["", "?", "NaN", "NA", "N/A", "null", "None"]
CATEGORICAL_MISSING = ["workclass", "occupation", "native-country"]
TOPCODE_CAPITAL_GAIN = 99999
K_THRESHOLD = 5
QUASI_IDENTIFIERS_RAW = ["age", "sex", "race", "marital-status", "native-country", "occupation"]
QUASI_IDENTIFIERS_PROTECTED = ["age_band", "sex", "race", "marital-status", "native_region", "occupation"]


def load(path) -> pd.DataFrame:
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    df.columns = [c.strip() for c in df.columns]
    for c in ["age", "fnlwgt", "education-num", "capital-gain", "capital-loss", "hours-per-week"]:
        df[c] = pd.to_numeric(df[c].str.strip(), errors="coerce")
    # the file uses several missing-value markers: empty, '?' (UCI convention) and 'NaN' text
    for c in df.columns:
        if str(df[c].dtype) in ("object", "str", "string"):
            df[c] = df[c].replace(MISSING_MARKERS, pd.NA)
    return df


# ---------- 2. Data quality ----------

def quality_rules(df: pd.DataFrame) -> dict:
    """Count how many rows break each rule. Used before and after cleaning."""
    income_clean = df["income"].astype("string").str.rstrip(".")
    string_cols = [c for c in df.columns if str(df[c].dtype) in ("object", "str", "string") or df[c].dtype == object]
    ws = sum(int((df[c].dropna().astype(str) != df[c].dropna().astype(str).str.strip()).sum())
             for c in string_cols)
    return {
        "missing_workclass": int(df["workclass"].isna().sum()),
        "missing_occupation": int(df["occupation"].isna().sum()),
        "missing_native_country": int(df["native-country"].isna().sum()),
        "income_trailing_period": int(df["income"].astype("string").str.endswith(".").sum()),
        "income_invalid_value": int((~income_clean.isin(["<=50K", ">50K"])).sum()),
        "exact_duplicate_rows": int(df.duplicated().sum()),
        "whitespace_in_text_cells": ws,
        "age_out_of_range": int((~df["age"].between(17, 90)).sum()),
        "hours_out_of_range": int((~df["hours-per-week"].between(1, 99)).sum()),
        "education_num_out_of_range": int((~df["education-num"].between(1, 16)).sum()),
        "negative_capital_values": int((df["capital-gain"] < 0).sum() + (df["capital-loss"] < 0).sum()),
        # only meaningful while both columns exist (the education column is dropped during cleaning)
        "education_to_education_num_conflicts": (
            int(df.groupby("education")["education-num"].nunique().gt(1).sum()) if "education" in df else 0),
        "capital_gain_topcode_99999": int((df["capital-gain"] == TOPCODE_CAPITAL_GAIN).sum()),
    }


def clean(df: pd.DataFrame):
    """Apply the fixes. Returns (clean_df, actions, quarantine_df). Every fix is counted."""
    actions = []
    out = df.copy()

    for c in [c for c in out.columns if str(out[c].dtype) in ("object", "str", "string")]:
        s = out[c].astype("string")
        changed = int((s.notna() & (s != s.str.strip())).sum())
        out[c] = s.str.strip().replace("", pd.NA)
        if changed:
            actions.append({"rule": "whitespace_in_text_cells", "column": c, "rows_changed": changed,
                            "fix": "trimmed leading and trailing spaces"})

    for c in CATEGORICAL_MISSING:
        n = int(out[c].isna().sum())
        if n:
            out[c] = out[c].fillna("Unknown")
            actions.append({"rule": f"missing_{c.replace('-', '_')}", "column": c, "rows_changed": n,
                            "fix": "kept the row, set missing value to 'Unknown' (not dropped)"})

    trailing = int(out["income"].astype("string").str.endswith(".").sum())
    out["income"] = out["income"].astype("string").str.rstrip(".")
    if trailing:
        actions.append({"rule": "income_trailing_period", "column": "income", "rows_changed": trailing,
                        "fix": "removed trailing period so both splits use the same labels"})

    # rows outside the allowed domain are quarantined, not silently changed
    bad = ~(out["age"].between(17, 90) & out["hours-per-week"].between(1, 99)
            & out["education-num"].between(1, 16) & (out["capital-gain"] >= 0) & (out["capital-loss"] >= 0))
    quarantine = out[bad].copy()
    if len(quarantine):
        actions.append({"rule": "out_of_range", "column": "various", "rows_changed": int(len(quarantine)),
                        "fix": "moved to quarantine.csv"})
    out = out[~bad]

    before = len(out)
    out = out.drop_duplicates()
    removed = before - len(out)
    if removed:
        actions.append({"rule": "exact_duplicate_rows", "column": "all", "rows_changed": removed,
                        "fix": "removed exact duplicate rows (after labels were normalised)"})

    out = out.assign(capital_gain_topcoded=out["capital-gain"] == TOPCODE_CAPITAL_GAIN)
    n_top = int(out["capital_gain_topcoded"].sum())
    actions.append({"rule": "capital_gain_topcode_99999", "column": "capital-gain", "rows_changed": n_top,
                    "fix": "value kept; flag column capital_gain_topcoded added (possible top-code, not corrected)"})

    # columns are dropped in protect(), after profiling, so duplicate and mapping checks see the full table
    return out.reset_index(drop=True), actions, quarantine


# ---------- 3. Privacy and security ----------

def _k_profile(df, cols):
    sizes = df.groupby(cols, dropna=False).size()
    return {"k_min": int(sizes.min()) if len(sizes) else 0,
            "groups": int(len(sizes)),
            "rows_in_groups_below_k": int(sizes[sizes < K_THRESHOLD].sum())}


def protect(clean_df: pd.DataFrame):
    """Generalise quasi-identifiers, then suppress rows in groups smaller than K_THRESHOLD."""
    before = _k_profile(clean_df, QUASI_IDENTIFIERS_RAW)

    p = clean_df.copy()
    p["age_band"] = pd.cut(p["age"], bins=[16, 24, 34, 44, 54, 64, 120],
                           labels=["17-24", "25-34", "35-44", "45-54", "55-64", "65+"]).astype("string")
    p["native_region"] = p["native-country"].where(p["native-country"] == "United-States", "Non-US")
    after_generalise = _k_profile(p, QUASI_IDENTIFIERS_PROTECTED)

    sizes = p.groupby(QUASI_IDENTIFIERS_PROTECTED, dropna=False)["income"].transform("size")
    suppressed = int((sizes < K_THRESHOLD).sum())
    p = p[sizes >= K_THRESHOLD].copy()
    after = _k_profile(p, QUASI_IDENTIFIERS_PROTECTED)

    p = p.drop(columns=["age", "native-country", "education", "fnlwgt"])
    metrics = {
        "data_minimisation": "dropped education (duplicate of education-num), fnlwgt (sampling weight), "
                             "and the raw age and native-country (replaced by generalised columns)",
        "k_threshold": K_THRESHOLD,
        "quasi_identifiers_before": QUASI_IDENTIFIERS_RAW,
        "quasi_identifiers_after": QUASI_IDENTIFIERS_PROTECTED,
        "before_generalisation_and_suppression": before,
        "after_generalisation_only": after_generalise,
        "after_suppression": after,
        "rows_suppressed": suppressed,
        "rows_suppressed_share": round(suppressed / len(clean_df), 5),
        "rows_published": int(len(p)),
    }
    return p.reset_index(drop=True), metrics


def classification_summary() -> dict:
    counts = {}
    for row in DATA_DICTIONARY:
        key = row["sensitivity"].split(" (")[0]
        counts[key] = counts.get(key, 0) + 1
    return counts
