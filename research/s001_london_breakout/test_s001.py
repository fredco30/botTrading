"""S001 minimal synthetic tests (no extra framework).

Run:  python test_s001.py
Covers: GMT/BST conversion, Asian-range window, signal-after-close,
entry = next open, LONG/SHORT, opposite-side stop, 1.5R target,
stop-first, gap-through-stop, favorable-gap cap, 12:00 time exit,
costs 2/4, invalid risk, one-trade-per-day, <2019 boundary.
"""

import sys
import os

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


def test_london_gmt_bst():
    bars = mkday("2010-06-15", {})  # BST: London 00:00 = 23:00 UTC (D-1)
    day_ord, time_min = S._day_frame(bars)
    assert set(np.unique(day_ord)) == {np.datetime64("2010-06-15", "D")}
    ldn = bars.index.tz_convert("Europe/London")
    assert ldn[0].strftime("%H:%M") == "00:00"
    assert time_min[0] == 0

    bars = mkday("2010-01-15", {})  # GMT: London 00:00 = 00:00 UTC
    ldn = bars.index.tz_convert("Europe/London")
    assert ldn[0].strftime("%H:%M") == "00:00"
    assert bars.index[0] == pd.Timestamp("2010-01-15 00:00", tz="UTC")

    # DST start 2010-03-28 01:00 UTC: 00:55 UTC -> 00:55 GMT, 01:05 UTC -> 02:05 BST
    idx = pd.date_range("2010-03-28 00:50", periods=6, freq="5min", tz="UTC")
    idx.name = None
    df = pd.DataFrame({"open": 1, "high": 1, "low": 1, "close": 1}, index=idx)
    _, time_min = S._day_frame(df)
    assert list(time_min) == [50, 55, 120, 125, 130, 135]


def test_asian_range_window_only():
    # spike AFTER 07:00 London (07:30) must NOT extend the range
    t = only(S.run_backtest(mkday("2010-01-15", {
        "07:30": (BASE, BASE + 100e-4, BASE, BASE), **SIGNAL_LONG,
        "09:05": (BASE + 10e-4, BASE + 15e-4, BASE + 8e-4, BASE + 12e-4),
        "09:10": (BASE + 12e-4, BASE + 25e-4, BASE + 11e-4, BASE + 20e-4),
    }))[0])
    assert t["direction"] == "LONG" and t["stop"] == BASE
    assert t["reason"] == S.R_TARGET

    # spike at 06:55 (inside) DOES extend the range -> no breakout, no trade
    trades, _ = S.run_backtest(mkday("2010-01-15", {
        "06:55": (BASE, BASE + 100e-4, BASE, BASE), **SIGNAL_LONG}))
    assert trades == []

    # spike exactly AT 07:00 (exclusive bound) must NOT extend the range
    t = only(S.run_backtest(mkday("2010-01-15", {
        "07:00": (BASE, BASE + 100e-4, BASE, BASE), **SIGNAL_LONG,
        "09:05": (BASE + 10e-4, BASE + 25e-4, BASE + 8e-4, BASE + 20e-4),
    }))[0])
    assert t["stop"] == BASE and t["reason"] == S.R_TARGET

    # spike at 00:00 (inclusive bound) DOES extend the range
    trades, _ = S.run_backtest(mkday("2010-01-15", {
        "00:00": (BASE, BASE + 100e-4, BASE, BASE), **SIGNAL_LONG}))
    assert trades == []


def test_signal_after_close_entry_next_open():
    # 08:30 spikes above the high intrabar but CLOSES back inside: no signal.
    # First close-above is 09:00; entry must be 09:05 open, not 08:35.
    bars = mkday("2010-01-15", {
        "08:30": (BASE, BASE + 15e-4, BASE - 2e-4, BASE), **SIGNAL_LONG,
        "09:05": (BASE + 10e-4, BASE + 15e-4, BASE + 8e-4, BASE + 12e-4),
        "09:10": (BASE + 12e-4, BASE + 25e-4, BASE + 11e-4, BASE + 20e-4),
    })
    t = only(S.run_backtest(bars)[0])
    assert t["entry_ts"] == pd.Timestamp("2010-01-15 09:05", tz="UTC")
    assert t["entry"] == BASE + 10e-4


def test_long_target_1_5r():
    bars = mkday("2010-01-15", {**SIGNAL_LONG,
        "09:05": (BASE + 10e-4, BASE + 15e-4, BASE + 8e-4, BASE + 12e-4),
        "09:10": (BASE + 12e-4, BASE + 25e-4, BASE + 11e-4, BASE + 20e-4),
    })
    t = only(S.run_backtest(bars)[0])
    entry, stop = BASE + 10e-4, BASE
    assert t["direction"] == "LONG"
    assert t["stop"] == stop  # opposite side of the range
    assert abs(t["target"] - (entry + 1.5 * (entry - stop))) < 1e-12
    assert t["reason"] == S.R_TARGET and abs(t["exit"] - (entry + 15e-4)) < 1e-9
    assert abs(t["gross_pips"] - 15.0) < 1e-9
    assert abs(t["net_normal"] - 13.0) < 1e-9
    assert abs(t["net_stress"] - 11.0) < 1e-9
    assert abs(t["risk_pips"] - 10.0) < 1e-9


def test_short_target_1_5r():
    bars = mkday("2010-01-15", {**SIGNAL_SHORT,
        "09:05": (BASE - 10e-4, BASE - 8e-4, BASE - 15e-4, BASE - 12e-4),
        "09:10": (BASE - 12e-4, BASE - 11e-4, BASE - 25e-4, BASE - 20e-4),
    })
    t = only(S.run_backtest(bars)[0])
    entry, stop = BASE - 10e-4, BASE
    assert t["direction"] == "SHORT"
    assert t["stop"] == stop  # opposite side of the range
    assert abs(t["target"] - (entry - 1.5 * (stop - entry))) < 1e-12
    assert t["reason"] == S.R_TARGET and abs(t["exit"] - (entry - 15e-4)) < 1e-9
    assert abs(t["gross_pips"] - 15.0) < 1e-9


def test_entry_bar_touches():
    # target touched on the entry bar itself
    bars = mkday("2010-01-15", {**SIGNAL_LONG,
        "09:05": (BASE + 10e-4, BASE + 30e-4, BASE + 5e-4, BASE + 12e-4),
    })
    t = only(S.run_backtest(bars)[0])
    assert t["reason"] == S.R_TARGET and abs(t["gross_pips"] - 15.0) < 1e-9


def test_stop_first_same_bar():
    bars = mkday("2010-01-15", {**SIGNAL_LONG,
        "09:05": (BASE + 10e-4, BASE + 30e-4, BASE - 5e-4, BASE + 12e-4),
        "09:10": (BASE + 12e-4, BASE + 40e-4, BASE, BASE + 20e-4),
    })
    t = only(S.run_backtest(bars)[0])
    assert t["reason"] == S.R_STOP_FIRST
    assert t["exit"] == BASE  # conservative: stop, never the target
    assert abs(t["gross_pips"] + 10.0) < 1e-9


def test_gap_through_stop():
    bars = mkday("2010-01-15", {**SIGNAL_LONG,
        "09:05": (BASE + 10e-4, BASE + 15e-4, BASE + 8e-4, BASE + 12e-4),
        "09:10": (BASE - 5e-4, BASE, BASE - 20e-4, BASE - 15e-4),
    })
    t = only(S.run_backtest(bars)[0])
    assert t["reason"] == S.R_STOP_GAP
    assert t["exit"] == BASE - 5e-4  # exit at the unfavorable open
    assert abs(t["gross_pips"] + 15.0) < 1e-9  # worse than the -10 pip stop


def test_gap_target_capped():
    bars = mkday("2010-01-15", {**SIGNAL_LONG,
        "09:05": (BASE + 10e-4, BASE + 15e-4, BASE + 8e-4, BASE + 12e-4),
        "09:10": (BASE + 40e-4, BASE + 45e-4, BASE + 35e-4, BASE + 40e-4),
    })
    t = only(S.run_backtest(bars)[0])
    assert t["reason"] == S.R_TARGET
    assert abs(t["exit"] - (BASE + 25e-4)) < 1e-9  # credited at target, never better
    assert abs(t["gross_pips"] - 15.0) < 1e-9


def test_time_exit_1200():
    # asian low set at 02:00 (1.4980); flat bars never touch stop (1.4980)
    # nor target (1.5055) -> exit at the 12:00 open
    bars = mkday("2010-01-15", {**SIGNAL_LONG,
        "02:00": (BASE, BASE, BASE - 20e-4, BASE),
        "09:05": (BASE + 10e-4, BASE + 14e-4, BASE + 5e-4, BASE + 8e-4),
        "11:55": (BASE + 8e-4, BASE + 12e-4, BASE + 2e-4, BASE + 5e-4),
        "12:00": (BASE + 6e-4, BASE + 9e-4, BASE + 1e-4, BASE + 4e-4),
    })
    t = only(S.run_backtest(bars)[0])
    assert t["reason"] == S.R_TIME_1200
    assert t["exit_ts"] == pd.Timestamp("2010-01-15 12:00", tz="UTC")
    assert t["exit"] == BASE + 6e-4
    assert abs(t["gross_pips"] + 4.0) < 1e-9


def test_risk_invalid_no_trade():
    # long breakout but next bar opens BELOW the asian low -> risk <= 0
    bars = mkday("2010-01-15", {**SIGNAL_LONG,
        "09:05": (BASE - 10e-4, BASE, BASE - 20e-4, BASE - 5e-4),
    })
    trades, _ = S.run_backtest(bars)
    assert trades == []


def test_one_trade_per_day():
    bars = mkday("2010-01-15", {**SIGNAL_LONG,
        "09:05": (BASE + 10e-4, BASE + 15e-4, BASE + 8e-4, BASE + 12e-4),
        "09:10": (BASE + 12e-4, BASE + 25e-4, BASE + 11e-4, BASE + 20e-4),
        "10:00": (BASE + 20e-4, BASE + 20e-4, BASE - 20e-4, BASE - 15e-4),
    })
    trades, _ = S.run_backtest(bars)
    assert len(trades) == 1  # second (short) breakout ignored


def test_no_breakout_no_trade():
    trades, _ = S.run_backtest(mkday("2010-01-15", {}))
    assert trades == []
    # signal window only: a breakout at 07:30 must NOT signal
    trades, _ = S.run_backtest(mkday("2010-01-15", {
        "07:30": (BASE, BASE + 20e-4, BASE, BASE + 10e-4)}))
    assert trades == []
    # a breakout at 11:00 (excluded bound) must NOT signal
    trades, _ = S.run_backtest(mkday("2010-01-15", {
        "11:00": (BASE, BASE + 20e-4, BASE, BASE + 10e-4)}))
    assert trades == []
    # a breakout at 10:55 (last allowed open) MUST signal, entry at 11:00
    bars = mkday("2010-01-15", {
        "10:55": (BASE, BASE + 20e-4, BASE, BASE + 10e-4),
        "11:00": (BASE + 10e-4, BASE + 15e-4, BASE + 8e-4, BASE + 12e-4),
        "11:05": (BASE + 12e-4, BASE + 25e-4, BASE + 11e-4, BASE + 20e-4),
    })
    t = only(S.run_backtest(bars)[0])
    assert t["entry_ts"] == pd.Timestamp("2010-01-15 11:00", tz="UTC")


def test_dst_summer_end_to_end():
    # BST summer: London 09:00 signal bar == 08:00 UTC; entry 08:05 UTC
    bars = mkday("2010-06-15", {**SIGNAL_LONG,
        "09:05": (BASE + 10e-4, BASE + 25e-4, BASE + 8e-4, BASE + 20e-4),
    })
    t = only(S.run_backtest(bars)[0])
    assert t["entry_ts"] == pd.Timestamp("2010-06-15 08:05", tz="UTC")
    assert t["date"] == "2010-06-15"


def test_remove_best_and_costs():
    x = [5.0] * 99 + [1000.0]  # N=100 -> drop floor(100*0.01)=1 best
    assert abs(S.remove_best_1_percent(x) - 5.0) < 1e-9
    assert abs(S.remove_best_1_percent([3.0, 1.0]) - 2.0) < 1e-9  # k=0 -> mean
    g = 10.0
    assert abs((g - S.COST_NORMAL) - 8.0) < 1e-9
    assert abs((g - S.COST_STRESS) - 6.0) < 1e-9


def test_bootstrap_deterministic():
    rng = np.random.default_rng(1)
    x = rng.normal(0, 1, 300)
    a = S.ci95_mean(x, n_boot=100, seed=42)
    b = S.ci95_mean(x, n_boot=100, seed=42)
    assert a == b


def test_discovery_loader_boundary():
    bars = S.load_discovery_bars(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..",
                     "..", "data_raw", "parquet", "GBPUSD_5m.parquet"))
    assert bars.index.min() >= pd.Timestamp("2010-01-01", tz="UTC")
    assert bars.index.max() < pd.Timestamp("2019-01-01", tz="UTC")
    day_ord, _ = S._day_frame(bars)
    years = pd.DatetimeIndex(day_ord).year
    assert years.max() <= 2018 and years.min() >= 2010


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
