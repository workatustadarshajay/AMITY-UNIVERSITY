"""Compare the real-time (streaming) results with the batch results, measure streaming latency, and draw figures.

    python compare.py --out output
"""
import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402


def read_dir(path: Path) -> pd.DataFrame:
    """Spark writes JSON as part files (one JSON object per line)."""
    parts = sorted(path.glob("part-*.json"))
    if not parts:
        raise FileNotFoundError(f"no Spark output in {path}")
    return pd.concat([pd.read_json(p, lines=True) for p in parts], ignore_index=True)


def latest_monthly(stream_monthly: pd.DataFrame) -> pd.DataFrame:
    """Update mode re-emits a month each time it changes; the last emission is the final value."""
    s = stream_monthly.sort_values("batch_id")
    return s.drop_duplicates(subset="month", keep="last").sort_values("month").reset_index(drop=True)


def compare_events(stream: pd.DataFrame, batch: pd.DataFrame) -> dict:
    m = stream.merge(batch, on="date", how="outer", suffixes=("_stream", "_batch"), indicator=True)
    both = m[m["_merge"] == "both"]
    return {
        "stream_events": int(len(stream)),
        "batch_rows": int(len(batch)),
        "duplicate_dates_in_stream": int(stream["date"].duplicated().sum()),
        "dates_only_in_stream": int((m["_merge"] == "left_only").sum()),
        "dates_only_in_batch": int((m["_merge"] == "right_only").sum()),
        "regime_mismatches": int((both["regime_stream"] != both["regime_batch"]).sum()),
        "alert_mismatches": int((both["alert_stream"] != both["alert_batch"]).sum()),
        "max_abs_close_diff": float((both["close_stream"] - both["close_batch"]).abs().max()),
        "max_abs_range_pct_diff": float((both["range_pct_stream"] - both["range_pct_batch"]).abs().max()),
        "identical_per_event_results": bool(
            len(m[m["_merge"] != "both"]) == 0
            and (both["regime_stream"] == both["regime_batch"]).all()
            and (both["alert_stream"] == both["alert_batch"]).all()
            and (both["close_stream"] - both["close_batch"]).abs().max() < 1e-9
            and (both["range_pct_stream"] - both["range_pct_batch"]).abs().max() < 1e-6),
    }


def compare_monthly(stream_m: pd.DataFrame, batch_m: pd.DataFrame) -> dict:
    s = latest_monthly(stream_m)
    b = batch_m.sort_values("month").reset_index(drop=True)
    s["month"] = pd.to_datetime(s["month"], utc=True).dt.tz_localize(None)
    b["month"] = pd.to_datetime(b["month"], utc=True).dt.tz_localize(None)
    m = s.merge(b, on="month", how="outer", suffixes=("_stream", "_batch"), indicator=True)
    both = m[m["_merge"] == "both"]
    return {
        "months_stream": int(len(s)),
        "months_batch": int(len(b)),
        "months_only_in_one": int((m["_merge"] != "both").sum()),
        "days_mismatches": int((both["days_stream"] != both["days_batch"]).sum()),
        "alert_days_mismatches": int((both["alert_days_stream"] != both["alert_days_batch"]).sum()),
        "max_abs_avg_close_diff": float((both["avg_close_stream"] - both["avg_close_batch"]).abs().max()),
        "max_abs_max_close_diff": float((both["max_close_stream"] - both["max_close_batch"]).abs().max()),
        "identical_monthly_results": bool(
            (m["_merge"] == "both").all()
            and (both["days_stream"] == both["days_batch"]).all()
            and (both["alert_days_stream"] == both["alert_days_batch"]).all()
            and (both["avg_close_stream"] - both["avg_close_batch"]).abs().max() < 1e-6),
    }, m


def main(out: str):
    out = Path(out)
    metrics = json.loads((out / "metrics.json").read_text(encoding="utf-8"))
    stream = read_dir(out / "stream_events")
    batch = read_dir(out / "batch_events")
    stream_m = read_dir(out / "stream_monthly")
    batch_m = read_dir(out / "batch_monthly")

    result = {"mode": metrics["mode"]}
    result["events"] = compare_events(stream, batch)
    monthly_result, monthly_merged = compare_monthly(stream_m, batch_m)
    result["monthly"] = monthly_result

    lat = stream["latency_s"]
    result["latency_seconds"] = {
        "mean": round(float(lat.mean()), 4), "p50": round(float(lat.quantile(0.5)), 4),
        "p95": round(float(lat.quantile(0.95)), 4), "max": round(float(lat.max()), 4),
    }
    span = float(stream["processed_epoch"].max() - stream["ingest_epoch"].min())
    result["stream"] = {
        "end_to_end_seconds": round(span, 3),
        "throughput_events_per_second": round(len(stream) / span, 2) if span > 0 else None,
        "micro_batches_with_data": int(sum(1 for p in metrics["stream_progress"] if (p.get("input_rows") or 0) > 0)),
        "producer_pause_seconds": metrics["pause_seconds"],
        "batch_size": metrics["batch_size"],
    }
    result["batch"] = {"wall_seconds": metrics["batch"]["wall_seconds"], "rows": metrics["batch"]["rows"]}
    regimes = pd.DataFrame({
        "stream": stream["regime"].value_counts(),
        "batch": batch["regime"].value_counts(),
    }).fillna(0).astype(int)
    result["regime_counts"] = regimes.to_dict()
    result["alert_days_total"] = int(batch["alert"].sum())
    (out / "comparison.json").write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")

    fig_dir = out / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(8, 4))
    ax.hist(lat, bins=40, color="#4C72B0")
    ax.axvline(lat.median(), color="black", ls="--", label=f"median {lat.median():.3f}s")
    ax.set_xlabel("Event latency: processed time minus ingest time (s)")
    ax.set_ylabel("Events")
    ax.set_title("Real-time pipeline: latency per event")
    ax.legend()
    fig.tight_layout()
    fig.savefig(fig_dir / "01_latency_histogram.png", dpi=130)
    plt.close(fig)

    b = batch.assign(date=pd.to_datetime(batch["date"])).sort_values("date")
    fig, ax = plt.subplots(figsize=(11, 4.5))
    ax.plot(b["date"], b["close"], lw=0.6, color="#4C72B0", label="VIX close (batch and stream agree)")
    ax.axhline(30, color="#C44E52", ls="--", lw=0.8, label="stress level 30")
    ax.axhline(20, color="#DD8452", ls="--", lw=0.8, label="elevated level 20")
    al = b[b["alert"]]
    ax.scatter(al["date"], al["close"], s=6, color="#C44E52", label="stress alert days", zorder=3)
    ax.set_ylabel("VIX close")
    ax.set_title("VIX history with stress alerts (from the streaming pipeline)")
    ax.legend(loc="upper right", fontsize=8)
    fig.tight_layout()
    fig.savefig(fig_dir / "02_vix_timeline.png", dpi=130)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(7, 4))
    regimes.plot(kind="bar", ax=ax, color=["#55A868", "#4C72B0"], rot=0)
    ax.set_ylabel("Trading days")
    ax.set_title("Regime counts: real-time vs batch (identical)")
    fig.tight_layout()
    fig.savefig(fig_dir / "03_regime_counts.png", dpi=130)
    plt.close(fig)

    print(f"  per-event identical: {result['events']['identical_per_event_results']}, "
          f"monthly identical: {result['monthly']['identical_monthly_results']}, "
          f"latency p50 {result['latency_seconds']['p50']}s p95 {result['latency_seconds']['p95']}s")
    print("wrote", out / "comparison.json")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="output")
    main(ap.parse_args().out)
