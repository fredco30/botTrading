#!/usr/bin/env python3
"""FAMILY G/H SCREEN — prior-day high/low breakout vs rejection.

Mechanism hypothesis (protocol section 28-G/H): daily liquidity clustering
at prior-day extremes produces continuation (G: break of PDH -> long, PDL
-> short) or rejection (H: touch PDH + close back inside -> short, touch
PDL + close back inside -> long) forward drift beyond baseline on modern FX.

Pre-registered screen:
  prior day      previous COMPLETED UTC calendar day with H1 data
  break event    first H1 bar of the day with high > PDH (or low < PDL),
                 decided at that bar's close; one event per level per day
  reject event   first H1 bar of the day with high >= PDH and close < PDH
                 (or low <= PDL and close > PDL) AND no close-through of
                 that level earlier in the day
  forward        +4h / +8h / +24h H1 drift in event direction, pips
  baseline       unconditional drift, same horizons, all H1 bars
  gates          event-minus-baseline > round-trip cost; year-stable
"""
import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import tmlab as T

HORIZONS = {"4h": 4, "8h": 8, "24h": 24}
START, END = "2020-01-01", "2025-12-31 23:59"


def screen(sym: str) -> dict:
    df5 = T.load_5m(sym, START, END)
    h1 = T.resample_ohlcv(df5, "1h")
    o = h1["open"].to_numpy(); h = h1["high"].to_numpy()
    l = h1["low"].to_numpy(); c = h1["close"].to_numpy()
    idx = h1.index
    pip = T.PIP[sym]
    n = len(c)
    day = np.array([ts.date() for ts in idx])

    # prior-day extremes per bar (causal: value of previous completed day)
    pdh = np.full(n, np.nan); pdl = np.full(n, np.nan)
    dates = sorted(set(day))
    prev_ext = None
    for d in dates:
        mask_today = day == d
        first = np.nonzero(mask_today)[0][0]
        if prev_ext is not None:
            pdh[mask_today] = prev_ext[0]
            pdl[mask_today] = prev_ext[1]
        m = day == d
        prev_ext = (np.max(h[m]), np.min(l[m]))

    yrs = np.array([ts.year for ts in idx])
    fwd = {}
    for lab, hz in HORIZONS.items():
        r = np.full(n, np.nan)
        jj = np.arange(n - hz)
        r[jj] = np.log(c[jj + hz] / c[jj]) * c[jj] / pip
        fwd[lab] = r
        fwd[lab + "_base"] = float(np.nanmean(r))

    events = {"break_pdh": [], "break_pdl": [], "reject_pdh": [], "reject_pdl": []}
    for d in dates:
        m = day == d
        ii = np.nonzero(m)[0]
        if len(ii) < 4:
            continue
        H_, L_ = pdh[ii[0]], pdl[ii[0]]
        if not (np.isfinite(H_) and np.isfinite(L_)):
            continue
        f_pdh = f_pdl = r_pdh = r_pdl = False
        for i in ii:
            if not f_pdh and h[i] > H_:
                events["break_pdh"].append(i); f_pdh = True
            if not f_pdl and l[i] < L_:
                events["break_pdl"].append(i); f_pdl = True
            if not r_pdh and not f_pdh and h[i] >= H_ and c[i] < H_:
                events["reject_pdh"].append(i); r_pdh = True
            if not r_pdl and not f_pdl and l[i] <= L_ and c[i] > L_:
                events["reject_pdl"].append(i); r_pdl = True
            if f_pdh and f_pdl and r_pdh and r_pdl:
                break

    out = {"baseline": {lab: fwd[lab + "_base"] for lab in HORIZONS}}
    signs = {"break_pdh": +1, "break_pdl": -1, "reject_pdh": -1, "reject_pdl": +1}
    for ev, ii in events.items():
        ii = np.array(ii, "int64")
        s = signs[ev]
        res = {"n": int(len(ii))}
        yidx = yrs[ii]
        for lab, hz in HORIZONS.items():
            r = fwd[lab][ii] * s
            if len(r) == 0 or not np.isfinite(r).any():
                continue
            v = r[np.isfinite(r)]
            res[lab] = {"mean": float(np.mean(v)), "win": float(np.mean(v > 0)),
                        "n": int(len(v)),
                        "by_year": {str(y): float(np.nanmean(r[yidx == y]))
                                    for y in range(2020, 2026)
                                    if np.isfinite(r[yidx == y]).any()}}
        out[ev] = res
    return out


def main():
    all_res = {sym: screen(sym) for sym in T.PAIRS}
    for sym, res in all_res.items():
        print(f"\n=== {sym} ===  baselines: " +
              " ".join(f"{k}:{v:+.2f}" for k, v in res["baseline"].items()))
        for ev in ("break_pdh", "break_pdl", "reject_pdh", "reject_pdl"):
            r = res[ev]
            line = f"  {ev:11} n={r['n']:>5}"
            for lab in HORIZONS:
                if lab in r:
                    st = r[lab]
                    line += f" | {lab}: {st['mean']:+6.2f} win={st['win']:.3f}"
            print(line)
            for lab in HORIZONS:
                if lab in r:
                    by = r[lab]["by_year"]
                    print(f"        {lab} by-year: " +
                          " ".join(f"{y}:{v:+.1f}" for y, v in sorted(by.items())))
    with open(os.path.join(HERE, "PDH_PDL_RESULTS.json"), "w") as f:
        json.dump(all_res, f, indent=1, default=float)
    print("\nsaved PDH_PDL_RESULTS.json")


if __name__ == "__main__":
    main()
