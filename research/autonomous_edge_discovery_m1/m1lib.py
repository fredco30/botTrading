#!/usr/bin/env python3
"""AUTONOMOUS_EDGE_DISCOVERY_M1 — causality gate + cheap screens + helpers.
Builds on infra_lib (validated data layer + audited replay engine)."""
import numpy as np
import pandas as pd
import infra_lib as I

NS = I.NS
PIP = I.PIP


def load_year_bars(year):
    ts, bid, ask = I.load_year(year)
    bars = I.m1_bars(ts, bid, ask)
    return ts, bid, ask, bars


def add_n_ticks(ts, bars):
    """Tick counts per M1 bar (causal; part of bar construction)."""
    tf = 60 * NS
    ids = ts // tf
    bounds = np.flatnonzero(np.diff(ids)) + 1
    si = np.concatenate(([0], bounds))
    ei = np.concatenate((bounds, [len(ts)]))
    bars = dict(bars)
    bars["n_ticks"] = (ei - si).astype(np.int64)
    return bars


def hhmm(bars):
    secs = bars["close_time"] // NS
    return ((secs // 3600) % 24).astype(np.int64) * 100 + (secs % 3600) // 60


def day_id(bars):
    return pd.factorize(pd.to_datetime(bars["close_time"], utc=True).date)[0]


# ------------------------------------------------------------ gate (§4)

def causality_gate(family, feat_fn, build_extras, bars, extras,
                   n_samples=28, seed=20260915):
    """feat_fn(bars, extras, j) -> dict(value|None, input_ts, aux?).
    Samples ONLY bars where the feature fires. T1 max input ts <= T;
    T2 truncation identity; T3 future-mutation identity; each test rebuilds
    bars+extras from raw ticks. Returns (ok: bool, n_tested)."""
    ts, bid, ask = I.load_year(2017)
    n = len(bars["close"])
    rng = np.random.default_rng(seed)
    finite = []
    for j in range(500, n):
        f = feat_fn(bars, extras, j)
        if f is not None and f["value"] is not None and np.isfinite(f["value"]):
            finite.append(j)
    picks = list(rng.permutation(finite)[:n_samples]) if len(finite) > n_samples else finite
    t1 = t2 = t3 = True
    tested = 0
    for j in picks:
        T = int(bars["close_time"][j])
        f = feat_fn(bars, extras, int(j))
        if f is None or f["value"] is None or not np.isfinite(f["value"]):
            continue
        tested += 1
        its = [int(x) for x in f["input_ts"]]
        aux = f.get("aux")
        if not all(x <= T for x in its):
            t1 = False
            print(f"  T1 FAIL {family} j={j}: max_input={max(its)} T={T}")
        m = int(np.searchsorted(ts, T, side="right"))
        bars_t = add_n_ticks(ts[:m], I.m1_bars(ts[:m], bid[:m], ask[:m]))
        extras_t = build_extras(ts[:m], bid[:m], ask[:m], bars_t)
        jt = int(np.searchsorted(bars_t["close_time"], T, side="left"))
        f2 = feat_fn(bars_t, extras_t, jt) if (
            jt < len(bars_t["close_time"])
            and bars_t["close_time"][jt] == T) else None
        if (f2 is None or f2["value"] is None
                or f2["value"] != f["value"]
                or [int(x) for x in f2["input_ts"]] != its
                or f2.get("aux") != aux):
            t2 = False
            print(f"  T2 FAIL {family} j={j}: {f} vs {f2}")
        bid3, ask3 = bid.copy(), ask.copy()
        mut = ts > T
        bid3[mut] += 50 * PIP
        ask3[mut] += 50 * PIP
        bars_m = add_n_ticks(ts, I.m1_bars(ts, bid3, ask3))
        extras_m = build_extras(ts, bid3, ask3, bars_m)
        f3 = feat_fn(bars_m, extras_m, int(j))
        if (f3 is None or f3["value"] is None
                or f3["value"] != f["value"]
                or [int(x) for x in f3["input_ts"]] != its
                or f3.get("aux") != aux):
            t3 = False
            print(f"  T3 FAIL {family} j={j}: {f} vs {f3}")
    ok = t1 and t2 and t3 and tested >= 20
    print(f"GATE {family}: T1={'PASS' if t1 else 'FAIL'} "
          f"T2={'PASS' if t2 else 'FAIL'} T3={'PASS' if t3 else 'FAIL'} "
          f"({tested} tested) -> {'PASS' if ok else 'CAUSALITY_FAIL'}")
    return ok, tested


def signal_vector(feat_fn, sign_of, ts, bid, ask, bars, extras):
    """Production signals derived from the SAME audited scalar feature.
    sign_of(feature_dict) -> 0/1/-1. Data/extras prebuilt by the caller."""
    n = len(bars["close"])
    sig = np.zeros(n, dtype=np.int8)
    for j in range(n):
        f = feat_fn(bars, extras, j)
        sig[j] = 0 if (f is None or f["value"] is None
                       or not np.isfinite(f["value"])) else sign_of(f)
    return sig


# ------------------------------------------------------- cheap screens

def fwd_screen(cond, bars, horizons=(30, 60, 120, 240)):
    """Non-overlapping conditional fwd mid returns per horizon.
    Entry proxy: next bar open; exit: close[i+h]. Returns dict h->(N, mean, t)."""
    close, opn = bars["close"], bars["open"]
    n = len(close)
    idx = np.flatnonzero(cond)
    out = {}
    for h in horizons:
        if len(idx) == 0:
            out[h] = (0, np.nan, np.nan)
            continue
        j0 = np.minimum(idx + 1, n - 1)
        j1 = np.minimum(idx + h, n - 1)
        r = (close[j1] - opn[j0]) / PIP
        keep, last = [], -10 ** 9
        for k, i in enumerate(idx):
            if i >= last + h:
                keep.append(k)
                last = i
        rr = r[np.array(keep)]
        mean = float(rr.mean())
        t = mean / (rr.std(ddof=1) / np.sqrt(len(rr))) if len(rr) > 1 else np.nan
        out[h] = (len(rr), round(mean, 3), round(float(t), 2))
    return out


def monthly_consistency(sig, bars, months, hold=120):
    """Coarse monthly sign check of a condition via nonoverlap fwd returns."""
    out = {}
    idx = np.flatnonzero(sig != 0)
    n = len(bars["close"])
    j0 = np.minimum(idx + 1, n - 1)
    j1 = np.minimum(idx + hold, n - 1)
    r = (bars["close"][j1] - bars["open"][j0]) / PIP
    mon = months[np.minimum(idx + 1, n - 1)]
    for m in np.unique(mon):
        sel = r[mon == m]
        if len(sel) >= 5:
            out[int(m)] = round(float(sel.mean()), 2)
    return out
