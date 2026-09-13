#!/usr/bin/env python3
"""MTF-M1 bar builder: causal M15/H1/H4 MID bars + GAP LIST from the
existing month-partitioned tick parquet (no redownload, no duplication).

Output (under <data_root>/derived/mtf_m1/, i.e. next to the source data,
NOT in the repo):
  gaps.json                 frozen GAP LIST (non-weekend inter-tick gaps > 1h)
  bars_M15.parquet          columns: start_ns, open, high, low, close,
  bars_H1.parquet                    n_ticks, gap_flag
  bars_H4.parquet
  _bars_manifest.json       tick digest + bar counts (cache invalidation)
"""
import argparse
import hashlib
import json
import os
import sys

import numpy as np
import pandas as pd

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(REPO, "research", "tick_m1_microstructure"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import data_root  # noqa: E402  (TICK-M1 resolver: env / --data-root)
import mtf_lib   # noqa: E402


def ticks_digest(pdir, symbol):
    """Digest of the partition manifest: detects source-data changes."""
    mf = os.path.join(pdir, symbol, "_manifest.json")
    with open(mf) as f:
        m = json.load(f)
    blob = json.dumps({k: m[k]["n_ticks"] for k in sorted(m)},
                      sort_keys=True).encode()
    return hashlib.sha256(blob).hexdigest()[:16]


def derived_dir(root):
    d = os.path.join(root, "derived", "mtf_m1")
    os.makedirs(d, exist_ok=True)
    return d


def build(pdir, symbol, ddir, force=False):
    man_path = os.path.join(ddir, "_bars_manifest.json")
    dig = ticks_digest(pdir, symbol)
    if not force and os.path.exists(man_path):
        with open(man_path) as f:
            man = json.load(f)
        if man.get("digest") == dig:
            print(f"cache valid (digest {dig}); use --force to rebuild")
            return
    print("pass 1/2: gap detection (timestamps only)...", flush=True)
    gaps = mtf_lib.detect_gaps(mtf_lib.iter_month_tick_ts(pdir, symbol))
    with open(os.path.join(ddir, "gaps.json"), "w") as f:
        json.dump({"n": len(gaps),
                   "gaps": [[int(a), int(b)] for a, b in gaps]}, f)
    print(f"  {len(gaps)} data gaps (non-weekend >1h)", flush=True)

    print("pass 2/2: bar aggregation...", flush=True)
    counts = {}
    for tf, tf_ns in mtf_lib.TF_NS.items():
        starts, o, h, l, c, nt = [], [], [], [], [], []
        for y in range(2010, 2019):
            for m in range(1, 13):
                df = mtf_lib.read_month_ticks(pdir, symbol, y, m,
                                              columns=["timestamp_utc", "bid",
                                                       "ask"])
                if df is None or len(df) == 0:
                    continue
                ts = df["timestamp_utc"].astype("int64").to_numpy()
                mid = (df["bid"].to_numpy(np.float64)
                       + df["ask"].to_numpy(np.float64)) / 2.0
                b = mtf_lib.bars_from_ticks(ts, mid, tf_ns)
                starts.append(b["start"]); o.append(b["open"])
                h.append(b["high"]); l.append(b["low"]); c.append(b["close"])
                nt.append(b["n_ticks"])
        bar = {"start_ns": np.concatenate(starts),
               "open": np.concatenate(o), "high": np.concatenate(h),
               "low": np.concatenate(l), "close": np.concatenate(c),
               "n_ticks": np.concatenate(nt).astype(np.int64)}
        order = np.argsort(bar["start_ns"], kind="stable")
        bar = {k: v[order] for k, v in bar.items()}
        bar["gap_flag"] = mtf_lib.mark_gap_bars(bar["start_ns"], tf_ns, gaps)
        df_out = pd.DataFrame(bar)
        df_out.to_parquet(os.path.join(ddir, f"bars_{tf}.parquet"),
                          compression="zstd", index=False)
        counts[tf] = {"n_bars": int(len(df_out)),
                      "n_gap_flagged": int(df_out["gap_flag"].sum()),
                      "first": int(df_out["start_ns"].iloc[0]),
                      "last": int(df_out["start_ns"].iloc[-1])}
        print(f"  {tf}: {counts[tf]['n_bars']} bars "
              f"({counts[tf]['n_gap_flagged']} gap-flagged)", flush=True)
    with open(man_path, "w") as f:
        json.dump({"digest": dig, "counts": counts}, f, indent=2)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--symbol", default="EURUSD")
    ap.add_argument("--data-root", default=None)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    root = data_root.resolve_data_root(args.data_root)
    pdir = os.path.join(root, "parquet")
    ddir = derived_dir(root)
    print(f"data root: {root}")
    build(pdir, args.symbol, ddir, args.force)


if __name__ == "__main__":
    main()
