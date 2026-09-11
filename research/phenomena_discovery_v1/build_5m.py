#!/usr/bin/env python3
"""Build 5-minute OHLCV parquet files from downloaded Dukascopy .bi5 files.

bi5 daily candle record (24 B, big-endian): int32 offset_sec (UTC day),
int32 open, close, low, high — prices scaled by 10^POINT_SCALE — then
float32 volume (format verified empirically: EURUSD 2020-06-30 rec0 =
(0, 112466, 112462, 112458, 112470, 194.08) -> 1.12466/1.12462/...).

POINT_SCALE auto-detected per symbol: the only scale in {1e2..1e5} that
puts the median close inside a plausible instrument range.

Output: data_raw/parquet/<SYM>_5m.parquet (ts = bar OPEN, UTC; 'n' = number
of 1-min source bars; 1-min bars with any price <= 0 dropped — placeholder
prints, not real quotes).
"""
import glob
import lzma
import os

import numpy as np
import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
RAW_DIR = os.path.join(ROOT, "data_raw")
OUT_DIR = os.path.join(RAW_DIR, "parquet")

REC = np.dtype([("off", ">i4"), ("o", ">i4"), ("c", ">i4"),
                ("l", ">i4"), ("h", ">i4"), ("v", ">f4")])

PLAUSIBLE = {
    "EURUSD": (0.60, 1.80), "GBPUSD": (1.10, 2.30), "USDJPY": (60.0, 200.0),
    "USA500IDXUSD": (400.0, 12000.0), "USATECHIDXUSD": (800.0, 30000.0),
}


def parse_day(path):
    with open(path, "rb") as f:
        raw = f.read()
    try:
        buf = lzma.decompress(raw, format=lzma.FORMAT_ALONE)
    except Exception:
        return None
    n = len(buf) // 24
    if n == 0:
        return None
    arr = np.frombuffer(buf[: n * 24], dtype=REC)
    day_midnight = int(pd.Timestamp(
        os.path.basename(path).replace(".bi5", "")).timestamp())
    ts = pd.to_datetime(day_midnight + arr["off"].astype(np.int64),
                        unit="s", utc=True)
    df = pd.DataFrame({"open": arr["o"].astype(np.float64),
                       "close": arr["c"].astype(np.float64),
                       "low": arr["l"].astype(np.float64),
                       "high": arr["h"].astype(np.float64),
                       "volume": arr["v"].astype(np.float64)}, index=ts)
    return df[df["open"].gt(0) & df["close"].gt(0) &
              df["low"].gt(0) & df["high"].gt(0)]


def detect_scale(frames, sym):
    med = np.median(np.concatenate([f["close"].to_numpy() for f in frames[:400]]))
    lo, hi = PLAUSIBLE.get(sym, (1e-4, 1e6))
    for scale in (1e5, 1e4, 1e3, 1e2, 1e1, 1.0):
        v = med / scale
        if lo <= v <= hi:
            return scale
    raise ValueError(f"cannot detect price scale for {sym}: raw median {med}")


def build_symbol(sym):
    files = sorted(glob.glob(os.path.join(RAW_DIR, sym, "*", "*.bi5")))
    if not files:
        print(f"{sym}: NO FILES")
        return None
    frames = []
    for p in files:
        df = parse_day(p)
        if df is not None and len(df):
            frames.append(df)
    if not frames:
        print(f"{sym}: no parsable files")
        return None
    scale = detect_scale(frames, sym)
    m1 = pd.concat(frames).sort_index()
    m1 = m1[~m1.index.duplicated(keep="first")]
    for col in ("open", "high", "low", "close"):
        m1[col] = m1[col] / scale

    agg = pd.DataFrame({
        "open": m1["open"].resample("5min", label="left", closed="left").first(),
        "high": m1["high"].resample("5min", label="left", closed="left").max(),
        "low": m1["low"].resample("5min", label="left", closed="left").min(),
        "close": m1["close"].resample("5min", label="left", closed="left").last(),
        "volume": m1["volume"].resample("5min", label="left", closed="left").sum(),
    })
    agg = agg.dropna(subset=["open", "high", "low", "close"])
    agg["n"] = m1["volume"].resample("5min", label="left", closed="left").count()
    agg = agg[agg["n"] >= 3]     # drop thin edge bars (real bars, not fabricated)
    bad = int(((agg["high"] < agg[["open", "close"]].max(axis=1) - 1e-9) |
               (agg["low"] > agg[["open", "close"]].min(axis=1) + 1e-9)).sum())
    os.makedirs(OUT_DIR, exist_ok=True)
    out = os.path.join(OUT_DIR, f"{sym}_5m.parquet")
    agg.to_parquet(out)
    print(f"{sym}: scale=1/{scale:.0f} files={len(files)} rows_5m={len(agg)} "
          f"first={agg.index[0]} last={agg.index[-1]} bad_ohlc={bad}")
    return agg


if __name__ == "__main__":
    import sys
    syms = sys.argv[1:] or ["EURUSD", "GBPUSD", "USDJPY", "USA500IDXUSD",
                            "USATECHIDXUSD"]
    for s in syms:
        build_symbol(s)
