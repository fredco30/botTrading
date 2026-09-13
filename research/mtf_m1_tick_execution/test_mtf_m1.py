#!/usr/bin/env python3
"""MTF-M1 synthetic validation tests (frozen spec section 14).

Pure synthetic data; never touches the Discovery tick store, no network.
Run:  python -m unittest research.mtf_m1_tick_execution.test_mtf_m1 -v
"""
import os
import sys
import unittest

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mtf_lib as L  # noqa: E402

NS = L.NS
H = 3600 * NS


def ns(s):
    return int(pd.Timestamp(s).value)


class ArrayStore:
    """Minimal TickStore stand-in over synthetic sorted tick arrays."""

    def __init__(self, ts, bid, ask):
        self.ts, self.bid, self.ask = np.asarray(ts), np.asarray(bid), np.asarray(ask)

    def get_range(self, a, b):
        i0 = int(np.searchsorted(self.ts, a, side="left"))
        i1 = int(np.searchsorted(self.ts, b, side="left"))
        return self.ts[i0:i1], self.bid[i0:i1], self.ask[i0:i1]


class TestBars(unittest.TestCase):
    def test_bar_aggregation_m15_grid_and_ohlc(self):
        t0 = ns("2012-03-05T10:00:00Z")  # Monday, hour-aligned
        ts = np.array([t0 + 60 * NS, t0 + 300 * NS, t0 + 600 * NS,
                       t0 + 899 * NS, t0 + 900 * NS])
        mid = np.array([1.10, 1.12, 1.09, 1.11, 1.20])
        b = L.bars_from_ticks(ts, mid, L.TF_NS["M15"])
        self.assertEqual(b["start"][0], t0)
        self.assertEqual(b["start"][1], t0 + 900 * NS)
        self.assertEqual(b["open"][0], 1.10)
        self.assertEqual(b["high"][0], 1.12)
        self.assertEqual(b["low"][0], 1.09)
        self.assertEqual(b["close"][0], 1.11)   # last tick < t+900s
        self.assertEqual(b["close"][1], 1.20)   # next bar's only tick
        np.testing.assert_array_equal(b["n_ticks"], [4, 1])

    def test_bar_left_label_and_h4_alignment(self):
        t0 = ns("2013-07-01T00:00:00Z")
        ts = np.array([t0 + 3 * H, t0 + 3 * H + 1])          # inside [0,4h)
        b = L.bars_from_ticks(ts, np.array([1.5, 1.6]), L.TF_NS["H4"])
        self.assertEqual(len(b["start"]), 1)
        self.assertEqual(b["start"][0], t0)                  # left-labelled
        self.assertEqual(b["close"][0], 1.6)

    def test_bar_close_causality_future_tick_excluded(self):
        t0 = ns("2014-01-06T08:00:00Z")
        ts1 = np.array([t0 + 10 * NS, t0 + 20 * NS])
        ts2 = np.array([t0 + 10 * NS, t0 + 20 * NS, t0 + L.TF_NS["M15"] + 5])
        m = np.array([1.0, 1.5, 99.0])
        b1 = L.bars_from_ticks(ts1, m[:2], L.TF_NS["M15"])
        b2 = L.bars_from_ticks(ts2, m, L.TF_NS["M15"])
        self.assertEqual(b1["close"][0], 1.5)
        self.assertEqual(b2["close"][0], 1.5)                # future ignored
        self.assertEqual(b2["high"][0], 1.5)


class TestIndicators(unittest.TestCase):
    def test_ema_causality_and_formula(self):
        rng = np.random.default_rng(7)
        x = np.cumsum(rng.normal(0, 0.1, 300)) + 1.0
        e = L.ema(x, 20)
        a = x[0]
        ref = []
        for v in x:
            a = a + (2.0 / 21.0) * (v - a)
            ref.append(a)
        np.testing.assert_allclose(e, ref, atol=1e-12)
        x2 = np.concatenate([x[:100], np.full(200, 999.0)])
        np.testing.assert_array_equal(L.ema(x2, 20)[:100], e[:100])  # causal

    def test_atr14_wilder_reference(self):
        rng = np.random.default_rng(11)
        n = 200
        close = 1.0 + np.cumsum(rng.normal(0, 0.01, n))
        high = close + np.abs(rng.normal(0, 0.005, n))
        low = close - np.abs(rng.normal(0, 0.005, n))
        atr = L.atr14(high, low, close)
        tr = np.empty(n)
        tr[0] = high[0] - low[0]
        for i in range(1, n):
            tr[i] = max(high[i] - low[i], abs(high[i] - close[i - 1]),
                        abs(low[i] - close[i - 1]))
        a = tr[:14].mean()
        ref = {13: a}
        for i in range(14, n):
            a = (13 * a + tr[i]) / 14
            ref[i] = a
        self.assertTrue(np.isnan(atr[:13]).all())
        for i in range(13, n):
            self.assertAlmostEqual(atr[i], ref[i], places=12)

    def test_adx14_reference(self):
        rng = np.random.default_rng(23)
        n = 400
        close = 1.0 + np.cumsum(rng.normal(0, 0.01, n))
        high = close + np.abs(rng.normal(0, 0.004, n))
        low = close - np.abs(rng.normal(0, 0.004, n))
        adx = L.adx14(high, low, close)
        # independent reference
        tr = np.empty(n); pdm = np.zeros(n); mdm = np.zeros(n)
        tr[0] = high[0] - low[0]
        for i in range(1, n):
            tr[i] = max(high[i] - low[i], abs(high[i] - close[i - 1]),
                        abs(low[i] - close[i - 1]))
            u, d = high[i] - high[i - 1], low[i - 1] - low[i]
            pdm[i] = u if (u > d and u > 0) else 0.0
            mdm[i] = d if (d > u and d > 0) else 0.0

        def rma(x):
            a = x[:14].mean()
            out = {13: a}
            for i in range(14, len(x)):
                a = (13 * a + x[i]) / 14
                out[i] = a
            return out

        atr, sp, sm = rma(tr), rma(pdm), rma(mdm)
        dxs = []
        for i in range(13, n):            # DI defined from the 14th bar (idx 13)
            pdi = 100 * sp[i] / atr[i]
            mdi = 100 * sm[i] / atr[i]
            dxs.append((i, 100 * abs(pdi - mdi) / (pdi + mdi)))
        a = np.mean([v for _, v in dxs[:14]])     # bars idx 13..26
        ref = {dxs[13][0]: a}                     # placed at idx 26
        for i, v in dxs[14:]:
            a = (13 * a + v) / 14
            ref[i] = a
        self.assertTrue(np.isnan(adx[:26]).all())     # needs 14 DX values
        for i, v in ref.items():
            self.assertAlmostEqual(adx[i], v, places=10)

    def test_bollinger_population_std_includes_current(self):
        x = np.arange(1, 41, dtype=float)
        mid, lo, hi = L.bollinger(x, 20, 2.0)
        self.assertTrue(np.isnan(mid[:19]).all())
        for i in range(19, 40):
            w = x[i - 19:i + 1]
            m = w.mean()
            sd = w.std(ddof=0)
            self.assertAlmostEqual(mid[i], m, places=12)
            self.assertAlmostEqual(lo[i], m - 2 * sd, places=12)
            self.assertAlmostEqual(hi[i], m + 2 * sd, places=12)


class TestGaps(unittest.TestCase):
    def test_weekend_not_a_gap_midweek_hole_is(self):
        fri = pd.Timestamp("2015-06-12T21:59:56Z").value
        sun = pd.Timestamp("2015-06-14T22:00:03Z").value
        self.assertFalse(L.is_data_gap(fri, sun))                 # regular
        wed1 = pd.Timestamp("2015-06-10T17:59:59Z").value
        wed2 = pd.Timestamp("2015-06-10T19:00:03Z").value
        self.assertTrue(L.is_data_gap(wed1, wed2))                # 1h hole
        xmas1 = pd.Timestamp("2017-12-25T07:59:47Z").value
        xmas2 = pd.Timestamp("2017-12-25T22:32:12Z").value
        self.assertTrue(L.is_data_gap(xmas1, xmas2))              # holiday
        self.assertFalse(L.is_data_gap(wed1, wed1 + 3599 * NS))   # < 1h

    def test_detect_gaps_cross_month(self):
        mon = pd.Timestamp("2015-06-08T00:00:00Z").value
        ts_a = np.array([mon, mon + H, mon + 2 * H])
        ts_b = np.array([mon + 6 * H, mon + 7 * H])               # 4h hole
        gaps = L.detect_gaps([ts_a, ts_b])
        self.assertEqual(len(gaps), 1)
        self.assertEqual(gaps[0], (int(ts_a[-1]), int(ts_b[0])))

    def test_mark_gap_bars_boundaries(self):
        t0 = ns("2016-02-01T00:00:00Z")
        starts = np.array([t0, t0 + H, t0 + 2 * H, t0 + 3 * H])
        g_inside = (t0 + H + 100, t0 + 2 * H - 100)   # strictly inside bar 1
        f = L.mark_gap_bars(starts, H, [g_inside])
        np.testing.assert_array_equal(f, [False, True, False, False])
        g_edge = (t0 + H, t0 + H + 50)                # starts at bar 1 start
        f2 = L.mark_gap_bars(starts, H, [g_edge])
        np.testing.assert_array_equal(f2, [False, True, False, False])
        g_end = (t0 - 100, t0)                        # ends at bar 0 start
        f3 = L.mark_gap_bars(starts, H, [g_end])
        np.testing.assert_array_equal(f3, [False, False, False, False])


class TestEntry(unittest.TestCase):
    def setUp(self):
        self.t = ns("2016-03-02T10:00:00Z")

    def test_latency_250ms_boundary(self):
        ts = np.array([self.t + 249 * 10**6, self.t + 250 * 10**6])
        bid = np.array([1.0, 1.0])
        ask = np.array([1.0010, 1.0012])
        r = L.resolve_entry(ts, bid, ask, self.t, 1, np.array([], dtype=np.int64))
        self.assertEqual(r["status"], "FILLED")
        self.assertEqual(r["fill_ts"], ts[1])       # 249ms tick skipped
        self.assertEqual(r["price"], 1.0012)

    def test_long_uses_ask_short_uses_bid(self):
        ts = np.array([self.t + NS, self.t + 2 * NS])
        bid = np.array([1.0000, 1.0001])
        ask = np.array([1.0002, 1.0003])
        rl = L.resolve_entry(ts, bid, ask, self.t, 1, np.array([], dtype=np.int64))
        rs = L.resolve_entry(ts, bid, ask, self.t, -1, np.array([], dtype=np.int64))
        self.assertEqual(rl["price"], 1.0002)       # LONG at ASK (not 1.0000)
        self.assertEqual(rs["price"], 1.0000)       # SHORT at BID (not 1.0002)

    def test_no_fill_after_one_hour(self):
        ts = np.array([self.t + 3600 * NS + NS])    # first tick too late
        r = L.resolve_entry(ts, np.array([1.0]), np.array([1.0]), self.t, 1,
                            np.array([], dtype=np.int64))
        self.assertEqual(r["status"], "NO_FILL")

    def test_no_fill_gap_when_hole_between_decision_and_fill(self):
        g = np.array([self.t + NS])
        ts = np.array([self.t + 5 * NS])
        r = L.resolve_entry(ts, np.array([1.0]), np.array([1.0]), self.t, 1, g)
        self.assertEqual(r["status"], "NO_FILL_GAP")

    def test_fill_just_before_hard_end_is_valid(self):
        t = ns("2018-12-31T23:00:00Z")
        self.assertLess(t, L.DISCOVERY_END_NS)
        r = L.resolve_entry(np.array([t]), np.array([1.0]), np.array([1.0]),
                            t - NS, 1, np.array([], dtype=np.int64))
        self.assertEqual(r["status"], "FILLED")
        # (the entry+T >= 2019 skip itself is covered by
        #  TestDiscoveryPass.test_hard_end_skip_near_2019)

    def test_loader_refuses_2019_partition(self):
        with self.assertRaises(ValueError):
            L.assert_month_in_discovery(2019, 1)
        with self.assertRaises(ValueError):
            L.assert_month_in_discovery(2009, 12)


class TestTradeResolution(unittest.TestCase):
    """resolve_trade on synthetic ticks; LONG entry tick at index 2."""

    def _run(self, ts, bid, ask, side=1, stop=None, target=None,
             t_exit_h=24, gaps=(), entry_idx=2):
        gap_starts = (np.array([g[0] for g in gaps], dtype=np.int64)
                      if len(gaps) else np.array([], dtype=np.int64))
        if stop is None:
            stop = bid[entry_idx] - 0.0020
        if target is None:
            target = bid[entry_idx] + 0.0040
        e_ts = int(ts[entry_idx])
        return L.resolve_trade(np.asarray(ts), np.asarray(bid), np.asarray(ask),
                               side, entry_idx, e_ts, stop, target,
                               e_ts + t_exit_h * H, gap_starts,
                               last_tick=(int(ts[-1]), float(bid[-1]),
                                          float(ask[-1])))

    def test_long_enters_ask_exits_bid_spread_charged_once(self):
        t = ns("2016-04-06T08:00:00Z")
        ts = np.array([t, t + NS, t + 2 * NS, t + H])
        bid = np.array([1.1000, 1.1000, 1.1000, 1.1000])
        ask = np.array([1.1002, 1.1002, 1.1002, 1.1002])
        r = L.resolve_trade(ts, bid, ask, 1, 2, int(ts[2]), 1.0950, 1.1100,
                            int(ts[2]) + 24 * H, np.array([], dtype=np.int64),
                            last_tick=(int(ts[-1]), 1.1000, 1.1002))
        self.assertEqual(r["status"], "TIME")
        self.assertEqual(r["exit_price"], 1.1000)   # BID exit
        net = (r["exit_price"] - 1.1002) / 1e-4     # ASK entry
        self.assertAlmostEqual(net, -2.0, places=9)  # spread charged once

    def test_short_enters_bid_exits_ask(self):
        t = ns("2016-04-06T08:00:00Z")
        ts = np.array([t, t + NS, t + 2 * NS, t + H])
        bid = np.array([1.1000, 1.1000, 1.1000, 1.1000])
        ask = np.array([1.1002, 1.1002, 1.1002, 1.1002])
        r = L.resolve_trade(ts, bid, ask, -1, 2, int(ts[2]), 1.1050, 1.0950,
                            int(ts[2]) + 24 * H, np.array([], dtype=np.int64),
                            last_tick=(int(ts[-1]), 1.1000, 1.1002))
        self.assertEqual(r["status"], "TIME")
        self.assertEqual(r["exit_price"], 1.1002)   # ASK exit
        net = (1.1000 - r["exit_price"]) / 1e-4     # BID entry
        self.assertAlmostEqual(net, -2.0, places=9)

    def test_long_stop_uses_bid_with_overshoot(self):
        t = ns("2016-04-06T08:00:00Z")
        ts = np.array([t, t + NS, t + 2 * NS, t + H])
        bid = np.array([1.1000, 1.1000, 1.1000, 1.0940])   # through the stop
        ask = bid + 0.0002
        r = self._run(ts, bid, ask, 1, stop=1.0950)
        self.assertEqual(r["status"], "STOP")
        self.assertEqual(r["exit_price"], 1.0940)   # current BID, no cap

    def test_short_stop_uses_ask(self):
        t = ns("2016-04-06T08:00:00Z")
        ts = np.array([t, t + NS, t + 2 * NS, t + H])
        ask = np.array([1.1002, 1.1002, 1.1002, 1.1060])
        bid = ask - 0.0002
        r = self._run(ts, bid, ask, -1, stop=1.1050)
        self.assertEqual(r["status"], "STOP")
        self.assertEqual(r["exit_price"], 1.1060)

    def test_target_capped_at_target(self):
        t = ns("2016-04-06T08:00:00Z")
        ts = np.array([t, t + NS, t + 2 * NS, t + H])
        bid = np.array([1.1000, 1.1000, 1.1000, 1.1130])   # overshoots target
        ask = bid + 0.0002
        r = self._run(ts, bid, ask, 1, stop=1.0950, target=1.1100)
        self.assertEqual(r["status"], "TARGET")
        self.assertEqual(r["exit_price"], 1.1100)   # capped, not 1.1130

    def test_short_target_capped(self):
        t = ns("2016-04-06T08:00:00Z")
        ts = np.array([t, t + NS, t + 2 * NS, t + H])
        ask = np.array([1.1002, 1.1002, 1.1002, 1.0880])
        bid = ask - 0.0002
        r = self._run(ts, bid, ask, -1, stop=1.1050, target=1.0900)
        self.assertEqual(r["status"], "TARGET")
        self.assertEqual(r["exit_price"], 1.0900)

    def test_time_exit_first_tick_at_or_after(self):
        t = ns("2016-04-06T08:00:00Z")
        exit_due = t + 24 * H
        ts = np.array([t, t + NS, t + 2 * NS, exit_due - NS, exit_due + NS])
        bid = np.full(5, 1.1000)
        ask = bid + 0.0002
        r = self._run(ts, bid, ask, 1, t_exit_h=24)
        self.assertEqual(r["status"], "TIME")
        self.assertEqual(r["exit_ts"], exit_due + NS)  # first >= due
        self.assertEqual(r["exit_price"], 1.1000)      # BID for LONG

    def test_stop_before_target_first_event_wins(self):
        t = ns("2016-04-06T08:00:00Z")
        ts = np.array([t, t + NS, t + 2 * NS, t + H, t + 2 * H])
        bid = np.array([1.1000, 1.1000, 1.1000, 1.0940, 1.1150])
        ask = bid + 0.0002
        r = self._run(ts, bid, ask, 1, stop=1.0950, target=1.1100)
        self.assertEqual(r["status"], "STOP")

    def test_data_gap_while_open_invalidates(self):
        t = ns("2016-04-06T08:00:00Z")
        ts = np.array([t, t + NS, t + 2 * NS, t + 5 * H, t + 10 * H])
        # stop (1.0950) is crossed only AFTER the hole -> no honest path
        bid = np.array([1.1000, 1.1000, 1.1000, 1.1000, 1.0940])
        ask = bid + 0.0002
        gaps = (int(ts[3]), int(ts[4]) - H)   # gap onset before the crossing
        r = self._run(ts, bid, ask, 1, stop=1.0950, gaps=(gaps,))
        self.assertEqual(r["status"], "DATA_GAP_INVALID")

    def test_gap_after_resolution_does_not_invalidate(self):
        t = ns("2016-04-06T08:00:00Z")
        ts = np.array([t, t + NS, t + 2 * NS, t + H, t + 10 * H])
        bid = np.array([1.1000, 1.1000, 1.1000, 1.1110, 1.1110])
        ask = bid + 0.0002
        gaps = (int(ts[4]), int(ts[4]) + 3 * H)     # after the target tick
        r = self._run(ts, bid, ask, 1, stop=1.0950, target=1.1100, gaps=(gaps,))
        self.assertEqual(r["status"], "TARGET")


class TestDiscoveryPass(unittest.TestCase):
    def _store(self, t0, n_hours=30, spread=0.0002):
        ts = [t0 + i * NS for i in range(n_hours * 3600)]
        bid = np.full(len(ts), 1.1000)
        ask = bid + spread
        return ArrayStore(np.array(ts), bid, ask)

    def test_one_position_at_a_time_occupancy(self):
        t0 = ns("2016-05-02T00:00:00Z")
        store = self._store(t0, n_hours=40)
        gap0 = np.array([], dtype=np.int64)
        # two A triggers 1h apart; first trade occupies for 24h
        ev = [{"kind": "A", "decision_ns": t0 + H, "side": 1,
               "stop_price": 1.0900, "r_mult": 2.0, "T_ns": 24 * H},
              {"kind": "A", "decision_ns": t0 + 2 * H, "side": 1,
               "stop_price": 1.0900, "r_mult": 2.0, "T_ns": 24 * H},
              {"kind": "A", "decision_ns": t0 + 30 * H, "side": 1,
               "stop_price": 1.0900, "r_mult": 2.0, "T_ns": 24 * H}]
        trades, counts = L.run_discovery_pass(ev, store, gap0)
        self.assertEqual(len(trades), 2)   # 2nd ignored while open
        self.assertEqual(trades[0]["decision_ns"], t0 + H)
        self.assertEqual(trades[1]["decision_ns"], t0 + 30 * H)
        for t in trades:
            self.assertEqual(t["exit_reason"], "TIME")
            self.assertAlmostEqual(t["net_pips"], -2.0, places=6)

    def test_hard_end_skip_near_2019(self):
        t0 = ns("2018-12-31T20:00:00Z")
        store = self._store(t0, n_hours=4)          # ticks until 23:59
        ev = [{"kind": "C", "decision_ns": t0 + 3600 * NS, "side": 1,
               "atr": 0.0010, "sl_mult": 1.0,
               "target_price": 1.1050, "T_ns": 12 * H}]
        trades, counts = L.run_discovery_pass(ev, store, np.array([], dtype=np.int64))
        self.assertEqual(len(trades), 0)
        self.assertEqual(counts["SKIPPED_HARD_END"], 1)  # fill+12h crosses 2019

    def test_c_target_crossed_at_entry_no_trade(self):
        t0 = ns("2016-05-02T00:00:00Z")
        store = self._store(t0)
        ev = [{"kind": "C", "decision_ns": t0 + H, "side": 1, "atr": 0.0010,
               "sl_mult": 1.0, "target_price": 1.1001, "T_ns": 12 * H}]
        trades, counts = L.run_discovery_pass(ev, store, np.array([], dtype=np.int64))
        self.assertEqual(len(trades), 0)
        self.assertEqual(counts["NO_TRADE_TARGET_CROSSED"], 1)

    def test_a_invalid_stop_not_beyond_entry(self):
        t0 = ns("2016-05-02T00:00:00Z")
        store = self._store(t0)
        ev = [{"kind": "A", "decision_ns": t0 + H, "side": 1,
               "stop_price": 1.1005, "r_mult": 2.0, "T_ns": 24 * H}]
        trades, counts = L.run_discovery_pass(ev, store, np.array([], dtype=np.int64))
        self.assertEqual(len(trades), 0)
        self.assertEqual(counts["INVALID_STOP"], 1)

    def test_b_uses_atr_stop_and_2r_target(self):
        t0 = ns("2016-05-02T00:00:00Z")
        # falling market hits the B stop: entry 1.1002, stop entry-1.5*0.001
        ts = np.array([t0 + i * NS for i in range(40 * 3600)])
        bid = np.full(len(ts), 1.1000)
        bid[len(ts) // 2:] = 1.0970                  # crash through stop
        ask = bid + 0.0002
        store = ArrayStore(ts, bid, ask)
        ev = [{"kind": "B", "decision_ns": t0 + H, "side": 1, "atr": 0.0010,
               "sl_mult": 1.5, "r_mult": 2.0, "T_ns": 48 * H}]
        trades, _ = L.run_discovery_pass(ev, store, np.array([], dtype=np.int64))
        self.assertEqual(len(trades), 1)
        tr = trades[0]
        self.assertEqual(tr["exit_reason"], "STOP")
        self.assertAlmostEqual(tr["entry"], 1.1002, places=9)
        self.assertAlmostEqual(tr["stop"], 1.1002 - 0.0015, places=9)
        self.assertAlmostEqual(tr["target"], 1.1002 + 0.0030, places=9)
        self.assertAlmostEqual(tr["risk_pips"], 15.0, places=6)
        self.assertAlmostEqual(tr["net_pips"], (1.0970 - 1.1002) / 1e-4,
                               places=6)


class TestStrategyLogic(unittest.TestCase):
    def _bars(self, starts, o, h, l, c):
        n = len(starts)
        return {"start": np.asarray(starts, dtype=np.int64),
                "open": np.asarray(o, float), "high": np.asarray(h, float),
                "low": np.asarray(l, float), "close": np.asarray(c, float),
                "n_ticks": np.ones(n, dtype=np.int64),
                "close_ts": np.asarray(starts, dtype=np.int64) + H}

    def test_breakout_reference_excludes_current_bar(self):
        t0 = ns("2016-06-01T00:00:00Z")
        n = 25
        starts = [t0 + i * H for i in range(n)]
        c = [1.1000] * n
        h = [1.1005] * n
        l = [1.0995] * n
        o = list(c)
        # signal bar itself has the highest high of all 25 bars, so if the
        # reference window wrongly included it, close (1.15) < high (1.20)
        h[-1] = 1.2000
        c[-1] = 1.1500
        bars = self._bars(starts, o, h, l, c)
        # no completed H4 bar (single close far in the past) -> regime 0
        h4_none = np.array([t0 - 10 * H])
        e50_flat = np.array([1.0] * 4)
        e200_flat = np.array([1.0] * 4)
        ev = L.strategy_B_events(h4_none, bars, e50_flat, e200_flat,
                                 np.full(n, 0.001), lookback=20)
        self.assertEqual(len(ev), 0)
        # completed H4 bars available: rising EMA50 above EMA200 -> long regime
        h4_ts = np.array([t0 + (i - 5) * H for i in range(10)])
        e50_up = np.linspace(1.0, 1.2, 10)
        e200 = np.full(10, 1.1)
        ev3 = L.strategy_B_events(h4_ts, bars, e50_up, e200,
                                  np.full(n, 0.001), lookback=20)
        # close 1.15 > prev-20 max high 1.1005 -> fires despite own 1.20 high
        self.assertEqual(len(ev3), 1)
        self.assertEqual(ev3[0]["side"], 1)

    def test_m15_trigger_uses_previous_completed_bar(self):
        t0 = ns("2016-06-01T00:00:00Z")
        # H1 pullback at 10:00-11:00 (closes 11:00); regime long
        h1_starts = np.array([t0 + 9 * H, t0 + 10 * H, t0 + 11 * H])
        h1 = {"start": h1_starts,
              "high": np.array([1.1010, 1.0990, 1.1010]),
              "low": np.array([1.0990, 1.0950, 1.0990]),
              "close": np.array([1.1005, 1.0970, 1.1005]),
              "open": np.array([1.1000] * 3),
              "n_ticks": np.array([1, 1, 1]),
              "close_ts": h1_starts + H}
        e20 = np.array([1.0995, 1.0960, 1.0995])   # pullback bar 2 dips
        e50 = np.array([1.0990, 1.0950, 1.0990])   # close stays above EMA50
        m15_starts = []
        m15_h, m15_l, m15_c = [], [], []
        m = t0 + 8 * H  # M15 from 08:00
        for i in range(16):  # 08:00 .. 11:45
            m15_starts.append(m + i * 900 * NS)
            m15_h.append(1.1000); m15_l.append(1.0990); m15_c.append(1.0995)
        # window bars after pullback close (11:00): indices 12..15
        # bar 12 high 1.1010 -> trigger needs close > 1.1010
        m15_h[12] = 1.1010; m15_c[12] = 1.1000       # no trigger
        m15_h[13] = 1.1005; m15_c[13] = 1.1020       # close > prev high -> TRIGGER
        m15 = {"start": np.array(m15_starts),
               "high": np.array(m15_h), "low": np.array(m15_l),
               "close": np.array(m15_c), "open": np.array(m15_c),
               "n_ticks": np.ones(16, dtype=np.int64)}
        # completed H4 bars (closes 1h..8h): rising EMA50 above EMA200
        h4_close_ts = np.array([t0 + i * H for i in range(1, 9)])
        e50_h4 = np.array([1.0] * 6 + [1.1, 1.1])
        e200_h4 = np.full(8, 1.0)
        ev = L.strategy_A_events(h4_close_ts, h1, m15, e20, e50, e50_h4, e200_h4)
        self.assertEqual(len(ev), 1)
        self.assertEqual(ev[0]["side"], 1)
        self.assertEqual(ev[0]["decision_ns"], int(m15_starts[13] + 900 * NS))
        self.assertAlmostEqual(ev[0]["stop_price"], 1.0950)  # pullback LOW

    def test_m15_window_expires_after_four_bars(self):
        t0 = ns("2016-06-01T00:00:00Z")
        h1_starts = np.array([t0 + 9 * H, t0 + 10 * H, t0 + 15 * H])
        h1 = {"start": h1_starts,
              "high": np.array([1.1010, 1.0990, 1.1010]),
              "low": np.array([1.0990, 1.0950, 1.0990]),
              "close": np.array([1.1005, 1.0970, 1.1005]),
              "open": np.array([1.1000] * 3),
              "n_ticks": np.array([1, 1, 1]),
              "close_ts": h1_starts + H}
        e20 = np.array([1.0995, 1.0960, 1.0995])
        e50 = np.array([1.0990, 1.0950, 1.0990])
        m15_starts, m15_h, m15_l, m15_c = [], [], [], []
        m = t0 + 8 * H
        for i in range(36):   # 08:00 .. 16:45
            m15_starts.append(m + i * 900 * NS)
            m15_h.append(1.1000); m15_l.append(1.0990); m15_c.append(1.0995)
        m15 = {"start": np.array(m15_starts),
               "high": np.array(m15_h), "low": np.array(m15_l),
               "close": np.array(m15_c), "open": np.array(m15_c),
               "n_ticks": np.ones(36, dtype=np.int64)}
        h4_close_ts = np.array([t0 + i * H for i in range(1, 9)])
        e50_h4 = np.array([1.0] * 6 + [1.1, 1.1])
        e200_h4 = np.full(8, 1.0)
        ev = L.strategy_A_events(h4_close_ts, h1, m15, e20, e50, e50_h4, e200_h4)
        self.assertEqual(len(ev), 0)   # no trigger inside the 4-bar window

    def test_h4_regime_uses_only_completed_bars(self):
        t0 = ns("2016-06-01T00:00:00Z")
        closes_ts = np.array([t0 + (2 + 2 * i) * H for i in range(6)])  # 2h..12h
        e50 = np.array([1.02, 1.02, 1.02, 1.03, 1.03, 1.00])
        e200 = np.full(6, 1.02)
        self.assertEqual(L.h4_regime_at(closes_ts, e50, e200,
                                        t0 + 6 * H), 0)      # idx 2 < 3
        self.assertEqual(L.h4_regime_at(closes_ts, e50, e200,
                                        t0 + 8 * H + 1), 1)  # completed at 8h
        self.assertEqual(L.h4_regime_at(closes_ts, e50, e200,
                                        t0 + 12 * H), -1)    # 12h bar complete
        self.assertEqual(L.h4_regime_at(closes_ts, e50, e200,
                                        t0 + 10 * H + 1), 1)


class TestMetrics(unittest.TestCase):
    def test_remove_best_and_bootstrap_deterministic(self):
        net = np.array([1.0, -1.0, 2.0, -0.5, 3.0, -2.0, 0.5, 0.2, -0.1, 10.0])
        rb = L.remove_best_1pct(net)               # removes the 10.0 (ceil 1%)
        self.assertAlmostEqual(rb, float(net[:-1].mean()), places=12)
        c1 = L.bootstrap_ci95(net)
        c2 = L.bootstrap_ci95(net)
        self.assertEqual(c1, c2)                   # seed 42 deterministic

    def test_gate_verdict_fail_fast(self):
        base = {"net_mean_pips": -1.0, "profit_factor": 0.8,
                "expectancy_r": -0.1, "positive_years": 2,
                "remove_best_1pct_mean": -0.5, "stress_010_mean": -1.2,
                "n_trades": 500, "total_net_pips": -500.0}
        self.assertEqual(L.gate_verdict(base), "REJECT")
        passing = dict(base, net_mean_pips=2.5, profit_factor=1.4,
                       expectancy_r=0.2, positive_years=7,
                       remove_best_1pct_mean=0.3, stress_010_mean=2.3,
                       total_net_pips=1000.0)
        self.assertEqual(L.gate_verdict(passing), "MTF_DISCOVERY_PROMISING")
        mid = dict(passing, profit_factor=1.1)     # positive but weak
        self.assertEqual(L.gate_verdict(mid), "FAIL_GATE")


if __name__ == "__main__":
    unittest.main(verbosity=2)
