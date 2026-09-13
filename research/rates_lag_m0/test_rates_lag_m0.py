#!/usr/bin/env python3
"""RATES-LAG-M0 synthetic validation tests (frozen spec section 18).

Pure synthetic data — no network, no E: dependency, no real dataset.
Run:  python -m unittest research.rates_lag_m0.test_rates_lag_m0 -v
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rates_lag_lib as L  # noqa: E402

NS = 1
S = 1_000_000_000
T0 = 1_412_339_400_000_000_000  # 2014-10-03T12:30:00Z, inside Discovery


def ns(off_s: float) -> int:
    return T0 + int(round(off_s * S))


class TestDiscoveryGuards(unittest.TestCase):
    def test_2019_cutoff_range_guard(self):
        with self.assertRaises(L.OutOfWindowError):
            L.assert_discovery_range(ns(0), int(np.datetime64("2019-01-02", "ns")
                                                .astype(np.int64)))
        with self.assertRaises(L.OutOfWindowError):
            L.assert_discovery_range(int(np.datetime64("2019-01-01", "ns")
                                         .astype(np.int64)),
                                     int(np.datetime64("2019-02-01", "ns")
                                         .astype(np.int64)))
        # inside Discovery: OK
        L.assert_discovery_range(T0, T0 + 300 * S)

    def test_discovery_bounds_constants(self):
        self.assertEqual(L.DISCOVERY_END_NS,
                         int(np.datetime64("2019-01-01", "ns").astype(np.int64)))
        self.assertEqual(L.DISCOVERY_START_NS,
                         int(np.datetime64("2010-06-07", "ns").astype(np.int64)))

    def test_event_universe_statuses_and_cutoff(self):
        m = {"entries": {
            # both ok, inside window -> kept
            "A:ZF": {"event_id": "A", "family": "NFP", "status": "ok", "symbol": "ZF",
                     "t0": "2014-10-03T12:30:00+00:00", "raw_symbol": "ZFZ4"},
            "A:ZN": {"event_id": "A", "family": "NFP", "status": "ok", "symbol": "ZN",
                     "t0": "2014-10-03T12:30:00+00:00", "raw_symbol": "ZNZ4"},
            # ZN zero_records -> dropped
            "B:ZF": {"event_id": "B", "family": "CPI", "status": "ok", "symbol": "ZF",
                     "t0": "2015-01-09T13:30:00+00:00", "raw_symbol": "ZFZ5"},
            "B:ZN": {"event_id": "B", "family": "CPI", "status": "zero_records",
                     "symbol": "ZN", "t0": "2015-01-09T13:30:00+00:00",
                     "raw_symbol": "ZNZ5"},
            # EXPECTED_MARKET_CLOSED -> dropped
            "C:ZF": {"event_id": "C", "family": "CPI", "status": "EXPECTED_MARKET_CLOSED",
                     "symbol": "ZF", "t0": "2017-04-14T12:30:00+00:00",
                     "raw_symbol": "ZFM7"},
            "C:ZN": {"event_id": "C", "family": "CPI", "status": "EXPECTED_MARKET_CLOSED",
                     "symbol": "ZN", "t0": "2017-04-14T12:30:00+00:00",
                     "raw_symbol": "ZNM7"},
            # CONFIRMED_DATA_GAP -> dropped
            "D:ZF": {"event_id": "D", "family": "NFP", "status": "CONFIRMED_DATA_GAP",
                     "symbol": "ZF", "t0": "2014-10-03T12:30:00+00:00",
                     "raw_symbol": "ZFZ4"},
            "D:ZN": {"event_id": "D", "family": "NFP", "status": "CONFIRMED_DATA_GAP",
                     "symbol": "ZN", "t0": "2014-10-03T12:30:00+00:00",
                     "raw_symbol": "ZNZ4"},
            # 2019+ forbidden -> dropped
            "E:ZF": {"event_id": "E", "family": "NFP", "status": "ok", "symbol": "ZF",
                     "t0": "2019-01-04T13:30:00+00:00", "raw_symbol": "ZFH9"},
            "E:ZN": {"event_id": "E", "family": "NFP", "status": "ok", "symbol": "ZN",
                     "t0": "2019-01-04T13:30:00+00:00", "raw_symbol": "ZNH9"},
            # before 2010-06-07 -> dropped
            "F:ZF": {"event_id": "F", "family": "NFP", "status": "ok", "symbol": "ZF",
                     "t0": "2010-01-08T13:30:00+00:00", "raw_symbol": "ZFH0"},
            "F:ZN": {"event_id": "F", "family": "NFP", "status": "ok", "symbol": "ZN",
                     "t0": "2010-01-08T13:30:00+00:00", "raw_symbol": "ZNH0"},
        }}
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "m.json"
            p.write_text(json.dumps(m))
            evs = L.load_valid_events(str(p))
        self.assertEqual([e.event_id for e in evs], ["A"])
        self.assertEqual(evs[0].zf_raw, "ZFZ4")
        self.assertEqual(evs[0].t0_ns, T0)


class TestRateBookCausality(unittest.TestCase):
    def _book(self, ts_offsets_s, mids, ts_recv_offsets_s=None):
        """Build a RateBook; optionally with ts_recv differing from ts_event."""
        if ts_recv_offsets_s is None:
            ts_recv_offsets_s = ts_offsets_s
        return L.RateBook.from_records(
            np.array([ns(o) for o in ts_recv_offsets_s], dtype=np.int64),
            np.array(mids, dtype=np.float64),
            np.array(mids, dtype=np.float64),
            window_start_ns=ns(-301))

    def test_ts_recv_selection_not_ts_event(self):
        # ts_recv order differs from a hypothetical ts_event ordering:
        # selection must use ts_recv (what we feed it).
        b = self._book([0.0, 1.0, 2.0], [10.0, 11.0, 12.0],
                       ts_recv_offsets_s=[0.0, 1.0, 2.0])
        self.assertEqual(b.pre_mid(ns(2.0)), 11.0)
        self.assertEqual(b.horizon_mid(ns(2.0), 10), 12.0)

    def test_pre_rate_mid_causal_strictly_before(self):
        b = self._book([-5.0, -1.0, 0.0, 3.0], [100.0, 101.0, 102.0, 103.0])
        self.assertEqual(b.pre_mid(T0), 101.0)      # record AT T0 is NOT pre
        self.assertEqual(b.pre_mid(ns(0.5)), 102.0)
        self.assertIsNone(b.pre_mid(ns(-10)))        # nothing before
        self.assertEqual(b.pre_mid(ns(-0.5)), 101.0)  # -1s IS strictly before -0.5s

    def test_horizon_window_h10_bound(self):
        # last obs inside [T0, T0+10s] wins; +10s+1ns is NOT accessible
        b = self._book([-2.0, 9.999999999, 10.000000001], [1.0, 2.0, 99.0])
        self.assertEqual(b.horizon_mid(T0, 10), 2.0)
        self.assertEqual(b.horizon_mid(T0, 11), 99.0)

    def test_horizon_window_h30_bound(self):
        b = self._book([-2.0, 30.0, 30.000000001], [1.0, 2.0, 99.0])
        self.assertEqual(b.horizon_mid(T0, 30), 2.0)   # closed upper bound T0+30s
        self.assertEqual(b.horizon_mid(T0, 60), 99.0)

    def test_horizon_window_h60_latest_within(self):
        b = self._book([1.0, 5.0, 60.0], [1.0, 2.0, 3.0])
        self.assertEqual(b.horizon_mid(T0, 60), 3.0)   # LAST within window, not first

    def test_horizon_unavailable(self):
        b = self._book([-3.0, -1.0], [1.0, 2.0])       # nothing at/after T0
        self.assertIsNone(b.horizon_mid(T0, 10))
        self.assertIsNone(b.horizon_mid(T0, 30))
        self.assertIsNone(b.horizon_mid(T0, 60))

    def test_invalid_bbo_records_skipped_midpoint(self):
        ts = np.array([ns(-5), ns(-4), ns(-3), ns(1), ns(2), ns(3)])
        bid = np.array([100.0, np.nan, -1.0, 0.0, 101.0, 102.0])
        ask = np.array([100.125, 100.2, 100.3, 100.4, np.inf, 102.0625])
        b = L.RateBook.from_records(ts, bid, ask, window_start_ns=ns(-301))
        # kept: (-5, 100.0625), (2? no bid=0 at ns(1) dropped, nan dropped, inf dropped)
        self.assertEqual(b.ts.tolist(), [ns(-5), ns(3)])
        self.assertAlmostEqual(b.mid[0], (100.0 + 100.125) / 2)
        self.assertAlmostEqual(b.mid[1], (102.0 + 102.0625) / 2)

    def test_window_start_hygiene_drops_pre_window(self):
        ts = np.array([ns(-400), ns(-300), ns(-1)])
        bid = ask = np.array([1.0, 2.0, 3.0])
        b = L.RateBook.from_records(ts, bid, ask, window_start_ns=ns(-300))
        self.assertEqual(b.ts.tolist(), [ns(-300), ns(-1)])


class TestRateSignal(unittest.TestCase):
    ZF_TICK = 0.0078125
    ZN_TICK = 0.015625

    def test_minimum_increment_guard(self):
        # exactly one tick each -> signal
        self.assertEqual(L.rate_signal(110.0, 110.0 + self.ZF_TICK,
                                       120.0, 120.0 + self.ZN_TICK,
                                       self.ZF_TICK, self.ZN_TICK), 1)
        # just under one tick on ZF -> no signal
        self.assertEqual(L.rate_signal(110.0, 110.0 + self.ZF_TICK * 0.99,
                                       120.0, 120.0 + self.ZN_TICK,
                                       self.ZF_TICK, self.ZN_TICK), 0)
        # just under on ZN -> no signal
        self.assertEqual(L.rate_signal(110.0, 110.0 + self.ZF_TICK,
                                       120.0, 120.0 + self.ZN_TICK * 0.99,
                                       self.ZF_TICK, self.ZN_TICK), 0)

    def test_same_sign_requirement(self):
        # opposite signs -> no signal
        self.assertEqual(L.rate_signal(110.0, 110.0 + self.ZF_TICK,
                                       120.0, 120.0 - self.ZN_TICK,
                                       self.ZF_TICK, self.ZN_TICK), 0)
        # ZF moves, ZN flat -> no signal
        self.assertEqual(L.rate_signal(110.0, 110.0 + self.ZF_TICK,
                                       120.0, 120.0,
                                       self.ZF_TICK, self.ZN_TICK), 0)
        # both down -> signal -1
        self.assertEqual(L.rate_signal(110.0, 110.0 - self.ZF_TICK,
                                       120.0, 120.0 - self.ZN_TICK,
                                       self.ZF_TICK, self.ZN_TICK), -1)

    def test_direction_mapping_frozen(self):
        # Treasury UP -> yields DOWN -> USD weaker -> EURUSD LONG (+1)
        self.assertEqual(L.rate_signal(1.0, 2.0, 1.0, 2.0, 0.001, 0.001), 1)
        # Treasury DOWN -> yields UP -> USD stronger -> EURUSD SHORT (-1)
        self.assertEqual(L.rate_signal(1.0, 0.5, 1.0, 0.5, 0.001, 0.001), -1)

    def test_unavailable_inputs(self):
        self.assertEqual(L.rate_signal(None, 1.0, 1.0, 1.0, 0.1, 0.1), 0)
        self.assertEqual(L.rate_signal(1.0, 1.0, None, 1.0, 0.1, 0.1), 0)


class TestFxExecution(unittest.TestCase):
    def _fx(self, offsets_s, bid, ask):
        return L.FxBook.from_records(
            np.array([ns(o) for o in offsets_s], dtype=np.int64),
            np.array(bid, dtype=np.float64), np.array(ask, dtype=np.float64))

    # decision = T0+10s. LONG entry ref = T0+11s, SHORT ref = T0+11s.
    def test_long_asks_entry_1s_delay(self):
        fx = self._fx([0, 11.0, 11.5, 20.0],
                      [1.1000, 1.1002, 1.1004, 1.1006],
                      [1.0001, 1.1004, 1.1006, 1.1008])
        q = fx.entry(ns(10.0), 1.0, +1)
        self.assertEqual(q, (ns(11.0), 1.1004))     # first ASK at/after T0+11s

    def test_entry_not_before_reference(self):
        fx = self._fx([10.5, 11.0], [1.0, 1.0], [1.2, 1.2])
        q = fx.entry(ns(10.0), 1.0, +1)             # quote at 10.5 is too early
        self.assertEqual(q, (ns(11.0), 1.2))

    def test_short_bids_entry(self):
        fx = self._fx([11.0, 12.0], [1.0610, 1.0612], [1.0614, 1.0616])
        q = fx.entry(ns(10.0), 1.0, -1)
        self.assertEqual(q, (ns(11.0), 1.0610))     # BID for short entry

    def test_latency_5s_delay(self):
        fx = self._fx([13.0, 15.0, 15.5], [1.0, 1.05, 1.06], [1.1, 1.06, 1.07])
        q = fx.entry(ns(10.0), 5.0, +1)
        self.assertEqual(q, (ns(15.0), 1.06))       # first ASK at/after T0+15s

    def test_no_fill_beyond_10s_bound(self):
        fx = self._fx([21.5], [1.0], [1.1])
        self.assertIsNone(fx.entry(ns(10.0), 1.0, +1))  # next ask at +11.5s > bound

    def test_fill_at_exact_bound(self):
        fx = self._fx([21.0], [1.0], [1.1])
        q = fx.entry(ns(10.0), 1.0, +1)
        self.assertEqual(q, (ns(21.0), 1.1))        # exactly decision+1+10 is a fill

    def test_long_bid_exit_120s(self):
        fx = self._fx([0.0, 131.0, 131.5], [1.05, 1.0610, 1.0612],
                      [1.06, 1.0614, 1.0616])
        x = fx.exit(ns(11.0), +1)                   # entry T0+11s -> exit ref T0+131s
        self.assertEqual(x, (ns(131.0), 1.0610))    # first BID at/after

    def test_short_ask_exit_120s(self):
        fx = self._fx([131.0, 132.0], [1.05, 1.06], [1.0612, 1.0616])
        x = fx.exit(ns(11.0), -1)
        self.assertEqual(x, (ns(131.0), 1.0612))    # first ASK at/after

    def test_mark_side_convention(self):
        fx = self._fx([41.0], [1.0550, ], [1.0562])
        m = fx.mark(ns(11.0), +1, 30.0)             # LONG MTM at +30s uses BID
        self.assertEqual(m, (ns(41.0), 1.0550))
        m2 = fx.mark(ns(11.0), -1, 30.0)            # SHORT MTM uses ASK
        self.assertEqual(m2, (ns(41.0), 1.0562))

    def test_net_pips_spread_arithmetic(self):
        # LONG: enter ask 1.1004, exit bid 1.1044 -> +40 pips (spread already paid)
        self.assertAlmostEqual(L.net_pips(1.1004, 1.1044, +1), 40.0)
        # SHORT: enter bid 1.1002, exit ask 1.0982 -> +20 pips
        self.assertAlmostEqual(L.net_pips(1.1002, 1.0982, -1), 20.0)
        # losing short: enter 1.1000, exit ask 1.1030 -> -30
        self.assertAlmostEqual(L.net_pips(1.1000, 1.1030, -1), -30.0)

    def test_stress_arithmetic(self):
        self.assertAlmostEqual(L.stressed(3.0, 0.5), 2.0)
        self.assertAlmostEqual(L.stressed(3.0, 1.0), 1.0)
        self.assertAlmostEqual(L.stressed(-3.0, 0.5), -4.0)


class TestMakeTradeEndToEnd(unittest.TestCase):
    def test_full_baseline_plus_latency(self):
        fx = L.FxBook.from_records(
            np.array([ns(o) for o in [10.2, 11.4, 15.3, 41.8, 75.0, 131.8, 135.2,
                                      141.8, 171.8, 311.8, 411.8]], dtype=np.int64),
            np.array([1.0500, 1.0510, 1.0512, 1.0608, 1.0630, 1.0600, 1.0602,
                      1.0608, 1.0630, 1.0700, 1.0800]),
            np.array([1.0502, 1.0512, 1.0514, 1.0610, 1.0632, 1.0602, 1.0604,
                      1.0610, 1.0632, 1.0702, 1.0802]))
        ev = L.LagEvent("X", "NFP", T0, "ZFZ4", "ZNZ4", "", "")
        tr = _trade(ev, +1, 10.0, fx)
        self.assertEqual(tr["status"], "ok")
        self.assertEqual(tr["entry_ts_ns"], ns(11.4))      # dec=T0+10, +1s
        self.assertEqual(tr["entry_px"], 1.0512)           # ASK
        self.assertEqual(tr["exit_ts_ns"], ns(131.8))      # entry+120s
        self.assertEqual(tr["exit_px"], 1.0600)            # BID
        self.assertAlmostEqual(tr["net_pips"], 88.0)
        # latency 5s: entry ASK 1.0514 @+15.3s; exit ref +135.3s -> first BID
        # at/after is 1.0608 @+141.8s -> (1.0608-1.0514)*1e4
        self.assertAlmostEqual(tr["latency5_net"], 94.0)
        self.assertAlmostEqual(tr["stress050_net"], 87.0)
        self.assertAlmostEqual(tr["stress100_net"], 86.0)
        self.assertAlmostEqual(tr["realistic_net"], 93.0)
        self.assertAlmostEqual(tr["mtm30"], 96.0)    # bid 1.0608 @+41.8s vs entry 1.0512
        self.assertAlmostEqual(tr["mtm60"], 118.0)   # bid 1.0630 @+171.8s
        self.assertAlmostEqual(tr["mtm300"], 188.0)  # bid 1.0700 @+311.8s

    def test_short_flow(self):
        fx = L.FxBook.from_records(
            np.array([ns(o) for o in [11.2, 131.4]], dtype=np.int64),
            np.array([1.1000, 1.0900]),
            np.array([1.1002, 1.0902]))
        ev = L.LagEvent("X", "CPI", T0, "ZFZ4", "ZNZ4", "", "")
        tr = _trade(ev, -1, 10.0, fx)
        self.assertEqual(tr["status"], "ok")
        self.assertEqual(tr["entry_px"], 1.1000)           # BID entry
        self.assertEqual(tr["exit_px"], 1.0902)            # ASK exit
        self.assertAlmostEqual(tr["net_pips"], 98.0)

    def test_no_fill_recorded(self):
        fx = L.FxBook.from_records(np.array([ns(500.0)]), np.array([1.0]),
                                   np.array([1.1]))
        ev = L.LagEvent("X", "NFP", T0, "ZFZ4", "ZNZ4", "", "")
        tr = _trade(ev, +1, 10.0, fx)
        self.assertEqual(tr["status"], "NO_FILL")
        self.assertTrue(np.isnan(tr["net_pips"]))


def _trade(ev, direction, horizon_s, fx):
    """Direct use of run_discovery.make_trade without importing the runner's E:
    dependencies — re-implemented here via a tiny shim to keep tests offline."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import importlib
    rd = importlib.import_module("run_discovery")
    return rd.make_trade(ev, direction, horizon_s, fx)


class TestMetrics(unittest.TestCase):
    def test_remove_best_1pct(self):
        nets = np.array([5.0] * 99 + [1000.0])          # 100 trades
        m = L.remove_best_1pct_mean(nets)               # k = ceil(1) = 1
        self.assertAlmostEqual(m, 5.0)
        small = np.array([1.0, 2.0, 3.0])
        self.assertAlmostEqual(L.remove_best_1pct_mean(small), 1.5)  # k=1 removes 3

    def test_profit_factor_and_cap(self):
        self.assertAlmostEqual(L.profit_factor(np.array([2.0, 3.0, -2.5])), 2.0)
        self.assertEqual(L.profit_factor(np.array([2.0, 2.0])), L.PF_CAP)

    def test_bootstrap_deterministic_seed42(self):
        nets = np.array([1.0, -1.0, 2.0, -0.5, 0.25] * 20)
        a = L.bootstrap_ci95_mean(nets)
        b = L.bootstrap_ci95_mean(nets)
        self.assertEqual(a, b)
        lo, hi = a
        self.assertLessEqual(lo, hi)

    def test_year_buckets(self):
        ets = np.array([int(np.datetime64("2013-06-05T12:31", "ns").astype(np.int64)),
                        int(np.datetime64("2014-01-05T12:31", "ns").astype(np.int64)),
                        int(np.datetime64("2014-06-05T12:31", "ns").astype(np.int64))])
        nets = np.array([10.0, -20.0, 5.0])
        pos, elig = L.year_bucket_stats(ets, nets)
        self.assertEqual((pos, elig), (1, 2))

    def test_gate_matrix(self):
        base = dict(N_TRADES=60, NET_MEAN_PIPS=3.0, PROFIT_FACTOR=1.3,
                    TOTAL_NET_PIPS=180.0, POSITIVE_YEARS=7, YEARS_ELIGIBLE=8,
                    REMOVE_BEST_1_PERCENT_NET_MEAN=1.0, LATENCY_5S_MEAN=1.5,
                    REALISTIC_STRESS_MEAN=0.5, NFP_MEAN=2.0, CPI_MEAN=2.5)
        self.assertTrue(L.gate(dict(base)))
        # boundary: NET_MEAN == 2.0 exactly still passes (>= threshold)
        at_thr = dict(base)
        at_thr["NET_MEAN_PIPS"] = 2.0
        self.assertTrue(L.gate(at_thr))
        for key, bad in [("N_TRADES", 49), ("NET_MEAN_PIPS", 1.99),
                         ("PROFIT_FACTOR", 1.19), ("TOTAL_NET_PIPS", 0.0),
                         ("REMOVE_BEST_1_PERCENT_NET_MEAN", 0.0),
                         ("LATENCY_5S_MEAN", 0.0), ("REALISTIC_STRESS_MEAN", -0.1),
                         ("NFP_MEAN", -0.1), ("CPI_MEAN", 0.0)]:
            broken = dict(base)
            broken[key] = bad
            self.assertFalse(L.gate(broken), f"gate must fail on {key}={bad}")
        ratio_broken = dict(base)
        ratio_broken.update(POSITIVE_YEARS=5, YEARS_ELIGIBLE=8)  # 0.625 < 0.67
        self.assertFalse(L.gate(ratio_broken))
        # N_TRADES == 50 exactly is eligible if the rest pass
        fifty = dict(base)
        fifty["N_TRADES"] = 50
        self.assertTrue(L.gate(fifty))

    def test_stability_counts(self):
        sig = {"H10": {"a": 1, "b": 1, "c": -1},
               "H30": {"a": 1, "b": -1, "c": -1, "d": 1},
               "H60": {"a": -1, "b": -1, "c": -1}}
        st = L.stability_counts(sig)
        self.assertEqual(st["H10_SIGNAL_COUNT"], 3)
        self.assertEqual(st["H30_SIGNAL_COUNT"], 4)
        self.assertEqual(st["H60_SIGNAL_COUNT"], 3)
        self.assertAlmostEqual(st["H10_TO_H30_SAME_DIRECTION_PCT"], 200 / 3)
        # H30∩H60 = {a,b,c}: a differs, b same, c same -> 2/3
        self.assertAlmostEqual(st["H30_TO_H60_SAME_DIRECTION_PCT"], 200 / 3)
        # H10∩H60 = {a,b,c}: only c same -> 1/3
        self.assertAlmostEqual(st["H10_TO_H60_SAME_DIRECTION_PCT"], 100 / 3)


class TestTickSizes(unittest.TestCase):
    def test_tick_size_map_shape(self):
        # repo artifact exists (tiny JSON); values must match authoritative defs
        p = Path(__file__).parent / "instrument_tick_sizes.json"
        self.assertTrue(p.exists())
        ticks = L.load_tick_sizes(str(p))
        zf = {v for k, v in ticks.items() if k.startswith("ZF")}
        zn = {v for k, v in ticks.items() if k.startswith("ZN")}
        self.assertEqual(zf, {0.0078125})   # 1/128 (Databento definitions)
        self.assertEqual(zn, {0.015625})   # 1/64
        self.assertGreaterEqual(len(ticks), 70)


if __name__ == "__main__":
    unittest.main()
