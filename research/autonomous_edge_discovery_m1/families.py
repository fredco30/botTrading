#!/usr/bin/env python3
"""AUTONOMOUS_EDGE_DISCOVERY_M1 — mechanism families (preferred territory).
Every family exposes feat_fn(bars, extras, j) -> {value, input_ts, aux?} and
one or more sign_of(f) configs. All constructions are causal (trailing/shifted
windows only); the gate proves it before any screen/PnL."""
import numpy as np
import pandas as pd
import m1lib as M
import infra_lib as I

NS = I.NS
PIP = I.PIP


def extras_common(ts, bid, ask, bars):
    high, low, close = bars["high"], bars["low"], bars["close"]
    ex = {}
    s = pd.Series
    hl = s(high - low)
    ex["range60"] = hl.rolling(60).sum().to_numpy()
    ex["range60_ref"] = s(ex["range60"]).shift(1).rolling(7200).median().to_numpy()
    r360 = s(high).rolling(360).max() - s(low).rolling(360).min()
    ex["range360"] = r360.to_numpy()
    ex["r360_q20"] = s(r360).shift(1).rolling(28800).quantile(0.20).to_numpy()
    ex["r360_q30"] = s(r360).shift(1).rolling(28800).quantile(0.30).to_numpy()
    ex["box_hi"] = s(high).shift(1).rolling(360).max().to_numpy()
    ex["box_lo"] = s(low).shift(1).rolling(360).min().to_numpy()
    for w in (15, 30, 60):
        ex[f"r{w}"] = np.r_[np.full(w, np.nan), close[w:] - close[:-w]]
    ex["hh24"] = s(high).shift(1).rolling(1440).max().to_numpy()
    ex["ll24"] = s(low).shift(1).rolling(1440).min().to_numpy()
    ex["hh120"] = s(high).shift(1).rolling(120).max().to_numpy()
    ex["ll120"] = s(low).shift(1).rolling(120).min().to_numpy()
    ex["hhmm"] = M.hhmm(bars)
    ex["day"] = M.day_id(bars)
    return ex


# F01 serial dependence conditional on volatility regime
def f01_feat(bars, ex, j):
    r30, v, vref = ex["r30"][j], ex["range60"][j], ex["range60_ref"][j]
    if not (np.isfinite(r30) and np.isfinite(v) and np.isfinite(vref)):
        return None
    if v > 1.25 * vref:
        reg = 1
    elif v < 0.85 * vref:
        reg = -1
    else:
        return None
    return {"value": float(r30 * reg / PIP), "input_ts": [bars["last_tick_ts"][j]],
            "aux": int(reg)}


def f01_cont(f):   # continue impulse in high-vol regime
    if f["aux"] != 1:
        return 0
    return 1 if f["value"] > 6 else (-1 if f["value"] < -6 else 0)


def f01_rev(f):    # fade impulse in low-vol regime
    if f["aux"] != -1:
        return 0
    return -1 if f["value"] > 6 else (1 if f["value"] < -6 else 0)


# F02 compression -> box breakout continuation
def f02_feat(bars, ex, j):
    c, bh, bl = bars["close"][j], ex["box_hi"][j], ex["box_lo"][j]
    r360, q20 = ex["range360"][j], ex["r360_q20"][j]
    if not all(np.isfinite(x) for x in (c, bh, bl, r360, q20)):
        return None
    if not (r360 < q20):
        return None
    if c > bh:
        return {"value": float((c - bh) / PIP), "input_ts": [bars["last_tick_ts"][j]], "aux": 1}
    if c < bl:
        return {"value": float((c - bl) / PIP), "input_ts": [bars["last_tick_ts"][j]], "aux": -1}
    return None


def f02_break(f):
    if f["aux"] == 1 and f["value"] > 0:
        return 1
    if f["aux"] == -1 and f["value"] < 0:
        return -1
    return 0


# F03 failed break out of compression -> fade
def f03_feat(bars, ex, j):
    c, h, l = bars["close"][j], bars["high"][j], bars["low"][j]
    bh, bl = ex["box_hi"][j], ex["box_lo"][j]
    r360, q30 = ex["range360"][j], ex["r360_q30"][j]
    if not all(np.isfinite(x) for x in (c, h, l, bh, bl, r360, q30)):
        return None
    if not (r360 < q30):
        return None
    if h > bh:
        return {"value": float((c - bh) / PIP), "input_ts": [bars["last_tick_ts"][j]], "aux": 1}
    if l < bl:
        return {"value": float((c - bl) / PIP), "input_ts": [bars["last_tick_ts"][j]], "aux": -1}
    return None


def f03_fade(f):
    if f["aux"] == 1 and f["value"] <= 0:
        return -1
    if f["aux"] == -1 and f["value"] >= 0:
        return 1
    return 0


# F04 overnight -> London direction flip
def _bar_at_or_before(ex, bars, j, hhmm_val):
    t = int(bars["close_time"][j])
    d0 = t - (t % (86400 * NS)) + hhmm_val // 100 * 3600 * NS + (hhmm_val % 100) * 60 * NS
    return int(np.searchsorted(bars["close_time"], d0, side="right")) - 1


def f04_feat(bars, ex, j):
    if ex["hhmm"][j] != 759:
        return None
    i_on = _bar_at_or_before(ex, bars, j, 559)
    if i_on < 0:
        return None
    lon = (bars["close"][j] - bars["close"][i_on]) / PIP
    d_start = int(bars["close_time"][j]) - (int(bars["close_time"][j]) % (86400 * NS))
    i0 = int(np.searchsorted(bars["close_time"], d_start, side="left"))
    if i0 > i_on:
        return None
    onr = (bars["close"][i_on] - bars["close"][i0]) / PIP
    if abs(onr) <= 5:
        return None
    return {"value": float(lon * np.sign(onr)), "input_ts": [bars["last_tick_ts"][j], bars["last_tick_ts"][i_on]],
            "aux": int(np.sign(onr))}


def f04_flip(f):   # London opposite to overnight -> follow London
    return 1 if f["value"] < -5 else (-1 if f["value"] > 5 else 0)


# F05 London -> NY reversal handoff
def f05_feat(bars, ex, j):
    if ex["hhmm"][j] != 1629:
        return None
    i_1530 = _bar_at_or_before(ex, bars, j, 1529)
    i_1200 = _bar_at_or_before(ex, bars, j, 1159)
    if i_1530 < 0 or i_1200 < 0:
        return None
    lon = (bars["close"][i_1530] - bars["close"][i_1200]) / PIP
    us = (bars["close"][j] - bars["close"][i_1530]) / PIP
    if abs(lon) <= 15:
        return None
    return {"value": float(us * np.sign(lon)), "input_ts": [bars["last_tick_ts"][j], bars["last_tick_ts"][i_1530]],
            "aux": int(np.sign(lon))}


def f05_rev(f):    # NY opposes London move -> fade London direction
    return -1 if f["value"] < -5 else (1 if f["value"] > 5 else 0)


# F06 directional deceleration (exhaustion)
def f06_feat(bars, ex, j):
    cur, prev = ex["r15"][j], ex["r15"][j - 15] if j >= 15 else np.nan
    if not (np.isfinite(cur) and np.isfinite(prev)):
        return None
    pp, cp = prev / PIP, cur / PIP
    if pp > 6 and cp > 2:
        return {"value": float((cur - 0.5 * prev) / PIP), "input_ts": [bars["last_tick_ts"][j]], "aux": 1}
    if pp < -6 and cp < -2:
        return {"value": float((cur - 0.5 * prev) / PIP), "input_ts": [bars["last_tick_ts"][j]], "aux": -1}
    return None


def f06_decel(f):  # decelerating advance -> short; decelerating decline -> long
    if f["aux"] == 1 and f["value"] < 0:
        return -1
    if f["aux"] == -1 and f["value"] > 0:
        return 1
    return 0


# F07 fresh 24h extreme continuation
def f07_feat(bars, ex, j):
    h, l, c = bars["high"][j], bars["low"][j], bars["close"][j]
    hh, ll = ex["hh24"][j], ex["ll24"][j]
    if not all(np.isfinite(x) for x in (h, l, c, hh, ll)):
        return None
    i0 = j - 60
    if h > hh:
        if i0 >= 0 and np.any(bars["high"][i0:j] > ex["hh24"][i0:j]):
            return None
        return {"value": float((hh - c) / PIP), "input_ts": [bars["last_tick_ts"][j]], "aux": 1}
    if l < ll:
        if i0 >= 0 and np.any(bars["low"][i0:j] < ex["ll24"][i0:j]):
            return None
        return {"value": float((c - ll) / PIP), "input_ts": [bars["last_tick_ts"][j]], "aux": -1}
    return None


def f07_fresh(f):  # fresh high + close near it -> long; fresh low -> short
    if f["aux"] == 1 and 0 <= f["value"] < 4:
        return 1
    if f["aux"] == -1 and 0 <= f["value"] < 4:
        return -1
    return 0


# F08 absorption: new 2h extreme then 3 fading closes against it
def f08_feat(bars, ex, j):
    if j < 122:
        return None
    c = bars["close"][j:j + 1][0]
    hi120, lo120 = ex["hh120"][j], ex["ll120"][j]
    if not (np.isfinite(hi120) and np.isfinite(lo120)):
        return None
    c2, c1 = bars["close"][j - 1], bars["close"][j]
    mid2 = (bars["high"][j - 1] + bars["low"][j - 1]) / 2
    if bars["high"][j] > hi120 and c2 < mid2 and c1 < (bars["high"][j] + bars["low"][j]) / 2 and c1 < c2:
        return {"value": float((c1 - bars["high"][j]) / PIP), "input_ts": [bars["last_tick_ts"][j]], "aux": 1}
    if bars["low"][j] < lo120 and c2 > mid2 and c1 > (bars["high"][j] + bars["low"][j]) / 2 and c1 > c2:
        return {"value": float((c1 - bars["low"][j]) / PIP), "input_ts": [bars["last_tick_ts"][j]], "aux": -1}
    return None


def f08_absorb(f):  # distribution below fresh highs -> short; mirror -> long
    if f["aux"] == 1 and f["value"] < 0:
        return -1
    if f["aux"] == -1 and f["value"] > 0:
        return 1
    return 0


# F10 range persistence -> expansion day breakout
F10_TIGHT_K = 0.75


def f10_build_extras(ts, bid, ask, bars):
    ex = extras_common(ts, bid, ask, bars)
    day = ex["day"]
    n = len(day)
    d_hi = np.full(n, np.nan)
    d_lo = np.full(n, np.nan)
    df_h = pd.DataFrame({"d": day, "h": bars["high"], "l": bars["low"]})
    g = df_h.groupby("d")
    dr = g["h"].max() - g["l"].min()
    med20 = dr.rolling(20).median().shift(1)
    dr4 = (dr.shift(1) < F10_TIGHT_K * dr.rolling(20).median().shift(1))
    prev_hi_arr = np.full(n, np.nan)
    prev_lo_arr = np.full(n, np.nan)
    tight_arr = np.zeros(n, dtype=bool)
    # map per-day scalars to bars of the NEXT day
    days = np.array(sorted(g.size().index))
    hi_by_day = g["h"].max().to_numpy()
    lo_by_day = g["l"].min().to_numpy()
    tight_by_day = dr4.to_numpy()
    for d in range(len(days)):
        m = day == days[d]
        if d >= 1:
            prev_hi_arr[m] = hi_by_day[d - 1]
            prev_lo_arr[m] = lo_by_day[d - 1]
        if d >= 1 and tight_by_day[d - 1]:
            tight_arr[m] = True
    ex["prev_hi"], ex["prev_lo"], ex["tight_yday"] = prev_hi_arr, prev_lo_arr, tight_arr
    return ex


def f10_feat(bars, ex, j):
    if not ex["tight_yday"][j]:
        return None
    c, ph, pl = bars["close"][j], ex["prev_hi"][j], ex["prev_lo"][j]
    if not all(np.isfinite(x) for x in (c, ph, pl)):
        return None
    if c > ph:
        return {"value": float((c - ph) / PIP), "input_ts": [bars["last_tick_ts"][j]], "aux": 1}
    if c < pl:
        return {"value": float((c - pl) / PIP), "input_ts": [bars["last_tick_ts"][j]], "aux": -1}
    return None


def f10_expand(f):
    if f["aux"] == 1 and f["value"] > 0:
        return 1
    if f["aux"] == -1 and f["value"] < 0:
        return -1
    return 0


# F11 tick-activity surge with direction
def f11_build_extras(ts, bid, ask, bars):
    ex = extras_common(ts, bid, ask, bars)
    s = pd.Series
    base = s(bars["n_ticks"]).shift(1).rolling(1440).median().to_numpy()
    r1 = np.r_[np.nan, np.diff(bars["close"]) / PIP]
    ex["act_z"] = bars["n_ticks"] / np.maximum(base, 1)
    ex["r1"] = r1
    return ex


def f11_feat(bars, ex, j):
    z, r1 = ex["act_z"][j], ex["r1"][j]
    if not (np.isfinite(z) and np.isfinite(r1)) or z <= 3 or abs(r1) <= 1.5:
        return None
    return {"value": float(z * np.sign(r1)), "input_ts": [bars["last_tick_ts"][j]], "aux": int(np.sign(r1))}


def f11_surge(f):  # follow the activity-surge direction (both sides)
    return f["aux"] if abs(f["value"]) > 3 else 0


# F12 volatility expansion directional continuation
def f12_build_extras(ts, bid, ask, bars):
    ex = extras_common(ts, bid, ask, bars)
    s = pd.Series
    q80 = s(ex["range60"]).shift(1).rolling(28800).quantile(0.80).to_numpy()
    ex["range60_q80"] = q80
    return ex


def f12_feat(bars, ex, j):
    v, q, r60 = ex["range60"][j], ex["range60_q80"][j], ex["r60"][j]
    if not (np.isfinite(v) and np.isfinite(q) and np.isfinite(r60)):
        return None
    if v <= q:
        return None
    return {"value": float(r60 / PIP), "input_ts": [bars["last_tick_ts"][j]], "aux": 1}


def f12_cont(f):
    return 1 if f["value"] > 8 else (-1 if f["value"] < -8 else 0)


# F13 NY-window range breakout (11:30-13:00 range, 13:00-16:00 execution window)
def f13_build_extras(ts, bid, ask, bars):
    ex = extras_common(ts, bid, ask, bars)
    hhmm = ex["hhmm"]
    n = len(hhmm)
    rng_hi = np.full(n, np.nan)
    rng_lo = np.full(n, np.nan)
    day_start_trend = np.full(n, np.nan)
    in_win = (hhmm >= 1130) & (hhmm < 1300)
    for i in range(n):
        if hhmm[i] == 1300:
            m = in_win & (ex["day"] == ex["day"][i])
            if m.sum() >= 30:
                rng_hi[i] = bars["high"][m].max()
                rng_lo[i] = bars["low"][m].min()
                i0 = int(np.flatnonzero(m)[0])
                day_start_trend[i] = bars["close"][i0] - bars["open"][m][0]
    ex["ny_hi"], ex["ny_lo"], ex["ny_trend"] = _ffill_daily(rng_hi), _ffill_daily(rng_lo), _ffill_daily(day_start_trend)
    return ex


def _ffill_daily(a):
    s = pd.Series(a)
    return s.ffill().to_numpy()


def f13_feat(bars, ex, j):
    hm = ex["hhmm"][j]
    if not (1300 <= hm < 1600):
        return None
    hi, lo, tr = ex["ny_hi"][j], ex["ny_lo"][j], ex["ny_trend"][j]
    if not all(np.isfinite(x) for x in (hi, lo, tr)):
        return None
    c = bars["close"][j]
    if c > hi:
        return {"value": float((c - hi) / PIP), "input_ts": [bars["last_tick_ts"][j]],
                "aux": 1 if tr > 0 else 0}
    if c < lo:
        return {"value": float((c - lo) / PIP), "input_ts": [bars["last_tick_ts"][j]],
                "aux": -1 if tr < 0 else 0}
    return None


def f13_nybrk(f):  # breakout aligned with day trend (aux 0 = unaligned -> no trade)
    if f["aux"] == 1 and f["value"] > 0:
        return 1
    if f["aux"] == -1 and f["value"] < 0:
        return -1
    return 0
