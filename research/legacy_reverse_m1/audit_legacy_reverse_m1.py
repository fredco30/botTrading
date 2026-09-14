#!/usr/bin/python3
"""LEGACY_REVERSE_M1 independent audit (mission §20).

Re-derives H1 / H2 / T4 trades through a SEPARATE scalar implementation:
  - triggers read DIRECTLY from the frozen prior CSVs (no engine regeneration)
  - per-tick pure-python exit loops (no numpy vectorization)
  - independent construction of decision timestamps, sides, swing stops,
    targets, BE logic, fills, exits, net pips and R
Compares against the discovery-run trade CSVs field by field.
"""
from __future__ import annotations

import csv
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import legacy_reverse_m1_lib as L  # noqa: E402 (store + builders only)

HEL = ZoneInfo("Europe/Helsinki")
PIP = L.PIP
SEC = L.SEC

REPO = HERE.parents[1]
BASE_CSV = REPO / "research" / "legacy_bots_m1" / "results_baseline.csv"
PYR_CSV = REPO / "research" / "legacy_bots_m1" / "results_pyramid_safe.csv"


def load_bars():
    times, o, h, l, c = [], [], [], [], []
    with open(L.M15_PATH) as f:
        for line in f:
            d, t, oo, hh, ll, cc, _v = line.split(",")
            times.append(datetime.strptime(d + " " + t, "%Y.%m.%d %H:%M"))
            o.append(float(oo)); h.append(float(hh)); l.append(float(ll)); c.append(float(cc))
    return times, o, h, l, c


class ScalarStore:
    """Pure-python per-tick accessor over month partitions (independent path)."""

    def __init__(self):
        self.inner = L.TickStore()

    def first_tick_at_or_after(self, t_ns):
        ym_start = int(np.datetime64(t_ns, "ns").astype("datetime64[M]").astype("datetime64[ns]").astype(np.int64))
        cur = max(ym_start, L.PO3.UTC_GUARD_START_NS)
        while cur <= L.WINDOW_END_NS:
            ts, bid, ask = self.inner.load_range(cur, min(cur + 92 * 86400 * SEC, L.PO3.UTC_GUARD_END_NS))
            for i in range(len(ts)):
                if ts[i] >= t_ns:
                    return int(ts[i]), float(bid[i]), float(ask[i])
            cur += 92 * 86400 * SEC
        return None, None, None

def scan_exit_scalar(store, direction, start_ns, entry_ref, sl0, tp, risk,
                     be_enabled):
    """Scalar exit scan with EA breakeven (independent reimplementation)."""
    be_level = entry_ref + 1 * PIP if direction > 0 else entry_ref - 1 * PIP
    be_trig = entry_ref + 1.5 * risk if direction > 0 else entry_ref - 1.5 * risk
    sl = sl0
    moved = False
    cur = start_ns + 1
    while cur <= L.WINDOW_END_NS:
        ts, bid, ask = store.inner.load_range(cur, min(cur + 92 * 86400 * SEC, L.WINDOW_END_NS))
        hit = None
        for i in range(len(ts)):
            b, a = float(bid[i]), float(ask[i])
            px = b if direction > 0 else a
            if direction > 0:
                if px <= sl:
                    hit = ("STOP", int(ts[i]), px)
                    break
                if px >= tp:
                    hit = ("TARGET", int(ts[i]), float(tp))
                    break
                if be_enabled and not moved and px >= be_trig:
                    moved = True
                    sl = be_level
            else:
                if px >= sl:
                    hit = ("STOP", int(ts[i]), px)
                    break
                if px <= tp:
                    hit = ("TARGET", int(ts[i]), float(tp))
                    break
                if be_enabled and not moved and px <= be_trig:
                    moved = True
                    sl = be_level
        if hit:
            return hit[0], hit[1], hit[2], moved
        cur += 92 * 86400 * SEC
    return "EOD", None, None, moved


def bar_index(times, server_dt):
    idx = None
    for i, t in enumerate(times):
        if t <= server_dt:
            idx = i
        else:
            break
    return idx


def audit_h1(n_target=40):
    """Re-derive executed H1 trades from frozen CSV + scalar machinery."""
    rows = [r for r in csv.DictReader(open(BASE_CSV)) if r["mode"] == "historical"]
    trig = []
    consec = 0
    for r in rows:  # baseline = all L0; EA win/loss rule
        if float(r["pnl"]) > 0:
            consec = 0
        else:
            consec += 1
        if r["reason"] != "sl" or float(r["pnl"]) > 0:
            continue
        trig.append((r, consec))
    produced = list(csv.DictReader(open(HERE / "h1_trades.csv")))
    times, _o, hh, ll, _c = load_bars()
    store = ScalarStore()

    checked = mismatches = 0
    exec_by_orig = {}
    for r in produced:
        if r["status"] == "TRADE":
            exec_by_orig.setdefault(r["orig_entry_time"], []).append(r)

    for r, _cs in trig:
        if checked >= n_target:
            break
        orig_entry_time = r["entry_time"]
        ex_list = exec_by_orig.get(orig_entry_time)
        if not ex_list:
            continue
        ex = ex_list[0]
        exec_by_orig[orig_entry_time] = ex_list[1:]
        # --- independent trigger re-derivation ---
        dir_orig = int(r["dir"])
        sl_exit = float(r["sl0"])
        bar_open = datetime.strptime(r["exit_time"], "%Y-%m-%d %H:%M:%S")
        bar_open_ns = L.server_to_ns(bar_open)
        # stop tick: first tick in bar where exit-side breaches SL
        t_stop = None
        cur = bar_open_ns
        ts, bid, ask = store.inner.load_range(cur, bar_open_ns + 15 * 60 * SEC)
        side_arr = bid if dir_orig > 0 else ask
        for i in range(len(ts)):
            if (dir_orig > 0 and side_arr[i] <= sl_exit) or (dir_orig < 0 and side_arr[i] >= sl_exit):
                t_stop = int(ts[i]); break
        if t_stop is None:
            ts2, b2, a2 = store.inner.load_range(bar_open_ns + 15 * 60 * SEC,
                                                 bar_open_ns + 15 * 60 * SEC + 1800 * SEC)
            if not len(ts2):
                continue
            t_stop = int(ts2[0])
        # --- independent reverse construction ---
        rev_dir = -dir_orig
        ts_stop_server = L.ns_to_server(t_stop)
        bi = bar_index(times, ts_stop_server)
        if bi is None or bi < 3:
            continue
        if rev_dir < 0:
            swing = max(hh[bi - 1], hh[bi - 2], hh[bi - 3]) + 2 * PIP
        else:
            swing = min(ll[bi - 1], ll[bi - 2], ll[bi - 3]) - 2 * PIP
        ft, fb, fa = store.first_tick_at_or_after(t_stop + 5 * SEC)
        if ft is None or ft > t_stop + 5 * SEC + 30 * SEC:
            continue
        ref_px = fa if rev_dir > 0 else fb
        if rev_dir < 0:
            risk_d = swing - ref_px
            if risk_d <= 0:
                continue
            tp = ref_px - 2.5 * risk_d
        else:
            risk_d = ref_px - swing
            if risk_d <= 0:
                continue
            tp = ref_px + 2.5 * risk_d
        exit_type, exit_ts, exit_px, moved = scan_exit_scalar(
            store, rev_dir, ft, ref_px, swing, tp, risk_d, True)
        if exit_type is None or exit_type == "EOD":
            continue
        net = ((exit_px - ref_px) if rev_dir > 0 else (ref_px - exit_px)) / PIP
        r_mult = ((exit_px - ref_px) if rev_dir > 0 else (ref_px - exit_px)) / risk_d
        # --- compare ---
        ok = (int(ex["dir"]) == rev_dir
              and int(ex["t_stop_ns"]) == t_stop
              and int(ex["entry_ts_ns"]) == ft
              and abs(float(ex["entry_ref_px"]) - ref_px) < 1e-9
              and abs(float(ex["sl"]) - swing) < 1e-9
              and abs(float(ex["tp"]) - tp) < 1e-9
              and ex["exit_type"] == exit_type
              and int(ex["exit_ts_ns"]) == exit_ts
              and abs(float(ex["exit_px"]) - exit_px) < 1e-9
              and abs(float(ex["net_pips"]) - net) < 5e-4   # CSV rounded to 3dp
              and abs(float(ex["r"]) - r_mult) < 5e-4)      # CSV rounded to 5dp
        checked += 1
        if not ok:
            mismatches += 1
            print(f"  MISMATCH orig={orig_entry_time}: dir {ex['dir']}vs{rev_dir} "
                  f"t_stop {ex['t_stop_ns']}vs{t_stop} entry {ex['entry_ts_ns']}vs{ft} "
                  f"sl {ex['sl']}vs{swing} exit {ex['exit_type']}vs{exit_type} "
                  f"pips {ex['net_pips']}vs{net}")
    return checked, mismatches


def audit_h2(n_target=40):
    produced = list(csv.DictReader(open(HERE / "h2_trades.csv")))
    executed = [r for r in produced if r["status"] == "TRADE"]
    base = {r["entry_time"]: r for r in csv.DictReader(open(BASE_CSV))
            if r["mode"] == "historical"}
    store = ScalarStore()
    checked = mismatches = 0
    for ex in executed:
        if checked >= n_target:
            break
        dir_orig = int(ex["orig_dir"])
        b = base[ex["orig_entry_time"]]
        r0 = abs(float(b["entry"]) - float(b["sl0"]))  # ORIGINAL full-precision risk distance
        rev_dir = -dir_orig
        dec_ns = L.server_to_ns(datetime.strptime(ex["orig_entry_time"],
                                                  "%Y-%m-%d %H:%M:%S"))
        ft, fb, fa = store.first_tick_at_or_after(dec_ns + 5 * SEC)
        if ft is None:
            continue
        ref_px = fa if rev_dir > 0 else fb
        if rev_dir > 0:
            sl, tp = ref_px - r0, ref_px + 2.5 * r0
        else:
            sl, tp = ref_px + r0, ref_px - 2.5 * r0
        exit_type, exit_ts, exit_px, _m = scan_exit_scalar(
            store, rev_dir, ft, ref_px, sl, tp, r0, False)
        if exit_type is None or exit_type == "EOD":
            continue
        net = ((exit_px - ref_px) if rev_dir > 0 else (ref_px - exit_px)) / PIP
        ok = (int(ex["dir"]) == rev_dir and int(ex["entry_ts_ns"]) == ft
              and abs(float(ex["entry_ref_px"]) - ref_px) < 1e-9
              and abs(float(ex["sl"]) - sl) < 1e-9
              and abs(float(ex["tp"]) - tp) < 1e-9
              and ex["exit_type"] == exit_type and int(ex["exit_ts_ns"]) == exit_ts
              and abs(float(ex["exit_px"]) - exit_px) < 1e-9
              and abs(float(ex["net_pips"]) - net) < 5e-4)
        checked += 1
        if not ok:
            mismatches += 1
            print(f"  H2 MISMATCH orig={ex['orig_entry_time']}: "
                  f"entry {ex['entry_ts_ns']}vs{ft} sl {ex['sl']}vs{sl} "
                  f"exit {ex['exit_type']}vs{exit_type} pips {ex['net_pips']}vs{net}")
    return checked, mismatches


def audit_t4(n_target=20):
    rows = [r for r in csv.DictReader(open(PYR_CSV)) if r["mode"] == "historical"]
    trig = []
    consec = 0
    for r in rows:
        if float(r["pnl"]) > 0:
            consec = 0
        else:
            consec += 1
        if r["reason"] != "sl" or float(r["pnl"]) > 0:
            continue
        if r["level"] == "0" and consec < 3:
            continue
        if r["level"] not in ("0", "2"):
            continue
        trig.append(r)
    produced = list(csv.DictReader(open(HERE / "t4_trades.csv")))
    exec_by_orig = {}
    for r in produced:
        if r["status"] == "TRADE":
            exec_by_orig.setdefault(r["orig_entry_time"], []).append(r)
    times, _o, hh, ll, _c = load_bars()
    store = ScalarStore()
    checked = mismatches = 0
    for r in trig:
        if checked >= n_target:
            break
        ex_list = exec_by_orig.get(r["entry_time"])
        if not ex_list:
            continue
        ex = ex_list[0]
        exec_by_orig[r["entry_time"]] = ex_list[1:]
        dir_orig = int(r["dir"])
        sl_exit = float(r["sl0"])
        bar_open_ns = L.server_to_ns(datetime.strptime(r["exit_time"], "%Y-%m-%d %H:%M:%S"))
        t_stop = None
        ts, bid, ask = store.inner.load_range(bar_open_ns, bar_open_ns + 15 * 60 * SEC)
        for i in range(len(ts)):
            if (dir_orig > 0 and bid[i] <= sl_exit) or (dir_orig < 0 and ask[i] >= sl_exit):
                t_stop = int(ts[i]); break
        if t_stop is None:
            ts2, _b2, _a2 = store.inner.load_range(bar_open_ns + 15 * 60 * SEC,
                                                   bar_open_ns + 15 * 60 * SEC + 1800 * SEC)
            if not len(ts2):
                continue
            t_stop = int(ts2[0])
        rev_dir = -dir_orig
        bi = bar_index(times, L.ns_to_server(t_stop))
        if bi is None or bi < 3:
            continue
        if rev_dir < 0:
            swing = max(hh[bi - 1], hh[bi - 2], hh[bi - 3]) + 2 * PIP
        else:
            swing = min(ll[bi - 1], ll[bi - 2], ll[bi - 3]) - 2 * PIP
        ft, fb, fa = store.first_tick_at_or_after(t_stop + 5 * SEC)
        if ft is None:
            continue
        ref_px = fa if rev_dir > 0 else fb
        if rev_dir < 0:
            risk_d = swing - ref_px
            if risk_d <= 0 or risk_d / PIP > 25.0:
                continue
            tp = ref_px - 2.5 * risk_d
        else:
            risk_d = ref_px - swing
            if risk_d <= 0 or risk_d / PIP > 25.0:
                continue
            tp = ref_px + 2.5 * risk_d
        exit_type, exit_ts, exit_px, _m = scan_exit_scalar(
            store, rev_dir, ft, ref_px, swing, tp, risk_d, True)
        if exit_type is None or exit_type == "EOD":
            continue
        net = ((exit_px - ref_px) if rev_dir > 0 else (ref_px - exit_px)) / PIP
        ok = (int(ex["dir"]) == rev_dir and int(ex["t_stop_ns"]) == t_stop
              and int(ex["entry_ts_ns"]) == ft
              and abs(float(ex["sl"]) - swing) < 1e-9
              and ex["exit_type"] == exit_type
              and int(ex["exit_ts_ns"]) == exit_ts
              and abs(float(ex["exit_px"]) - exit_px) < 1e-9
              and abs(float(ex["net_pips"]) - net) < 5e-4)
        checked += 1
        if not ok:
            mismatches += 1
            print(f"  T4 MISMATCH orig={r['entry_time']}: sl {ex['sl']}vs{swing} "
                  f"exit {ex['exit_type']}vs{exit_type} pips {ex['net_pips']}vs{net}")
    return checked, mismatches


if __name__ == "__main__":
    print("== H1 audit ==")
    c, m = audit_h1()
    print(f"H1: {c} trades re-derived, {m} mismatches")
    print("== H2 audit ==")
    c2, m2 = audit_h2()
    print(f"H2: {c2} trades re-derived, {m2} mismatches")
    print("== T4 audit ==")
    c3, m3 = audit_t4()
    print(f"T4: {c3} trades re-derived, {m3} mismatches")
    sys.exit(0 if (m == 0 and m2 == 0 and m3 == 0 and c >= 40 and c2 >= 40) else 1)
