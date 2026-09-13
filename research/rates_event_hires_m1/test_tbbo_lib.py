"""RATES-EVENT-HIRES-M1 synthetic tests — no network, no E: dependency."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from tbbo_lib import (
    Event, RollMap, classify_zero_window, coverage_horizons, is_expected_closed,
    load_events, sha256_file, validate_records,
)

UTC = timezone.utc


def ev(y, m, d, hh=12, mm=30):
    return Event(f"E-{y}{m:02}{d:02}", "NFP", datetime(y, m, d, hh, mm, tzinfo=UTC))


def test_window_construction():
    e = ev(2014, 9, 5)
    assert e.window_start == datetime(2014, 9, 5, 12, 25, tzinfo=UTC)
    assert e.window_end == datetime(2014, 9, 5, 12, 40, tzinfo=UTC)


def test_event_cutoff_2010_06_07_and_2019():
    import csv as _csv
    p = Path(__file__).parent / "_tmp_events.csv"
    rows = [
        ("A", "NFP", "2010-06-07T12:30:00Z"),   # boundary: included
        ("B", "CPI", "2010-06-01T12:30:00Z"),   # before cut: excluded
        ("C", "NFP", "2018-12-07T13:30:00Z"),   # included
        ("D", "NFP", "2019-01-04T13:30:00Z"),   # at/after 2019-01-01: excluded
        ("E", "FOMC", "2014-09-05T12:30:00Z"),  # wrong family: excluded
    ]
    with open(p, "w", newline="") as f:
        w = _csv.writer(f)
        w.writerow(["event_id", "family", "release_timestamp_utc"])
        w.writerows(rows)
    evs = load_events(str(p))
    p.unlink()
    assert [e.event_id for e in evs] == ["A", "C"]


def test_good_friday_exclusion():
    e = ev(2017, 4, 14)
    assert is_expected_closed(e)
    assert not is_expected_closed(ev(2014, 10, 3))


def test_classify_zero_window_matrix():
    assert classify_zero_window(10, 0, 500) == "CONTINUOUS_METADATA_RESOLUTION_ISSUE"
    assert classify_zero_window(10, 0, 0) == "DATABENTO_TBBO_HISTORICAL_GAP"
    assert classify_zero_window(0, 0, 0) == "CONFIRMED_DATA_GAP"


def test_roll_guard_detects_intra_window_roll():
    tmp_path = Path(__file__).parent / "_tmp_test"
    tmp_path.mkdir(exist_ok=True)
    p = tmp_path / "roll_map.csv"
    p.write_text(
        "symbol,instrument_id,raw_symbol,start_date,end_date\n"
        "ZF,1,ZFZ4,2014-09-01,2014-11-30\n"
        "ZF,2,ZFH5,2014-12-01,2015-02-28\n"
    )
    roll = RollMap.from_csv(str(p))
    assert roll.resolve("ZF", datetime(2014, 10, 3, tzinfo=UTC)) == ("ZFZ4", "1")
    # window crossing the 2014-12-01 switch is invalid
    s = datetime(2014, 11, 30, 23, 58, tzinfo=UTC)
    e = datetime(2014, 12, 1, 0, 5, tzinfo=UTC)
    assert roll.roll_invalid("ZF", s, e) is True
    assert roll.roll_invalid("ZF", datetime(2014, 10, 3, 12, 25, tzinfo=UTC),
                             datetime(2014, 10, 3, 12, 40, tzinfo=UTC)) is False
    assert roll.roll_invalid("ZF", datetime(2014, 8, 1, tzinfo=UTC),
                             datetime(2014, 8, 1, 0, 5, tzinfo=UTC)) is True  # unmapped


def test_manifest_idempotency_key_shape():
    from download_tbbo import key_for
    assert key_for(ev(2014, 9, 5), "ZF") == "E-20140905:ZF"


def test_validate_records_flags():
    t0 = datetime(2014, 9, 5, 12, 30, tzinfo=UTC)
    start = int(t0.timestamp()) * 1_000_000_000 - 300 * 1_000_000_000
    end = start + 900 * 1_000_000_000
    good = [
        {"ts_event": start + i * 1_000_000_000, "ts_recv": start + i * 1_000_000_000 + 5,
         "price": 118 + i * 0.01}
        for i in range(5)
    ]
    v = validate_records(good, start, end)
    assert v["n_records"] == 5 and v["monotonic_ts_event"]
    assert v["duplicate_exact_records"] == 0
    assert v["records_outside_window"] == 0

    outside = {"ts_event": start - 1, "ts_recv": start - 1, "price": 1.0}
    dup = dict(good[0])                                  # exact duplicate of good[0]
    ooo = {"ts_event": start, "ts_recv": 0, "price": 9.0}  # jumps back -> non-monotonic
    bad = good + [outside, dup, ooo]
    v2 = validate_records(bad, start, end)
    assert v2["records_outside_window"] == 1
    assert v2["duplicate_exact_records"] == 1
    assert v2["monotonic_ts_event"] is False


def test_coverage_horizons():
    t0 = int(datetime(2014, 9, 5, 12, 30, tzinfo=UTC).timestamp() * 1e9)
    rows = [{"ts_event": t0 + 6 * 1_000_000_000, "ts_recv": 0}]
    c = coverage_horizons(rows, t0, (1, 2, 5, 10, 30))
    assert c == {1: False, 2: False, 5: False, 10: True, 30: True}
    assert coverage_horizons([{"ts_event": t0, "ts_recv": 0}], t0, (1,))[1] is True


def test_sha256_file():
    tmp_path = Path(__file__).parent / "_tmp_test"
    tmp_path.mkdir(exist_ok=True)
    f = tmp_path / "x.bin"
    f.write_bytes(b"databento")
    assert sha256_file(str(f)) == sha256_file(str(f))
    assert len(sha256_file(str(f))) == 64
