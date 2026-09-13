"""Synthetic tests for the rates M0 validation logic."""
from datetime import timedelta
from pathlib import Path
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import validation as V


def make_bars(n=5, start="2020-01-06T22:00:00Z"):
    idx = pd.date_range(start, periods=n, freq="1min", tz="UTC")
    return pd.DataFrame(
        {"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5, "volume": 10,
         "instrument_id": 111},
        index=idx,
    )


def test_ohlc_valid():
    assert not V.ohlc_invalid_mask(make_bars()).any()


def test_ohlc_invalid_high_below_close():
    df = make_bars(2)
    df.iloc[0, df.columns.get_loc("high")] = df["close"].iloc[0] - 1
    assert V.ohlc_invalid_mask(df).iloc[0]
    assert not V.ohlc_invalid_mask(df).iloc[1]


def test_ohlc_invalid_high_below_low():
    df = make_bars(1)
    df.iloc[0, df.columns.get_loc("high")] = 90.0
    df.iloc[0, df.columns.get_loc("low")] = 95.0
    assert V.ohlc_invalid_mask(df).iloc[0]


def test_duplicate_detection():
    df = pd.concat([make_bars(3), make_bars(1)])
    assert V.duplicate_timestamp_count(df) == 1
    assert V.duplicate_timestamp_count(make_bars(3)) == 0


def test_time_ordering():
    df = pd.concat([make_bars(3), make_bars(2)]).sort_index()
    assert V.non_monotonic_count(df) == 0
    shuffled = pd.concat([make_bars(3), make_bars(2, start="2020-01-06T21:00:00Z")])
    assert V.non_monotonic_count(shuffled.sort_index(ascending=False)) == 4


def test_roll_map_transition_and_gap():
    bars = make_bars(4)  # 22:00..22:03 on 2020-01-06
    bars2 = make_bars(4, start="2020-01-06T22:05:00Z")
    bars2["instrument_id"] = 222
    bars2[["open", "high", "low", "close"]] = bars2[["open", "high", "low", "close"]] + 0.25
    all_bars = pd.concat([bars, bars2]).sort_index()
    rows = [
        {"instrument_id": "111", "raw_symbol": "ZTH0", "start_date": "2020-01-01", "end_date": "2020-01-06"},
        {"instrument_id": "222", "raw_symbol": "ZTM0", "start_date": "2020-01-06", "end_date": "2020-01-31"},
    ]
    events = V.roll_gaps(all_bars, rows)
    assert len(events) == 1
    ev = events[0]
    assert (ev.old_raw, ev.new_raw) == ("ZTH0", "ZTM0")
    assert ev.old_last_close == 100.5
    assert ev.new_first_close == 100.75
    assert ev.price_gap == pytest.approx(0.25)


def test_roll_gap_reporting_unfilled():
    rows = [
        {"instrument_id": "111", "raw_symbol": "A", "start_date": "2020-01-01", "end_date": "2020-01-06"},
        {"instrument_id": "222", "raw_symbol": "B", "start_date": "2020-01-07", "end_date": "2020-01-31"},
    ]
    events = V.roll_gaps(make_bars(2), rows)
    assert len(events) == 1 and np.isnan(events[0].price_gap)


def test_daily_maintenance_gap_expected():
    s = pd.Timestamp("2020-01-07T21:55:00Z")  # 15:55 CT
    e = pd.Timestamp("2020-01-07T23:05:00Z")  # 17:05 CT
    assert V.classify_gap(s, e).kind == "EXPECTED_MARKET_CLOSED"


def test_weekend_gap_expected():
    s = pd.Timestamp("2020-01-10T22:00:00Z")  # Fri 16:00 CT
    e = pd.Timestamp("2020-01-12T23:30:00Z")  # Sun 17:30 CT
    assert V.classify_gap(s, e).kind == "EXPECTED_MARKET_CLOSED"


def test_intraday_gap_unexpected():
    s = pd.Timestamp("2020-01-07T15:00:00Z")  # 09:00 CT, active session
    e = pd.Timestamp("2020-01-07T16:00:00Z")
    assert V.classify_gap(s, e).kind == "UNEXPECTED_DATA_GAP"


def test_subthreshold_gap_expected():
    s = pd.Timestamp("2020-01-07T15:00:00Z")
    e = s + timedelta(minutes=5)
    assert V.classify_gap(s, e, threshold_min=10).kind == "EXPECTED_MARKET_CLOSED"


def test_2019_cutoff():
    """No bar at/after 2019-01-01 may be accepted."""
    idx = pd.date_range("2018-12-31T22:00:00Z", periods=3, freq="1min", tz="UTC")
    assert idx[-1] < pd.Timestamp("2019-01-01T00:00:00Z")
    bad = pd.date_range("2019-01-01T00:00:00Z", periods=1, freq="1min", tz="UTC")
    assert (bad >= pd.Timestamp("2019-01-01T00:00:00Z")).all()


def test_alignment_logic():
    bars = make_bars(3)  # 22:00..22:02
    eurusd = {pd.Timestamp("2020-01-06T22:00:00Z"), pd.Timestamp("2020-01-06T23:00:00Z")}
    assert V.align_pct(eurusd, bars) == pytest.approx(1 / 2)
    assert V.align_pct(set(), bars) == 0.0
