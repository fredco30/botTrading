#!/usr/bin/env python3
"""Autonomous mission — extended-horizon check (intraday -> multi-day).

Tests whether any of the three surviving signal families shows positive
drift at 4h..24h horizons (open-to-open).  EXPLORATORY screen.
"""
from __future__ import annotations

import json
import statistics
import sys
import time

from event_study import DATA_END, DATA_START, SignalCollector, load_filtered_bars
from variants import DonchianBreakoutH1, EmaBaseVariant, RsiMeanReversion
from research_engine import CostModel, ResearchEngine, SizingConfig

HORIZONS = {4: "1h", 8: "2h", 16: "4h", 48: "12h", 96: "24h"}  # M15 bars
PIP = 0.0001


def study(bars, signal):
    eng = ResearchEngine(
        instrument=__import__("research_engine").get_instrument("EURUSD"),
        costs=CostModel(spread_pips=1.0),
        sizing=SizingConfig(mode="fixed_lot", fixed_lot=0.01),
    )
    collector = SignalCollector(signal)
    eng.run(bars, collector)
    opens = [b.open for b in bars]
    n = len(bars)
    out = {}
    for h in HORIZONS:
        vals = []
        for i, ts, side in collector.events:
            if i + h >= n:
                continue
            sign = 1.0 if side == "LONG" else -1.0
            vals.append(sign * (opens[i + h] - opens[i]) / PIP)
        out[HORIZONS[h]] = {
            "N": len(vals),
            "MEAN_PIPS": round(statistics.fmean(vals), 3) if vals else None,
            "MEDIAN_PIPS": round(statistics.median(vals), 3) if vals else None,
            "WIN_RATE": round(sum(1 for v in vals if v > 0) / len(vals), 4) if vals else None,
            "STD": round(statistics.stdev(vals), 2) if len(vals) > 1 else None,
        }
    out["N_SIGNALS"] = len(collector.events)
    return out


def main():
    csv_path, out_json = sys.argv[1], sys.argv[2]
    bars = load_filtered_bars(csv_path)
    print(f"window {bars[0].dt} .. {bars[-1].dt} ({len(bars)} bars)", flush=True)
    families = {
        "H6_rsi_meanrev": RsiMeanReversion(),
        "H7_donchian_24h": DonchianBreakoutH1(),
        "H1_trend_pullback": EmaBaseVariant(use_rejection=False,
                                            use_body_ratio=False,
                                            use_body_compare=False,
                                            use_rsi=False),
    }
    results = {}
    for name, sig in families.items():
        t0 = time.time()
        results[name] = study(bars, sig)
        print(f"\n=== {name} ({time.time() - t0:.0f}s) N={results[name]['N_SIGNALS']}",
              flush=True)
        for h, s in results[name].items():
            if h == "N_SIGNALS":
                continue
            print(f"  {h:>5}: mean={s['MEAN_PIPS']:+8.3f} med={s['MEDIAN_PIPS']:+8.3f} "
                  f"win={s['WIN_RATE']*100:5.2f}%", flush=True)
    with open(out_json, "w", encoding="utf-8") as fh:
        json.dump(results, fh, indent=2)
    print("saved", out_json, flush=True)


if __name__ == "__main__":
    main()
