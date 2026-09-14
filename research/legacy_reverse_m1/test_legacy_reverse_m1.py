#!/usr/bin/python3
"""LEGACY_REVERSE_M1 synthetic tests (mission §21).

Pure-synthetic fixtures (no tick store, no network) + store guards.
Run: python test_legacy_reverse_m1.py   (exit 0 = all pass)
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import numpy as np

import legacy_reverse_m1_lib as L
import po3_base_m0_lib as PO3

PIP = L.PIP
SEC = L.SEC
FAILS = []


def check(name, cond, detail=""):
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def make_store(ts, bid, ask):
    """Injective fake TickStore with the same load_range/next_month_boundary API."""
    ts = np.asarray(ts, dtype=np.int64)
    bid = np.asarray(bid, dtype=np.float64)
    ask = np.asarray(ask, dtype=np.float64)
    order = np.argsort(ts)
    ts, bid, ask = ts[order], bid[order], ask[order]

    class FakeStore(L.TickStore):
        def __init__(self):
            self.cache = {}
            self.verified = set()
            self.verify_hash = False
            self.entries = {}

        def load_range(self, start_ns, end_ns):
            end_ns = min(end_ns, L.WINDOW_END_NS)
            i0 = int(np.searchsorted(ts, start_ns, side="left"))
            i1 = int(np.searchsorted(ts, end_ns, side="right"))
            return ts[i0:i1], bid[i0:i1], ask[i0:i1]

        def next_month_boundary(self, ns):
            return L.TickStore.next_month_boundary(self, ns)
    return FakeStore()


# 1 tick/second synthetic feed around a decision at 2015-06-15 10:00:00 UTC
T0 = int(datetime(2015, 6, 15, 10, 0, 0, tzinfo=L.UTC).timestamp()) * SEC
BASE = 1.10000


def feed(n=3600, base=BASE, spread=1.0, drift=0.0):
    ts = T0 + np.arange(n) * SEC
    mid = base + drift * np.arange(n) * PIP
    bid = mid - spread / 2 * PIP
    ask = mid + spread / 2 * PIP
    return ts, bid, ask


def level_builder_fixed(sl_offset_from_entry, rr=2.5):
    """sl defined as entry+sl_offset (direction-aware offsets supplied by caller)."""
    def build(ref_px):
        return ref_px + sl_offset_from_entry[0], ref_px + sl_offset_from_entry[1]
    return build


# ---- L0 stop trigger semantics (EA rule, on the canonical stream shape) ----
def test_reverse_trigger_rules():
    t_loss = SimpleNamespace(reason="sl", pnl=-50.0, dir=1, be_moved=False,
                             entry=1.10, sl0=1.0980,
                             exit_time=datetime(2015, 6, 15, 11, 30),
                             entry_time=datetime(2015, 6, 15, 10, 0), level=0)
    t_win = SimpleNamespace(**{**vars(t_loss), "pnl": +30.0})          # BE-positive stop = win
    t_tp = SimpleNamespace(**{**vars(t_loss), "reason": "tp"})          # target exit
    t_eod = SimpleNamespace(**{**vars(t_loss), "reason": "eod"})        # time/eod exit
    check("L0 stop loss triggers reverse", len(L.h1_triggers([t_loss])) == 1)
    check("BE-positive stop does NOT trigger (EA win rule)",
          len(L.h1_triggers([t_win])) == 0)
    check("target exit does NOT trigger reverse", len(L.h1_triggers([t_tp])) == 0)
    check("time/eod exit does NOT trigger reverse", len(L.h1_triggers([t_eod])) == 0)


def test_consec_gate_t4():
    trades = []
    for i, pnl in enumerate([+1, -1, -1, -1, -1, +1, -1, -1, -1]):
        trades.append(SimpleNamespace(reason="sl" if pnl < 0 else "tp", pnl=pnl,
                                      dir=1, be_moved=False, entry=1.1, sl0=1.098,
                                      exit_time=datetime(2015, 6, 15 + i // 3, 10 + i % 3),
                                      entry_time=datetime(2015, 6, 15 + i // 3, 9 + i % 3),
                                      level=0 if i != 4 else 2))
    trg = L.t4_triggers(trades)
    # L0 losses at idx 2,3 (consec 2,3 -> only idx3 fires), idx4 is L2 (unconditional),
    # idx 7,8 (consec 2,3 -> only idx8 fires). idx6 consec1 no.
    lv0 = [t for t in trg if t["level"] == 0]
    lv2 = [t for t in trg if t["level"] == 2]
    check("T4 L0 gate fires only at consec>=3", len(lv0) == 2 and lv0[0]["consec"] == 3,
          f"got {[(t['consec']) for t in lv0]}")
    check("T4 L2 reverse unconditional (consec<3 still fires)",
          len(lv2) == 1 and lv2[0]["consec"] == 4)


# ---- execution semantics on the synthetic feed ----
def test_fill_delay_and_side():
    ts, bid, ask = feed(n=120)
    store = make_store(ts, bid, ask)
    # LONG: entry at ASK, 5s delay -> tick index 5
    res = L.simulate(store, +1, T0, 5 * SEC, 0.0,
                     level_builder_fixed((-10 * PIP, +25 * PIP)), be_enabled=False)
    check("5s baseline delay honored", res.entry_ts == T0 + 5 * SEC)
    check("LONG fills at ASK", abs(res.entry_px - ask[5]) < 1e-12)
    res_s = L.simulate(store, -1, T0, 5 * SEC, 0.0,
                       level_builder_fixed((+10 * PIP, -25 * PIP)), be_enabled=False)
    check("SHORT fills at BID", abs(res_s.entry_px - bid[5]) < 1e-12)
    # 30s stress delay
    res30 = L.simulate(store, +1, T0, 30 * SEC, 0.0,
                       level_builder_fixed((-10 * PIP, +25 * PIP)), be_enabled=False)
    check("30s latency delay honored", res30.entry_ts == T0 + 30 * SEC)


def test_no_fill_bound():
    ts = T0 + np.arange(10) * SEC
    store = make_store(ts, np.full(10, BASE) - 0.5 * PIP, np.full(10, BASE) + 0.5 * PIP)
    res = L.simulate(store, +1, T0 + 60 * SEC, 0.0, 0.0,
                     level_builder_fixed((-10 * PIP, +25 * PIP)), False)
    check("NO_FILL when no tick within 30s bound", res.status == "NO_FILL")


def test_stop_target_exit_sides_and_cap():
    # LONG: flat at entry, rises +30 pips (target +25 caps), then falls back
    ts, _b, _a = feed(n=120)
    path = np.where(np.arange(120) < 10, 0,
                    np.where(np.arange(120) < 40, 30, 0)) * PIP
    store = make_store(ts, BASE + path - 0.5 * PIP, BASE + path + 0.5 * PIP)
    res = L.simulate(store, +1, T0, 0 * SEC, 0.0,
                     level_builder_fixed((-10 * PIP, +25 * PIP)), be_enabled=False)
    check("LONG target cap at TP", res.exit_type == "TARGET"
          and abs(res.exit_px - (res.entry_px + 25 * PIP)) < 1e-12)
    # LONG stop: price falls through stop; exit at tick price (gap)
    mid_dn = BASE - np.where(np.arange(120) >= 20, 15, 0) * PIP
    store2 = make_store(ts, mid_dn - 0.5 * PIP, mid_dn + 0.5 * PIP)
    res2 = L.simulate(store2, +1, T0, 0 * SEC, 0.0,
                      level_builder_fixed((-10 * PIP, +25 * PIP)), be_enabled=False)
    check("LONG stop exits on BID at tick price (gap-through)",
          res2.exit_type == "STOP" and res2.exit_px == mid_dn[20] - 0.5 * PIP
          and res2.r < -1.0)
    # SHORT stop: price rises through the short stop; exits on ASK
    mid_up2 = BASE + np.where(np.arange(120) >= 20, 15, 0) * PIP
    store3 = make_store(ts, mid_up2 - 0.5 * PIP, mid_up2 + 0.5 * PIP)
    res3 = L.simulate(store3, -1, T0, 0 * SEC, 0.0,
                      level_builder_fixed((+10 * PIP, -25 * PIP)), be_enabled=False)
    check("SHORT stop exits on ASK", res3.exit_type == "STOP"
          and res3.exit_px == mid_up2[20] + 0.5 * PIP and res3.r < -1.0)


def test_be_lock():
    # LONG: flat, rises +20 pips (>1.5R=15 of risk 10, below TP=25) -> BE lock,
    # then declines 1 pip per tick (no gap) so the BE stop fills AT the lock
    ts, _b, _a = feed(n=200)
    dec = np.clip(19 - (np.arange(200) - 50), -60, None)   # ticks >=50: 19,18,17,...
    path = np.where(np.arange(200) < 20, 0.0,
                    np.where(np.arange(200) < 50, 20.0, dec)) * PIP
    store = make_store(ts, BASE + path - 0.5 * PIP, BASE + path + 0.5 * PIP)
    res = L.simulate(store, +1, T0, 0 * SEC, 0.0,
                     level_builder_fixed((-10 * PIP, +25 * PIP)), be_enabled=True)
    check("BE moves at 1.5R then locks entry+1pip", res.be_moved
          and res.exit_type == "STOP" and abs(res.net_pips - 1.0) < 1e-9, f"{res.net_pips}")
    # gapped crash through the lock fills at the tick price (frozen convention)
    gap = np.where(np.arange(200) < 20, 0.0,
                   np.where(np.arange(200) < 50, 20.0, -50.0)) * PIP
    store_g = make_store(ts, BASE + gap - 0.5 * PIP, BASE + gap + 0.5 * PIP)
    res_g = L.simulate(store_g, +1, T0, 0 * SEC, 0.0,
                       level_builder_fixed((-10 * PIP, +25 * PIP)), be_enabled=True)
    check("BE lock gapped through fills at tick price (gap-through convention)",
          res_g.be_moved and res_g.exit_type == "STOP" and res_g.net_pips < -49,
          f"{res_g.net_pips}")
    # same path with BE disabled -> full -1R stop at the original level
    res_nb = L.simulate(store, +1, T0, 0 * SEC, 0.0,
                        level_builder_fixed((-10 * PIP, +25 * PIP)), be_enabled=False)
    check("BE disabled -> stop at original level", (not res_nb.be_moved)
          and res_nb.exit_type == "STOP" and res_nb.r < -0.999, f"{res_nb.r}")


def test_slippage_stress():
    ts, bid, ask = feed(n=120)
    store = make_store(ts, bid, ask)
    res = L.simulate(store, +1, T0, 0 * SEC, 0.50,
                     level_builder_fixed((-10 * PIP, +25 * PIP)), be_enabled=False)
    check("stress: LONG entry slips +0.5pip",
          abs(res.entry_px_eff - (ask[0] + 0.5 * PIP)) < 1e-12)
    check("stress: levels built from UNSLIPPED reference",
          abs(res.sl - (ask[0] - 10 * PIP)) < 1e-12)


def test_inversion_mirror():
    # Direct inversion mirrors the risk DISTANCE, never reuses the old stop price
    b = L.h2_level_builder(20 * PIP, -1)   # inverted SHORT with R0=20 pips
    sl, tp = b(1.23456)
    check("H2 inverted SHORT: stop above at R0, target 2.5R0 below",
          abs(sl - (1.23456 + 20 * PIP)) < 1e-12 and abs(tp - (1.23456 - 50 * PIP)) < 1e-12)
    b2 = L.h2_level_builder(20 * PIP, +1)  # inverted LONG
    sl2, tp2 = b2(1.23456)
    check("H2 inverted LONG mirrored", abs(sl2 - (1.23456 - 20 * PIP)) < 1e-12
          and abs(tp2 - (1.23456 + 50 * PIP)) < 1e-12)


def test_h1_swing_construction():
    # EA swing SL: sell -> max high bars 1..3 + 2 pips ; buy -> min low - 2 pips
    # Bars: 9:15(h1.20/l1.085) 9:30(h1.10/l1.09) 9:45(h1.12/l1.10) 10:00(h1.11/l1.095)
    #       10:15(h1.13/l1.096)  <- forming at the probe times
    class Ctx: pass
    ctx = Ctx()
    ctx.t = [datetime(2015, 6, 15, 9, 15), datetime(2015, 6, 15, 9, 30),
             datetime(2015, 6, 15, 9, 45), datetime(2015, 6, 15, 10, 0),
             datetime(2015, 6, 15, 10, 15)]
    ctx.h = [1.20, 1.10, 1.12, 1.11, 1.13]
    ctx.l = [1.085, 1.09, 1.10, 1.095, 1.096]
    # T_stop at 10:08 (inside the 10:00 bar): bars 1..3 = 9:45,9:30,9:15
    ns_stop = L.server_to_ns(datetime(2015, 6, 15, 10, 8))
    b_sell = L.h1_level_builder(ctx, ns_stop, -1)
    sl, _tp = b_sell(1.10)
    check("H1 sell reverse SL = max(high[1..3]) + 2 pips",
          abs(sl - (1.20 + 2 * PIP)) < 1e-12)
    b_buy = L.h1_level_builder(ctx, ns_stop, +1)
    sl2, _tp2 = b_buy(1.10)
    check("H1 buy reverse SL = min(low[1..3]) - 2 pips",
          abs(sl2 - (1.085 - 2 * PIP)) < 1e-12)
    # T_stop at 10:16 (inside the 10:15 bar): window rolls -> 10:00,9:45,9:30
    ns_in_bar = L.server_to_ns(datetime(2015, 6, 15, 10, 16))
    b2 = L.h1_level_builder(ctx, ns_in_bar, -1)
    sl3, _ = b2(1.10)
    check("swing window uses last 3 CLOSED bars at T_stop (rolls with forming bar)",
          abs(sl3 - (1.12 + 2 * PIP)) < 1e-12)
    b3 = L.h1_level_builder(ctx, ns_in_bar, +1)
    sl4, _ = b3(1.10)
    check("buy window rolls identically",
          abs(sl4 - (1.09 - 2 * PIP)) < 1e-12)


def test_no_cascade_and_daily_guard():
    # All fixture times are SERVER time (Europe/Helsinki), consistent with the
    # canonical-stream convention; feed covers server 10:00-12:00.
    TL = L.server_to_ns(datetime(2015, 6, 15, 10, 0))
    ts = TL + np.arange(7200) * SEC
    bid = np.full(7200, BASE - 0.5 * PIP)
    ask = np.full(7200, BASE + 0.5 * PIP)

    class MiniCtx:
        pass
    ctx = MiniCtx()
    ctx.t = [datetime(2015, 6, 15, 10, 0), datetime(2015, 6, 15, 10, 15),
             datetime(2015, 6, 15, 10, 30), datetime(2015, 6, 15, 10, 45),
             datetime(2015, 6, 15, 11, 0), datetime(2015, 6, 15, 11, 15),
             datetime(2015, 6, 15, 11, 30), datetime(2015, 6, 15, 11, 45),
             datetime(2015, 6, 15, 12, 0), datetime(2015, 6, 15, 12, 15),
             datetime(2015, 6, 15, 12, 30), datetime(2015, 6, 15, 12, 45)]
    ctx.h = [BASE + 8 * PIP] * len(ctx.t)
    ctx.l = [BASE - 12 * PIP] * len(ctx.t)

    store = make_store(ts, bid, ask)
    trades = [SimpleNamespace(reason="sl", pnl=-10, dir=1, be_moved=False, entry=BASE,
                              sl0=BASE - 10 * PIP,
                              entry_time=datetime(2015, 6, 15, 11, 0),
                              exit_time=datetime(2015, 6, 15, 11, 30))]
    trg = L.h1_triggers(trades)
    runs = L.run_h1(store, ctx, trg + trg, trades, [("base", 0 * SEC, 0.0)])
    statuses = [r["status"] for r in runs["base"]]
    # first trigger trades; the duplicated trigger cannot cascade (overlap)
    check("no reverse cascade (exactly 1 trade for duplicated trigger)",
          statuses.count("TRADE") == 1, str(statuses))
    # daily cap: the stopped L0 is the 2nd baseline trade of the day -> skip
    trades2 = trades + [SimpleNamespace(**{**vars(trades[0]),
                                           "reason": "tp", "pnl": +5.0,
                                           "entry_time": datetime(2015, 6, 15, 10, 30),
                                           "exit_time": datetime(2015, 6, 15, 10, 45)})]
    trg2 = L.h1_triggers(trades2)
    runs2 = L.run_h1(make_store(ts, bid, ask), ctx, trg2, trades2,
                     [("base", 0 * SEC, 0.0)])
    check("EA daily limit (MaxTradesPerDay=2) skips reverses",
          all(r["status"] == "SKIP_DAILY" for r in runs2["base"]),
          str([r["status"] for r in runs2["base"]]))


def test_guard_2019_and_oos():
    try:
        L.TickStore().load_range(PO3.UTC_GUARD_END_NS, PO3.UTC_GUARD_END_NS + SEC)
        ok = False
    except PO3.OutOfWindowError:
        ok = True
    check("2019+ tick access raises OutOfWindowError", ok)
    try:
        PO3.guard_partition_path("x/year=2019/month=01/ticks.parquet")
        ok = False
    except PO3.OutOfWindowError:
        ok = True
    check("2019+ partition guard raises", ok)
    try:
        L.TickStore().load_range(PO3.UTC_GUARD_START_NS - SEC, PO3.UTC_GUARD_START_NS)
        ok = False
    except PO3.OutOfWindowError:
        ok = True
    check("pre-2010 access raises (OOS guard symmetric)", ok)


def test_prior_ema_replication_identity():
    """Mission §21: run the prior EMA replication coherence tests too."""
    import subprocess
    import unittest
    data_csv = L._HERE.parent / "legacy_bots_m1" / "data" / "EURUSD15_2010_2018.csv"
    if not data_csv.exists():
        raise unittest.SkipTest("local M15 data file absent (bulk data not in git)")
    repo_root = L._HERE.parents[1]
    r = subprocess.run([sys.executable, str(L._HERE.parent / "legacy_bots_m1" / "test_m1_coherence.py")],
                       capture_output=True, text=True, cwd=repo_root)
    check("prior EMA replication test suite passes", r.returncode == 0,
          r.stdout[-400:] + r.stderr[-400:])


try:
    import unittest as _ut
except ImportError:
    _ut = None

if _ut is not None:
    class TestLegacyReverseM1(_ut.TestCase):
        """unittest wrapper so CI discovery actually executes every suite."""
        maxDiff = None

        def test_all_synthetic_suites(self):
            test_reverse_trigger_rules()
            test_consec_gate_t4()
            test_fill_delay_and_side()
            test_no_fill_bound()
            test_stop_target_exit_sides_and_cap()
            test_be_lock()
            test_slippage_stress()
            test_inversion_mirror()
            test_h1_swing_construction()
            test_no_cascade_and_daily_guard()
            test_guard_2019_and_oos()
            self.assertEqual(FAILS, [], f"failed checks: {FAILS}")

        def test_prior_ema_replication_identity(self):
            test_prior_ema_replication_identity()
            self.assertEqual(FAILS, [], f"failed checks: {FAILS}")


if __name__ == "__main__":
    test_reverse_trigger_rules()
    test_consec_gate_t4()
    test_fill_delay_and_side()
    test_no_fill_bound()
    test_stop_target_exit_sides_and_cap()
    test_be_lock()
    test_slippage_stress()
    test_inversion_mirror()
    test_h1_swing_construction()
    test_no_cascade_and_daily_guard()
    test_guard_2019_and_oos()
    test_prior_ema_replication_identity()
    print(f"\n{len(FAILS)} failure(s)" + (": " + ", ".join(FAILS) if FAILS else ""))
    sys.exit(1 if FAILS else 0)
