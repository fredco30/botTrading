#!/usr/bin/env python3
"""FX_PDH_001 — pre-registered plateau pass (frozen spec, section 24/30).

Cells: stop_mult in {0.75, 1.0(default), 1.5} x trail_mult {2.25, 3.0(def), 4.5}
       plus hold_mult {24, 72} at default stop/trail.
Original default (1.0/3.0/48) remains the PRIMARY reference; the pass
tests whether performance sits on a broad plateau or on a spike.
"""
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import tmlab as T
from run_pdh_backtest import backtest, gates

df5 = T.load_5m("USDJPY", "2020-01-01", "2025-12-31 23:59")
h1 = T.resample_ohlcv(df5, "1h")

cells = [(sm, tm, 48) for sm in (0.75, 1.0, 1.5) for tm in (2.25, 3.0, 4.5)
         if not (sm == 1.0 and tm == 3.0)]
cells += [(0.75, 4.5, 48)]            # diagonal neighbour
cells += [(1.0, 3.0, 24), (1.0, 3.0, 72), (1.0, 3.0, 48)]   # hold neighbours + default

print(f"{'cell (stop/trail/hold)':>22} {'PF':>5} {'mean':>6} {'win':>5} {'t':>5} "
      f"{'rb1':>5}  {'2020':>6} {'2021':>6} {'2022':>6} {'2023':>6} {'2024':>6} {'2025':>6}  stress_mean")
for sm, tm, hold in cells:
    res = {}
    for label, slip in (("N", 0.0), ("S", T.SLIP_STRESS_PIPS)):
        tdf = backtest(h1, stop_mult=sm, trail_mult=tm, max_hold=hold, slip=slip)
        res[label] = gates(tdf, label)
    g, s = res["N"], res["S"]
    tag = " <- DEFAULT" if (sm, tm, hold) == (1.0, 3.0, 48) else ""
    by = g["by_year"]
    print(f"{sm:>7}/{tm:<5}/{hold:<4} {g['pf']:>5.2f} {g['mean_net_pips']:>+6.2f} "
          f"{g['win']:>5.3f} {g['t']:>+5.2f} {g['rb1_net']:>+5.2f}  " +
          " ".join(f"{by.get(y, 0):+6.1f}" for y in range(2020, 2026)) +
          f"  {s['mean_net_pips']:+.2f}{tag}")
