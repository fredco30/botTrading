#!/usr/bin/env python3
"""M0 tick analysis: stats, parquet export, storage estimates, 5m comparison vs existing feed.

Reads raw .bi5 downloaded by dukascopy_tick_probe.py for the sample dates,
writes research/tick_m0/tick_stats.json and data_raw/tick_m0/EURUSD_sample.parquet.
Pure data validation - no strategy logic.
"""
import json
import os
import sys
from datetime import datetime

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
import decode_ticks as dt

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
RAW_DIR = os.path.join(ROOT, "data_raw", "tick_m0")
SAMPLE_DATES = ["2018-06-04", "2018-06-05", "2018-06-06", "2018-06-07", "2018-06-08"]
SYMBOL = "EURUSD"
EXISTING_5M = os.path.join(ROOT, "data_raw", "parquet", "EURUSD_5m.parquet")
OUT_PARQUET = os.path.join(RAW_DIR, "EURUSD_sample_ticks.parquet")
OUT_STATS = os.path.join(os.path.dirname(__file__), "tick_stats.json")


def raw_compressed_bytes():
    total = 0
    for ds in SAMPLE_DATES:
        day_dir = os.path.join(RAW_DIR, SYMBOL, ds.replace("-", ""))
        if os.path.isdir(day_dir):
            total += sum(os.path.getsize(os.path.join(day_dir, f)) for f in os.listdir(day_dir))
    return total


def main():
    frames = []
    day_stats = []
    for ds in SAMPLE_DATES:
        t = dt.load_day(RAW_DIR, SYMBOL, ds)
        frames.append(t)
        day_stats.append(dt.summarize(t, ds))
    t = {k: np.concatenate([f[k] for f in frames]) for k in frames[0]}
    overall = dt.summarize(t, SAMPLE_DATES[0])
    for d in day_stats[1:]:
        for k in ("median_ticks_per_minute", "p95_ticks_per_minute"):
            pass
    overall["date"] = "SAMPLE_TOTAL"

    # parquet export + sizes
    df = dt.to_parquet(t, OUT_PARQUET)
    raw_bytes = raw_compressed_bytes()
    pq_bytes = os.path.getsize(OUT_PARQUET)
    n = len(df)
    days = len(SAMPLE_DATES)
    overall["raw_compressed_bytes"] = raw_bytes
    overall["parquet_bytes"] = pq_bytes
    overall["n_ticks"] = int(n)
    overall["estimated_1y_parquet_gb"] = round(pq_bytes / days * 252 / 1e9, 3)
    overall["estimated_2010_2018_parquet_gb"] = round(pq_bytes / days * (252 * 9) / 1e9, 3)

    # 5m BID comparison with existing feed
    bars = dt.aggregate_5m_bid(t)
    ex = pd.read_parquet(EXISTING_5M).loc[bars.index[0]:bars.index[-1]]
    joined = bars.join(ex, how="inner", rsuffix="_ex")
    diffs = {}
    for col in ("open", "high", "low", "close"):
        d = (joined[col] - joined[f"{col}_ex"]).abs() / 1e-4
        diffs[f"max_{col}_diff_pips"] = round(float(d.max()), 2)
        diffs[f"p99_{col}_diff_pips"] = round(float(np.percentile(d, 99)), 2)
    overall["n_5m_bars_compared"] = int(len(joined))
    overall["existing_5m_comparison"] = diffs

    # per-day and per-hour detail
    report = {
        "generated_utc": datetime.utcnow().isoformat() + "Z",
        "symbol": SYMBOL,
        "sample_dates": SAMPLE_DATES,
        "format": "20B BE: u32 ms-from-hour-start, u32 ask, u32 bid, f32 askvol, f32 bidvol; point=1e5",
        "sample_total": overall,
        "days": day_stats,
    }
    with open(OUT_STATS, "w") as f:
        json.dump(report, f, indent=2)
    print(json.dumps(overall, indent=2))
    print("\nPer-day:")
    for d in day_stats:
        print(json.dumps({k: v for k, v in d.items() if k != "hours"}))


if __name__ == "__main__":
    main()
