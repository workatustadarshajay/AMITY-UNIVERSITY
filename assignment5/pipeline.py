"""Governance pipeline: ingest -> profile -> clean -> profile -> protect -> publish.

Each step runs in order and is logged with its status and duration. A failed step stops the run, which
is how AWS Data Pipeline would handle a failed activity (see aws/datapipeline_definition.json).

    python pipeline.py --raw data/adult.csv --out output
"""
import argparse
import hashlib
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

import governance as G


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def run(raw_path: Path, out: Path):
    out.mkdir(parents=True, exist_ok=True)
    (out / "logs").mkdir(exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        handlers=[logging.FileHandler(out / "logs" / "pipeline.log", mode="w"),
                                  logging.StreamHandler(sys.stdout)])
    log = logging.getLogger("governance")
    state = {"lineage": [], "steps": []}

    def step(name, fn):
        t0 = time.perf_counter()
        log.info("step %s: start", name)
        try:
            result = fn()
        except Exception:
            log.exception("step %s: FAILED", name)
            state["steps"].append({"step": name, "status": "failed"})
            raise
        dt = round(time.perf_counter() - t0, 3)
        state["steps"].append({"step": name, "status": "succeeded", "seconds": dt})
        log.info("step %s: succeeded in %.3fs", name, dt)
        return result

    # 1. ingest
    def ingest():
        raw = G.load(raw_path)
        digest = sha256(raw_path)
        state["lineage"].append({"step": "ingest", "source": str(raw_path), "sha256": digest,
                                 "rows": int(len(raw))})
        log.info("  %d rows, sha256 %s", len(raw), digest)
        return raw, digest

    raw, digest = step("ingest", ingest)

    # 2. profile before cleaning
    before = step("profile_before", lambda: G.quality_rules(raw))

    # 3. clean
    def do_clean():
        clean_df, actions, quarantine = G.clean(raw)
        state["lineage"].append({"step": "clean", "rows_in": int(len(raw)), "rows_out": int(len(clean_df)),
                                 "actions": len(actions)})
        return clean_df, actions, quarantine

    clean_df, actions, quarantine = step("clean", do_clean)

    # 4. profile after cleaning
    after = step("profile_after", lambda: G.quality_rules(clean_df))

    # 5. protect
    protected, privacy = step("protect", lambda: G.protect(clean_df))
    state["lineage"].append({"step": "protect", "rows_in": int(len(clean_df)), "rows_out": int(len(protected)),
                             "k_threshold": G.K_THRESHOLD})

    # 6. publish outputs
    def publish():
        meta_dir, q_dir, p_dir = out / "metadata", out / "quality", out / "privacy"
        for d in (meta_dir, q_dir, p_dir, out / "protected"):
            d.mkdir(parents=True, exist_ok=True)

        pd.DataFrame(G.DATA_DICTIONARY).to_csv(meta_dir / "data_dictionary.csv", index=False)
        dataset_meta = {
            "name": "UCI Adult (Census Income)",
            "source": "https://archive.ics.uci.edu/dataset/2/adult",
            "source_file_sha256": digest,
            "rows_raw": int(len(raw)),
            "rows_clean": int(len(clean_df)),
            "rows_published": int(len(protected)),
            "rows_quarantined": int(len(quarantine)),
            "columns_published": list(protected.columns),
            "classification_counts": G.classification_summary(),
            "owner": "[to be assigned by the data governance council]",
            "retention": "[to be set by policy; example: 1 year after the analysis ends]",
            "lineage": state["lineage"],
            "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        (meta_dir / "dataset_metadata.json").write_text(json.dumps(dataset_meta, indent=2), encoding="utf-8")

        qa = pd.DataFrame({"rule": list(before), "rows_failing_before": list(before.values()),
                           "rows_failing_after": [after[k] for k in before]})
        qa.to_csv(q_dir / "quality_before_after.csv", index=False)
        (q_dir / "quality_actions.json").write_text(json.dumps(actions, indent=2), encoding="utf-8")
        if len(quarantine):
            quarantine.to_csv(q_dir / "quarantine.csv", index=False)

        (p_dir / "privacy_metrics.json").write_text(json.dumps(privacy, indent=2), encoding="utf-8")
        protected.to_csv(out / "protected" / "adult_protected.csv", index=False)
        return qa

    qa = step("publish", publish)

    run_summary = {"steps": state["steps"], "rows": {"raw": len(raw), "clean": len(clean_df),
                                                    "published": len(protected)}}
    (out / "run_summary.json").write_text(json.dumps(run_summary, indent=2), encoding="utf-8")
    log.info("pipeline finished: %d raw -> %d clean -> %d published", len(raw), len(clean_df), len(protected))
    return {"quality": qa, "privacy": privacy, "actions": actions, "before": before, "after": after}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", default="data/adult.csv")
    ap.add_argument("--out", default="output")
    a = ap.parse_args()
    run(Path(a.raw), Path(a.out))
