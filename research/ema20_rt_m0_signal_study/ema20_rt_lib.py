#!/usr/bin/env python3
"""EMA20-RT-M0 library: EMA20 reclaim -> first retest signal study (LONG only).

Frozen rules live in `EMA20_RT_M0_FROZEN_SPEC.md` (committed BEFORE any
outcome). Validated MTF-M1 components are REUSED, not reimplemented:
`mtf_lib` (TickStore with the 2019+ hard guard, GAP LIST tools, EMA,
bootstrap CI95, remove_best_1pct).

Units: timestamps int64 ns UTC; prices float64; 1 pip = 1e-4.
"""
import os
import sys

import numpy as np
import pandas as pd

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(REPO, "research", "mtf_m1_tick_execution"))
sys.path.insert(0, os.path.join(REPO, "research", "tick_m1_microstructure"))

import mtf_lib as L  # noqa: E402

PIP = L.PIP
NS = L.NS
DISCOVERY_END_NS = L.DISCOVERY_END_NS
YEARS = L.YEARS

EMA_PERIOD = 20                          # frozen
ENTRY_LATENCY_NS = L.LATENCY_NS          # frozen: 250 ms
NO_FILL_WINDOW_NS = 60 * NS              # frozen: NO_FILL after 60 s
HORIZON_MIN = (15, 30, 60, 120, 240)     # frozen
HORIZON_NS = {h: h * 60 * NS for h in HORIZON_MIN}
NON_OVERLAP_NS = 4 * 3600 * NS           # frozen: NON_OVERLAP_4H
GATE_HORIZONS = (30, 60, 120, 240)       # frozen: 15m can never pass


# ------------------------------------------------------------------ bars

def load_m15_bars(ddir):
    """Frozen bar series: validated M15 MID bars, gap-flagged bars REMOVED
    (same convention as MTF-M1). Raises if a bar label sits at/after the
    2019 hard cut."""
    df = pd.read_parquet(os.path.join(ddir, "bars_M15.parquet"))
    keep = ~df["gap_flag"].to_numpy(dtype=bool)
    bar = {("start" if k == "start_ns" else k): df[k].to_numpy()
           for k in ("start_ns", "open", "high", "low", "close", "n_ticks")}
    bar = {k: v[keep] for k, v in bar.items()}
    bar["close_ts"] = bar["start"] + L.TF_NS["M15"]
    if len(bar["start"]) and bar["start"][-1] >= DISCOVERY_END_NS:
        raise AssertionError("bar label at/after the 2019 hard cut")
    return bar


def ema20_of_closes(close):
    """Frozen EMA20 on completed M15 mid closes (validated mtf_lib.ema)."""
    return L.ema(close, EMA_PERIOD)


def reclaim_mask(close, ema):
    """Frozen LONG reclaim: bar i (with predecessor) satisfies
    CLOSE[i-1] <= EMA20[i-1] AND CLOSE[i] > EMA20[i]. Element 0 is False."""
    rec = np.zeros(len(close), dtype=bool)
    if len(close) >= 2:
        rec[1:] = (close[:-1] <= ema[:-1]) & (close[1:] > ema[1:])
    return rec


# ------------------------------------------------------- setup state machine

def scan_retest(store, scan_start, scan_end, prev0_mid, ema, bar_close_ts):
    """Frozen retest scan over ticks in [scan_start, scan_end): FIRST tick
    where prev_mid > active_EMA AND mid <= active_EMA. Active EMA at a tick =
    EMA20 of the latest completed bar with close_ts <= tick ts. The first
    scanned tick's predecessor is by construction the reclaim bar's close
    tick (`prev0_mid` = reclaim close > EMA). Returns
    (retest_ts, retest_mid, active_ema, prev_mid) or None."""
    if scan_end <= scan_start:
        return None
    ts, bid, ask = store.get_range(scan_start, scan_end)
    if ts.size == 0:
        return None
    mid = (bid + ask) / 2.0
    idx = np.searchsorted(bar_close_ts, ts, side="right") - 1
    ema_ref = ema[idx]
    prev_mid = np.empty(mid.size, dtype=np.float64)
    prev_mid[0] = prev0_mid
    prev_mid[1:] = mid[:-1]
    cross = np.flatnonzero((prev_mid > ema_ref) & (mid <= ema_ref))
    if cross.size == 0:
        return None
    k = int(cross[0])
    return int(ts[k]), float(mid[k]), float(ema_ref[k]), float(prev_mid[k])


def resolve_entry(store, event_ts):
    """Frozen entry: first ASK tick with ts >= event+250ms; NO_FILL if none
    within event+250ms+60s (window inclusive at the far end)."""
    t0 = event_ts + ENTRY_LATENCY_NS
    bound = event_ts + ENTRY_LATENCY_NS + NO_FILL_WINDOW_NS
    ts, bid, ask = store.get_range(t0, bound + 1)
    if ts.size == 0:
        return {"status": "NO_FILL"}
    return {"status": "FILLED", "entry_ts": int(ts[0]),
            "ask": float(ask[0]), "bid": float(bid[0]),
            "mid": float((bid[0] + ask[0]) / 2.0)}


def sweep_setups(store, close, close_ts, ema):
    """Frozen state machine sweep. One ARMED_LONG setup at a time; reclaims
    while armed (or while a resolution blocks them, close_ts <= cursor) are
    ignored; armed setup ends at FIRST retest tick or at the close time of
    the first later bar closing strictly below EMA20 (invalidation evaluated
    first at equal timestamps: the retest window is [reclaim_ts, T_END)).
    Returns (events, counts)."""
    rec = reclaim_mask(close, ema)
    below = close < ema
    reclaim_idx = np.flatnonzero(rec)
    counts = {"N_RECLAIM_BARS": int(reclaim_idx.size), "N_RECLAIMS": 0,
              "N_RETESTS": 0, "N_INVALIDATED_BEFORE_RETEST": 0,
              "N_NO_FILL": 0, "N_UNRESOLVED_AT_END": 0}
    events = []
    cursor = np.int64(-1)
    ri, n_recl = 0, reclaim_idx.size
    while ri < n_recl:
        i = int(reclaim_idx[ri])
        if close_ts[i] <= cursor:
            ri += 1
            continue
        counts["N_RECLAIMS"] += 1
        nxt = np.flatnonzero(below[i + 1:])
        if nxt.size:
            t_end = int(close_ts[i + 1 + int(nxt[0])])
        else:
            t_end = DISCOVERY_END_NS
        r = scan_retest(store, int(close_ts[i]), t_end, float(close[i]),
                        ema, close_ts)
        if r is None:
            if t_end >= DISCOVERY_END_NS:
                counts["N_UNRESOLVED_AT_END"] += 1
            else:
                counts["N_INVALIDATED_BEFORE_RETEST"] += 1
            cursor = np.int64(t_end)
        else:
            rt_ts, rt_mid, ema_ref, prev_mid = r
            counts["N_RETESTS"] += 1
            er = resolve_entry(store, rt_ts)
            ev = {
                "reclaim_bar": i,
                "reclaim_ts": int(close_ts[i]),
                "reclaim_close": float(close[i]),
                "ema_at_reclaim": float(ema[i]),
                "retest_ts": int(rt_ts),
                "retest_mid": float(rt_mid),
                "active_ema_at_retest": ema_ref,
                "prev_mid_at_retest": prev_mid,
                "bars_reclaim_to_retest": int(
                    np.searchsorted(close_ts, rt_ts, side="right")
                    - np.searchsorted(close_ts, int(close_ts[i]), side="right")),
                "minutes_reclaim_to_retest": (rt_ts - int(close_ts[i]))
                / (60.0 * NS),
                "entry_status": er["status"],
            }
            if er["status"] == "FILLED":
                ev["entry_ts"] = er["entry_ts"]
                ev["entry_ask"] = er["ask"]
                ev["entry_bid"] = er["bid"]
                ev["entry_mid"] = er["mid"]
                ev["entry_year"] = int(pd.Timestamp(er["entry_ts"],
                                                    tz="UTC").year)
            else:
                counts["N_NO_FILL"] += 1
            events.append(ev)
            cursor = np.int64(rt_ts)
        while ri < n_recl and close_ts[int(reclaim_idx[ri])] <= cursor:
            ri += 1
    return events, counts


# ------------------------------------------------------------- horizons

def resolve_horizons(store, ev, gap_intervals):
    """Frozen horizons: exit = first BID tick with ts >= entry+H
    (NOT_MEASURABLE if entry+H >= hard cut or no tick exists before the
    dataset end); GAP_INVALID if a GAP LIST interval (g1,g2) satisfies
    g1 < exit_ts AND g2 > entry_ts (per horizon only)."""
    hor = {}
    if ev["entry_status"] != "FILLED":
        return hor
    entry_ts = ev["entry_ts"]
    for h in HORIZON_MIN:
        target = entry_ts + HORIZON_NS[h]
        if target >= DISCOVERY_END_NS:
            hor[h] = {"status": "NOT_MEASURABLE"}
            continue
        pad = 4 * 86400 * NS
        exit_k = None
        while True:
            end_bound = min(target + pad + NS, DISCOVERY_END_NS)
            ts, bid, ask = store.get_range(entry_ts, end_bound)
            j = int(np.searchsorted(ts, target, side="left"))
            if j < ts.size:
                exit_k = j
                break
            if end_bound >= DISCOVERY_END_NS:
                break
            pad *= 4
        if exit_k is None:
            hor[h] = {"status": "NOT_MEASURABLE"}
            continue
        exit_ts = int(ts[exit_k])
        gap_hit = False
        for g1, g2 in gap_intervals:
            if g1 >= exit_ts:
                break
            if g2 > entry_ts:
                gap_hit = True
                break
        if gap_hit:
            hor[h] = {"status": "GAP_INVALID"}
            continue
        exit_bid = float(bid[exit_k])
        exit_mid = float((bid[exit_k] + ask[exit_k]) / 2.0)
        hor[h] = {"status": "OK", "exit_ts": exit_ts, "exit_bid": exit_bid,
                  "exit_mid": exit_mid,
                  "net_pips": (exit_bid - ev["entry_ask"]) / PIP,
                  "mid_pips": (exit_mid - ev["entry_mid"]) / PIP,
                  "exit_year": int(pd.Timestamp(exit_ts, tz="UTC").year)}
    return hor


# -------------------------------------------------------------- metrics

def horizon_metrics(nets, mids, years):
    """Frozen metric block for one horizon. Raw values are kept in `_raw`
    for exact gate evaluation; rounded values are for display/JSON only."""
    nets = np.asarray(nets, dtype=np.float64)
    mids = np.asarray(mids, dtype=np.float64)
    years = np.asarray(years, dtype=np.int64)
    n = nets.size
    out = {"N": int(n)}
    if n == 0:
        return out
    ci_lo, ci_hi = L.bootstrap_ci95(nets)
    by_year, pos = {}, 0
    for y in YEARS:
        m = years == y
        if not m.any():
            by_year[str(y)] = None
            continue
        mean_y = float(nets[m].mean())
        by_year[str(y)] = {"N": int(m.sum()),
                           "MEAN_NET": round(mean_y, 4),
                           "MEDIAN_NET": round(float(np.median(nets[m])), 4),
                           "WIN_RATE": round(float((nets[m] > 0).mean()), 4)}
        if mean_y > 0:
            pos += 1
    std = float(nets.std(ddof=1)) if n > 1 else float("nan")
    out.update({
        "MEAN_MID_RETURN_PIPS": round(float(mids.mean()), 4),
        "MEDIAN_MID_RETURN_PIPS": round(float(np.median(mids)), 4),
        "MEAN_EXECUTABLE_NET_PIPS": round(float(nets.mean()), 4),
        "MEDIAN_EXECUTABLE_NET_PIPS": round(float(np.median(nets)), 4),
        "WIN_RATE_NET": round(float((nets > 0).mean()), 4),
        "STD": round(std, 4), "STANDARD_ERROR": round(std / np.sqrt(n), 4),
        "CI95_LO": round(ci_lo, 4), "CI95_HI": round(ci_hi, 4),
        "POSITIVE_YEARS": pos,
        "BY_YEAR": by_year,
        "REMOVE_BEST_1_PERCENT_NET_MEAN": round(L.remove_best_1pct(nets), 4),
        "_raw": {"nets": nets, "mean_net": float(nets.mean()),
                 "median_net": float(np.median(nets)),
                 "remove_best": float(L.remove_best_1pct(nets)),
                 "ci_lo": ci_lo, "positive_years": pos, "n": int(n)},
    })
    return out


def non_overlap_keep(entry_ts_list, window_ns=NON_OVERLAP_NS):
    """Frozen NON_OVERLAP_4H greedy: keep an event iff its entry occurs at or
    after last_kept_entry + 4h. `entry_ts_list` must be chronological."""
    keep, last = [], None
    for k, t in enumerate(entry_ts_list):
        if last is None or int(t) >= last + window_ns:
            keep.append(k)
            last = int(t)
    return keep


def signal_gate(metrics_by_h, nonoverlap_by_h):
    """Frozen §12 gate evaluated on RAW (unrounded) values. Returns the list
    of passing horizons; 15m can never pass."""
    passed = []
    for h in GATE_HORIZONS:
        m = (metrics_by_h.get(h) or {}).get("_raw", {})
        no = (nonoverlap_by_h.get(h) or {}).get("_raw", {})
        if (m.get("n", 0) >= 500
                and m.get("mean_net", -1e18) >= 1.5
                and m.get("median_net", -1e18) > 0
                and m.get("positive_years", -1) >= 6
                and m.get("remove_best", -1e18) > 0
                and m.get("ci_lo", -1e18) > 0
                and no.get("mean_net", -1e18) > 0):
            passed.append(h)
    return passed


def strip_raw(obj):
    """JSON-safe copy without `_raw` / numpy scalars."""
    if isinstance(obj, dict):
        return {k: strip_raw(v) for k, v in obj.items() if k != "_raw"}
    if isinstance(obj, (list, tuple)):
        return [strip_raw(v) for v in obj]
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    return obj
