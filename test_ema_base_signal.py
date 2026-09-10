#!/usr/bin/env python3
"""Synthetic test suite for EMA_BASE_CORE_V1 (Mission 2).

Tests are labeled A..R as mandated.  All data is SYNTHETIC and built in
memory — no real dataset is read, no OOS window is touched, no performance
metric is computed.  The signal component is exercised through the
canonical research engine so the causal views (closed M15, closed H1) are
the engine's own bounded views.

Run:  python -m unittest test_ema_base_signal -v
"""
from __future__ import annotations

import math
import unittest
from datetime import datetime, timedelta

from ema_base_signal import (
    EmaBaseCoreV1,
    EmaBaseCoreV1Params,
    EXCLUDED_POSTHOC_FILTERS,
    SignalType,
)
from research_engine import (
    Bar,
    CostModel,
    ResearchEngine,
    SizingConfig,
    Strategy,
    ema,
    rsi_wilder,
)

PIP = 0.0001
T0 = datetime(2023, 1, 2, 9, 0)   # bar 0 opens here; 15-min bars
RISE_BARS = 288                   # 72 hours of steady rise (phase 1)
DRIFT_BARS = 60                   # alternating drift (phase 2)
DECISION = RISE_BARS + 44         # deep enough in drift for RSI convergence


def make_bars(deltas_pips, start_close=1.1000, low_extra=None, high_extra=None):
    """Build OHLC bars from per-bar close deltas (pips).

    Default wicks: 1 pip each side.  low_extra/high_extra: {index: pips}.
    """
    bars = []
    prev = start_close
    for k, d in enumerate(deltas_pips):
        o = prev
        c = o + d * PIP
        le = (low_extra or {}).get(k, 1.0)
        he = (high_extra or {}).get(k, 1.0)
        bars.append(Bar(T0 + timedelta(minutes=15 * k), o,
                        max(o, c) + he * PIP, min(o, c) - le * PIP, c))
        prev = c
    return bars


def long_scenario_bars():
    """Phase 1: steady +3 pips/bar rise (H1 trend long, EMA50 rising).
    Phase 2: alternating -3/+5 drift (RSI ~60s, mild up-drift keeps trend).
    Decision bar: b2 = -3 pullback bar (wick dips below the lagging EMA20),
    b1 = +5 rejection bar."""
    deltas = [3.0] * RISE_BARS
    deltas += [(-3.0 if k % 2 == 0 else 5.0) for k in range(DRIFT_BARS)]
    b2 = DECISION - 2
    return make_bars(deltas, low_extra={b2: 12.0})


def short_scenario_bars():
    """Mirror: steady -3 pips/bar fall, then alternating +3/-5 drift.
    b2 = +3 pullback bar (wick above the lagging EMA20), b1 = -5 rejection."""
    deltas = [-3.0] * RISE_BARS
    deltas += [(3.0 if k % 2 == 0 else -5.0) for k in range(DRIFT_BARS)]
    b2 = DECISION - 2
    return make_bars(deltas, high_extra={b2: 12.0})


class SignalProbe(Strategy):
    """Records the signal diagnostic at every decision; opens NO order."""

    def __init__(self, params=None):
        self.signal = EmaBaseCoreV1(params)
        self.records = []

    def on_bar(self, ctx):
        diag = self.signal.evaluate(ctx)
        self.records.append(diag)
        return None  # signal-only: never trades


def run_signal(bars, params=None):
    eng = ResearchEngine(
        instrument=__import__("research_engine").EURUSD_SPEC,
        costs=CostModel(spread_pips=1.0),
        sizing=SizingConfig(mode="fixed_lot", fixed_lot=0.01),
    )
    probe = SignalProbe(params)
    res = eng.run(bars, probe)
    return res, probe.records


def tail_deltas():
    """The drift-phase delta list (for surgical tail edits in tests)."""
    return [(-3.0 if k % 2 == 0 else 5.0) for k in range(DRIFT_BARS)]


class TestEmaBaseCoreV1(unittest.TestCase):
    def rec(self, records, idx=DECISION):
        return records[idx]

    # -- A ---------------------------------------------------------------
    def test_a_full_long_setup(self):
        res, records = run_signal(long_scenario_bars())
        d = self.rec(records)
        self.assertEqual(d.final_signal, SignalType.LONG)
        self.assertEqual(d.blocked_by, ())
        self.assertTrue(d.trend_long and not d.trend_short)
        self.assertTrue(d.pullback_long and d.rejection_long)
        self.assertGreaterEqual(d.body_ratio, 0.60)
        self.assertTrue(d.body_comparison)
        self.assertIsNotNone(d.rsi_value)
        self.assertLessEqual(d.rsi_value, 70.0)
        # signal-only component: the engine opened no trade
        self.assertEqual(res.n_trades, 0)

    # -- B ---------------------------------------------------------------
    def test_b_full_short_setup(self):
        res, records = run_signal(short_scenario_bars())
        d = self.rec(records)
        self.assertEqual(d.final_signal, SignalType.SHORT)
        self.assertEqual(d.blocked_by, ())
        self.assertTrue(d.trend_short and not d.trend_long)
        self.assertTrue(d.pullback_short and d.rejection_short)
        self.assertGreaterEqual(d.body_ratio, 0.60)
        self.assertTrue(d.body_comparison)
        self.assertGreaterEqual(d.rsi_value, 30.0)

    # -- C ---------------------------------------------------------------
    def test_c_trend_absent(self):
        # perfectly flat H1 closes -> close == EMA50, slope == 0 -> no trend
        deltas = []
        for _ in range(64 * 4):          # 64 hours
            deltas += [1.0, -1.0, 1.0, -1.0]   # hour close = start level
        bars = make_bars(deltas)
        decision = 64 * 4 - 2
        _, records = run_signal(bars)
        d = records[decision]
        self.assertEqual(d.final_signal, SignalType.NONE)
        self.assertEqual(d.blocked_by, ("TREND_ABSENT",))
        self.assertFalse(d.trend_long)
        self.assertFalse(d.trend_short)

    # -- D ---------------------------------------------------------------
    def test_d_pullback_absent(self):
        deltas = [3.0] * RISE_BARS + tail_deltas()
        b2 = DECISION - 2
        # force the last three bars to end clearly ABOVE EMA20 with tiny wicks:
        # low[i-2] > EMA20[i-2] -> no pullback
        deltas[b2 - 1], deltas[b2], deltas[DECISION - 1] = 6.0, 3.0, 5.0
        bars = make_bars(deltas, low_extra={b2: 0.5, DECISION - 1: 1.0})
        _, records = run_signal(bars)
        d = self.rec(records)
        self.assertEqual(d.final_signal, SignalType.NONE)
        self.assertEqual(d.blocked_by, ("PULLBACK_LONG",))
        self.assertFalse(d.pullback_long)

    # -- E ---------------------------------------------------------------
    def test_e_rejection_wrong_sense(self):
        deltas = [3.0] * RISE_BARS + tail_deltas()
        deltas[DECISION - 1] = -10.0          # bearish rejection bar in long trend
        bars = make_bars(deltas, low_extra={DECISION - 2: 12.0})
        _, records = run_signal(bars)
        d = self.rec(records)
        self.assertEqual(d.final_signal, SignalType.NONE)
        self.assertEqual(d.blocked_by, ("REJECTION_LONG",))
        self.assertFalse(d.rejection_long)

    # -- F ---------------------------------------------------------------
    def test_f_body_ratio_below_min(self):
        deltas = [3.0] * RISE_BARS + tail_deltas()
        b1 = DECISION - 1
        bars = make_bars(deltas, low_extra={DECISION - 2: 12.0, b1: 6.0},
                         high_extra={b1: 6.0})
        _, records = run_signal(bars)
        d = self.rec(records)
        self.assertEqual(d.final_signal, SignalType.NONE)
        self.assertEqual(d.blocked_by, ("BODY_RATIO_LONG",))
        self.assertIsNotNone(d.body_ratio)
        self.assertLess(d.body_ratio, 0.60)

    # -- G ---------------------------------------------------------------
    def test_g_body_comparison_fails(self):
        deltas = [3.0] * RISE_BARS + tail_deltas()
        b2 = DECISION - 2
        deltas[b2], deltas[DECISION - 1] = -14.0, 12.0
        bars = make_bars(deltas, low_extra={b2: 3.0})
        _, records = run_signal(bars)
        d = self.rec(records)
        self.assertEqual(d.final_signal, SignalType.NONE)
        self.assertEqual(d.blocked_by, ("BODY_COMPARISON_LONG",))
        self.assertFalse(d.body_comparison)

    # -- H ---------------------------------------------------------------
    def test_h_rsi_over_max_long(self):
        deltas = [3.0] * RISE_BARS
        deltas += [5.0] * DRIFT_BARS          # steady rise -> RSI ~100
        b2 = DECISION - 2
        deltas[DECISION - 1] = 8.0            # body(i-1) > body(i-2)
        bars = make_bars(deltas, low_extra={b2: 60.0})   # force pullback wick
        _, records = run_signal(bars)
        d = self.rec(records)
        self.assertIsNotNone(d.rsi_value)
        self.assertGreater(d.rsi_value, 70.0)
        self.assertEqual(d.final_signal, SignalType.NONE)
        self.assertEqual(d.blocked_by, ("RSI_LONG_OVER_MAX",))

    # -- I ---------------------------------------------------------------
    def test_i_rsi_under_min_short(self):
        deltas = [-3.0] * RISE_BARS
        deltas += [-5.0] * DRIFT_BARS         # steady fall -> RSI ~0
        b2 = DECISION - 2
        deltas[DECISION - 1] = -8.0           # body(i-1) > body(i-2)
        bars = make_bars(deltas, high_extra={b2: 60.0})
        _, records = run_signal(bars)
        d = self.rec(records)
        self.assertIsNotNone(d.rsi_value)
        self.assertLess(d.rsi_value, 30.0)
        self.assertEqual(d.final_signal, SignalType.NONE)
        self.assertEqual(d.blocked_by, ("RSI_SHORT_UNDER_MIN",))

    # -- J / K -----------------------------------------------------------
    def test_j_rsi_exactly_at_long_max_allowed(self):
        _, records = run_signal(long_scenario_bars())
        rsi_at_b1 = self.rec(records).rsi_value
        self.assertLess(rsi_at_b1, 70.0)      # base setup valid with defaults
        # threshold exactly equal to the observed RSI -> allowed (RSI <= max)
        _, rec_eq = run_signal(long_scenario_bars(),
                               EmaBaseCoreV1Params(rsi_long_max=rsi_at_b1))
        self.assertEqual(rec_eq[DECISION].final_signal, SignalType.LONG)
        # threshold one float below the observed RSI -> RSI > max -> rejected
        _, rec_lo = run_signal(
            long_scenario_bars(),
            EmaBaseCoreV1Params(rsi_long_max=math.nextafter(rsi_at_b1, 0.0)))
        self.assertEqual(rec_lo[DECISION].final_signal, SignalType.NONE)
        self.assertEqual(rec_lo[DECISION].blocked_by, ("RSI_LONG_OVER_MAX",))

    def test_k_rsi_exactly_at_short_min_allowed(self):
        _, records = run_signal(short_scenario_bars())
        rsi_at_b1 = self.rec(records).rsi_value
        self.assertGreater(rsi_at_b1, 30.0)
        _, rec_eq = run_signal(short_scenario_bars(),
                               EmaBaseCoreV1Params(rsi_short_min=rsi_at_b1))
        self.assertEqual(rec_eq[DECISION].final_signal, SignalType.SHORT)
        _, rec_hi = run_signal(
            short_scenario_bars(),
            EmaBaseCoreV1Params(rsi_short_min=math.nextafter(rsi_at_b1,
                                                             math.inf)))
        self.assertEqual(rec_hi[DECISION].final_signal, SignalType.NONE)
        self.assertEqual(rec_hi[DECISION].blocked_by, ("RSI_SHORT_UNDER_MIN",))

    # -- L / M / N ---------------------------------------------------------
    def test_l_h1_ema50_not_warm(self):
        _, records = run_signal(long_scenario_bars())
        d = records[100]                       # 25 closed H1 buckets < 50
        self.assertEqual(d.final_signal, SignalType.NONE)
        self.assertFalse(d.warmup_h1_ema50_ready)
        self.assertIn("H1_EMA50_NOT_WARM", d.blocked_by)
        self.assertIn("H1_SLOPE_NOT_WARM", d.blocked_by)

    def test_m_ema20_not_warm(self):
        _, records = run_signal(long_scenario_bars())
        d = records[17]                        # EMA20 needs 21, RSI needs 15
        self.assertEqual(d.final_signal, SignalType.NONE)
        self.assertFalse(d.warmup_m15_ema20_ready)
        self.assertTrue(d.warmup_m15_rsi_ready)
        self.assertIn("M15_EMA20_NOT_WARM", d.blocked_by)

    def test_n_rsi_not_warm(self):
        _, records = run_signal(long_scenario_bars())
        d = records[10]                        # RSI needs 15 closes
        self.assertEqual(d.final_signal, SignalType.NONE)
        self.assertFalse(d.warmup_m15_rsi_ready)
        self.assertIn("M15_RSI_NOT_WARM", d.blocked_by)
        # NOTE: RSI-only isolation is impossible (EMA20 requires more bars
        # than RSI), so the diagnostic legitimately lists both.

    # -- O ---------------------------------------------------------------
    def test_o_decision_bar_cannot_influence_signal(self):
        bars = long_scenario_bars()
        _, records_a = run_signal(bars)
        mutated = list(bars)
        D = bars[DECISION]
        mutated[DECISION] = Bar(D.dt, D.open, D.high + 90 * PIP,
                                D.low - 90 * PIP, D.close - 90 * PIP)
        _, records_b = run_signal(mutated)
        self.assertEqual(records_a[DECISION], records_b[DECISION])
        self.assertEqual(records_a[DECISION].final_signal, SignalType.LONG)

    # -- P ---------------------------------------------------------------
    def test_p_forming_h1_mutation_cannot_change_signal(self):
        bars = long_scenario_bars()
        _, records_a = run_signal(bars)
        mutated = list(bars)
        D = bars[DECISION]
        hour = D.dt.hour
        for k in range(DECISION, len(mutated)):
            if mutated[k].dt.hour == hour and k > DECISION:
                b = mutated[k]
                mutated[k] = Bar(b.dt, b.open, b.high + 50 * PIP,
                                 b.low - 50 * PIP, b.close + 50 * PIP)
        _, records_b = run_signal(mutated)
        self.assertEqual(records_a[DECISION], records_b[DECISION])

    # -- Q ---------------------------------------------------------------
    def test_q_deterministic_same_history_same_timestamp(self):
        bars = long_scenario_bars()
        _, r1 = run_signal(bars)
        _, r2 = run_signal(bars)
        self.assertEqual(r1, r2)               # full diagnostic list equality

    # -- R ---------------------------------------------------------------
    def test_r_blocked_reason_identifies_blocking_condition(self):
        # pullback absent AND body ratio bad -> the FIRST blocking gate in the
        # documented canonical order (PULLBACK) is reported, precisely.
        deltas = [3.0] * RISE_BARS + tail_deltas()
        b2 = DECISION - 2
        deltas[b2 - 1], deltas[b2], deltas[DECISION - 1] = 6.0, 3.0, 5.0
        bars = make_bars(deltas, low_extra={b2: 0.5, DECISION - 1: 1.0},
                         high_extra={DECISION - 1: 8.0})
        _, records = run_signal(bars)
        d = self.rec(records)
        self.assertEqual(d.final_signal, SignalType.NONE)
        self.assertEqual(d.blocked_by, ("PULLBACK_LONG",))

    # -- extra: incremental indicators match the engine reference ---------
    def test_indicator_state_matches_engine_reference(self):
        deltas = [3.0, -1.0, 2.0, -2.0, 1.0, -3.0, 4.0, 0.5] * 40
        bars = make_bars(deltas)
        _, records = run_signal(bars)
        closes = [b.close for b in bars]
        ref_rsi = rsi_wilder(closes, 14)
        # diagnostics expose rsi_value only after the full H1 warm-up
        # (55 closed buckets); compare at such decisions
        for D in (240, 260, 280, 300, 319):
            d = records[D]
            self.assertIsNotNone(d.rsi_value)
            self.assertAlmostEqual(d.rsi_value, ref_rsi[D - 1], places=10)
        # EMA seeding convention: first EMA value equals SMA of first 20 closes
        ref_ema = ema(closes, 20)
        self.assertAlmostEqual(ref_ema[19],
                               sum(closes[:20]) / 20.0, places=15)

    # -- extra: pre-registration markers ----------------------------------
    def test_preregistration_markers_and_exclusions(self):
        self.assertTrue(__import__("ema_base_signal").PARAMETERS_FROZEN_BEFORE_RESULTS)
        self.assertTrue(__import__("ema_base_signal").LEGACY_DERIVED_PARAMETERS)
        self.assertTrue(__import__("ema_base_signal").HISTORICALLY_CONTAMINATED_PARAMETERS)
        for f in ("ATR min/max band (H1)", "EMA50 distance max", "Friday block",
                  "blocked hour 13", "toxic hour/day combinations",
                  "MinSL / MaxSL bounds", "London / NY session windows",
                  "swing SL + pip buffer", "MinRR / take-profit", "breakeven",
                  "pyramid L0/L1/L2", "reverse trades"):
            self.assertIn(f, EXCLUDED_POSTHOC_FILTERS)
        p = EmaBaseCoreV1Params()
        self.assertEqual((p.h1_trend_ema_period, p.h1_trend_bars,
                          p.m15_entry_ema_period, p.rsi_period, p.rsi_long_max,
                          p.rsi_short_min, p.rejection_body_min),
                         (50, 5, 20, 14, 70.0, 30.0, 0.60))


if __name__ == "__main__":
    unittest.main(verbosity=2)
