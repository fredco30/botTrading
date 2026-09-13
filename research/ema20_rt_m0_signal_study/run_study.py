#!/usr/bin/env python3
"""EMA20-RT-M0 discovery runner: executes the ONE frozen setup (EMA20 M15
reclaim -> first retest, LONG only) over Discovery 2010-01-01..2019-01-01
exclusive with tick-accurate executable reference returns.

Requires the validated M15 bar cache (research/mtf_m1_tick_execution/
build_bars.py). Writes ema20_rt_m0_results.json / ema20_rt_m0_events.json
next to this script and prints the EMA20_RT_M0_SIGNAL_STUDY block.
"""
import argparse
import json
import os
import sys
import time

import numpy as np

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(REPO, "research", "tick_m1_microstructure"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import data_root     # noqa: E402
import ema20_rt_lib as R  # noqa: E402
import mtf_lib as L  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--symbol", default="EURUSD")
    ap.add_argument("--data-root", default=None)
    ap.add_argument("--out", default=os.path.join(HERE, "ema20_rt_m0_results.json"))
    args = ap.parse_args()

    root = data_root.resolve_data_root(args.data_root)
    pdir = os.path.join(root, "parquet")
    ddir = os.path.join(root, "derived", "mtf_m1")
    print(f"data root: {root}")

    with open(os.path.join(ddir, "gaps.json")) as f:
        gap_intervals = [(int(a), int(b)) for a, b in json.load(f)["gaps"]]
    assert all(gap_intervals[i][0] <= gap_intervals[i + 1][0]
               for i in range(len(gap_intervals) - 1)), "GAP LIST not sorted"
    print(f"gap list: {len(gap_intervals)} data gaps")

    t0 = time.time()
    bars = R.load_m15_bars(ddir)
    close, close_ts = bars["close"], bars["close_ts"]
    ema = R.ema20_of_closes(close)
    print(f"bars: M15={len(close)} (gap bars removed), EMA20 done "
          f"({time.time() - t0:.1f}s)")

    store = L.TickStore(pdir, args.symbol, max_months=4)
    t0 = time.time()
    events, counts = R.sweep_setups(store, close, close_ts, ema)
    print(f"sweep: {counts} ({time.time() - t0:.1f}s)")

    t0 = time.time()
    for ev in events:
        ev["horizons"] = R.resolve_horizons(store, ev, gap_intervals)
    print(f"horizons resolved ({time.time() - t0:.1f}s)")

    # ---- primary metrics per horizon (events valid for that horizon)
    filled = [e for e in events if e["entry_status"] == "FILLED"]
    metrics = {}
    for h in R.HORIZON_MIN:
        ok = [e["horizons"][h] for e in filled if e["horizons"][h]["status"] == "OK"]
        nets = [x["net_pips"] for x in ok]
        mids = [x["mid_pips"] for x in ok]
        years = [e["entry_year"] for e in filled
                 if e["horizons"][h]["status"] == "OK"]
        metrics[h] = R.horizon_metrics(nets, mids, years)
        per_h = {"N": metrics[h]["N"],
                 "n_not_measurable": sum(1 for e in filled
                                         if e["horizons"][h]["status"] == "NOT_MEASURABLE"),
                 "n_gap_invalid": sum(1 for e in filled
                                      if e["horizons"][h]["status"] == "GAP_INVALID")}
        metrics[h]["STATUS_COUNTS"] = per_h

    # ---- NON_OVERLAP_4H robustness (diagnostic only)
    entry_ts_all = [e["entry_ts"] for e in filled]
    keep = R.non_overlap_keep(entry_ts_all)
    nonoverlap = {}
    for h in R.HORIZON_MIN:
        ok = [filled[k]["horizons"][h] for k in keep
              if filled[k]["horizons"][h]["status"] == "OK"]
        years = [filled[k]["entry_year"] for k in keep
                 if filled[k]["horizons"][h]["status"] == "OK"]
        nonoverlap[h] = R.horizon_metrics([x["net_pips"] for x in ok],
                                          [x["mid_pips"] for x in ok], years)

    passing = R.signal_gate(metrics, nonoverlap)
    final_status = ("EMA20_RT_SIGNAL_PROMISING" if passing
                    else "NO_EMA20_RT_SIGNAL")

    if events:
        med_bars = float(np.median([e["bars_reclaim_to_retest"] for e in events]))
        med_min = float(np.median([e["minutes_reclaim_to_retest"] for e in events]))
    else:
        med_bars = med_min = float("nan")

    results = {
        "meta": {
            "spec": "EMA20_RT_M0_FROZEN_SPEC.md (this branch, commit BEFORE outcomes)",
            "base_head": "def3a943dfdd9ee0c59249080e5c1318815b11ae",
            "data_root": root,
            "discovery": "2010-01-01T00:00:00Z .. 2019-01-01T00:00:00Z (exclusive)",
            "symbol": args.symbol,
            "n_gaps": len(gap_intervals),
            "bars_m15": int(len(close)),
            "latency_ms": 250, "no_fill_window_s": 60,
            "horizons_min": list(R.HORIZON_MIN),
            "bootstrap": "2000x seed42 percentile",
            "short_side_tested": "NO",
        },
        "counts": counts,
        "MEDIAN_RECLAIM_TO_RETEST_BARS": med_bars,
        "MEDIAN_RECLAIM_TO_RETEST_MINUTES": round(med_min, 3),
        "horizons": {str(h): metrics[h] for h in R.HORIZON_MIN},
        "non_overlap_4h": {str(h): nonoverlap[h] for h in R.HORIZON_MIN},
        "GATE_PASSING_HORIZONS": passing,
        "FINAL_STATUS": final_status,
    }
    with open(args.out, "w") as f:
        json.dump(R.strip_raw(results), f, indent=2, default=float)
    slim = []
    for e in events:
        s = {k: v for k, v in e.items() if k != "horizons"}
        s["horizons"] = {str(h): e["horizons"][h] for h in R.HORIZON_MIN}
        slim.append(R.strip_raw(s))
    with open(os.path.join(HERE, "ema20_rt_m0_events.json"), "w") as f:
        json.dump(slim, f, indent=1, default=float)

    print(f"\n=== EMA20_RT_M0_SIGNAL_STUDY ===")
    print(f"counts: {counts}")
    print(f"MEDIAN_RECLAIM_TO_RETEST_BARS={med_bars} "
          f"MEDIAN_RECLAIM_TO_RETEST_MINUTES={med_min:.2f}")
    for h in R.HORIZON_MIN:
        m = metrics[h]
        print(f"{h}m: N={m['N']} mean_net={m.get('MEAN_EXECUTABLE_NET_PIPS')} "
              f"median_net={m.get('MEDIAN_EXECUTABLE_NET_PIPS')} "
              f"CI95=[{m.get('CI95_LO')}, {m.get('CI95_HI')}] "
              f"pos_years={m.get('POSITIVE_YEARS')} "
              f"remove_best={m.get('REMOVE_BEST_1_PERCENT_NET_MEAN')} "
              f"win={m.get('WIN_RATE_NET')} {m.get('STATUS_COUNTS')}")
        no = nonoverlap[h]
        print(f"    4H: N={no['N']} mean_net={no.get('MEAN_EXECUTABLE_NET_PIPS')} "
              f"median={no.get('MEDIAN_EXECUTABLE_NET_PIPS')} "
              f"pos_years={no.get('POSITIVE_YEARS')} "
              f"remove_best={no.get('REMOVE_BEST_1_PERCENT_NET_MEAN')}")
    print(f"GATE_PASSING_HORIZONS={passing}")
    print(f"FINAL_STATUS = {final_status}")
    print(f"results: {args.out}")


if __name__ == "__main__":
    main()
