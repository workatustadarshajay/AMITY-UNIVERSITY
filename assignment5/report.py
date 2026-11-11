"""Build the Assignment 5 PDF report from the pipeline outputs.

    python report.py --out output
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
from reportlab.lib.utils import ImageReader  # noqa: E402
from reportlab.platypus import Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle  # noqa: E402

styles = getSampleStyleSheet()
H1, H2, BODY = styles["Heading1"], styles["Heading2"], styles["BodyText"]
SMALL = styles["BodyText"].clone("small", fontSize=7.5, leading=9)


def table(rows, widths=None, font=8):
    rows = [[Paragraph(str(c), SMALL) if isinstance(c, str) and len(c) > 28 else c for c in r] for r in rows]
    t = Table(rows, colWidths=widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#DDE4EE")),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
        ("FONTSIZE", (0, 0), (-1, -1), font),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    return t


def fig(path: Path, width=15 * cm):
    w, h = ImageReader(str(path)).getSize()
    return Image(str(path), width=width, height=width * h / w)


def main(out: str):
    out = Path(out)
    meta = json.loads((out / "metadata" / "dataset_metadata.json").read_text(encoding="utf-8"))
    dictionary = pd.read_csv(out / "metadata" / "data_dictionary.csv")
    qa = pd.read_csv(out / "quality" / "quality_before_after.csv")
    actions = json.loads((out / "quality" / "quality_actions.json").read_text(encoding="utf-8"))
    privacy = json.loads((out / "privacy" / "privacy_metrics.json").read_text(encoding="utf-8"))
    run = json.loads((out / "run_summary.json").read_text(encoding="utf-8"))
    figs = out / "figures"
    figs.mkdir(parents=True, exist_ok=True)

    # figures
    fig_q, ax = plt.subplots(figsize=(9, 4))
    q = qa[qa.rows_failing_before > 0]
    x = range(len(q))
    ax.bar([i - 0.2 for i in x], q.rows_failing_before, 0.4, label="before", color="#C44E52")
    ax.bar([i + 0.2 for i in x], q.rows_failing_after, 0.4, label="after", color="#55A868")
    ax.set_xticks(list(x), q.rule, rotation=30, ha="right", fontsize=8)
    ax.set_ylabel("Rows failing the rule")
    ax.set_title("Data quality rules: rows failing before and after cleaning")
    ax.legend()
    fig_q.tight_layout()
    fig_q.savefig(figs / "01_quality_before_after.png", dpi=130)
    plt.close(fig_q)

    kb = privacy["before_generalisation_and_suppression"]
    ka = privacy["after_suppression"]
    fig_k, ax = plt.subplots(figsize=(7, 3.8))
    labels = ["Raw quasi-identifiers", "After generalisation", "After suppression"]
    ax.bar(labels, [kb["rows_in_groups_below_k"], privacy["after_generalisation_only"]["rows_in_groups_below_k"],
                    ka["rows_in_groups_below_k"]], color=["#C44E52", "#DD8452", "#55A868"])
    ax.set_ylabel(f"Rows in groups smaller than k={privacy['k_threshold']}")
    ax.set_title("Re-identification risk: rows in small groups")
    ax.tick_params(axis="x", labelsize=8)
    fig_k.tight_layout()
    fig_k.savefig(figs / "02_k_anonymity.png", dpi=130)
    plt.close(fig_k)

    s = []
    s.append(Paragraph("Data Governance for the UCI Adult Dataset", H1))
    s.append(Paragraph("Assignment No. 5", BODY))
    s.append(Spacer(1, 0.3 * cm))

    s.append(Paragraph("1. Purpose of data governance for this dataset", H2))
    s.append(Paragraph(
        "The Adult dataset (48,842 census records) is used to study income. Its records describe people and include "
        "sensitive attributes: race, sex, and capital gains and losses. Governance sets the rules that make the data "
        "fit for use and protects the people in it. For this dataset that means four things:", BODY))
    for t in [
        "<b>Trust in results.</b> Income studies are only as good as the data. Label inconsistencies and hidden missing "
        "values change the answers, so they must be found and fixed in a documented, repeatable way.",
        "<b>Privacy.</b> Demographic combinations can single out individuals. Quasi-identifiers must be generalised "
        "and small groups suppressed before the data is shared.",
        "<b>Accountability.</b> Every value that changes must be traceable: source checksum, rules applied, rows affected.",
        "<b>Operational control.</b> A scheduled, monitored pipeline that stops on failure, so governance does not depend "
        "on someone running scripts by hand.",
    ]:
        s.append(Paragraph("- " + t, BODY))

    s.append(Paragraph("2. Metadata management", H2))
    s.append(Paragraph(
        f"Source: {meta['source']}. Source file SHA-256: <font face='Courier' size=7>{meta['source_file_sha256']}</font>. "
        f"Rows: {meta['rows_raw']:,} raw, {meta['rows_clean']:,} clean, {meta['rows_published']:,} published. "
        f"Classification of the 15 raw columns: "
        + ", ".join(f"{k} {v}" for k, v in meta["classification_counts"].items()) + ". "
        f"Owner and retention are placeholders in <font face='Courier'>dataset_metadata.json</font> until a data "
        "governance council assigns them.", BODY))
    rows = [["Column", "Type", "Description", "Sensitivity", "Nullable", "Published as"]]
    for _, r in dictionary.iterrows():
        rows.append([r["column"], r["type"], r["description"], r["sensitivity"], "yes" if r["nullable"] else "no",
                     r["protected_output"]])
    s.append(table(rows, widths=[2.6 * cm, 1.7 * cm, 3.8 * cm, 3.4 * cm, 1.3 * cm, 4.2 * cm], font=7))
    s.append(Paragraph(
        "The dictionary is the metadata catalogue for this dataset. Apache Atlas could hold the same records for a "
        "larger estate; this project keeps them as CSV and JSON so they can be checked in version control.", BODY))
    s.append(PageBreak())

    dup_raw = int(qa.loc[qa.rule == "exact_duplicate_rows", "rows_failing_before"].iloc[0])
    dup_removed = next(a["rows_changed"] for a in actions if a["rule"] == "exact_duplicate_rows")
    s.append(Paragraph("3. Data quality assessment and improvement", H2))
    s.append(Paragraph(
        "Each rule counts rows that break it. The profile runs on the raw file, then on the cleaned table, using the "
        "same rules. Rules that find nothing still appear with zero, so the assessment shows what was checked.", BODY))
    rows = [["Rule", "Rows failing before", "Rows failing after"]] + [
        [r.rule, f"{int(r.rows_failing_before):,}", f"{int(r.rows_failing_after):,}"] for r in qa.itertuples()]
    s.append(table(rows, widths=[8 * cm, 4 * cm, 4 * cm]))
    s.append(fig(figs / "01_quality_before_after.png", width=14 * cm))
    s.append(Paragraph("Improvements made, with the number of rows changed:", BODY))
    rows = [["Rule", "Column", "Rows changed", "Fix"]] + [
        [a["rule"], a["column"], f"{a['rows_changed']:,}", a["fix"]] for a in actions]
    s.append(table(rows, widths=[4.2 * cm, 2.8 * cm, 2 * cm, 7.7 * cm], font=7))
    s.append(Spacer(1, 0.2 * cm))
    s.append(Paragraph(
        "<b>Examples.</b> (1) In the raw file, 2,799 workclass values are missing. Two markers are used: "
        "<font face='Courier'>?</font> (1,836 rows) and the text <font face='Courier'>NaN</font> (963 rows). The "
        "first profile counted only the first. Both are now recognised, and the rows are kept with the value "
        "<i>Unknown</i>. (2) The test split labels income as <font face='Courier'>&lt;=50K.</font> with a trailing "
        f"period, {int(qa.loc[qa.rule == 'income_trailing_period', 'rows_failing_before'].iloc[0]):,} rows. "
        f"{dup_raw} exact duplicates are in the raw file. Once labels and missing markers are normalised, more rows "
        f"match, so {dup_removed} duplicate rows are removed in total. "
        "(3) 244 rows have capital gain 99999. That looks like a top-code, so the value is kept and a flag column is "
        "added rather than changing the number.", BODY))
    s.append(PageBreak())

    s.append(Paragraph("4. Privacy and security", H2))
    s.append(Paragraph(
        "<b>Classification.</b> The dataset has no direct identifiers (no names, IDs or addresses); the checks confirm "
        "none of the columns carries one. Quasi-identifiers (age, sex, race, marital status, native country, "
        "occupation, relationship, education, hours) could single someone out when combined. Income, race and "
        "capital gains and losses are sensitive attributes.", BODY))
    s.append(Paragraph(
        f"<b>Re-identification risk.</b> Quasi-identifiers were measured as a k-anonymity check: the smallest group "
        f"of records sharing the same values. Before protection, the smallest group has {kb['k_min']} record(s), and "
        f"{kb['rows_in_groups_below_k']:,} rows ({kb['rows_in_groups_below_k'] / meta['rows_clean']:.1%}) sit in "
        f"groups smaller than {privacy['k_threshold']}. Age was generalised to 10-year bands and native country to "
        "United-States or Non-US. Groups still smaller than k are suppressed. The published file has k_min = "
        f"{ka['k_min']} and removes {privacy['rows_suppressed']:,} rows "
        f"({privacy['rows_suppressed_share']:.1%}).", BODY))
    s.append(fig(figs / "02_k_anonymity.png", width=12 * cm))
    s.append(table([
        ["Measure", "Raw (cleaned)", "Generalised only", "Published"],
        ["Smallest group size (k_min)", str(kb["k_min"]), str(privacy["after_generalisation_only"]["k_min"]),
         str(ka["k_min"])],
        ["Groups", f"{kb['groups']:,}", f"{privacy['after_generalisation_only']['groups']:,}", f"{ka['groups']:,}"],
        ["Rows in groups below k", f"{kb['rows_in_groups_below_k']:,}",
         f"{privacy['after_generalisation_only']['rows_in_groups_below_k']:,}", "0"],
        ["Rows published", f"{meta['rows_clean']:,}", f"{meta['rows_clean']:,}", f"{meta['rows_published']:,}"],
    ], widths=[6 * cm, 3.5 * cm, 3.5 * cm, 3.5 * cm]))
    s.append(Spacer(1, 0.2 * cm))
    s.append(Paragraph(
        "<b>Data minimisation.</b> education (duplicate of education-num), fnlwgt (a census sampling weight that describes "
        "the sample, not a person), and the raw age and native-country (replaced by the generalised columns) are not "
        "published.", BODY))
    s.append(Paragraph("<b>Access and security design (documented; configured in the AWS definition where stated):</b>", BODY))
    s.append(table([
        ["Control", "Design", "Status"],
        ["Access roles", "Analysts read only the published file. The governance steward alone reads the raw file "
                         "(least privilege).", "Designed. Not applied to any account."],
        ["Encryption at rest", "S3 buckets with SSE-KMS default encryption. Keys managed by the data owner.",
         "Designed. Bucket settings are outside the pipeline definition."],
        ["Encryption in transit", "HTTPS only (bucket policy denies insecure transport).", "Designed."],
        ["Public access", "Block all public access on the governance buckets.", "Designed."],
        ["Audit", "Pipeline logs written to S3 (pipelineLogUri) and kept with the run summary.",
         "In the AWS definition; logs are written locally here."],
        ["Failure alerting", "SNS alarm on failed activity.", "In the AWS definition; topic not created."],
    ], widths=[3.2 * cm, 8 * cm, 5.5 * cm], font=7.5))
    s.append(PageBreak())

    s.append(Paragraph("5. Orchestration", H2))
    s.append(Paragraph(
        "The pipeline runs as ordered steps. A failed step stops the run and is logged, which is how an AWS Data "
        "Pipeline activity behaves when it fails. Steps and durations from this run:", BODY))
    rows = [["Step", "Status", "Seconds"]] + [
        [st["step"], st["status"], f"{st.get('seconds', 0):.3f}"] for st in run["steps"]]
    s.append(table(rows, widths=[5 * cm, 4 * cm, 4 * cm]))
    s.append(Spacer(1, 0.2 * cm))
    s.append(Paragraph(
        "<b>AWS Data Pipeline definition.</b> <font face='Courier'>aws/datapipeline_definition.json</font> defines the "
        "same steps: an S3 input node (raw data), a ShellCommandActivity on a t2.micro EC2 resource that runs "
        "<font face='Courier'>pipeline.py</font>, an S3 output node (protected data), S3 pipeline logs, and an SNS "
        "failure alarm. It was not deployed, because the project has no AWS credits. It can be checked before "
        "deployment with <font face='Courier'>aws datapipeline validate-pipeline-definition</font>. AWS Data "
        "Pipeline is an older orchestration service; check that it is available to your account, and consider AWS "
        "Step Functions or Amazon MWAA for new work.", BODY))
    s.append(Paragraph(
        "<b>Screenshots.</b> The deliverables ask for screenshots of the privacy and security measures. None are "
        "included, because no AWS console was used. The local outputs (logs, privacy metrics, quality tables) serve "
        "as the evidence instead.", BODY))

    s.append(Paragraph("6. Limitations", H2))
    for t in [
        "The dataset is public and already anonymised by its providers. The privacy work shows the method, not a "
        "real re-identification risk assessment.",
        "Owner, retention period and the governance council are placeholders.",
        "The 99999 capital-gain value is flagged, not corrected. Whether it is a true top-code needs the data owner's "
        "confirmation.",
        "The AWS definition and access design were not deployed or tested in an account.",
        "The k threshold (5) and the age bands are policy choices, and they can be changed in governance.py.",
    ]:
        s.append(Paragraph("- " + t, BODY))

    s.append(Paragraph("7. References", H2))
    for t in [
        "UCI Machine Learning Repository, Adult dataset: https://archive.ics.uci.edu/dataset/2/adult",
        "Sweeney, L. (2002). k-anonymity: a model for protecting privacy. International Journal on Uncertainty, "
        "Fuzziness and Knowledge-Based Systems, 10(5), 557-570.",
        "Apache Atlas, metadata and governance platform: https://atlas.apache.org",
        "AWS, Data Pipeline Developer Guide: https://docs.aws.amazon.com/datapipeline/latest/DeveloperGuide/what-is-datapipeline.html",
    ]:
        s.append(Paragraph("- " + t, BODY))

    doc = SimpleDocTemplate(str(out / "Assignment5_Report.pdf"), pagesize=A4,
                            leftMargin=2 * cm, rightMargin=2 * cm, topMargin=2 * cm, bottomMargin=2 * cm,
                            title="Assignment 5 Report")
    doc.build(s)
    print("wrote", out / "Assignment5_Report.pdf")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="output")
    main(ap.parse_args().out)
