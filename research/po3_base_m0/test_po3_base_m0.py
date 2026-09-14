"""PO3-BASE-M0 synthetic tests. Deterministic tick arrays; no real data, no network.

Run:  python -m unittest discover -s research/po3_base_m0 -p "test_*.py" -v
Covers the frozen test list in PO3_BASE_M0_FROZEN_SPEC.md section 19.
"""
from __future__ import annotations

import unittest
from datetime import date, datetime, timezone

import numpy as np

import po3_base_m0_lib as L

DAY_BST = date(2015, 6, 15)   # BST: London 00:00 == 2015-06-14 23:00 UTC
DAY_GMT = date(2015, 1, 15)   # GMT: London 00:00 == 2015-01-15 00:00 UTC
SPREAD = 0.00004              # 0.4 pip bid/ask spread around mid

A_MID = 1.1000
B_MID = 1.1004                # Asian range 4 pips: [1.1000, 1.1004]
UPPER_THR = B_MID + L.SWEEP_FRAC * 0.0004   # 1.1012
LOWER_THR = A_MID - L.SWEEP_FRAC * 0.0004   # 1.0992


def ln_ns(d: date, h: int, m: int = 0, s: float = 0.0) -> int:
    dt = datetime(d.year, d.month, d.day, h, m, tzinfo=L.LONDON)
    return int(dt.timestamp()) * 1_000_000_000 + int(s * 1e9)


def build_day(d: date, asia_step_s: float = 6.0, events=None,
              asia_a: float = A_MID, asia_b: float = B_MID):
    """Asian session filled with alternating ticks (eligible by default).

    events: list of (london_ns, mid) appended to the London window (sorted after).
    Returns ts, bid, ask, mid arrays.
    """
    ts = []
    mids = []
    t0 = ln_ns(d, 0, 0)
    t1 = ln_ns(d, 7, 0)
    step = int(asia_step_s * 1e9)
    i = 0
    t = t0
    while t < t1:
        ts.append(t)
        mids.append(asia_a if i % 2 == 0 else asia_b)
        i += 1
        t += step
    for t_ev, m_ev in (events or []):
        ts.append(t_ev)
        mids.append(m_ev)
    ts_a = np.array(ts, dtype=np.int64)
    mid_a = np.array(mids, dtype=np.float64)
    order = np.argsort(ts_a, kind="stable")
    ts_a, mid_a = ts_a[order], mid_a[order]
    bid_a = mid_a - SPREAD / 2
    ask_a = mid_a + SPREAD / 2
    return ts_a, bid_a, ask_a, mid_a


def rng_of(ts, bid, ask, d: date) -> L.AsianRange:
    return L.asian_range(ts, (bid + ask) / 2, L.day_bounds(d))


# ---------------------------------------------------------------------------
# Timezone / guards
# ---------------------------------------------------------------------------

class TestTimezones(unittest.TestCase):
    def test_dst_bst_vs_gmt(self):
        b_bst = L.day_bounds(DAY_BST)
        b_gmt = L.day_bounds(DAY_GMT)
        self.assertEqual(b_bst.asia_start, ln_ns(DAY_BST, 0, 0))
        self.assertEqual(b_bst.asia_start,
                         int(datetime(2015, 6, 14, 23, 0,
                                      tzinfo=timezone.utc).timestamp()) * 10**9)
        self.assertEqual(b_gmt.asia_start,
                         int(datetime(2015, 1, 15, 0, 0,
                                      tzinfo=timezone.utc).timestamp()) * 10**9)
        self.assertNotEqual(b_bst.asia_start % 86400 * 10**9 // 10**9, 0)

    def test_no_hardcoded_offset_across_history(self):
        # Same wall-clock midnight maps to different UTC offsets in 2010 vs 2015 BST.
        b10 = L.day_bounds(date(2010, 6, 15))
        b15 = L.day_bounds(date(2015, 6, 15))
        off10 = b10.asia_start - int(datetime(2010, 6, 15, 0, 0,
                                              tzinfo=L.LONDON).timestamp()) * 10**9
        off15 = b15.asia_start - int(datetime(2015, 6, 15, 0, 0,
                                              tzinfo=L.LONDON).timestamp()) * 10**9
        self.assertEqual(off10, off15)  # both resolve via the same tz database
        self.assertEqual(off15, 0)      # timestamp() already encodes the offset

    def test_2019_cutoff(self):
        with self.assertRaises(L.OutOfWindowError):
            L.day_bounds(date(2019, 1, 1))
        with self.assertRaises(L.OutOfWindowError):
            L.assert_utc_range(L.UTC_GUARD_START_NS, L.UTC_GUARD_END_NS + 1)
        with self.assertRaises(L.OutOfWindowError):
            L.guard_partition_path("store/year=2019/month=01/ticks.parquet")
        self.assertEqual(L.guard_partition_path("x/year=2018/month=12/t.parquet"),
                         (2018, 12))

    def test_discovery_dates_weekdays(self):
        ds = L.discovery_dates()
        self.assertEqual(ds[0], date(2010, 1, 4))
        self.assertEqual(ds[-1], date(2018, 12, 31))
        self.assertTrue(all(d.weekday() < 5 for d in ds))


# ---------------------------------------------------------------------------
# Asian range + eligibility
# ---------------------------------------------------------------------------

class TestAsianRange(unittest.TestCase):
    def test_boundaries_0000_inclusive_0700_exclusive(self):
        d = DAY_GMT
        ts, bid, ask, mid = build_day(d, events=[
            (ln_ns(d, 0, 0, 0.000000001), 1.0900),   # first Asia tick -> low
            (ln_ns(d, 6, 59, 59.9), 1.1050),         # still Asia -> high
            (ln_ns(d, 7, 0, 0.0), 1.5000),           # NOT in Asia
            (ln_ns(d, 9, 0, 0.0), 0.5000),           # NOT in Asia
        ])
        r = rng_of(ts, bid, ask, d)
        self.assertEqual(r.low, 1.0900)
        self.assertEqual(r.high, 1.1050)

    def test_eligibility_gap_and_count_and_zero_range(self):
        d = DAY_GMT
        r = rng_of(*build_day(d)[:3], d)  # default alternating: eligible
        self.assertTrue(r.eligible)
        # gap > 300 s
        ts, bid, ask, mid = build_day(d, asia_step_s=400.0)
        self.assertFalse(L.asian_range(ts, mid, L.day_bounds(d)).eligible)
        # fewer than 3600 ticks
        ts, bid, ask, mid = build_day(d, asia_step_s=60.0)
        self.assertFalse(L.asian_range(ts, mid, L.day_bounds(d)).eligible)
        # zero range
        ts, bid, ask, mid = build_day(d, asia_a=1.1000, asia_b=1.1000)
        self.assertFalse(L.asian_range(ts, mid, L.day_bounds(d)).eligible)


# ---------------------------------------------------------------------------
# Sweep detection
# ---------------------------------------------------------------------------

class TestSweep(unittest.TestCase):
    def test_0700_inclusive(self):
        d = DAY_GMT
        ts, bid, ask, mid = build_day(d, events=[(ln_ns(d, 7, 0, 0.0), UPPER_THR)])
        s = L.detect_setup(ts, mid, L.day_bounds(d), rng_of(ts, bid, ask, d))
        self.assertEqual(s.side, 1)
        self.assertEqual(s.sweep_ts, ln_ns(d, 7, 0, 0.0))

    def test_1000_exclusive(self):
        d = DAY_GMT
        ts, bid, ask, mid = build_day(d, events=[(ln_ns(d, 10, 0, 0.0), UPPER_THR + 0.001)])
        s = L.detect_setup(ts, mid, L.day_bounds(d), rng_of(ts, bid, ask, d))
        self.assertEqual(s.status, L.NO_SWEEP)
        ts, bid, ask, mid = build_day(d, events=[(ln_ns(d, 9, 59, 59.9), UPPER_THR)])
        s = L.detect_setup(ts, mid, L.day_bounds(d), rng_of(ts, bid, ask, d))
        self.assertEqual(s.side, 1)

    def test_upper_threshold_exact_ge(self):
        d = DAY_GMT
        # just below threshold: no sweep; exactly at: sweep
        ts, bid, ask, mid = build_day(d, events=[(ln_ns(d, 8, 0, 0.0), UPPER_THR - 1e-9)])
        s = L.detect_setup(ts, mid, L.day_bounds(d), rng_of(ts, bid, ask, d))
        self.assertEqual(s.status, L.NO_SWEEP)
        ts, bid, ask, mid = build_day(d, events=[(ln_ns(d, 8, 0, 0.0), UPPER_THR)])
        s = L.detect_setup(ts, mid, L.day_bounds(d), rng_of(ts, bid, ask, d))
        self.assertEqual(s.side, 1)

    def test_lower_threshold_exact_le(self):
        d = DAY_GMT
        ts, bid, ask, mid = build_day(d, events=[(ln_ns(d, 8, 0, 0.0), LOWER_THR)])
        s = L.detect_setup(ts, mid, L.day_bounds(d), rng_of(ts, bid, ask, d))
        self.assertEqual(s.side, -1)
        ts, bid, ask, mid = build_day(d, events=[(ln_ns(d, 8, 0, 0.0), LOWER_THR + 1e-9)])
        s = L.detect_setup(ts, mid, L.day_bounds(d), rng_of(ts, bid, ask, d))
        self.assertEqual(s.status, L.NO_SWEEP)

    def test_first_crossing_wins(self):
        d = DAY_GMT
        ts, bid, ask, mid = build_day(d, events=[
            (ln_ns(d, 8, 0, 0.0), UPPER_THR),
            (ln_ns(d, 8, 30, 0.0), LOWER_THR),
        ])
        s = L.detect_setup(ts, mid, L.day_bounds(d), rng_of(ts, bid, ask, d))
        self.assertEqual(s.side, 1)
        self.assertEqual(s.sweep_ts, ln_ns(d, 8, 0, 0.0))


# ---------------------------------------------------------------------------
# Reintegration
# ---------------------------------------------------------------------------

class TestReintegration(unittest.TestCase):
    def base_upper(self, d):
        """Upper sweep exactly 07:10:00 at threshold; returns builder closure."""
        return d

    def test_15min_boundary_inclusive(self):
        d = DAY_GMT
        sweep = ln_ns(d, 7, 10, 0.0)
        close_t = sweep + L.REINTEGRATION_LIMIT_NS - 1  # candle ends exactly at +900s
        ts, bid, ask, mid = build_day(d, events=[
            (sweep, UPPER_THR),
            (close_t, 1.1002),  # close inside
        ])
        s = L.detect_setup(ts, mid, L.day_bounds(d), rng_of(ts, bid, ask, d))
        self.assertEqual(s.status, L.TRADE)
        self.assertEqual(s.decision_ts, sweep + L.REINTEGRATION_LIMIT_NS)

    def test_15min_boundary_miss(self):
        d = DAY_GMT
        sweep = ln_ns(d, 7, 10, 0.0)
        ts, bid, ask, mid = build_day(d, events=[
            (sweep, UPPER_THR),
            (sweep + L.REINTEGRATION_LIMIT_NS + 61 * 10**9, 1.1002),  # too late
        ])
        s = L.detect_setup(ts, mid, L.day_bounds(d), rng_of(ts, bid, ask, d))
        self.assertEqual(s.status, L.NO_REINTEGRATION)

    def test_m1_causality_bucket_end_close_and_same_instant_tick(self):
        d = DAY_GMT
        sweep = ln_ns(d, 7, 10, 0.0)
        # Bucket [07:10,07:11) closes inside via tick at 07:10:30 -> decision 07:11:00.
        # A tick AT 07:11:00 belongs to the NEXT bucket and must not pre-empt it.
        ts, bid, ask, mid = build_day(d, events=[
            (sweep, UPPER_THR),
            (ln_ns(d, 7, 10, 30.0), 1.1002),
            (ln_ns(d, 7, 11, 0.0), LOWER_THR),  # opposite side at decision instant
        ])
        s = L.detect_setup(ts, mid, L.day_bounds(d), rng_of(ts, bid, ask, d))
        self.assertEqual(s.status, L.TRADE)
        self.assertEqual(s.decision_ts, ln_ns(d, 7, 11, 0.0))

    def test_sweep_candle_own_close_qualifies(self):
        d = DAY_GMT
        sweep = ln_ns(d, 7, 10, 30.0)
        ts, bid, ask, mid = build_day(d, events=[
            (sweep, UPPER_THR),
            (ln_ns(d, 7, 10, 50.0), 1.1002),  # same-bucket close inside
        ])
        s = L.detect_setup(ts, mid, L.day_bounds(d), rng_of(ts, bid, ask, d))
        self.assertEqual(s.status, L.TRADE)
        self.assertEqual(s.decision_ts, ln_ns(d, 7, 11, 0.0))

    def test_double_sweep_invalid(self):
        d = DAY_GMT
        sweep = ln_ns(d, 7, 10, 0.0)
        ts, bid, ask, mid = build_day(d, events=[
            (sweep, UPPER_THR),
            (ln_ns(d, 7, 14, 0.0), LOWER_THR),   # opposite side before reintegration
            (ln_ns(d, 7, 16, 0.0), 1.1002),
        ])
        s = L.detect_setup(ts, mid, L.day_bounds(d), rng_of(ts, bid, ask, d))
        self.assertEqual(s.status, L.DOUBLE_SWEEP_INVALID)

    def test_close_must_be_strictly_inside(self):
        d = DAY_GMT
        sweep = ln_ns(d, 7, 10, 0.0)
        ts, bid, ask, mid = build_day(d, events=[
            (sweep, UPPER_THR),
            (ln_ns(d, 7, 10, 30.0), B_MID),  # close == AsianHigh: NOT inside
        ])
        s = L.detect_setup(ts, mid, L.day_bounds(d), rng_of(ts, bid, ask, d))
        self.assertEqual(s.status, L.NO_REINTEGRATION)

    def test_no_future_extreme_in_stop(self):
        d = DAY_GMT
        sweep = ln_ns(d, 7, 10, 0.0)
        ts, bid, ask, mid = build_day(d, events=[
            (sweep, UPPER_THR),
            (ln_ns(d, 7, 12, 0.0), 1.1100),              # same-side extreme, pre-decision
            (ln_ns(d, 7, 12, 30.0), 1.1002),             # inside close -> decision 07:13
            (ln_ns(d, 7, 13, 5.0), 1.1002),              # SHORT entry tick
            (ln_ns(d, 7, 14, 0.0), 1.2000),              # post-decision: must be ignored
            (ln_ns(d, 12, 0, 10.0), 1.1000),             # time-exit tick
        ])
        b = L.day_bounds(d)
        s = L.detect_setup(ts, mid, b, rng_of(ts, bid, ask, d))
        self.assertEqual(s.status, L.TRADE)
        self.assertEqual(s.sweep_extreme, 1.1100)
        self.assertEqual(s.decision_ts, ln_ns(d, 7, 13, 0.0))
        ex = L.execute(ts, bid, ask, -1, s.sweep_extreme, s.decision_ts,
                       L.ENTRY_DELAY_BASE_NS, b.time_exit)
        self.assertEqual(ex.status, L.TRADE)
        self.assertEqual(ex.stop, 1.1100)

# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------

def long_setup_day(d, extra):
    """Lower sweep at 07:10 -> LONG; stop = LOWER_THR. extra: [(ns, mid), ...]."""
    sweep = ln_ns(d, 7, 10, 0.0)
    events = [(sweep, LOWER_THR),
              (ln_ns(d, 7, 12, 0.0), 1.0990),       # deeper extreme pre-decision
              (ln_ns(d, 7, 12, 30.0), 1.1002),      # close inside (>1.1000) -> 07:13
              (ln_ns(d, 12, 0, 10.0), 1.1000)] + extra  # default 12:00 time-exit tick
    ts, bid, ask, mid = build_day(d, events=events)
    b = L.day_bounds(d)
    s = L.detect_setup(ts, mid, b, rng_of(ts, bid, ask, d))
    assert s.status == L.TRADE and s.side == -1, s.status
    return ts, bid, ask, mid, b, s


class TestExecution(unittest.TestCase):
    def test_long_ask_entry_5s_delay(self):
        d = DAY_GMT
        ts, bid, ask, mid, b, s = long_setup_day(d, extra=[
            (ln_ns(d, 7, 13, 4.0), 1.1000),   # decision+4s: too early
            (ln_ns(d, 7, 13, 5.0), 1.1000),   # decision+5s: entry tick
        ])
        ex = L.execute(ts, bid, ask, 1, s.sweep_extreme, s.decision_ts,
                       L.ENTRY_DELAY_BASE_NS, b.time_exit)
        self.assertEqual(ex.status, L.TRADE)
        self.assertEqual(ex.entry_ts, ln_ns(d, 7, 13, 5.0))
        self.assertAlmostEqual(ex.entry_px, 1.1000 + SPREAD / 2)  # ASK
        self.assertEqual(ex.stop, 1.0990)
        self.assertAlmostEqual(ex.r, ex.entry_px - 1.0990)
        self.assertAlmostEqual(ex.target, ex.entry_px + 2 * ex.r)

    def test_short_bid_entry(self):
        d = DAY_GMT
        sweep = ln_ns(d, 7, 10, 0.0)
        ts, bid, ask, mid = build_day(d, events=[
            (sweep, UPPER_THR),
            (ln_ns(d, 7, 12, 0.0), 1.1100),
            (ln_ns(d, 7, 12, 30.0), 1.1002),
            (ln_ns(d, 7, 13, 5.0), 1.1000),
            (ln_ns(d, 12, 0, 10.0), 1.1000),
        ])
        b = L.day_bounds(d)
        s = L.detect_setup(ts, mid, b, rng_of(ts, bid, ask, d))
        ex = L.execute(ts, bid, ask, -1, s.sweep_extreme, s.decision_ts,
                       L.ENTRY_DELAY_BASE_NS, b.time_exit)
        self.assertEqual(ex.status, L.TRADE)
        self.assertAlmostEqual(ex.entry_px, 1.1000 - SPREAD / 2)  # BID
        self.assertEqual(ex.stop, 1.1100)

    def test_no_fill_bound_30s(self):
        d = DAY_GMT
        ts, bid, ask, mid, b, s = long_setup_day(d, extra=[
            (ln_ns(d, 7, 13, 35.5), 1.1000),  # decision+5s+30.5s: outside bound
        ])
        ex = L.execute(ts, bid, ask, 1, s.sweep_extreme, s.decision_ts,
                       L.ENTRY_DELAY_BASE_NS, b.time_exit)
        self.assertEqual(ex.status, L.NO_FILL)
        # within bound: fills
        ts, bid, ask, mid, b, s = long_setup_day(d, extra=[
            (ln_ns(d, 7, 13, 35.0), 1.1000),
        ])
        ex = L.execute(ts, bid, ask, 1, s.sweep_extreme, s.decision_ts,
                       L.ENTRY_DELAY_BASE_NS, b.time_exit)
        self.assertEqual(ex.status, L.TRADE)

    def test_latency_30s_scenario(self):
        d = DAY_GMT
        ts, bid, ask, mid, b, s = long_setup_day(d, extra=[
            (ln_ns(d, 7, 13, 20.0), 1.1004),  # +20s: used by base only
            (ln_ns(d, 7, 13, 35.0), 1.1008),  # +35s: used by latency only
        ])
        ex5 = L.execute(ts, bid, ask, 1, s.sweep_extreme, s.decision_ts,
                        L.ENTRY_DELAY_BASE_NS, b.time_exit)
        ex30 = L.execute(ts, bid, ask, 1, s.sweep_extreme, s.decision_ts,
                         L.ENTRY_DELAY_STRESS_NS, b.time_exit)
        self.assertEqual(ex5.entry_ts, ln_ns(d, 7, 13, 20.0))
        self.assertEqual(ex30.entry_ts, ln_ns(d, 7, 13, 35.0))
        self.assertGreater(ex30.entry_px, ex5.entry_px)
        self.assertGreater(ex30.r, ex5.r)  # R re-derived from latency entry
        self.assertEqual(ex30.stop, ex5.stop)

    def test_stop_side_and_gap(self):
        d = DAY_GMT
        ts, bid, ask, mid, b, s = long_setup_day(d, extra=[
            (ln_ns(d, 7, 13, 5.0), 1.1000),   # entry tick (ask 1.10002)
            (ln_ns(d, 7, 20, 0.0), 1.0950),   # gap through stop -> worse bid fill
        ])
        ex = L.execute(ts, bid, ask, 1, s.sweep_extreme, s.decision_ts,
                       L.ENTRY_DELAY_BASE_NS, b.time_exit)
        self.assertEqual(ex.exit_type, "STOP")
        self.assertEqual(ex.exit_ts, ln_ns(d, 7, 20, 0.0))
        self.assertAlmostEqual(ex.exit_px, 1.0950 - SPREAD / 2)  # BID (executed side)
        self.assertGreater(ex.stop_gap_pips, 0.0)

    def test_target_cap(self):
        d = DAY_GMT
        ts, bid, ask, mid, b, s = long_setup_day(d, extra=[
            (ln_ns(d, 7, 13, 5.0), 1.1000),
            (ln_ns(d, 7, 25, 0.0), 1.1100),   # far beyond target -> capped
        ])
        ex = L.execute(ts, bid, ask, 1, s.sweep_extreme, s.decision_ts,
                       L.ENTRY_DELAY_BASE_NS, b.time_exit)
        self.assertEqual(ex.exit_type, "TARGET")
        self.assertAlmostEqual(ex.exit_px, ex.target)

    def test_invalid_risk(self):
        d = DAY_GMT
        ts, bid, ask, mid, b, s = long_setup_day(d, extra=[
            (ln_ns(d, 7, 13, 5.0), 1.0980),   # ask 1.09802 < stop 1.0990
        ])
        ex = L.execute(ts, bid, ask, 1, s.sweep_extreme, s.decision_ts,
                       L.ENTRY_DELAY_BASE_NS, b.time_exit)
        self.assertEqual(ex.status, L.INVALID_RISK)

    def test_time_exit_1200(self):
        d = DAY_GMT
        ts, bid, ask, mid, b, s = long_setup_day(d, extra=[
            (ln_ns(d, 7, 13, 5.0), 1.1000),
            (ln_ns(d, 11, 0, 0.0), 1.1001),
        ])
        ex = L.execute(ts, bid, ask, 1, s.sweep_extreme, s.decision_ts,
                       L.ENTRY_DELAY_BASE_NS, b.time_exit)
        self.assertEqual(ex.exit_type, "TIME")
        self.assertEqual(ex.exit_ts, ln_ns(d, 12, 0, 10.0))
        self.assertAlmostEqual(ex.exit_px, 1.1000 - SPREAD / 2)  # LONG exits on BID

    def test_no_time_exit_data(self):
        d = DAY_GMT
        sweep = ln_ns(d, 7, 10, 0.0)
        ts, bid, ask, mid = build_day(d, events=[
            (sweep, LOWER_THR),
            (ln_ns(d, 7, 12, 0.0), 1.0990),
            (ln_ns(d, 7, 12, 30.0), 1.1002),
            (ln_ns(d, 7, 13, 5.0), 1.1000),
            (ln_ns(d, 11, 0, 0.0), 1.1001),   # nothing at/after 12:00
        ])
        b = L.day_bounds(d)
        s = L.detect_setup(ts, mid, b, rng_of(ts, bid, ask, d))
        ex = L.execute(ts, bid, ask, 1, s.sweep_extreme, s.decision_ts,
                       L.ENTRY_DELAY_BASE_NS, b.time_exit)
        self.assertEqual(ex.status, L.NO_TIME_EXIT_DATA)


# ---------------------------------------------------------------------------
# Metrics + scenario math
# ---------------------------------------------------------------------------

class TestMetrics(unittest.TestCase):
    def test_profit_factor_and_sentinel(self):
        nets = np.array([1.0, 2.0, -1.0, -0.5, 0.5])
        self.assertAlmostEqual(L.profit_factor(nets), 3.5 / 1.5)
        self.assertEqual(L.profit_factor(np.array([1.0, 2.0])), L.PF_CAP)

    def test_remove_best_1pct(self):
        vals = np.concatenate([np.zeros(247), np.array([10.0, 20.0, 30.0])])  # n=250
        # k = ceil(2.5) = 3 -> remove 30,20,10 -> mean 0
        self.assertAlmostEqual(L.remove_best_1pct_mean(vals), 0.0)
        self.assertAlmostEqual(L.remove_best_1pct_mean(np.array([5.0, 1.0])),
                               1.0)  # k=1

    def test_bootstrap_deterministic(self):
        v = np.array([0.1, -0.2, 0.3, 0.05, -0.05] * 20)
        a = L.bootstrap_ci95_mean(v)
        b = L.bootstrap_ci95_mean(v)
        self.assertEqual(a, b)
        self.assertLess(a[0], a[1])
        c = L.bootstrap_ci95_mean(v, seed=7)
        self.assertNotEqual(a, c)

    def test_drawdown_and_streaks_and_years(self):
        self.assertAlmostEqual(L.max_drawdown_r(np.array([1, 1, -1, 1])), 1.0)
        self.assertAlmostEqual(L.max_drawdown_r(np.array([-1, -1])), 2.0)
        self.assertEqual(L.max_consecutive_losses(np.array([-1, -1, 1, -1, 1, -1])), 2)
        ts = np.array([int(datetime(2014, 6, 1, tzinfo=timezone.utc).timestamp()) * 10**9,
                       int(datetime(2015, 6, 1, tzinfo=timezone.utc).timestamp()) * 10**9])
        nets = np.array([1.0, -0.5])
        self.assertEqual(L.positive_years(ts, nets), (1, 2))

    def test_slippage_formula(self):
        # SLIPPAGE_050 removes 1.0 pip from net; REALISTIC removes 1.0 pip from latency net.
        net, r = 4.0, 5.0
        self.assertAlmostEqual((net - 2 * L.SLIP_PER_SIDE_PIPS) / r, 3.0 / 5.0)

    def test_r_mult_units_clean_target_is_plus_2R(self):
        # Regression: r_mult is net_pips / r_pips. A capped target win == exactly +2R.
        d = DAY_GMT
        ts, bid, ask, mid, b, s = long_setup_day(d, extra=[
            (ln_ns(d, 7, 13, 5.0), 1.1000),
            (ln_ns(d, 7, 25, 0.0), 1.1100),
        ])
        ex = L.execute(ts, bid, ask, 1, s.sweep_extreme, s.decision_ts,
                       L.ENTRY_DELAY_BASE_NS, b.time_exit)
        r_mult = ex.net_pips / (ex.r / L.PIP)
        self.assertAlmostEqual(r_mult, 2.0, places=9)
        # A stop exit at exactly the stop level would be -1R; gap-through is < -1R.
        self.assertLess(ex.stop_gap_pips, 1e-9)


# ---------------------------------------------------------------------------
# End-to-end synthetic day
# ---------------------------------------------------------------------------

class TestEndToEnd(unittest.TestCase):
    def test_full_long_trade(self):
        d = DAY_GMT
        ts, bid, ask, mid, b, s = long_setup_day(d, extra=[
            (ln_ns(d, 7, 13, 5.0), 1.1000),   # entry ask = 1.10002
            (ln_ns(d, 8, 0, 0.0), 1.0995),    # adverse but above stop
            (ln_ns(d, 8, 30, 0.0), 1.1030),   # beyond target -> TARGET cap
        ])
        ex = L.execute(ts, bid, ask, 1, s.sweep_extreme, s.decision_ts,
                       L.ENTRY_DELAY_BASE_NS, b.time_exit)
        self.assertEqual(ex.status, L.TRADE)
        r = ex.entry_px - ex.stop
        self.assertAlmostEqual(ex.net_pips, 2 * r / L.PIP)
        mfe = L.mfe_r(ts, bid, ask, ex, 1, 120.0)
        self.assertGreaterEqual(mfe, 2.0)
        self.assertTrue(L.reaches_kr_before_stop(ts, bid, ask, ex, 1, 1.0))
        self.assertTrue(L.reaches_kr_before_stop(ts, bid, ask, ex, 1, 2.0))

    def test_entry_tick_self_stop(self):
        d = DAY_GMT
        # Stop level 1.0990 lies between the entry tick's BID (1.09898) and ASK
        # (1.09902): valid entry, then the entry tick's own BID stops it instantly.
        ts, bid, ask, mid, b, s = long_setup_day(d, extra=[
            (ln_ns(d, 7, 13, 5.0), 1.0990),
        ])
        ex = L.execute(ts, bid, ask, 1, s.sweep_extreme, s.decision_ts,
                       L.ENTRY_DELAY_BASE_NS, b.time_exit)
        self.assertEqual(ex.exit_type, "STOP")
        self.assertEqual(ex.exit_ts, ex.entry_ts)


if __name__ == "__main__":
    unittest.main()
