"""MACRO_TICK_M0 library: causal macro event database primitives.

Scope (mission): event timestamp handling, ALFRED vintage causality checks,
event/tick timestamp alignment. NO strategy logic, NO returns, NO PnL.
"""
from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")

DISCOVERY_START = date(2010, 1, 1)   # inclusive
DISCOVERY_END = date(2019, 1, 1)     # exclusive

MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5,
    "june": 6, "july": 7, "august": 8, "september": 9, "october": 10,
    "november": 11, "december": 12,
}

_REF_RE = re.compile(
    r"(?:for\s+)?(january|february|march|april|may|june|july|august|september|"
    r"october|november|december)\s+(\d{4})", re.I)


def et_to_utc(d: date, hhmm: str) -> datetime:
    """Convert a wall-clock ET time on date d to an aware UTC datetime.

    Uses zoneinfo with real DST rules - no hard-coded -5/-4 offsets.
    """
    hh, mm = int(hhmm[:2]), int(hhmm[3:5])
    local = datetime(d.year, d.month, d.day, hh, mm, tzinfo=ET)
    return local.astimezone(UTC)


def utc_to_et(ts: datetime) -> datetime:
    if ts.tzinfo is None:
        raise ValueError("naive datetime")
    return ts.astimezone(ET)


def parse_schedule_time(text: str) -> str:
    """'08:30 AM' -> '08:30' (24h). Raises on anything else."""
    m = re.fullmatch(r"(\d{2}):(\d{2}) (AM|PM)", text.strip())
    if not m:
        raise ValueError(f"unexpected schedule time {text!r}")
    hh, mm, ap = int(m.group(1)), int(m.group(2)), m.group(3)
    if ap == "PM" and hh != 12:
        hh += 12
    if ap == "AM" and hh == 12:
        hh = 0
    return f"{hh:02d}:{mm:02d}"


def reference_period_from_label(label: str) -> str | None:
    """'Employment Situation for December 2015' -> '2015-12'
    'December 2015 Employment Situation' -> '2015-12'."""
    m = _REF_RE.search(label or "")
    if not m:
        return None
    return f"{int(m.group(2)):04d}-{MONTHS[m.group(1).lower()]:02d}"


def prev_month(yyyymm: str) -> str:
    y, m = int(yyyymm[:4]), int(yyyymm[5:7])
    y, m = (y - 1, 12) if m == 1 else (y, m - 1)
    return f"{y:04d}-{m:02d}"


def shift_month(yyyymm: str, k: int) -> str:
    y, m = int(yyyymm[:4]), int(yyyymm[5:7])
    t = y * 12 + (m - 1) + k
    return f"{t // 12:04d}-{t % 12 + 1:02d}"


def in_discovery_range(ts_utc: datetime) -> bool:
    d = utc_to_et(ts_utc).date()
    return DISCOVERY_START <= d < DISCOVERY_END


def dedupe_and_sort(events: list[dict]) -> list[dict]:
    """Reject duplicate event_ids, return events ordered by UTC timestamp."""
    seen: set[str] = set()
    dups: list[str] = []
    for e in events:
        if e["event_id"] in seen:
            dups.append(e["event_id"])
        seen.add(e["event_id"])
    if dups:
        raise ValueError(f"duplicate event_ids: {dups}")
    return sorted(events, key=lambda e: e["release_timestamp_utc"])


def assert_no_2019_plus(events: list[dict]) -> None:
    for e in events:
        if not in_discovery_range(datetime.fromisoformat(e["release_timestamp_utc"])):
            raise ValueError(f"event outside discovery range: {e['event_id']}")


def assert_value_causality(event: dict) -> None:
    """VALUE_AVAILABLE_TIME must be >= official release timestamp."""
    ts = datetime.fromisoformat(event["release_timestamp_utc"])
    vat = event.get("value_available_time_utc")
    if vat is None:
        return
    vat_dt = datetime.fromisoformat(vat)
    if vat_dt < ts:
        raise ValueError(
            f"value available before release for {event['event_id']}: "
            f"{vat} < {ts}")


def vintage_semantics_note(series: str) -> dict:
    """Document how ALFRED vintages map to release events (mission §7).

    ALFRED realtime/vintage dates for PAYEMS/CPIAUCSL/CPILFESL equal the BLS
    release dates; values in vintage D became public intraday on date D
    (08:30 ET for BLS releases), so DATE_ONLY precision is the maximum
    ALFRED can prove. First-print = vintage(release_date) at the reference
    month observation date.
    """
    return {
        "value_time_precision": "DATE_ONLY",
        "note": (
            "ALFRED vintage (realtime_start) date D for this series equals the "
            "BLS release date; values in vintage D were first public on date D "
            "at the official release time. Intraday proof beyond the official "
            "release time is not possible from daily vintages."),
        "series": series,
    }


def find_tick_neighbors(
    tick_ts, ts: datetime, pre_window_s: int = 60, post_window_s: int = 60
) -> dict:
    """Timestamp-only alignment of an event against a sorted tick index.

    tick_ts: monotonically increasing pandas DatetimeIndex (tz-aware UTC).
    Returns last tick strictly before ts and first tick >= ts, with lags.
    """
    import pandas as pd  # local import: tests may pass synthetic indexes

    if len(tick_ts) == 0:
        return {"status": "NO_TICKS_IN_WINDOW", "pre_tick_ts": None,
                "post_tick_ts": None, "pre_tick_lag_ms": None,
                "post_tick_lag_ms": None}
    if ts.tzinfo is None:
        raise ValueError("event timestamp must be tz-aware")
    ts = ts.astimezone(tick_ts.tz if tick_ts.tz is not None else UTC)
    lo = ts - timedelta(seconds=pre_window_s)
    hi = ts + timedelta(seconds=post_window_s)
    left = tick_ts.searchsorted(lo, side="left")
    right = tick_ts.searchsorted(hi, side="right")
    window = tick_ts[left:right]
    if len(window) == 0:
        return {"status": "NO_TICKS_IN_WINDOW", "pre_tick_ts": None,
                "post_tick_ts": None, "pre_tick_lag_ms": None,
                "post_tick_lag_ms": None}
    idx = tick_ts.searchsorted(ts, side="left")  # first tick >= ts
    pre_ts = tick_ts[idx - 1] if idx > 0 else None
    post_ts = tick_ts[idx] if idx < len(tick_ts) else None
    pre_lag = int((ts - pre_ts).total_seconds() * 1000) if pre_ts is not None else None
    post_lag = int((post_ts - ts).total_seconds() * 1000) if post_ts is not None else None
    status = "OK"
    if post_ts is None or (post_ts - ts) > timedelta(seconds=5):
        status = "NO_TICK_WITHIN_5S"
    if pre_ts is None or (ts - pre_ts) > timedelta(seconds=60):
        status = "NO_TICK_WITHIN_60S_BEFORE" if status == "OK" else status + "+PRE_GAP"
    return {"status": status, "pre_tick_ts": pre_ts, "post_tick_ts": post_ts,
            "pre_tick_lag_ms": pre_lag, "post_tick_lag_ms": post_lag}


def is_probable_market_closure(ts_utc: datetime) -> bool:
    """Weekend check in ET. Holiday calendars are NOT modeled; any weekday
    gap is reported as a data gap, not silently excused."""
    wd = utc_to_et(ts_utc).weekday()
    return wd >= 5


def parse_fomc_release_line(raw: str | None) -> tuple[str, str] | None:
    """Extract (hhmm, tz_label) from an official 'For release at ...' line."""
    if not raw:
        return None
    m = re.search(
        r"for release at\s+(\d{1,2}):(\d{2})\s*([ap])\.?m\.?\s*(E[SD]T)",
        raw, re.I)
    if not m:
        return None
    hh, mm, ap, tz = int(m.group(1)), int(m.group(2)), m.group(3).lower(), m.group(4).upper()
    if ap == "p" and hh != 12:
        hh += 12
    if ap == "a" and hh == 12:
        hh = 0
    return f"{hh:02d}:{mm:02d}", tz


def tz_label_matches_date(tz_label: str, d: date) -> bool:
    """EST/EDT page label must agree with zoneinfo DST for the date."""
    want = "EST" if not _is_dst(d) else "EDT"
    return tz_label.upper() == want


def _is_dst(d: date) -> bool:
    return datetime(d.year, d.month, d.day, 12, tzinfo=ET).dst() != timedelta(0)


def norm_num(tok: str) -> float:
    """'0'->0, '1/4'->0.25, '1-1/2'->1.5, '2\\u20111/4'->2.25 (Fed NB-hyphen)."""
    tok = tok.replace("\u2011", "-")
    if "/" in tok:
        whole_s, frac_s = tok.split("/")
        if "-" in whole_s:
            whole, num = whole_s.split("-")
            return float(whole) + float(num) / float(frac_s)
        return float(whole_s) / float(frac_s)
    return float(tok)


def fomc_rate_chain(scheduled_events: list[dict]) -> list[dict]:
    """Fill target_before/target_after/rate_change_bp chronologically.

    Each scheduled event must carry target_ranges_in_text (extracted from the
    statement page). The prevailing 'after' range is the extracted range of
    that meeting; 'before' is the previous meeting's 'after'. Meetings with
    no extractable range keep DATA_UNAVAILABLE (no guessing).
    """
    prev = None
    for e in sorted(scheduled_events, key=lambda x: x["date"]):
        rng = e.get("_extracted_range")
        e.setdefault("target_before", None)
        e.setdefault("target_after", None)
        e.setdefault("rate_change_bp", None)
        if prev is not None:
            e["target_before"] = prev
        if rng is not None:
            e["target_after"] = rng
            if prev is not None:
                e["rate_change_bp"] = int(round((rng[1] - prev[1]) * 100))
            prev = rng
        # rng None -> leave DATA_UNAVAILABLE, do not update prev
    return scheduled_events
