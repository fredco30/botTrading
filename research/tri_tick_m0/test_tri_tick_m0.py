#!/usr/bin/env python3
"""TRI-TICK-M0 synthetic tests: decode, scaling, causal sync, triangular
identity, currency-conversion sides, cycle formulas, lead/lag sign convention.

Run:  python test_tri_tick_m0.py
"""
import os
import struct
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tri_lib


def hour_start_ns(y, m, d, h):
    return tri_lib.hour_start_ns(y, m, d, h)


def enc(recs):
    """recs: list of (ms, ask_raw, bid_raw, av, bv) -> LZMA .bi5 body bytes."""
    import lzma
    out = b"".join(struct.pack(">IIIff", ms, a, b, av, bv) for (ms, a, b, av, bv) in recs)
    return lzma.compress(out, format=lzma.FORMAT_ALONE)


BASE = hour_start_ns(2018, 6, 4, 0)
SEC = tri_lib.SEC
MS = tri_lib.MS


def ticks(recs, point=1e5):
    import lzma
    buf = lzma.decompress(enc(recs), format=lzma.FORMAT_ALONE)
    t = tri_lib.decode_buf(buf, BASE, point)
    return t


class TestDecode(unittest.TestCase):
    def test_record_size_and_field_count(self):
        # 3 records -> exactly 60 decompressed bytes; decode succeeds.
        t = ticks([(500, 131000, 130990, 1.0, 2.0),
                   (1500, 131001, 130991, 1.0, 2.0),
                   (2500, 131002, 130992, 1.0, 2.0)])
        self.assertEqual(len(t["timestamp_ns"]), 3)

    def test_timestamp_from_hour_semantics(self):
        # ms offsets are relative to the HOUR start passed in.
        t = ticks([(0, 131000, 130990, 1.0, 1.0), (59_000, 131000, 130990, 1.0, 1.0)])
        self.assertEqual(t["timestamp_ns"][0], BASE)
        self.assertEqual(t["timestamp_ns"][1], BASE + 59 * SEC)

    def test_ask_gte_bid_passes(self):
        t = ticks([(0, 131_000, 130_990, 1.0, 1.0)])
        self.assertEqual(tri_lib.validate_arrays(t, BASE, 0.5, 2.5), [])

    def test_ask_lt_bid_flagged(self):
        t = ticks([(0, 130_990, 131_000, 1.0, 1.0)])
        errs = tri_lib.validate_arrays(t, BASE, 0.5, 2.5)
        self.assertTrue(any("ASK < BID" in e for e in errs))

    def test_non_monotonic_flagged(self):
        t = ticks([(2000, 131000, 130990, 1.0, 1.0),
                   (1000, 131000, 130990, 1.0, 1.0)])
        errs = tri_lib.validate_arrays(t, BASE, 0.5, 2.5)
        self.assertTrue(any("monotone" in e for e in errs))

    def test_hour_bounds_flagged(self):
        # ms offset 3_600_500 lands beyond the hour -> must be flagged
        t = ticks([(3_600_500, 131000, 130990, 1.0, 1.0)])
        errs = tri_lib.validate_arrays(t, BASE, 0.5, 2.5)
        self.assertTrue(any("hour bounds" in e for e in errs))

    def test_price_scaling_empirical(self):
        # raw 1.31000*1e5 -> 1.31 under 1e5; 131000 under 1e3 -> implausible
        t5 = ticks([(0, 131_000, 130_995, 1.0, 1.0)], point=1e5)
        import lzma
        raw5 = lzma.decompress(enc([(0, 131_000, 130_995, 1.0, 1.0)]), format=lzma.FORMAT_ALONE)
        p5, e5 = tri_lib.pick_scaling(raw5, BASE, (0.5, 2.5))
        self.assertEqual(p5, 1e5)
        self.assertEqual(e5, [])
        raw3 = lzma.decompress(enc([(0, 1310, 1305, 1.0, 1.0)]), format=lzma.FORMAT_ALONE)
        p3, e3 = tri_lib.pick_scaling(raw3, BASE, (0.5, 2.5))
        self.assertEqual(p3, 1e3)
        self.assertEqual(e3, [])

    def test_negative_volume_flagged(self):
        t = ticks([(0, 131000, 130990, -1.0, 1.0)])
        errs = tri_lib.validate_arrays(t, BASE, 0.5, 2.5)
        self.assertTrue(any("negative volume" in e for e in errs))


class TestSync(unittest.TestCase):
    def make_feed(self, ts_ms, price):
        ts = BASE + np.array(ts_ms, dtype=np.int64) * MS
        n = len(ts)
        return {"timestamp_ns": ts,
                "bid": np.full(n, price), "ask": np.full(n, price + 1e-4),
                "ask_volume": np.ones(n), "bid_volume": np.ones(n)}

    def test_causal_uses_latest_prior_quote_never_future(self):
        f = self.make_feed([0, 300, 700], 1.10)
        grid = BASE + np.array([100, 350, 900], dtype=np.int64) * MS
        idx, qts, bid, ask = tri_lib.causal_snapshot(
            f["timestamp_ns"], f["bid"], f["ask"], grid)
        self.assertEqual(list(idx), [0, 1, 2])       # 100->t0, 350->t300, 900->t700
        self.assertTrue(np.all(qts <= grid))         # strictly causal

    def test_no_prior_quote_marked(self):
        f = self.make_feed([500], 1.10)
        grid = BASE + np.array([100, 600], dtype=np.int64) * MS
        idx, qts, bid, ask = tri_lib.causal_snapshot(
            f["timestamp_ns"], f["bid"], f["ask"], grid)
        self.assertEqual(idx[0], -1)
        self.assertEqual(idx[1], 0)

    def test_quote_age(self):
        f = self.make_feed([100], 1.10)
        grid = BASE + np.array([400], dtype=np.int64) * MS
        _, qts, _, _ = tri_lib.causal_snapshot(
            f["timestamp_ns"], f["bid"], f["ask"], grid)
        self.assertEqual((grid[0] - qts[0]) / MS, 300.0)

    def test_identity_synthetic_eurusd(self):
        # EURGBP_MID * GBPUSD_MID built here == the synthetic EURUSD used as input
        eurgbp = self.make_feed([0, 100], 0.8750)
        gbpusd = self.make_feed([0, 100], 1.3120)
        grid = BASE + np.array([100], dtype=np.int64) * MS
        snap = tri_lib.build_snapshots({"EURGBP": eurgbp, "GBPUSD": gbpusd}, grid)
        synth = snap["mid_EURGBP"] * snap["mid_GBPUSD"]
        # make_feed half-spread = 5e-5, so mids sit a half-spread above the bid
        self.assertAlmostEqual(synth[0], 0.87505 * 1.31205, places=12)


class TestConversionSides(unittest.TestCase):
    """Each conversion uses the correct BID/ASK side.

    Quotes: EURUSD = USD/EUR, GBPUSD = USD/GBP, EURGBP = GBP/EUR.
    Buy base -> pay ASK; sell base -> receive BID.
    """

    def test_usd_to_eur(self):
        ask = 1.1000  # pay 1.1000 USD per EUR
        eur = 100.0 / ask
        self.assertAlmostEqual(eur, 90.90909090909091, places=8)

    def test_eur_to_usd(self):
        bid = 1.1000  # receive 1.1000 USD per EUR
        usd = 90.0 * bid
        self.assertAlmostEqual(usd, 99.0, places=8)

    def test_usd_to_gbp(self):
        ask = 1.3000  # GBPUSD ask = USD per GBP
        gbp = 100.0 / ask
        self.assertAlmostEqual(gbp, 76.92307692307692, places=8)

    def test_gbp_to_usd(self):
        bid = 1.3000
        self.assertAlmostEqual(70.0 * bid, 91.0, places=8)

    def test_gbp_to_eur(self):
        ask = 0.8750  # EURGBP ask = GBP per EUR; buying EUR pays ask
        eur = 87.5 / ask
        self.assertAlmostEqual(eur, 100.0, places=8)

    def test_eur_to_gbp(self):
        bid = 0.8750  # selling EUR for GBP receives EURGBP bid
        self.assertAlmostEqual(100.0 * bid, 87.5, places=8)

    def test_cycle_a_formula_directions(self):
        # A = BID(EURUSD) / (ASK(GBPUSD) * ASK(EURGBP))
        bid_eurusd, ask_gbpusd, ask_eurgbp = 1.1000, 1.3000, 0.8750
        usd1 = 1.0 / ask_gbpusd            # USD -> GBP (buy GBP at ask)
        eur = usd1 / ask_eurgbp            # GBP -> EUR (buy EUR at ask)
        usd2 = eur * bid_eurusd            # EUR -> USD (sell EUR at bid)
        self.assertAlmostEqual(usd2, bid_eurusd / (ask_gbpusd * ask_eurgbp),
                               places=15)

    def test_cycle_b_formula_directions(self):
        # B = BID(EURGBP) * BID(GBPUSD) / ASK(EURUSD)
        ask_eurusd, bid_eurgbp, bid_gbpusd = 1.1000, 0.8750, 1.3000
        eur = 1.0 / ask_eurusd             # USD -> EUR (buy EUR at ask)
        gbp = eur * bid_eurgbp             # EUR -> GBP (sell EUR at bid)
        usd2 = gbp * bid_gbpusd            # GBP -> USD (sell GBP at bid)
        self.assertAlmostEqual(usd2, bid_eurgbp * bid_gbpusd / ask_eurusd,
                               places=15)

    def _consistent_feeds(self, spread):
        """Triangle exactly consistent at mid=EURUSD 1.10, EURGBP 0.875,
        GBPUSD = 1.10/0.875 = 1.257142857...; per-pair half-spread `spread`."""
        m_eur, m_gbp = 0.8750, 1.10 / 0.8750
        def mk(p):
            ts = BASE + np.array([0], dtype=np.int64) * MS
            return {"timestamp_ns": ts, "bid": np.array([p - spread]),
                    "ask": np.array([p + spread]),
                    "ask_volume": np.array([1.0]), "bid_volume": np.array([1.0])}
        return {"EURUSD": mk(1.10), "EURGBP": mk(m_eur), "GBPUSD": mk(m_gbp)}

    def test_zero_spread_consistent_triangle_cycles_equal_one(self):
        grid = BASE + np.array([0], dtype=np.int64) * MS
        snap = tri_lib.build_snapshots(self._consistent_feeds(0.0), grid)
        self.assertAlmostEqual(snap["cycle_A"][0], 1.0, places=12)
        self.assertAlmostEqual(snap["cycle_B"][0], 1.0, places=12)
        self.assertAlmostEqual(snap["resid_pips"][0], 0.0, places=9)

    def test_positive_spread_consistent_triangle_cycles_le_one(self):
        grid = BASE + np.array([0], dtype=np.int64) * MS
        snap = tri_lib.build_snapshots(self._consistent_feeds(1e-4), grid)
        self.assertLessEqual(snap["cycle_A"][0], 1.0)
        self.assertLessEqual(snap["cycle_B"][0], 1.0)
        self.assertGreater(snap["cycle_A"][0], 0.99)  # realistic, not degenerate


class TestLeadLagSign(unittest.TestCase):
    def test_sign_convention(self):
        # b is a DELAYED copy of a (b[t] = a[t-2 steps]); with step=100ms,
        # corr(a[t], b[t+200ms]) must be ~1 -> lag=+200 means "a leads b".
        rng = np.random.default_rng(7)
        a = rng.normal(size=2000)
        b = np.r_[np.full(2, a[0]), a[:-2]]
        lags = [-200, 0, 200]
        res = {lag: c for lag, c, _n in tri_lib.lead_lag_corr(a, b, lags, step_ms=100)}
        self.assertGreater(res[200], 0.99)
        self.assertLess(abs(res[0]), 0.5)
        self.assertLess(abs(res[-200]), 0.5)


if __name__ == "__main__":
    unittest.main(verbosity=2)
