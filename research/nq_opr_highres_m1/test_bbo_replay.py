#!/usr/bin/env python3
"""Execution-causality tests for the BBO replay (mission section 28)."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent))
import bbo_replay as B  # noqa: E402
import nq_lib as N  # noqa: E402

ET = "America/New_York"


class FakeW:
    def __init__(self, ts, bid, ask):
        self.ts = np.array(ts, dtype=np.int64)
        self.bid = np.array(bid, float)
        self.ask = np.array(ask, float)

    def first_idx_after(self, ts, inclusive=False):
        k = np.searchsorted(self.ts, int(pd.Timestamp(ts).value),
                            side="left" if inclusive else "right")
        return k if k < len(self.ts) else None


def base_trade(**kw):
    d = {"SIDE": "LONG", "RETEST_TIMESTAMP": "2021-06-01 14:55:00+00:00",
         "ORDER_ACTIVATION_TIMESTAMP": "2021-06-01 15:00:00+00:00",
         "MODELED_FINAL_EXIT_TIMESTAMP": "2021-06-01 15:30:00+00:00",
         "MODELED_ENTRY": 100.9, "MODELED_FINAL_EXIT": 101.0,
         "INITIAL_STOP": 100.7, "TRIM_LEVEL": 101.4, "TRIM_TRIGGERED": False,
         "MODELED_EXIT_REASON": "LEVEL_STOP"}
    d.update(kw)
    return d


def mk_frame():
    ts = pd.date_range("2021-06-01 14:30", periods=30, freq="5min", tz="UTC")
    df = pd.DataFrame({"open": 100.0, "high": 101.0, "low": 99.0,
                       "close": 100.5, "volume": 1}, index=ts)
    return df


def sec(day, hhmmss):
    return int(pd.Timestamp(f"{day} {hhmmss}", tz="UTC").value)


DAY = "2021-06-01"


def test_long_entry_triggers_on_ask():
    # activation 15:00: ask < trigger (100.8) until 15:02 where ask=101.0
    ts = [sec(DAY, "15:00:01"), sec(DAY, "15:01:01"), sec(DAY, "15:02:01")]
    w = FakeW(ts, bid=[100.5, 100.6, 100.8], ask=[100.7, 100.75, 101.0])
    df = mk_frame()
    t = base_trade()
    tap = pd.Timestamp(t["RETEST_TIMESTAMP"])
    df.loc[tap, "high"] = 100.8                     # tap-bar extreme (trigger)
    r = B.replay_trade(t, df, w, "L1_BASE", "NORMAL")
    # trigger = tap high 100.8; first ask >= 100.8 at 15:02 -> entry at ask 101.0
    assert abs(r["entry_exec"] - 101.0) < 1e-9


def test_short_entry_triggers_on_bid():
    t = base_trade(SIDE="SHORT")
    # tap low = trigger: set tap bar low
    df = mk_frame()
    tap = pd.Timestamp(t["RETEST_TIMESTAMP"])
    df.loc[tap, "low"] = 100.2
    ts = [sec(DAY, "15:00:01"), sec(DAY, "15:01:01")]
    w = FakeW(ts, bid=[100.4, 100.1], ask=[100.6, 100.3])
    r = B.replay_trade(t, df, w, "L1_BASE", "NORMAL")
    assert abs(r["entry_exec"] - 100.1) < 1e-9      # first bid <= 100.2


def test_long_market_exit_at_bid():
    t = base_trade()
    df = mk_frame()
    tap = pd.Timestamp(t["RETEST_TIMESTAMP"])
    df.loc[tap, "high"] = 100.8
    ts = [sec(DAY, "15:00:01"), sec(DAY, "15:35:01")]
    w = FakeW(ts, bid=[100.75, 101.25], ask=[101.0, 101.5])
    r = B.replay_trade(t, df, w, "L1_BASE", "NORMAL")
    # exit decision 15:35 (LEVEL_STOP bar end 15:35) -> first sample >= 15:35
    assert abs(r["exit_exec"] - 101.25) < 1e-9      # BID for long exit
    # gross = exit - entry on 1.0; fees 1.0
    assert abs(r["gross"] - (101.25 - 101.0)) < 1e-9
    assert abs(r["net"] - (0.25 - 1.0)) < 1e-9


def test_no_pre_activation_fill():
    # trigger already marketable BEFORE activation: must NOT use pre-activation
    t = base_trade()
    df = mk_frame()
    tap = pd.Timestamp(t["RETEST_TIMESTAMP"])
    df.loc[tap, "high"] = 100.8
    ts = [sec(DAY, "14:59:00"), sec(DAY, "15:02:01")]
    w = FakeW(ts, bid=[100.5, 100.9], ask=[100.9, 101.1])
    r = B.replay_trade(t, df, w, "L1_BASE", "NORMAL")
    assert abs(r["entry_exec"] - 101.1) < 1e-9      # 15:02 sample, not 14:59


def test_trim_queue_uncertain_replays_untrimmed():
    t = base_trade(TRIM_TRIGGERED=True, MODELED_EXIT_REASON="BE_STOP")
    df = mk_frame()
    tap = pd.Timestamp(t["RETEST_TIMESTAMP"])
    df.loc[tap, "high"] = 100.8
    ts = [sec(DAY, "15:00:01"), sec(DAY, "15:05:01"), sec(DAY, "15:35:01")]
    # trim bar = entry bar (15:00-15:05), frozen high >= TRIM_LEVEL 101.4:
    df.loc[pd.Timestamp(t["ORDER_ACTIVATION_TIMESTAMP"]), "high"] = 101.5
    w = FakeW(ts, bid=[100.5, 100.6, 101.0], ask=[101.0, 100.8, 101.3])
    r = B.replay_trade(t, df, w, "L1_BASE", "NORMAL")
    assert "TRIM_QUEUE_UNCERTAIN" in r["ambiguity"]
    # full size market exit at frozen exit -> gross on 1.0 at bid 101.0
    assert abs(r["gross"] - (101.0 - r["entry_exec"])) < 1e-9


def test_trim_fills_when_bid_proven():
    t = base_trade(TRIM_TRIGGERED=True, MODELED_EXIT_REASON="BE_STOP",
                   TRIM_LEVEL=100.9)
    df = mk_frame()
    tap = pd.Timestamp(t["RETEST_TIMESTAMP"])
    df.loc[tap, "high"] = 100.8
    ts = [sec(DAY, "15:00:01"), sec(DAY, "15:02:01"), sec(DAY, "15:35:01")]
    # entry 15:00:01 at ask 100.85 (>= trigger 100.8); trim bar = entry bar:
    # bid reaches 100.9 at 15:02:01 -> passive fill at 100.9
    w = FakeW(ts, bid=[100.6, 100.9, 101.0], ask=[100.85, 101.05, 101.2])
    r = B.replay_trade(t, df, w, "L1_BASE", "NORMAL")
    assert abs(r["trim_exec"] - 100.9) < 1e-9
    exp = 0.5 * (100.9 - 100.85) + 0.5 * (101.0 - 100.85)
    assert abs(r["gross"] - exp) < 1e-9


def test_slippage_scenarios():
    t = base_trade()
    df = mk_frame()
    tap = pd.Timestamp(t["RETEST_TIMESTAMP"])
    df.loc[tap, "high"] = 100.8
    ts = [sec(DAY, "15:00:01"), sec(DAY, "15:35:01")]
    w = FakeW(ts, bid=[100.75, 101.25], ask=[101.0, 101.5])
    rb = B.replay_trade(t, df, w, "L1_BASE", "NORMAL")
    rc = B.replay_trade(t, df, w, "L1_CONSERVATIVE", "NORMAL")
    rs = B.replay_trade(t, df, w, "L1_STRESS", "NORMAL")
    assert abs(rc["net"] - (rb["net"] - 0.5)) < 1e-9   # 2 marketable legs x 1 tick
    assert abs(rs["net"] - (rb["net"] - 1.0)) < 1e-9


def test_fee_tiers():
    t = base_trade()
    df = mk_frame()
    tap = pd.Timestamp(t["RETEST_TIMESTAMP"])
    df.loc[tap, "high"] = 100.8
    ts = [sec(DAY, "15:00:01"), sec(DAY, "15:35:01")]
    w = FakeW(ts, bid=[100.75, 101.25], ask=[101.0, 101.5])
    rn = B.replay_trade(t, df, w, "L1_BASE", "NORMAL")
    rs = B.replay_trade(t, df, w, "L1_BASE", "STRESS")
    assert abs(rs["net"] - rn["net"] - (-1.5)) < 1e-9  # fees 2.5 vs 1.0


def test_point_tick_usd_consistency():
    net_pts = 12.75
    assert abs(net_pts * 20 - (net_pts / 0.25) * 5) < 1e-9


def test_2026_guard():
    df = N.load_5m()
    assert df.index.max() < pd.Timestamp("2026-01-01", tz="UTC")


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
