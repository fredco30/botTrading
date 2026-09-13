#!/usr/bin/env python3
"""MTF-M1 discovery runner: executes the THREE frozen strategies
(A trend-pullback, B trend-breakout, C range-reversion) over the Discovery
window 2010-01-01..2019-01-01 exclusive with tick-accurate BID/ASK execution.

Requires bars built by build_bars.py (cached under <data_root>/derived/mtf_m1).
Writes mtf_m1_results.json next to this script and prints the summary.
"""
import argparse
import json
import os
import sys
import time

import numpy as np
import pandas as pd

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(REPO, "research", "tick_m1_microstructure"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import data_root  # noqa: E402
import mtf_lib    # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))


def load_bars(ddir, tf):
    df = pd.read_parquet(os.path.join(ddir, f"bars_{tf}.parquet"))
    keep = ~df["gap_flag"].to_numpy(dtype=bool)     # frozen: drop gap bars
    bar = {("start" if k == "start_ns" else k): df[k].to_numpy()
           for k in ("start_ns", "open", "high", "low", "close", "n_ticks")}
    bar = {k: v[keep] for k, v in bar.items()}
    bar["close_ts"] = bar["start"] + mtf_lib.TF_NS[tf]
    # bar LABELS must sit inside Discovery; the final grid bar may CLOSE
    # exactly at the 2019-01-01 hard cut — it can never produce a decision
    # (run_discovery_pass refuses decision_ns >= DISCOVERY_END).
    if len(bar["start"]) and bar["start"][-1] >= mtf_lib.DISCOVERY_END_NS:
        raise AssertionError("bar label at/after the 2019 hard cut")
    return bar


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--symbol", default="EURUSD")
    ap.add_argument("--data-root", default=None)
    ap.add_argument("--out", default=os.path.join(HERE, "mtf_m1_results.json"))
    args = ap.parse_args()

    root = data_root.resolve_data_root(args.data_root)
    pdir = os.path.join(root, "parquet")
    ddir = os.path.join(root, "derived", "mtf_m1")
    print(f"data root: {root}")

    with open(os.path.join(ddir, "gaps.json")) as f:
        gaps = [(int(a), int(b)) for a, b in json.load(f)["gaps"]]
    gap_starts = mtf_lib.gap_starts_array(gaps)
    print(f"gap list: {len(gaps)} data gaps")

    t0 = time.time()
    m15 = load_bars(ddir, "M15")
    h1 = load_bars(ddir, "H1")
    h4 = load_bars(ddir, "H4")
    print(f"bars: M15={len(m15["start"])} H1={len(h1["start"])} "
          f"H4={len(h4["start"])} ({time.time()-t0:.1f}s)")

    t0 = time.time()
    ema20_h1 = mtf_lib.ema(h1["close"], 20)
    ema50_h1 = mtf_lib.ema(h1["close"], 50)
    ema50_h4 = mtf_lib.ema(h4["close"], 50)
    ema200_h4 = mtf_lib.ema(h4["close"], 200)
    atr_h1 = mtf_lib.atr14(h1["high"], h1["low"], h1["close"])
    adx_h4 = mtf_lib.adx14(h4["high"], h4["low"], h4["close"])
    bb_mid, bb_lo, bb_hi = mtf_lib.bollinger(h1["close"], 20, 2.0)
    print(f"indicators done ({time.time()-t0:.1f}s)")

    t0 = time.time()
    ev_a = mtf_lib.strategy_A_events(h4["close_ts"], h1, m15, ema20_h1,
                                     ema50_h1, ema50_h4, ema200_h4)
    ev_b = mtf_lib.strategy_B_events(h4["close_ts"], h1, ema50_h4, ema200_h4,
                                     atr_h1, lookback=20)
    ev_c = mtf_lib.strategy_C_events(h4["close_ts"], h1, adx_h4, bb_mid,
                                     bb_lo, bb_hi, atr_h1, adx_max=20.0)
    print(f"signals: A={len(ev_a)} B={len(ev_b)} C={len(ev_c)} "
          f"({time.time()-t0:.1f}s)")

    store = mtf_lib.TickStore(pdir, args.symbol, max_months=4)
    t0 = time.time()
    trades, counts = mtf_lib.run_discovery_pass(ev_a + ev_b + ev_c, store,
                                                gap_starts)
    print(f"execution pass done: {len(trades)} trade records "
          f"({time.time()-t0:.1f}s)")

    results = {"meta": {
        "spec": "MTF_M1_FROZEN_SPEC.md (commit 7dd5a02)",
        "base_head": "27b6e24eb27f26efec77f42bd1755ee9dbfc3275",
        "data_root": root,
        "discovery": "2010-01-01T00:00:00Z .. 2019-01-01T00:00:00Z (exclusive)",
        "n_gaps": len(gaps),
        "n_ticks": 208_003_917,
        "bars": {tf: int(len(b["start"])) for tf, b in
                 (("M15", m15), ("H1", h1), ("H4", h4))},
        "signals": {k: len(v) for k, v in (("A", ev_a), ("B", ev_b), ("C", ev_c))},
        "latency_ms": 250, "bootstrap": "2000x seed42 percentile",
    }}
    summary = {}
    for kind, name in (("A", "MTF_A_TREND_PULLBACK"),
                       ("B", "MTF_B_TREND_BREAKOUT"),
                       ("C", "MTF_C_RANGE_REVERSION")):
        kt = [t for t in trades if t["kind"] == kind]
        m = mtf_lib.strategy_metrics(kt, counts[kind])
        m["id"] = name
        results[kind] = m
        summary[kind] = m
        print(f"\n=== {name} ===")
        for k in ("n_trades", "n_gap_invalid", "verdict", "net_mean_pips",
                  "profit_factor", "expectancy_r", "positive_years",
                  "remove_best_1pct_mean", "stress_010_mean",
                  "max_drawdown_pips", "total_net_pips", "win_rate",
                  "ci95_lo", "ci95_hi", "exits"):
            print(f"  {k}: {m.get(k)}")
        print(f"  setup_counts: {m.get('setup_counts')}")

    passing = [k for k in ("A", "B", "C")
               if results[k].get("verdict") == "MTF_DISCOVERY_PROMISING"]
    results["FINAL_STATUS"] = ("STOP_FOR_HUMAN_REVIEW" if passing
                               else "NO_MTF_CANDIDATE")
    results["STRATEGIES_PASSING_GATE"] = passing
    with open(os.path.join(HERE, "mtf_m1_trades.json"), "w") as f:
        json.dump(trades, f, indent=1, default=float)
    with open(args.out, "w") as f:
        json.dump(results, f, indent=2, default=float)
    print(f"\nFINAL_STATUS = {results['FINAL_STATUS']} "
          f"(passing gate: {passing or 'none'})")
    print(f"results written: {args.out}")


if __name__ == "__main__":
    main()
