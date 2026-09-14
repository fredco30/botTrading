#!/usr/bin/python3
"""LAB_AUDIT_M0 — Control G: execution unit test matrix (spec section 6).
Every case's expected values are hand-calculated in the comments. The
automated result must match within 1e-9 (price) / 1e-6 (pips, R).

Production code under test: PO3.execute(), the audit slippage wrapper,
and LEGACY.simulate() (breakeven / slippage / EOD) on a synthetic
in-memory store implementing TickStore's two-method interface.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import lab_audit_lib as AL
import po3_base_m0_lib as PO3
import legacy_reverse_m1_lib as LEGACY

PIP = AL.PIP
SEC = AL.SEC
FAILS = []


def check(name, got, want, tol=1e-9):
    ok = (got == want) if isinstance(want, str) or isinstance(want, bool) \
        else abs(got - want) <= tol
    if not ok:
        FAILS.append(f"{name}: got {got!r} want {want!r}")
    return ok


def s(case, field, got, want, tol=1e-9):
    check(f"{case}.{field}", got, want, tol)


def ticks(*rows):
    """rows of (t_seconds, mid); 1-pip spread."""
    ts = np.array([int(t * SEC) for t, _ in rows], dtype=np.int64)
    mid = np.array([m for _, m in rows], dtype=np.float64)
    return ts, mid - 0.5 * PIP, mid + 0.5 * PIP


# stop 10 pips below/above mid0 => r = 10.5 pips after 1-pip spread, target 21 pips
STOP_L = 1.09900
STOP_S = 1.10100


def case_long_short_entry():
    """CASE 1/2/3/4 — entry/exit side selection, round trip at flat mid.
    Hand-calc: LONG entry ASK=1.100050, TIME exit BID=1.099950, net -1.0 pip,
    r = 1.100050-1.099000 = 10.5 pips, r_mult = -1/10.5 = -0.09523809523809523.
    SHORT entry BID=1.099950, exit ASK=1.100050, net -1.0 pip, r = 10.5 pips."""
    ts, bid, ask = ticks((5, 1.10000), (120, 1.10000))
    ex = PO3.execute(ts, bid, ask, +1, STOP_L, 0, 5 * SEC, 120 * SEC)
    s("G1", "status", ex.status, "TRADE")
    s("G1", "entry_px", ex.entry_px, 1.100050)
    s("G1", "exit_px", ex.exit_px, 1.099950)
    s("G1", "exit_type", ex.exit_type, "TIME")
    s("G1", "net_pips", ex.net_pips, -1.0, 1e-6)
    s("G1", "r", ex.r, 0.00105)
    s("G1", "r_mult", ex.net_pips / (ex.r / PIP), -1.0 / 10.5, 1e-6)
    ex = PO3.execute(ts, bid, ask, -1, STOP_S, 0, 5 * SEC, 120 * SEC)
    s("G2", "entry_px", ex.entry_px, 1.099950)
    s("G2", "exit_px", ex.exit_px, 1.100050)
    s("G2", "net_pips", ex.net_pips, -1.0, 1e-6)
    s("G2", "r", ex.r, 0.00105)
    s("G2", "r_mult", ex.net_pips / (ex.r / PIP), -1.0 / 10.5, 1e-6)


def case_target_touch():
    """CASE 5 — target exact touch (LONG). stop 1.09900, entry ASK 1.100050,
    target = 1.100050 + 2*0.00105 = 1.102150. Tick mid 1.102201 -> BID
    1.102151 >= target (touch with 1e-6 price margin for float robustness).
    Fill capped EXACTLY at target. Hand: exit_px 1.102150 (to 1e-9),
    net +21.0 pips, r_mult +2.0. Exit on BID (CASE 3)."""
    ts, bid, ask = ticks((5, 1.10000), (10, 1.102201))
    ex = PO3.execute(ts, bid, ask, +1, STOP_L, 0, 5 * SEC, 120 * SEC)
    s("G5", "exit_type", ex.exit_type, "TARGET")
    s("G5", "exit_px", ex.exit_px, 1.102150)
    s("G5", "net_pips", ex.net_pips, 21.0, 1e-6)
    s("G5", "r_mult", ex.net_pips / (ex.r / PIP), 2.0, 1e-6)


def case_target_overshoot():
    """CASE 6 — favorable overshoot capped: mid 1.10300 -> BID 1.102500 >=
    target 1.102150, fill EXACTLY at target. net +21.0, r_mult +2.0."""
    ts, bid, ask = ticks((5, 1.10000), (10, 1.10300))
    ex = PO3.execute(ts, bid, ask, +1, STOP_L, 0, 5 * SEC, 120 * SEC)
    s("G6", "exit_type", ex.exit_type, "TARGET")
    s("G6", "exit_px", ex.exit_px, 1.102150)
    s("G6", "net_pips", ex.net_pips, 21.0, 1e-6)


def case_target_overshoot_short():
    """CASE 6b — SHORT mirrored: stop 1.10100, entry BID 1.099950, target
    1.099950-21 pips = 1.097850. mid 1.097500 -> ASK 1.097550 <= target,
    fill exactly at target. net +21.0 (exit on ASK = CASE 4)."""
    ts, bid, ask = ticks((5, 1.10000), (10, 1.09750))
    ex = PO3.execute(ts, bid, ask, -1, STOP_S, 0, 5 * SEC, 120 * SEC)
    s("G6b", "exit_type", ex.exit_type, "TARGET")
    s("G6b", "exit_px", ex.exit_px, 1.097850)
    s("G6b", "net_pips", ex.net_pips, 21.0, 1e-6)


def case_stop_touch():
    """CASE 7 — stop exact touch (LONG): mid 1.099000 -> BID 1.098950 <=
    stop 1.099000. Fill at the exit-side TICK price 1.098950 (one tick beyond
    the stop level because the touch is defined on BID). net -11.0 pips,
    r_mult -11/10.5 = -1.0476190476190477, gap = (1.09900-1.09895)/pip = 0.5."""
    ts, bid, ask = ticks((5, 1.10000), (10, 1.09900))
    ex = PO3.execute(ts, bid, ask, +1, STOP_L, 0, 5 * SEC, 120 * SEC)
    s("G7", "exit_type", ex.exit_type, "STOP")
    s("G7", "exit_px", ex.exit_px, 1.098950)
    s("G7", "net_pips", ex.net_pips, -11.0, 1e-6)
    s("G7", "r_mult", ex.net_pips / (ex.r / PIP), -11.0 / 10.5, 1e-6)
    s("G7", "stop_gap_pips", ex.stop_gap_pips, 0.5, 1e-6)


def case_stop_gap():
    """CASE 8 — stop gap-through: mid 1.098000 -> BID 1.097950. Fill at tick
    price. net -21.0 pips, r_mult -2.0, gap = (1.09900-1.09795)/pip = 10.5."""
    ts, bid, ask = ticks((5, 1.10000), (10, 1.09800))
    ex = PO3.execute(ts, bid, ask, +1, STOP_L, 0, 5 * SEC, 120 * SEC)
    s("G8", "exit_type", ex.exit_type, "STOP")
    s("G8", "exit_px", ex.exit_px, 1.097950)
    s("G8", "net_pips", ex.net_pips, -21.0, 1e-6)
    s("G8", "r_mult", ex.net_pips / (ex.r / PIP), -2.0, 1e-6)
    s("G8", "stop_gap_pips", ex.stop_gap_pips, 10.5, 1e-6)


def case_same_tick_priority():
    """CASE 9 — same-tick event priority.
    9a stop vs time at same index: tick (120, mid 1.09850) is both the first
        tick >= time_exit AND a stop touch (BID 1.098450 <= 1.099000).
        Priority stop(0) < time(2) => STOP. exit 1.098450, net -16.0 pips,
        gap 5.5 pips.
    9b target vs time at same index: tick (120, mid 1.10220) is time tick and
        BID 1.102150 == target => TARGET (priority 1). net +21.0.
    9c entry-tick stop: single tick at t=5, mid 1.10000, stop = 1.10000 =>
        entry ASK 1.100050 > stop (valid risk), BID 1.099950 <= stop at the
        SAME index => immediate STOP at entry tick. r = 0.5 pip,
        net -1.0 pip, r_mult -2.0, gap 0.5.
    9d INVALID_RISK: stop 1.098000 with entry ASK 1.098050 <= stop.
    Note (frozen spec): a same-index stop+target co-hit is geometrically
    unreachable (one exit-side series, stop and target on opposite sides)."""
    ts, bid, ask = ticks((5, 1.10000), (120, 1.09850))
    ex = PO3.execute(ts, bid, ask, +1, STOP_L, 0, 5 * SEC, 120 * SEC)
    s("G9a", "exit_type", ex.exit_type, "STOP")
    s("G9a", "exit_ts", ex.exit_ts, int(120 * SEC))
    s("G9a", "exit_px", ex.exit_px, 1.098450)
    s("G9a", "net_pips", ex.net_pips, -16.0, 1e-6)
    s("G9a", "gap", ex.stop_gap_pips, 5.5, 1e-6)

    ts, bid, ask = ticks((5, 1.10000), (60, 1.10000), (120, 1.102201))
    ex = PO3.execute(ts, bid, ask, +1, STOP_L, 0, 5 * SEC, 120 * SEC)
    s("G9b", "exit_type", ex.exit_type, "TARGET")
    s("G9b", "exit_ts", ex.exit_ts, int(120 * SEC))
    s("G9b", "net_pips", ex.net_pips, 21.0, 1e-6)

    ts, bid, ask = ticks((5, 1.10000), (120, 1.10000))
    ex = PO3.execute(ts, bid, ask, +1, 1.10000, 0, 5 * SEC, 120 * SEC)
    s("G9c", "status", ex.status, "TRADE")
    s("G9c", "exit_type", ex.exit_type, "STOP")
    s("G9c", "exit_ts", ex.exit_ts, int(5 * SEC))
    s("G9c", "exit_px", ex.exit_px, 1.099950)
    s("G9c", "r", ex.r, 0.00005)
    s("G9c", "net_pips", ex.net_pips, -1.0, 1e-6)
    s("G9c", "r_mult", ex.net_pips / (ex.r / PIP), -2.0, 1e-6)

    ts, bid, ask = ticks((5, 1.09800), (120, 1.09800))
    ex = PO3.execute(ts, bid, ask, +1, 1.09900, 0, 5 * SEC, 120 * SEC)
    s("G9d", "status", ex.status, "INVALID_RISK")


def case_latency():
    """CASE 10 — latency: same stream, delay 5s vs 30s.
    Ticks: (5, 1.10000), (30, 1.10100), (120, 1.10100); stop 1.09900.
    base: fill t=5 ASK 1.100050, r=10.5 pips, TIME exit BID 1.100950 at t=120,
          net +9.0 pips, r_mult 9/10.5 = 0.8571428571428571.
    lat:  fill t=30 ASK 1.101050, r = 1.101050-1.099000 = 20.5 pips,
          net (1.100950-1.101050)/pip = -1.0 pip, r_mult -1/20.5 =
          -0.04878048780487805."""
    ts, bid, ask = ticks((5, 1.10000), (30, 1.10100), (120, 1.10100))
    ex = PO3.execute(ts, bid, ask, +1, STOP_L, 0, 5 * SEC, 120 * SEC)
    s("G10a", "entry_ts", ex.entry_ts, int(5 * SEC))
    s("G10a", "net_pips", ex.net_pips, 9.0, 1e-6)
    s("G10a", "r_mult", ex.net_pips / (ex.r / PIP), 9.0 / 10.5, 1e-6)
    ex = PO3.execute(ts, bid, ask, +1, STOP_L, 0, 30 * SEC, 120 * SEC)
    s("G10b", "entry_ts", ex.entry_ts, int(30 * SEC))
    s("G10b", "entry_px", ex.entry_px, 1.101050)
    s("G10b", "net_pips", ex.net_pips, -1.0, 1e-6)
    s("G10b", "r_mult", ex.net_pips / (ex.r / PIP), -1.0 / 20.5, 1e-6)


def case_no_fill_and_bounds():
    """CASE 11/13 — NO_FILL and quote bounds.
    11: first tick >= decision+5s is at t=36 > 35 (=ref+30s) => NO_FILL.
    13a: time_exit=120s, first tick >= 120s is t=150 < 180 => TIME exit at 150.
    13b: first tick >= 120s is t=181 >= 180 => NO_TIME_EXIT_DATA.
    13c: boundary: tick exactly at +60s bound (t=180) is EXCLUDED
         (condition is >= time_exit+60s) => NO_TIME_EXIT_DATA."""
    ts, bid, ask = ticks((0, 1.10000), (36, 1.10000), (120, 1.10000))
    ex = PO3.execute(ts, bid, ask, +1, STOP_L, 0, 5 * SEC, 120 * SEC)
    s("G11", "status", ex.status, "NO_FILL")

    ts, bid, ask = ticks((5, 1.10000), (150, 1.10000))
    ex = PO3.execute(ts, bid, ask, +1, STOP_L, 0, 5 * SEC, 120 * SEC)
    s("G13a", "status", ex.status, "TRADE")
    s("G13a", "exit_ts", ex.exit_ts, int(150 * SEC))

    ts, bid, ask = ticks((5, 1.10000), (181, 1.10000))
    ex = PO3.execute(ts, bid, ask, +1, STOP_L, 0, 5 * SEC, 120 * SEC)
    s("G13b", "status", ex.status, "NO_TIME_EXIT_DATA")

    ts, bid, ask = ticks((5, 1.10000), (180, 1.10000))
    ex = PO3.execute(ts, bid, ask, +1, STOP_L, 0, 5 * SEC, 120 * SEC)
    s("G13c", "status", ex.status, "NO_TIME_EXIT_DATA")


def case_time_exit_selection():
    """CASE 12 — time exit takes the FIRST tick >= time_exit, not a later one:
    ticks (119, 1.10050) then (120, 1.10100): exit at t=120, BID 1.100950.
    net (1.100950-1.100050)/pip = +9.0 pips."""
    ts, bid, ask = ticks((5, 1.10000), (119, 1.10050), (120, 1.10100))
    ex = PO3.execute(ts, bid, ask, +1, STOP_L, 0, 5 * SEC, 120 * SEC)
    s("G12", "exit_ts", ex.exit_ts, int(120 * SEC))
    s("G12", "exit_px", ex.exit_px, 1.100950)
    s("G12", "net_pips", ex.net_pips, 9.0, 1e-6)


def case_slippage_wrapper():
    """CASE 14a — audit slippage wrapper (0.15 pip/side) on case 1:
    LONG entry eff 1.100050+0.000015 = 1.100065, exit eff 1.099950-0.000015 =
    1.099935, net -1.3 pips, r_mult -1.3/10.5 = -0.12380952380952381."""
    ts, bid, ask = ticks((5, 1.10000), (120, 1.10000))
    ex = PO3.execute(ts, bid, ask, +1, STOP_L, 0, 5 * SEC, 120 * SEC)
    slip = 0.15 * PIP
    entry_eff = ex.entry_px + slip
    exit_eff = ex.exit_px - slip
    net = (exit_eff - entry_eff) / PIP
    s("G14a", "net_pips", net, -1.3, 1e-6)
    s("G14a", "r_mult", net / 10.5, -1.3 / 10.5, 1e-6)


class SyntheticStore:
    """Implements TickStore's load_range/next_month_boundary interface over
    in-memory arrays so LEGACY.simulate() runs unmodified. Synthetic ns sit
    inside 2015 (below the 2019 guard)."""
    def __init__(self, ts, bid, ask, boundary_ns):
        self.ts, self.bid, self.ask = ts, bid, ask
        self.boundary = int(boundary_ns)

    def load_range(self, start_ns, end_ns):
        i0 = int(np.searchsorted(self.ts, start_ns, side="left"))
        i1 = int(np.searchsorted(self.ts, end_ns, side="right"))
        return self.ts[i0:i1], self.bid[i0:i1], self.ask[i0:i1]

    def next_month_boundary(self, ns):
        return self.boundary


BASE_NS = 1433162400 * SEC   # 2015-06-01T10:00:00Z (synthetic but in-window)


def legacy_ticks(*rows):
    ts = np.array([BASE_NS + int(t * SEC) for t, _ in rows], dtype=np.int64)
    mid = np.array([m for _, m in rows], dtype=np.float64)
    return ts, mid - 0.5 * PIP, mid + 0.5 * PIP


def h2_like_builder(direction, r_pips):
    def build(ref):
        if direction > 0:
            return ref - r_pips * PIP, ref + 2.5 * r_pips * PIP
        return ref + r_pips * PIP, ref - 2.5 * r_pips * PIP
    return build


def case_legacy_slippage_and_be():
    """CASE 14b — LEGACY STOP with 0.5 pip/side slippage. decision 0(+BASE),
    delay 5s. Ticks: (5, 1.10000) fill LONG ref ASK 1.100050, eff
    1.100100; levels sl=ref-10pips=1.099050, tp=ref+25pips=1.102550.
    Tick (10, 1.09850): BID 1.098450 <= sl => STOP exit at tick price
    MINUS 0.5 pip = 1.098400. net = (1.098400-1.100100)/pip = -17.0 pips,
    r = |ref-sl| = 10 pips, r_mult -1.7.

    CASE 15 — breakeven (be_enabled, no slip): fill ref 1.100050, sl0
    1.099050 (r=10 pips), tp 1.102550. BE trigger level = ref+1.5R =
    1.101550 on the exit side. Tick (10, 1.10200): BID 1.101950 >= trigger
    -> sl := ref+1 pip = 1.100150. Tick (20, 1.10015): BID 1.100100 <=
    locked sl => STOP at tick price 1.100100. net = +0.5 pips,
    r_mult +0.05, be_moved True.
    CASE 15b — BE not triggered: straight down through sl0: tick (10,
    1.09850) BID 1.098450 <= 1.099050 => STOP at the exit-side TICK price
    1.098450 (gap-through fill semantics). net = (1.098450-1.100050)/pip
    = -16.0 pips, r_mult -1.6, be_moved False.

    CASE 16c — LEGACY EOD_WINDOW close at last tick with slip 0.5/side:
    boundary := WINDOW_END forces the end-of-data path. Ticks after entry:
    (30, 1.10000), (60, 1.10000): no stop/tgt/be hit; close at last BID
    1.099950 - 0.5 pip = 1.099900; eff entry 1.100100; net = -2.0 pips,
    r_mult -0.2, exit_type EOD_WINDOW.

    CASE 16d — LEGACY NO_FILL: no tick in [ref, ref+30s]."""
    ts, bid, ask = legacy_ticks((5, 1.10000), (10, 1.09850))
    store = SyntheticStore(ts, bid, ask, LEGACY.WINDOW_END_NS)
    res = LEGACY.simulate(store, +1, BASE_NS, 5 * SEC, 0.5, h2_like_builder(+1, 10.0), False)
    s("G14b", "status", res.status, "TRADE")
    s("G14b", "entry_ref", res.entry_px, 1.100050)
    s("G14b", "entry_eff", res.entry_px_eff, 1.100100)
    s("G14b", "exit_px", res.exit_px, 1.098400)
    s("G14b", "net_pips", res.net_pips, -17.0, 1e-6)
    s("G14b", "r", res.r, -1.7, 1e-6)

    ts, bid, ask = legacy_ticks((5, 1.10000), (10, 1.10200), (20, 1.10015))
    store = SyntheticStore(ts, bid, ask, LEGACY.WINDOW_END_NS)
    res = LEGACY.simulate(store, +1, BASE_NS, 5 * SEC, 0.0, h2_like_builder(+1, 10.0), True)
    s("G15", "status", res.status, "TRADE")
    s("G15", "exit_type", res.exit_type, "STOP")
    s("G15", "exit_px", res.exit_px, 1.100100)
    s("G15", "net_pips", res.net_pips, 0.5, 1e-6)
    s("G15", "r", res.r, 0.05, 1e-6)
    s("G15", "be_moved", res.be_moved, True)

    ts, bid, ask = legacy_ticks((5, 1.10000), (10, 1.09850))
    store = SyntheticStore(ts, bid, ask, LEGACY.WINDOW_END_NS)
    res = LEGACY.simulate(store, +1, BASE_NS, 5 * SEC, 0.0, h2_like_builder(+1, 10.0), True)
    s("G15b", "exit_type", res.exit_type, "STOP")
    s("G15b", "exit_px", res.exit_px, 1.098450)
    s("G15b", "net_pips", res.net_pips, -16.0, 1e-6)
    s("G15b", "r", res.r, -1.6, 1e-6)
    s("G15b", "be_moved", res.be_moved, False)

    ts, bid, ask = legacy_ticks((5, 1.10000), (30, 1.10000), (60, 1.10000))
    store = SyntheticStore(ts, bid, ask, LEGACY.WINDOW_END_NS)
    res = LEGACY.simulate(store, +1, BASE_NS, 5 * SEC, 0.5, h2_like_builder(+1, 10.0), True)
    s("G16c", "exit_type", res.exit_type, "EOD_WINDOW")
    s("G16c", "exit_px", res.exit_px, 1.099900)
    s("G16c", "net_pips", res.net_pips, -2.0, 1e-6)
    s("G16c", "r", res.r, -0.2, 1e-6)

    ts, bid, ask = legacy_ticks((0, 1.10000), (100, 1.10000))
    store = SyntheticStore(ts, bid, ask, LEGACY.WINDOW_END_NS)
    res = LEGACY.simulate(store, +1, BASE_NS, 5 * SEC, 0.0, h2_like_builder(+1, 10.0), False)
    s("G16d", "status", res.status, "NO_FILL")


def case_partial_sample():
    """CASE 16a/16b — partial sample / unavailable quotes.
    16a: array ends at t=60 before time exit, no stop/target hit =>
         PO3 NO_TIME_EXIT_DATA (entry fields still populated).
    16b: no tick at/after decision+5s => NO_FILL."""
    ts, bid, ask = ticks((5, 1.10000), (60, 1.10000))
    ex = PO3.execute(ts, bid, ask, +1, STOP_L, 0, 5 * SEC, 120 * SEC)
    s("G16a", "status", ex.status, "NO_TIME_EXIT_DATA")
    s("G16a", "entry_px", ex.entry_px, 1.100050)

    ts, bid, ask = ticks((0, 1.10000), (4, 1.10000))
    ex = PO3.execute(ts, bid, ask, +1, STOP_L, 0, 5 * SEC, 120 * SEC)
    s("G16b", "status", ex.status, "NO_FILL")


def main() -> dict:
    case_long_short_entry()
    case_target_touch()
    case_target_overshoot()
    case_target_overshoot_short()
    case_stop_touch()
    case_stop_gap()
    case_same_tick_priority()
    case_latency()
    case_no_fill_and_bounds()
    case_time_exit_selection()
    case_slippage_wrapper()
    case_legacy_slippage_and_be()
    case_partial_sample()
    n_cases = 26
    return {
        "control": "G_execution_matrix",
        "n_checks": n_cases,
        "failures": FAILS,
        "n_failures": len(FAILS),
        "PASS": len(FAILS) == 0,
    }


if __name__ == "__main__":
    import json
    r = main()
    (Path(__file__).parent / "RESULTS_g.json").write_text(json.dumps(r, indent=1))
    print(json.dumps(r, indent=1))
    print("CONTROL_G_PASS" if r["PASS"] else "CONTROL_G_FAIL")
