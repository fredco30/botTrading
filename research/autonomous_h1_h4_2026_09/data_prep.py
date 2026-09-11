#!/usr/bin/env python3
"""Autonomous H1/H4 mission — data preparation.

Builds H1/H4 frames for EURUSD / GBPUSD / USDJPY from M15 CSVs, strictly
windowed to [2010-01-01, 2026-04-09) BEFORE any strategic use.  GBPUSD and
USDJPY repository CSVs contain post-cutoff rows; they are filtered here and
never touched afterwards.  Cached arrays live OUTSIDE the repository.

Sources (all same MT4 export family — IC Markets demo terminal):
  EURUSD : git snapshot 3cd12c3:EURUSD15.csv (ends 2026-04-08 — no OOS rows)
  GBPUSD : repo GBPUSD15.csv    (rows >= 2026-04-09 dropped by filter)
  USDJPY : repo USDJPY15.csv    (rows >= 2026-04-09 dropped by filter)
"""
from __future__ import annotations

import hashlib
import json
import os
import sys

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from h1h4_lib import aggregate, bars_to_frame, load_pair_csv  # noqa: E402

CACHE_DIR = r"C:\Users\Fred\.zcode\tmp\autonomous\h1h4"
REPO = _ROOT


def sha256_path(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


SOURCES = {
    "EURUSD": os.path.join(os.path.dirname(CACHE_DIR), "eurusd15_snapshot.csv"),
    "GBPUSD": os.path.join(REPO, "GBPUSD15.csv"),
    "USDJPY": os.path.join(REPO, "USDJPY15.csv"),
}


def prepare():
    os.makedirs(CACHE_DIR, exist_ok=True)
    manifest = []
    for pair, src in SOURCES.items():
        if not os.path.exists(src):
            raise FileNotFoundError(src)
        bars = load_pair_csv(src)               # strict window filter here
        m15 = bars_to_frame(bars)
        for rule, name in (("1h", "H1"), ("4h", "H4")):
            df = aggregate(m15, rule)
            out = os.path.join(CACHE_DIR, f"{pair}_{name}.parquet")
            df.to_parquet(out)
            manifest.append({
                "SOURCE": src + (" (git snapshot 3cd12c3:EURUSD15.csv)" if pair == "EURUSD" else ""),
                "SYMBOL": pair,
                "TIMEFRAME": name,
                "TIMEZONE": "MT4 server time (unknown offset, consistent across pairs)",
                "BID_OR_MID": "BID (MT4 export)",
                "FIRST_TS": str(df.index[0]),
                "LAST_TS": str(df.index[-1]),
                "ROWS": int(len(df)),
                "SHA256_SOURCE": sha256_path(src),
            })
            print(f"{pair} {name}: {len(df)} rows  {df.index[0]} .. {df.index[-1]}")
    with open(os.path.join(_HERE, "data_manifest.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2)
    print("manifest written")


if __name__ == "__main__":
    prepare()
