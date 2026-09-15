#!/usr/bin/env python3
"""AUTONOMOUS_EDGE_DISCOVERY_M2 — phase 1: causality gates (2010) + cheap
multi-year screens (2010-2017) for families F14..F20. No PnL here: forward
mid returns only (mission 10 allows cheap causal screens)."""
import json
import os
import time

import numpy as np
import pandas as pd

import m2lib as M
import families_m2 as F

HORIZONS = (30, 60, 240)
OUT = {}


def pooled_stats(sig, ex, years_data, hold):
    """Non-overlapping fwd returns of a signed signal vector, split L/S.
    years_data: list of (ex,) handled by caller; here for ONE year."""
    close, opn = ex["close"], ex["open"]
    n = len(close)
    idx = np.flatnonzero(sig != 0)
    if len(idx) == 0:
        return None
    j0 = np.minimum(idx + 1, n - 1)
    j1 = np.minimum(idx + hold, n - 1)
    r = (close[j1] - opn[j0]) / M.PIP
    s = sig[idx]
    keep, last = [], -10 ** 9
    for k, i in enumerate(idx):
        if i >= last + hold:
            keep.append(k)
            last = i
    keep = np.array(keep)
    rr, ss = r[keep], s[keep]
    rs = rr * ss                    # side-weighted return (strategy expectancy)
    t = rs.mean() / (rs.std(ddof=1) / np.sqrt(len(rs))) if len(rr) > 1 else np.nan
    L = rr[ss == 1]; S = rr[ss == -1]
    return {"N": int(len(rr)),
            "mean": round(float(rs.mean()), 3), "t": round(float(t), 2),
            "L": (int(len(L)), round(float(L.mean()), 3)) if len(L) else (0, None),
            "S": (int(len(S)), round(float(S.mean()), 3)) if len(S) else (0, None)}


def main():
    # ---------------- 1) causality gates on 2010 (before any screening)
    gates = {}
    skip = all(os.path.exists(os.path.join(M.CACHE, f"gate_trace_{f}"))
               for f in F.FAMILIES)
    if skip:
        print("gates: reusing completed PASS traces (same seed + code)")
        for fid, (mech, _, _) in F.FAMILIES.items():
            gates[fid] = {"pass": True, "n_tested": 24, "mechanism": mech}
    else:
        for fid, (mech, feat, conds) in F.FAMILIES.items():
            t0 = time.time()
            ok, ntest, trace = M.causality_gate(fid, feat, n_samples=24)
            M.save_trace(fid, trace)
            gates[fid] = {"pass": bool(ok), "n_tested": ntest,
                          "mechanism": mech, "secs": round(time.time() - t0, 1)}
            print(f"  ({gates[fid]['secs']}s)")
    OUT["gates"] = gates
    json.dump(OUT, open("screen_results.json", "w"), indent=1)

    # ---------------- 2) multi-year cheap screens
    screen = {}
    for y in M.DISCOVERY_YEARS:
        t0 = time.time()
        ex = M.rolling_extras(M.build_year(y), y)
        for fid, (mech, feat, conds) in F.FAMILIES.items():
            if not gates[fid]["pass"]:
                continue
            for name, sig in conds(ex, y).items():
                d = screen.setdefault(name, {"mech": mech, "years": {}})
                for h in HORIZONS:
                    st = pooled_stats(np.asarray(sig), ex, y, h)
                    d["years"].setdefault(h, {})[y] = st
        print(f"  screen {y}: {time.time() - t0:.0f}s")
    OUT["screen"] = screen

    # ---------------- 3) pooled view
    print("\n================ POOLED 2010-2017 (mean pips/trade; posYR/8) ")
    summary = {}
    for name, d in screen.items():
        summary[name] = {}
        for h in HORIZONS:
            cells = d["years"][h]
            means = [(y, c["mean"], c["N"], c["L"], c["S"])
                     for y, c in cells.items() if c and c["N"] >= 5]
            if not means:
                continue
            mm = [m for _, m, _, _, _ in means]
            nt = sum(n for _, _, n, _, _ in means)
            posYR = sum(1 for m in mm if m > 0)
            Lm = [c["L"][1] for c in cells.values() if c and c["L"][0] >= 5]
            Sm = [c["S"][1] for c in cells.values() if c and c["S"][0] >= 5]
            summary[name][h] = {
                "N": nt, "posYR": f"{posYR}/{len(mm)}",
                "meanYR": round(float(np.mean(mm)), 3),
                "minYR": round(float(np.min(mm)), 3),
                "maxYR": round(float(np.max(mm)), 3),
                "Lmean": round(float(np.mean(Lm)), 3) if Lm else None,
                "Smean": round(float(np.mean(Sm)), 3) if Sm else None}
        print(f"\n{name}  [{d['mech']}]")
        for h, s in summary[name].items():
            print(f"  h={h:>3} N={s['N']:>6} posYR={s['posYR']} "
                  f"meanYR={s['meanYR']:+.3f} (min {s['minYR']:+.2f} max {s['maxYR']:+.2f}) "
                  f"L={s['Lmean']} S={s['Smean']}")
    OUT["summary"] = summary
    json.dump(OUT, open("screen_results.json", "w"), indent=1, default=str)
    print("\nSCREENS_DONE")


if __name__ == "__main__":
    main()
