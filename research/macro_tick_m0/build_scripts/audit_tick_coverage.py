#!/usr/bin/env python3
"""MACRO_TICK_M0: audit per-month coverage of the EURUSD tick store.

Records first/last tick timestamp and tick count per month so that events
falling inside source-data gaps are identifiable (mission §9).
Output: ../data/tick_store_month_coverage.csv
"""
from __future__ import annotations

import csv
import os

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.normpath(os.path.join(HERE, ".."))
TICKS = r"E:\ResearchData\botTrading\ticks\parquet\EURUSD"
OUT = os.path.join(BASE, "data", "tick_store_month_coverage.csv")


def main():
    rows = []
    for year in sorted(os.listdir(TICKS)):
        ydir = os.path.join(TICKS, year)
        if not os.path.isdir(ydir):
            continue
        for month in sorted(os.listdir(ydir)):
            p = os.path.join(ydir, month, "ticks.parquet")
            if not os.path.exists(p):
                continue
            df = pd.read_parquet(p, columns=["timestamp_utc"])
            ts = pd.DatetimeIndex(df["timestamp_utc"])
            rows.append({
                "month": f"{year[5:]}-{month[6:]}",  # year=YYYY month=MM
                "n_ticks": len(ts),
                "first_tick_utc": "" if len(ts) == 0 else ts.min().isoformat(),
                "last_tick_utc": "" if len(ts) == 0 else ts.max().isoformat(),
                "days_covered": len({t.date() for t in ts}) if len(ts) else 0,
            })
    rows.sort(key=lambda r: r["month"])
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    bad = [r for r in rows if r["n_ticks"] == 0]
    print("months:", len(rows), "empty:", len(bad))
    for r in rows:
        if r["days_covered"] < 20:
            print("LOW COVERAGE:", r["month"], r["n_ticks"], "ticks,",
                  r["days_covered"], "days,", r["first_tick_utc"][:10],
                  "->", r["last_tick_utc"][:10])


if __name__ == "__main__":
    main()
