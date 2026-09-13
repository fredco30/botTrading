#!/usr/bin/env python3
"""MACRO-TICK-M1 independent real-data audit (frozen spec §21).

Re-verifies at least 10 trades per strategy (or all if < 10) with a
SEPARATE audit path: direct month-parquet reads, plain Python lists,
`bisect` searches and scalar loops — deliberately different from the
production executor (vectorised numpy + validated mtf_lib resolution).

Confirms per audited trade: event timestamp, P0, P30, shock direction,
trigger timestamp, entry timestamp, entry side/price, SL, TP, exit
timestamp, exit side/price, PnL.

Run:  python research/macro_tick_m1_event_strategies/audit_m1.py
"""
import bisect
import csv
import json
import os
import sys
from datetime import datetime, timedelta, timezone

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.normpath(os.path.join(_HERE, "..", ".."))
TICK_PARQUET = os.environ.get(
    "RESEARCH_TICK_PARQUET",
    r"E:\ResearchData\botTrading\ticks\parquet")
EVENTS_CSV = os.path.join(_REPO, "research", "macro_tick_m0", "data",
                          "macro_events_2010_2018_aligned.csv")
TRADES_JSON = os.path.join(_HERE, "macro_m1_trades.json")
OUT_JSON = os.path.join(_HERE, "macro_m1_audit.json")

PIP = 1e-4
MS = 1_000_000          # ns per ms
MIN_AUDIT_PER_STRATEGY = 10
TOL = 1e-9


def iso_to_ns(s):
    return int(datetime.fromisoformat(s.replace("Z", "+00:00"))
               .astimezone(timezone.utc).timestamp() * 1e9)


def ns_to_dt(ns):
    return datetime.fromtimestamp(ns / 1e9, tz=timezone.utc)


def load_month(year, month):
    """Direct parquet read -> plain python lists (independent path)."""
    import pandas as pd
    p = os.path.join(TICK_PARQUET, "EURUSD", f"year={year:04d}",
                     f"month={month:02d}", "ticks.parquet")
    if not os.path.exists(p):
        return [], [], []
    df = pd.read_parquet(p, columns=["timestamp_utc", "bid", "ask"])
    ts = [int(v) for v in df["timestamp_utc"].astype("int64")]
    bid = [float(v) for v in df["bid"]]
    ask = [float(v) for v in df["ask"]]
    return ts, bid, ask


def load_window_months(t_from, t_to):
    """Concatenated ticks covering [t_from, t_to) from every overlapping
    month file, sorted; returns (ts, bid, ask) python lists."""
    parts = []
    d0 = ns_to_dt(t_from).replace(day=1)
    d1 = ns_to_dt(t_to - 1)
    months = set()
    cur = d0
    while cur <= d1:
        months.add((cur.year, cur.month))
        cur = (cur + timedelta(days=32)).replace(day=1)
    for y, m in sorted(months):
        parts.append(load_month(y, m))
    ts = [t for p in parts for t in p[0]]
    bid = [b for p in parts for b in p[1]]
    ask = [a for p in parts for a in p[2]]
    order = sorted(range(len(ts)), key=lambda i: ts[i])
    return ([ts[i] for i in order], [bid[i] for i in order],
            [ask[i] for i in order])


def is_weekend(dt):
    """Frozen weekend window: [Fri 21:59Z, Sun 22:01Z)."""
    wd, t = dt.weekday(), dt.time()
    if wd == 4:                                   # Friday
        return t >= datetime(2000, 1, 1, 21, 59).time()
    if wd == 5:                                   # Saturday
        return True
    if wd == 6:                                   # Sunday
        return t < datetime(2000, 1, 1, 22, 1).time()
    return False


def non_weekend_gap_seconds(t1_ns, t2_ns):
    """Rough independent gap measure: count non-weekend seconds in (t1,t2)."""
    d1, d2 = ns_to_dt(t1_ns), ns_to_dt(t2_ns)
    total = 0.0
    step = timedelta(minutes=1)
    cur = d1
    while cur < d2:
        nxt = min(cur + step, d2)
        if not is_weekend(cur):
            total += (nxt - cur).total_seconds()
        cur = nxt
    return total


def find_gap_containing(ts, i_before):
    """True iff the delta between ts[i_before] and ts[i_before+1] is a real
    data gap (> 1 h non-weekend)."""
    if i_before + 1 >= len(ts):
        return False
    delta_s = (ts[i_before + 1] - ts[i_before]) / 1e9
    if delta_s <= 3600:
        return False
    return non_weekend_gap_seconds(ts[i_before], ts[i_before + 1]) > 3600


def audit_one(trade, ev_by_id):
    """Full independent re-derivation of one production trade."""
    ev = ev_by_id[trade["event_id"]]
    t0 = iso_to_ns(ev["release_timestamp_utc"])
    t_from, t_to = t0 - 62 * 60 * 10**9, t0 + 200 * 60 * 10**9
    ts, bid, ask = load_window_months(t_from, t_to)
    mid = [(b + a) / 2.0 for b, a in zip(bid, ask)]
    got = {}
    # --- P0: last tick strictly before T0
    i0 = bisect.bisect_left(ts, t0) - 1
    got["t0_ns"] = t0
    got["p0"] = mid[i0]
    # --- P30: first tick >= T0+30s
    i30 = bisect.bisect_left(ts, t0 + 30 * 10**9)
    got["p30"] = mid[i30]
    got["shock_dir"] = "LONG" if got["p30"] > got["p0"] else "SHORT"
    shock = got["p30"] - got["p0"]
    # --- trigger timestamp per strategy
    kind = trade["strategy"]
    if kind == "A":
        trig = t0 + 30 * 10**9
    elif kind == "B":
        level = got["p0"] + 0.50 * shock
        lo = bisect.bisect_left(ts, t0 + 30 * 10**9)
        hi = bisect.bisect_right(ts, t0 + 5 * 60 * 10**9)
        trig_i = None
        for i in range(lo, hi):
            if (shock > 0 and mid[i] <= level) or \
                    (shock < 0 and mid[i] >= level):
                trig_i = i
                break
        if trig_i is None:
            return {"ok": False, "event_id": trade["event_id"],
                    "strategy": kind, "error": "NO_TRIGGER_IN_AUDIT"}
        trig = ts[trig_i]
    else:  # C
        lo = bisect.bisect_left(ts, t0 + 5 * 60 * 10**9)
        hi = bisect.bisect_right(ts, t0 + 35 * 60 * 10**9)
        r0 = bisect.bisect_left(ts, t0)
        r1 = bisect.bisect_left(ts, t0 + 5 * 60 * 10**9)
        nh = max(mid[r0:r1])
        nl = min(mid[r0:r1])
        trig_i = None
        c_side = None
        for i in range(lo, hi):
            if mid[i] > nh:
                trig_i, c_side = i, 1
                break
            if mid[i] < nl:
                trig_i, c_side = i, -1
                break
        if trig_i is None:
            return {"ok": False, "event_id": trade["event_id"],
                    "strategy": kind, "error": "NO_TRIGGER_IN_AUDIT"}
        trig = ts[trig_i]
    got["trigger_ns"] = trig
    # --- frozen direction conventions: A follows the shock, B reverses it,
    # C follows the breakout side observed above
    if kind == "A":
        exp_side = 1 if shock > 0 else -1
    elif kind == "B":
        exp_side = -1 if shock > 0 else 1
    else:
        exp_side = c_side
    side = exp_side
    ie = bisect.bisect_left(ts, trig + 250 * MS)
    got["entry_ts"] = ts[ie]
    got["entry_side"] = "ASK" if side == 1 else "BID"
    got["entry"] = ask[ie] if side == 1 else bid[ie]
    # --- SL / TP
    if kind == "A":
        sl = got["p0"]
        risk = got["entry"] - sl if side == 1 else sl - got["entry"]
        tp = got["entry"] + side * 1.5 * risk
    elif kind == "B":
        r0 = bisect.bisect_left(ts, t0)
        seg = mid[r0:bisect.bisect_right(ts, trig)]
        sl = max(seg) if shock > 0 else min(seg)
        tp = got["p0"]
    else:
        r0 = bisect.bisect_left(ts, t0)
        r1 = bisect.bisect_left(ts, t0 + 5 * 60 * 10**9)
        sl = (max(mid[r0:r1]) + min(mid[r0:r1])) / 2.0
        risk = got["entry"] - sl if side == 1 else sl - got["entry"]
        tp = got["entry"] + side * 1.5 * risk
    got["sl"] = sl
    got["tp"] = tp
    # --- exit scan: ticks strictly after entry, first event wins
    # (stop checked before target before time, also on the same tick)
    hold_ns = (60 if kind == "A" else 30 if kind == "B" else 120) * 60 * 10**9
    reason = None
    k = ie + 1
    while k < len(ts):
        b, a = bid[k], ask[k]
        stopped = (b <= sl) if side == 1 else (a >= sl)
        targeted = (b >= tp) if side == 1 else (a <= tp)
        if stopped:
            reason = "STOP"
            break
        if targeted:
            reason = "TARGET"
            break
        if ts[k] >= trade["entry_ts"] + hold_ns:
            reason = "TIME"
            break
        k += 1
    if reason == "TARGET":
        exit_ts, exit_px = ts[k], tp
    elif reason in ("STOP", "TIME"):
        exit_ts, exit_px = ts[k], (bid[k] if side == 1 else ask[k])
    else:
        # frozen fallback: no tick found up to window end -> TIME at the
        # last window tick (matches production last-tick fallback)
        reason = "TIME"
        exit_ts, exit_px = ts[-1], (bid[-1] if side == 1 else ask[-1])
    # data gap onset before the resolved exit?
    j = ie
    while j + 1 < len(ts) and (exit_ts is None or ts[j + 1] < exit_ts):
        if find_gap_containing(ts, j):
            reason, exit_ts, exit_px = "DATA_GAP_INVALID", None, None
            break
        j += 1
    got["exit_reason"] = reason
    got["exit_ts"] = exit_ts
    got["exit_side"] = ("BID" if side == 1 else "ASK") if exit_px is not None \
        else None
    got["exit_price"] = exit_px
    got["net_pips"] = (None if exit_px is None else
                       ((exit_px - got["entry"]) if side == 1
                        else (got["entry"] - exit_px)) / PIP)
    # --- compare with production record
    checks = {}
    checks["t0_ns"] = got["t0_ns"] == trade["t0_ns"]
    checks["p0"] = abs(got["p0"] - trade["p0"]) <= TOL
    checks["p30"] = abs(got["p30"] - trade["p30"]) <= TOL
    checks["shock_dir"] = ((got["p30"] - got["p0"]) > 0) \
        == (trade["shock_pips"] > 0)
    checks["side_convention"] = exp_side == trade["side"]
    checks["trigger_ns"] = (got["trigger_ns"] == trade["trigger_ns"]) \
        if trade["trigger_ns"] is not None \
        else (got["trigger_ns"] == trade["decision_ns"])
    checks["entry_ts"] = got["entry_ts"] == trade["entry_ts"]
    checks["entry_price"] = abs(got["entry"] - trade["entry"]) <= TOL
    checks["sl"] = abs(got["sl"] - trade["stop"]) <= TOL
    checks["tp"] = abs(got["tp"] - trade["target"]) <= TOL
    checks["exit_reason"] = got["exit_reason"] == trade["exit_reason"]
    if got["exit_ts"] is not None:
        checks["exit_ts"] = got["exit_ts"] == trade["exit_ts"]
        checks["exit_price"] = abs(got["exit_price"]
                                   - trade["exit_price"]) <= TOL
        checks["pnl"] = abs(got["net_pips"] - trade["net_pips"]) <= 1e-6
    ok = all(checks.values())
    return {"ok": ok, "event_id": trade["event_id"], "strategy": kind,
            "checks": checks, "audit": got}


def pick(trades, n):
    """Deterministic spread across the chronological trade list."""
    if len(trades) <= n:
        return list(trades)
    step = len(trades) / n
    return [trades[int(i * step)] for i in range(n)]


def main():
    with open(TRADES_JSON, encoding="utf-8") as f:
        trades = json.load(f)
    ev_by_id = {}
    with open(EVENTS_CSV, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            ev_by_id[r["event_id"]] = r
    by_kind = {"A": [], "B": [], "C": []}
    for t in trades:
        if t["exit_reason"] == "DATA_GAP_INVALID":
            continue
        by_kind[t["strategy"]].append(t)
    for k in by_kind:
        by_kind[k].sort(key=lambda t: t["entry_ts"])
    report = {"min_per_strategy": MIN_AUDIT_PER_STRATEGY, "strategies": {}}
    all_ok = True
    for k, lst in by_kind.items():
        sel = pick(lst, MIN_AUDIT_PER_STRATEGY)
        rows = [audit_one(t, ev_by_id) for t in sel]
        n_ok = sum(1 for r in rows if r["ok"])
        all_ok = all_ok and n_ok == len(rows)
        report["strategies"][k] = {
            "n_available": len(lst), "n_audited": len(rows),
            "n_ok": n_ok, "all_match": n_ok == len(rows),
            "results": rows}
    report["ALL_MATCH"] = all_ok
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=1)
    print(json.dumps({k: {kk: vv for kk, vv in v.items()
                          if kk != "results"}
                      for k, v in report["strategies"].items()}, indent=1))
    print("ALL_MATCH:", all_ok)
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
