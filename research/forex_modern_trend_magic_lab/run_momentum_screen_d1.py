#!/usr/bin/env python3
"""FAMILY J broad pass — multi-week (D1) momentum terciles, same method.

This is the single permitted broad robustness pass for the near-miss L=24
cells before the family verdict (protocol section 30).
"""
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import tmlab as T

HZ = 24                      # 24h forward drift, as before
LOOKBACKS_D = (5, 10, 20)    # days
START, END = "2020-01-01", "2025-12-31 23:59"

for sym in T.PAIRS:
    df5 = T.load_5m(sym, START, END)
    h1 = T.resample_ohlcv(df5, "1h")
    c = h1["close"].to_numpy()
    pip = T.PIP[sym]
    yrs = np.array([ts.year for ts in h1.index])
    j = np.arange(480, len(c) - HZ)
    fwd = np.log(c[j + HZ] / c[j]) * c[j] / pip
    base = float(np.mean(fwd))
    print(f"\n=== {sym} baseline {base:+.2f} pips/day ===")
    for Ld in LOOKBACKS_D:
        L = Ld * 24
        mom = np.log(c / np.roll(c, L))
        m = mom[j]
        q1, q2 = np.quantile(m, [1 / 3, 2 / 3])
        out = []
        for name, sign, mask in (("bot(short)", -1.0, m <= q1),
                                 ("top(long)", +1.0, m >= q2)):
            r = fwd[mask] * sign
            yidx = yrs[j][mask]
            by = " ".join(f"{y}:{np.mean(r[yidx == y]):+5.1f}" for y in range(2020, 2026))
            out.append(f"{name} n={mask.sum():>6} {np.mean(r):+6.2f} win={np.mean(r>0):.3f} | {by}")
        capture = (np.mean(fwd[m >= q2]) - np.mean(fwd[m <= q1]))
        print(f"  D{Ld:>2}: " + "  ".join(out))
        print(f"      top-vs-bot spread {capture:+.2f} pips/day")
