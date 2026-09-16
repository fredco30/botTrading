#!/usr/bin/env python3
"""Wave 2: broad neighbors of the two live screen families only (CN-I
dispersion-expansion continuation; CN-A/CN-F long-horizon strength trend).
Dead families (B,C,D,E,G,H,J) are NOT probed further (mission 12: kill
dead families). All parameters broad / coarse neighbors (mission 13).
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


def disp_cont(g4, zS, pct_thr, hold, zfilter=None):
    """I-family continuation: dispersion-percentile crossing trigger, trend
    exit. Optional zfilter: require |z| extreme confirmation >= value."""
    S = g4.strength(6)
    disp = S.std(axis=1, ddof=1)
    pct = disp.rolling(180, min_periods=180).apply(
        lambda a: (a <= a[-1]).mean(), raw=True)
    pv = pct.to_numpy()
    up = np.isfinite(pv) & (pv >= pct_thr)
    cross = up & ~np.roll(up, 1); cross[0] = False
    if zfilter is not None:
        fin, zmax, zmin, _, _ = R.strength_extremes(g4, zS)
        cross = cross & (zmax >= zfilter) & (zmin <= -zfilter)
    return R.run_strength_family(g4, zS, cross)


def main():
    t0 = time.time()
    g4 = N.grid("H4")
    gH1 = N.grid("H1")
    z4 = {n: g4.zstrength(n, 180) for n in (6, 12, 18, 24, 48)}
    print(f"grids ready ({time.time()-t0:.0f}s)", flush=True)

    # CN-I neighbors (trend continuation of the extreme pair in
    # dispersion-expansion regime)
    for pct_thr, n, hold in ((0.7, 6, 48), (0.9, 6, 48), (0.8, 12, 48),
                             (0.8, 6, 24)):
        tr = disp_cont(g4, z4[n], pct_thr, hold)
        m, _ = log_metrics("CN-I", f"disp_hi_cont pct={pct_thr} n={n*4}h "
                                   f"hold={hold}h",
                           {"pct": pct_thr, "lookback_h": n * 4,
                            "max_hold_h": hold}, tr)
    # CN-I + strength-extreme confirmation
    tr = disp_cont(g4, z4[6], 0.8, 48, zfilter=0.75)
    log_metrics("CN-I", "disp_hi_cont+extreme z>=0.75",
                {"pct": 0.8, "lookback_h": 24, "z_thr": 0.75}, tr)
    # CN-I on H1 grid (faster reaction to the same regime trigger)
    zH1 = gH1.zstrength(6, 180)
    S1 = gH1.strength(6)
    disp1 = S1.std(axis=1, ddof=1)
    pct1 = disp1.rolling(180, min_periods=180).apply(
        lambda a: (a <= a[-1]).mean(), raw=True)
    pv1 = pct1.to_numpy()
    up1 = np.isfinite(pv1) & (pv1 >= 0.8)
    cross1 = up1 & ~np.roll(up1, 1); cross1[0] = False
    tr = R.run_strength_family(gH1, zH1, cross1)
    log_metrics("CN-I", "disp_hi_cont H1 n=6h",
                {"pct": 0.8, "lookback_h": 6, "tf": "H1"}, tr)

    # CN-A longer lookbacks (screen showed monotone improvement with n)
    fin, zmax, zmin, _, _ = R.strength_extremes(g4, z4[18])
    tr = R.run_strength_family(g4, z4[18], (zmax >= 1.0) & (zmin <= -1.0))
    log_metrics("CN-A", "cont n=72h thr=1.0",
                {"lookback_h": 72, "z_thr": 1.0}, tr)
    fin, zmax, zmin, _, _ = R.strength_extremes(g4, z4[24])
    tr = R.run_strength_family(g4, z4[24], (zmax >= 1.0) & (zmin <= -1.0))
    log_metrics("CN-A", "cont n=96h thr=1.0",
                {"lookback_h": 96, "z_thr": 1.0}, tr)
    # CN-F longer lookbacks (same monotone pattern)
    tr = R.run_strength_family(g4, z4[48], np.ones(len(g4.t), bool))
    log_metrics("CN-F", "rank n=192h", {"lookback_h": 192}, tr)
    # CN-A H1 decisions at the best H4 horizon
    zA1 = gH1.zstrength(48, 360)
    fin1, zmax1, zmin1, _, _ = R.strength_extremes(gH1, zA1)
    tr = R.run_strength_family(gH1, zA1, (zmax1 >= 1.0) & (zmin1 <= -1.0))
    log_metrics("CN-A", "cont H1 n=48h thr=1.0",
                {"lookback_h": 48, "z_thr": 1.0, "tf": "H1"}, tr)

    print(f"wave2 done {time.time()-t0:.0f}s, "
          f"experiments used: {N.experiments_used()}")


if __name__ == "__main__":
    main()
