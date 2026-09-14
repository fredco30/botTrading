#!/usr/bin/env python3
"""F07 deepen: H1-trend-aligned M1 impulse -> trade sim with real spread cost,
stop/target/time exits, monthly breakdown, long/short split."""
import numpy as np
import pandas as pd
import aedis_lib as A
import ledger as L

b = A.load_bars("H1")
close, opn, high, low = b["close"], b["open"], b["high"], b["low"]
n = len(close)
P = 1e-4

# H1 mid bars from M1 (completed-bar trend, causal)
h1_start = (b["start"] // (3600 * int(1e9))) * (3600 * int(1e9))
hu, inv = np.unique(h1_start, return_inverse=True)
ho = np.array([opn[inv == i][0] for i in range(len(hu))])
hc = np.array([close[inv == i][-1] for i in range(len(hu))])
ema20 = A.mtf_lib.ema(hc, 20)
trend_h = np.where(hc > ema20, 1, np.where(hc < ema20, -1, 0))
trend = trend_h[inv]

def run(side_sign, k, x, stop_p, tp_p, tmax, lab):
    ret_k = np.full(n, np.nan)
    ret_k[k:] = (close[k:] - close[:-k]) / P
    ok = np.isfinite(ret_k) & np.isfinite(trend)
    cond = ok & (trend == side_sign) & ((ret_k > x) if side_sign == 1 else (ret_k < -x))
    idx = np.flatnonzero(cond)
    # one position at a time: greedy non-overlap on (entry bar, entry+tmax)
    keep, last = [], -10**9
    for i in idx:
        if i + 1 > last:
            keep.append(i)
            last = i + 1 + tmax
    idx = np.array(keep, dtype=int)
    tr = A.sim_trades_m1(b, idx, side_sign, stop_p, tp_p, tmax)
    nt = np.array([t["net_pips"] for t in tr]) if tr else np.array([])
    if len(nt) == 0:
        L.log("F07d", lab, f"k={k} x={x} SL={stop_p} TP={tp_p} T={tmax}", 0,
              np.nan, status="NO_TRADES", reason="")
        return
    wins, losses = nt[nt > 0], nt[nt < 0]
    pf = min(float(wins.sum() / abs(losses.sum())), 999.0) if len(losses) and losses.sum() else 999.0
    expr = float(np.mean(nt / stop_p))  # 1R = stop distance
    stress = float(nt.mean()) - 1.0     # +0.5 pip/side stress
    rb = A.mtf_lib.remove_best_1pct(nt)
    L.log("F07d", lab, f"k={k} x={x} SL={stop_p} TP={tp_p} T={tmax}", len(nt),
          nt.mean(), PF=pf, expectancy_R=expr, stress_R=stress, remove_best=rb,
          status="SIM", reason="one-position, real spread, SL/TP tick-proxy")
    print(f"F07d {lab} k={k} x={x} SL={stop_p} TP={tp_p} T={tmax}: N={len(nt)} "
          f"mean={nt.mean():.2f}p PF={pf:.2f} expR={expr:.3f} stressR={stress:.3f} rb={rb:.2f} "
          f"WR={(nt>0).mean():.2f}")

print("=== F07d grid: time-exit + SL/TP variants, both sides pooled separately")
for k, x in ((15, 4), (15, 6), (30, 4)):
    run(1, k, x, 12, 12, 60, "LONG")
    run(-1, k, x, 12, 12, 60, "SHORT")

# monthly consistency of the primary config (LONG side)
k, x, stop_p, tp_p, tmax = 15, 4, 12, 12, 60
ret_k = np.full(n, np.nan)
ret_k[k:] = (close[k:] - close[:-k]) / P
ok = np.isfinite(ret_k) & np.isfinite(trend)
months = pd.to_datetime(b["start"], utc=True).month
for sgn, nm in ((1, "LONG"), (-1, "SHORT")):
    cond = ok & (trend == sgn) & ((ret_k > x) if sgn == 1 else (ret_k < -x))
    idx = np.flatnonzero(cond)
    keep, last = [], -10**9
    for i in idx:
        if i + 1 > last:
            keep.append(i); last = i + 1 + tmax
    idx = np.array(keep, dtype=int)
    tr = A.sim_trades_m1(b, idx, sgn, stop_p, tp_p, tmax)
    print(f"--- {nm} monthly")
    for mth in range(1, 7):
        tt = [t["net_pips"] for t, i in zip(tr, idx) if months[min(i + 1, n - 1)] == mth]
        if tt:
            tt = np.array(tt)
            print(f"   2017-{mth:02d} N={len(tt):4d} mean={tt.mean():7.2f}p total={tt.sum():8.1f}p")
