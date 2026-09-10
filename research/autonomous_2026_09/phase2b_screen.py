#!/usr/bin/env python3
"""Autonomous mission — Phase 2B exploratory screening.

Runs a small set of causally-defined signal families on the SAME filtered
history (2010-01-04 .. 2026-04-09 exclusive) and reports horizon stats.
EXPLORATORY ONLY — multiple-testing caveats apply; nothing here is a
validation.
"""
from __future__ import annotations

import json
import os
import statistics
import sys
import time

from event_study import HORIZONS, load_filtered_bars, run_event_study
from variants import DonchianBreakoutH1, EmaBaseVariant, RsiMeanReversion

FAMILIES = {
    "H1_trend_pullback": lambda: EmaBaseVariant(
        use_rejection=False, use_body_ratio=False, use_body_compare=False,
        use_rsi=False),
    "H2_trend_pullback_color": lambda: EmaBaseVariant(
        use_body_ratio=False, use_body_compare=False, use_rsi=False),
    "H3_full_no_rsi": lambda: EmaBaseVariant(use_rsi=False),
    "H4_trend_rejection": lambda: EmaBaseVariant(
        use_pullback=False, use_body_ratio=False, use_body_compare=False,
        use_rsi=False),
    "H5_pullback_rejection_no_trend": lambda: EmaBaseVariant(
        require_trend=False, use_body_ratio=False, use_body_compare=False,
        use_rsi=False),
    "H6_rsi_mean_reversion": lambda: RsiMeanReversion(),
    "H7_donchian_24h_breakout": lambda: DonchianBreakoutH1(),
}


def main():
    csv_path, out_json = sys.argv[1], sys.argv[2]
    print("Loading + filtering history ...", flush=True)
    bars = load_filtered_bars(csv_path)
    print(f"window {bars[0].dt} .. {bars[-1].dt} ({len(bars)} bars)", flush=True)

    results = {}
    for name, factory in FAMILIES.items():
        t0 = time.time()
        report, _ = run_event_study(bars, signal=factory(), signal_name=name)
        results[name] = report
        print(f"\n=== {name}  ({time.time() - t0:.0f}s) ===", flush=True)
        print(f"N={report['N_SIGNALS']} L={report['N_LONG']} "
              f"S={report['N_SHORT']} overlap16={report['N_OVERLAPPING_EVENTS']}",
              flush=True)
        for h, sides in report["horizons"].items():
            row = sides["ALL"]
            if row["N"]:
                print(f"  {h:>4}: ALL mean={row['MEAN_PIPS']:+7.3f} "
                      f"med={row['MEDIAN_PIPS']:+7.3f} win={row['WIN_RATE']*100:5.2f}% "
                      f"| L mean={sides['LONG']['MEAN_PIPS']:+7.3f} "
                      f"| S mean={sides['SHORT']['MEAN_PIPS']:+7.3f}", flush=True)
        # per-year mean sign consistency at 1h
        ys = [v.get("MEAN_1h") for v in report["per_year"].values()
              if v.get("MEAN_1h") is not None]
        if ys:
            pos = sum(1 for v in ys if v > 0)
            print(f"  1h per-year: {pos}/{len(ys)} years positive", flush=True)

    with open(out_json, "w", encoding="utf-8") as fh:
        json.dump(results, fh, indent=2)
    print(f"\nsaved {out_json}", flush=True)


if __name__ == "__main__":
    main()
