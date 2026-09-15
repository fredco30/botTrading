#!/usr/bin/env python3
"""Cheap gross screens (mid-price, completed bars, 2010-2017) for all M3
families. One ledger row per configuration. Deepen bar (mission 8/12):
pooled gross >= +3 pips/trade, >= 5/8 positive years, sane N."""
import numpy as np

import m3lib as L
import families_m3 as F

H_M15 = (8, 16, 32, 64)
H_H4 = (6, 12, 18, 24)

CONFIGS = [
    ("F01", "f01a", F.f01_band_fade(False, 2.0, 50), H_H4),
    ("F01", "f01b", F.f01_band_fade(True, 2.0, 50), H_H4),
    ("F01", "f01c", F.f01_band_fade(False, 2.5, 50), H_H4),
    ("F02", "f02a", F.f02_donchian(30), H_H4),
    ("F02", "f02b", F.f02_donchian(60), H_H4),
    ("F03", "f03a", F.f03_london_break(False, 0), H_M15),
    ("F03", "f03b", F.f03_london_break(True, 0), H_M15),
    ("F03", "f03c", F.f03_london_break(False, 15), H_M15),
    ("F04", "f04a", F.f04_prev_day("break"), H_M15),
    ("F04", "f04b", F.f04_prev_day("fade"), H_M15),
    ("F05", "f05a", F.f05_failed_break(30, 3), H_M15),
    ("F05", "f05b", F.f05_failed_break(30, 6), H_M15),
    ("F06", "f06a", F.f06_trend_pullback(), H_M15),
    ("F07", "f07a", F.f07_squeeze_break(0.75), H_M15),
    ("F08", "f08a", F.f08_asia_transfer("continuation", 10), H_M15),
    ("F08", "f08b", F.f08_asia_transfer("reversal", 10), H_M15),
    ("F09", "f09a", F.f09_accel_thrust(), H_M15),
    ("F10", "f10a", F.f10_prev_week("break"), H_M15),
    ("F10", "f10b", F.f10_prev_week("fade"), H_M15),
]


def side_split(bars, side, horizons, tf):
    out = {}
    for s, name in ((1, "L"), (-1, "S")):
        arr = side.copy()
        arr[side != s] = 0
        res = L.screen_year(L.sig_bars(bars, tf), arr, horizons)
        out[name] = {h: np.asarray(res[h]) for h in horizons}
    return out


def main():
    cache = {}
    for fam, cname, fn, horizons in CONFIGS:
        key = fn.signal_tf
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
            L.log(fam, fn.desc, "SCREEN_ONLY",
                  f"{cname} h={best_h}", N=0, status="SCREEN",
                  reason="no signals")
            continue
        L.log(fam, fn.desc, "SCREEN_ONLY",
              f"{cname} h={best_h} pooled_gross_pips={best:.2f} posYR={posYR}/8",
              N=len(pool), mean_pips=float(pool.mean()),
              status="SCREEN_PASS" if (best >= 3.0 and posYR >= 5
                                       and len(pool) >= 250) else "SCREEN",
              reason=f"best horizon {best_h} of {horizons}")
        # side split at best horizon printed for mechanism sanity
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


if __name__ == "__main__":
    main()
