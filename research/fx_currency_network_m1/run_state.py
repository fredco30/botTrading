#!/usr/bin/env python3
"""Wave 3: CN-I state-based trigger variants (pre-registered BEFORE seeing
their PnL, to fix E035's only failing gate: trigger frequency).

Mechanism reading: dispersion-expansion is a REGIME, not an event. E035
fired only on the crossing into the top quintile (1.86 trades/wk). State
variant: while the cross-sectional dispersion percentile is in the top
quintile, the extreme strongest-vs-weakest pair position is kept working
(occupancy one-per-pair, trend exit architecture unchanged: 2xATR stop,
3xATR chandelier trail, strength-differential sign flip exit, 48h cap).
Hysteresis variant: re-entry additionally requires having seen the
percentile fall back below 0.7 since the last regime entry (anti-churn).
DISCOVERY fold evaluation only."""
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import numpy as np
import pandas as pd

import netlib as N
import importlib.util
_spec = importlib.util.spec_from_file_location(
    "cn_screens", os.path.join(HERE, "run_screens.py"))
R = importlib.util.module_from_spec(_spec)
sys.modules["cn_screens"] = R
_spec.loader.exec_module(R)

CUT_D = int(pd.Timestamp(N.FOLDS["DISCOVERY"][1], tz="UTC").value)


def log_metrics(fam, mech, params, trades):
    ft = [t for t in trades if t["entry_ts"] < CUT_D]
    m = N.SW.pooled_metrics(ft, fam + "." + mech)
    tpw = round(m.get("N", 0) / N.weeks("DISCOVERY"), 2) if m.get("N") else 0.0
    gate = N.discovery_gate(m)
    N.log(fam, mech, params, m, tpw, None,
          "DISCOVERY_PASS" if gate else "DISCOVERY_FAIL")
    return m, ft


def disp_pct(g, n, win=180):
    S = g.strength(n)
    disp = S.std(axis=1, ddof=1)
    return disp.rolling(win, min_periods=win).apply(
        lambda a: (a <= a[-1]).mean(), raw=True)


def run_state(g, zS, pv, hi, hold, lo=None):
    """State entry: pv >= hi (optional hysteresis: must have seen pv < lo
    since last entry). Trend exit architecture (E035's), unchanged."""
    fin, zmax, zmin, amax, amin = R.strength_extremes(g, zS)
    active = np.isfinite(pv) & (pv >= hi)
    if lo is not None:
        below = np.isfinite(pv) & (pv < lo)
        armed = np.zeros(len(pv), bool)
        ok = False
        for i in range(len(pv)):
            if below[i]:
                ok = True
            elif active[i]:
                if ok:
                    armed[i] = True
                ok = False
        active = armed
    blocks = {}
    for i in np.flatnonzero(active & fin):
        c1, c2 = N.CURR[amax[i]], N.CURR[amin[i]]
        p = R.pair_for(c1, c2)
        if p is None:
            continue
        s = 1 if N.BASE[p] == c1 else -1
        a = float(g.atr_of(p, np.array([g.t[i]]))[0])
        blocks.setdefault(p, []).append(
            {"ts": [g.t[i]], "side": [s], "stop_pips": [2.0 * a],
             "atr_pips": [a]})
    trades = []
    for p, c in R.merge_cands(blocks).items():
        diff = (zS[N.BASE[p]] - zS[N.QUOTE[p]]).to_numpy()
        tr = N.replay(p, g.tf, c, 2.0, 3.0, g.t, diff,
                      lambda s, v: (s == 1 and v < 0) or (s == -1 and v > 0),
                      hold, "SIGNAL_EXIT")
        trades += tr
    return trades


def main():
    t0 = time.time()
    g4 = N.grid("H4")
    z12 = g4.zstrength(12, 180)
    pv12 = disp_pct(g4, 12).to_numpy()
    print(f"grid ready ({time.time()-t0:.0f}s)", flush=True)
    # state, top quintile
    tr = run_state(g4, z12, pv12, 0.8, 48)
    log_metrics("CN-I", "disp_hi_STATE pct>=0.8 n=48h hold=48h",
                {"pct": 0.8, "lookback_h": 48, "max_hold_h": 48}, tr)
    # state with hysteresis (re-arm below 0.7)
    tr = run_state(g4, z12, pv12, 0.8, 48, lo=0.7)
    log_metrics("CN-I", "disp_hi_STATE hyst 0.8/0.7 n=48h hold=48h",
                {"pct": 0.8, "lo": 0.7, "lookback_h": 48,
                 "max_hold_h": 48}, tr)
    # state, top 30 percent (frequency/quality curve, coarse)
    tr = run_state(g4, z12, pv12, 0.7, 48)
    log_metrics("CN-I", "disp_hi_STATE pct>=0.7 n=48h hold=48h",
                {"pct": 0.7, "lookback_h": 48, "max_hold_h": 48}, tr)
    print(f"wave3 done {time.time()-t0:.0f}s, "
          f"experiments used: {N.experiments_used()}")


if __name__ == "__main__":
    main()
