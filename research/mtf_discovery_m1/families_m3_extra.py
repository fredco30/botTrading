#!/usr/bin/env python3
"""Families F11 (Sunday gap fade) and F12 (daily-range break + M15 retest).
Same causal conventions as families_m3."""
import numpy as np
import pandas as pd

import m3lib as L

NS, PIP = L.NS, L.PIP


def f11_gap(mode="fade", min_gap=10.0, hour_end=23):
    """Sunday open vs Friday close (last completed M15 close of Friday).
    Decision: first M15 bar closing at/after 22:15 UTC Sunday with an
    unwind-safe gap measure (|gap| >= min_gap pips)."""
    def sig(bars, year):
        c = bars["M15_close"]
        ct = bars["M15_close_time"]
        dt = pd.to_datetime(ct, unit="ns", utc=True)
        dow = dt.dayofweek.to_numpy()
        hh = dt.hour.to_numpy()
        n = len(c)
        side = np.zeros(n, dtype=np.int8)
        # last M15 close of each Friday, first eligible Sunday bar per week
        fri_last = {}
        for i in range(n):
            if dow[i] == 4:
                fri_last[dt[i].floor("D")] = c[i]
        for i in range(n):
            if dow[i] != 6 or hh[i] < 22 or hh[i] >= hour_end:
                continue
            prev_fri = dt[i].floor("D") - pd.Timedelta(days=2)
            f = fri_last.get(prev_fri)
            if f is None or not np.isfinite(f):
                continue
            gap = (c[i] - f) / PIP
            if abs(gap) < min_gap:
                continue
            sgn = -1 if mode == "fade" else 1
            side[i] = sgn * np.sign(gap)
        return side
    sig.signal_tf = "M15"
    sig.desc = f"Sunday gap {mode} (|gap|>={min_gap}p, Sun 22-24h)"
    return sig


def f12_break_retest(ndays=10, near_atr=0.25, mode="retest"):
    """Daily context: highest high / lowest low of previous ndays UTC days
    (completed days, M15 aggregation). Break = M15 close beyond level.
    Retest entry: after the break (same day, within 12 M15 bars), price pulls
    back within near_atr*ATR15 of the level and closes back in break
    direction. Direct-break mode = enter on the break bar itself."""
    def sig(bars, year):
        c = bars["M15_close"]; h = bars["M15_high"]; l = bars["M15_low"]
        ct = bars["M15_close_time"]
        a14 = L.atr(h, l, c, 14)
        days = L.day_groups_safe(ct) if hasattr(L, "day_groups_safe") \
            else pd.to_datetime(ct, unit="ns", utc=True).floor("D").to_numpy()
        ud = np.unique(days)
        n = len(c)
        side = np.zeros(n, dtype=np.int8)
        for di in range(ndays + 1, len(ud)):
            cur = days == ud[di]
            # previous ndays completed days excluding today
            past = np.zeros(len(days), dtype=bool)
            for k in range(1, ndays + 1):
                past |= days == ud[di - k]
            if past.sum() < 100:
                continue
            hi, lo = h[past].max(), l[past].min()
            ids = np.flatnonzero(cur)
            cc = c[ids]
            up = np.flatnonzero(cc > hi)
            dn = np.flatnonzero(cc < lo)
            if mode == "break":
                if len(up):
                    side[ids[up[0]]] = 1
                if len(dn):
                    side[ids[dn[0]]] = -1
                continue
            for first, lvl, sgn in ((up, hi, 1), (dn, lo, -1)):
                if not len(first):
                    continue
                b0 = ids[first[0]]
                for j in range(b0 + 1, min(b0 + 13, n)):
                    if days[j] != ud[di]:
                        break
                    near = near_atr * a14[j] * PIP
                    if sgn == 1 and l[j] <= hi + near and c[j] > c[j - 1]:
                        side[j] = 1
                        break
                    if sgn == -1 and h[j] >= lo - near and c[j] < c[j - 1]:
                        side[j] = -1
                        break
        side[:60] = 0
        return side
    sig.signal_tf = "M15"
    sig.desc = f"{ndays}-day range break + {mode} (near={near_atr} ATR15)"
    return sig
