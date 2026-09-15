#!/usr/bin/env python3
"""Family definitions for FX_MULTIPAIR_SWING_DISCOVERY_M1.

Every signal function is f(bars, sym, params) -> int8 side array on
`signal_tf` (completed bars only; value i may read bars 0..i of any TF whose
close_time <= close_time[i]). All quantities are normalized (ATR multiples,
z-scores, log returns, ratios) so one conceptual rule transfers across pairs.
Discovery pairs: EURUSD + GBPUSD only (USDJPY is the sealed holdout).
"""
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import swing_lib as S

NS = S.NS
PIP = S.PIP


def sig_tf(tf):
    def deco(fn):
        fn.signal_tf = tf
        return fn
    return deco


def scan_signal(sym, signal_fn, params, horizons):
    """Gross screen for one (signal_fn, params) on one pair.
    Returns {h: np.array of gross returns in pips}."""
    bars = S.build_discovery_bars(sym)
    side = signal_fn(bars, sym, params)
    tf = signal_fn.signal_tf
    b = {k: bars[f"{tf}_{k}"] for k in ("open", "high", "low", "close")}
    opn, close, n = b["open"], b["close"], len(b["close"])
    pip = PIP[sym]
    out = {}
    for h in horizons:
        rets = []
        last = -10 ** 9
        for i in np.flatnonzero(side != 0):
            if i <= last or i + 1 >= n:
                continue
            j = min(i + h, n - 1)
            rets.append(side[i] * (close[j] - opn[i + 1]) / pip)
            last = j
        out[h] = np.asarray(rets)
    return out, int((side != 0).sum())


def summarize_scan(title, res, n_sig, horizons, years=8):
    lines = [f"--- {title} (signals={n_sig}) ---"]
    for h in horizons:
        v = res[h]
        if len(v) == 0:
            lines.append(f"h={h:>3} N=0")
            continue
        mean = float(v.mean()); sd = float(v.std(ddof=1)) if len(v) > 1 else 0
        t = mean / (sd / np.sqrt(len(v))) if sd > 0 and len(v) > 2 else np.nan
        lines.append(f"h={h:>3} N={len(v):>5} pooled={mean:+7.2f}p "
                     f"med={np.median(v):+6.2f} t={t:+.1f}")
    return "\n".join(lines)


def pool_two(res_e, res_g, horizons):
    return {h: np.concatenate([res_e[h], res_g[h]]) for h in horizons}


# =====================================================================
# G01 — Donchian multi-day breakout (D1 signal)
# =====================================================================

@sig_tf("D1")
def g01_donchian(bars, sym, p):
    c = bars["D1_close"]
    hi, lo = S.donhi(c, p["n"]), S.donlo(c, p["n"])
    side = np.zeros(len(c), dtype=np.int8)
    side[c > hi] = 1
    side[c < lo] = -1
    return side


# =====================================================================
# G02 — Time-series momentum (D1 signal)
# =====================================================================

@sig_tf("D1")
def g02_tsmom(bars, sym, p):
    c = bars["D1_close"]
    r = S.ret(c, p["k"])
    side = np.zeros(len(c), dtype=np.int8)
    side[r > 0] = 1
    side[r < 0] = -1
    return side


# =====================================================================
# G03 — Trend + pullback (H4 trend, H1 entry)
# =====================================================================

@sig_tf("H1")
def g03_trend_pullback(bars, sym, p):
    h1c = bars["H1_close"]; h1ct = bars["H1_close_time"]
    h1l = bars["H1_low"]; h1h = bars["H1_high"]
    h4c = bars["H4_close"]; h4ct = bars["H4_close_time"]
    ema = S.ema(h4c, p["trend_n"])
    # H4 trend state aligned causally to each H1 bar
    idx4 = np.searchsorted(h4ct, h1ct, side="right") - 1
    up = (h4c > ema)[idx4]
    e1 = S.ema(h1c, p["pb_n"])
    a1 = S.atr(sym, bars["H1_high"], bars["H1_low"], h1c, 14) * p["depth"] \
        * PIP[sym]                                     # ATR pips -> price
    # pullback state: price tagged EMA - depth*ATR recently; entry on the
    # H1 close that re-crosses above the EMA while state armed (both sides)
    below = h1l < e1 - a1          # touched deep pullback intrabar
    above = h1c > e1 + a1
    # arm/disarm state machine, vectorized via cumulative logic per side
    def recross(deep, back):
        armed = np.zeros(len(h1c), dtype=bool)
        arm = False
        out = np.zeros(len(h1c), dtype=bool)
        for i in range(len(h1c)):
            if back[i] and arm:
                out[i] = True
                arm = False
            elif deep[i]:
                arm = True
        return out
    lo_entry = recross(below, h1c > e1)
    hi_entry = recross(h1h > e1 + a1, h1c < e1)
    side = np.zeros(len(h1c), dtype=np.int8)
    side[lo_entry & up] = 1
    side[hi_entry & ~up] = -1
    return side


# =====================================================================
# G04 — Conditional mean reversion at N-day extremes (D1, time exits)
# =====================================================================

@sig_tf("D1")
def g04_extreme_fade(bars, sym, p):
    c = bars["D1_close"]
    z = S.zsc(c, p["z_n"])
    side = np.zeros(len(c), dtype=np.int8)
    side[z <= -p["z"]] = 1
    side[z >= p["z"]] = -1
    return side


# =====================================================================
# G05 — Previous day/week structure: acceptance break (H1 signal)
# =====================================================================

@sig_tf("H1")
def g05_acceptance(bars, sym, p):
    h1c = bars["H1_close"]; h1ct = bars["H1_close_time"]
    dh = bars["D1_high"]; dl = bars["D1_low"]; dct = bars["D1_close_time"]
    # prior completed D1 bar's H/L, causal at each H1 bar (-2 = previous day)
    idx = np.searchsorted(dct, h1ct, side="right") - 2
    valid = idx >= 0
    vi = np.clip(idx, 0, None)
    pdh = np.where(valid, dh[vi], np.nan)
    pdl = np.where(valid, dl[vi], np.nan)
    above = h1c > pdh
    below = h1c < pdl
    # acceptance = two consecutive H1 closes beyond the prior-day extreme;
    # fire only on the FIRST such pair after a non-accepted state
    acc_up = above & np.roll(above, 1) & ~np.roll(above & np.roll(above, 1), 1)
    acc_dn = below & np.roll(below, 1) & ~np.roll(below & np.roll(below, 1), 1)
    acc_up[:2] = False; acc_dn[:2] = False
    side = np.zeros(len(h1c), dtype=np.int8)
    side[acc_up & valid] = 1
    side[acc_dn & valid] = -1
    return side


# =====================================================================
# G06 — Volatility compression -> expansion (D1)
# =====================================================================

@sig_tf("D1")
def g06_compression(bars, sym, p):
    c = bars["D1_close"]; h = bars["D1_high"]; l = bars["D1_low"]
    fast = S.atr(sym, h, l, c, 5)
    slow = S.atr(sym, h, l, c, 50)
    squeeze = fast / slow <= p["ratio"]
    hi, lo = S.donhi(c, 5), S.donlo(c, 5)
    side = np.zeros(len(c), dtype=np.int8)
    side[squeeze & (c > hi)] = 1
    side[squeeze & (c < lo)] = -1
    return side


# =====================================================================
# G07 — Unusual displacement continuation (H4)
# =====================================================================

@sig_tf("H4")
def g07_displacement(bars, sym, p):
    h = bars["H4_high"]; l = bars["H4_low"]; c = bars["H4_close"]
    rng = h - l
    atr50 = S.atr(sym, h, l, c, 50) * PIP[sym]        # pips -> price
    big = rng >= p["mult"] * atr50
    pos = (c - l) / np.maximum(rng, 1e-12)      # close location in range
    side = np.zeros(len(c), dtype=np.int8)
    side[big & (pos >= 0.75)] = 1
    side[big & (pos <= 0.25)] = -1
    return side


# =====================================================================
# G08 — Path efficiency at fresh extremes (D1)
# =====================================================================

@sig_tf("D1")
def g08_efficiency(bars, sym, p):
    c = bars["D1_close"]
    k = p["k"]
    net = c - np.roll(c, k); net[:k] = np.nan
    moves = np.abs(np.diff(c, prepend=c[0]))
    path = pd.Series(moves).rolling(k).sum().to_numpy()
    eff = np.abs(net) / np.maximum(path, 1e-12)
    hi, lo = S.donhi(c, k), S.donlo(c, k)
    side = np.zeros(len(c), dtype=np.int8)
    side[(eff >= p["eff"]) & (c > hi)] = 1
    side[(eff >= p["eff"]) & (c < lo)] = -1
    return side


# =====================================================================
# G09 — Cross-pair common-USD regime (D1, EURUSD+GBPUSD synchronized)
# =====================================================================

@sig_tf("D1")
def g09_usd_regime(bars, sym, p):
    """USD proxy = mean of z-scored D1 log returns of EURUSD & GBPUSD,
    aligned per close_time (both D1 bars close at UTC midnight -> perfectly
    synchronized; missing other-pair bars are skipped, never back-filled).
    Trade BOTH pairs in the USD direction: USD strong -> short majors,
    USD weak -> long majors."""
    assert sym in S.DISCOVERY_PAIRS
    other = "GBPUSD" if sym == "EURUSD" else "EURUSD"
    me_ct = bars["D1_close_time"]
    ot = S.build_discovery_bars(other)
    ot_ct = ot["D1_close_time"]
    j = np.searchsorted(ot_ct, me_ct)
    j = np.clip(j, 0, len(ot_ct) - 1)
    aligned = ot_ct[j] == me_ct
    mc = bars["D1_close"]
    oc = ot["D1_close"][j]
    ok = aligned & (mc > 0) & (oc > 0)
    with np.errstate(divide="ignore", invalid="ignore"):
        rm = np.full(len(mc), np.nan)
        ro = np.full(len(mc), np.nan)
        rm[1:] = np.where(ok[1:] & ok[:-1],
                          np.log(mc[1:]) - np.log(mc[:-1]), np.nan)
        ro[1:] = np.where(ok[1:] & ok[:-1],
                          np.log(oc[1:]) - np.log(oc[:-1]), np.nan)
    sd_m, sd_o = S.std(rm, p["z_n"]), S.std(ro, p["z_n"])
    sm, so = S.sma(rm, p["z_n"]), S.sma(ro, p["z_n"])
    ze = (rm - sm) / np.maximum(sd_m, 1e-12)
    zg = (ro - so) / np.maximum(sd_o, 1e-12)
    usd = -(ze + zg) / 2                        # + = USD strong
    side = np.zeros(len(mc), dtype=np.int8)
    side[usd >= p["z"]] = -1                    # USD strong -> short majors
    side[usd <= -p["z"]] = 1                    # USD weak -> long majors
    return side


# =====================================================================
# G10 — Multi-TF state machine: D1 trend x H4 breakout trigger
# =====================================================================

@sig_tf("H4")
def g10_state_machine(bars, sym, p):
    dc = bars["D1_close"]; dct = bars["D1_close_time"]
    h4c = bars["H4_close"]; h4ct = bars["H4_close_time"]
    h4h = bars["H4_high"]; h4l = bars["H4_low"]
    ema_f, ema_s = S.ema(dc, p["fast"]), S.ema(dc, p["slow"])
    idx = np.searchsorted(dct, h4ct, side="right") - 1
    bull = (ema_f > ema_s)[idx]
    hi, lo = S.donhi(h4c, p["break_n"]), S.donlo(h4c, p["break_n"])
    side = np.zeros(len(h4c), dtype=np.int8)
    side[bull & (h4c > hi)] = 1
    side[~bull & (h4c < lo)] = -1
    return side


# =====================================================================
# G11 — Volatility regime transition (D1)
# =====================================================================

@sig_tf("D1")
def g11_vol_regime(bars, sym, p):
    c = bars["D1_close"]; h = bars["D1_high"]; l = bars["D1_low"]
    atr14 = S.atr(sym, h, l, c, 14)
    pct = pd.Series(atr14).rolling(p["win"]).rank(pct=True).to_numpy()
    rising = c > S.sma(c, p["ma_n"])
    fire_hi = (pct >= p["hi"]) & (np.roll(pct, 1) < p["hi"])
    fire_lo = (pct <= p["lo"]) & (np.roll(pct, 1) > p["lo"])
    side = np.zeros(len(c), dtype=np.int8)
    side[fire_hi & rising] = 1
    side[fire_hi & ~rising] = -1
    return side


# =====================================================================
# G12 — Monday range breakout -> week direction (H1 signal)
# =====================================================================

@sig_tf("H1")
def g12_monday_range(bars, sym, p):
    h1c = bars["H1_close"]; h1h = bars["H1_high"]; h1l = bars["H1_low"]
    h1ct = bars["H1_close_time"]
    dt = pd.to_datetime(h1ct, unit="ns", utc=True)
    hour = h1ct // NS // 3600 % 24
    dow = dt.dayofweek.to_numpy()
    is_mon = dow == 0
    mon_range_win = is_mon & (hour >= 0) & (hour < p["end_hr"])
    # per-ISO-week Monday range, fully formed once the window closes
    week = dt.isocalendar()
    wk = (week.year * 100 + week.week).to_numpy()
    df = pd.DataFrame({"wk": wk, "h": np.where(mon_range_win, h1h, np.nan),
                       "l": np.where(mon_range_win, h1l, np.nan)})
    mrh = df.groupby("wk")["h"].transform("max").to_numpy()
    mrl = df.groupby("wk")["l"].transform("min").to_numpy()
    side = np.zeros(len(h1c), dtype=np.int8)
    after = ~is_mon
    side[after & (h1c > mrh)] = 1
    side[after & (h1c < mrl)] = -1
    # once per ISO week: keep only the first fire
    fired = np.zeros(len(h1c), dtype=bool)
    last_wk = -1
    for i in range(len(h1c)):
        if side[i] != 0 and wk[i] != last_wk:
            fired[i] = True
            last_wk = wk[i]
    return np.where(fired, side, 0)
