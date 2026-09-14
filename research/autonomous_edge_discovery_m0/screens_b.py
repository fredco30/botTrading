#!/usr/bin/env python3
"""Screens B: session-structure / breakout / microstructure families."""
import numpy as np
import pandas as pd
import aedis_lib as A
import ledger as L

b = A.load_bars("H1")
close, opn, high, low = b["close"], b["open"], b["high"], b["low"]
n = len(close)
nticks = b["n_ticks"]
P = 1e-4
hhmm = A.hhmm(b["start"])
hour = hhmm // 100
minute = hhmm % 100
date = pd.to_datetime(b["start"], utc=True).date
dates = pd.factorize(date)[0]
ndays = dates.max() + 1

# ---------- F05 session false breakout (London 07:00-08:00 range) ----------
print("=== F05 London-range false breakout")
for sess_start, sess_end, nm in ((700, 800, "LDN07"), (1300, 1400, "NY13")):
    # session range from the first hour bars
    in_sess = (hhmm >= sess_start) & (hhmm < sess_end)
    # per-day session high/low using only completed bars: evaluate at hhmm==sess_end
    evalm = hhmm == sess_end
    day_sh = np.full(ndays, np.nan); day_sl = np.full(ndays, np.nan)
    day_sc = np.full(ndays, np.nan)
    for d in range(ndays):
        m = (dates == d) & in_sess
        if m.sum() >= 20:
            day_sh[d] = high[m].max(); day_sl[d] = low[m].min()
            day_sc[d] = close[m][-1]
    sh = day_sh[dates]; sl = day_sl[dates]; sc = day_sc[dates]
    rng = sh - sl
    for brk in (2, 4):
        up = evalm & np.isfinite(sh) & (close > sh + brk * P)
        dn = evalm & np.isfinite(sl) & (close < sl - brk * P)
        res = L.fwd_table(up, b, horizons=(30, 60, 120), nonoverlap=True)
        L.show(res, f"F05 {nm} breakout UP >{brk}p")
        for h, (N, m, t) in res.items():
            L.log("F05", f"{nm} orbrk", f"UP>{brk}p h={h}", N, m, status="SCREEN", reason=f"t={t}")
        res = L.fwd_table(dn, b, horizons=(30, 60, 120), nonoverlap=True)
        L.show(res, f"F05 {nm} breakout DOWN <{brk}p")
        for h, (N, m, t) in res.items():
            L.log("F05", f"{nm} orbrk", f"DN<{brk}p h={h}", N, m, status="SCREEN", reason=f"t={t}")
        # FALSE breakout: pierce then close back inside -> reversal
        m15end = (hhmm >= sess_end) & (hhmm < sess_end + 15)
        fb_up = np.zeros(n, bool); fb_dn = np.zeros(n, bool)
        for d in range(ndays):
            m0 = (dates == d) & in_sess
            if m0.sum() < 20:
                continue
            sh_d, sl_d = high[m0].max(), low[m0].min()
            aft = (dates == d) & m15end
            if aft.sum() == 0:
                continue
            i = np.flatnonzero(aft)[0]
            if high[i] > sh_d + brk * P and close[i] < sh_d:
                fb_up[i] = True
            if low[i] < sl_d - brk * P and close[i] > sl_d:
                fb_dn[i] = True
        res = L.fwd_table(fb_up, b, horizons=(30, 60), nonoverlap=True)
        L.show(res, f"F05 {nm} FALSE breakout UP (fade)")
        for h, (N, m, t) in res.items():
            L.log("F05", f"{nm} falsebrk", f"UP>{brk}p h={h}", N, m, status="SCREEN", reason=f"t={t}")
        res = L.fwd_table(fb_dn, b, horizons=(30, 60), nonoverlap=True)
        L.show(res, f"F05 {nm} FALSE breakout DN (fade)")
        for h, (N, m, t) in res.items():
            L.log("F05", f"{nm} falsebrk", f"DN<{brk}p h={h}", N, m, status="SCREEN", reason=f"t={t}")

# ---------- F06 post-spike reversal (1-min climactic range) ----------
print("=== F06 spike -> reversal")
med_rng = pd.Series(high - low).rolling(120).median().to_numpy()
spike = (high - low) > 3.0 * med_rng
up_spike = spike & (close > (high + low) / 2)
dn_spike = spike & (close < (high + low) / 2)
for nm, cond in (("UP-spike fade", up_spike), ("DN-spike fade", dn_spike)):
    res = L.fwd_table(cond, b, horizons=(15, 30, 60), nonoverlap=True)
    L.show(res, f"F06 {nm}")
    for h, (N, m, t) in res.items():
        L.log("F06", "climactic spike fade", f"{nm} 3x medrange h={h}", N, m,
              status="SCREEN", reason=f"t={t}")

# ---------- F08 weekend gap ----------
print("=== F08 weekend gap behavior")
fri_close = {}
sun_open = {}
for d in range(ndays):
    m = dates == d
    hrs = hour[m]
    dow = pd.Timestamp(sorted(set(np.array(list(date))[m]))[0]).dayofweek
    if dow == 4 and m.sum() > 0:
        fri_close[d] = close[m][-1]
    if dow == 6 and m.sum() > 0:
        sun_open[d] = opn[m][0]
gaps = []
for d in sorted(sun_open):
    f = d - 2
    if f in fri_close:
        gaps.append((d, (sun_open[d] - fri_close[f]) / P))
print(f"  weekends found: {len(gaps)}")
for d, g in gaps:
    m = (dates == d) & (hour >= 22)
    m2 = (dates == d + 1) & (hour < 6)
    if m.sum() and m2.sum():
        fwd = (close[m2][np.argmin(np.abs(hour[m2] - 600))] - opn[m][0]) / P
        print(f"   gap {g:+7.1f}p -> Sun22:00-06:00 move {fwd:+7.1f}p")
if gaps:
    g = np.array([x[1] for x in gaps]); fw = []
    for d, gg in gaps:
        m = (dates == d) & (hour >= 22)
        m2 = (dates == d + 1) & (hour < 6)
        if m.sum() and m2.sum():
            fw.append((close[m2][np.argmin(np.abs(hour[m2] - 600))] - opn[m][0]) / P)
    fw = np.array(fw)
    fade = -np.sign(g) * fw
    print(f"  fade-gap mean {fade.mean():+.2f}p (N={len(fw)})  cont mean {(-fade).mean():+.2f}p")
    L.log("F08", "weekend gap", "fade, eval 06:00", len(fw), float(fade.mean()),
          status="SCREEN", reason="few events")

# ---------- F10 tick-activity intensity directional bias ----------
print("=== F10 high tick activity minute -> next drift")
z = (pd.Series(nticks).rolling(120).mean() + 1).to_numpy()
act = nticks / np.maximum(z, 1)
for q in (95,):
    thr = np.nanpercentile(act, q)
    hi_act = act > thr
    res = L.fwd_table(hi_act, b, horizons=(15, 30, 60), nonoverlap=True)
    L.show(res, f"F10 activity >q{q} (unconditional)")
    for h, (N, m, t) in res.items():
        L.log("F10", "tick activity", f"q{q} h={h}", N, m, status="SCREEN", reason=f"t={t}")

# ---------- F12 multi-hour momentum persistence ----------
print("=== F12 4h-return sign persistence")
h4 = (b["start"] // (4 * 3600 * int(1e9)))
hu4, inv4 = np.unique(h4, return_inverse=True)
hc4 = np.zeros(len(hu4))
for i in range(len(hu4)):
    hc4[i] = close[inv4 == i][-1]
r4 = np.full(len(hu4), np.nan)
r4[4:] = (hc4[4:] - hc4[:-4]) / P
r4now = r4[inv4]
pos = np.isfinite(r4now) & (r4now > 10)
neg = np.isfinite(r4now) & (r4now < -10)
res = L.fwd_table(pos, b, horizons=(60, 120), nonoverlap=True)
L.show(res, "F12 4h ret > +10p -> continuation")
for h, (N, m, t) in res.items():
    L.log("F12", "4h momentum", f"+10p h={h}", N, m, status="SCREEN", reason=f"t={t}")
res = L.fwd_table(neg, b, horizons=(60, 120), nonoverlap=True)
L.show(res, "F12 4h ret < -10p -> continuation")
for h, (N, m, t) in res.items():
    L.log("F12", "4h momentum", f"-10p h={h}", N, m, status="SCREEN", reason=f"t={t}")

# ---------- F15 VWAP distance reversion (daily) ----------
print("=== F15 daily VWAP distance")
tp = (high + low + close) / 3
dvo = np.zeros(ndays); dv = np.zeros(ndays); dvo_n = np.zeros(ndays)
for d in range(ndays):
    m = dates == d
    dvo[d] = np.sum(tp[m] * nticks[m])
    dv[d] = np.sum(nticks[m])
cum_v = np.cumsum(dvo)
cum_n = np.cumsum(dv)
vwap_d = np.zeros(n)
for d in range(ndays):
    m = dates == d
    vwap_d[m] = cum_v[d] / max(cum_n[d], 1)
dist = (close - vwap_d) / P
atr = pd.Series(high - low).rolling(240).mean().to_numpy() / P
for km in (3.0, 5.0):
    far_up = dist > km * atr
    far_dn = dist < -km * atr
    res = L.fwd_table(far_up, b, horizons=(30, 60), nonoverlap=True)
    L.show(res, f"F15 >{km}xATR above VWAP (fade?)")
    for h, (N, m2, t) in res.items():
        L.log("F15", "vwap reversion", f"up>{km}ATR h={h}", N, m2, status="SCREEN", reason=f"t={t}")
    res = L.fwd_table(far_dn, b, horizons=(30, 60), nonoverlap=True)
    L.show(res, f"F15 >{km}xATR below VWAP (fade?)")
    for h, (N, m2, t) in res.items():
        L.log("F15", "vwap reversion", f"dn<{km}ATR h={h}", N, m2, status="SCREEN", reason=f"t={t}")
print("screens_b done")
