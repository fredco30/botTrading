#!/usr/bin/env python3
"""CAUSAL_MOMENTUM_M1 library — STRICT CAUSAL retest of the momentum finding.

Self-contained. Signal logic written fresh from CAUSAL_MOMENTUM_M1 spec;
does NOT import or replicate the contaminated feature construction of PR #42.
Only the validated data layer (mtf_lib TickStore / gap rule, LAB_AUDIT_M0
LAB_PASS) is reused, via validated/mtf_lib.py.

Units: ns timestamps UTC, float64 prices, 1 pip = 1e-4. 1R = 15 pips.
"""
import os
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
import validated_mtf_lib as mtf_lib  # validated data layer (LAB_PASS)

NS = mtf_lib.NS
PIP = mtf_lib.PIP
STORE = mtf_lib.STORE if hasattr(mtf_lib, "STORE") else None
SYMBOL = "EURUSD"
DATA_ROOT = "E:/ResearchData/botTrading/ticks/parquet"

LATENCY_NS = 5 * NS            # mission 9: baseline entry delay
ENTRY_WAIT_NS = 30 * NS        # mission 7: max entry wait after the delay
SL_PIPS = 15.0                 # frozen parameters (mission 10)
TP_PIPS = 15.0
T_EXIT_MIN = 120
THR_PIPS = 10.0
R_PIPS = SL_PIPS               # 1R = 15 pips (mission 18)

CACHE = os.path.join(HERE, "cache")
os.makedirs(CACHE, exist_ok=True)


def load_year(year):
    """Raw ticks for one calendar year via the validated store. Only years
    explicitly passed by the caller are opened (no internal year ranges)."""
    f = os.path.join(CACHE, f"ticks_{year}.npz")
    if os.path.exists(f):
        z = np.load(f)
        return z["ts"], z["bid"], z["ask"]
    parts = []
    for m in range(1, 13):
        df = mtf_lib.read_month_ticks(DATA_ROOT, SYMBOL, year, m)
        if df is not None:
            parts.append((df["timestamp_utc"].astype("int64").to_numpy(),
                          df["bid"].to_numpy(np.float64),
                          df["ask"].to_numpy(np.float64)))
    ts = np.concatenate([p[0] for p in parts])
    bid = np.concatenate([p[1] for p in parts])
    ask = np.concatenate([p[2] for p in parts])
    np.savez_compressed(f, ts=ts, bid=bid, ask=ask)
    return ts, bid, ask


def load_half_year(year, months):
    """Raw ticks for a month subset (confirmation uses this)."""
    f = os.path.join(CACHE, f"ticks_{year}_m{months[0]:02d}-{months[-1]:02d}.npz")
    if os.path.exists(f):
        z = np.load(f)
        return z["ts"], z["bid"], z["ask"]
    parts = []
    for m in months:
        df = mtf_lib.read_month_ticks(DATA_ROOT, SYMBOL, year, m)
        if df is not None:
            parts.append((df["timestamp_utc"].astype("int64").to_numpy(),
                          df["bid"].to_numpy(np.float64),
                          df["ask"].to_numpy(np.float64)))
    ts = np.concatenate([p[0] for p in parts])
    bid = np.concatenate([p[1] for p in parts])
    ask = np.concatenate([p[2] for p in parts])
    np.savez_compressed(f, ts=ts, bid=bid, ask=ask)
    return ts, bid, ask


# ------------------------------------------------------------------ bars

def m1_bars(ts, bid, ask):
    """M1 bars, left-labelled [t, t+60s). close_time = start+60s (nominal).
    last_tick_ts = actual timestamp of the final tick in the bar (this is the
    timestamp of the close actually used by features)."""
    mid = (bid + ask) / 2.0
    tf = 60 * NS
    ids = ts // tf
    bounds = np.flatnonzero(np.diff(ids)) + 1
    si = np.concatenate(([0], bounds))
    ei = np.concatenate((bounds, [len(ts)]))
    return {
        "start": (ids[si] * tf).astype(np.int64),
        "close_time": (ids[si] * tf + tf).astype(np.int64),
        "open": mid[si],
        "high": np.maximum.reduceat(mid, si),
        "low": np.minimum.reduceat(mid, si),
        "close": mid[ei - 1],
        "close_bid": bid[ei - 1], "close_ask": ask[ei - 1],
        "last_tick_ts": ts[ei - 1],
    }


def h4_closes(close_time, close):
    """Completed-H4-bar closes on the UTC 4h grid. Bar g spans [4h*g, 4h*(g+1));
    its END is 4h*(g+1) and its close is the last M1 close inside it.
    Returns (end_ts, close) arrays, one row per observed bar, sorted."""
    g = (close_time - 1) // (4 * 3600 * NS)     # bucket of the M1 close
    ug, first = np.unique(g, return_index=True)
    # last M1 close per bucket:
    idx = np.searchsorted(g, ug, side="right") - 1
    ends = (ug + 1) * 4 * 3600 * NS
    return ends.astype(np.int64), close[idx], idx


# -------------------------------------------------------------- features
# Both features are SCALAR functions of (arrays, decision index). The vector
# paths used by the replay are thin loops over these; this guarantees the
# audited scalar logic IS the production logic.

def mom4h_rolling(bars, j):
    """H1 MOM4H_ROLLING at decision index j (decision at bars.close_time[j]).

    current   = MID close of the just-completed M1 bar ending at T
    reference = last completed M1 MID close with close_time <= T-4h
    Returns (mom_pips, current_ts_used, reference_ts_used) where the *_ts_used
    are the ACTUAL tick timestamps of the closes consumed."""
    T = int(bars["close_time"][j])
    cur = float(bars["close"][j])
    cur_ts = int(bars["last_tick_ts"][j])
    ref_t = T - 4 * 3600 * NS
    k = int(np.searchsorted(bars["close_time"], ref_t, side="right")) - 1
    if k < 0:
        return None
    ref = float(bars["close"][k])
    ref_ts = int(bars["last_tick_ts"][k])
    return ((cur - ref) / PIP, cur_ts, ref_ts)


def mom16h_h4_completed(bars, j, h4_end, h4_close, h4_last_tick_ts):
    """H2 MOM16H_H4_COMPLETED at decision index j.

    Uses ONLY fully completed H4 bars whose END <= T (T = M1 close_time[j]).
    C0 = close of the latest completed H4 bar; C4 = close of the bar four
    H4 slots before C0. ~16 clock hours close-to-close (labelled honestly)."""
    T = int(bars["close_time"][j])
    c0i = int(np.searchsorted(h4_end, T, side="right")) - 1
    if c0i < 4:
        return None
    c0_ts = int(h4_last_tick_ts[c0i])
    c4_ts = int(h4_last_tick_ts[c0i - 4])
    mom = (float(h4_close[c0i]) - float(h4_close[c0i - 4])) / PIP
    return (mom, c0_ts, c4_ts)


def signal_of(mom):
    if mom is None:
        return 0
    if mom > THR_PIPS:
        return 1
    if mom < -THR_PIPS:
        return -1
    return 0


def signals_all(bars, h4, which):
    """Vector of directions (0/1/-1) for every M1 decision index.
    h4 = (h4_end, h4_close, h4_last_tick_ts)."""
    out = np.zeros(len(bars["close"]), dtype=np.int8)
    for j in range(len(out)):
        if which == "H1":
            m = mom4h_rolling(bars, j)
        else:
            m = mom16h_h4_completed(bars, j, *h4)
        out[j] = signal_of(m[0] if m else None)
    return out


# --------------------------------------------------------------- replay

def replay(ts, bid, ask, bars, sig, latency_ns=LATENCY_NS,
           slip_pips=0.0, wait_ns=ENTRY_WAIT_NS):
    """Frozen execution of a signal vector over the tick series.

    Entry: first tick in [decision+latency, decision+latency+wait) on the
    execution side (LONG ASK / SHORT BID) + adverse slip.
    Exit: first event wins, STOP priority; gap-through stop fills at the
    actual adverse tick; target capped; time exit on the executable side;
    every fill pays adverse slip. No gap invalidation (spec 8)."""
    slip = slip_pips * PIP
    n = len(bars["close"])
    trades = []
    no_fill = 0
    last_exit_ts = -1        # signals with decision_ts < last_exit_ts are ignored
    for j in range(n):
        side = int(sig[j])
        if side == 0:
            continue
        d = int(bars["close_time"][j])
        if d < last_exit_ts:
            continue         # position still open: signal ignored
        i0 = int(np.searchsorted(ts, d + latency_ns, side="left"))
        i1 = int(np.searchsorted(ts, d + latency_ns + wait_ns, side="left"))
        if i0 >= i1:
            no_fill += 1
            continue
        k = i0
        entry = float(ask[k] if side == 1 else bid[k]) + (slip if side == 1 else -slip)
        stop = entry - side * SL_PIPS * PIP
        tgt = entry + side * TP_PIPS * PIP
        t_end = int(ts[k]) + T_EXIT_MIN * 60 * NS
        # walk ticks after entry
        m = k + 1
        nts = len(ts)
        exit_ts = None
        while m < nts and ts[m] <= t_end:
            if side == 1:
                if bid[m] <= stop:
                    exit_ts, exit_px, reason = int(ts[m]), float(bid[m]) - slip, "STOP"
                    break
                if bid[m] >= tgt:
                    exit_ts, exit_px, reason = int(ts[m]), float(tgt) - slip, "TARGET"
                    break
            else:
                if ask[m] >= stop:
                    exit_ts, exit_px, reason = int(ts[m]), float(ask[m]) + slip, "STOP"
                    break
                if ask[m] <= tgt:
                    exit_ts, exit_px, reason = int(ts[m]), float(tgt) + slip, "TARGET"
                    break
            m += 1
        if exit_ts is None:
            if m >= nts:                       # dataset tail
                m = nts - 1
            exit_ts = int(ts[m])
            exit_px = float(bid[m] if side == 1 else ask[m])
            exit_px += -slip if side == 1 else slip
            reason = "TIME"
        net = side * (exit_px - entry) / PIP
        trades.append({"j": int(j), "side": side, "decision_ts": d,
                       "entry_idx": int(k), "entry_ts": int(ts[k]),
                       "entry": entry, "exit_ts": exit_ts, "exit_px": exit_px,
                       "reason": reason, "net_pips": float(net),
                       "r": float(net / R_PIPS)})
        last_exit_ts = exit_ts
    return trades, no_fill


def common_sample(base_trades, stress_trades):
    """Intersection on decision index (same signal). Returns (base_common,
    stress_common) aligned lists."""
    bmap = {t["j"]: t for t in base_trades}
    smap = {t["j"]: t for t in stress_trades}
    keys = sorted(set(bmap) & set(smap))
    return [bmap[k] for k in keys], [smap[k] for k in keys]


# -------------------------------------------------------------- metrics

def pf_of(net):
    wins = net[net > 0]
    losses = net[net < 0]
    if len(losses) and losses.sum() != 0:
        return float(min(wins.sum() / abs(losses.sum()), 999.0))
    return 999.0


def remove_best_1pct(x):
    x = np.sort(np.asarray(x, dtype=np.float64))
    n = len(x)
    k = max(1, int(np.ceil(0.01 * n)))
    if k >= n:
        return float("nan")
    return float(x[:n - k].mean())


def bootstrap_ci95_r(r, n_res=2000, seed=42):
    rng = np.random.default_rng(seed)
    x = np.asarray(r, dtype=np.float64)
    n = len(x)
    if n == 0:
        return (float("nan"), float("nan"))
    means = np.empty(n_res)
    for i in range(n_res):
        means[i] = x[rng.integers(0, n, n)].mean()
    return (float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5)))


def metrics(trades, months_of_bar, label):
    out = {"label": label}
    if not trades:
        return {"label": label, "N": 0, "VERDICT": "NO_TRADES"}
    net = np.array([t["net_pips"] for t in trades])
    r = np.array([t["r"] for t in trades])
    mon = np.array([months_of_bar[t["j"]] for t in trades])
    pos_months = len({m for m, tot in
                      ((m, net[mon == m].sum()) for m in np.unique(mon)) if tot > 0})
    cum = np.cumsum(r)
    peak = np.maximum.accumulate(cum)
    consec = best = 0
    for v in r:
        consec = consec + 1 if v < 0 else 0
        best = max(best, consec)
    lr = r[[i for i, t in enumerate(trades) if t["side"] == 1]]
    sr = r[[i for i, t in enumerate(trades) if t["side"] == -1]]
    ci = bootstrap_ci95_r(r)
    out.update({
        "N": len(trades), "UNIT_N": "COUNT",
        "trades_per_month": round(len(trades) / 12.0, 2),
        "mean_pips": round(float(net.mean()), 3), "UNIT_mean": "PIPS",
        "median_pips": round(float(np.median(net)), 3), "UNIT_median": "PIPS",
        "total_pips": round(float(net.sum()), 2), "UNIT_total": "PIPS",
        "PF": round(pf_of(net), 3),
        "expectancy_r": round(float(r.mean()), 4), "UNIT_expR": "R",
        "win_rate": round(float((net > 0).mean()), 4), "UNIT_wr": "PERCENT_FRACTION",
        "pos_months": pos_months, "UNIT_pos_months": "COUNT_of_12",
        "long_r": round(float(lr.mean()), 4) if len(lr) else None, "UNIT_long": "R",
        "short_r": round(float(sr.mean()), 4) if len(sr) else None, "UNIT_short": "R",
        "remove_best": round(remove_best_1pct(net), 3), "UNIT_rb": "PIPS",
        "ci95_r": (round(ci[0], 4), round(ci[1], 4)), "UNIT_ci": "R",
        "max_dd_r": round(float((peak - cum).max()) if len(cum) else 0.0, 2),
        "UNIT_dd": "R",
        "max_consec_losses": int(best), "UNIT_streak": "COUNT",
        "exits": {s: sum(1 for t in trades if t["reason"] == s)
                  for s in ("STOP", "TARGET", "TIME")},
    })
    return out


def gate_check(m):
    """Mission 12 discovery gate. Returns (bool, failed_clauses)."""
    fails = []
    if m.get("N", 0) < 500: fails.append("N<500")
    if not (m.get("mean_pips", -9) >= 0.75): fails.append("mean<+0.75p")
    if not (m.get("PF", 0) >= 1.20): fails.append("PF<1.20")
    if not (m.get("expectancy_r", -9) >= 0.05): fails.append("expR<+0.05")
    if not (m.get("total_pips", -9) > 0): fails.append("total<=0")
    if m.get("pos_months", 0) < 8: fails.append("pos_months<8")
    if not (m.get("long_r", -9) or 0 > 0): fails.append("LONG_R<=0")
    if not (m.get("short_r", -9) or 0 > 0): fails.append("SHORT_R<=0")
    if not (m.get("remove_best", -9) > 0): fails.append("remove_best<=0")
    return (len(fails) == 0, fails)
