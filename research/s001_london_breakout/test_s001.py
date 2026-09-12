"""S001 minimal synthetic tests (stdlib unittest only).

Run:  python -m unittest discover -s research/s001_london_breakout -p "test_*.py" -v
   or python test_s001.py

Covers: GMT/BST conversion, Asian-range window, signal-after-close,
entry = next open, LONG/SHORT, opposite-side stop, 1.5R target,
stop-first, gap-through-stop, favorable-gap cap, 12:00 time exit,
costs 2/4, invalid risk, one-trade-per-day, <2019 boundary.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
import pandas as pd

import s001_lib as S

BASE = 1.5000


def mkday(d, rows, upto="13:00"):
    """Build a UTC-indexed 5m OHLC frame for London date d.

    rows: {"HH:MM" (London): (o, h, l, c)}; missing slots are flat at BASE.
    """
    start = pd.Timestamp(f"{d} 00:00", tz="Europe/London").tz_convert("UTC")
    end = pd.Timestamp(f"{d} {upto}", tz="Europe/London").tz_convert("UTC")
    idx = pd.date_range(start, end, freq="5min", inclusive="left")
    idx.name = None
    n = len(idx)
    o = np.full(n, BASE)
    h = np.full(n, BASE)
    l = np.full(n, BASE)
    c = np.full(n, BASE)
    ldn = idx.tz_convert("Europe/London")
    pos = {t.strftime("%H:%M"): i for i, t in enumerate(ldn)}
    for hm, vals in rows.items():
        i = pos[hm]
        o[i], h[i], l[i], c[i] = vals
    return pd.DataFrame({"open": o, "high": h, "low": l, "close": c}, index=idx)


SIGNAL_LONG = {"09:00": (BASE, BASE + 20e-4, BASE, BASE + 10e-4)}
# 09:00 bar closes at 1.5010 > asian_high (BASE) -> LONG signal.
# Entry 09:05 open BASE+10e-4, stop BASE, risk 10 pips, target BASE+25e-4.

SIGNAL_SHORT = {"09:00": (BASE, BASE, BASE - 20e-4, BASE - 10e-4)}


def only(trades):
    assert len(trades) == 1, f"expected 1 trade, got {len(trades)}: {trades}"
    return trades[0]


class TestS001(unittest.TestCase):
    def test_london_gmt_bst(self):
        bars = mkday("2010-06-15", {})  # BST: London 00:00 = 23:00 UTC (D-1)
        day_ord, time_min = S._day_frame(bars)
        self.assertEqual(set(np.unique(day_ord)), {np.datetime64("2010-06-15", "D")})
        ldn = bars.index.tz_convert("Europe/London")
        self.assertEqual(ldn[0].strftime("%H:%M"), "00:00")
        self.assertEqual(time_min[0], 0)

        bars = mkday("2010-01-15", {})  # GMT: London 00:00 = 00:00 UTC
        ldn = bars.index.tz_convert("Europe/London")
        self.assertEqual(ldn[0].strftime("%H:%M"), "00:00")
        self.assertEqual(bars.index[0], pd.Timestamp("2010-01-15 00:00", tz="UTC"))

        # DST start 2010-03-28 01:00 UTC: 00:55 UTC -> 00:55 GMT, 01:00 UTC -> 02:00 BST
        idx = pd.date_range("2010-03-28 00:50", periods=6, freq="5min", tz="UTC")
        idx.name = None
        df = pd.DataFrame({"open": 1, "high": 1, "low": 1, "close": 1}, index=idx)
        _, time_min = S._day_frame(df)
        self.assertEqual(list(map(int, time_min)), [50, 55, 120, 125, 130, 135])

    def test_asian_range_window_only(self):
        # spike AFTER 07:00 London (07:30) must NOT extend the range
        t = only(S.run_backtest(mkday("2010-01-15", {
            "07:30": (BASE, BASE + 100e-4, BASE, BASE), **SIGNAL_LONG,
            "09:05": (BASE + 10e-4, BASE + 15e-4, BASE + 8e-4, BASE + 12e-4),
            "09:10": (BASE + 12e-4, BASE + 25e-4, BASE + 11e-4, BASE + 20e-4),
        }))[0])
        self.assertEqual(t["direction"], "LONG")
        self.assertEqual(t["stop"], BASE)
        self.assertEqual(t["reason"], S.R_TARGET)

        # spike at 06:55 (inside) DOES extend the range -> no breakout, no trade
        trades, _ = S.run_backtest(mkday("2010-01-15", {
            "06:55": (BASE, BASE + 100e-4, BASE, BASE), **SIGNAL_LONG}))
        self.assertEqual(trades, [])

        # spike exactly AT 07:00 (exclusive bound) must NOT extend the range
        t = only(S.run_backtest(mkday("2010-01-15", {
            "07:00": (BASE, BASE + 100e-4, BASE, BASE), **SIGNAL_LONG,
            "09:05": (BASE + 10e-4, BASE + 25e-4, BASE + 8e-4, BASE + 20e-4),
        }))[0])
        self.assertEqual(t["stop"], BASE)
        self.assertEqual(t["reason"], S.R_TARGET)

        # spike at 00:00 (inclusive bound) DOES extend the range
        trades, _ = S.run_backtest(mkday("2010-01-15", {
            "00:00": (BASE, BASE + 100e-4, BASE, BASE), **SIGNAL_LONG}))
        self.assertEqual(trades, [])

    def test_signal_after_close_entry_next_open(self):
        # 08:30 spikes above the high intrabar but CLOSES back inside: no signal.
        # First close-above is 09:00; entry must be 09:05 open, not 08:35.
        bars = mkday("2010-01-15", {
            "08:30": (BASE, BASE + 15e-4, BASE - 2e-4, BASE), **SIGNAL_LONG,
            "09:05": (BASE + 10e-4, BASE + 15e-4, BASE + 8e-4, BASE + 12e-4),
            "09:10": (BASE + 12e-4, BASE + 25e-4, BASE + 11e-4, BASE + 20e-4),
        })
        t = only(S.run_backtest(bars)[0])
        self.assertEqual(t["entry_ts"], pd.Timestamp("2010-01-15 09:05", tz="UTC"))
        self.assertEqual(t["entry"], BASE + 10e-4)

    def test_long_target_1_5r(self):
        bars = mkday("2010-01-15", {**SIGNAL_LONG,
            "09:05": (BASE + 10e-4, BASE + 15e-4, BASE + 8e-4, BASE + 12e-4),
            "09:10": (BASE + 12e-4, BASE + 25e-4, BASE + 11e-4, BASE + 20e-4),
        })
        t = only(S.run_backtest(bars)[0])
        entry, stop = BASE + 10e-4, BASE
        self.assertEqual(t["direction"], "LONG")
        self.assertEqual(t["stop"], stop)  # opposite side of the range
        self.assertAlmostEqual(t["target"], entry + 1.5 * (entry - stop), places=9)
        self.assertEqual(t["reason"], S.R_TARGET)
        self.assertAlmostEqual(t["exit"], entry + 15e-4, places=9)
        self.assertAlmostEqual(t["gross_pips"], 15.0, places=6)
        self.assertAlmostEqual(t["net_normal"], 13.0, places=6)
        self.assertAlmostEqual(t["net_stress"], 11.0, places=6)
        self.assertAlmostEqual(t["risk_pips"], 10.0, places=6)

    def test_short_target_1_5r(self):
        bars = mkday("2010-01-15", {**SIGNAL_SHORT,
            "09:05": (BASE - 10e-4, BASE - 8e-4, BASE - 15e-4, BASE - 12e-4),
            "09:10": (BASE - 12e-4, BASE - 11e-4, BASE - 25e-4, BASE - 20e-4),
        })
        t = only(S.run_backtest(bars)[0])
        entry, stop = BASE - 10e-4, BASE
        self.assertEqual(t["direction"], "SHORT")
        self.assertEqual(t["stop"], stop)  # opposite side of the range
        self.assertAlmostEqual(t["target"], entry - 1.5 * (stop - entry), places=9)
        self.assertEqual(t["reason"], S.R_TARGET)
        self.assertAlmostEqual(t["exit"], entry - 15e-4, places=9)
        self.assertAlmostEqual(t["gross_pips"], 15.0, places=6)

    def test_entry_bar_touches(self):
        # target touched on the entry bar itself
        bars = mkday("2010-01-15", {**SIGNAL_LONG,
            "09:05": (BASE + 10e-4, BASE + 30e-4, BASE + 5e-4, BASE + 12e-4),
        })
        t = only(S.run_backtest(bars)[0])
        self.assertEqual(t["reason"], S.R_TARGET)
        self.assertAlmostEqual(t["gross_pips"], 15.0, places=6)

    def test_stop_first_same_bar(self):
        bars = mkday("2010-01-15", {**SIGNAL_LONG,
            "09:05": (BASE + 10e-4, BASE + 30e-4, BASE - 5e-4, BASE + 12e-4),
            "09:10": (BASE + 12e-4, BASE + 40e-4, BASE, BASE + 20e-4),
        })
        t = only(S.run_backtest(bars)[0])
        self.assertEqual(t["reason"], S.R_STOP_FIRST)
        self.assertEqual(t["exit"], BASE)  # conservative: stop, never the target
        self.assertAlmostEqual(t["gross_pips"], -10.0, places=6)

    def test_gap_through_stop(self):
        bars = mkday("2010-01-15", {**SIGNAL_LONG,
            "09:05": (BASE + 10e-4, BASE + 15e-4, BASE + 8e-4, BASE + 12e-4),
            "09:10": (BASE - 5e-4, BASE, BASE - 20e-4, BASE - 15e-4),
        })
        t = only(S.run_backtest(bars)[0])
        self.assertEqual(t["reason"], S.R_STOP_GAP)
        self.assertEqual(t["exit"], BASE - 5e-4)  # exit at the unfavorable open
        self.assertAlmostEqual(t["gross_pips"], -15.0, places=6)  # worse than stop

    def test_gap_target_capped(self):
        bars = mkday("2010-01-15", {**SIGNAL_LONG,
            "09:05": (BASE + 10e-4, BASE + 15e-4, BASE + 8e-4, BASE + 12e-4),
            "09:10": (BASE + 40e-4, BASE + 45e-4, BASE + 35e-4, BASE + 40e-4),
        })
        t = only(S.run_backtest(bars)[0])
        self.assertEqual(t["reason"], S.R_TARGET)
        self.assertAlmostEqual(t["exit"], BASE + 25e-4, places=9)  # never better
        self.assertAlmostEqual(t["gross_pips"], 15.0, places=6)

    def test_time_exit_1200(self):
        # asian low set at 02:00 (1.4980); flat bars never touch stop (1.4980)
        # nor target (1.5055) -> exit at the 12:00 open
        bars = mkday("2010-01-15", {**SIGNAL_LONG,
            "02:00": (BASE, BASE, BASE - 20e-4, BASE),
            "09:05": (BASE + 10e-4, BASE + 14e-4, BASE + 5e-4, BASE + 8e-4),
            "11:55": (BASE + 8e-4, BASE + 12e-4, BASE + 2e-4, BASE + 5e-4),
            "12:00": (BASE + 6e-4, BASE + 9e-4, BASE + 1e-4, BASE + 4e-4),
        })
        t = only(S.run_backtest(bars)[0])
        self.assertEqual(t["reason"], S.R_TIME_1200)
        self.assertEqual(t["exit_ts"], pd.Timestamp("2010-01-15 12:00", tz="UTC"))
        self.assertEqual(t["exit"], BASE + 6e-4)
        self.assertAlmostEqual(t["gross_pips"], -4.0, places=6)

    def test_risk_invalid_no_trade(self):
        # long breakout but next bar opens BELOW the asian low -> risk <= 0
        bars = mkday("2010-01-15", {**SIGNAL_LONG,
            "09:05": (BASE - 10e-4, BASE, BASE - 20e-4, BASE - 5e-4),
        })
        trades, _ = S.run_backtest(bars)
        self.assertEqual(trades, [])

    def test_one_trade_per_day(self):
        bars = mkday("2010-01-15", {**SIGNAL_LONG,
            "09:05": (BASE + 10e-4, BASE + 15e-4, BASE + 8e-4, BASE + 12e-4),
            "09:10": (BASE + 12e-4, BASE + 25e-4, BASE + 11e-4, BASE + 20e-4),
            "10:00": (BASE + 20e-4, BASE + 20e-4, BASE - 20e-4, BASE - 15e-4),
        })
        trades, _ = S.run_backtest(bars)
        self.assertEqual(len(trades), 1)  # second (short) breakout ignored

    def test_no_breakout_no_trade(self):
        trades, _ = S.run_backtest(mkday("2010-01-15", {}))
        self.assertEqual(trades, [])
        # signal window only: a breakout at 07:30 must NOT signal
        trades, _ = S.run_backtest(mkday("2010-01-15", {
            "07:30": (BASE, BASE + 20e-4, BASE, BASE + 10e-4)}))
        self.assertEqual(trades, [])
        # a breakout at 11:00 (excluded bound) must NOT signal
        trades, _ = S.run_backtest(mkday("2010-01-15", {
            "11:00": (BASE, BASE + 20e-4, BASE, BASE + 10e-4)}))
        self.assertEqual(trades, [])
        # a breakout at 10:55 (last allowed open) MUST signal, entry at 11:00
        bars = mkday("2010-01-15", {
            "10:55": (BASE, BASE + 20e-4, BASE, BASE + 10e-4),
            "11:00": (BASE + 10e-4, BASE + 15e-4, BASE + 8e-4, BASE + 12e-4),
            "11:05": (BASE + 12e-4, BASE + 25e-4, BASE + 11e-4, BASE + 20e-4),
        })
        t = only(S.run_backtest(bars)[0])
        self.assertEqual(t["entry_ts"], pd.Timestamp("2010-01-15 11:00", tz="UTC"))

    def test_dst_summer_end_to_end(self):
        # BST summer: London 09:00 signal bar == 08:00 UTC; entry 08:05 UTC
        bars = mkday("2010-06-15", {**SIGNAL_LONG,
            "09:05": (BASE + 10e-4, BASE + 25e-4, BASE + 8e-4, BASE + 20e-4),
        })
        t = only(S.run_backtest(bars)[0])
        self.assertEqual(t["entry_ts"], pd.Timestamp("2010-06-15 08:05", tz="UTC"))
        self.assertEqual(t["date"], "2010-06-15")

    def test_remove_best_and_costs(self):
        x = [5.0] * 99 + [1000.0]  # N=100 -> drop floor(100*0.01)=1 best
        self.assertAlmostEqual(S.remove_best_1_percent(x), 5.0, places=9)
        self.assertAlmostEqual(S.remove_best_1_percent([3.0, 1.0]), 2.0, places=9)
        self.assertAlmostEqual(10.0 - S.COST_NORMAL, 8.0, places=9)
        self.assertAlmostEqual(10.0 - S.COST_STRESS, 6.0, places=9)

    def test_bootstrap_deterministic(self):
        rng = np.random.default_rng(1)
        x = rng.normal(0, 1, 300)
        self.assertEqual(S.ci95_mean(x, n_boot=100, seed=42),
                         S.ci95_mean(x, n_boot=100, seed=42))

    def test_discovery_loader_boundary(self):
        try:
            import pyarrow  # noqa: F401
        except ImportError:
            self.skipTest("pyarrow unavailable (CI installs numpy/pandas only)")
        parquet = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "..", "..", "data_raw", "parquet", "GBPUSD_5m.parquet")
        bars = S.load_discovery_bars(parquet)
        self.assertGreaterEqual(bars.index.min(), pd.Timestamp("2010-01-01", tz="UTC"))
        self.assertLess(bars.index.max(), pd.Timestamp("2019-01-01", tz="UTC"))
        years = pd.DatetimeIndex(S._day_frame(bars)[0]).year
        self.assertLessEqual(int(years.max()), 2018)
        self.assertGreaterEqual(int(years.min()), 2010)


if __name__ == "__main__":
    unittest.main(verbosity=2)
