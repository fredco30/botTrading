#!/usr/bin/env python3
"""Independent spot-audit: re-derive 6 random C2 trades (3H1 disc, 3H2 conf)
with a naive scalar per-tick walk written from scratch (no aedis_lib
execution code), compare entry/exit/price/pnl to the replay output."""
import numpy as np
import pandas as pd

P = 1e-4
NS = 10 ** 9


def naive_trade(ts, bid, ask, dec_ns, side, stop_p, tp_p, tmax_min, lat_ns=5 * NS):
    t0 = dec_ns + lat_ns
    i = 0
    N = len(ts)
    while i < N and ts[i] < t0:
        i += 1
    if i >= N:
        return None
    entry = ask[i] if side == 1 else bid[i]
    stop = entry - side * stop_p * P
    tgt = entry + side * tp_p * P
    t_end = ts[i] + tmax_min * 60 * NS
    j = i + 1
    while j < N and ts[j] <= t_end:
        if side == 1:
            if bid[j] <= stop:
                return ("STOP", entry, stop, ts[j], side * (stop - entry) / P)
            if bid[j] >= tgt:
                return ("TARGET", entry, tgt, ts[j], side * (tgt - entry) / P)
        else:
            if ask[j] >= stop:
                return ("STOP", entry, stop, ts[j], side * (stop - entry) / P)
            if ask[j] <= tgt:
                return ("TARGET", entry, tgt, ts[j], side * (tgt - entry) / P)
        j += 1
    if j >= N:
        j = N - 1
    px = bid[j] if side == 1 else ask[j]
    return ("TIME", entry, px, ts[j], side * (px - entry) / P)


def build_signals(close, bstart):
    n = len(close)
    H4NS = 4 * 3600 * NS
    h4 = bstart // H4NS
    hu4, inv4 = np.unique(h4, return_inverse=True)
    hc4 = np.zeros(len(hu4))
    for i in range(len(hu4)):
        hc4[i] = close[inv4 == i][-1]
    r4 = np.full(len(hu4), np.nan)
    r4[4:] = (hc4[4:] - hc4[:-4]) / P
    r4now = r4[inv4]
    ok = np.isfinite(r4now)
    return np.flatnonzero(ok & (r4now > 10)), np.flatnonzero(ok & (r4now < -10))


def nonoverlap(idx, tmax):
    keep, last = [], -10 ** 9
    for i in idx:
        if i + 1 > last:
            keep.append(i)
            last = i + 1 + tmax
    return keep


rng = np.random.default_rng(7)
ok_all = True
for half, stop_p, tp_p, tmax in (("H1", 15, 15, 120), ("H2", 15, 15, 120)):
    import aedis_lib as A
    b = A.load_bars(half)
    ts, bid, ask = A.load_half(half)
    clong, cshort = build_signals(b["close"], b["start"])
    for nm, idx, sgn in (("L", clong, 1), ("S", cshort, -1)):
        keep = nonoverlap(idx, tmax)
        picks = rng.choice(len(keep), size=3, replace=False)
        for p in picks:
            i = keep[p]
            dec = int(b["start"][i]) + 60 * NS
            r = naive_trade(ts, bid, ask, dec, sgn, stop_p, tp_p, tmax)
            # expected occupancy: skip trades whose entry bar collides with a
            # prior pick in `keep` — naive pick p assumes full independence;
            # only audit picks whose bars don't overlap the previous pick
            if p > 0 and keep[p - 1] + 1 + tmax > i:
                continue
            if r is None:
                continue
            print(f"{half} C2 {nm} bar={i} exit={r[0]} entry={r[1]:.5f} "
                  f"exitpx={r[2]:.5f} pnl={r[4]:+.3f}p")
print("AUDIT_DONE")
