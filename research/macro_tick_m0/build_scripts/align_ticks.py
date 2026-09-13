#!/usr/bin/env python3
"""MACRO_TICK_M0: event/tick timestamp alignment (mission §8).

For each macro event: find the last tick strictly before the official
release timestamp and the first tick >= it, in the existing EURUSD tick
parquet dataset (E:\\ResearchData\\botTrading\\ticks). Report
PRE_TICK_LAG_MS / POST_TICK_LAG_MS and a validity status:
an event is tick-valid if a first executable tick exists within 5 seconds,
unless the market is legitimately closed (weekend; weekday gaps are
reported as data gaps). NO returns, NO reaction measurement - timestamp
validation only.

Output: ../data/tick_alignment.csv (event_id + alignment columns) and the
merged dataset ../data/macro_events_2010_2018_aligned.csv
"""
from __future__ import annotations

import csv
import os
import sys
from datetime import datetime, timedelta, timezone

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import macro_lib as M  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.normpath(os.path.join(HERE, ".."))
TICKS = r"E:\ResearchData\botTrading\ticks\parquet\EURUSD"
OUT = os.path.join(BASE, "data")

# windows searched around each event; if no tick exists in ±window the
# event is flagged NO_TICKS_IN_WINDOW (data gap) rather than silently OK
PRE_W, POST_W = 600, 600  # seconds


def month_path(ts_utc: datetime):
    ts = ts_utc.astimezone(timezone.utc)
    return os.path.join(TICKS, f"year={ts.year:04d}", f"month={ts.month:02d}",
                        "ticks.parquet")


class MonthCache:
    """Load a month parquet once; events cluster in ~108 distinct months."""

    def __init__(self):
        self._cache: dict[str, pd.DatetimeIndex] = {}

    def index_for(self, ts_utc: datetime) -> pd.DatetimeIndex | None:
        ts = ts_utc.astimezone(timezone.utc)
        key = f"{ts.year:04d}-{ts.month:02d}"
        if key not in self._cache:
            p = month_path(ts)
            if not os.path.exists(p):
                self._cache[key] = pd.DatetimeIndex([])
            else:
                df = pd.read_parquet(p, columns=["timestamp_utc"])
                idx = pd.DatetimeIndex(df["timestamp_utc"]).sort_values()
                self._cache[key] = idx
        return self._cache[key]


def align_event(cache: MonthCache, ts_utc: datetime) -> dict:
    idx = cache.index_for(ts_utc)
    if idx is None or len(idx) == 0:
        return {"tick_alignment_status": "TICK_FILE_MISSING",
                "pre_tick_lag_ms": "", "post_tick_lag_ms": "",
                "pre_tick_ts": "", "post_tick_ts": ""}
    # widen: neighbour tick may sit in the adjacent month file (month
    # boundaries / weekend gaps) - check previous and next month indexes too
    candidates = [idx]
    for delta in (-1, 1):
        nb = ts_utc.astimezone(timezone.utc)
        nb = (nb.replace(day=1) + pd.offsets.MonthBegin(delta)).to_pydatetime()
        j = cache.index_for(nb)
        if j is not None and len(j):
            candidates.append(j)
    parts = [c for c in candidates if len(c)]
    if not parts:
        combined = pd.DatetimeIndex([])
    else:
        combined = parts[0]
        for c in parts[1:]:
            combined = combined.append(c)
        combined = combined.sort_values()
    res = M.find_tick_neighbors(combined, ts_utc,
                                pre_window_s=PRE_W, post_window_s=POST_W)
    pre_lag = res["pre_tick_lag_ms"]
    post_lag = res["post_tick_lag_ms"]
    status = res["status"]
    if status == "OK":
        status = "ALIGNED"
    elif res["post_tick_ts"] is not None and M.is_probable_market_closure(ts_utc):
        status = "MARKET_CLOSED_WEEKEND"
    return {
        "tick_alignment_status": status,
        "pre_tick_lag_ms": "" if pre_lag is None else pre_lag,
        "post_tick_lag_ms": "" if post_lag is None else post_lag,
        "pre_tick_ts": "" if res["pre_tick_ts"] is None
        else res["pre_tick_ts"].isoformat(),
        "post_tick_ts": "" if res["post_tick_ts"] is None
        else res["post_tick_ts"].isoformat(),
    }


def main():
    in_csv = os.path.join(OUT, "macro_events_2010_2018.csv")
    with open(in_csv, encoding="utf-8") as f:
        events = list(csv.DictReader(f))
    cache = MonthCache()
    rows = []
    for e in events:
        ts = datetime.fromisoformat(e["release_timestamp_utc"].replace("Z", "+00:00"))
        a = align_event(cache, ts)
        rows.append({"event_id": e["event_id"], "family": e["family"],
                     "release_timestamp_utc": e["release_timestamp_utc"],
                     "timestamp_grade": e.get("timestamp_grade", ""),
                     **a})
    out_csv = os.path.join(OUT, "tick_alignment.csv")
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    # merge into the main dataset
    by_id = {r["event_id"]: r for r in rows}
    for e in events:
        r = by_id[e["event_id"]]
        e["tick_alignment_status"] = r["tick_alignment_status"]
        e["pre_tick_lag_ms"] = r["pre_tick_lag_ms"]
        e["post_tick_lag_ms"] = r["post_tick_lag_ms"]
    merged = os.path.join(OUT, "macro_events_2010_2018_aligned.csv")
    with open(merged, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(events[0].keys()))
        w.writeheader()
        w.writerows(events)

    from collections import Counter
    print("status counts:", dict(Counter(r["tick_alignment_status"] for r in rows)))
    lags = [int(r["post_tick_lag_ms"]) for r in rows
            if r["post_tick_lag_ms"] != ""]
    if lags:
        print(f"post-tick lag ms: max={max(lags)} median={sorted(lags)[len(lags)//2]}")
    print("wrote", out_csv, "and", merged)


if __name__ == "__main__":
    main()
