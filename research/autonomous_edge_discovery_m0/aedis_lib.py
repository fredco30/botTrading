#!/usr/bin/env python3
"""AUTONOMOUS-EDGE-DISCOVERY-M0 library.

Fast research sandbox on EURUSD 2017H1 (discovery) / 2017H2 (confirmation).
Reuses the validated TickStore/bar/execution primitives from mtf_lib.py
(LAB_AUDIT_M0: LAB_PASS) via import; window guards are narrowed to 2017.

Units: ns timestamps UTC, float64 prices, 1 pip = 1e-4.
"""
import os
import numpy as np
import pandas as pd

import mtf_lib

NS = mtf_lib.NS
PIP = mtf_lib.PIP

STORE = "E:/ResearchData/botTrading/ticks/parquet"
SYMBOL = "EURUSD"

# mission windows
DISC_START = int(pd.Timestamp("2017-01-01T00:00:00Z").value)
DISC_END = int(pd.Timestamp("2017-07-01T00:00:00Z").value)
CONF_START = DISC_END
CONF_END = int(pd.Timestamp("2018-01-01T00:00:00Z").value)

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache")
os.makedirs(CACHE, exist_ok=True)

# execution (mission §6): 5 s baseline delay, 30 s stress latency,
# 0.50 pip adverse slippage per side stress
LATENCY_NS = 5 * NS
LATENCY_STRESS_NS = 30 * NS
SLIP_STRESS = 0.50 * PIP


def month_arrays(year, month):
    """bid/ask arrays for one month (validated TickStore, 2017 only)."""
    assert year == 2017, "AUTONOMOUS_EDGE_DISCOVERY_M0: 2017 only"
    df = mtf_lib.read_month_ticks(STORE, SYMBOL, year, month)
    if df is None:
        return (np.array([], dtype=np.int64), np.array([]), np.array([]))
    return (df["timestamp_utc"].astype("int64").to_numpy(),
            df["bid"].to_numpy(np.float64),
            df["ask"].to_numpy(np.float64))


def load_half(half):
    """Load one half-year of ticks; cached npz. half in {'H1','H2'}."""
    assert half in ("H1", "H2")
    f = os.path.join(CACHE, f"ticks_2017{half}.npz")
    if os.path.exists(f):
        z = np.load(f)
        return z["ts"], z["bid"], z["ask"]
    parts = []
    months = range(1, 7) if half == "H1" else range(7, 13)
    for m in months:
        parts.append(month_arrays(2017, m))
    ts = np.concatenate([p[0] for p in parts])
    bid = np.concatenate([p[1] for p in parts])
    ask = np.concatenate([p[2] for p in parts])
    np.savez_compressed(f, ts=ts, bid=bid, ask=ask)
    return ts, bid, ask


def m1_bars(ts, bid, ask):
    """M1 mid OHLC + per-bar first/last bid/ask, tick count, mean spread.
    Left-labelled [t, t+60s)."""
    mid = (bid + ask) / 2.0
    tf = 60 * NS
    ids = ts // tf
    bounds = np.flatnonzero(np.diff(ids)) + 1
    si = np.concatenate(([0], bounds))
    ei = np.concatenate((bounds, [len(ts)]))
    spread = ask - bid
    return {
        "start": (ids[si] * tf).astype(np.int64),
        "open": mid[si], "high": np.maximum.reduceat(mid, si),
        "low": np.minimum.reduceat(mid, si), "close": mid[ei - 1],
        "open_bid": bid[si], "open_ask": ask[si],
        "close_bid": bid[ei - 1], "close_ask": ask[ei - 1],
        "n_ticks": (ei - si).astype(np.int64),
        "spread_mean": np.add.reduceat(spread, si) / (ei - si),
    }


def save_bars(half):
    ts, bid, ask = load_half(half)
    b = m1_bars(ts, bid, ask)
    np.savez_compressed(os.path.join(CACHE, f"m1_2017{half}.npz"), **b)
    return b


def load_bars(half):
    f = os.path.join(CACHE, f"m1_2017{half}.npz")
    if not os.path.exists(f):
        return save_bars(half)
    z = np.load(f)
    return {k: z[k] for k in z.files}


def hhmm(ts):
    """UTC hour-of-day*100+minute int array for ns timestamps."""
    secs = ts // NS
    return (((secs // 3600) % 24).astype(np.int64) * 100
            + (secs % 3600) // 60)


def fwd_ret(b, i, horizon_min):
    """Forward mid return in pips from decision at close of bar i (entry
    approximated at open of bar i+1) to close of bar i+horizon_min.
    Causal: uses only future data relative to the decision, never before."""
    n = len(b["close"])
    j0 = np.minimum(i + 1, n - 1)
    j1 = np.minimum(i + horizon_min, n - 1)
    return (b["close"][j1] - b["open"][j0]) / PIP


def event_stats(rets, label, ledger, family, params, cost_rt=0.7):
    """Summary of a conditional forward-return screen. cost_rt = round-trip
    cost proxy in pips (spread + slip)."""
    r = np.asarray(rets, dtype=np.float64)
    n = len(r)
    if n == 0:
        row = dict(experiment_id=label, family_id=family, parameters=params,
                   N=0, mean_pips=np.nan, tstat=np.nan, net_proxy=np.nan,
                   win_rate=np.nan, status="NO_EVENTS", reason="no events")
        ledger.append(row)
        return row
    mean = float(r.mean())
    sd = float(r.std(ddof=1)) if n > 1 else np.nan
    t = mean / (sd / np.sqrt(n)) if sd and sd > 0 else np.nan
    row = dict(experiment_id=label, family_id=family, parameters=params,
               N=n, mean_pips=round(mean, 3), tstat=round(float(t), 2),
               net_proxy=round(mean - cost_rt, 3),
               win_rate=round(float((r > 0).mean()), 3),
               status="SCREEN", reason="conditional fwd return")
    ledger.append(row)
    return row


# ------------------------------------------------------------------ sim

def sim_trades_m1(b, sig_idx, side, stop_pips, tp_pips, t_max_min,
                  slippage_pips=0.0, cost_mode="spread"):
    """Fast M1-bar trade simulator for screening.

    Decision at close of bar i (sig_idx). Entry at bar i+1 open on the
    execution side (long: ask, short: bid). Stop/target resolved on bar
    high/low with stop-priority when both are touched in one bar.
    Time exit at close of entry bar + t_max_min. Exit on the execution side
    (long: bid, short: ask). Costs: real per-bar spread (entry/exit side) +
    slippage per side. Returns list of trade dicts.
    """
    o, h, l, c = b["open"], b["high"], b["low"], b["close"]
    ob_a, ob_b = b["open_ask"], b["open_bid"]
    cl_b, cl_a = b["close_bid"], b["close_ask"]
    n = len(o)
    out = []
    sp = slippage_pips * PIP
    for i in sig_idx:
        j = i + 1
        if j >= n:
            continue
        if side == 1:
            entry = ob_a[j] + sp
            stop, tgt = entry - stop_pips * PIP, entry + tp_pips * PIP
            js = j + t_max_min
            exit_px = None
            # walk bars until stop/target/time
            k_end = min(js, n - 1)
            k = j
            while k <= k_end:
                if l[k] <= stop:
                    exit_px = stop
                    break
                if h[k] >= tgt:
                    exit_px = tgt
                    break
                k += 1
            if exit_px is None:
                k = k_end
                exit_px = cl_b[k] - sp
            net = (exit_px - entry) / PIP
        else:
            entry = ob_b[j] - sp
            stop, tgt = entry + stop_pips * PIP, entry - tp_pips * PIP
            js = j + t_max_min
            exit_px = None
            k_end = min(js, n - 1)
            k = j
            while k <= k_end:
                if h[k] >= stop:
                    exit_px = stop
                    break
                if l[k] <= tgt:
                    exit_px = tgt
                    break
                k += 1
            if exit_px is None:
                k = k_end
                exit_px = cl_a[k] + sp
            net = (entry - exit_px) / PIP
        out.append({"i": int(i), "net_pips": float(net)})
    return out


def sim_metrics(trades, label, ledger, family, params):
    nt = np.array([t["net_pips"] for t in trades], dtype=np.float64)
    n = len(nt)
    if n == 0:
        row = dict(experiment_id=label, family_id=family, parameters=params,
                   N=0, mean_pips=np.nan, PF=np.nan, expectancy_R=np.nan,
                   stress_R=np.nan, remove_best=np.nan, status="NO_TRADES",
                   reason="no trades")
        ledger.append(row)
        return row
    wins = nt[nt > 0]
    losses = nt[nt < 0]
    pf = float(wins.sum() / abs(losses.sum())) if len(losses) and losses.sum() else float("inf")
    pf = min(pf, 999.0)
    # risk = stop distance approximated by median loss when stopped; use
    # stop_pips passed via params dict? simpler: R-units computed by caller
    # when stop known; here report pip stats.
    rb = mtf_lib.remove_best_1pct(nt)
    row = dict(experiment_id=label, family_id=family, parameters=params,
               N=n, mean_pips=round(float(nt.mean()), 3),
               PF=round(pf, 3), expectancy_R=np.nan,
               stress_R=round(float(nt.mean()) - 1.0, 3),
               remove_best=round(float(rb), 3), status="SIM",
               reason="M1 sim, 1.0 pip/side stress deduction")
    ledger.append(row)
    return row


# ------------------------------------------------------- tick execution

def tick_entry(ts, bid, ask, decision_ns, side, gap_starts, latency_ns=LATENCY_NS,
               no_fill_window_ns=1800 * NS):
    """First tick at/after decision+latency (mirrors validated resolve_entry)."""
    t0 = decision_ns + latency_ns
    i0 = int(np.searchsorted(ts, t0, side="left"))
    if i0 >= len(ts) or ts[i0] > decision_ns + no_fill_window_ns:
        return None
    fill_ts = int(ts[i0])
    gi = int(np.searchsorted(gap_starts, decision_ns, side="right"))
    if gi < len(gap_starts) and gap_starts[gi] < fill_ts:
        return None
    return {"idx": i0, "ts": fill_ts,
            "price": float(ask[i0] if side == 1 else bid[i0])}


def tick_resolve(ts, bid, ask, side, entry_idx, entry_ts, stop, target,
                 time_exit_ns, gap_starts, slip=0.0):
    """Tick-accurate resolution after entry; first event wins, stop priority
    on ties (mirrors validated resolve_trade). slip = adverse slippage in
    price units applied to the EXECUTION side exits."""
    n = len(ts)
    lo = entry_idx + 1
    if side == 1:
        js = np.flatnonzero(bid[lo:] <= stop)
        jt = np.flatnonzero(bid[lo:] >= target)
    else:
        js = np.flatnonzero(ask[lo:] >= stop)
        jt = np.flatnonzero(ask[lo:] <= target)
    e_stop = int(ts[lo + js[0]]) if len(js) else np.inf
    e_tgt = int(ts[lo + jt[0]]) if len(jt) else np.inf
    j_time = int(np.searchsorted(ts, time_exit_ns, side="left"))
    e_time = int(ts[j_time]) if j_time < n else np.inf
    gi = int(np.searchsorted(gap_starts, int(entry_ts), side="right"))
    e_gap = int(gap_starts[gi]) if gi < len(gap_starts) else np.inf
    resolved = min(e_stop, e_tgt, e_time)
    if e_gap < resolved:
        return {"status": "GAP"}
    if not np.isfinite(resolved):
        k = n - 1
        px = float(bid[k] if side == 1 else ask[k])
        return {"status": "TIME", "exit_ts": int(ts[k]), "exit_price": px - slip}
    if e_stop <= min(e_tgt, e_time):
        k = lo + js[0]
        px = float(bid[k] if side == 1 else ask[k])
        return {"status": "STOP", "exit_ts": e_stop, "exit_price": px - slip}
    if e_tgt <= e_time:
        return {"status": "TARGET", "exit_ts": e_tgt,
                "exit_price": float(target) - slip}
    k = j_time
    px = float(bid[k] if side == 1 else ask[k])
    return {"status": "TIME", "exit_ts": e_time, "exit_price": px - slip}
