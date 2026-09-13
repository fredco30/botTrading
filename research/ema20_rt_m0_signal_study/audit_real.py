#!/usr/bin/env python3
"""EMA20-RT-M0 independent real-data audit (frozen spec section 16).

SEPARATE CODE PATH: re-derives EVERYTHING from the raw monthly tick parquet
with its own implementations — M15 close series, GAP LIST, EMA20 recursion,
the armed/retest/invalidation state walk, entry latency resolution and
horizon exits. Imports NO event-derivation logic from ema20_rt_lib/mtf_lib.
Compares every engine event field-by-field, exactly, and prints a detailed
field verification for >= 20 events spread across the Discovery years.

Usage:
  python audit_real.py --data-root <root> \
      --events ema20_rt_m0_events.json --results ema20_rt_m0_results.json
"""
import argparse
import json
import os
import sys
from collections import OrderedDict

import numpy as np
import pandas as pd

NS = 1_000_000_000
PIP = 1e-4
BAR_NS = 900 * NS
LATENCY = 250 * 1_000_000
NOFILL = 60 * NS
HORIZONS = (15, 30, 60, 120, 240)
ALPHA = 2.0 / 21.0
START = int(pd.Timestamp("2010-01-01T00:00:00Z").value)
END = int(pd.Timestamp("2019-01-01T00:00:00Z").value)
FIELDS = ["reclaim_ts", "reclaim_close", "ema_at_reclaim", "retest_ts",
          "retest_mid", "active_ema_at_retest", "prev_mid_at_retest",
          "bars_reclaim_to_retest", "minutes_reclaim_to_retest",
          "entry_status", "entry_ts", "entry_ask", "entry_mid"]


# ------------------------------------------------------------ own data path

class MonthTicks:
    """Own month-partition reader with FIFO cache (no mtf_lib)."""

    def __init__(self, pdir, symbol="EURUSD", max_months=6):
        self.pdir = pdir
        self.symbol = symbol
        self.max = max_months
        self.cache = OrderedDict()

    def _month(self, y, m):
        key = (y, m)
        if key in self.cache:
            self.cache.move_to_end(key)
            return self.cache[key]
        f = os.path.join(self.pdir, self.symbol, f"year={y:04d}",
                         f"month={m:02d}", "ticks.parquet")
        if not os.path.exists(f):
            a = (np.array([], dtype=np.int64), np.array([]), np.array([]))
        else:
            df = pd.read_parquet(f)
            a = (df["timestamp_utc"].to_numpy(dtype=np.int64),
                 df["bid"].to_numpy(dtype=np.float64),
                 df["ask"].to_numpy(dtype=np.float64))
        self.cache[key] = a
        while len(self.cache) > self.max:
            self.cache.popitem(last=False)
        return a

    def range(self, a, b):
        ts_p, bi_p, as_p = [], [], []
        y, m = 2010, 1
        while y <= 2018:
            ms = int(pd.Timestamp(f"{y:04d}-{m:02d}-01T00:00:00Z").value)
            me = int((pd.Timestamp(f"{y:04d}-{m:02d}-01T00:00:00Z")
                      + pd.offsets.MonthBegin(1)).value)
            if ms >= b:
                break
            if me > a:
                ts, bi, as_ = self._month(y, m)
                if len(ts):
                    i0 = int(np.searchsorted(ts, max(ms, a), side="left"))
                    i1 = int(np.searchsorted(ts, min(me, b), side="left"))
                    if i1 > i0:
                        ts_p.append(ts[i0:i1])
                        bi_p.append(bi[i0:i1])
                        as_p.append(as_[i0:i1])
            m += 1
            if m == 13:
                y, m = y + 1, 1
        if not ts_p:
            return np.array([], dtype=np.int64), np.array([]), np.array([])
        return (np.concatenate(ts_p), np.concatenate(bi_p),
                np.concatenate(as_p))


def own_close_series(mt, gaps):
    """Own M15 MID close series: last tick's mid per occupied UTC grid slot,
    then the frozen gap-flagged-bar REMOVAL (bar [t,t+15m) invalid iff a gap
    (g1,g2) has g1 < t+15m and g2 > t)."""
    starts, closes = [], []
    for y in range(2010, 2019):
        for m in range(1, 13):
            ts, bid, ask = mt._month(y, m)
            if len(ts) == 0:
                continue
            mid = (bid + ask) / 2.0
            slot = ts // BAR_NS
            uniq = np.unique(slot)
            last = np.searchsorted(slot, uniq, side="right") - 1
            starts.append(uniq * BAR_NS)
            closes.append(mid[last])
    starts = np.concatenate(starts)
    closes = np.concatenate(closes)
    keep = np.ones(len(starts), dtype=bool)
    for g1, g2 in gaps:
        keep &= ~((g1 < starts + BAR_NS) & (g2 > starts))
    return starts[keep], closes[keep]


def own_gap_list(mt):
    """Own GAP LIST: inter-tick delta > 1h whose non-weekend part > 1h.
    Weekend windows via pandas calendar math (independent of mtf_lib)."""
    gaps = []
    prev_last = None
    for y in range(2010, 2019):
        for m in range(1, 13):
            ts, _, _ = mt._month(y, m)
            if len(ts) == 0:
                continue
            if prev_last is not None:
                _maybe_gap(gaps, int(prev_last), int(ts[0]))
            d = np.diff(ts)
            for i in np.flatnonzero(d > 3600 * NS):
                _maybe_gap(gaps, int(ts[i]), int(ts[i + 1]))
            prev_last = ts[-1]
    return gaps


def _maybe_gap(gaps, t1, t2):
    if t2 - t1 <= 3600 * NS:
        return
    d1 = pd.Timestamp(t1, tz="UTC")
    friday = (d1 - pd.Timedelta(days=int(d1.dayofweek) - 4)).normalize() \
        + pd.Timedelta(hours=21, minutes=59)
    remain = t2 - t1
    for k in (-1, 0, 1, 2):
        w0 = (friday + pd.Timedelta(days=7 * k)).value
        w1 = (friday + pd.Timedelta(days=7 * k)
              + pd.Timedelta(days=2, minutes=2)).value
        lo, hi = max(t1, w0), min(t2, w1)
        if hi > lo:
            remain -= hi - lo
    if remain > 3600 * NS:
        gaps.append((t1, t2))


def own_ema(closes):
    """Own EMA20 recursion (mul-form; verified bit-identical to the engine)."""
    out = np.empty(len(closes), dtype=np.float64)
    e = float(closes[0])
    out[0] = e
    for i in range(1, len(closes)):
        e = (1.0 - ALPHA) * e + ALPHA * float(closes[i])
        out[i] = e
    return out


# ------------------------------------------------- own state-machine walk

def first_tick_at_or_after(mt, t):
    """First tick with ts >= t, searching forward with a growing pad (never
    reading beyond the dataset end)."""
    pad = 4 * 86400 * NS
    while True:
        b = min(t + pad + NS, END)
        ts, bid, ask = mt.range(t, b)
        k = int(np.searchsorted(ts, t, side="left"))
        if k < len(ts) or b >= END:
            return ts, bid, ask, k
        pad *= 4


def scan_segment(mt, a, b, prev_mid, ema, close_ts):
    """Own retest scan over [a, b): first tick with prev>ema & cur<=ema."""
    if b <= a:
        return None, prev_mid
    ts, bid, ask = mt.range(a, b)
    if len(ts) == 0:
        return None, prev_mid
    mid = (bid + ask) / 2.0
    ref = ema[np.searchsorted(close_ts, ts, side="right") - 1]
    pm = np.concatenate(([prev_mid], mid[:-1]))
    hit = np.flatnonzero((pm > ref) & (mid <= ref))
    if len(hit) == 0:
        return None, float(mid[-1])
    k = int(hit[0])
    return {"ts": int(ts[k]), "mid": float(mid[k]), "ema": float(ref[k]),
            "prev": float(pm[k])}, float(mid[-1])


def own_walk(mt, close_ts, closes, ema):
    """Literal chronological bar-close walk (independent formulation)."""
    n = len(closes)
    events = []
    cnt = {"N_RECLAIM_BARS": 0, "N_RECLAIMS": 0, "N_RETESTS": 0,
           "N_INVALIDATED_BEFORE_RETEST": 0, "N_NO_FILL": 0,
           "N_UNRESOLVED_AT_END": 0}
    rec = np.zeros(n, dtype=bool)
    rec[1:] = (closes[:-1] <= ema[:-1]) & (closes[1:] > ema[1:])
    cnt["N_RECLAIM_BARS"] = int(rec.sum())
    state = "NEUTRAL"
    i = 1
    scan_pos = prev_mid = None
    while i < n:
        if state == "NEUTRAL":
            if rec[i]:
                state = "ARMED"
                cnt["N_RECLAIMS"] += 1
                arm = i
                scan_pos = int(close_ts[i])
                prev_mid = float(closes[i])   # reclaim close tick = last tick
            i += 1
            continue
        # ARMED: bar i is the next close to become known
        invalidates = closes[i] < ema[i]
        t_end = int(close_ts[i])
        r, last_mid = scan_segment(mt, scan_pos, t_end, prev_mid, ema,
                                   close_ts)
        if r is not None:
            cnt["N_RETESTS"] += 1
            ev = {"reclaim_bar": int(arm), "reclaim_ts": int(close_ts[arm]),
                  "reclaim_close": float(closes[arm]),
                  "ema_at_reclaim": float(ema[arm]),
                  "retest_ts": r["ts"], "retest_mid": r["mid"],
                  "active_ema_at_retest": r["ema"], "prev_mid_at_retest": r["prev"],
                  "bars_reclaim_to_retest": int(
                      np.searchsorted(close_ts, r["ts"], side="right")
                      - np.searchsorted(close_ts, int(close_ts[arm]),
                                        side="right")),
                  "minutes_reclaim_to_retest": (r["ts"] - int(close_ts[arm]))
                  / (60.0 * NS)}
            t0 = r["ts"] + LATENCY
            bound = r["ts"] + LATENCY + NOFILL + 1
            ts, bid, ask = mt.range(t0, bound)   # bounded NO_FILL window
            k = int(np.searchsorted(ts, t0, side="left"))
            if k >= len(ts):
                ev["entry_status"] = "NO_FILL"
                cnt["N_NO_FILL"] += 1
            else:
                ev["entry_status"] = "FILLED"
                ev["entry_ts"] = int(ts[k])
                ev["entry_ask"] = float(ask[k])
                ev["entry_bid"] = float(bid[k])
                ev["entry_mid"] = float((bid[k] + ask[k]) / 2.0)
            events.append(ev)
            state = "NEUTRAL"
            i = int(np.searchsorted(close_ts, r["ts"], side="right"))
            continue
        prev_mid = last_mid
        scan_pos = t_end
        if invalidates:
            cnt["N_INVALIDATED_BEFORE_RETEST"] += 1
            state = "NEUTRAL"
        i += 1
    if state == "ARMED":
        r, _ = scan_segment(mt, scan_pos, END, prev_mid, ema, close_ts)
        if r is not None:
            cnt["N_RETESTS"] += 1
        else:
            cnt["N_UNRESOLVED_AT_END"] += 1
    return events, cnt


def own_horizons(mt, ev, gaps):
    hor = {}
    if ev["entry_status"] != "FILLED":
        return hor
    for h in HORIZONS:
        target = ev["entry_ts"] + h * 60 * NS
        if target >= END:
            hor[h] = {"status": "NOT_MEASURABLE"}
            continue
        ts, bid, ask, k = first_tick_at_or_after(mt, target)
        if k >= len(ts):
            hor[h] = {"status": "NOT_MEASURABLE"}
            continue
        x_ts, x_bid = int(ts[k]), float(bid[k])
        if any(g1 < x_ts and g2 > ev["entry_ts"] for g1, g2 in gaps):
            hor[h] = {"status": "GAP_INVALID"}
            continue
        x_mid = float((bid[k] + ask[k]) / 2.0)
        hor[h] = {"status": "OK", "exit_ts": x_ts, "exit_bid": x_bid,
                  "exit_mid": x_mid,
                  "net_pips": (x_bid - ev["entry_ask"]) / PIP,
                  "mid_pips": (x_mid - ev["entry_mid"]) / PIP}
    return hor


def fields_equal(a, b):
    if isinstance(a, float) or isinstance(b, float):
        try:
            return float(a) == float(b)
        except (TypeError, ValueError):
            return a == b
    if isinstance(a, int) or isinstance(b, int):
        try:
            return int(a) == int(b)
        except (TypeError, ValueError):
            return a == b
    return a == b


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data-root", default=None)
    ap.add_argument("--events", default=os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "ema20_rt_m0_events.json"))
    ap.add_argument("--results", default=os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "ema20_rt_m0_results.json"))
    ap.add_argument("--detail", type=int, default=24)
    ap.add_argument("--out", default=os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "ema20_rt_m0_audit.json"))
    args = ap.parse_args()

    root = args.data_root or os.environ.get("BOTTRADING_TICK_DATA_ROOT")
    pdir = os.path.join(root, "parquet")
    print(f"audit data root: {root}")

    mt = MonthTicks(pdir)
    print("own GAP LIST ...", flush=True)
    gaps = own_gap_list(mt)
    print(f"  {len(gaps)} data gaps", flush=True)

    print("own M15 close series from raw ticks ...", flush=True)
    starts, closes = own_close_series(mt, gaps)
    close_ts = starts + BAR_NS
    if starts[-1] >= END:
        raise AssertionError("audit: bar label at/after hard cut")
    print(f"  {len(closes)} bars after gap-bar removal (last close "
          f"{close_ts[-1]})", flush=True)

    print("own EMA20 ...", flush=True)
    ema = own_ema(closes)

    print("own chronological state walk ...", flush=True)
    events, cnt = own_walk(mt, close_ts, closes, ema)
    print(f"  {len(events)} retest events, counts: {cnt}", flush=True)

    print("own horizons ...", flush=True)
    for ev in events:
        ev["horizons"] = own_horizons(mt, ev, gaps)

    # ---------------- compare against the engine's stored events
    with open(args.events) as f:
        eng = json.load(f)
    with open(args.results) as f:
        results = json.load(f)
    mismatches = []
    if len(eng) != len(events):
        mismatches.append(f"event count: engine {len(eng)} vs audit {len(events)}")
    for k, (e, a) in enumerate(zip(eng, events)):
        bad = [f for f in FIELDS if not fields_equal(e.get(f), a.get(f))]
        eh, ah = e.get("horizons", {}), a.get("horizons", {})
        if set(eh) != {str(h) for h in ah}:
            bad.append("horizon-keys")
        for h in ah:
            hs = str(h)
            x, y = eh.get(hs, {}), ah[h]
            if x.get("status") != y.get("status"):
                bad.append(f"H{h}.status")
                continue
            if y["status"] == "OK":
                for f in ("exit_ts", "exit_bid", "exit_mid", "net_pips",
                          "mid_pips"):
                    if not fields_equal(x.get(f), y[f]):
                        bad.append(f"H{h}.{f}")
        if bad:
            mismatches.append((k, bad))
    eng_counts = results["counts"]
    counts_match = {k2: (eng_counts.get(k2) == cnt[k2]) for k2 in cnt}
    ok = (not mismatches) and all(counts_match.values())

    # ---------------- detailed verification for >= 20 spread events
    idx = np.linspace(0, max(len(events) - 1, 0),
                      min(args.detail, len(events))).astype(int)
    detail = []
    for k in np.unique(idx):
        e, a = eng[k], events[k]
        row = {"event_index": int(k), "year": int(pd.Timestamp(
            e["entry_ts"] if "entry_ts" in e else e["retest_ts"],
            tz="UTC").year), "all_fields_match": True, "fields": {}}
        for f in FIELDS:
            match = fields_equal(e.get(f), a.get(f))
            row["fields"][f] = {"engine": e.get(f), "audit": a.get(f),
                                "match": bool(match)}
            row["all_fields_match"] &= bool(match)
        for h in (15, 30, 60, 120, 240):
            x = e["horizons"].get(str(h))
            if x is None:
                continue
            y_h = a["horizons"][h]
            status_match = x.get("status") == y_h.get("status")
            sub = {"status": {"engine": x.get("status"), "audit": y_h.get("status"),
                              "match": bool(status_match)}}
            row["all_fields_match"] &= bool(status_match)
            if status_match and x.get("status") == "OK":
                for f in ("exit_ts", "exit_bid", "exit_mid", "net_pips",
                          "mid_pips"):
                    m2 = fields_equal(x.get(f), y_h[f])
                    sub[f] = {"engine": x.get(f), "audit": y_h[f],
                              "match": bool(m2)}
                    row["all_fields_match"] &= bool(m2)
            row["fields"][f"H{h}"] = sub
        detail.append(row)

    n_detail_ok = sum(1 for d in detail if d["all_fields_match"])
    years_covered = sorted({d["year"] for d in detail})
    out = {
        "independent_code_path": True,
        "engine_events": len(eng),
        "audit_events": len(events),
        "n_detail_verified": len(detail),
        "n_detail_ok": n_detail_ok,
        "years_covered": years_covered,
        "counts_engine": eng_counts,
        "counts_audit": cnt,
        "counts_match": counts_match,
        "mismatches": mismatches[:20],
        "ALL_MATCH": bool(ok and n_detail_ok == len(detail)
                          and len(detail) >= 20),
        "detail": detail,
    }
    with open(args.out, "w") as f:
        json.dump(out, f, indent=1, default=float)
    print(f"\nREAL_DATA_AUDIT: engine={len(eng)} audit={len(events)} "
          f"detail={n_detail_ok}/{len(detail)} years={years_covered} "
          f"ALL_MATCH={out['ALL_MATCH']}")
    if not out["ALL_MATCH"]:
        print("MISMATCHES:", mismatches[:5])
        sys.exit(1)


if __name__ == "__main__":
    main()
