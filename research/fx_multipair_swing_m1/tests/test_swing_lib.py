#!/usr/bin/env python3
"""Synthetic tests for swing_lib: bar aggregation, replay fill model,
causality conventions, window guards. No real data needed except for the
(parquet-backed) window-guard test, which uses no sealed pair."""
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))

import swing_lib as S
NS = S.NS


def test_bars_from_5m_synthetic():
    # 2 hours of 5m bars -> H1 bars; verify OHLC aggregation + close labels
    t0 = int(pd.Timestamp("2012-03-05 00:00", tz="UTC").value)
    n = 24
    ts = t0 + np.arange(n) * 5 * 60 * NS
    px = 1.0 + 0.0001 * np.arange(n)          # steadily rising 1 pip/5m
    d5 = {"ts": ts, "open": px, "high": px + 0.00005, "low": px - 0.00005,
          "close": px + 0.00004}
    b = S.bars_from_5m(d5, 60)
    assert len(b["close"]) == 2, len(b["close"])
    # first H1: opens at px[0], closes at px[11] + 4e-4 offset, high = px[11]+5e-5
    assert b["open"][0] == px[0]
    assert b["close"][0] == px[11] + 0.00004
    assert b["high"][0] == px[11] + 0.00005
    assert b["low"][0] == px[0] - 0.00005
    assert b["close_time"][0] == t0 + 3600 * NS
    assert b["close_time"][1] == t0 + 7200 * NS
    # D1 aggregation of the same 2 hours -> one bar closing at midnight
    d = S.bars_from_5m(d5, 1440)
    assert len(d["close"]) == 1
    assert d["close_time"][0] == t0 + 86400 * NS
    assert d["close"][0] == px[-1] + 0.00004
    print("PASS bars_from_5m_synthetic")


def test_replay_fill_model_synthetic():
    # Craft a 5m frame where a long hits target and a short hits stop.
    t0 = int(pd.Timestamp("2012-03-05 00:00", tz="UTC").value)
    m5 = 5 * 60 * NS
    # 60 bars; long decision at t0 (bar 0), entry at bar 1 open
    px = np.full(60, 1.20000)
    ts = t0 + np.arange(60) * m5
    o = px.copy()
    # bar 2-3: rally; bar 3 high reaches entry+10 pips (target 10 pips)
    o[3] = 1.20000
    h = np.full(60, 1.20000); h[3] = 1.20250   # pierces short stop trigger + long tgt
    l = np.full(60, 1.20000)
    c = px.copy()
    d5 = {"ts": ts, "open": o, "high": h, "low": l, "close": c}
    real_build = S.build_discovery_bars
    S.build_discovery_bars = lambda sym: {"5m_" + k: d5[k] for k in
                                          ("ts", "open", "high", "low", "close")}
    try:
        dec = {"ts": np.array([t0]), "side": np.array([1])}
        tr = S.bar_replay("EURUSD", None, dec, np.array([20.0]),
                          np.array([10.0]), 24)
        t = tr[0]
        spread = 0.6e-4
        assert t["entry"] == 1.2 + spread, t["entry"]
        assert t["reason"] == "TARGET", t
        assert abs(t["net_pips"] - 10.0) < 1e-9 and abs(t["r"] - 0.5) < 1e-9
        # short: stop at entry+20 pips (ask) triggers when bid high >=
        # entry+20-spread = 1.20194; bar-3 high 1.2025 pierces it; fill at
        # the stop level (no gap: bar open 1.2 below trigger) -> -20.0 net
        dec = {"ts": np.array([t0]), "side": np.array([-1])}
        tr = S.bar_replay("EURUSD", None, dec, np.array([20.0]),
                          np.array([10.0]), 24)
        t = tr[0]
        assert t["reason"] == "STOP", t
        assert abs(t["net_pips"] + 20.0) < 1e-6, t["net_pips"]
        # time exit for a flat frame (short pays spread at exit)
        h2 = np.full(60, 1.20000)
        d5["high"] = h2
        S.build_discovery_bars = lambda sym: {"5m_" + k: d5[k] for k in
                                              ("ts", "open", "high", "low", "close")}
        dec = {"ts": np.array([t0]), "side": np.array([-1])}
        tr = S.bar_replay("EURUSD", None, dec, np.array([20.0]),
                          np.array([10.0]), 1)
        t = tr[0]
        assert t["reason"] == "TIME" and abs(t["net_pips"] + 0.6) < 1e-9, t
    finally:
        S.build_discovery_bars = real_build
    print("PASS replay_fill_model_synthetic")


def test_replay_nonoverlap():
    t0 = int(pd.Timestamp("2012-03-05 00:00", tz="UTC").value)
    m5 = 5 * 60 * NS
    n = 200
    ts = t0 + np.arange(n) * m5
    o = np.full(n, 1.2); h = np.full(n, 1.2)
    l = np.full(n, 1.2); c = np.full(n, 1.2)
    d5 = {"ts": ts, "open": o, "high": h, "low": l, "close": c}
    real_build = S.build_discovery_bars
    S.build_discovery_bars = lambda sym: {"5m_" + k: d5[k] for k in
                                          ("ts", "open", "high", "low", "close")}
    try:
        # decisions every 15 min for 10 hours, hold 2h -> must collapse to
        # non-overlapping trades (5 trades)
        dec_ts = t0 + np.arange(40) * 15 * 60 * NS
        dec = {"ts": dec_ts, "side": np.ones(40, dtype=int)}
        tr = S.bar_replay("EURUSD", None, dec, np.array([20.0] * 40),
                          np.array([10.0] * 40), 2)
        assert len(tr) == 5, len(tr)   # 10h / 2h hold
        for a, b in zip(tr, tr[1:]):
            assert b["decision_ts"] >= a["exit_ts"]
    finally:
        S.build_discovery_bars = real_build
    print("PASS replay_nonoverlap")


def test_window_guards():
    a, b = S.window_ns("2020-01-01", "2021-01-01")
    try:
        S.load_5m("EURUSD", a, b, "TEST")
        raise AssertionError("2019+ load not refused")
    except PermissionError:
        pass
    a, b = S.window_ns("2015-01-01", "2016-01-01")
    try:
        S.load_5m("USDJPY", a, b, "TEST")
        raise AssertionError("USDJPY load without sentinel not refused")
    except PermissionError:
        pass
    assert not os.path.exists(S.STAGE_B_SENTINEL)
    try:
        S.load_eurusd_2018h2()
        raise AssertionError("EURUSD 2018H2 load without sentinel not refused")
    except PermissionError:
        pass
    print("PASS window_guards")


def test_discovery_data_real():
    """Real discovery data sanity: coverage, gaps, bars counts."""
    for sym in S.DISCOVERY_PAIRS:
        bars = S.build_discovery_bars(sym)
        h1ct = bars["H1_close_time"]
        a, b = S.discovery_window_ns()
        assert h1ct[0] >= a + 3600 * NS and h1ct[-1] <= b
        assert np.all(np.diff(h1ct) > 0)
        # weekends absent: max gap <= 5 days (weekend + holiday)
        gaps = np.diff(bars["D1_close_time"]) / (86400 * NS)
        assert gaps.max() <= 6, f"{sym} D1 gap {gaps.max()} days"
        # no zeros/negatives
        for k in ("open", "high", "low", "close"):
            assert np.all(bars[f"H1_{k}"] > 0)
        print(f"PASS discovery_data_real {sym}: "
              f"H1={len(bars['H1_close'])} H4={len(bars['H4_close'])} "
              f"D1={len(bars['D1_close'])}")


if __name__ == "__main__":
    test_bars_from_5m_synthetic()
    test_replay_fill_model_synthetic()
    test_replay_nonoverlap()
    test_window_guards()
    test_discovery_data_real()
    print("ALL TESTS PASS")
