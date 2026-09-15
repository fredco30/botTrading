#!/usr/bin/env python3
"""AUTONOMOUS_EDGE_DISCOVERY_M2 — families F14..F20.

Each family: (mechanism, feat_fn(bars/extras, j) scalar for the causality
gate, cond builder for the cheap multi-year screen). The scalar feature is
the production quantity; thresholds live in sign/cond logic. All quantities
are causal functions of completed M1 bars / ticks inside them.
"""
import numpy as np
import pandas as pd

import m2lib as M

PIP = M.PIP


def _rq(arr, w, q):
    """Rolling quantile over completed window ending at current bar."""
    return pd.Series(arr).rolling(w).quantile(q).to_numpy()


# ---------------------------------------------------------------- F14
# Spread-state transitions: close-spread vs its own 24h distribution.
def f14_feat(bars, ex, j):
    """Raw feature: (spread_z_bucket, dir30). value = c_spr - spr_med24 in
    pips (negative = compressed, positive = expanded); aux = sign of net30."""
    if j < 1440 + 30:
        return None
    v = float(ex["c_spr"][j] - ex["spr_med24"][j])
    d = float(ex["net30"][j])
    if not np.isfinite(v) or not np.isfinite(d):
        return None
    return {"value": v, "input_ts": [int(ex["last_tick_ts"][j])], "aux": 1 if d > 0 else -1}


def f14_conds(ex, y):
    cs, med = ex["c_spr"], ex["spr_med24"]
    q10 = _rq(cs, 1440, 0.10); q90 = _rq(cs, 1440, 0.90)
    d30 = ex["net30"]
    c_comp = np.zeros(len(cs), bool); c_exp = np.zeros(len(cs), bool)
    ok = np.isfinite(med) & np.isfinite(d30) & (np.arange(len(cs)) >= 1440 + 30)
    c_comp[ok] = (cs[ok] <= q10[ok]) & (np.abs(d30[ok]) >= 3.0)
    c_exp[ok] = (cs[ok] >= q90[ok]) & (np.abs(d30[ok]) >= 3.0)
    longs_comp = np.where(c_comp & (d30 > 0), 1, 0) + np.where(c_comp & (d30 < 0), -1, 0)
    fade_exp = np.where(c_exp & (d30 > 0), -1, 0) + np.where(c_exp & (d30 < 0), 1, 0)
    return {
        "F14a comp-cont (spr<=q10,|net30|>=3p, w/ move)": longs_comp,
        "F14b exp-fade (spr>=q90,|net30|>=3p, vs move)": fade_exp,
    }


# ---------------------------------------------------------------- F15
# Displacement-per-tick: net30/dpt30 — thin fast moves vs active grinds.
def f15_feat(bars, ex, j):
    """value = dpt30 - rolling-24h-median(dpt30) (price-units per tick);
    aux = sign(net30)."""
    if j < 1440 + 30:
        return None
    v = float(ex["dpt30"][j] - np.nanmedian(ex["dpt30"][j - 1440:j]))
    d = float(ex["net30"][j])
    if not np.isfinite(v) or not np.isfinite(d):
        return None
    return {"value": v, "input_ts": [int(ex["last_tick_ts"][j])], "aux": 1 if d > 0 else -1}


def f15_conds(ex, y):
    dpt, d30 = ex["dpt30"], ex["net30"]
    q10 = _rq(dpt, 1440, 0.10); q90 = _rq(dpt, 1440, 0.90)
    ok = np.isfinite(dpt) & np.isfinite(d30) & (np.arange(len(dpt)) >= 1440 + 30)
    thin = np.zeros(len(dpt), bool); grind = np.zeros(len(dpt), bool)
    thin[ok] = (dpt[ok] >= q90[ok]) & (np.abs(d30[ok]) >= 3.0)
    grind[ok] = (dpt[ok] <= q10[ok]) & (np.abs(d30[ok]) >= 3.0)
    fade_thin = np.where(thin & (d30 > 0), -1, 0) + np.where(thin & (d30 < 0), 1, 0)
    cont_grind = np.where(grind & (d30 > 0), 1, 0) + np.where(grind & (d30 < 0), -1, 0)
    return {
        "F15a thin-fade (dpt30>=q90,|net30|>=3p, vs move)": fade_thin,
        "F15b grind-cont (dpt30<=q10,|net30|>=3p, w/ move)": cont_grind,
    }


# ---------------------------------------------------------------- F16
# Tick-flow imbalance (tick-rule proxy): sum(up-dn) over 15 bars.
def f16_feat(bars, ex, j):
    """value = rolling 15-bar sum(up-dn) normalized by rolling 15-bar
    sum(up+dn) (imbalance in [-1,1]); aux = sign of value."""
    if j < 15:
        return None
    imb = float((ex["up"][j - 14:j + 1].sum() - ex["dn"][j - 14:j + 1].sum())
                / max(ex["up"][j - 14:j + 1].sum() + ex["dn"][j - 14:j + 1].sum(), 1))
    if not np.isfinite(imb):
        return None
    return {"value": imb, "input_ts": [int(ex["last_tick_ts"][j])],
            "aux": 1 if imb > 0 else -1}


def f16_conds(ex, y):
    up, dn = ex["up"], ex["dn"]
    s_up = pd.Series(up).rolling(15).sum().to_numpy()
    s_dn = pd.Series(dn).rolling(15).sum().to_numpy()
    imb = (s_up - s_dn) / np.maximum(s_up + s_dn, 1)
    ok = np.isfinite(imb) & (np.arange(len(imb)) >= 30)
    sig = np.zeros(len(imb), np.int8)
    sig[ok & (imb >= 0.25)] = 1
    sig[ok & (imb <= -0.25)] = -1
    return {"F16a flow-imb cont (imb15>=+0.25 L / <=-0.25 S)": sig}


# ---------------------------------------------------------------- F17
# Post-spike reaction asymmetry: retrace fraction of a directional
# range-expansion bar measured over the next 3 completed bars.
SPIKE_K = 3.0     # bar range vs rolling 30-bar mean range
SPIKE_BODY = 0.6  # |close-open| / range


def f17_feat(bars, ex, j):
    """Decision at close of reaction window (3 bars after spike bar k=j-3).
    value = retrace fraction [0,1] of the spike; aux = spike direction."""
    k = j - 3
    if k < 30:
        return None
    rng_m = float(np.mean(ex["high"][k - 29:k + 1] - ex["low"][k - 29:k + 1]))
    rng_k = float(ex["high"][k] - ex["low"][k])
    body = float(abs(ex["close"][k] - ex["open"][k]))
    if not (rng_m > 0 and rng_k >= SPIKE_K * rng_m
            and body >= SPIKE_BODY * rng_k):
        return None
    sgn = 1 if ex["close"][k] > ex["open"][k] else -1
    if sgn == 1:
        ext = float(np.min(ex["low"][k + 1:j + 1]))
        retrace = (float(ex["high"][k]) - ext) / max(rng_k, 1e-12)
    else:
        ext = float(np.max(ex["high"][k + 1:j + 1]))
        retrace = (ext - float(ex["low"][k])) / max(rng_k, 1e-12)
    retrace = float(np.clip(retrace, 0.0, 1.5))
    # decision uses data through bar j (spike bar + 3 reaction bars)
    its = [int(ex["last_tick_ts"][j])]
    return {"value": retrace, "input_ts": its, "aux": sgn}


def f17_conds(ex, y):
    n = len(ex["close"])
    hi, lo, op, cl = ex["high"], ex["low"], ex["open"], ex["close"]
    rng = hi - lo
    rng_m = pd.Series(rng).rolling(30).mean().to_numpy()
    body = np.abs(cl - op)
    k = np.arange(n)
    is_spike = (rng >= SPIKE_K * rng_m) & (body >= SPIKE_BODY * rng) & (k >= 30)
    sgn = np.where(cl > op, 1, -1)
    # retrace over next 3 bars: at index k -> min/max of bars k+1..k+3
    lo1 = pd.Series(lo).rolling(3, min_periods=3).min().shift(-3).to_numpy()
    hi1 = pd.Series(hi).rolling(3, min_periods=3).max().shift(-3).to_numpy()
    retr = np.where(sgn == 1, (hi - lo1) / np.maximum(rng, 1e-12),
                    (hi1 - lo) / np.maximum(rng, 1e-12))
    dec = k + 3  # decision bar index (bar where window completes)
    valid = is_spike & (dec < n)
    idx = np.flatnonzero(valid)
    cont = np.zeros(n, np.int8); fade = np.zeros(n, np.int8)
    shallow = valid & np.isfinite(retr) & (retr <= 1 / 3)
    deep = valid & np.isfinite(retr) & (retr >= 2 / 3)
    up_s = shallow & (sgn == 1); dn_s = shallow & (sgn == -1)
    up_d = deep & (sgn == 1); dn_d = deep & (sgn == -1)
    cont[dec[up_s]] = 1
    cont[dec[dn_s]] = -1
    fade[dec[up_d]] = -1
    fade[dec[dn_d]] = 1
    return {
        "F17a spike shallow-retrace cont (<=1/3)": cont,
        "F17b spike deep-retrace fade (>=2/3)": fade,
    }


# ---------------------------------------------------------------- F18
# Path geometry: inefficient chop (er60 low) + price at 60-bar extreme -> fade.
def f18_feat(bars, ex, j):
    """value = er60; aux = +1 if near 60-bar high, -1 if near 60-bar low,
    0 mid-range."""
    if j < 1440 + 60:
        return None
    v = float(ex["er60"][j])
    if not np.isfinite(v):
        return None
    hh = float(np.max(ex["high"][j - 59:j + 1]))
    ll = float(np.min(ex["low"][j - 59:j + 1]))
    rng = max(hh - ll, 1e-12)
    posn = (float(ex["close"][j]) - ll) / rng
    return {"value": v, "input_ts": [int(ex["last_tick_ts"][j])],
            "aux": 1 if posn >= 0.75 else (-1 if posn <= 0.25 else 0)}


def f18_conds(ex, y):
    er, q10 = ex["er60"], _rq(ex["er60"], 1440, 0.10)
    hh = pd.Series(ex["high"]).rolling(60).max().to_numpy()
    ll = pd.Series(ex["low"]).rolling(60).min().to_numpy()
    rng = np.maximum(hh - ll, 1e-12)
    posn = (ex["close"] - ll) / rng
    ok = np.isfinite(er) & np.isfinite(q10) & (np.arange(len(er)) >= 1440 + 60)
    chop = ok & (er <= q10)
    fade = np.zeros(len(er), np.int8)
    fade[chop & (posn >= 0.85)] = -1
    fade[chop & (posn <= 0.15)] = 1
    return {"F18a chop-extreme fade (er60<=q10, posn>=.85/<=.15)": fade}


# ---------------------------------------------------------------- F19
# Vol-crush state transition: rv30/rv1440 extreme low after expansion.
def f19_feat(bars, ex, j):
    """value = volratio - rolling 24h median(volratio); aux = sign(net120)
    (direction of the preceding expansion)."""
    if j < 1440 + 120:
        return None
    v = float(ex["volratio"][j] - np.nanmedian(ex["volratio"][j - 1440:j]))
    d = float(ex["net120"][j])
    if not np.isfinite(v) or not np.isfinite(d):
        return None
    return {"value": v, "input_ts": [int(ex["last_tick_ts"][j])], "aux": 1 if d > 0 else -1}


def f19_conds(ex, y):
    vr, q10 = ex["volratio"], _rq(ex["volratio"], 1440, 0.10)
    d120 = ex["net120"]
    ok = np.isfinite(vr) & np.isfinite(d120) & (np.arange(len(vr)) >= 1440 + 120)
    crush = ok & (vr <= q10) & (np.abs(d120) >= 8.0)
    rev = np.where(crush & (d120 > 0), -1, 0) + np.where(crush & (d120 < 0), 1, 0)
    cont = np.where(crush & (d120 > 0), 1, 0) + np.where(crush & (d120 < 0), -1, 0)
    return {
        "F19a crush-reversal (vr<=q10,|net120|>=8p, vs move)": rev,
        "F19b crush-continuation (vr<=q10,|net120|>=8p, w/ move)": cont,
    }


# ---------------------------------------------------------------- F20
# Time-since-extreme acceptance: price holds near a 60-bar extreme that is
# at least AGE bars old (extreme not revisited since) -> acceptance trade.
F20_AGE = 20
F20_POSN = 0.90


def f20_feat(bars, ex, j):
    """value = bars since the 60-bar high was set (age); aux = +1 near high,
    -1 near low (0 otherwise). Age = argmax distance within window."""
    if j < 60:
        return None
    w_hi = ex["high"][j - 59:j + 1]
    w_lo = ex["low"][j - 59:j + 1]
    age_hi = int(59 - np.argmax(w_hi))
    age_lo = int(59 - np.argmin(w_lo))
    hh = float(np.max(w_hi)); ll = float(np.min(w_lo))
    rng = max(hh - ll, 1e-12)
    posn = (float(ex["close"][j]) - ll) / rng
    age = age_hi if posn >= F20_POSN else (age_lo if posn <= 1 - F20_POSN else -1)
    return {"value": float(age), "input_ts": [int(ex["last_tick_ts"][j])],
            "aux": 1 if posn >= F20_POSN else (-1 if posn <= 1 - F20_POSN else 0)}


def f20_conds(ex, y):
    hi, lo, cl = ex["high"], ex["low"], ex["close"]
    n = len(cl)
    hh60 = pd.Series(hi).rolling(60).max().to_numpy()
    ll60 = pd.Series(lo).rolling(60).min().to_numpy()
    rng = np.maximum(hh60 - ll60, 1e-12)
    posn = (cl - ll60) / rng
    # extreme is >=20 bars old  <=>  the 60-bar max is attained inside
    # [j-59, j-20]  <=>  max(40 bars ending at j-20) == hh60 (ties: the
    # scalar argmax also takes the OLDEST max, so this matches exactly)
    hh40s = pd.Series(hi).rolling(40).max().shift(20).to_numpy()
    ll40s = pd.Series(lo).rolling(40).min().shift(20).to_numpy()
    ok = np.arange(n) >= 60
    sig = np.zeros(n, np.int8)
    sig[ok & (hh40s == hh60) & (posn >= F20_POSN)] = 1
    sig[ok & (ll40s == ll60) & (posn <= 1 - F20_POSN)] = -1
    return {"F20a accepted-extreme cont (age>=20, posn>=.90/<=.10)": sig}


FAMILIES = {
    "F14": ("spread-state transitions", f14_feat, f14_conds),
    "F15": ("displacement-per-tick thin/grind", f15_feat, f15_conds),
    "F16": ("tick-flow imbalance continuation", f16_feat, f16_conds),
    "F17": ("post-spike reaction asymmetry", f17_feat, f17_conds),
    "F18": ("inefficient-path extreme fade", f18_feat, f18_conds),
    "F19": ("vol-crush state transition", f19_feat, f19_conds),
    "F20": ("time-since-extreme acceptance", f20_feat, f20_conds),
}
