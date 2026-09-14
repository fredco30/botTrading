#!/usr/bin/env python3
"""Screens A: directional persistence / session / daily-extremes families.
All conditions causal (computed from data up to the deciding bar close)."""
import numpy as np
import pandas as pd
import aedis_lib as A
import ledger as L

b = A.load_bars("H1")
close, opn, high, low = b["close"], b["open"], b["high"], b["low"]
n = len(close)
hr = A.hhmm(b["start"]) // 100
P = 1e-4

# unconditional baseline drift
print("=== BASELINE unconditional fwd mid drift (all bars, nonoverlap)")
for h in (15, 30, 60, 120):
    j0 = np.arange(1, n)
    j1 = np.minimum(np.arange(1, n) + h, n - 1)
    r = (close[j1] - opn[j0]) / P
    keep, last = [], -10**9
    idx = np.arange(1, n)
    for k, i in enumerate(idx):
        if i >= last + h:
            keep.append(k); last = i
    rr = r[np.array(keep)]
    print(f"  h={h:4d}m N={len(rr):6d} mean={rr.mean():8.3f}p t={rr.mean()/(rr.std()/np.sqrt(len(rr))):6.2f}")

# ---------- F01 short-horizon momentum (k-minute impulse) ----------
print("=== F01 momentum: ret(last k) > +x pips -> continuation")
for k in (5, 15, 30, 60):
    ret_k = np.full(n, np.nan)
    ret_k[k:] = (close[k:] - close[:-k]) / P
    for x in (2, 4, 6, 10):
        cond = ret_k > x
        res = L.fwd_table(cond, b, horizons=(15, 30, 60), nonoverlap=True)
        for h, (N, m, t) in res.items():
            L.log("F01", f"momentum k={k}", f"x>{x}p h={h}", N, m,
                  status="SCREEN", reason=f"t={t} nonoverlap")
        L.show({h: res[h] for h in (15, 60)}, f"F01 k={k} x>{x}")

# ---------- F02 mean reversion on impulse (inverse reading of F01) ----------
print("=== F02 reversion: ret(last k) < -x pips -> bounce")
for k in (15, 30, 60):
    ret_k = np.full(n, np.nan)
    ret_k[k:] = (close[k:] - close[:-k]) / P
    for x in (4, 6, 10):
        cond = ret_k < -x
        res = L.fwd_table(cond, b, horizons=(15, 30, 60), nonoverlap=True)
        for h, (N, m, t) in res.items():
            L.log("F02", f"reversion k={k}", f"x<-{x}p h={h}", N, m,
                  status="SCREEN", reason=f"t={t} nonoverlap")
        L.show({h: res[h] for h in (15, 60)}, f"F02 k={k} x<-{x}")

# ---------- F03 hour-of-day drift map ----------
print("=== F03 hour-of-day unconditional drift, h=60")
r60 = np.full(n, np.nan)
j1 = np.minimum(np.arange(n) + 60, n - 1)
j0 = np.minimum(np.arange(n) + 1, n - 1)
r60 = (close[j1] - opn[j0]) / P
for h0 in range(24):
    m = hr == h0
    if m.sum() < 200:
        continue
    rr = r60[m]
    rr = rr[np.isfinite(rr)]
    t = rr.mean() / (rr.std() / np.sqrt(len(rr)))
    L.log("F03", "hour drift", f"hour={h0} h=60", len(rr), rr.mean(),
          status="SCREEN", reason=f"t={t:.2f}")
    print(f"  hour={h0:02d} N={len(rr):6d} mean={rr.mean():8.3f}p t={t:6.2f}")

# ---------- F07 H1 trend filter x M1 momentum ----------
print("=== F07 H1 trend (EMA20 vs close) x M1 impulse alignment")
h1_start = (b["start"] // (3600 * int(1e9))) * (3600 * int(1e9))
# build H1 mid bars from M1
hu, inv = np.unique(h1_start, return_inverse=True)
ho = np.zeros(len(hu)); hc = np.zeros(len(hu)); hh = np.full(len(hu), -9e9); hl = np.full(len(hu), 9e9)
np.add.at(ho, inv, opn * 0)  # placeholder
ho = np.array([opn[inv == i][0] for i in range(len(hu))])
hc = np.array([close[inv == i][-1] for i in range(len(hu))])
hh = np.array([high[inv == i].max() for i in range(len(hu))])
hl = np.array([low[inv == i].min() for i in range(len(hu))])
ema20 = A.mtf_lib.ema(hc, 20)
trend = np.full(n, np.nan)
trend_h = np.where(hc > ema20, 1, np.where(hc < ema20, -1, 0))
trend = trend_h[inv]
for k in (15, 30):
    ret_k = np.full(n, np.nan)
    ret_k[k:] = (close[k:] - close[:-k]) / P
    for x in (3, 5):
        witht = np.isfinite(ret_k) & np.isfinite(trend)
        cond_long = witht & (trend == 1) & (ret_k > x)
        cond_short = witht & (trend == -1) & (ret_k < -x)
        for nm, cond in (("long", cond_long), ("short", cond_short)):
            res = L.fwd_table(cond, b, horizons=(30, 60, 120), nonoverlap=True)
            for h, (N, m, t) in res.items():
                L.log("F07", "H1 trend x impulse", f"{nm} k={k} x>{x} h={h}", N, m,
                      status="SCREEN", reason=f"t={t}")
            L.show({h: res[h] for h in (60,)}, f"F07 {nm} k={k} x>{x} (aligned)")

# ---------- F11 distance from rolling daily extremes ----------
print("=== F11 stretch from 24h high/low -> reversion")
roll_hi = pd.Series(high).rolling(1440).max().shift(1).to_numpy()
roll_lo = pd.Series(low).rolling(1440).min().shift(1).to_numpy()
atr = pd.Series(np.maximum(high - low, np.maximum(abs(high - np.roll(close, 1)), abs(low - np.roll(close, 1))))).rolling(60).mean().to_numpy()
for km in (1.0, 1.5, 2.0):
    near_hi = (high >= roll_hi - km * atr) & np.isfinite(roll_hi)
    near_lo = (low <= roll_lo + km * atr) & np.isfinite(roll_lo)
    res = L.fwd_table(near_hi, b, horizons=(30, 60), nonoverlap=True)
    L.show(res, f"F11 near 24h-high within {km}xATR60 (fade?)")
    for h, (N, m, t) in res.items():
        L.log("F11", "stretch reversion", f"near24hHigh {km}ATR h={h}", N, m,
              status="SCREEN", reason=f"t={t}")
    res = L.fwd_table(near_lo, b, horizons=(30, 60), nonoverlap=True)
    L.show(res, f"F11 near 24h-low within {km}xATR60 (bounce?)")
    for h, (N, m, t) in res.items():
        L.log("F11", "stretch reversion", f"near24hLow {km}ATR h={h}", N, m,
              status="SCREEN", reason=f"t={t}")

# ---------- F14 compression -> expansion readiness ----------
print("=== F14 compression (60m range pct low) -> next-hour drift")
rng60 = pd.Series(high - low).rolling(60).sum().to_numpy() / P
q20, q40, q60 = np.nanpercentile(rng60, [20, 40, 60])
for nm, cond in (("tight_q20", rng60 < q20), ("tight_q40", rng60 < q40),
                 ("wide_q80", rng60 > np.nanpercentile(rng60, 80))):
    res = L.fwd_table(cond, b, horizons=(30, 60, 120), nonoverlap=True)
    L.show(res, f"F14 range60 {nm}")
    for h, (N, m, t) in res.items():
        L.log("F14", "vol regime", f"range60 {nm} h={h}", N, m,
              status="SCREEN", reason=f"t={t}")
print("screens_a done")
