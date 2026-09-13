#!/usr/bin/env python3
"""MACRO-TICK-M1 synthetic validation tests (frozen spec section 20).

Pure synthetic data; never touches the Discovery tick store, no network.
Run:  python -m unittest research.macro_tick_m1_event_strategies.test_macro_tick_m1 -v
"""
import os
import sys
import tempfile
import unittest

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.normpath(os.path.join(_HERE, "..", "..")))
import macro_lib as L  # noqa: E402
import mtf_lib as MTF  # noqa: E402

NS = L.NS
PIP = L.PIP
T0 = int(pd.Timestamp("2013-06-07T12:30:00Z").value)   # Friday, NFP slot


def ns(s):
    return int(pd.Timestamp(s).value)


def ticks(spec):
    """spec: list of (offset_seconds, bid, ask) -> sorted arrays."""
    s = sorted(spec, key=lambda r: r[0])
    ts = np.array([T0 + int(round(o * NS)) for o, _b, _a in s], dtype=np.int64)
    bid = np.array([b for _o, b, _a in s], dtype=np.float64)
    ask = np.array([a for _o, _b, a in s], dtype=np.float64)
    return ts, bid, ask


def ev(t0=T0, alignment="ALIGNED", post_lag=100.0, event_id="MACRO-NFP-X",
       family="NFP"):
    return {"event_id": event_id, "family": family, "t0_ns": t0,
            "alignment": alignment, "post_lag_ms": post_lag}


def quiet_baseline(spread=0.0001, level=1.10000):
    """Ticks every 30 s through [T0-60m, T0-5m) at flat mid, 1-pip spread,
    plus the P0 tick at T0-1 s (mid = level exactly)."""
    out = []
    for k in range(110):
        t = -3600 + 30 * k + 15
        out.append((t, level - spread / 2, level + spread / 2))
    out.append((-1.0, level - spread / 2, level + spread / 2))
    return out


class BaselineTests(unittest.TestCase):
    def test_q95_computation_and_bucket_grid(self):
        # two ticks per 30 s bucket (+5 s, +25 s): bucket change = mid(+25s)
        # minus mid(+5s). Level sequence f(k) = (0,1,3,6,10)[k%5] pips, so
        # |changes| are 1,2,3,4 (x22 each) and 10 (x22) -> Q95 = 10.0 pips.
        spec = []
        steps = (0.0, 1e-4, 3e-4, 6e-4, 10e-4)
        for k in range(110):
            a = 1.10000 + steps[k % 5]
            b = 1.10000 + steps[(k + 1) % 5]
            t = -3600 + 30 * k
            spec.append((t + 5, a - 5e-5, a + 5e-5))
            spec.append((t + 25, b - 5e-5, b + 5e-5))
        spec.append((-1.0, 1.09995, 1.10005))
        ts, bid, ask = ticks(spec)
        mid = (bid + ask) / 2
        sp = (ask - bid) / PIP
        q95, med, n = L.baseline_stats(ts, mid, sp, T0)
        self.assertEqual(n, 110)
        self.assertAlmostEqual(q95, 10.0, places=9)
        self.assertAlmostEqual(med, 1.0, places=9)

    def test_baseline_uses_only_60m_to_5m_window(self):
        # huge moves INSIDE the excluded last-5-minutes must not count
        spec = quiet_baseline()
        spec.append((-120.0, 1.09000, 1.09010))          # T0-2m, 100 pips
        spec.append((-60.0, 1.09000, 1.09010))           # T0-1m
        ts, bid, ask = ticks(spec)
        mid = (bid + ask) / 2
        sp = (ask - bid) / PIP
        q95, _med, n = L.baseline_stats(ts, mid, sp, T0)
        self.assertEqual(n, 110)                          # flat buckets only
        self.assertAlmostEqual(q95, 0.0, places=9)

    def test_future_tick_cannot_change_baseline_or_shock(self):
        spec = quiet_baseline() + [(1.0, 1.10100, 1.10110),
                                   (30.0, 1.10100, 1.10110),
                                   (31.0, 1.10100, 1.10110),
                                   (40.0, 1.10300, 1.10310)]
        r1 = L.run_event_on_window(ev(), *ticks(spec))
        spec2 = spec + [(3600.0, 2.0, 2.001), (7200.0, 0.5, 0.501)]
        r2 = L.run_event_on_window(ev(), *ticks(spec2))
        self.assertAlmostEqual(r1["shock_pips"], r2["shock_pips"], places=9)
        self.assertAlmostEqual(r1["shock_score"], r2["shock_score"], places=9)
        self.assertEqual(r1["qualifying"], r2["qualifying"])
        self.assertEqual(r1["trades"][0]["net_pips"],
                         r2["trades"][0]["net_pips"])

    def test_median_spread_baseline(self):
        spec = quiet_baseline()
        for k in range(110):
            t, _b, _a = spec[k]
            spr = 0.0001 + (k % 3) * 0.0001              # 1,2,3 pip cycle
            spec[k] = (t, 1.10000 - spr / 2, 1.10000 + spr / 2)
        ts, bid, ask = ticks(spec)
        mid = (bid + ask) / 2
        sp = (ask - bid) / PIP
        _q95, med, _n = L.baseline_stats(ts, mid, sp, T0)
        self.assertAlmostEqual(med, 2.0, places=9)


class ShockTests(unittest.TestCase):
    def test_p0_last_tick_strictly_before_t0(self):
        spec = quiet_baseline() + [(0.5, 1.10500, 1.10510),   # AFTER T0
                                   (30.0, 1.10100, 1.10110)]
        ts, bid, ask = ticks(spec)
        sh = L.shock_stats(ts, (bid + ask) / 2, T0)
        self.assertEqual(sh["status"], "OK")
        self.assertAlmostEqual(sh["p0"], 1.10000, places=12)
        self.assertLess(sh["p0_ts"], T0)

    def test_p30_first_tick_at_or_after_t0_plus_30s(self):
        spec = quiet_baseline() + [(29.0, 1.10100, 1.10110),
                                   (30.0, 1.10200, 1.10210)]   # mid 1.10205
        ts, bid, ask = ticks(spec)
        sh = L.shock_stats(ts, (bid + ask) / 2, T0)
        self.assertAlmostEqual(sh["p30"], 1.10205, places=12)  # the 30s tick
        self.assertAlmostEqual(sh["shock_pips"], 20.5, places=6)

    def test_p30_missing_beyond_90s_excludes(self):
        spec = quiet_baseline() + [(95.0, 1.10100, 1.10110)]
        r = L.run_event_on_window(ev(), *ticks(spec))
        self.assertEqual(r["exclusion"], "POST_TICK_MISSING_P30")

    def test_shock_score_sign_and_magnitude(self):
        qual_hi, s_hi = L.qualifying(11.0, 5.0)
        self.assertTrue(qual_hi)
        self.assertAlmostEqual(s_hi, 2.2, places=9)
        qual_lo, s_lo = L.qualifying(-11.0, 5.0)
        self.assertTrue(qual_lo)
        self.assertAlmostEqual(s_lo, 2.2, places=9)
        qual_small, _ = L.qualifying(9.0, 5.0)
        self.assertFalse(qual_small)                 # 1.8 < 2.0
        qual_tiny, _ = L.qualifying(11.0 * 0.09, 5.0)
        self.assertFalse(qual_tiny)                  # below 1 pip floor

    def test_shock_direction_long_and_short(self):
        base = quiet_baseline()
        up = base + [(1.0, 1.10100, 1.10110), (30.0, 1.10100, 1.10110),
                     (31.0, 1.10100, 1.10110), (40.0, 1.10300, 1.10310)]
        r = L.run_event_on_window(ev(), *ticks(up))
        self.assertTrue(r["qualifying"])
        self.assertEqual(r["trades"][0]["side"], 1)
        dn = base + [(1.0, 1.09900, 1.09910), (30.0, 1.09900, 1.09910),
                     (31.0, 1.09900, 1.09910), (40.0, 1.09700, 1.09710)]
        r = L.run_event_on_window(ev(), *ticks(dn))
        self.assertTrue(r["qualifying"])
        self.assertEqual(r["trades"][0]["side"], -1)


class EventEligibilityTests(unittest.TestCase):
    def test_not_aligned_excluded(self):
        r = L.run_event_on_window(ev(alignment="NO_TICK_WITHIN_5S"),
                                  *ticks(quiet_baseline()))
        self.assertEqual(r["exclusion"], "NOT_ALIGNED")

    def test_post_tick_gt_5s_excluded_and_reported(self):
        r = L.run_event_on_window(ev(post_lag=7291.0),
                                  *ticks(quiet_baseline()))
        self.assertEqual(r["exclusion"], "POST_TICK_GT_5S")
        self.assertEqual(r["trades"], [])

    def test_baseline_or_shock_gap_excluded(self):
        spec = [(-4200.0, 1.10000, 1.10010),           # T0-70m
                (-480.0, 1.10000, 1.10010)]            # T0-8m -> 62m gap
        spec += [(1.0, 1.10100, 1.10110), (30.0, 1.10100, 1.10110)]
        r = L.run_event_on_window(ev(), *ticks(spec))
        self.assertEqual(r["exclusion"], "BASELINE_OR_SHOCK_GAP")

    def test_invalid_ticks_are_dropped(self):
        spec = quiet_baseline()
        spec.append((-0.5, 1.30000, 1.20000))          # crossed quote
        spec += [(30.0, 1.10100, 1.10110)]
        ts, bid, ask = ticks(spec)
        r = L.run_event_on_window(ev(), ts, bid, ask)
        self.assertIsNone(r["exclusion"])
        # invalid tick ignored: P0 comes from the T0-1s tick, not -0.5s
        self.assertAlmostEqual(r["p0"], 1.10000, places=12)

    def test_non_qualifying_shock_blocks_all_strategies(self):
        # 1.5 pip shock: above the 1-pip floor but score 1.5 < 2.0
        spec = quiet_baseline() + [(1.0, 1.10010, 1.10020),
                                   (30.0, 1.10010, 1.10020)]
        r = L.run_event_on_window(ev(), *ticks(spec))
        self.assertFalse(r["qualifying"])
        for k in "ABC":
            self.assertEqual(r["setups"][k]["status"], "SHOCK_NOT_QUALIFYING")


class StrategyATests(unittest.TestCase):
    def qualifying_up(self, extra):
        spec = quiet_baseline() + [(1.0, 1.10100, 1.10110),
                                   (30.0, 1.10100, 1.10110),
                                   (31.0, 1.10100, 1.10110)] + extra
        return L.run_event_on_window(ev(), *ticks(spec))

    def test_a_target_fill_uses_ask_entry_and_bid_target(self):
        r = self.qualifying_up([(40.0, 1.10300, 1.10310)])
        self.assertEqual(len(r["trades"]), 1)
        t = r["trades"][0]
        self.assertEqual(t["strategy"], "A")
        self.assertEqual(t["side"], 1)
        self.assertEqual(t["entry_ts"], T0 + 31 * NS)    # first tick >= +250ms
        self.assertAlmostEqual(t["entry"], 1.10110, places=12)  # ASK
        self.assertAlmostEqual(t["stop"], 1.10000, places=12)   # P0
        self.assertAlmostEqual(t["target"], 1.10110 + 1.5 * 0.00110,
                               places=12)                    # 1.5R
        self.assertEqual(t["exit_reason"], "TARGET")
        self.assertAlmostEqual(t["exit_price"], t["target"], places=12)
        self.assertAlmostEqual(t["net_pips"], 16.5, places=6)
        self.assertAlmostEqual(t["risk_pips"], 11.0, places=6)

    def test_a_structural_p0_stop(self):
        # bid falls back to P0 -> structural stop
        r = self.qualifying_up([(40.0, 1.09995, 1.10005)])
        t = r["trades"][0]
        self.assertEqual(t["exit_reason"], "STOP")
        self.assertAlmostEqual(t["exit_price"], 1.09995, places=12)
        self.assertAlmostEqual(t["net_pips"], -11.5, places=6)

    def test_a_stop_executes_with_overshoot_not_at_requested_stop(self):
        r = self.qualifying_up([(40.0, 1.09900, 1.09910)])
        t = r["trades"][0]
        self.assertEqual(t["exit_reason"], "STOP")
        self.assertAlmostEqual(t["exit_price"], 1.09900, places=12)
        self.assertAlmostEqual(t["net_pips"], -21.0, places=6)

    def test_a_time_exit_at_bid_after_60_minutes(self):
        drift = [(60.0 * k, 1.10115, 1.10125) for k in range(1, 66)]
        r = self.qualifying_up(drift)
        t = r["trades"][0]
        self.assertEqual(t["exit_reason"], "TIME")
        # entry at T0+31s -> time exit T0+3631s -> first drift tick at 3660s
        self.assertEqual(t["exit_ts"], T0 + 3660 * NS)
        self.assertAlmostEqual(t["exit_price"], 1.10115, places=12)

    def test_a_latency_250ms_skips_earlier_tick(self):
        spec = quiet_baseline() + [(1.0, 1.10100, 1.10110),
                                   (30.0, 1.10100, 1.10110),
                                   (30.1, 1.10100, 1.10110),   # +100ms < 250
                                   (30.3, 1.10105, 1.10115),   # +300ms
                                   (40.0, 1.10300, 1.10310)]
        r = L.run_event_on_window(ev(), *ticks(spec))
        t = r["trades"][0]
        self.assertEqual(t["entry_ts"], T0 + int(30.3 * NS))

    def test_a_short_entry_bid_exit_ask(self):
        spec = quiet_baseline() + [(1.0, 1.09900, 1.09910),
                                   (30.0, 1.09900, 1.09910),
                                   (31.0, 1.09900, 1.09910),
                                   (40.0, 1.09700, 1.09710)]
        r = L.run_event_on_window(ev(), *ticks(spec))
        t = r["trades"][0]
        self.assertEqual(t["side"], -1)
        self.assertAlmostEqual(t["entry"], 1.09900, places=12)  # BID
        self.assertAlmostEqual(t["target"], 1.09900 - 1.5 * 0.00100,
                               places=12)
        self.assertEqual(t["exit_reason"], "TARGET")
        self.assertAlmostEqual(t["exit_price"], 1.09900 - 1.5 * 0.00100,
                               places=12)
        self.assertAlmostEqual(t["net_pips"], 15.0, places=6)


class StrategyBTests(unittest.TestCase):
    def b_up(self, extra):
        # P0 1.10000 -> P30 1.10205 (+20.5 pips); level = 1.101025
        spec = quiet_baseline() + [(1.0, 1.10200, 1.10210),
                                   (30.0, 1.10200, 1.10210)] + extra
        return L.run_event_on_window(ev(), *ticks(spec))

    def test_b_50pct_retracement_trigger_and_short(self):
        r = self.b_up([(40.0, 1.10170, 1.10180),
                       (90.0, 1.10070, 1.10080),          # mid 1.10075<=level
                       (95.0, 1.10050, 1.10060),          # entry tick (BID)
                       (120.0, 1.09890, 1.09900)])        # ask <= P0: target
        t = [x for x in r["trades"] if x["strategy"] == "B"][0]
        self.assertEqual(t["side"], -1)
        self.assertEqual(t["trigger_ns"], T0 + 90 * NS)
        self.assertAlmostEqual(t["stop"], 1.10205, places=12)
        self.assertAlmostEqual(t["entry"], 1.10050, places=12)   # BID
        self.assertAlmostEqual(t["target"], 1.10000, places=12)
        self.assertEqual(t["exit_reason"], "TARGET")
        self.assertAlmostEqual(t["exit_price"], 1.10000, places=12)
        self.assertAlmostEqual(t["net_pips"], 5.0, places=6)

    def test_b_stop_is_observed_extreme_between_t0_and_trigger(self):
        r = self.b_up([(45.0, 1.10345, 1.10355),           # spike mid 1.1035
                       (90.0, 1.10070, 1.10080),
                       (95.0, 1.10050, 1.10060),
                       (120.0, 1.10290, 1.10300)])
        t = [x for x in r["trades"] if x["strategy"] == "B"][0]
        self.assertAlmostEqual(t["stop"], 1.10350, places=12)

    def test_b_target_crossed_at_entry_no_trade(self):
        r = self.b_up([(90.0, 1.10070, 1.10080),
                       (95.0, 1.09970, 1.09980)])         # ask 1.0998 <= P0
        st = r["setups"]["B"]
        self.assertEqual(st["status"], "NO_TRADE_TARGET_CROSSED")
        self.assertFalse([x for x in r["trades"] if x["strategy"] == "B"])

    def test_b_no_trigger_within_5m(self):
        r = self.b_up([(40.0, 1.10170, 1.10180),
                       (200.0, 1.10170, 1.10180),
                       (310.0, 1.10170, 1.10180)])
        self.assertEqual(r["setups"]["B"]["status"], "NO_TRIGGER")

    def test_b_down_shock_mirror_long(self):
        spec = quiet_baseline() + [(1.0, 1.09800, 1.09810),
                                   (30.0, 1.09800, 1.09810),
                                   (90.0, 1.09930, 1.09940),  # mid>=1.0990 lvl
                                   (95.0, 1.09950, 1.09960),  # entry ASK
                                   (150.0, 1.10010, 1.10020)]  # bid>=P0 target
        r = L.run_event_on_window(ev(), *ticks(spec))
        t = [x for x in r["trades"] if x["strategy"] == "B"][0]
        self.assertEqual(t["side"], 1)
        self.assertAlmostEqual(t["stop"], 1.09805, places=12)
        self.assertAlmostEqual(t["entry"], 1.09960, places=12)   # ASK
        self.assertEqual(t["exit_reason"], "TARGET")
        self.assertAlmostEqual(t["net_pips"], 4.0, places=6)

    def test_b_trigger_window_is_t0_30s_to_t0_5m_inclusive(self):
        # retrace tick at T0+5m exactly (300 s) still triggers
        r = self.b_up([(300.0, 1.10070, 1.10080),
                       (305.0, 1.10050, 1.10060)])
        t = [x for x in r["trades"] if x["strategy"] == "B"][0]
        self.assertEqual(t["trigger_ns"], T0 + 300 * NS)


class StrategyCTests(unittest.TestCase):
    # range over [T0, T0+5m): highs/lows from mids
    #   +1s/+60s mid 1.10055, +150s mid 1.10105, +240s mid 1.10025
    #   -> NEWS_HIGH 1.10105, NEWS_LOW 1.10025, NEWS_MID 1.10065
    def c_up(self, extra):
        spec = quiet_baseline() + [(1.0, 1.10050, 1.10060),
                                   (60.0, 1.10050, 1.10060),
                                   (150.0, 1.10100, 1.10110),
                                   (240.0, 1.10020, 1.10030)] + extra
        return L.run_event_on_window(ev(), *ticks(spec))

    def test_c_range_freezes_exactly_at_t0_plus_5m(self):
        # tick AT T0+5m is outside the range and may be the breakout tick
        r = self.c_up([(300.0, 1.10200, 1.10210),          # exactly T0+5m
                       (305.0, 1.10205, 1.10215),          # entry ASK
                       (330.0, 1.10450, 1.10460)])         # bid >= 1.5R target
        st = r["setups"]["C"]
        self.assertEqual(st["status"], "TRADED")
        t = [x for x in r["trades"] if x["strategy"] == "C"][0]
        self.assertEqual(t["side"], 1)
        self.assertEqual(t["trigger_ns"], T0 + 300 * NS)
        self.assertAlmostEqual(t["news_high"], 1.10105, places=12)
        self.assertAlmostEqual(t["news_low"], 1.10025, places=12)
        self.assertAlmostEqual(t["news_mid"], 1.10065, places=12)
        self.assertAlmostEqual(t["stop"], 1.10065, places=12)
        self.assertAlmostEqual(t["entry"], 1.10215, places=12)   # ASK
        risk = 1.10215 - 1.10065
        self.assertAlmostEqual(t["target"], 1.10215 + 1.5 * risk, places=12)
        self.assertEqual(t["exit_reason"], "TARGET")

    def test_c_cannot_trigger_before_t0_plus_5m(self):
        # spike at T0+4m10s is INSIDE the range (raises NEWS_HIGH, no trade);
        # nothing breaks it afterwards
        r = self.c_up([(250.0, 1.10300, 1.10310)])
        self.assertEqual(r["setups"]["C"]["status"], "NO_BREAKOUT")
        self.assertFalse([x for x in r["trades"] if x["strategy"] == "C"])

    def test_c_breakout_below_range_short(self):
        r = self.c_up([(320.0, 1.09900, 1.09910),          # mid < news_low
                       (330.0, 1.09895, 1.09905),          # entry BID
                       (400.0, 1.09500, 1.09510)])         # ask <= 1.5R target
        t = [x for x in r["trades"] if x["strategy"] == "C"][0]
        self.assertEqual(t["side"], -1)
        self.assertAlmostEqual(t["stop"], 1.10065, places=12)   # NEWS_MID
        self.assertAlmostEqual(t["entry"], 1.09895, places=12)
        self.assertEqual(t["exit_reason"], "TARGET")

    def test_c_search_window_closes_at_t0_plus_35m(self):
        # first move beyond the range arrives AFTER T0+35m -> no breakout
        r = self.c_up([(2101.0, 1.10200, 1.10210)])        # T0+35m01s
        self.assertEqual(r["setups"]["C"]["status"], "NO_BREAKOUT")

    def test_c_no_breakout_inside_35m_if_range_holds(self):
        r = self.c_up([(600.0, 1.10080, 1.10090),
                       (1200.0, 1.10030, 1.10040)])
        self.assertEqual(r["setups"]["C"]["status"], "NO_BREAKOUT")


class ExecutionSafetyTests(unittest.TestCase):
    def base(self, entry_spread):
        spec = quiet_baseline() + [(1.0, 1.10100, 1.10110),
                                   (30.0, 1.10100, 1.10110)]
        spec.append((31.0, 1.10100 - entry_spread / 2,
                     1.10100 + entry_spread / 2))
        spec += [(40.0, 1.10300, 1.10310)]
        return L.run_event_on_window(ev(), *ticks(spec))

    def test_spread_safety_skips_wide_entry(self):
        r = self.base(0.0006)                     # 6 pips vs 3x1 allowed
        self.assertEqual(r["setups"]["A"]["status"], "SPREAD_TOO_WIDE")
        self.assertFalse([x for x in r["trades"] if x["strategy"] == "A"])

    def test_spread_safety_allows_entry_at_exactly_3x(self):
        r = self.base(0.0003)                     # == 3 x 1 pip -> allowed
        self.assertEqual(r["setups"]["A"]["status"], "TRADED")

    def test_risk_too_small_no_trade(self):
        # 11.5 pip shock qualifies but executable entry sits 0.5 pip above
        # P0 -> effective risk < 1 pip -> NO TRADE
        spec = quiet_baseline() + [(1.0, 1.10110, 1.10120),
                                   (30.0, 1.10110, 1.10120),
                                   (31.0, 1.09995, 1.10005),
                                   (40.0, 1.10300, 1.10310)]
        r = L.run_event_on_window(ev(), *ticks(spec))
        self.assertEqual(r["setups"]["A"]["status"], "NO_TRADE_RISK_TOO_SMALL")

    def test_no_fill_when_no_tick_after_decision(self):
        spec = quiet_baseline() + [(1.0, 1.10100, 1.10110),
                                   (30.0, 1.10100, 1.10110)]
        r = L.run_event_on_window(ev(), *ticks(spec))
        self.assertEqual(r["setups"]["A"]["status"], "NO_FILL")


class DataGapTests(unittest.TestCase):
    def test_data_gap_invalidates_open_trade(self):
        spec = quiet_baseline() + [(1.0, 1.10100, 1.10110),
                                   (30.0, 1.10100, 1.10110),
                                   (31.0, 1.10100, 1.10110),
                                   (40.0, 1.10120, 1.10130),   # trade open
                                   (9000.0, 1.10120, 1.10130)]  # ~2.5h silence
        r = L.run_event_on_window(ev(), *ticks(spec))
        t = r["trades"][0]
        self.assertEqual(t["exit_reason"], "DATA_GAP_INVALID")
        self.assertIsNone(t["net_pips"])
        self.assertEqual(t["exit_ts"], T0 + 40 * NS)     # gap onset tick

    def test_weekend_closure_is_not_a_data_gap(self):
        # Fri 21:30Z -> Sun 22:05Z silence: non-weekend portion is only the
        # Friday 21:30-21:59 + Sunday 22:01-22:05 minutes -> below 1h
        fri = ns("2013-06-07T21:30:00Z")
        sun = ns("2013-06-09T22:05:00Z")
        ts = np.array([fri, sun], dtype=np.int64)
        self.assertFalse(L.gaps_in_window(ts))
        # a same-length silence in the middle of a weekday IS a gap
        wed1 = ns("2013-06-05T21:00:00Z")
        wed2 = ns("2013-06-07T22:05:00Z")
        self.assertTrue(L.gaps_in_window(
            np.array([wed1, wed2], dtype=np.int64)))


class HardCutTests(unittest.TestCase):
    def test_month_guard_blocks_2019(self):
        with self.assertRaises(ValueError):
            MTF.assert_month_in_discovery(2019, 1)
        with self.assertRaises(ValueError):
            MTF.assert_month_in_discovery(2018, 13)
        MTF.assert_month_in_discovery(2018, 12)          # last allowed

    def test_load_events_drops_fomc_and_2019(self):
        csv_txt = (
            "event_id,family,release_timestamp_utc,tick_alignment_status,"
            "post_tick_lag_ms\n"
            "MACRO-NFP-201806,NFP,2018-06-01T12:30:00Z,ALIGNED,120\n"
            "MACRO-CPI-201806,CPI,2018-07-12T12:30:00Z,ALIGNED,488\n"
            "MACRO-FOMC-201806,FOMC,2018-06-13T18:00:00Z,ALIGNED,19\n"
            "MACRO-NFP-201901,NFP,2019-02-01T13:30:00Z,ALIGNED,100\n")
        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False,
                                         encoding="utf-8") as f:
            f.write(csv_txt)
            path = f.name
        try:
            evs = L.load_events(path)
        finally:
            os.unlink(path)
        self.assertEqual([e["event_id"] for e in evs],
                         ["MACRO-NFP-201806", "MACRO-CPI-201806"])
        self.assertLess(evs[0]["t0_ns"], L.DISCOVERY_END_NS)

    def test_entry_skips_fill_at_or_after_2019(self):
        d = ns("2018-12-31T23:59:00Z")
        ts = np.array([ns("2019-01-01T00:01:00Z")], dtype=np.int64)
        bid = np.array([1.0])
        ask = np.array([1.1])
        status, _i, _fts, _px = L.find_entry(ts, bid, ask, d, 1,
                                             np.array([], dtype=np.int64))
        self.assertEqual(status, "SKIPPED_HARD_END")


class MetricsTests(unittest.TestCase):
    @staticmethod
    def trade(net, risk, family, year, reason="TARGET", shock=20.0,
              score=4.0):
        return {"strategy": "A", "event_id": f"E{net}_{year}_{family}",
                "family": family, "side": 1,
                "t0_ns": int(pd.Timestamp(f"{year}-06-07T12:30:00Z").value),
                "decision_ns": 0, "trigger_ns": None,
                "entry_ts": int(
                    pd.Timestamp(f"{year}-06-07T12:31:00Z").value),
                "entry": 1.1, "stop": 1.09, "target": 1.12,
                "risk_pips": risk, "exit_ts": None, "exit_reason": reason,
                "exit_price": None, "entry_bid": 1.0, "entry_ask": 1.2,
                "net_pips": net, "gross_mid_pips": net + 0.3,
                "shock_pips": shock, "shock_score": score}

    def test_stress_arithmetic_and_exit_counts(self):
        trades = [self.trade(10.0, 10.0, "NFP", 2011),
                  self.trade(-5.0, 10.0, "CPI", 2011),
                  self.trade(3.0, 10.0, "NFP", 2012, reason="STOP"),
                  self.trade(1.0, 10.0, "CPI", 2012, reason="TIME"),
                  self.trade(2.0, 10.0, "NFP", 2012,
                             reason="DATA_GAP_INVALID")]
        m = L.compute_metrics("A", trades,
                              ["TRADED"] * 4 + ["DATA_GAP_INVALID"], 5, 4)
        self.assertEqual(m["n_trades"], 4)              # gap-invalid excluded
        self.assertAlmostEqual(m["net_mean_pips"],
                               (10 - 5 + 3 + 1) / 4, places=6)
        self.assertAlmostEqual(m["stress_025_mean"],
                               m["net_mean_pips"] - 0.50, places=6)
        self.assertAlmostEqual(m["stress_050_mean"],
                               m["net_mean_pips"] - 1.00, places=6)
        self.assertAlmostEqual(m["stress_100_mean"],
                               m["net_mean_pips"] - 2.00, places=6)
        self.assertEqual(m["exit_counts"]["TARGET"], 2)
        self.assertEqual(m["exit_counts"]["STOP"], 1)
        self.assertEqual(m["exit_counts"]["TIME"], 1)
        self.assertEqual(m["exit_counts"]["DATA_GAP_INVALID"], 1)
        self.assertEqual(m["n_data_gap_invalid"], 1)

    def test_bootstrap_and_remove_best_match_reference(self):
        nets = np.array([3.0, -1.0, 2.0, 5.0, -2.0, 1.5, 4.0, -0.5])
        lo, hi = MTF.bootstrap_ci95(nets, n_res=2000, seed=42)
        trades = [self.trade(v, 10.0, "NFP" if i % 2 else "CPI",
                             2010 + i % 9) for i, v in enumerate(nets)]
        m = L.compute_metrics("A", trades, ["TRADED"] * len(nets),
                              len(nets), len(nets))
        self.assertAlmostEqual(m["ci95_lo"], round(lo, 4), places=6)
        self.assertAlmostEqual(m["ci95_hi"], round(hi, 4), places=6)
        self.assertAlmostEqual(m["remove_best_1pct_mean"],
                               round(MTF.remove_best_1pct(nets), 4),
                               places=6)

    def test_fail_fast_reject(self):
        trades = [self.trade(-4.0, 10.0, "NFP", 2011),
                  self.trade(-6.0, 10.0, "CPI", 2012)]
        m = L.compute_metrics("A", trades, ["TRADED"] * 2, 2, 2)
        self.assertEqual(m["verdict"], "REJECT")

    def test_fail_gate_between_reject_and_promising(self):
        # positive but tiny edge, too few trades
        trades = [self.trade(1.0, 10.0, "NFP", y) for y in range(2010, 2019)]
        m = L.compute_metrics("A", trades, ["TRADED"] * 9, 9, 9)
        self.assertEqual(m["verdict"], "FAIL_GATE")

    def test_promising_gate_pass(self):
        trades = []
        for y in range(2010, 2019):
            for j in range(5):
                trades.append(self.trade(12.0, 10.0,
                                         "NFP" if j % 2 else "CPI", y))
                trades.append(self.trade(-3.0, 10.0,
                                         "CPI" if j % 2 else "NFP", y))
        m = L.compute_metrics("A", trades, ["TRADED"] * len(trades),
                              len(trades), len(trades))
        self.assertEqual(m["n_trades"], 90)
        self.assertAlmostEqual(m["net_mean_pips"], 4.5, places=6)
        self.assertEqual(m["positive_years"], 9)
        self.assertGreater(m["profit_factor"], 1.25)
        self.assertGreater(m["expectancy_r"], 0.10)
        self.assertGreater(m["nfp_mean_net"], 0)
        self.assertGreater(m["cpi_mean_net"], 0)
        self.assertGreater(m["stress_050_mean"], 0)
        self.assertGreater(m["remove_best_1pct_mean"], 0)
        self.assertEqual(m["verdict"], "MACRO_TICK_PROMISING")

    def test_pooled_cannot_pass_with_negative_family(self):
        trades = []
        for y in range(2010, 2019):
            for j in range(5):
                trades.append(self.trade(12.0, 10.0, "NFP", y))
                trades.append(self.trade(-3.0, 10.0, "CPI", y))
        trades.append(self.trade(-500.0, 10.0, "CPI", 2018))   # sinks CPI
        m = L.compute_metrics("A", trades, ["TRADED"] * len(trades),
                              len(trades), len(trades))
        self.assertLess(m["cpi_mean_net"], 0)
        self.assertNotEqual(m["verdict"], "MACRO_TICK_PROMISING")


class PipelineIntegrationTest(unittest.TestCase):
    def test_full_event_produces_all_three_setups(self):
        # quiet baseline, +20.5 pip shock, B retrace trigger, C breakout
        spec = quiet_baseline() + [
            (1.0, 1.10200, 1.10210),           # post-release
            (30.0, 1.10200, 1.10210),          # P30 -> +20.5 pips
            (40.0, 1.10170, 1.10180),          # A entry zone / B watching
            (90.0, 1.10070, 1.10080),          # B trigger (mid <= 1.101025)
            (95.0, 1.10050, 1.10060),          # B entry
            (120.0, 1.09890, 1.09900),         # B target (ask <= P0)
            (200.0, 1.10040, 1.10050),
            (290.0, 1.10040, 1.10050),
            (300.0, 1.10250, 1.10260),         # C breakout above range high
            (305.0, 1.10255, 1.10265),         # C entry
            (420.0, 1.10600, 1.10610)]         # C target
        r = L.run_event_on_window(ev(), *ticks(spec))
        self.assertIsNone(r["exclusion"])
        self.assertTrue(r["qualifying"])
        self.assertEqual({"A", "B", "C"}, set(r["setups"].keys()))
        kinds = {t["strategy"] for t in r["trades"]}
        self.assertEqual(kinds, {"A", "B", "C"})
        for k in "ABC":
            self.assertEqual(len([t for t in r["trades"]
                                  if t["strategy"] == k]), 1)
        for t in r["trades"]:
            self.assertIn(t["family"], ("NFP", "CPI"))
            self.assertIsNotNone(t["shock_score"])
        by_k = {t["strategy"]: t for t in r["trades"]}
        self.assertEqual(by_k["A"]["exit_reason"], "STOP")
        self.assertEqual(by_k["B"]["exit_reason"], "TARGET")
        self.assertEqual(by_k["C"]["exit_reason"], "TARGET")


if __name__ == "__main__":
    unittest.main(verbosity=2)
