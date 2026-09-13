#!/usr/bin/env python3
"""M0 tick decode: parse Dukascopy .bi5 tick files, validate, export parquet.

Record layout HYPOTHESIS to validate experimentally (not assumed blindly):
  20 bytes / record, big endian:
    uint32 ms offset from HOUR start (tick files are hourly)
    uint32 ask price  (scaled by instrument point, EURUSD => 1e5)
    uint32 bid price
    float32 ask volume
    float32 bid volume

Validation strategy: decode one file under the hypothesis, then check
- record count divisibility by 20
- price magnitude plausibility under 1e5 scaling (EURUSD ~ 0.5..2.5)
- ASK >= BID
- monotone timestamps within valid hour bounds
If any check fails under a candidate scaling, try alternates and report.
"""
import argparse
import json
import os
import struct
from datetime import datetime, timedelta, timezone

import numpy as np

RECORD = struct.Struct(">IIIf f")  # 20 bytes, big endian
POINT_CANDIDATES = [1e5, 1e3, 1.0]  # EURUSD point scaling candidates


def decompress(path):
    import lzma

    with open(path, "rb") as f:
        raw = f.read()
    if len(raw) == 0:
        return b""  # empty 200 body marker: no ticks this hour
    return lzma.decompress(raw, format=lzma.FORMAT_ALONE)


def decode_buf(buf, hour_start_utc, point=1e5, strict=True):
    """Decode decompressed bytes into arrays. hour_start_utc is aware datetime."""
    n, rem = divmod(len(buf), RECORD.size)
    if rem != 0:
        raise ValueError(f"corrupt buffer: {len(buf)} bytes not divisible by {RECORD.size}")
    if n == 0:
        return {
            "timestamp_ns": np.array([], dtype=np.int64),
            "ask": np.array([], dtype=np.float64),
            "bid": np.array([], dtype=np.float64),
            "ask_volume": np.array([], dtype=np.float64),
            "bid_volume": np.array([], dtype=np.float64),
        }
    recs = np.frombuffer(buf, dtype=[("ms", ">u4"), ("a", ">u4"), ("b", ">u4"),
                                     ("av", ">f4"), ("bv", ">f4")])
    ms = recs["ms"].astype(np.int64)
    ask = recs["a"].astype(np.float64) / point
    bid = recs["b"].astype(np.float64) / point
    base_ns = int(hour_start_utc.timestamp() * 1_000_000_000)
    ts = base_ns + ms * 1_000_000  # int64 nanoseconds since epoch, UTC
    out = {
        "timestamp_ns": ts,
        "ask": ask,
        "bid": bid,
        "ask_volume": recs["av"].astype(np.float64),
        "bid_volume": recs["bv"].astype(np.float64),
    }
    errs = validate(out, hour_start_utc)
    if strict and errs:
        raise ValueError("validation failed: " + "; ".join(errs))
    return out


def validate(t, hour_start_utc):
    errs = []
    ts = t["timestamp_ns"]
    if len(ts) and np.any(np.diff(ts) < 0):
        errs.append("timestamps not monotone non-decreasing")
    if len(ts):
        lo = int(hour_start_utc.timestamp() * 1_000_000_000)
        hi = lo + 3_600_000_000_000 - 1_000_000  # ns bounds of the hour
        if ts.min() < lo or ts.max() > hi:
            errs.append("timestamps outside hour bounds")
    if np.any(t["ask"] < t["bid"]):
        errs.append("ASK < BID present")
    if np.any(t["ask_volume"] < 0) or np.any(t["bid_volume"] < 0):
        errs.append("negative volumes")
    if np.any((t["bid"] < 0.5) | (t["bid"] > 2.5)):
        errs.append("price implausible for EURUSD (expected ~0.5-2.5)")
    return errs


def pick_scaling(buf, hour_start_utc):
    """Try candidate point scalings; return (point, n_errors) of the best."""
    best = None
    for p in POINT_CANDIDATES:
        try:
            t = decode_buf(buf, hour_start_utc, point=p, strict=False)
        except ValueError:
            return None, ["record size mismatch"]
        errs = validate(t, hour_start_utc)
        if best is None or len(errs) < len(best[1]):
            best = (p, errs)
        if not errs:
            break
    return best


def load_day(raw_dir, sym, ds):
    """Load all hours for one day into a single array dict (bid, ask order)."""
    day_dir = os.path.join(raw_dir, sym, ds.replace("-", ""))
    frames = []
    for h in range(24):
        p = os.path.join(day_dir, f"{h:02d}h_ticks.bi5")
        if not os.path.exists(p):
            continue
        hour_start = datetime.fromisoformat(f"{ds}T{h:02d}:00:00+00:00")
        buf = decompress(p)
        t = decode_buf(buf, hour_start, point=1e5, strict=True)
        frames.append(t)
    if not frames:
        raise FileNotFoundError(f"no tick data for {ds}")
    return {
        k: np.concatenate([f[k] for f in frames])
        for k in frames[0]
    }


def summarize(t, ds):
    import pandas as pd

    spread = t["ask"] - t["bid"]
    sp_pips = spread / 1e-4
    ts = pd.to_datetime(t["timestamp_ns"], utc=True)
    mins = ((ts - pd.Timestamp(f"{ds}T00:00:00Z")).total_seconds() // 60).astype(int).to_numpy()
    per_min = np.bincount(mins, minlength=1440)
    hrs = mins // 60
    hour_rows = []
    for h in range(24):
        m = hrs == h
        if m.sum():
            hour_rows.append({"hour_utc": h, "n_ticks": int(m.sum()),
                              "median_spread_pips": round(float(np.median(sp_pips[m])), 3)})
    return {
        "date": ds,
        "n_ticks": int(t["bid"].size),
        "median_spread_pips": round(float(np.median(sp_pips)), 3),
        "p05_spread_pips": round(float(np.percentile(sp_pips, 5)), 3),
        "p95_spread_pips": round(float(np.percentile(sp_pips, 95)), 3),
        "p99_spread_pips": round(float(np.percentile(sp_pips, 99)), 3),
        "max_spread_pips": round(float(sp_pips.max()), 3),
        "median_ticks_per_minute": round(float(np.median(per_min[per_min > 0])) if (per_min > 0).any() else 0.0, 1),
        "p95_ticks_per_minute": round(float(np.percentile(per_min, 95)), 1),
        "bid_volume_zero_pct": round(float((t["bid_volume"] == 0).mean() * 100), 2),
        "ask_volume_zero_pct": round(float((t["ask_volume"] == 0).mean() * 100), 2),
        "median_bid_volume": round(float(np.median(t["bid_volume"])), 3),
        "median_ask_volume": round(float(np.median(t["ask_volume"])), 3),
        "hours": hour_rows,
    }


def to_parquet(t, out_path):
    import pandas as pd

    spread_pips = (t["ask"] - t["bid"]) / 1e-4
    df = pd.DataFrame({
        "bid": t["bid"].astype(np.float64),
        "ask": t["ask"].astype(np.float64),
        "bid_volume": t["bid_volume"].astype(np.float32),
        "ask_volume": t["ask_volume"].astype(np.float32),
        "spread_pips": spread_pips.astype(np.float64),
    }, index=pd.DatetimeIndex(pd.to_datetime(t["timestamp_ns"], utc=True), name="timestamp_utc"))
    df.to_parquet(out_path, compression="zstd")
    return df


def aggregate_5m_bid(t):
    """Causally correct 5m BID bars: bucket [t, t+5m), open=first bid, close=last."""
    import pandas as pd

    ts = pd.DatetimeIndex(pd.to_datetime(t["timestamp_ns"], utc=True))
    s = pd.Series(t["bid"], index=ts)
    g = s.resample("5min", label="left", closed="left")
    df = pd.DataFrame({
        "open": g.first(), "high": g.max(), "low": g.min(), "close": g.last(),
        "n": g.count(),
    }).dropna(subset=["n"])
    return df[df["n"] > 0].drop(columns="n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="EURUSD")
    ap.add_argument("--dates", nargs="*", required=True)
    args = ap.parse_args()
    raw_dir = os.path.join(RAW_DIR := os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "data_raw", "tick_m0")))
    report = {"days": [], "format_probe": None}
    for ds in args.dates:
        t = load_day(raw_dir, args.symbol, ds)
        summary = summarize(t, ds)
        report["days"].append(summary)
        print(json.dumps({k: v for k, v in summary.items() if k != "hours"}, indent=2))
    with open(os.path.join(os.path.dirname(__file__), "tick_stats.json"), "w") as f:
        json.dump(report, f, indent=2)


if __name__ == "__main__":
    main()
