#!/usr/bin/env python3
"""FAMILIES L + D SCREEN — session-transition mechanisms, baseline-controlled.

L (session momentum): direction of the 07:00-12:00 UTC London morning move
   predicts the 12:00-20:00 UTC continuation? (event = sign of 07-12 move,
   forward drift 12:00->20:00 in event direction vs unconditional same-window
   baseline)
D (London false breakout): during 07:00-12:00 UTC, sweep of the Asia range
   (00:00-06:59 UTC high/low) that closes back inside -> fade event, forward
   drift over the next 8h vs baseline. S004 tested the ASIA false breakout
   (dead); this is the LONDON-session variant (different session mechanics).
"""
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import tmlab as T

START, END = "2020-01-01", "2025-12-31 23:59"
HZ = 8  # hours forward for D events (12:00 -> 20:00 for L events)


def hours_of(idx):
    return np.array([ts.hour for ts in idx])


for sym in T.PAIRS:
    df5 = T.load_5m(sym, START, END)
    h1 = T.resample_ohlcv(df5, "1h")
    h = h1["high"].to_numpy(); l = h1["low"].to_numpy()
    c = h1["close"].to_numpy()
    idx = h1.index
    hr = hours_of(idx)
    day = np.array([ts.date() for ts in idx])
    yrs = np.array([ts.year for ts in idx])
    pip = T.PIP[sym]
    n = len(c)

    fwd = np.full(n, np.nan)
    jj = np.arange(n - HZ)
    fwd[jj] = np.log(c[jj + HZ] / c[jj]) * c[jj] / pip
    base = float(np.nanmean(fwd))

    ev_L, ev_D_up, ev_D_dn = [], [], []
    dates = sorted(set(day))
    for d in dates:
        m = day == d
        ii = np.nonzero(m)[0]
        if len(ii) < 20:
            continue
        i07 = ii[hr[ii] == 7]
        i12 = ii[hr[ii] == 12]
        i00 = ii[hr[ii] == 0]
        if len(i07) == 0 or len(i12) == 0:
            continue
        a, b = i07[0], i12[0]
        if a + 1 > b:
            continue
        # Asia range (00:00-06:59)
        asia = ii[hr[ii] < 7]
        if len(i00) and len(asia) > 3:
            a_hi, a_lo = np.max(h[asia]), np.min(l[asia])
            london_m = ii[(hr[ii] >= 7) & (hr[ii] < 12)]
            f_up = f_dn = False
            for i in london_m:
                if not f_up and h[i] > a_hi and c[i] < a_hi:
                    ev_D_up.append(i); f_up = True
                if not f_dn and l[i] < a_lo and c[i] > a_lo:
                    ev_D_dn.append(i); f_dn = True
        # L: London morning move sign, drift 12:00 -> +8h
        move = c[b] - c[a]
        if abs(move) / pip > 5:          # ignore dead-flat mornings
            ev_L.append((b, np.sign(move)))
    for name, ev, sign in (("L_london_momentum", ev_L, None),
                           ("D_london_false_break_high_fade", ev_D_up, -1),
                           ("D_london_false_break_low_fade", ev_D_dn, +1)):
        if name.startswith("L"):
            r = np.array([fwd[i] * s for i, s in ev if np.isfinite(fwd[i])])
        else:
            ii = np.array(ev, "int64")
            ii = ii[ii + HZ < n]
            r = fwd[ii] * sign
        r = r[np.isfinite(r)]
        if len(r) == 0:
            print(f"{sym} {name:34} n=0")
            continue
        yidx = (yrs[np.array([e[0] if name.startswith("L") else e for e in
                              (ev if name.startswith("L") else ev)])]) if False else None
        print(f"{sym} {name:34} n={len(r):>4} baseline={base:+.2f} "
              f"mean={np.mean(r):+.2f} win={np.mean(r>0):.3f} "
              f"marginal={np.mean(r)-base:+.2f}")
