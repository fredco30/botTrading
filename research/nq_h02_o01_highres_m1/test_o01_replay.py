#!/usr/bin/env python3
"""Execution tests for the O01 BBO replay (mission section 7)."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent))
import o01_replay as R  # noqa: E402

DAY = "2021-06-01"


class FakeW:
    def __init__(self, ts, bid, ask):
        self.ts = np.array(ts, dtype=np.int64)
        self.bid = np.array(bid, float)
        self.ask = np.array(ask, float)

    def first_idx_ge(self, ts):
        k = np.searchsorted(self.ts, int(pd.Timestamp(ts).value), side="left")
        return k if k < len(self.ts) else None


def sec(hhmmss):
    return int(pd.Timestamp(f"{DAY} {hhmmss}", tz="UTC").value)


def base(**kw):
    d = {"SIDE": "LONG", "ORDER_ACTIVATION_TIMESTAMP": f"{DAY} 13:35:00+00:00",
         "MODELED_FINAL_EXIT_TIMESTAMP": f"{DAY} 15:00:00+00:00",
         "MODELED_ENTRY": 100.5, "MODELED_FINAL_EXIT": 101.0,
         "level": 100.0, "MODELED_EXIT_REASON": "TRAIL"}
    d.update(kw)
    return d


def test_long_market_entry_at_ask():
    w = FakeW([sec("13:35:00")], bid=[100.2], ask=[100.5])
    r = R.replay_o01(base(), w, "L1_BASE", "NORMAL")
    assert abs(r["entry_exec"] - 100.5) < 1e-9


def test_short_market_entry_at_bid():
    w = FakeW([sec("13:35:00")], bid=[100.5], ask=[100.8])
    r = R.replay_o01(base(SIDE="SHORT"), w, "L1_BASE", "NORMAL")
    assert abs(r["entry_exec"] - 100.5) < 1e-9


def test_long_stop_executes_at_bid():
    t = base(level=100.0, MODELED_EXIT_REASON="STOP")
    # stop live since entry; at 15:00 the bid dips to 99.9 <= 100 -> STOP at bid
    w = FakeW([sec("13:35:00"), sec("15:00:01")],
              bid=[100.2, 99.9], ask=[100.5, 100.2])
    r = R.replay_o01(t, w, "L1_BASE", "NORMAL")
    assert r["exit_exec"] == 99.9
    assert abs(r["gross"] - (99.9 - 100.5)) < 1e-9


def test_short_stop_executes_at_ask():
    t = base(SIDE="SHORT", level=101.0, MODELED_EXIT_REASON="STOP")
    w = FakeW([sec("13:35:00"), sec("15:00:01")],
              bid=[100.5, 101.05], ask=[100.8, 101.3])
    r = R.replay_o01(t, w, "L1_BASE", "NORMAL")
    assert r["exit_exec"] == 101.3                  # ask >= 101 stop, market buy
    assert abs(r["gross"] - (100.5 - 101.3)) < 1e-9


def test_chandelier_exit_close_based():
    t = base(MODELED_EXIT_REASON="TRAIL")
    # trail decision at exit bar END (15:05): first sample >= 15:05
    w = FakeW([sec("13:35:00"), sec("15:05:01")],
              bid=[100.2, 100.7], ask=[100.5, 101.0])
    r = R.replay_o01(t, w, "L1_BASE", "NORMAL")
    assert abs(r["exit_exec"] - 100.7) < 1e-9       # BID for long exit
    assert "STOP" not in r["flag"]


def test_eod_exit():
    t = base(MODELED_EXIT_REASON="EOD")
    w = FakeW([sec("13:35:00"), sec("20:55:01")],
              bid=[100.2, 102.0], ask=[100.5, 102.3])
    r = R.replay_o01(t, w, "L1_BASE", "NORMAL")
    assert abs(r["exit_exec"] - 102.0) < 1e-9


def test_no_pre_activation_fill():
    # an attractive quote BEFORE activation must never fill
    w = FakeW([sec("13:30:00"), sec("13:36:00")],
              bid=[100.0, 100.2], ask=[100.1, 100.5])
    r = R.replay_o01(base(), w, "L1_BASE", "NORMAL")
    assert abs(r["entry_exec"] - 100.5) < 1e-9      # uses the 13:36 sample


def test_slippage_direction():
    w = FakeW([sec("13:35:00"), sec("15:05:01")],
              bid=[100.2, 100.7], ask=[100.5, 101.0])
    rb = R.replay_o01(base(), w, "L1_BASE", "NORMAL")
    rc = R.replay_o01(base(), w, "L1_CONSERVATIVE", "NORMAL")
    rs = R.replay_o01(base(), w, "L1_STRESS", "NORMAL")
    # long: entry pays +tick, exit receives -tick -> net drops 2 ticks/scenario
    assert abs(rc["net"] - (rb["net"] - 0.5)) < 1e-9
    assert abs(rs["net"] - (rb["net"] - 1.0)) < 1e-9


def test_spread_decomposition_and_fees():
    w = FakeW([sec("13:35:00"), sec("15:05:01")],
              bid=[100.2, 100.7], ask=[100.5, 101.0])
    r = R.replay_o01(base(), w, "L1_BASE", "NORMAL")
    # long: ask-in 100.5, bid-out 100.7 -> gross 0.2 (spread observed 0.3/0.3)
    assert abs(r["gross"] - 0.2) < 1e-9
    assert r["fees"] == 1.0
    assert abs(r["entry_spread"] - 0.3) < 1e-9


def test_point_tick_usd():
    assert abs(12.75 * 20 - (12.75 / 0.25) * 5) < 1e-9


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
