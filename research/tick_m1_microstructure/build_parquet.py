#!/usr/bin/env python3
"""TICK-M1 parquet builder: decode raw Dukascopy .bi5 hours into a
month-partitioned parquet dataset.

Reuses the TICK-M0 validated decoder (`research/tick_m0/decode_ticks.py`,
20-byte big-endian records, point=1e5 for EURUSD).

Output layout (under the resolved data root):
  parquet/EURUSD/year=YYYY/month=MM/ticks.parquet
    columns: timestamp_utc (datetime64[ns, UTC]), bid, ask, mid,
             spread_pips, bid_volume, ask_volume
  parquet/EURUSD/_manifest.json   (per-month counts; small, for inspection)

Idempotent: existing partitions are skipped unless --force.
Raw hours that are absent (download incomplete) or marked .missing are
counted and reported per month; decoding failures are listed and excluded.
"""
import argparse
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import date

import numpy as np

import data_root

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(REPO, "research", "tick_m0"))
import decode_ticks as m0  # validated TICK-M0 decoder

import pandas as pd


def month_day_dirs(raw, year, month):
    out = []
    prefix = f"{year:04d}{month:02d}"
    root = raw
    if not os.path.isdir(root):
        return out
    for name in sorted(os.listdir(root)):
        if name.startswith(prefix) and len(name) == 8 and os.path.isdir(os.path.join(root, name)):
            out.append(name)
    return out


def decode_hour(day_dir_name, h, raw):
    """Returns (status, arrays_or_None). status in {ok, empty, missing, absent, corrupt}.
    Reordered fields note: M0 record is (ask, bid, ask_vol, bid_vol) on the wire;
    M0 decoder already maps them to named arrays."""
    day_path = os.path.join(raw, day_dir_name)
    bi5 = os.path.join(day_path, f"{h:02d}h_ticks.bi5")
    if os.path.exists(bi5 + ".missing"):
        return "missing", None
    if not os.path.exists(bi5):
        return "absent", None
    try:
        buf = m0.decompress(bi5)
    except Exception:
        return "corrupt", None
    if len(buf) == 0:
        return "empty", None
    if len(buf) % 20 != 0:
        return "corrupt", None
    try:
        hour_start = pd.Timestamp(f"{day_dir_name[:4]}-{day_dir_name[4:6]}-{day_dir_name[6:8]}T{h:02d}:00:00Z").to_pydatetime()
        t = m0.decode_buf(buf, hour_start, point=1e5, strict=True)
    except Exception:
        return "corrupt", None
    return "ok", t


def decode_month(raw, year, month, workers=8):
    days = month_day_dirs(raw, year, month)
    jobs = [(d, h) for d in days for h in range(24)]
    stats = {"ok": 0, "empty": 0, "missing": 0, "absent": 0, "corrupt": 0, "corrupt_files": []}
    frames = []

    def run(job):
        d, h = job
        return (d, h) + decode_hour(d, h, raw)

    with ThreadPoolExecutor(max_workers=workers) as ex:
        for (d, h, status, t) in ex.map(run, jobs):
            stats[status] = stats.get(status, 0) + 1
            if status == "corrupt":
                stats["corrupt_files"].append(f"{d}/{h:02d}h_ticks.bi5")
            if status == "ok":
                frames.append(t)

    if not frames:
        return None, stats
    arr = {k: np.concatenate([f[k] for f in frames]) for k in frames[0]}
    order = np.argsort(arr["timestamp_ns"], kind="stable")
    for k in arr:
        arr[k] = arr[k][order]
    return arr, stats


def to_partition_df(arr):
    ts = pd.DatetimeIndex(pd.to_datetime(arr["timestamp_ns"], utc=True), name="timestamp_utc")
    bid = arr["bid"]
    ask = arr["ask"]
    return pd.DataFrame({
        "timestamp_utc": ts,
        "bid": bid.astype(np.float64),
        "ask": ask.astype(np.float64),
        "mid": ((bid + ask) / 2.0).astype(np.float64),
        "spread_pips": ((ask - bid) / 1e-4).astype(np.float64),
        "bid_volume": arr["bid_volume"].astype(np.float32),
        "ask_volume": arr["ask_volume"].astype(np.float32),
    }).reset_index(drop=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--symbol", default="EURUSD")
    ap.add_argument("--start", required=True, help="YYYY-MM inclusive, e.g. 2010-01")
    ap.add_argument("--end", required=True, help="YYYY-MM exclusive")
    ap.add_argument("--data-root", default=None)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    root = data_root.resolve_data_root(args.data_root)
    raw = data_root.raw_dir(root, args.symbol)
    pdir = data_root.parquet_dir(root, args.symbol)
    y0, m0_ = (int(x) for x in args.start.split("-"))
    y1, m1_ = (int(x) for x in args.end.split("-"))

    manifest_path = os.path.join(pdir, "_manifest.json")
    manifest = {}
    if os.path.exists(manifest_path) and not args.force:
        with open(manifest_path) as f:
            manifest = json.load(f)

    y, m = y0, m0_
    total_ticks = 0
    while (y, m) < (y1, m1_):
        part_dir = os.path.join(pdir, f"year={y:04d}", f"month={m:02d}")
        part_file = os.path.join(part_dir, "ticks.parquet")
        key = f"{y:04d}-{m:02d}"
        if os.path.exists(part_file) and not args.force and key in manifest:
            print(f"{key}: partition exists, skipped", flush=True)
            total_ticks += manifest[key]["n_ticks"]
        else:
            arr, stats = decode_month(raw, y, m, args.workers)
            os.makedirs(part_dir, exist_ok=True)
            if arr is None:
                manifest[key] = {"n_ticks": 0, **{k: v for k, v in stats.items() if k != "corrupt_files"},
                                 "corrupt_files": stats["corrupt_files"]}
                print(f"{key}: no ticks ({stats})", flush=True)
            else:
                df = to_partition_df(arr)
                df.to_parquet(part_file, compression="zstd", index=False)
                nbytes = os.path.getsize(part_file)
                manifest[key] = {"n_ticks": int(len(df)), "parquet_bytes": int(nbytes),
                                 **{k: v for k, v in stats.items() if k != "corrupt_files"},
                                 "corrupt_files": stats["corrupt_files"]}
                total_ticks += len(df)
                print(f"{key}: {len(df)} ticks, {nbytes/1e6:.1f} MB parquet, "
                      f"raw hours ok={stats['ok']} empty={stats['empty']} "
                      f"missing={stats['missing']} absent={stats['absent']} "
                      f"corrupt={stats['corrupt']}", flush=True)
        m += 1
        if m == 13:
            y, m = y + 1, 1

    os.makedirs(pdir, exist_ok=True)
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)
    print(f"TOTAL_TICKS={total_ticks}", flush=True)


if __name__ == "__main__":
    sys.exit(main())
