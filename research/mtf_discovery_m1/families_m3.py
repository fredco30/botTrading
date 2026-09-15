#!/usr/bin/env python3
"""Signal families for MULTITIMEFRAME_DISCOVERY_M1.

Every sig_fn(bars, year) -> int8 side array on its signal TF (vectorized,
completed bars only: value at bar i uses bars with close_time <= close[i];
higher-TF context enters via 'as-of' joins on close_time). Termination-safe:
first year rows have NaN context -> side 0.
"""
import numpy as np
import pandas as pd

import m3lib as L

NS, PIP = L.NS, L.PIP


def asof(ct_ctx, val, ct_sig):
    """Context values as of each signal decision: last val[j] with
    ct_ctx[j] <= ct_sig (completed context bars only)."""
    k = np.searchsorted(ct_ctx, ct_sig, side="right") - 1
    k = np.maximum(k, 0)
    ok = (k >= 0) & (ct_ctx[k] <= ct_sig)
    v = np.asarray(val, dtype=np.float64)[k]
    return np.where(ok, v, np.nan)


def day_groups(ct):
    d = pd.to_datetime(ct, unit="ns", utc=True).floor("D")
    return d.to_numpy()


# ------------------------------------------------------------- F01 H4 fade

def f01_band_fade(flat_filter=False, zthr=2.0, L1=50):
    def sig(bars, year):
        c = bars["H4_close"]
        z = L.zsc(c, L1)
        side = np.zeros(len(c), dtype=np.int8)
        ok = np.isfinite(z)
        if flat_filter:
            adx = L.adx(bars["H4_high"], bars["H4_low"], c, 14)
            ok &= np.isfinite(adx) & (adx < 20)
        side[ok & (z <= -zthr)] = 1
        side[ok & (z >= zthr)] = -1
        side[:L1 + 5] = 0
        return side
    sig.signal_tf = "H4"
    sig.desc = f"H4 z(SMA{L1}) fade |z|>={zthr} flatfilt={flat_filter}"
    return sig


# ------------------------------------------------------- F02 H4 Donchian

def f02_donchian(N=30):
    def sig(bars, year):
        c = bars["H4_close"]
        hi, lo = L.donhi(c, N), L.donlo(c, N)
        side = np.zeros(len(c), dtype=np.int8)
        side[np.isfinite(hi) & (c > hi)] = 1
        side[np.isfinite(lo) & (c < lo)] = -1
        return side
    sig.signal_tf = "H4"
    sig.desc = f"H4 close breaks Donchian{N}"
    return sig


# -------------------------------------------------- F03 London-open break

def f03_london_break(trend_filter=False, range_min=0):
    def sig(bars, year):
        c = bars["M15_close"]; o = bars["M15_open"]
        h = bars["M15_high"]; l = bars["M15_low"]
        ct = bars["M15_close_time"]
        t = L.hhmm(ct)
        days = day_groups(ct)
        ud, first = np.unique(days, return_index=True)
        n = len(c)
        side = np.zeros(n, dtype=np.int8)
        # H4 trend context as of decision
        e50 = L.ema(bars["H4_close"], 50)
        h4trend = np.sign(bars["H4_close"] - e50)
        tr = asof(bars["H4_close_time"], h4trend, ct)
        for di in range(len(ud)):
            m = days == ud[di]
            ids = np.flatnonzero(m)
            asia = ids[(t[ids] >= 0) & (t[ids] <= 645)]
            if len(asia) < 10:
                continue
            ah, al = h[asia].max(), l[asia].min()
            rng = (ah - al) / PIP
            if rng < range_min:
                continue
            tok = ids[(t[ids] >= 700) & (t[ids] <= 1100)]
            lon_c = c[tok]
            up = np.flatnonzero(lon_c > ah)
            dn = np.flatnonzero(lon_c < al)
            if len(up) and (not trend_filter or tr[tok[up[0]]] > 0):
                side[tok[up[0]]] = 1
            if len(dn) and (not trend_filter or tr[tok[dn[0]]] < 0):
                side[tok[dn[0]]] = -1
        side[:30] = 0
        return side
    sig.signal_tf = "M15"
    sig.desc = f"London break of 00-07h Asia range trendfilt={trend_filter} minrng={range_min}"
    return sig


# ------------------------------------------------------- F04 PDH/PDL

def f04_prev_day(mode="break"):
    def sig(bars, year):
        c = bars["M15_close"]; h = bars["M15_high"]; l = bars["M15_low"]
        ct = bars["M15_close_time"]
        t = L.hhmm(ct)
        days = day_groups(ct)
        ud = np.unique(days)
        n = len(c)
        side = np.zeros(n, dtype=np.int8)
        for di in range(1, len(ud)):
            prev = days == ud[di - 1]
            cur = days == ud[di]
            if prev.sum() < 10:
                continue
            pdh, pdl = h[prev].max(), l[prev].min()
            ids = np.flatnonzero(cur & (t >= 700) & (t <= 1700))
            cc = c[ids]
            if mode == "break":
                up = np.flatnonzero(cc > pdh)
                dn = np.flatnonzero(cc < pdl)
                if len(up):
                    side[ids[up[0]]] = 1
                if len(dn):
                    side[ids[dn[0]]] = -1
            else:  # fade: first close above PDH then a close back below it
                fired_up = fired_dn = False
                above = False
                below = False
                for k, i in enumerate(ids):
                    if not fired_up:
                        if not above and cc[k] > pdh:
                            above = True
                        elif above and cc[k] < pdh:
                            side[i] = -1
                            fired_up = True
                    if not fired_dn:
                        if not below and cc[k] < pdl:
                            below = True
                        elif below and cc[k] > pdl:
                            side[i] = 1
                            fired_dn = True
                    if fired_up and fired_dn:
                        break
        side[:40] = 0
        return side
    sig.signal_tf = "M15"
    sig.desc = f"Prev-day H/L {mode} (M15 trigger 07-17h)"
    return sig


# ------------------------------------- F05 failed H4-Donchian break (M15)

def f05_failed_break(N=30, window=3):
    def sig(bars, year):
        c = bars["M15_close"]
        ct = bars["M15_close_time"]
        hc = bars["H4_close"]
        hi = L.donhi(hc, N)
        lo = L.donlo(hc, N)
        hi_a = asof(bars["H4_close_time"], hi, ct)
        lo_a = asof(bars["H4_close_time"], lo, ct)
        n = len(c)
        side = np.zeros(n, dtype=np.int8)
        above = np.isfinite(hi_a) & (c > hi_a)
        below = np.isfinite(lo_a) & (c < lo_a)
        for i in np.flatnonzero(above):
            j_end = min(i + window, n - 1)
            seg = c[i + 1:j_end + 1]
            fail = np.flatnonzero(seg < hi_a[i])
            if len(fail):
                side[i + 1 + fail[0]] = -1
        for i in np.flatnonzero(below):
            j_end = min(i + window, n - 1)
            seg = c[i + 1:j_end + 1]
            fail = np.flatnonzero(seg > lo_a[i])
            if len(fail):
                side[i + 1 + fail[0]] = 1
        side[:40] = 0
        return side
    sig.signal_tf = "M15"
    sig.desc = f"Failed break of H4 Donchian{N} within {window} M15 bars"
    return sig


# --------------------------- F06 H4 trend + H1 pullback + M15 trigger

def f06_trend_pullback():
    def sig(bars, year):
        mc = bars["M15_close"]
        mct = bars["M15_close_time"]
        hc = bars["H4_close"]
        h1c, h1l = bars["H1_close"], bars["H1_low"]
        hct = bars["H1_close_time"]
        # H4 trend (completed H4 bars)
        e20, e50 = L.ema(hc, 20), L.ema(hc, 50)
        tr = np.sign((hc - e50) + 0.01 * (e20 - e50) / PIP)
        tr_a = asof(bars["H4_close_time"], tr, mct)
        # H1 setup: pullback touched EMA20 within last 4 completed H1 bars
        h1e = L.ema(h1c, 20)
        touched = np.zeros(len(h1c), dtype=bool)
        for k in range(1, 5):
            touched[k:] |= h1l[k:] <= h1e[:-k]
        up_t = touched & (h1c > h1e)          # dip held above the EMA
        up_a = asof(hct, up_t.astype(float), mct) > 0
        dn_a = asof(hct, (touched & (h1c < h1e)).astype(float), mct) > 0
        # M15 trigger: close crosses back above/below EMA20(M15)
        me = L.ema(mc, 20)
        cross_up = (mc > me) & (np.roll(mc, 1) <= np.roll(me, 1))
        cross_dn = (mc < me) & (np.roll(mc, 1) >= np.roll(me, 1))
        side = np.zeros(len(mc), dtype=np.int8)
        side[np.isfinite(tr_a) & (tr_a > 0) & up_a & cross_up] = 1
        side[np.isfinite(tr_a) & (tr_a < 0) & dn_a & cross_dn] = -1
        side[:60] = 0
        return side
    sig.signal_tf = "M15"
    sig.desc = "H4 EMA20>50 trend + H1 EMA20 pullback + M15 EMA20 cross trigger"
    return sig


# ------------------------------------ F07 squeeze + H4 direction (M15)

def f07_squeeze_break(ratio=0.75):
    def sig(bars, year):
        mc = bars["M15_close"]
        mct = bars["M15_close_time"]
        hc = bars["H4_close"]
        a14 = L.atr(bars["M15_high"], bars["M15_low"], mc, 14)
        a96 = L.atr(bars["M15_high"], bars["M15_low"], mc, 96)
        sq = np.roll(a14 / np.maximum(a96, 1e-9), 1) <= ratio   # known at bar i
        hc_sma = L.sma(hc, 50)
        d = np.sign(hc - hc_sma)
        d_a = asof(bars["H4_close_time"], d, mct)
        hi, lo = L.donhi(mc, 48), L.donlo(mc, 48)
        side = np.zeros(len(mc), dtype=np.int8)
        side[np.isfinite(d_a) & sq & np.isfinite(hi) & (mc > hi) & (d_a > 0)] = 1
        side[np.isfinite(d_a) & sq & np.isfinite(lo) & (mc < lo) & (d_a < 0)] = -1
        side[:100] = 0
        return side
    sig.signal_tf = "M15"
    sig.desc = f"M15 ATR14/96<={ratio} squeeze + break in H4 SMA50 direction"
    return sig


# --------------------------------- F08 Asia->London state transfer (M15)

def f08_asia_transfer(mode="continuation", min_move=10.0):
    def sig(bars, year):
        c = bars["M15_close"]
        ct = bars["M15_close_time"]
        t = L.hhmm(ct)
        days = day_groups(ct)
        ud = np.unique(days)
        side = np.zeros(len(c), dtype=np.int8)
        for di in range(1, len(ud)):
            cur = days == ud[di]
            ids = np.flatnonzero(cur)
            b0 = ids[(t[ids] == 0)][0] if (t[ids] == 0).any() else None
            aend = ids[(t[ids] == 645)]
            if b0 is None or not len(aend):
                continue
            aret = (c[aend[0]] - c[b0]) / PIP
            tok = ids[(t[ids] == 700)]
            if not len(tok) or abs(aret) < min_move:
                continue
            sgn = 1 if aret > 0 else -1
            side[tok[0]] = sgn if mode == "continuation" else -sgn
        side[:40] = 0
        return side
    sig.signal_tf = "M15"
    sig.desc = f"London 07:00 {mode} of Asia move (|move|>={min_move}p)"
    return sig


# ------------------------------- F09 H4 trend acceleration + M15 thrust

def f09_accel_thrust():
    def sig(bars, year):
        mc, mo = bars["M15_close"], bars["M15_open"]
        mct = bars["M15_close_time"]
        hc = bars["H4_close"]
        mom = hc - np.roll(hc, 6)
        accel = (mom > np.roll(mom, 6)) & (mom > 0)
        decel = (mom < np.roll(mom, 6)) & (mom < 0)
        ac_a = asof(bars["H4_close_time"], accel.astype(float), mct) > 0
        dc_a = asof(bars["H4_close_time"], decel.astype(float), mct) > 0
        a14 = L.atr(bars["M15_high"], bars["M15_low"], mc, 14)
        body = (mc - mo) / PIP
        side = np.zeros(len(mc), dtype=np.int8)
        side[ac_a & (body > 1.5 * a14)] = 1
        side[dc_a & (body < -1.5 * a14)] = -1
        side[:100] = 0
        return side
    sig.signal_tf = "M15"
    sig.desc = "H4 6-bar momentum accelerating + M15 body>1.5ATR thrust"
    return sig


# ------------------------------------------ F10 previous-week break (M15)

def f10_prev_week(mode="break"):
    def sig(bars, year):
        c = bars["M15_close"]; h = bars["M15_high"]; l = bars["M15_low"]
        ct = bars["M15_close_time"]
        wk = pd.to_datetime(ct, unit="ns", utc=True).strftime("%G-%V").to_numpy()
        uw = np.unique(wk)
        side = np.zeros(len(c), dtype=np.int8)
        for wi in range(1, len(uw)):
            cur = wk == uw[wi]
            prev = wk == uw[wi - 1]
            if prev.sum() < 50:
                continue
            pwh, pwl = h[prev].max(), l[prev].min()
            ids = np.flatnonzero(cur)
            dow = pd.to_datetime(ct[ids], unit="ns", utc=True).dayofweek.to_numpy()
            ids = ids[dow <= 3]
            cc = c[ids]
            if mode == "break":
                up = np.flatnonzero(cc > pwh)
                dn = np.flatnonzero(cc < pwl)
                if len(up):
                    side[ids[up[0]]] = 1
                if len(dn):
                    side[ids[dn[0]]] = -1
            else:
                fired = 0
                above = below = False
                for k, i in enumerate(ids):
                    if not (fired & 1) and cc[k] > pwh:
                        above = True
                    elif above and cc[k] < pwh and not (fired & 1):
                        side[i] = -1; fired |= 1
                    if not (fired & 2) and cc[k] < pwl:
                        below = True
                    elif below and cc[k] > pwl and not (fired & 2):
                        side[i] = 1; fired |= 2
                    if fired == 3:
                        break
        side[:60] = 0
        return side
    sig.signal_tf = "M15"
    sig.desc = f"Prev-week H/L {mode} (M15 trigger, Mon-Thu)"
    return sig
