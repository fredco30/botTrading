#!/usr/bin/env python3
"""Screens for F11 (gap) and F12 (break+retest)."""
import numpy as np

import m3lib as L
import families_m3_extra as FX


def side_split(bars, side, horizons, tf):
    out = {}
    for s, name in ((1, "L"), (-1, "S")):
        arr = side.copy()
        arr[side != s] = 0
        res = L.screen_year(L.sig_bars(bars, tf), arr, horizons)
        out[name] = {h: np.asarray(res[h]) for h in horizons}
    return out

CONFIGS = [
    ("F11", "f11a_fade", FX.f11_gap("fade", 10), (8, 16, 32)),
    ("F11", "f11b_fade", FX.f11_gap("fade", 20), (8, 16, 32)),
    ("F11", "f11c_cont", FX.f11_gap("cont", 10), (8, 16, 32)),
    ("F12", "f12a_retest", FX.f12_break_retest(10, 0.25, "retest"), (8, 16, 32, 64)),
    ("F12", "f12b_retest", FX.f12_break_retest(20, 0.25, "retest"), (8, 16, 32, 64)),
    ("F12", "f12c_break", FX.f12_break_retest(10, 0.25, "break"), (8, 16, 32, 64)),
]

for fam, cname, fn, horizons in CONFIGS:
    res = L.screen_years(fn, horizons=horizons)
    best_h, best = None, -1e9
    for h in horizons:
        pool = res[h]["all"]
        m = float(pool.mean()) if len(pool) else np.nan
        if np.isfinite(m) and m > best:
            best, best_h = m, h
    pool = res[best_h]["all"]
    posYR = sum(1 for y in res[best_h]["y"]
                if len(res[best_h]["y"][y]) >= 5
                and res[best_h]["y"][y].mean() > 0)
    if len(pool) == 0:
        L.log(fam, fn.desc, "SCREEN_ONLY", cname, N=0, status="SCREEN",
              reason="no signals")
        continue
    L.log(fam, fn.desc, "SCREEN_ONLY",
          f"{cname} h={best_h} pooled_gross_pips={best:.2f} posYR={posYR}/8",
          N=len(pool), mean_pips=float(pool.mean()),
          status="SCREEN_PASS" if (best >= 3.0 and posYR >= 5
                                   and len(pool) >= 100) else "SCREEN",
          reason=f"best horizon {best_h} of {horizons}")
    agg = {"L": [], "S": []}
    for y in L.DISCOVERY_YEARS:
        bars = L.build_year(y)
        side = fn(bars, y)
        sp = side_split(bars, side, (best_h,), fn.signal_tf)
        for nm in ("L", "S"):
            agg[nm].append(sp[nm][best_h])
    ls = {nm: (float(np.concatenate(v).mean()) if sum(len(x) for x in v)
               else np.nan) for nm, v in agg.items()}
    nn = {nm: sum(len(x) for x in v) for nm, v in agg.items()}
    print(f"    side split: L n={nn['L']} {ls['L']:+.2f}p | "
          f"S n={nn['S']} {ls['S']:+.2f}p")
