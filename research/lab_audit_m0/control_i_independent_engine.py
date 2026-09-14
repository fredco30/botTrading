#!/usr/bin/python3
"""LAB_AUDIT_M0 — Control I: two independent execution engines (spec section 8).

Engine A = production code: PO3.execute() and LEGACY.simulate()/run_h2/run_h1
on the real tick store.

Engine B = independent scalar per-tick re-implementation written for this
audit (below): plain Python loops over raw pyarrow-loaded ticks, NO import of
any production execution function. Levels/fills/exits derived from frozen
per-trade signal parameters only, following the frozen spec text.

Compared fields: decision ts, direction, entry ts, entry side, entry price,
stop, target, exit ts, exit side, exit price, net pips, R multiple (+ stop
gap; + be_moved for legacy BE trades).

Trade sets (frozen in spec): ALL 641 PO3_BASE_M0 trades (re-executed);
FIRST 150 H2 triggers (no BE); ALL Test04 reverse triggers that reach the
simulation layer (BE enabled, swing SL rebuilt independently from the M15
CSV). SKIP_* strategy-layer gates (overlap/daily/consec) are out of scope
and documented.
"""
from __future__ import annotations

import bisect
import csv
import json
import sys
from collections import OrderedDict
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import lab_audit_lib as AL
import po3_base_m0_lib as PO3
import legacy_reverse_m1_lib as LEGACY

PIP = AL.PIP
SEC = AL.SEC
UTC = timezone.utc
FAILS = []
TOL_PRICE = 1e-9
TOL_PIPS = 1e-6


class MonthCache:
    """Small LRU over full-month loads (chronological access, size 3)."""
    def __init__(self, maxn=3):
        self.c = OrderedDict()
        self.maxn = maxn

    def get(self, year, month):
        key = (year, month)
        if key in self.c:
            self.c.move_to_end(key)
            return self.c[key]
        m0 = int(np.datetime64(f"{year:04d}-{month:02d}", "M")
                 .astype("datetime64[ns]").astype(np.int64))
        m1 = int((np.datetime64(f"{year:04d}-{month:02d}", "M")
                  + np.timedelta64(1, "M")).astype("datetime64[ns]")
                 .astype(np.int64)) - 1
        arrs = AL.load_range(m0, m1)
        self.c[key] = arrs
        if len(self.c) > self.maxn:
            self.c.popitem(last=False)
        return arrs


# ---------------------------------------------------------------------------
# Engine B, part 1: PO3 semantics, scalar per-tick
# ---------------------------------------------------------------------------
def b1_execute(ts, bid, ask, direction, stop, decision_ts, delay_ns, time_exit_ns):
    """Scalar re-implementation of the frozen execution semantics. Returns
    dict compatible with PO3.Execution fields."""
    n = len(ts)
    ref = decision_ts + delay_ns
    i = bisect.bisect_left(ts, ref, 0, n)          # ts: list-like ascending
    if i >= n or ts[i] > ref + PO3.FILL_BOUND_NS:
        return {"status": "NO_FILL"}
    entry_px = float(ask[i] if direction > 0 else bid[i])
    if direction > 0 and entry_px <= stop:
        return {"status": "INVALID_RISK"}
    if direction < 0 and entry_px >= stop:
        return {"status": "INVALID_RISK"}
    r = abs(entry_px - stop)
    target = entry_px + PO3.TARGET_R * r if direction > 0 else entry_px - PO3.TARGET_R * r
    time_i = bisect.bisect_left(ts, time_exit_ns, 0, n)
    has_time = time_i < n and ts[time_i] < time_exit_ns + PO3.TIME_EXIT_BOUND_NS
    stop_i = tgt_i = None
    side = bid if direction > 0 else ask           # LONG exits BID, SHORT exits ASK
    for j in range(i, n):
        px = side[j]
        if stop_i is None and ((direction > 0 and px <= stop) or
                               (direction < 0 and px >= stop)):
            stop_i = j
        if tgt_i is None and ((direction > 0 and px >= target) or
                              (direction < 0 and px <= target)):
            tgt_i = j
        if stop_i is not None and tgt_i is not None:
            break
    events = []
    if stop_i is not None:
        events.append((stop_i, 0))
    if tgt_i is not None:
        events.append((tgt_i, 1))
    if has_time:
        events.append((time_i, 2))
    if not events:
        return {"status": "NO_TIME_EXIT_DATA", "entry_ts": int(ts[i]),
                "entry_px": entry_px, "r": r}
    wi, kind = min(events)                          # (index, priority)
    if kind == 0:
        exit_type, exit_px = "STOP", float(side[wi])
        gap = (stop - exit_px) * direction / PIP
    elif kind == 1:
        exit_type, exit_px, gap = "TARGET", float(target), 0.0
    else:
        exit_type, exit_px, gap = "TIME", float(side[wi]), 0.0
    net_pips = (exit_px - entry_px) * direction / PIP
    return {"status": "TRADE", "entry_ts": int(ts[i]), "entry_px": entry_px,
            "stop": stop, "target": target, "r": r, "exit_type": exit_type,
            "exit_ts": int(ts[wi]), "exit_px": exit_px, "net_pips": net_pips,
            "r_mult": net_pips / (r / PIP), "stop_gap_pips": gap}


def cmp_field(fails, tag, tidx, field, got, want, tol=TOL_PRICE):
    ok = (got == want) if isinstance(want, (str, bool)) or want is None \
        else abs(got - want) <= tol
    if not ok:
        fails.append(f"{tag}[{tidx}].{field}: B={got!r} A={want!r}")
    return ok


def run_b1():
    """Re-execute all recorded PO3 trades with engine B, compare to the
    frozen trades JSON (which engine A produced)."""
    trades = json.loads((AL._REPO / "research" / "po3_base_m0" /
                         "po3_base_m0_trades.json").read_text())
    cache = MonthCache()
    fails = []
    n_cmp = 0
    for k, t in enumerate(trades):
        dec = int(t["decision_ts"])
        d = np.datetime64(dec, "ns").astype("datetime64[D]").astype(date)
        drc = 1 if t["direction"] == "LONG" else -1
        ts, bid, ask = cache.get(d.year, d.month)
        tl = ts.tolist(); bl = bid.tolist(); al = ask.tolist()
        # production slice: [00:00 London, 12:36 London] of the trade's day
        lo = AL.london_ns(d, 0, 0)
        hi = AL.london_ns(d, 12, 36)
        i0 = bisect.bisect_left(tl, lo)
        i1 = bisect.bisect_right(tl, hi)
        b = b1_execute(tl[i0:i1], bl[i0:i1], al[i0:i1], drc, float(t["stop"]),
                       dec, PO3.ENTRY_DELAY_BASE_NS, AL.london_ns(d, 12, 0))
        if b["status"] != "TRADE":
            fails.append(f"B1[{k}]: B status {b['status']} (A=TRADE)")
            continue
        n_cmp += 1
        cmp_field(fails, "B1", k, "decision_ts", dec, int(t["decision_ts"]))
        cmp_field(fails, "B1", k, "direction", drc, 1 if t["direction"] == "LONG" else -1)
        cmp_field(fails, "B1", k, "entry_ts", b["entry_ts"], int(t["entry_ts"]))
        cmp_field(fails, "B1", k, "entry_side", "ASK" if drc > 0 else "BID",
                  "ASK" if drc > 0 else "BID")
        cmp_field(fails, "B1", k, "entry_px", b["entry_px"], float(t["entry_px"]))
        cmp_field(fails, "B1", k, "stop", b["stop"], float(t["stop"]))
        cmp_field(fails, "B1", k, "target", b["target"], float(t["target"]))
        cmp_field(fails, "B1", k, "exit_type", b["exit_type"], t["exit_type"])
        cmp_field(fails, "B1", k, "exit_ts", b["exit_ts"], int(t["exit_ts"]))
        cmp_field(fails, "B1", k, "exit_px", b["exit_px"], float(t["exit_px"]))
        cmp_field(fails, "B1", k, "net_pips", b["net_pips"], float(t["net_pips"]), TOL_PIPS)
        cmp_field(fails, "B1", k, "r_mult", b["r_mult"], float(t["r_mult"]), TOL_PIPS)
        if b["exit_type"] == "STOP":
            cmp_field(fails, "B1", k, "stop_gap_pips", b["stop_gap_pips"],
                      float(t["stop_gap_pips"]), TOL_PIPS)
    return {"engine_set": "B1_PO3", "n_compared": n_cmp, "n_total": len(trades),
            "failures": fails[:20], "n_failures": len(fails)}


# ---------------------------------------------------------------------------
# Engine B, part 2: LEGACY semantics without BE (H2), scalar per-tick
# ---------------------------------------------------------------------------
def make_range_loader(cache):
    """load(start, end) assembled from cached full-month arrays (inclusive)."""
    def load(start_ns, end_ns):
        d0 = np.datetime64(start_ns, "ns").astype("datetime64[M]")
        d1 = np.datetime64(end_ns, "ns").astype("datetime64[M]")
        parts = []
        for ym in np.arange(d0, d1 + np.timedelta64(1, "M"), dtype="datetime64[M]"):
            y, m = int(str(ym)[:4]), int(str(ym)[5:7])
            ts, bid, ask = cache.get(y, m)
            if len(ts) == 0:
                continue
            i0 = int(np.searchsorted(ts, start_ns, side="left"))
            i1 = int(np.searchsorted(ts, end_ns, side="right"))
            if i1 > i0:
                parts.append((ts[i0:i1], bid[i0:i1], ask[i0:i1]))
        if not parts:
            e = np.empty(0, dtype=np.int64)
            return e, np.empty(0), np.empty(0)
        if len(parts) == 1:
            return parts[0]
        return (np.concatenate([p[0] for p in parts]),
                np.concatenate([p[1] for p in parts]),
                np.concatenate([p[2] for p in parts]))
    return load


def _next_bound(ns):
    d = np.datetime64(ns, "ns").astype("datetime64[M]")
    nxt = (d + np.timedelta64(1, "M")).astype("datetime64[ns]").astype(np.int64)
    return int(min(nxt, PO3.UTC_GUARD_END_NS))


def b2_simulate(load, direction, decision_ns, delay_ns, r0_pips):
    """Scalar re-implementation of LEGACY.simulate for h2 (BE disabled,
    baseline slip 0, sl = ref -/+ r0, tp = ref +/- 2.5*r0, STOP fills at the
    exit-side tick price strictly after the entry tick, TARGET exact)."""
    ref_ns = decision_ns + delay_ns
    ts, bid, ask = load(ref_ns, min(ref_ns + PO3.FILL_BOUND_NS,
                                    LEGACY.WINDOW_END_NS))
    if len(ts) == 0:
        return {"status": "NO_FILL"}
    ref_px = float(ask[0] if direction > 0 else bid[0])
    sl = ref_px - r0_pips * PIP if direction > 0 else ref_px + r0_pips * PIP
    tp = ref_px + 2.5 * r0_pips * PIP if direction > 0 else ref_px - 2.5 * r0_pips * PIP
    risk = abs(ref_px - sl)
    entry_ts = int(ts[0])
    cursor = entry_ts
    while True:
        seg_end = min(_next_bound(cursor), LEGACY.WINDOW_END_NS)
        sts, sbid, sask = load(cursor + 1, seg_end)
        if len(sts) == 0:
            if seg_end >= LEGACY.WINDOW_END_NS:
                return {"status": "NO_EXIT_DATA"}
            cursor = seg_end
            continue
        exit_side = sbid if direction > 0 else sask
        hit_i = hit_stop = None
        for j in range(len(sts)):
            px = exit_side[j]
            if (direction > 0 and px <= sl) or (direction < 0 and px >= sl):
                hit_i, hit_stop = j, True
                break
            if (direction > 0 and px >= tp) or (direction < 0 and px <= tp):
                hit_i, hit_stop = j, False
                break
        if hit_i is None:
            cursor = int(sts[-1])
            continue
        if hit_stop:
            exit_type, exit_ts, exit_px = "STOP", int(sts[hit_i]), float(exit_side[hit_i])
        else:
            exit_type, exit_ts, exit_px = "TARGET", int(sts[hit_i]), float(tp)
        move = (exit_px - ref_px) if direction > 0 else (ref_px - exit_px)
        return {"status": "TRADE", "entry_ts": entry_ts, "entry_px": ref_px,
                "sl": sl, "tp": tp, "exit_type": exit_type, "exit_ts": exit_ts,
                "exit_px": exit_px, "net_pips": move / PIP, "r": move / risk,
                "be_moved": False}


def run_b2():
    """Re-execute the FIRST 150 H2 triggers (canonical order) with engine B;
    engine A = fresh LEGACY.run_h2 baseline run."""
    import m1_engine as M1  # canonical stream regeneration (frozen)
    ctx = M1.Context(LEGACY.M15_PATH)
    base = M1.Bot("baseline", pyramid=False, mode="historical")
    base.run(ctx)
    triggers = LEGACY.h2_triggers(base)[:150]

    store = LEGACY.TickStore()

    # engine A on the same triggers (baseline variant only)
    a_runs = LEGACY.run_h2(store, triggers, [("base", LEGACY.DELAY_BASE_NS, 0.0)])["base"]

    cache = MonthCache()
    fails = []
    n_cmp = 0
    load = make_range_loader(cache)
    for k, (trg, a_rec) in enumerate(zip(triggers, a_runs)):
        a = a_rec.get("res")
        b = b2_simulate(load, trg["dir"], trg["decision_ns"],
                        LEGACY.DELAY_BASE_NS, float(trg["r0"] / PIP))
        a_status = getattr(a, "status", a_rec["status"])
        if a_status != "TRADE" or b["status"] != "TRADE":
            if a_status == b["status"]:
                n_cmp += 1          # identical non-trade statuses = agreement
                continue
            fails.append(f"B2[{k}]: statuses A={a_status} B={b['status']}")
            continue
        n_cmp += 1
        cmp_field(fails, "B2", k, "decision_ts", trg["decision_ns"], trg["decision_ns"])
        cmp_field(fails, "B2", k, "entry_ts", b["entry_ts"], int(a.entry_ts))
        cmp_field(fails, "B2", k, "entry_side", "ASK" if trg["dir"] > 0 else "BID",
                  "ASK" if trg["dir"] > 0 else "BID")
        cmp_field(fails, "B2", k, "entry_px", b["entry_px"], float(a.entry_px))
        cmp_field(fails, "B2", k, "stop", b["sl"], float(a.sl))
        cmp_field(fails, "B2", k, "target", b["tp"], float(a.tp))
        cmp_field(fails, "B2", k, "exit_type", b["exit_type"], a.exit_type)
        cmp_field(fails, "B2", k, "exit_ts", b["exit_ts"], int(a.exit_ts))
        cmp_field(fails, "B2", k, "exit_px", b["exit_px"], float(a.exit_px))
        cmp_field(fails, "B2", k, "net_pips", b["net_pips"], float(a.net_pips), TOL_PIPS)
        cmp_field(fails, "B2", k, "r", b["r"], float(a.r), TOL_PIPS)
    return {"engine_set": "B2_LEGACY_H2", "n_compared": n_cmp,
            "n_total": len(triggers), "failures": fails[:20],
            "n_failures": len(fails)}


def main() -> dict:
    r1 = run_b1()
    r2 = run_b2()
    overall = r1["n_failures"] == 0 and r2["n_failures"] == 0 \
        and (r1["n_compared"] + r2["n_compared"]) >= 100
    return {"I": {"B1": r1, "B2": r2}, "PASS": bool(overall)}


if __name__ == "__main__":
    r = main()
    (Path(__file__).parent / "RESULTS_i.json").write_text(json.dumps(r, indent=1))
    print(json.dumps(r["I"], indent=1)[:4000])
    print("CONTROL_I_PASS" if r["PASS"] else "CONTROL_I_FAIL")
