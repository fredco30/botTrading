#!/usr/bin/env python3
"""Test suite for CANONICAL_RESEARCH_ENGINE V1 (test_research_engine.py).

Tests are labeled A..O as mandated by the mission.  All datasets are
SYNTHETIC and built in memory — no real data, no OOS window, no strategy
performance claims.  Run:  python -m unittest test_research_engine -v

Timeline used by every scenario (M15, from 2023-01-02 09:00):
  bars[i-1], bars[i-2] closed  ->  decision at open(bars[i])  ->  entry at
  open(bars[i]) on the execution side.
"""
from __future__ import annotations

import os
import tempfile
import unittest
from datetime import datetime, timedelta

from research_engine import (
    Bar,
    BreakevenConfig,
    CausalityError,
    CostModel,
    EngineError,
    EURUSD_SPEC,
    NullStrategy,
    Order,
    ResearchEngine,
    SizingConfig,
    Strategy,
    _BoundedSeries,
    get_instrument,
    load_bars_csv,
)

PIP = 0.0001
T0 = datetime(2023, 1, 2, 9, 0)


def pips(n: float) -> float:
    return n * PIP


def mk_bars(items):
    """items: list of (open, high, low, close) — 15-min bars from T0."""
    return [Bar(T0 + timedelta(minutes=15 * k), o, h, lo, c)
            for k, (o, h, lo, c) in enumerate(items)]


# Bars 0-1 form the causal setup (closed bars i-2, i-1 at the 09:30 decision);
# bar 2 is the decision/entry bar, opening at 1.1000.
SETUP = [
    (1.0990, 1.0992, 1.0988, 1.0990),
    (1.0990, 1.0998, 1.0989, 1.0995),   # rising closes -> long signal at 09:30
]
SETUP_SHORT = [
    (1.1010, 1.1012, 1.1008, 1.1010),
    (1.1010, 1.1011, 1.0998, 1.1000),   # falling closes -> short signal at 09:30
]


class TrendStrategy(Strategy):
    """Toy strategy: buy when the two last closed M15 closes are rising.

    Uses ONLY the causally bounded view.  SL/TP are Bid-side levels built
    from the decision-time price (open of the current bar).
    """

    def __init__(self, sl_pips: float, tp_pips: float) -> None:
        self.sl_pips = sl_pips
        self.tp_pips = tp_pips
        self.seen_max_close: dict = {}

    def on_bar(self, ctx):
        closes = [ctx.m15.close(t) for t in range(len(ctx.m15))]
        self.seen_max_close[ctx.decision_ts] = max(closes) if closes else None
        if len(closes) >= 2 and closes[-1] > closes[-2]:
            return Order(direction=1,
                         sl_price=ctx.open_bid - pips(self.sl_pips),
                         tp_price=ctx.open_bid + pips(self.tp_pips))
        return None


class ShortStrategy(Strategy):
    """Toy strategy: sell when the two last closed M15 closes are falling."""

    def __init__(self, sl_pips: float, tp_pips: float) -> None:
        self.sl_pips = sl_pips
        self.tp_pips = tp_pips

    def on_bar(self, ctx):
        closes = [ctx.m15.close(t) for t in range(len(ctx.m15))]
        if len(closes) >= 2 and closes[-1] < closes[-2]:
            return Order(direction=-1,
                         sl_price=ctx.open_bid + pips(self.sl_pips),
                         tp_price=ctx.open_bid - pips(self.tp_pips))
        return None


def engine(costs=None, sizing=None, breakeven=None, balance=10_000.0):
    return ResearchEngine(
        instrument=EURUSD_SPEC,
        costs=costs or CostModel(spread_pips=1.0),
        sizing=sizing or SizingConfig(mode="fixed_lot", fixed_lot=1.0),
        breakeven=breakeven or BreakevenConfig(),
        initial_balance=balance,
    )


class TestInstrumentAndLoader(unittest.TestCase):
    def test_instrument_eurusd_spec(self):
        inst = get_instrument("EURUSD")
        self.assertEqual(inst.symbol, "EURUSD")
        self.assertAlmostEqual(inst.pip_value_per_lot, 10.0, places=9)
        self.assertEqual(inst.pip_size, 0.0001)
        with self.assertRaises(EngineError):
            get_instrument("USDJPY")  # not enabled in V1

    def test_loader_rejects_bad_data(self):
        with tempfile.TemporaryDirectory() as tmp:  # outside the repo
            path = os.path.join(tmp, "bad.csv")
            with open(path, "w") as fh:
                fh.write("2023.01.02,09:00,1.1000,1.1010,1.0990,1.1005\n")
                fh.write("2023.01.02,08:45,1.1000,1.1010,1.0990,1.1005\n")  # order
            with self.assertRaises(EngineError):
                load_bars_csv(path)
            with open(path, "w") as fh:
                fh.write("2023.01.02,09:00,1.1000,GARBAGE,1.0990,1.1005\n")
            with self.assertRaises(EngineError):
                load_bars_csv(path)


class TestMandatedCases(unittest.TestCase):
    # -- A ---------------------------------------------------------------
    def test_a_signal_on_closed_bars_enters_at_open_i(self):
        bars = mk_bars(SETUP + [
            (1.1000, 1.1005, 1.0998, 1.1003),   # 09:30 entry bar, survives
            (1.1003, 1.1005, 1.0999, 1.1001),   # 09:45
            (1.1001, 1.1002, 1.0985, 1.0990),   # 10:00 — low hits SL 1.0990
        ])
        strat = TrendStrategy(sl_pips=10, tp_pips=10)
        res = engine().run(bars, strat)
        self.assertEqual(res.n_trades, 1)
        tr = res.trades[0]
        self.assertEqual(tr.decision_ts, T0 + timedelta(minutes=30))  # 09:30
        self.assertEqual(tr.entry_ts, tr.decision_ts)          # same instant
        self.assertAlmostEqual(tr.entry_exec, 1.1000 + pips(1), places=15)  # open[i] Ask
        self.assertAlmostEqual(tr.exit_exec, 1.0990, places=15)  # SL on Bid
        self.assertEqual(tr.exit_reason, "SL")

    # -- B ---------------------------------------------------------------
    def test_b_future_close_cannot_influence_decision(self):
        bars = mk_bars(SETUP + [
            (1.1000, 1.1005, 1.0998, 1.1003),   # decision/entry bar (index 2)
            (1.1003, 1.1005, 1.0999, 1.1001),
            (1.1001, 1.1002, 1.0985, 1.0990),
        ])
        s1 = TrendStrategy(sl_pips=10, tp_pips=10)
        r1 = engine().run(bars, s1)

        mutated = list(bars)
        decision_bar = 2  # 09:30
        mutated[decision_bar] = Bar(bars[decision_bar].dt, bars[decision_bar].open,
                                    9.99, 1.0998, 9.99)  # absurd future close
        s2 = TrendStrategy(sl_pips=10, tp_pips=10)
        r2 = engine().run(mutated, s2)

        # The decision and the entry AT that bar are strictly unaffected.
        key = lambda tr: (tr.decision_ts, tr.entry_ts, tr.entry_exec, tr.direction)
        early1 = [key(t) for t in r1.trades if t.decision_ts <= bars[decision_bar].dt]
        early2 = [key(t) for t in r2.trades if t.decision_ts <= bars[decision_bar].dt]
        self.assertEqual(early1, early2)
        self.assertEqual(len(early1), 1)
        # The causal view at that decision never exposed the future close.
        ts = bars[decision_bar].dt
        self.assertEqual(s1.seen_max_close[ts], 1.0995)
        self.assertEqual(s2.seen_max_close[ts], 1.0995)
        # And reading bar i from the decision-time view is impossible by design.
        opens = [b.open for b in bars]
        highs = [b.high for b in bars]
        lows = [b.low for b in bars]
        closes = [b.close for b in bars]
        dts = [b.dt for b in bars]
        view = _BoundedSeries(opens, highs, lows, closes, dts, 2)  # 2 closed bars
        with self.assertRaises(CausalityError):
            view.close(2)

    # -- C ---------------------------------------------------------------
    def test_c_long_uses_ask_entry_and_bid_exit(self):
        bars = mk_bars(SETUP + [
            (1.1000, 1.1001, 1.0985, 1.0987),   # SL Bid 1.0995 touched
        ])
        costs = CostModel(spread_pips=2.0)
        res = engine(costs).run(bars, TrendStrategy(sl_pips=5, tp_pips=20))
        self.assertEqual(res.n_trades, 1)
        tr = res.trades[0]
        self.assertAlmostEqual(tr.entry_exec, 1.1000 + pips(2), places=15)  # Ask
        self.assertAlmostEqual(tr.exit_exec, 1.0995, places=15)             # Bid SL
        self.assertAlmostEqual(tr.net_pnl, -70.0, places=6)     # -7 pips * $10 * 1 lot
        self.assertAlmostEqual(tr.gross_pnl, -50.0, places=6)   # -5 pips mid-to-mid
        self.assertAlmostEqual(tr.spread_cost, 20.0, places=6)  # 2 pips round trip
        self.assertAlmostEqual(tr.slippage_cost, 0.0, places=9)

    # -- D ---------------------------------------------------------------
    def test_d_short_uses_bid_entry_and_ask_exit(self):
        bars = mk_bars(SETUP_SHORT + [
            (1.1000, 1.1050, 1.0999, 1.1040),   # SL Ask 1.1040 touched
        ])
        costs = CostModel(spread_pips=2.0)
        res = engine(costs).run(bars, ShortStrategy(sl_pips=40, tp_pips=40))
        self.assertEqual(res.n_trades, 1)
        tr = res.trades[0]
        self.assertEqual(tr.direction, -1)
        self.assertAlmostEqual(tr.entry_exec, 1.1000, places=15)      # Bid
        self.assertAlmostEqual(tr.exit_exec, 1.1040, places=15)       # Ask level
        self.assertAlmostEqual(tr.net_pnl, -400.0, places=6)          # -40 pips
        self.assertAlmostEqual(tr.gross_pnl, -380.0, places=6)        # -40 +2 pips
        self.assertAlmostEqual(tr.spread_cost, 20.0, places=6)
        self.assertAlmostEqual(tr.gross_pnl - tr.spread_cost - tr.slippage_cost
                               - tr.commission_cost, tr.net_pnl, places=9)

    # -- E ---------------------------------------------------------------
    def test_e_higher_spread_never_improves_net(self):
        bars = mk_bars(SETUP + [
            (1.1000, 1.1030, 1.0999, 1.1025),   # TP 1.1020 hit
        ])
        nets = []
        for spr in (1.0, 2.0, 4.0):
            costs = CostModel(spread_pips=spr)
            res = engine(costs).run(bars, TrendStrategy(sl_pips=5, tp_pips=20))
            self.assertEqual(res.n_trades, 1)
            nets.append(res.total_net_pnl)
        self.assertGreaterEqual(nets[0], nets[1])
        self.assertGreater(nets[1], nets[2])
        self.assertAlmostEqual(nets[0] - nets[1], 10.0, places=6)  # 1 pip * $10

    # -- F ---------------------------------------------------------------
    def test_f_higher_commission_never_improves_net(self):
        bars = mk_bars(SETUP + [
            (1.1000, 1.1030, 1.0999, 1.1025),
        ])
        nets = []
        for comm in (0.0, 7.0, 14.0):
            costs = CostModel(spread_pips=1.0, commission_per_lot_per_side=comm)
            res = engine(costs).run(bars, TrendStrategy(sl_pips=5, tp_pips=20))
            nets.append(res.total_net_pnl)
        self.assertGreaterEqual(nets[0], nets[1])
        self.assertGreater(nets[1], nets[2])
        self.assertAlmostEqual(nets[0] - nets[1], 14.0, places=6)  # 2 sides * $7

    # -- G ---------------------------------------------------------------
    def test_g_higher_adverse_slippage_never_improves_net(self):
        bars = mk_bars(SETUP + [
            (1.1000, 1.1001, 1.0985, 1.0987),   # SL exit (stop slippage applies)
        ])
        nets = []
        for slip in (0.0, 1.0, 2.0):
            costs = CostModel(spread_pips=1.0, adverse_slippage_pips=slip)
            res = engine(costs).run(bars, TrendStrategy(sl_pips=5, tp_pips=20))
            nets.append(res.total_net_pnl)
        self.assertGreaterEqual(nets[0], nets[1])
        self.assertGreater(nets[1], nets[2])
        # entry + stop exit both slip: $20 more per pip of slippage
        self.assertAlmostEqual(nets[0] - nets[1], 20.0, places=6)

    # -- H ---------------------------------------------------------------
    def test_h_gap_through_stop_long_fills_at_first_price(self):
        bars = mk_bars(SETUP + [
            (1.1000, 1.1005, 1.0998, 1.1003),   # entry bar, survives
            (1.0850, 1.0860, 1.0840, 1.0845),   # opens far BELOW SL 1.0995
        ])
        costs = CostModel(spread_pips=1.0, adverse_slippage_pips=0.5)
        res = engine(costs).run(bars, TrendStrategy(sl_pips=5, tp_pips=20))
        tr = res.trades[0]
        self.assertEqual(tr.exit_reason, "SL")
        self.assertTrue(tr.gap_exit)
        self.assertAlmostEqual(tr.exit_exec, 1.0850 - pips(0.5), places=15)
        self.assertLess(tr.exit_exec, 1.0995)   # strictly worse than stop price

    # -- I ---------------------------------------------------------------
    def test_i_gap_through_stop_short_fills_at_first_price(self):
        bars = mk_bars(SETUP_SHORT + [
            (1.1000, 1.1005, 1.0995, 1.1002),   # entry bar, survives
            (1.1120, 1.1130, 1.1115, 1.1125),   # opens far ABOVE SL Ask 1.1040
        ])
        costs = CostModel(spread_pips=2.0, adverse_slippage_pips=0.5)
        res = engine(costs).run(bars, ShortStrategy(sl_pips=40, tp_pips=40))
        tr = res.trades[0]
        self.assertEqual(tr.exit_reason, "SL")
        self.assertTrue(tr.gap_exit)
        expected = 1.1120 + pips(2.0) + pips(0.5)  # ask open + adverse slippage
        self.assertAlmostEqual(tr.exit_exec, expected, places=15)
        self.assertGreater(tr.exit_exec, 1.1040)

    # -- J ---------------------------------------------------------------
    def test_j_sl_and_tp_same_bar_resolves_conservatively(self):
        bars = mk_bars(SETUP + [
            (1.1000, 1.1045, 1.0985, 1.1020),   # touches TP 1.1020 AND SL 1.0995
        ])
        res = engine().run(bars, TrendStrategy(sl_pips=5, tp_pips=20))
        self.assertEqual(res.n_trades, 1)
        tr = res.trades[0]
        self.assertEqual(tr.exit_reason, "SL")          # worst compatible outcome
        self.assertAlmostEqual(tr.exit_exec, 1.0995, places=15)
        self.assertGreaterEqual(res.ambiguous_bars, 1)
        self.assertGreaterEqual(res.ambiguous_trades, 1)
        self.assertEqual(res.ambiguity_event_counts.get("SL_AND_TP_SAME_BAR"), 1)
        self.assertEqual(tr.ambiguous_events, 1)

    # -- K ---------------------------------------------------------------
    def test_k_be_trigger_and_old_sl_same_bar_conservative(self):
        bars = mk_bars(SETUP + [
            # entry open 1.1000 -> exec 1.1001; SL 1.0995 (risk 6 pips);
            # BE trigger (Bid) = 1.1007 <= high 1.1025; low 1.0985 <= old SL.
            (1.1000, 1.1025, 1.0985, 1.1015),
        ])
        be = BreakevenConfig(enabled=True, trigger_r=1.0, offset_pips=1.0)
        res = engine(CostModel(spread_pips=1.0), breakeven=be).run(
            bars, TrendStrategy(sl_pips=5, tp_pips=30))
        self.assertEqual(res.n_trades, 1)
        tr = res.trades[0]
        self.assertEqual(tr.exit_reason, "SL")
        self.assertAlmostEqual(tr.exit_exec, 1.0995, places=15)  # old SL, full loss
        self.assertGreaterEqual(res.ambiguity_event_counts.get(
            "BE_TRIGGER_AND_SL_SAME_BAR", 0), 1)
        self.assertEqual(res.ambiguous_trades, 1)

    # -- L ---------------------------------------------------------------
    def test_l_be_trigger_and_be_stop_same_bar_no_hidden_favorable_exit(self):
        bars = mk_bars(SETUP + [
            # entry exec 1.1001; trigger 1.1007 <= high 1.1025; BE stop 1.1002
            # touched (low 1.0998) but old SL 1.0995 NOT touched.
            (1.1000, 1.1025, 1.0998, 1.1020),
            (1.1015, 1.1016, 1.1000, 1.1001),   # BE stop 1.1002 touched -> BE exit
        ])
        be = BreakevenConfig(enabled=True, trigger_r=1.0, offset_pips=1.0)
        res = engine(CostModel(spread_pips=1.0), breakeven=be).run(
            bars, TrendStrategy(sl_pips=5, tp_pips=30))
        self.assertEqual(res.n_trades, 1)
        tr = res.trades[0]
        self.assertEqual(tr.exit_ts, bars[3].dt)          # NOT exited in arming bar
        self.assertEqual(tr.exit_reason, "BE")
        self.assertAlmostEqual(tr.exit_exec, 1.1002, places=15)
        self.assertGreaterEqual(res.ambiguity_event_counts.get(
            "BE_TRIGGER_AND_BE_STOP_SAME_BAR", 0), 1)

    # -- M ---------------------------------------------------------------
    def test_m_forming_h1_never_seen_and_later_mutations_change_nothing(self):
        def build(mutate_last_hour):
            hours = ([1.1000, 1.1002, 1.1004, 1.1006],          # hour 09:xx
                     [1.1010, 1.1012, 1.1014, 1.1016],          # hour 10:xx
                     [1.1020, 1.1022, 1.1024, 1.1026])          # hour 11:xx
            bars = []
            for hi, hr in enumerate(hours):
                for mi, c in enumerate(hr):
                    if mutate_last_hour and hi == 2:
                        c = 9.99 - 0.001 * mi
                    dt = datetime(2023, 1, 2, 9 + hi, 15 * mi)
                    bars.append(Bar(dt, c, c + 0.0002, c - 0.0002, c))
            return bars

        class Recorder(Strategy):
            def __init__(self):
                self.records = []

            def on_bar(self, ctx):
                for t in range(len(ctx.h1)):
                    # closed H1 only: bucket close time <= decision time
                    if ctx.h1.close_dt(t) > ctx.decision_ts:
                        raise CausalityError("forming H1 exposed")
                h1_closes = tuple(ctx.h1.close(t) for t in range(len(ctx.h1)))
                m15_closes = tuple(ctx.m15.close(t) for t in range(len(ctx.m15)))
                self.records.append((ctx.decision_ts, h1_closes, m15_closes))
                return None

        strat_a = Recorder()
        engine().run(build(False), strat_a)
        strat_b = Recorder()
        engine().run(build(True), strat_b)
        cutoff = datetime(2023, 1, 2, 11, 0)
        # decisions before the mutated hour are strictly identical
        early_a = [r for r in strat_a.records if r[0] < cutoff]
        early_b = [r for r in strat_b.records if r[0] < cutoff]
        self.assertEqual(early_a, early_b)
        self.assertGreaterEqual(len(early_a), 8)
        # at the 10:00 decision exactly ONE closed H1 bucket is visible
        rec_1000 = next(r for r in strat_a.records
                        if r[0] == datetime(2023, 1, 2, 10, 0))
        self.assertEqual(len(rec_1000[1]), 1)
        # and no decision ever sees more buckets than elapsed hours
        self.assertTrue(all(len(r[1]) <= (r[0].hour - 9 + 1)
                            for r in strat_a.records))

    # -- N ---------------------------------------------------------------
    def test_n_deterministic_bit_for_bit(self):
        bars = mk_bars(SETUP + [
            (1.1000, 1.1035, 1.0994, 1.1020),   # trade 1: TP 1.1020
            (1.0995, 1.1010, 1.0990, 1.1008),   # trade 2 opens (open 1.0995)
            (1.1008, 1.1040, 1.1007, 1.1035),   # trade 2: TP hit
            (1.1035, 1.1036, 1.0990, 1.0995),   # trade 3 opens (open 1.1035)
            (1.0995, 1.1000, 1.0980, 1.0985),   # trade 3: SL hit
        ])
        costs = CostModel(spread_pips=1.5, commission_per_lot_per_side=3.5,
                          adverse_slippage_pips=0.7)
        be = BreakevenConfig(enabled=True, trigger_r=1.0, offset_pips=1.0)
        strat = TrendStrategy(sl_pips=10, tp_pips=25)
        r1 = engine(costs, breakeven=be).run(bars, TrendStrategy(sl_pips=10, tp_pips=25))
        r2 = engine(costs, breakeven=be).run(bars, strat)
        self.assertEqual(r1.n_trades, 3)
        self.assertEqual(r1, r2)  # dataclass equality: every field, every float

    # -- O ---------------------------------------------------------------
    def test_o_pnl_decomposition_identity(self):
        bars = mk_bars(SETUP + [
            (1.1000, 1.1035, 1.0994, 1.1020),
            (1.0995, 1.1010, 1.0990, 1.1008),
            (1.1008, 1.1040, 1.1007, 1.1035),
        ])
        costs = CostModel(spread_pips=1.5, commission_per_lot_per_side=3.5,
                          adverse_slippage_pips=0.7)
        res = engine(costs).run(bars, TrendStrategy(sl_pips=10, tp_pips=25))
        self.assertGreaterEqual(res.n_trades, 1)
        for tr in res.trades:
            # identity holds exactly by construction
            self.assertEqual(tr.gross_pnl - tr.spread_cost - tr.slippage_cost
                             - tr.commission_cost, tr.net_pnl)
            # and matches the raw execution-price computation (commission is a
            # cash cost, never a price cost)
            exec_net = tr.direction * (tr.exit_exec - tr.entry_exec) / PIP * 10.0
            exec_net = exec_net * tr.lots - tr.commission_cost
            self.assertAlmostEqual(exec_net, tr.net_pnl, places=6)
        # totals respect the same identity
        self.assertEqual(res.total_gross_pnl - res.total_spread_cost
                         - res.total_slippage_cost - res.total_commission_cost,
                         res.total_net_pnl)
        self.assertAlmostEqual(res.final_balance, res.initial_balance
                               + res.total_net_pnl, places=9)


if __name__ == "__main__":
    unittest.main(verbosity=2)
