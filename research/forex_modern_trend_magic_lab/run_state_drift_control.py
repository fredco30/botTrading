#!/usr/bin/env python3
"""CONTROL for B0: unconditional vs in-state 24h-holding drift on H1 bars.

Decides whether USDJPY's bull-state drift is Trend Magic information or just
the 2020-2025 carry uptrend (if ALL ~= bull, the filter adds nothing).
"""
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import tmlab as T

HZ = 24  # bars (H1)

for sym in T.PAIRS:
    df5 = T.load_5m(sym, "2020-01-01", "2025-12-31 23:59")
    h1 = T.resample_ohlcv(df5, "1h")
    c = h1["close"].to_numpy()
    mt, d, _, _ = T.trend_magic(h1["high"].to_numpy(), h1["low"].to_numpy(), c)
    pip = T.PIP[sym]
    yrs = np.array([ts.year for ts in h1.index])

    j = np.arange(len(c) - HZ)
    rh = np.log(c[j + HZ] / c[j])          # log-return over next 24 bars
    state = d[j]
    for label, mask in (("ALL", np.ones(len(j), bool)),
                        ("bull", state == 1), ("bear", state == -1)):
        pips = rh[mask] * c[j][mask] / pip
        yidx = yrs[j][mask]
        by = " ".join(f"{y}:{np.mean(pips[yidx == y]):+.1f}"
                      for y in range(2020, 2026))
        print(f"{sym} 24h {label:4} n={mask.sum():>6} "
              f"mean={np.mean(pips):+.2f} pips/day | {by}")
