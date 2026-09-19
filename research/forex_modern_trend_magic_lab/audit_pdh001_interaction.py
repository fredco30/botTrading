#!/usr/bin/env python3
"""AUDIT addendum + TASK 3 — Trend Magic interaction test (A/B).

1. Correct 2022-concentration metric (year pips / total pips) for V0 and V1.
2. t-stats for V0/V1.
3. TASK 3: FX_PDH_001 as the base structural entry (independent of Trend
   Magic).  A = frozen entries, no filter.  B = identical entries+exits+
   costs+sizing, but only when the latest CLOSED H1 Trend Magic state at the
   signal bar close is bullish (+1).  Engine: the causally-strict V1 replay
   for BOTH arms (identical rules, only the filter differs).  Also reports
   the frozen-V0 arm for reference.  No optimization, default TM params.
"""
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import tmlab as T
from audit_pdh001 import replay, sig, atr, o, h, l, c, idx, n, yrs  # noqa

PIP = 1e-2
SPREAD = 0.9
CAPITAL, MIN_LOT, STEP = 500.0, 0.01, 0.01

# ---- Trend Magic state on the same H1 series (default params, causal) ----
mt, d, cc, vol = T.trend_magic(h, l, c)
print(f"TM H1 states: bull {np.mean(d==1):.1%}  bear {np.mean(d==-1):.1%}  "
      f"zero {np.mean(d==0):.1%}")

def sig_state(df):
    return d[df["sig_i"].to_numpy().astype(int)]

def report(df, label, baseline_year=None):
    r = df["net_pips"].to_numpy()
    wins = r[r > 0]; losses = r[r <= 0]
    pf = wins.sum() / -losses.sum()
    se = np.std(r, ddof=1) / np.sqrt(len(r))
    k = max(1, int(round(0.01 * len(r))))
    rb1 = np.mean(np.sort(r)[:-k])
    y = yrs[df["entry_i"].to_numpy().astype(int)]
    byy = {int(yy): float(np.mean(r[y == yy])) for yy in sorted(set(y))}
    ysum = {int(yy): float(np.sum(r[y == yy])) for yy in sorted(set(y))}
    tot = float(r.sum())
    c22 = 100 * ysum.get(2022, 0.0) / tot if tot else np.nan
    # equity sim at min-lot-compatible 0.5% sizing (recompute lots per trade)
    ei = df["entry_i"].to_numpy().astype(int)
    eur5 = T.load_5m("EURUSD", "2020-01-01", "2025-12-31 23:59")
    euri = eur5.index; eurc = eur5["close"].to_numpy()
    stop_pips = df["stop_pips"].to_numpy()
    pip_eur = 1000.0 * PIP / c[ei] * eurc[np.searchsorted(euri, idx[ei], side="right") - 1]
    lots = np.maximum(MIN_LOT, np.floor(
        (0.005 * CAPITAL / (stop_pips * pip_eur * 100)) / STEP) * STEP)
    rm = (r / stop_pips) * (stop_pips * pip_eur * (lots / MIN_LOT))
    eq = CAPITAL + np.cumsum(rm)
    peak = np.maximum.accumulate(eq)
    dd = 100 * np.max((peak - eq) / peak)
    print(f"[{label}] n={len(r)} ({len(r)/313.2:.2f}/wk) PF={pf:.3f} "
          f"net/trade={np.mean(r):+.3f} expR={np.mean(r/stop_pips):+.3f} "
          f"win={np.mean(r>0):.3f} t={np.mean(r)/se:+.2f} rb1={rb1:+.3f} "
          f"2022share={c22:.0f}% eq_end={eq[-1]:.0f} maxDD={dd:.1f}%")
    print("   by year: " + " ".join(f"{yy}:{v:+.2f}" for yy, v in byy.items()))

# ---- V0/V1 concentration + t-stats (proper metric) -----------------------
csv = pd.read_csv(os.path.join(HERE, "candidates", "FX_PDH_001",
                               "FX_PDH_001_TRADES.csv"))
for df, lab in ((csv, "V0 frozen CSV"), (replay(strict=True), "V1 strict")):
    r = df["net_pips"].to_numpy()
    y = yrs[df["entry_i"].to_numpy().astype(int)]
    tot = float(r.sum())
    sh22 = 100 * r[y == 2022].sum() / tot
    sh22n = 100 * (y == 2022).mean()
    se = np.std(r, ddof=1) / np.sqrt(len(r))
    print(f"[{lab}] 2022 pips share={sh22:.1f}% (trades share {sh22n:.0f}%) "
          f"t={np.mean(r)/se:+.2f}")

# ---- TASK 3: A/B interaction ---------------------------------------------
A_strict = replay(strict=True).copy()
A_strict["sig_i"] = A_strict["entry_i"].to_numpy().astype(int) - 1
A_strict["stop_pips"] = atr[A_strict["sig_i"].to_numpy().astype(int)] / PIP
B = A_strict[sig_state(A_strict) == 1].copy()

print("\n=== TASK 3 — TREND MAGIC INTERACTION (engine: strict V1 both arms) ===")
report(A_strict, "A: base PDH entries, NO TM filter")
report(B, "B: WITH TM H1 bullish-state filter")

# paired view on A's events: expectancy by TM state at signal
st = sig_state(A_strict)
for name, m_ in (("TM bull (+1)", st == 1), ("TM not-bull (0/-1)", st != 1)):
    sub = A_strict[m_]
    r = sub["net_pips"].to_numpy()
    print(f"  A-events {name:18}: n={len(r)} net/trade={np.mean(r):+.3f} "
          f"win={np.mean(r>0):.3f}")

# frozen V0 arm for reference
A0 = replay(strict=False).copy()
A0["sig_i"] = A0["entry_i"].to_numpy().astype(int) - 1
A0["stop_pips"] = atr[A0["sig_i"].to_numpy().astype(int)] / PIP
report(A0, "A: frozen V0 engine (reference)")
