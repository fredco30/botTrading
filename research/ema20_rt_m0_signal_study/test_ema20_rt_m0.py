#!/usr/bin/env python3
"""EMA20-RT-M0 synthetic validation tests (frozen spec section 15).

Pure synthetic data; never touches the Discovery tick store, no network.
Run:  python -m unittest research.ema20_rt_m0_signal_study.test_ema20_rt_m0 -v
"""
import os
import sys
import tempfile
import unittest

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ema20_rt_lib as R  # noqa: E402
import mtf_lib as L  # noqa: E402

NS = L.NS
M15 = L.TF_NS["M15"]
BASE = int(pd.Timestamp("2012-03-05T00:00:00Z").value)   # Monday 00:00 UTC
SPREAD = 0.00005                                          # 0.5 pip per side


def T(sec):
    """Absolute ns at `sec` seconds after BASE (exact via round-trip)."""
    return BASE + int(round(sec * NS))


class ArrayStore:
    """Minimal TickStore stand-in over synthetic sorted tick arrays."""

    def __init__(self, ts, bid, ask):
        self.ts, self.bid, self.ask = np.asarray(ts), np.asarray(bid), np.asarray(ask)

    def get_range(self, a, b):
        i0 = int(np.searchsorted(self.ts, a, side="left"))
        i1 = int(np.searchsorted(self.ts, b, side="left"))
        return self.ts[i0:i1], self.bid[i0:i1], self.ask[i0:i1]


def scenario(closes, emas, tick_specs):
    """closes/emas: per completed M15 bar; bar i closes at BASE+(i+1)*M15
    (bar 0 -> T(900), bar 1 -> T(1800), bar 2 -> T(2700), ...).
    tick_specs: list of (offset_seconds_from_BASE, mid)."""
    close = np.array(closes, dtype=np.float64)
    ema = np.array(emas, dtype=np.float64)
    close_ts = BASE + (np.arange(len(closes), dtype=np.int64) + 1) * M15
    ts = np.array([T(off) for off, _ in tick_specs], dtype=np.int64)
    mid = np.array([m for _, m in tick_specs], dtype=np.float64)
    store = ArrayStore(ts, mid - SPREAD / 2.0, mid + SPREAD / 2.0)
    return store, close, close_ts, ema


class TestBarsAndEma(unittest.TestCase):
    def test_m15_causal_aggregation_close_from_last_tick(self):
        t0 = T(3600)
        ts = np.array([t0 + 60 * NS, t0 + 300 * NS, t0 + 899 * NS,
                       t0 + 900 * NS + 5])
        mid = np.array([1.10, 1.09, 1.12, 99.0])
        b = L.bars_from_ticks(ts, mid, M15)
        self.assertEqual(b["start"][0], t0)              # left-labelled
        self.assertEqual(b["close"][0], 1.12)            # last tick < t+15m
        self.assertNotIn(99.0, b["close"][:1])           # future excluded

    def test_loader_drops_gap_flagged_bars_and_checks_hard_cut(self):
        with tempfile.TemporaryDirectory() as d:
            start = np.array([BASE, BASE + M15, BASE + 2 * M15])
            df = pd.DataFrame({"start_ns": start, "open": 1.0, "high": 1.0,
                               "low": 1.0, "close": [1.1, 1.2, 1.3],
                               "n_ticks": [3, 3, 3],
                               "gap_flag": [False, True, False]})
            df.to_parquet(os.path.join(d, "bars_M15.parquet"), index=False)
            bar = R.load_m15_bars(d)
            np.testing.assert_array_equal(bar["start"], [start[0], start[2]])
            np.testing.assert_array_equal(bar["close"], [1.1, 1.3])
            np.testing.assert_array_equal(bar["close_ts"],
                                          [start[0] + M15, start[2] + M15])
            df2 = pd.DataFrame({"start_ns": [L.DISCOVERY_END_NS],
                                "open": [1.0], "high": [1.0], "low": [1.0],
                                "close": [1.0], "n_ticks": [1],
                                "gap_flag": [False]})
            df2.to_parquet(os.path.join(d, "bars_M15.parquet"), index=False)
            with self.assertRaises(AssertionError):
                R.load_m15_bars(d)

    def test_ema20_causal_and_formula(self):
        rng = np.random.default_rng(5)
        x = np.cumsum(rng.normal(0, 0.01, 400)) + 1.1
        e = R.ema20_of_closes(x)
        a = 2.0 / 21.0
        v = float(x[0])
        ref = [v]
        for z in x[1:]:
            v = (1.0 - a) * v + a * float(z)
            ref.append(v)
        self.assertTrue(np.array_equal(e, np.array(ref)))   # bit-exact
        x2 = np.concatenate([x[:50], np.full(350, 999.0)])
        np.testing.assert_array_equal(R.ema20_of_closes(x2)[:50], e[:50])

    def test_latency_window_and_horizon_constants(self):
        self.assertEqual(R.ENTRY_LATENCY_NS, 250 * 1_000_000)
        self.assertEqual(R.NO_FILL_WINDOW_NS, 60 * NS)
        for h, want in zip(R.HORIZON_MIN, (900, 1800, 3600, 7200, 14400)):
            self.assertEqual(R.HORIZON_NS[h], want * NS)


class TestReclaim(unittest.TestCase):
    def test_reclaim_requires_previous_close_le_ema(self):
        close = np.array([1.12, 1.13])       # prev ABOVE ema
        ema = np.array([1.11, 1.11])
        np.testing.assert_array_equal(R.reclaim_mask(close, ema), [False, False])

    def test_reclaim_requires_current_close_strictly_above(self):
        close = np.array([1.10, 1.11])       # current == ema (not >)
        ema = np.array([1.11, 1.11])
        np.testing.assert_array_equal(R.reclaim_mask(close, ema), [False, False])
        close2 = np.array([1.10, 1.1100001])
        np.testing.assert_array_equal(R.reclaim_mask(close2, ema), [False, True])

    def test_no_reclaim_from_forming_candle(self):
        # bar 1 (span (T(900), T(1800)]) closes above EMA -> reclaim known ONLY
        # at close_ts[1]=T(1800); its intrabar ticks (incl. a dip below EMA)
        # must never arm or retest; the first post-close tick does.
        store, close, close_ts, ema = scenario(
            [1.10, 1.13], [1.11, 1.11],
            [(960, 1.115), (1100, 1.105), (1799, 1.13),   # inside reclaim bar
             (1860, 1.11)])                               # after close
        events, counts = R.sweep_setups(store, close, close_ts, ema)
        self.assertEqual(counts["N_RETESTS"], 1)
        self.assertEqual(events[0]["retest_ts"], T(1860))
        self.assertGreaterEqual(events[0]["retest_ts"], close_ts[1])


class TestStateMachine(unittest.TestCase):
    def test_armed_ignores_new_reclaims_until_resolution(self):
        # reclaim at bar1; bar3 closes == EMA (no invalidation, not below);
        # bar4 is a fresh reclaim WHILE ARMED -> ignored; retest after bar4.
        store, close, close_ts, ema = scenario(
            [1.10, 1.12, 1.12, 1.11, 1.13], [1.11] * 5,
            [(1900, 1.115), (2800, 1.125), (3700, 1.135),
             (4560, 1.11)])
        events, counts = R.sweep_setups(store, close, close_ts, ema)
        self.assertEqual(counts["N_RECLAIM_BARS"], 2)    # bars 1 and 4
        self.assertEqual(counts["N_RECLAIMS"], 1)        # only bar1 armed
        self.assertEqual(counts["N_RETESTS"], 1)
        self.assertEqual(events[0]["reclaim_bar"], 1)
        self.assertEqual(events[0]["reclaim_ts"], close_ts[1])
        self.assertEqual(events[0]["retest_ts"], T(4560))

    def test_first_retest_only(self):
        # touch at +1960 (retest), back above, second crossing at +2080:
        # state neutral -> NO second event; bars stay above -> no new reclaim.
        store, close, close_ts, ema = scenario(
            [1.10, 1.12, 1.12, 1.12], [1.11] * 4,
            [(1960, 1.11), (2020, 1.115), (2080, 1.11), (2500, 1.12)])
        events, counts = R.sweep_setups(store, close, close_ts, ema)
        self.assertEqual(counts["N_RETESTS"], 1)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["retest_ts"], T(1960))

    def test_retest_is_tick_level_inside_forming_bar(self):
        # armed at T(1800); a tick at T(2200) (bar 2 still FORMING) touching
        # the EMA is already the retest - no waiting for any bar close.
        store, close, close_ts, ema = scenario(
            [1.10, 1.12, 1.12], [1.11] * 3,
            [(1900, 1.115), (2200, 1.105)])
        events, counts = R.sweep_setups(store, close, close_ts, ema)
        self.assertEqual(counts["N_RETESTS"], 1)
        self.assertEqual(events[0]["retest_ts"], T(2200))
        self.assertLess(events[0]["retest_ts"], close_ts[2])

    def test_retest_must_approach_from_above_and_uses_latest_completed_ema(self):
        # EMA jumps 1.11 -> 1.13 when bar 2 completes at T(2700). Tick 1.12
        # (below the NEW ema, approached from below) is NOT a retest; the
        # 1.13 touch from above is.
        store, close, close_ts, ema = scenario(
            [1.10, 1.12, 1.14], [1.11, 1.11, 1.13],
            [(1960, 1.115), (2020, 1.125),   # bar 1 still active EMA
             (2860, 1.12),                   # after bar 2: below, from below
             (2920, 1.14),                   # back above 1.13
             (2980, 1.13)])                  # touch from above
        events, counts = R.sweep_setups(store, close, close_ts, ema)
        self.assertEqual(counts["N_RETESTS"], 1)
        self.assertEqual(events[0]["retest_ts"], T(2980))
        self.assertEqual(events[0]["active_ema_at_retest"], 1.13)
        self.assertEqual(events[0]["prev_mid_at_retest"], 1.14)

    def test_no_invalidation_from_forming_candle(self):
        # sub-EMA ticks while bar 2 is forming (approached from below after an
        # EMA jump) neither retest nor invalidate; bar 2 closes ABOVE its EMA;
        # setup stays armed and later retests from above.
        store, close, close_ts, ema = scenario(
            [1.10, 1.12, 1.14, 1.14], [1.11, 1.11, 1.13, 1.13],
            [(1960, 1.115), (2860, 1.12), (2920, 1.14), (2980, 1.13)])
        events, counts = R.sweep_setups(store, close, close_ts, ema)
        self.assertEqual(counts["N_INVALIDATED_BEFORE_RETEST"], 0)
        self.assertEqual(counts["N_RETESTS"], 1)
        self.assertEqual(events[0]["retest_ts"], T(2980))

    def test_invalidation_on_completed_close_below_and_rearm(self):
        # armed at bar1; bar2 closes BELOW EMA -> invalidated at T(2700); a
        # crossing tick exactly AT T(2700) is excluded (invalidation first);
        # bar4 reclaim re-arms and retests.
        store, close, close_ts, ema = scenario(
            [1.10, 1.12, 1.10, 1.09, 1.13], [1.11] * 5,
            [(1960, 1.115),                    # above, no retest yet
             (2700, 1.09),                     # AT close_ts[2]: excluded
             (4560, 1.11)])                    # retest of the re-armed setup
        events, counts = R.sweep_setups(store, close, close_ts, ema)
        self.assertEqual(counts["N_RECLAIM_BARS"], 2)
        self.assertEqual(counts["N_RECLAIMS"], 2)
        self.assertEqual(counts["N_INVALIDATED_BEFORE_RETEST"], 1)
        self.assertEqual(counts["N_RETESTS"], 1)
        self.assertEqual(events[0]["reclaim_bar"], 4)

    def test_unresolved_at_hard_end_when_armed_forever(self):
        # armed at bar1; price never returns to EMA, no bar closes below:
        # unresolved at DISCOVERY_END.
        store, close, close_ts, ema = scenario(
            [1.10, 1.12, 1.12], [1.11] * 3,
            [(1960, 1.115), (2800, 1.118)])
        events, counts = R.sweep_setups(store, close, close_ts, ema)
        self.assertEqual(counts["N_UNRESOLVED_AT_END"], 1)
        self.assertEqual(counts["N_RETESTS"], 0)
        self.assertEqual(len(events), 0)


class TestEntry(unittest.TestCase):
    def make_event(self, tick_specs):
        store, close, close_ts, ema = scenario([1.10, 1.12], [1.11, 1.11],
                                               tick_specs)
        events, counts = R.sweep_setups(store, close, close_ts, ema)
        return events, counts

    def test_entry_first_tick_at_or_after_250ms_at_ask(self):
        events, _ = self.make_event(
            [(1960, 1.11),                     # retest at T(1960)
             (1960.100, 1.111),                # +100 ms: too early
             (1960.250, 1.112)])               # +250 ms exactly: fill
        self.assertEqual(events[0]["entry_status"], "FILLED")
        self.assertEqual(events[0]["entry_ts"], T(1960) + 250 * 1_000_000)
        self.assertAlmostEqual(events[0]["entry_ask"], 1.112 + SPREAD / 2)
        self.assertAlmostEqual(events[0]["entry_mid"], 1.112)

    def test_entry_no_fill_after_60s(self):
        events, counts = self.make_event(
            [(1960, 1.11), (2271, 1.111)])     # first candidate +311 s
        self.assertEqual(events[0]["entry_status"], "NO_FILL")
        self.assertEqual(counts["N_NO_FILL"], 1)

    def test_entry_no_fill_boundary_inclusive(self):
        # a tick at EXACTLY event+250ms+60s (= T(2020.25)) is inside the
        # frozen window
        events, _ = self.make_event(
            [(1960, 1.11), (2020.250, 1.111)])
        self.assertEqual(events[0]["entry_status"], "FILLED")
        self.assertEqual(events[0]["entry_ts"], T(1960) + 250 * 1_000_000
                         + 60 * NS)


class TestHorizons(unittest.TestCase):
    def filled_event(self, fill_off, mid=1.112):
        return {"entry_status": "FILLED", "entry_ts": T(fill_off),
                "entry_ask": mid + SPREAD / 2, "entry_mid": mid}

    def test_five_horizons_first_bid_tick_exit(self):
        # 60m target has no tick exactly at +3600s -> first at/after = +3660s.
        entry = 2000.250
        specs = [(2000, 1.11), (entry, 1.112),
                 (entry + 900, 1.100), (entry + 1800, 1.105),
                 (entry + 3540, 1.104), (entry + 3660, 1.106),
                 (entry + 7200, 1.110), (entry + 14400, 1.120)]
        store, close, close_ts, ema = scenario([1.10, 1.12], [1.11, 1.11], specs)
        ev = self.filled_event(entry)
        hor = R.resolve_horizons(store, ev, [])
        want = {15: entry + 900, 30: entry + 1800, 60: entry + 3660,
                120: entry + 7200, 240: entry + 14400}
        for h, off in want.items():
            self.assertEqual(hor[h]["status"], "OK")
            self.assertEqual(hor[h]["exit_ts"], T(off))
        self.assertAlmostEqual(hor[15]["exit_bid"], 1.100 - SPREAD / 2)
        net = hor[15]["net_pips"]
        self.assertAlmostEqual(net, (1.100 - SPREAD / 2 - (1.112 + SPREAD / 2))
                               / 1e-4, places=9)
        # spread naturally charged: net = mid move - one full scenario spread
        self.assertAlmostEqual(net - hor[15]["mid_pips"], -SPREAD / 1e-4,
                               places=9)

    def test_gap_invalidation_per_horizon_only(self):
        entry = 2000.250
        specs = [(2000, 1.11), (entry, 1.112),
                 (entry + 900, 1.100), (entry + 1800, 1.105),
                 (entry + 3600, 1.106), (entry + 7200, 1.108),
                 (entry + 14400, 1.120)]
        store, close, close_ts, ema = scenario([1.10, 1.12], [1.11, 1.11], specs)
        ev = self.filled_event(entry)
        gap = (T(entry + 1200), T(entry + 1500))   # intersects every span > 15m
        hor = R.resolve_horizons(store, ev, [gap])
        self.assertEqual(hor[15]["status"], "OK")  # exit before the gap
        for h in (30, 60, 120, 240):
            self.assertEqual(hor[h]["status"], "GAP_INVALID")
        # gap BEFORE entry is harmless; a gap starting at/after an exit leaves
        # that horizon OK (strict g1 < exit_ts).
        hor2 = R.resolve_horizons(
            store, self.filled_event(entry),
            [(T(entry - 600), T(entry - 300)),
             (T(entry + 1500), T(entry + 1600))])
        self.assertEqual(hor2[15]["status"], "OK")
        self.assertEqual(hor2[30]["status"], "GAP_INVALID")

    def test_not_measurable_at_hard_end_or_data_end(self):
        # entry 5 minutes before the hard cut: no horizon measurable
        entry = (L.DISCOVERY_END_NS - 300 * NS - BASE) / NS
        specs = [(2000, 1.11), (entry, 1.112), (entry + 240, 1.111)]
        store, close, close_ts, ema = scenario([1.10, 1.12], [1.11, 1.11], specs)
        hor = R.resolve_horizons(store, self.filled_event(entry), [])
        for h in R.HORIZON_MIN:
            self.assertEqual(hor[h]["status"], "NOT_MEASURABLE")
        # data ends before the exit target -> NOT_MEASURABLE, nothing invented
        store2, c2, ct2, e2 = scenario([1.10, 1.12], [1.11, 1.11],
                                        [(2000, 1.11), (2000.250, 1.112),
                                         (2000.5, 1.111)])
        hor2 = R.resolve_horizons(store2, self.filled_event(2000.250), [])
        for h in R.HORIZON_MIN:
            self.assertEqual(hor2[h]["status"], "NOT_MEASURABLE")


class TestRobustnessAndGate(unittest.TestCase):
    def test_non_overlap_4h_greedy(self):
        ts = [T(0), T(3600), T(14400), T(14400) - 1, T(14400) + 1, T(28800)]
        self.assertEqual(R.non_overlap_keep(ts), [0, 2, 5])

    def m(self, n, mean, median, pos_years, remove_best, ci_lo):
        return {"N": n, "_raw": {"n": n, "mean_net": mean, "median_net": median,
                                 "positive_years": pos_years,
                                 "remove_best": remove_best, "ci_lo": ci_lo}}

    def test_signal_gate_frozen_conditions(self):
        good = self.m(600, 1.7, 0.5, 7, 0.8, 0.3)
        metrics = {15: good, 30: good, 60: good, 120: good, 240: good}
        nonoverlap = {30: good, 60: good, 120: good, 240: good}
        self.assertEqual(R.signal_gate(metrics, nonoverlap),
                         [30, 60, 120, 240])       # 15m can NEVER pass
        cases = [
            (self.m(499, 1.7, 0.5, 7, 0.8, 0.3), "N >= 500"),
            (self.m(600, 1.4999, 0.5, 7, 0.8, 0.3), "mean >= +1.5"),
            (self.m(600, 1.7, 0.0, 7, 0.8, 0.3), "median > 0"),
            (self.m(600, 1.7, 0.5, 5, 0.8, 0.3), "positive years >= 6"),
            (self.m(600, 1.7, 0.5, 7, 0.0, 0.3), "remove_best > 0"),
            (self.m(600, 1.7, 0.5, 7, 0.8, 0.0), "CI95 lower > 0"),
        ]
        for bad, why in cases:
            mm = {15: good, 30: bad, 60: bad, 120: bad, 240: bad}
            self.assertEqual(R.signal_gate(mm, nonoverlap), [], why)
        nonneg = self.m(600, -0.1, 0.0, 0, -0.1, -0.2)
        nonoverlap2 = {30: nonneg, 60: good, 120: good, 240: good}
        self.assertNotIn(30, R.signal_gate(metrics, nonoverlap2))

    def test_horizon_metrics_definitions(self):
        nets = [2.0] * 3 + [-1.0] * 3 + [1.0] * 2
        mids = [x + 1.0 for x in nets]
        years = [2010] * 6 + [2011] * 2
        m = R.horizon_metrics(nets, mids, years)
        self.assertEqual(m["N"], 8)
        self.assertAlmostEqual(m["MEAN_EXECUTABLE_NET_PIPS"], 0.625, places=4)
        self.assertEqual(m["POSITIVE_YEARS"], 2)   # both yearly means > 0
        self.assertEqual(m["BY_YEAR"]["2010"]["N"], 6)
        self.assertAlmostEqual(m["BY_YEAR"]["2010"]["MEAN_NET"], 0.5, places=4)
        self.assertAlmostEqual(m["BY_YEAR"]["2010"]["WIN_RATE"], 0.5, places=4)
        # remove top ceil(0.01*8)=1 event (+2.0): mean of the rest = 3/7
        self.assertAlmostEqual(m["REMOVE_BEST_1_PERCENT_NET_MEAN"],
                               3.0 / 7.0, places=4)
        self.assertLessEqual(m["CI95_LO"], 0.625)
        self.assertGreaterEqual(m["CI95_HI"], 0.625)
        self.assertEqual(R.horizon_metrics([], [], [])["N"], 0)

    def test_bootstrap_ci_contains_mean(self):
        rng = np.random.default_rng(3)
        x = rng.normal(0.5, 2.0, 300)
        lo, hi = L.bootstrap_ci95(x)
        self.assertLessEqual(lo, x.mean())
        self.assertLessEqual(x.mean(), hi)


class TestGuards(unittest.TestCase):
    def test_month_guard_forbids_2019(self):
        with self.assertRaises(ValueError):
            L.assert_month_in_discovery(2019, 1)
        with self.assertRaises(ValueError):
            L.assert_month_in_discovery(2018, 13)
        L.assert_month_in_discovery(2018, 12)       # allowed

    def test_discovery_constants(self):
        self.assertEqual(L.DISCOVERY_END_NS,
                         int(pd.Timestamp("2019-01-01T00:00:00Z").value))


if __name__ == "__main__":
    unittest.main()
