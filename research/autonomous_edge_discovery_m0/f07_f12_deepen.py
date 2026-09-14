#!/usr/bin/env python3
"""F12 deepen (4h momentum -> trade sim) + F07 plateau grid."""
import numpy as np
import pandas as pd
import aedis_lib as A
import ledger as L

b = A.load_bars("H1")
close, opn, high, low = b["close"], b["open"], b["high"], b["low"]
n = len(close)
P = 1e-4
months = pd.to_datetime(b["start"], utc=True).month

H4NS = 4 * 3600 * int(1e9)
h4 = b["start"] // H4NS
hu4, inv4 = np.unique(h4, return_inverse=True)
hc4 = np.zeros(len(hu4))
for i in range(len(hu4)):
    hc4[i] = close[inv4 == i][-1]
r4 = np.full(len(hu4), np.nan)
r4[4:] = (hc4[4:] - hc4[:-4]) / P
r4now = r4[inv4]


def sim(idx, sgn, stop_p, tp_p, tmax, spread_cost=True):
    tr = A.sim_trades_m1(b, idx, sgn, stop_p, tp_p, tmax)
    return np.array([t["net_pips"] for t in tr]) if tr else np.array([])


def nonoverlap(idx, tmax):
    keep, last = [], -10**9
    for i in idx:
        if i + 1 > last:
            keep.append(i)
            last = i + 1 + tmax
    return np.array(keep, dtype=int)


def report(nm, family, sgn, thr, stop_p, tp_p, tmax, months_break=False):
    ok = np.isfinite(r4now)
    cond = ok & ((r4now > thr) if sgn == 1 else (r4now < -thr))
    idx = nonoverlap(np.flatnonzero(cond), tmax)
    nt = sim(idx, sgn, stop_p, tp_p, tmax)
    if len(nt) == 0:
        L.log(family, "4h momentum", f"{'L' if sgn==1 else 'S'} thr={thr} SL={stop_p} TP={tp_p} T={tmax}",
              0, np.nan, status="NO_TRADES", reason="")
        return
    wins, losses = nt[nt > 0], nt[nt < 0]
    pf = min(float(wins.sum() / abs(losses.sum())), 999.0) if len(losses) and losses.sum() else 999.0
    rb = A.mtf_lib.remove_best_1pct(nt)
    L.log(family, "4h momentum", f"{'L' if sgn==1 else 'S'} thr={thr} SL={stop_p} TP={tp_p} T={tmax}",
          len(nt), nt.mean(), PF=pf, expectancy_R=float(np.mean(nt / stop_p)),
          stress_R=float(nt.mean()) - 1.0, remove_best=rb, status="SIM",
          reason="one-position, real spread")
    print(f"{family} {nm} thr={thr} SL={stop_p} TP={tp_p} T={tmax}: N={len(nt)} "
          f"mean={nt.mean():.2f}p PF={pf:.2f} expR={np.mean(nt/stop_p):.3f} "
          f"stressR={nt.mean()-1:.3f} rb={rb:.2f} WR={(nt>0).mean():.2f}")
    if months_break:
        mon = np.array([months[min(i + 1, n - 1)] for i in idx])
        for mth in range(1, 7):
            sel = nt[mon == mth]
            if len(sel):
                print(f"    2017-{mth:02d} N={len(sel):4d} mean={sel.mean():7.2f}p tot={sel.sum():8.1f}p")


print("=== F12d 4h momentum sim grid")
for sgn, nm in ((1, "LONG"), (-1, "SHORT")):
    for thr in (10, 15):
        for stop_p, tp_p, tmax in ((15, 15, 120), (20, 20, 120), (15, 30, 180), (20, 20, 240)):
            report(nm, "F12d", sgn, thr, stop_p, tp_p, tmax)

print("=== F12d monthly, primary L/S")
report("LONG", "F12d", 1, 10, 15, 15, 120, months_break=True)
report("SHORT", "F12d", -1, 10, 15, 15, 120, months_break=True)

# ---------------- F07 plateau ----------------
print("=== F07d plateau around (k=15,x=4,SL=12,TP=12,T=60)")
h1_start = (b["start"] // (3600 * int(1e9))) * (3600 * int(1e9))
hu, inv = np.unique(h1_start, return_inverse=True)
ho = np.array([opn[inv == i][0] for i in range(len(hu))])
hc = np.array([close[inv == i][-1] for i in range(len(hu))])
ema20 = A.mtf_lib.ema(hc, 20)
trend_h = np.where(hc > ema20, 1, np.where(hc < ema20, -1, 0))
trend = trend_h[inv]
ret15 = np.full(n, np.nan)
ret15[15:] = (close[15:] - close[:-15]) / P
ok = np.isfinite(ret15) & np.isfinite(trend)


def f07(sgn, x, stop_p, tp_p, tmax, kret=None):
    r = ret15 if kret is None else kret
    cond = ok & (trend == sgn) & ((r > x) if sgn == 1 else (r < -x))
    idx = nonoverlap(np.flatnonzero(cond), tmax)
    nt = sim(idx, sgn, stop_p, tp_p, tmax)
    if len(nt) == 0:
        return
    wins, losses = nt[nt > 0], nt[nt < 0]
    pf = min(float(wins.sum() / abs(losses.sum())), 999.0) if len(losses) and losses.sum() else 999.0
    rb = A.mtf_lib.remove_best_1pct(nt)
    nm = "L" if sgn == 1 else "S"
    L.log("F07p", "trend x impulse plateau", f"{nm} x={x} SL={stop_p} TP={tp_p} T={tmax}",
          len(nt), nt.mean(), PF=pf, expectancy_R=float(np.mean(nt / stop_p)),
          stress_R=float(nt.mean()) - 1.0, remove_best=rb, status="SIM", reason="plateau")
    print(f"F07p {nm} x={x} SL={stop_p} TP={tp_p} T={tmax}: N={len(nt)} mean={nt.mean():.2f} "
          f"PF={pf:.2f} expR={np.mean(nt/stop_p):.3f} rb={rb:.2f}")


for x in (3, 4, 5, 6, 8):
    for stop_p, tp_p in ((10, 10), (12, 12), (15, 15), (12, 20), (20, 12)):
        f07(1, x, stop_p, tp_p, 60)
for tmax in (30, 45, 60, 90, 120):
    f07(1, 4, 12, 12, tmax)
