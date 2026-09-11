#!/usr/bin/env python3
"""Synthetic tests for the H1/H4 research library (autonomous mission).

Covers: H1/H4 aggregation correctness, OOS window filtering, causal
execution shift, unique breakout crossing, no-lookahead under bar
mutation, forward-return signs.  All data synthetic.
"""
from __future__ import annotations

import os
import sys
import unittest
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from h1h4_lib import (aggregate, bars_to_frame, filter_window, f2_donchian,
                      forward_returns, to_executable_side)
from research_engine import Bar

T0 = datetime(2023, 1, 2, 0, 0)   # a Monday, hour 0 -> clean H4 buckets


def m15_bars(closes, start=T0):
    bars = []
    prev = closes[0]
    for k, c in enumerate(closes):
        o = prev
        bars.append(Bar(start + timedelta(minutes=15 * k), o,
                        max(o, c) + 0.0005, min(o, c) - 0.0005, c))
        prev = c
    return bars


class TestAggregation(unittest.TestCase):
    def test_h1_aggregation_ohlc(self):
        closes = [1.1000, 1.1010, 1.0990, 1.1020,  # hour 0
                  1.1020, 1.1030, 1.1010, 1.1040]  # hour 1
        df = aggregate(bars_to_frame(m15_bars(closes)), "1h")
        self.assertEqual(len(df), 2)
        r0, r1 = df.iloc[0], df.iloc[1]
        self.assertEqual(df.index[0], pd.Timestamp(T0))
        self.assertAlmostEqual(r0["open"], 1.1000)
        self.assertAlmostEqual(r0["high"], 1.1020 + 0.0005)
        self.assertAlmostEqual(r0["low"], 1.0990 - 0.0005)
        self.assertAlmostEqual(r0["close"], 1.1020)
        self.assertAlmostEqual(r1["close"], 1.1040)

    def test_h4_aggregation_buckets(self):
        closes = [1.10 + 0.0001 * k for k in range(16)]   # 4 hours of M15
        df = aggregate(bars_to_frame(m15_bars(closes)), "4h")
        self.assertEqual(len(df), 1)                       # one 4h bucket
        self.assertEqual(df.index[0], pd.Timestamp(T0))
        self.assertAlmostEqual(df.iloc[0]["close"], closes[-1])

    def test_filter_window_blocks_oos(self):
        bars = [
            Bar(datetime(2009, 12, 31, 23, 45), 1, 1, 1, 1),   # before start
            Bar(datetime(2026, 4, 8, 23, 45), 1, 1, 1, 1),     # allowed
            Bar(datetime(2026, 4, 9, 0, 0), 1, 1, 1, 1),       # OOS -> dropped
            Bar(datetime(2026, 7, 24, 0, 0), 1, 1, 1, 1),      # OOS -> dropped
        ]
        out = filter_window(bars)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].dt, datetime(2026, 4, 8, 23, 45))


class TestCausality(unittest.TestCase):
    def _bars(self, closes):
        return m15_bars(closes)

    def test_to_executable_side_shifts_by_one(self):
        side = np.array([0, 1, 0, -1, 0], dtype=np.int8)
        ex = to_executable_side(side)
        self.assertEqual(ex.tolist(), [0, 0, 1, 0, -1])

    def test_donchian_crossing_is_unique(self):
        # 60-hour flat plateau, one jump, then 12 hours of follow-through:
        # exactly ONE executable crossing event must exist.
        closes = ([1.1000] * 240 + [1.1200, 1.1205, 1.1210, 1.1215]
                  + [1.1215] * 48)
        df = aggregate(bars_to_frame(self._bars(closes)), "1h")
        side = to_executable_side(f2_donchian(df, lookback=12))
        ups = np.where(side == 1)[0]
        self.assertEqual(len(ups), 1)          # one crossing only
        # the event bar is AFTER the breakout close bar (causal execution)

    def test_no_lookahead_close_mutation(self):
        rng = np.random.default_rng(7)
        closes = 1.1000 + np.cumsum(rng.normal(0, 0.0008, 120))
        closes = list(np.round(closes, 5))
        df1 = aggregate(bars_to_frame(self._bars(list(closes))), "1h")
        side1 = to_executable_side(f2_donchian(df1, lookback=12))
        mutated = list(closes)
        mutated[90] = mutated[90] + 0.05       # absurd move on bar 90
        df2 = aggregate(bars_to_frame(self._bars(mutated)), "1h")
        side2 = to_executable_side(f2_donchian(df2, lookback=12))
        # decisions at or before the mutated bar are unchanged
        self.assertTrue((side1[:91] == side2[:91]).all())

    def test_forward_return_signs(self):
        opens = np.array([1.1000, 1.1010, 1.1020, 1.1030])
        long_side = np.array([0, 1, 0, 0], dtype=np.int8)
        short_side = np.array([0, -1, 0, 0], dtype=np.int8)
        # LONG event at index 1, horizon 1 -> open[2]-open[1] = 10 pips
        r_long = forward_returns(opens, long_side, [1], 0.0001)[1]
        r_short = forward_returns(opens, short_side, [1], 0.0001)[1]
        self.assertAlmostEqual(r_long[0], 10.0, places=6)
        self.assertAlmostEqual(r_short[0], -10.0, places=6)


if __name__ == "__main__":
    unittest.main(verbosity=2)
