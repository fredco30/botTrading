#!/usr/bin/env python3
"""Synthetic tests for the P013R V1 frozen validation (no real data access)."""
import os
import sys
import tempfile
import unittest

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import v1_lib as V  # noqa: E402


class TestV1Window(unittest.TestCase):
    def test_v1_window_bounds(self):
        self.assertEqual(V.V1_START, pd.Timestamp("2019-01-01 00:00", tz="UTC"))
        self.assertEqual(V.V1_END, pd.Timestamp("2023-01-01 00:00", tz="UTC"))

    def test_v1_daily_close_stops_at_v1_end(self):
        # direct slice semantics: nothing at/after 2023-01-01 may survive
        idx = pd.date_range("2022-12-28", periods=8, freq="D", tz="UTC")
        df = pd.DataFrame({"open": 1.0, "high": 1.0, "low": 1.0,
                           "close": np.linspace(140, 147, 8), "volume": 1.0},
                          index=idx)
        sliced = df[(df.index >= V.V1_START) & (df.index < V.V1_END)]
        self.assertLess(sliced.index[-1], V.V1_END)


class TestDecember2022Censoring(unittest.TestCase):
    def test_dec_2022_event_censored_if_exit_in_2023(self):
        # daily closes: Nov 30, Dec 29, Dec 30 (2022) and Jan 2 (2023).
        # November event: entry 11-30, exit 12-01 -> inside V1, kept.
        # December event: entry 12-30, exit would be 2023-01-02 -> CENSORED.
        idx = pd.to_datetime(["2022-11-29", "2022-11-30", "2022-12-01",
                              "2022-12-29", "2022-12-30", "2023-01-02"],
                             utc=True)
        px = pd.Series([145.0, 144.5, 145.2, 143.0, 142.5, 141.0],
                       index=idx)
        evs = V.month_end_events(px, pip=0.01)
        dates = [e["event_date"] for e in evs]
        self.assertIn(pd.Timestamp("2022-11-30").date(), dates)
        self.assertNotIn(pd.Timestamp("2022-12-30").date(), dates)
        nov = [e for e in evs
               if e["event_date"] == pd.Timestamp("2022-11-30").date()][0]
        self.assertEqual(nov["exit_date"], pd.Timestamp("2022-12-01").date())

    def test_no_exit_crosses_v1_end_in_real_helper_semantics(self):
        idx = pd.to_datetime(["2022-12-29", "2022-12-30", "2023-01-02"], utc=True)
        px = pd.Series([143.0, 142.5, 141.0], index=idx)
        evs = V.month_end_events(px, pip=0.01)
        self.assertEqual(evs, [])


class TestGateLocks(unittest.TestCase):
    def test_v2_always_locked_and_v1_authorizable(self):
        import gate as G
        G.LOG = os.path.join(tempfile.gettempdir(), "gate_audit_v1_test.log")
        with self.assertRaises(G.ValidationGateError):
            G.window("V2")
        with self.assertRaises(G.ValidationGateError):
            G.window("V1")            # locked until this mission authorizes
        try:
            G.authorize("V1", "unit-test scope only")
            lo, hi = G.window("V1")
            self.assertEqual(lo, V.V1_START)
            self.assertEqual(hi, V.V1_END)
        finally:
            G._AUTHORIZED.discard("V1")


class TestCommonTableAlignment(unittest.TestCase):
    def test_intersection_keeps_only_dates_valid_for_all_pairs(self):
        # pair B misses 2019-08-30 (data gap); pair C has an extra-only date
        ev_a = {"2019-07-31": {"event_date": pd.Timestamp("2019-07-31").date(),
                               "exit_date": pd.Timestamp("2019-08-01").date(),
                               "gross": 5.0},
                "2019-08-30": {"event_date": pd.Timestamp("2019-08-30").date(),
                               "exit_date": pd.Timestamp("2019-09-02").date(),
                               "gross": 3.0}}
        ev_b = {"2019-07-31": {"event_date": pd.Timestamp("2019-07-31").date(),
                               "exit_date": pd.Timestamp("2019-08-01").date(),
                               "gross": 4.0}}
        ev_c = {"2019-07-31": {"event_date": pd.Timestamp("2019-07-31").date(),
                               "exit_date": pd.Timestamp("2019-08-01").date(),
                               "gross": 2.0}}
        orig = V.per_pair_event_map
        V.per_pair_event_map = lambda s: {"USDJPY": ev_a, "EURJPY": ev_b,
                                          "GBPJPY": ev_c}[s]
        try:
            table = V.build_common_table()
        finally:
            V.per_pair_event_map = orig
        self.assertEqual(len(table), 1)
        self.assertEqual(str(table["event_date"][0]), "2019-07-31")
        # pooled = mean(5,4,2) = 11/3; net normal = pooled - 2
        self.assertAlmostEqual(table["POOLED_GROSS"][0], 11.0 / 3.0, places=9)
        self.assertAlmostEqual(table["POOLED_NET_NORMAL"][0],
                               11.0 / 3.0 - V.COST_NORMAL, places=9)


class TestPairedUnitIsTheEventRow(unittest.TestCase):
    def test_paired_bootstrap_rows_move_together(self):
        # each row constant across the three legs -> pooled series = the row
        # values; paired CI must equal the plain bootstrap of those values
        vals = np.array([10.0, -5.0, 3.0, 7.0, -2.0, 4.0])
        mat = np.column_stack([vals, vals, vals])
        out = V.paired_stats(mat, cost=0.0, n_boot=500, seed=42)
        rng = np.random.default_rng(42)
        direct = np.array([vals[rng.integers(0, len(vals), len(vals))].mean()
                           for _ in range(500)])
        self.assertAlmostEqual(out["gross_mean"], float(vals.mean()), delta=0.005)
        self.assertAlmostEqual(out["ci95_gross"][0],
                               float(np.percentile(direct, 2.5)), delta=0.005)
        self.assertAlmostEqual(out["ci95_gross"][1],
                               float(np.percentile(direct, 97.5)), delta=0.005)


class TestFrozenClassifier(unittest.TestCase):
    def test_frozen_verdict_branches(self):
        # REJECT: pooled net <= 0
        self.assertEqual(V.frozen_classify(-1.0, 3, 5.0, 1.0), "V1_REJECT")
        # REJECT: fewer than 2/3 pairs positive
        self.assertEqual(V.frozen_classify(5.0, 1, 5.0, 1.0), "V1_REJECT")
        # REJECT: remove-best-event <= 0
        self.assertEqual(V.frozen_classify(5.0, 3, -0.5, 1.0), "V1_REJECT")
        # WEAK: structure OK but CI low crosses zero
        self.assertEqual(V.frozen_classify(5.0, 3, 5.0, -1.0),
                         "V1_SUPPORTIVE_BUT_WEAK")
        # STRONG: everything passes
        self.assertEqual(V.frozen_classify(5.0, 3, 5.0, 0.5),
                         "V1_STRONG_CONFIRMATION")


if __name__ == "__main__":
    unittest.main()
