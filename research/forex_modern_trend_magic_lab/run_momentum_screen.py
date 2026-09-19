#!/usr/bin/env python3
"""FAMILY J SCREEN — time-series momentum vs unconditional baseline.

Mechanism hypothesis (protocol section 28-J/A): trailing momentum predicts
forward drift beyond the unconditional baseline, on modern 2020-2025 FX.

Design (pre-registered):
  momentum    trailing log-return of H1 closes over L bars
              L in {24 (1d), 72 (3d), 168 (1w)}
  buckets     terciles of the momentum distribution (per pair x L),
              computed causally over the full sample (weak assumption —
              screens only; a live variant would use trailing quantiles)
  forward     next-24h log drift (H1 bars), in pips, LONG when momentum
              tercile is top, SHORT when bottom (sign applied)
  baseline    unconditional 24h drift, same bars
  report      per bucket: n, mean, win, by-year; monotonicity; spread of
              top-minus-baseline vs round-trip cost
"""
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import tmlab as T

HZ = 24
LOOKBACKS = (24, 72, 168)
START, END = "2020-01-01", "2025-12-31 23:59"

for sym in T.PAIRS:
    df5 = T.load_5m(sym, START, END)
    h1 = T.resample_ohlcv(df5, "1h")
    c = h1["close"].to_numpy()
    pip = T.PIP[sym]
    yrs = np.array([ts.year for ts in h1.index])
    j = np.arange(HZ, len(c) - HZ)          # momentum window + forward window
    fwd = np.log(c[j + HZ] / c[j]) * c[j] / pip
    base = float(np.mean(fwd))
    base_by = {y: float(np.mean(fwd[yrs[j] == y])) for y in range(2020, 2026)}
    print(f"\n=== {sym}  24h baseline drift {base:+.2f} pips/day "
          f"(by year: " + " ".join(f"{y}:{v:+.1f}" for y, v in base_by.items()) + ")")
    for L in LOOKBACKS:
        mom = np.log(c / np.roll(c, L))
        m = mom[j]                           # trailing L-bar momentum
        q1, q2 = np.quantile(m, [1 / 3, 2 / 3])
        rows = []
        for name, mask in (("bot(short)", m <= q1), ("mid(hold)", (m > q1) & (m < q2)),
                           ("top(long)", m >= q2)):
            r = fwd[mask] * (1 if mask is not m else 1)
            sign = -1.0 if name.startswith("bot") else 1.0
            r = fwd[mask] * sign
            yidx = yrs[j][mask]
            by = " ".join(f"{y}:{np.mean(r[yidx == y]):+5.1f}" for y in range(2020, 2026))
            rows.append((name, int(mask.sum()), float(np.mean(r)),
                         float(np.mean(r > 0)), by))
        print(f"  L={L:>3}: " + "  ".join(
            f"{nm} n={n:>6} {mu:+6.2f} win={w:.3f}" for nm, n, mu, w, _ in rows))
        for nm, n, mu, w, by in rows[:1] + rows[2:]:
            print(f"           {nm:10} by-year: {by}")
        spread = rows[2][2] + rows[0][2]      # long-top + short-bottom (net drift capture)
        print(f"           top-long + bot-short capture = {spread:+.2f} pips/day "
              f"vs baseline {base:+.2f} -> marginal {spread - base:+.2f}")
