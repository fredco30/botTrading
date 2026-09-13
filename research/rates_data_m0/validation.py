"""Validation library for the rates M0 dataset (importable + tested).

Pure functions over pandas DataFrames so they can be unit-tested with
synthetic data. No network access here.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

# CME rates futures (CBOT): Sun 17:00 -> Fri 16:00 America/Chicago,
# daily maintenance break 16:00 -> 17:00 CT.
OPEN_HOUR_CT = 17   # Sunday open
CLOSE_HOUR_CT = 16  # daily close (Fri: weekend start)


def ohlc_invalid_mask(df: pd.DataFrame) -> pd.Series:
    """True where high/low are inconsistent with open/close."""
    hi, lo = df["high"], df["low"]
    body_max = np.maximum(df["open"], df["close"])
    body_min = np.minimum(df["open"], df["close"])
    return (hi < body_max) | (lo > body_min) | (hi < lo)


def duplicate_timestamp_count(df: pd.DataFrame) -> int:
    return int(df.index.duplicated().sum())


def non_monotonic_count(df: pd.DataFrame) -> int:
    ts = df.index.values
    if len(ts) < 2:
        return 0
    return int((np.diff(ts.astype("int64")) < 0).sum())


def missing_days(df: pd.DataFrame, start: str, end: str) -> int:
    """Calendar days in [start, end) with zero bars (for reference only;
    most are expected market closures)."""
    days = pd.date_range(start, end, freq="D", tz="UTC")
    have = set(df.index.tz_convert("UTC").date)
    return int(sum(d.date() not in have for d in days))


def nan_count(df: pd.DataFrame) -> int:
    return int(df[["open", "high", "low", "close", "volume"]].isna().sum().sum())


def zero_volume_count(df: pd.DataFrame) -> int:
    return int((df["volume"] == 0).sum())


@dataclass
class Gap:
    start: pd.Timestamp
    end: pd.Timestamp
    minutes: float
    kind: str  # EXPECTED_MARKET_CLOSED | UNEXPECTED_DATA_GAP


def _to_ct(ts: pd.Timestamp) -> pd.Timestamp:
    return ts.tz_convert("America/Chicago")


def classify_gap(start: pd.Timestamp, end: pd.Timestamp, threshold_min: float = 10.0) -> Gap:
    """Classify an inter-bar gap.

    Expected closures: daily maintenance 16:00-17:00 CT (+/- slack for
    settlement/holiday tails), weekends (Fri close -> Sun open), and full
    holiday days (gap spanning >= 23h). Anything else over the threshold
    during otherwise-active sessions is an unexpected data gap.
    """
    minutes = (end - start).total_seconds() / 60.0
    gap = Gap(start, end, minutes, "UNEXPECTED_DATA_GAP")
    if minutes <= threshold_min:
        gap.kind = "EXPECTED_MARKET_CLOSED"  # sub-threshold; normal micro-gaps
        return gap
    s, e = _to_ct(start), _to_ct(end)
    # full holiday closure (>= 23h but < weekend)
    if 23 * 60 <= minutes < 60 * 60:
        gap.kind = "EXPECTED_MARKET_CLOSED"
        return gap
    # multi-day holiday closures (Christmas / New Year) spanning Fri -> Tue
    if 55 * 60 <= minutes <= 100 * 60:
        gap.kind = "EXPECTED_MARKET_CLOSED"
        return gap
    # weekend: Friday close to Sunday open, allow slack
    if s.dayofweek == 4 and s.hour >= 15 and e.dayofweek in (0, 6) and minutes >= 60 * 60:
        gap.kind = "EXPECTED_MARKET_CLOSED"
        return gap
    # daily maintenance 16:00-17:00 CT (or Friday into weekend handled above)
    if s.hour >= 15 and e.hour <= 18 and minutes <= 3 * 60:
        gap.kind = "EXPECTED_MARKET_CLOSED"
        return gap
    # holiday early close / late reopen (half-day sessions around holidays):
    # gap of 3-23h starting at/after the 12:00 CT (18:00 UTC) early close
    if 3 * 60 <= minutes < 23 * 60 and s.hour >= 18:
        gap.kind = "EXPECTED_MARKET_CLOSED"
        return gap
    # thin overnight session: rates futures trade but rarely print between
    # ~17:00 CT and ~07:00 CT (22:00-12:00 UTC). A missing 1m bar means no
    # trades occurred, which is normal there — not a data gap.
    su = start.tz_convert("UTC")
    eu = end.tz_convert("UTC")
    if minutes <= 8 * 60 and (su.hour >= 22 or su.hour < 12) and (eu.hour >= 22 or eu.hour < 13):
        gap.kind = "EXPECTED_NO_TRADES"
        return gap
    return gap


def unexpected_gaps(df: pd.DataFrame, threshold_min: float = 10.0) -> list[Gap]:
    idx = df.index
    out = []
    for prev, cur in zip(idx[:-1], idx[1:]):
        delta = (cur - prev).total_seconds() / 60.0
        if delta > threshold_min:
            g = classify_gap(prev, cur, threshold_min)
            if g.kind == "UNEXPECTED_DATA_GAP":
                out.append(g)
    return out


def all_gaps(df: pd.DataFrame, threshold_min: float = 10.0) -> list[Gap]:
    idx = df.index
    out = []
    for prev, cur in zip(idx[:-1], idx[1:]):
        delta = (cur - prev).total_seconds() / 60.0
        if delta > threshold_min:
            out.append(classify_gap(prev, cur, threshold_min))
    return out


@dataclass
class RollEvent:
    old_raw: str
    new_raw: str
    old_last_ts: pd.Timestamp | None = None
    new_first_ts: pd.Timestamp | None = None
    old_last_close: float = np.nan
    new_first_close: float = np.nan
    price_gap: float = np.nan


def roll_gaps(bars: pd.DataFrame, roll_map_rows: list[dict]) -> list[RollEvent]:
    """Price gap at each contract switch for one symbol.

    bars: DataFrame indexed by ts_event with columns incl. close and
    instrument_id. roll_map_rows: roll_map.csv rows for this symbol, in order.
    """
    events = []
    for i in range(1, len(roll_map_rows)):
        old_row, new_row = roll_map_rows[i - 1], roll_map_rows[i]
        ev = RollEvent(old_raw=old_row["raw_symbol"], new_raw=new_row["raw_symbol"])
        old_bars = bars[bars["instrument_id"] == int(old_row["instrument_id"])]
        new_bars = bars[bars["instrument_id"] == int(new_row["instrument_id"])]
        if len(old_bars):
            ev.old_last_ts = old_bars.index[-1]
            ev.old_last_close = float(old_bars["close"].iloc[-1])
        if len(new_bars):
            ev.new_first_ts = new_bars.index[0]
            ev.new_first_close = float(new_bars["close"].iloc[0])
        if np.isfinite(ev.old_last_close) and np.isfinite(ev.new_first_close):
            ev.price_gap = ev.new_first_close - ev.old_last_close
        events.append(ev)
    return events


def align_pct(eurusd_minutes: set[pd.Timestamp], bars: pd.DataFrame) -> float:
    """Fraction of EURUSD M1 timestamps matched to a Treasury bar on the
    same UTC minute."""
    if not eurusd_minutes:
        return 0.0
    treas = pd.DatetimeIndex(bars.index)
    return float(treas.isin(eurusd_minutes).sum() / len(treas)) if False else float(
        len(eurusd_minutes.intersection(set(treas))) / len(eurusd_minutes)
    )
