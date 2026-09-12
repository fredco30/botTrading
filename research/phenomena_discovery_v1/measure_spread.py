#!/usr/bin/env python3
"""Measure Dukascopy BID/ASK spread on a sample of days to calibrate the
SYNTHETIC cost scenarios for USA500IDXUSD (index points, round trip).

Downloads a small stratified sample of ASK daily candle files (BID already
on disk), aligns minute closes, and reports spread distribution per year.
Purely for cost-model documentation; not used for any signal.
"""
import lzma
import os
import random
import struct
import urllib.request

import numpy as np
import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
RAW = os.path.join(ROOT, "data_raw")
BASE = "https://datafeed.dukascopy.com/datafeed/{sym}/{y}/{m:02d}/{d:02d}/ASK_candles_min_1.bi5"
UA = {"User-Agent": "Mozilla/5.0 (research-data-download)"}
CANDLE = np.dtype([("off", ">i4"), ("o", ">i4"), ("c", ">i4"),
                   ("l", ">i4"), ("h", ">i4"), ("v", ">f4")])


def parse_day(raw, y, m, d, scale=1e5):
    buf = lzma.decompress(raw, format=lzma.FORMAT_ALONE)
    n = len(buf) // 24
    arr = np.frombuffer(buf[: n * 24], dtype=CANDLE)
    off = arr["off"].astype(np.int64)
    close = arr["c"].astype(np.float64) / scale
    ts = pd.to_datetime(
        int(pd.Timestamp(f"{y:04d}-{m:02d}-{d:02d}").timestamp()) + off,
        unit="s", utc=True)
    return pd.Series(close, index=ts)


def sample_spread(sym, n_days=8):
    bid_root = os.path.join(RAW, sym)
    years = sorted(os.listdir(bid_root))
    per_year = {}
    rng = random.Random(7)
    for y in years:
        files = [os.path.join(bid_root, y, f) for f in os.listdir(os.path.join(bid_root, y))]
        for f in rng.sample(files, min(n_days, len(files))):
            name = os.path.basename(f).replace(".bi5", "")
            dt = pd.Timestamp(name)
            url = BASE.format(sym=sym, y=dt.year, m=dt.month - 1, d=dt.day)
            try:
                req = urllib.request.Request(url, headers=UA)
                with urllib.request.urlopen(req, timeout=40) as r:
                    raw = r.read()
                ask = parse_day(raw, dt.year, dt.month, dt.day)
                bid = parse_day(open(f, "rb").read(), dt.year, dt.month, dt.day)
                j = pd.concat([bid.rename("bid"), ask.rename("ask")], axis=1).dropna()
                if len(j) < 100:
                    continue
                sp = (j["ask"] - j["bid"])
                sp = sp[(sp > 0) & (sp < 50)]  # sanity
                per_year.setdefault(y, []).append(sp.median())
            except Exception:
                continue
    rows = {y: float(np.median(v)) for y, v in sorted(per_year.items()) if v}
    allv = np.array([x for v in per_year.values() for x in v])
    return rows, (float(np.median(allv)), float(np.percentile(allv, 75))) if len(allv) else (None, None)


if __name__ == "__main__":
    import sys
    sym = sys.argv[1] if len(sys.argv) > 1 else "USA500IDXUSD"
    per_year, (med, p75) = sample_spread(sym)
    print(f"{sym} median RT-ish spread (1-min close bid/ask diff, index pts):")
    for y, v in per_year.items():
        print(f"  {y}: {v:.3f}")
    print(f"OVERALL median={med} p75={p75}")
