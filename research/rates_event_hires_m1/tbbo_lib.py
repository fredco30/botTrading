"""RATES-EVENT-HIRES-M1 core library: event windows, classification, roll guard, validation.

Pure functions only — no network, no filesystem side effects. All timestamps are
UTC. Windows are half-open: [T0 - 5m, T0 + 10m).
"""
from __future__ import annotations

import csv
import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

DATASET = "GLBX.MDP3"
SCHEMA = "tbbo"
SYMBOLS = ("ZF", "ZN")
CONTINUOUS = {"ZF": "ZF.v.0", "ZN": "ZN.v.0"}
WINDOW_BEFORE = timedelta(minutes=5)
WINDOW_AFTER = timedelta(minutes=10)
EVENT_START_CUT = datetime(2010, 6, 7, tzinfo=timezone.utc)
EVENT_END_CUT = datetime(2019, 1, 1, tzinfo=timezone.utc)

# CME Globex was closed for the entire Good Friday 2017-04-14 session.
EXPECTED_CLOSED_DATES = {datetime(2017, 4, 14, tzinfo=timezone.utc).date()}


@dataclass(frozen=True)
class Event:
    event_id: str
    family: str
    t0: datetime

    @property
    def window_start(self) -> datetime:
        return self.t0 - WINDOW_BEFORE

    @property
    def window_end(self) -> datetime:
        return self.t0 + WINDOW_AFTER


@dataclass
class RollMap:
    """Front-contract periods per root symbol, from RATES-DATA-M0 roll_map.csv."""

    periods: dict[str, list[tuple[datetime, datetime, str, str]]] = field(default_factory=dict)

    @classmethod
    def from_csv(cls, path: str) -> "RollMap":
        periods: dict[str, list] = {}
        with open(path) as f:
            for row in csv.DictReader(f):
                d0 = datetime.fromisoformat(row["start_date"] + "T00:00:00+00:00")
                d1 = datetime.fromisoformat(row["end_date"] + "T23:59:59+00:00")
                periods.setdefault(row["symbol"], []).append(
                    (d0, d1, row["raw_symbol"], row["instrument_id"])
                )
        for lst in periods.values():
            lst.sort()
        return cls(periods)

    def resolve(self, symbol: str, ts: datetime) -> tuple[str, str] | None:
        for d0, d1, raw, iid in self.periods.get(symbol, []):
            if d0 <= ts <= d1:
                return raw, iid
        return None

    def roll_invalid(self, symbol: str, start: datetime, end: datetime) -> bool:
        """True if a front-contract switch instant falls inside [start, end).

        Boundaries in the M0 roll map are date-granular; a window is invalid when
        its endpoints resolve to different front contracts.
        """
        a = self.resolve(symbol, start)
        b = self.resolve(symbol, end - timedelta(microseconds=1))
        if a is None or b is None:
            return True
        return a[0] != b[0]


def load_events(csv_path: str) -> list[Event]:
    events = []
    with open(csv_path) as f:
        for row in csv.DictReader(f):
            if row["family"] not in ("NFP", "CPI"):
                continue
            t0 = datetime.fromisoformat(row["release_timestamp_utc"].replace("Z", "+00:00"))
            if EVENT_START_CUT <= t0 < EVENT_END_CUT:
                events.append(Event(row["event_id"], row["family"], t0))
    events.sort(key=lambda e: e.t0)
    return events


def is_expected_closed(event: Event) -> bool:
    return event.t0.date() in EXPECTED_CLOSED_DATES


def classify_zero_window(
    ohlcv_bars_in_window: int, continuous_records: int, raw_records: int
) -> str:
    """Classification per mission spec section 4."""
    if continuous_records == 0 and raw_records > 0:
        return "CONTINUOUS_METADATA_RESOLUTION_ISSUE"
    if ohlcv_bars_in_window > 0:
        return "DATABENTO_TBBO_HISTORICAL_GAP"
    return "CONFIRMED_DATA_GAP"


def sha256_file(path: str, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def validate_records(rows: list[dict], start_ns: int, end_ns: int) -> dict:
    """Validate decoded TBBO rows (dicts with ts_event/ts_recv in ns) for one window."""
    n = len(rows)
    ts = [r["ts_event"] for r in rows]
    monotonic = all(a <= b for a, b in zip(ts, ts[1:]))
    seen = set()
    dupes = 0
    for r in rows:
        key = tuple(sorted(r.items()))
        if key in seen:
            dupes += 1
        seen.add(key)
    in_before = sum(1 for t in ts if start_ns <= t < end_ns)
    return {
        "n_records": n,
        "first_ts_event": min(ts) if ts else None,
        "last_ts_event": max(ts) if ts else None,
        "first_ts_recv": min((r["ts_recv"] for r in rows), default=None),
        "last_ts_recv": max((r["ts_recv"] for r in rows), default=None),
        "monotonic_ts_event": monotonic,
        "duplicate_exact_records": dupes,
        "records_outside_window": n - in_before,
    }


def coverage_horizons(rows: list[dict], t0_ns: int, horizons_s=(1, 2, 5, 10, 30)) -> dict:
    """Fraction of horizons H with >=1 observation in [T0, T0+H] -> per-event booleans."""
    ts = sorted(r["ts_event"] for r in rows)
    import bisect

    out = {}
    for h in horizons_s:
        hi = t0_ns + h * 1_000_000_000
        i = bisect.bisect_left(ts, t0_ns)
        out[h] = i < len(ts) and ts[i] <= hi
    return out
