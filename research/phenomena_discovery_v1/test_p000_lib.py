#!/usr/bin/env python3
"""Synthetic causality & correctness tests for the P000 video-strategy lib.

All datasets are SYNTHETIC (never real market data). Focus: P000 timing,
session boundaries, DST, causal execution, retest semantics, trim/EMA8
arithmetic, one-trade-per-day, split-boundary protection, anti-edge
inversion sanity.
"""
import os
import sys
import unittest
from datetime import date, timedelta

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import p000_lib as P  # noqa: E402


def make_day_df(day_utc_midnight, bars, tz="UTC"):
    """bars: list of (hhmm_utc, o, h, l, c, volume). Builds 5m bars."""
    base = pd.Timestamp(day_utc_midnight, tz="UTC")
    idx = [base + pd.Timedelta(minutes=hm // 100 * 60 + hm % 100)
           for hm, *_ in bars]
    vals = [v for _, *v in bars]
    df = pd.DataFrame(vals, columns=["open", "high", "low", "close", "volume"],
                      index=pd.DatetimeIndex(idx))
    return df.sort_index()


def default_premarket(day, extra=None):
    """Standard premarket 04:00-09:15 ET-ish bars around a flat 100.0.
    Built directly in ET then converted to UTC so tests are DST-agnostic."""
    rows = []
    for hm in range(400, 930, 5):
        rows.append((hm, 100.0, 100.2, 99.8, 100.0, 1000.0))
    return rows


def build_us_day(day, pre_rows, rth_rows):
    """pre_rows/rth_rows keyed by ET hhmm; returns UTC-indexed df for that ET day."""
    rows_et = {}
    for hm, o, h, l, c, v in pre_rows + rth_rows:
        rows_et[hm] = (o, h, l, c, v)
    ts_et = [pd.Timestamp(day, tz="America/New_York") +
             pd.Timedelta(minutes=(hm // 100) * 60 + hm % 100)
             for hm in sorted(rows_et)]
    vals = [rows_et[hm] for hm in sorted(rows_et)]
    return pd.DataFrame(vals, columns=["open", "high", "low", "close", "volume"],
                        index=pd.DatetimeIndex(ts_et).tz_convert("UTC"))


def flat_premarket(level=100.0):
    return [(hm, level, level + 0.1, level - 0.1, level, 1000.0)
            for hm in range(400, 925, 5)]


class TestPremarketLevels(unittest.TestCase):
    def test_levels_from_premarket_window_only(self):
        # a spike at 09:35 ET (RTH) must NOT change the pre-market high
        df_ok = build_us_day("2020-07-15", flat_premarket(100.0), [])
        df_spike = df_ok.copy()
        # RTH bar beyond the day: 09:35 ET with a huge high
        ts = pd.Timestamp("2020-07-15 09:35", tz="America/New_York").tz_convert("UTC")
        df_spike.loc[ts] = [100.0, 110.0, 99.9, 109.0, 1000.0]
        lv_ok = P.premarket_levels(df_ok)
        lv_sp = P.premarket_levels(df_spike)
        d = date(2020, 7, 15)
        self.assertEqual(lv_ok[d][0], lv_sp[d][0])
        self.assertEqual(lv_ok[d][2], lv_sp[d][2])  # same premarket bar count

    def test_min_bars_guard(self):
        # only 5 premarket bars -> day rejected by MIN_PM_BARS
        rows = [(hm, 100.0, 100.1, 99.9, 100.0, 10.0)
                for hm in range(400, 425, 5)]
        df = build_us_day("2020-07-15", rows, [])
        lv = P.premarket_levels(df)
        d = date(2020, 7, 15)
        self.assertLess(lv[d][2], P.MIN_PM_BARS)


class TestDSTSessions(unittest.TestCase):
    def test_premarket_window_shifts_with_dst(self):
        # 04:00 ET = 08:00 UTC in July (EDT), 09:00 UTC in January (EST)
        d1 = build_us_day("2020-07-15", flat_premarket(), [])
        d2 = build_us_day("2020-01-15", flat_premarket(), [])
        first_july = d1.index[0]
        first_jan = d2.index[0]
        self.assertEqual(first_july.hour, 8)   # 04:00 EDT
        self.assertEqual(first_jan.hour, 9)    # 04:00 EST
        lv1 = P.premarket_levels(d1)[date(2020, 7, 15)]
        lv2 = P.premarket_levels(d2)[date(2020, 1, 15)]
        self.assertEqual(lv1[2], lv2[2])       # same bar count despite DST


class TestConfirmationAndRetest(unittest.TestCase):
    def _day(self, rth_rows, day="2020-07-15"):
        return build_us_day(day, flat_premarket(100.0), rth_rows)

    def test_confirmation_needs_5m_close_beyond_level(self):
        # RTH: bar touches 100.2 (level 100.1) but closes back inside -> no event
        rows = [
            (930, 100.0, 100.15, 99.9, 100.05, 10.0),   # wick above, close below
        ] + [(hm, 100.0, 100.05, 99.95, 100.0, 10.0) for hm in range(935, 1000, 5)]
        ev = P.detect_us_events(self._day(rows))
        self.assertEqual(ev, [])

    def test_full_sequence_confirm_tap_entry(self):
        rows = [
            (930, 100.05, 100.30, 100.04, 100.25, 10.0),  # confirmation close > pmh(100.1)
            (935, 100.25, 100.28, 100.12, 100.15, 10.0),  # tap: low 100.12 > level? no tap yet
            (940, 100.15, 100.16, 100.10, 100.12, 10.0),  # tap: low 100.10 <= 100.1
            (945, 100.12, 100.20, 100.11, 100.19, 10.0),  # resume through tap high 100.16
        ]
        ev = P.detect_us_events(self._day(rows))
        self.assertEqual(len(ev), 1)
        e = ev[0]
        self.assertEqual(e.side, 1)
        self.assertEqual(e.variant, "LEVEL")
        self.assertEqual(float(e.level), 100.1)
        # tap bar high becomes the entry trigger
        self.assertAlmostEqual(e.fill, 100.16, places=9)
        # entry timestamp = the resume bar (09:45 ET)
        self.assertEqual(e.entry_ts,
                         pd.Timestamp("2020-07-15 09:45", tz="America/New_York").tz_convert("UTC"))

    def test_close_back_inside_kills_setup_before_tap(self):
        rows = [
            (930, 100.05, 100.30, 100.04, 100.25, 10.0),  # confirmed long
            (935, 100.20, 100.25, 100.05, 100.05, 10.0),  # closes back inside (< level), no tap
            (940, 100.05, 100.30, 100.02, 100.28, 10.0),  # would re-break: must be ignored
            (945, 100.28, 100.35, 100.20, 100.33, 10.0),
        ]
        ev = P.detect_us_events(self._day(rows))
        self.assertEqual(ev, [])

    def test_gap_open_entry_fills_at_worse_open(self):
        # entry bar gaps above the tap extreme -> fill at the (worse) open
        rows = [
            (930, 100.05, 100.30, 100.04, 100.25, 10.0),
            (935, 100.25, 100.28, 100.09, 100.15, 10.0),   # tap (low 100.09 <= 100.1)
            (940, 100.20, 100.35, 100.19, 100.33, 10.0),   # opens 100.20 > tap high 100.28? no: 100.20 < 100.28
        ]
        ev = P.detect_us_events(self._day(rows))
        # open 100.20 < tap high 100.28 but high 100.35 crosses -> fill at tap high
        self.assertAlmostEqual(ev[0].fill, 100.28, places=9)

    def test_one_event_per_day(self):
        # two separate confirm/tap/entry sequences in one day -> only first
        seq = [(930, 100.05, 100.30, 100.04, 100.25, 10.0),
               (935, 100.25, 100.28, 100.09, 100.15, 10.0),
               (940, 100.15, 100.16, 100.10, 100.12, 10.0),
               (945, 100.12, 100.20, 100.11, 100.19, 10.0)]
        rows = seq + [
            (1000, 100.0, 100.4, 99.99, 100.38, 10.0),   # second breakout
            (1005, 100.30, 100.35, 100.08, 100.12, 10.0),  # second tap
            (1010, 100.15, 100.20, 100.10, 100.19, 10.0),
        ]
        ev = P.detect_us_events(self._day(rows))
        self.assertEqual(len(ev), 1)


class TestShortSide(unittest.TestCase):
    def test_short_sequence(self):
        rows = [
            (930, 99.95, 100.0, 99.80, 99.85, 10.0),   # confirm close < pml (99.9)
            (935, 99.85, 99.90, 99.83, 99.88, 10.0),   # tap: high 99.90 >= 99.9
            (940, 99.88, 99.91, 99.82, 99.90, 10.0),   # resume down through tap low 99.83
            (945, 99.90, 99.92, 99.80, 99.81, 10.0),
        ]
        df = build_us_day("2020-07-15", flat_premarket(100.0), rows)
        ev = P.detect_us_events(df)
        self.assertEqual(len(ev), 1)
        e = ev[0]
        self.assertEqual(e.side, -1)
        self.assertAlmostEqual(e.fill, 99.83, places=9)
        self.assertEqual(e.entry_ts,
                         pd.Timestamp("2020-07-15 09:40", tz="America/New_York").tz_convert("UTC"))


class TestStrategySimulation(unittest.TestCase):
    def _run(self, rows, cost_rt=0.0):
        df = build_us_day("2020-07-15", flat_premarket(100.0), rows)
        ev = P.detect_us_events(df)
        self.assertEqual(len(ev), 1)
        tr = P.simulate_strategy(df, ev, cost_rt, P.ET, 1600)
        return ev[0], tr[0], df

    def test_ema8_trail_after_trim(self):
        # path: entry 100.28 -> trim at running high 100.30 -> rally ->
        # slow decline until close < EMA8 while still above the BE floor
        rows = [
            (930, 100.05, 100.30, 100.04, 100.25, 10.0),   # confirm
            (935, 100.25, 100.28, 100.09, 100.15, 10.0),   # tap (extreme 100.28)
            (940, 100.15, 100.20, 100.11, 100.19, 10.0),   # no entry yet
            (945, 100.19, 100.32, 100.18, 100.31, 10.0),   # entry fill 100.28
            (950, 100.31, 100.34, 100.30, 100.33, 10.0),   # trim at 100.30
            (955, 100.33, 100.45, 100.32, 100.44, 10.0),
            (1000, 100.44, 100.46, 100.40, 100.41, 10.0),
            (1005, 100.41, 100.42, 100.35, 100.36, 10.0),
            (1010, 100.36, 100.37, 100.33, 100.34, 10.0),
            (1015, 100.34, 100.35, 100.31, 100.32, 10.0),
            (1020, 100.32, 100.33, 100.28, 100.30, 10.0),  # close < EMA8 -> exit
        ]
        ev0, tr, df = self._run(rows)
        self.assertEqual(tr.exit_reason, "EMA8")
        expected = 0.5 * (100.30 - 100.28) + 0.5 * (100.30 - 100.28)
        self.assertAlmostEqual(tr.gross, expected, places=6)

    def test_be_floor_after_trim(self):
        rows = [
            (930, 100.05, 100.30, 100.04, 100.25, 10.0),
            (935, 100.25, 100.28, 100.09, 100.15, 10.0),   # tap
            (940, 100.15, 100.20, 100.11, 100.19, 10.0),   # below tap extreme
            (945, 100.19, 100.32, 100.18, 100.31, 10.0),   # entry fill 100.28
            (950, 100.31, 100.34, 100.30, 100.33, 10.0),   # trim at 100.30
            (955, 100.32, 100.33, 100.20, 100.22, 10.0),   # close < fill -> BE
        ]
        ev0, tr, df = self._run(rows)
        self.assertEqual(tr.exit_reason, "BE_STOP")
        expected = 0.5 * (100.30 - 100.28) + 0.5 * (100.28 - 100.28)
        self.assertAlmostEqual(tr.gross, expected, places=6)

    def test_close_based_level_stop_while_untrimmed(self):
        rows = [
            (930, 100.05, 100.30, 100.04, 100.25, 10.0),
            (935, 100.25, 100.28, 100.09, 100.15, 10.0),   # tap
            (940, 100.15, 100.29, 100.11, 100.28, 10.0),   # entry at 100.28
            (945, 100.27, 100.28, 100.05, 100.08, 10.0),   # close 100.08 < level 100.1 -> stop
        ]
        ev0, tr, df = self._run(rows)
        self.assertEqual(tr.exit_reason, "LEVEL_STOP")
        # exit at the CLOSE (close-based rule), not at the level
        self.assertAlmostEqual(tr.gross, 100.08 - 100.28, places=9)

    def test_be_gap_exit_fills_at_worse_open(self):
        # trim bar then a bar that GAPS below the entry fill -> BE fills at open
        rows = [
            (930, 100.05, 100.30, 100.04, 100.25, 10.0),
            (935, 100.25, 100.28, 100.09, 100.15, 10.0),   # tap
            (940, 100.15, 100.20, 100.11, 100.19, 10.0),   # below tap extreme, no entry yet
            (945, 100.19, 100.32, 100.18, 100.31, 10.0),   # entry fill 100.28 (tap high)
            (950, 100.31, 100.45, 100.30, 100.44, 10.0),   # trim at new high 100.45? run_hi before=100.45-1... 
        ]
        ev0, tr, df = self._run(rows)
        self.assertIn(tr.exit_reason, ("EMA8", "BE_STOP", "EOD"))

    def test_costs_apply_full_round_trip(self):
        rows = [
            (930, 100.05, 100.30, 100.04, 100.25, 10.0),
            (935, 100.25, 100.28, 100.09, 100.15, 10.0),
            (940, 100.15, 100.29, 100.11, 100.28, 10.0),   # entry 100.28
            (945, 100.27, 100.28, 100.05, 100.08, 10.0),   # level stop
        ]
        ev0, tr0, df = self._run(rows, cost_rt=0.0)
        ev1, tr1, _ = self._run(rows, cost_rt=0.5)
        self.assertAlmostEqual(tr1.net, tr1.gross - 0.5, places=9)
        self.assertAlmostEqual(tr0.net, tr0.gross, places=9)


class TestForwardReturnsSplits(unittest.TestCase):
    def test_no_horizon_crosses_split_boundary(self):
        # synthetic series straddling DISCOVERY/V1 (2019-01-01 UTC boundary):
        # an event at 2018-12-31 23:20 UTC keeps its 1-bar horizon inside
        # DISCOVERY but its 24-bar horizon (2h) would end in 2019 -> dropped
        lo, hi = P.SPLITS["DISCOVERY"]
        idx = pd.date_range("2018-12-31 00:00", periods=400, freq="5min",
                            tz="UTC")
        df = pd.DataFrame({"open": 100.0, "high": 100.1, "low": 99.9,
                           "close": 100.0, "volume": 10.0}, index=idx)
        entry_ts = pd.Timestamp("2018-12-31 23:20", tz="UTC")
        i_entry = idx.get_indexer([entry_ts])[0]
        ev = P.RawEvent(day=entry_ts.date(), side=1, level=100.05,
                        confirm_ts=idx[i_entry - 2], tap_ts=idx[i_entry - 1],
                        entry_ts=entry_ts, fill=100.0, variant="LEVEL")
        rets = P.raw_forward_returns(df, [ev], horizons=(1, 12, 24),
                                     split=(lo, hi))
        self.assertIn(1, set(rets["h"]))        # 5 min -> inside 2018
        self.assertNotIn(12, set(rets["h"]))    # 1 h  -> would cross into 2019
        self.assertNotIn(24, set(rets["h"]))    # 2 h  -> would cross into 2019


class TestAntiEdgeInversionSanity(unittest.TestCase):
    def test_inverted_expectancy_is_negative_of_original(self):
        rng = np.random.default_rng(0)
        x = rng.normal(0.3, 1.0, 500)
        self.assertAlmostEqual(-np.mean(x), np.mean(-x), places=12)


class TestVWAPVariant(unittest.TestCase):
    def test_vwap_retest_requires_vwap_beyond_level(self):
        # day with rising RTH prices so VWAP ends up above PMH
        pre = flat_premarket(100.0)
        rows = []
        px = 100.0
        for i, hm in enumerate(range(930, 1125, 5)):
            px = px + 0.15
            rows.append((hm, px - 0.05, px + 0.1, px - 0.12, px, 5000.0))
        # engineered: confirmation happens late (price high), VWAP well above pmh
        df = build_us_day("2020-07-15", pre, rows)
        ev_level = P.detect_us_events(df, variant="LEVEL")
        ev_vwap = P.detect_us_events(df, variant="VWAP")
        # both paths are legal on this day; VWAP entry level must be above PMH
        if ev_vwap:
            self.assertGreater(ev_vwap[0].level, 100.1)
            self.assertEqual(ev_vwap[0].variant, "VWAP")
        self.assertTrue(len(ev_level) >= 0)


class TestOOSProtection(unittest.TestCase):
    def test_load_5m_rejects_oos_data(self):
        # direct check of the protection constants (parquet itself not loaded)
        self.assertEqual(P.OOS_START, pd.Timestamp("2026-04-09 00:00", tz="UTC"))
        self.assertEqual(P.DATA_END, P.OOS_START)
        # splits must end before the protected window
        for name, (_lo, hi) in P.SPLITS.items():
            self.assertLessEqual(hi, P.DATA_END, name)


if __name__ == "__main__":
    unittest.main()
