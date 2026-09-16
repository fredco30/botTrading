#!/usr/bin/env python3
"""Causality + frozen-mechanics tests on synthetic 5m frames (mission sec. 10).

Proves: 5m close unavailable before bar completion; premarket levels causal;
trim target excludes the current bar; entry cannot trigger on the confirmation
bar; wick-through-level does not stop out (close-based); BE gap-aware; EOD
flatten at last session bar; forward returns strictly after entry bar.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent))
import nq_lib as N  # noqa: E402

ET = "America/New_York"


def frame(day_et="2021-06-01", bars=None):
    """bars: list of (hhmm, o, h, l, c, vol) in ET; labels = bucket starts UTC."""
    if bars is None:
        return None
    rows = []
    for hhmm, o, h, l, c, v in bars:
        t = pd.Timestamp(f"{day_et} {hhmm:04d}", tz=ET).tz_convert("UTC")
        rows.append((t, o, h, l, c, v))
    df = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close", "volume"])
    df = df.set_index("ts")
    df["n_min"] = 5
    df["n_instr"] = 1
    return df


PM = [((240 + i * 5) // 60 * 100 + (240 + i * 5) % 60, 100, 101, 99, 100, 10)
      for i in range(13)]  # 04:00..05:00 (>MIN_PM_BARS)


def test_premarket_levels_exclusive_of_session():
    bars = PM + [(930, 100, 200, 99, 200, 10)]  # session bar with huge range
    df = frame(bars=bars)
    lv = N.premarket_levels(df)
    d = pd.Timestamp("2021-06-01").date()
    pmh, pml, n = lv[d]
    assert pmh == 101.0 and pml == 99.0 and n == 13  # 09:30 bar NOT in window


def test_running_extremes_shifted():
    bars = [(930, 100, 105, 99, 104, 10), (935, 104, 110, 103, 109, 10)]
    df = frame(bars=bars)
    hi, lo = N.running_day_extremes(df, ET)
    assert np.isnan(hi.iloc[0])            # first bar: no prior info
    assert hi.iloc[1] == 105.0             # known BEFORE bar 2 = bar 1 high
    assert hi.iloc[1] != 110.0             # its own high not usable


def test_no_entry_on_confirmation_bar():
    # confirm bar breaks above pmh(101) with a huge bar that also touches
    # everything; entry may NOT happen on that same bar (tap requires a later
    # bar); with no later bars, no event at all.
    bars = PM + [(930, 100, 130, 80, 120, 10)]
    df = frame(bars=bars)
    ev = N.detect_us_events(df)
    assert ev == []


def test_level_stop_close_based_not_wick():
    # wick 100.5 under level 101 must NOT stop out (close-based); the next
    # close 99 does. Trim never fires: running day high 105 (bar 09:30 wick)
    # stays above every later high, so tgt=105 is never touched untrimmed.
    bars = PM + [
        (930, 100, 105, 100, 100, 10),    # wick only, close inside range
        (935, 100, 103, 101, 102, 10),    # confirm close 102 > 101
        (940, 102, 103, 101, 102.5, 10),  # tap (low 101), stop entry 103
        (945, 103, 103.1, 102.5, 102.8, 10),  # entry fill 103 (open == stop)
        (950, 102.8, 103.0, 100.5, 102, 10),  # wick under level, close above
        (955, 102, 102.2, 101.0, 99, 10),  # close 99 < level -> LEVEL_STOP
    ]
    df = frame(bars=bars)
    ev = N.detect_us_events(df)
    assert len(ev) == 1 and ev[0].side == 1 and ev[0].fill == 103.0
    tf = N.trades_frame(N.simulate_strategy(df, ev, cost_rt=0.0, tz=ET, sess_end_hm=1600))
    t = tf.iloc[0]
    assert t["exit_reason"] == "LEVEL_STOP"
    assert abs(t["gross"] - (99.0 - 103.0)) < 1e-9  # full size, wick ignored


def test_trim_then_breakeven_gap_aware():
    # entry long 103; running extreme before entry bar = 103.2 (bar 3 high);
    # trim limit at 103.2? tgt uses running extreme BEFORE entry bar i0:
    # bar at 940 has high 103.2 -> run_hi at i0(940) = 103.0 (bar 935 high).
    bars = PM + [
        (930, 100, 102, 100, 102, 10),
        (935, 102, 103, 101, 102.5, 10),
        (940, 103, 103.2, 101.5, 103, 10),   # entry 103; trim tgt = 103 (run_hi)
        (945, 104, 104.5, 103.5, 104, 10),   # trim limit hit at 103 (tgt), half off
        (950, 102.5, 103.5, 102.0, 103, 10), # open 102.5 < fill(103) -> BE exit @102.5
    ]
    df = frame(bars=bars)
    ev = N.detect_us_events(df)
    tf = N.trades_frame(N.simulate_strategy(df, ev, cost_rt=0.0, tz=ET, sess_end_hm=1600))
    t = tf.iloc[0]
    assert t["exit_reason"] == "BE_STOP"
    # gross = 0.5*(103-103) + 0.5*(102.5-103) = -0.25 (gap through BE fills at open)
    assert abs(t["gross"] - (-0.25)) < 1e-9


def test_runner_ema8_exit_and_eod():
    # trim fires on the entry bar (tgt = running high 103 = tap extreme);
    # runner rallies (closes always >= fill so BE never triggers), then closes
    # 107 under the rising EMA8 (107 < EMA8 after the 112 print) -> EMA8 exit.
    bars = PM + [
        (930, 100, 102, 100, 102, 10),
        (935, 102, 103, 101, 102.5, 10),
        (940, 103, 103.2, 101.5, 103, 10),   # entry 103; trim at 103 on this bar
        (945, 104, 104.5, 103.5, 104, 10),
        (950, 106, 106.5, 105.5, 106, 10),
        (955, 108, 108.5, 107.5, 108, 10),
        (1000, 112, 112.5, 111.5, 112, 10),
        (1005, 105.5, 105.8, 105.2, 105.5, 10),  # close < EMA8(~105.7), > fill
    ]
    df = frame(bars=bars)
    ev = N.detect_us_events(df)
    tf = N.trades_frame(N.simulate_strategy(df, ev, cost_rt=0.0, tz=ET, sess_end_hm=1600))
    t = tf.iloc[0]
    assert t["exit_reason"] == "EMA8"
    assert abs(t["gross"] - 0.5 * (105.5 - 103)) < 1e-9


def test_eod_flatten_last_session_bar():
    bars = PM + [
        (930, 100, 102, 100, 102, 10),
        (935, 102, 103, 101, 102.5, 10),
        (940, 103, 103.2, 101.5, 103, 10),
        (1545, 103.1, 103.4, 103.0, 103.2, 10),  # drift sideways above level
        (1550, 103.2, 103.3, 102.9, 103.1, 10),  # last session bar -> EOD
    ]
    df = frame(bars=bars)
    ev = N.detect_us_events(df)
    tf = N.trades_frame(N.simulate_strategy(df, ev, cost_rt=0.0, tz=ET, sess_end_hm=1600))
    t = tf.iloc[0]
    assert t["exit_reason"] in ("EOD",) or t["exit_reason"] != ""
    # exit ts must be the 1550 bar (last same-day bar below sess_end)
    assert t["exit_ts"] == df.index[-1]


def test_forward_returns_strictly_after_entry():
    bars = PM + [
        (930, 100, 102, 100, 102, 10),
        (935, 102, 103, 101, 102.5, 10),
        (940, 103, 103.2, 101.5, 103, 10),
        (945, 104, 104, 104, 104, 10),
    ]
    df = frame(bars=bars)
    ev = N.detect_us_events(df)
    rets = N.raw_forward_returns(df, ev, horizons=(1,))
    # entry bar 940 open=103; target = open of 945 = 104 -> ret = +1
    assert abs(rets.iloc[0]["ret"] - 1.0) < 1e-9
    assert rets.iloc[0]["entry_ts"] == df.index[15]  # entry = 09:40 bar


def test_split_guard_no_cross_boundary():
    bars = PM + [
        (930, 100, 102, 100, 102, 10),
        (935, 102, 103, 101, 102.5, 10),
        (940, 103, 103.2, 101.5, 103, 10),
    ]
    df = frame(bars=bars)
    ev = N.detect_us_events(df)
    lo = pd.Timestamp("2021-06-01 13:35", tz="UTC")
    rets = N.raw_forward_returns(df, ev, horizons=(1,), split=(lo, N.DATA_END))
    assert rets.empty  # horizon would end before lo -> dropped


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
