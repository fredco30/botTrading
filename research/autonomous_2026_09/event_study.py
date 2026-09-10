#!/usr/bin/env python3
"""Autonomous mission — Phase 1 event study for EMA_BASE_CORE_V1.

Reads an MT4-style EURUSD M15 CSV, filters strictly to
[2010-01-04 00:00, 2026-04-09 00:00) BEFORE any strategic analysis,
runs the FROZEN EMA_BASE_CORE_V1 signal through the canonical causal
engine, and measures directional open-to-open returns at horizons
1/2/4/8/16 M15 bars.

No optimization, no strategy logic, no OOS access.

Usage:
  python event_study.py <eurusd_csv_path> <out_json_path> [<out_signals_csv>]
"""
from __future__ import annotations

import csv
import json
import os
import statistics
import sys
from datetime import datetime

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from ema_base_signal import EmaBaseCoreV1, SignalType
from research_engine import Bar, CostModel, ResearchEngine, SizingConfig, Strategy

DATA_START = datetime(2010, 1, 4, 0, 0)
DATA_END = datetime(2026, 4, 9, 0, 0)          # exclusive — OOS PROTECTED
HORIZONS = {1: "15m", 2: "30m", 4: "1h", 8: "2h", 16: "4h"}
PIP = 0.0001


class SignalCollector(Strategy):
    """Records every non-NONE decision; opens nothing."""

    def __init__(self, signal=None):
        self.signal = signal or EmaBaseCoreV1()
        self.events = []                 # (bar_index, decision_ts, "LONG"/"SHORT")

    def on_bar(self, ctx):
        sig = self.signal.on_bar(ctx)
        if sig in (SignalType.LONG, SignalType.SHORT):
            self.events.append((ctx.i, ctx.decision_ts, sig.value))
        return None


def load_filtered_bars(csv_path):
    """Load and strictly date-filter BEFORE any strategic use."""
    all_bars = __import__("research_engine").load_bars_csv(csv_path)
    bars = [b for b in all_bars if DATA_START <= b.dt < DATA_END]
    return bars


def stats_block(values):
    if not values:
        return {"N": 0}
    n = len(values)
    return {
        "N": n,
        "MEAN_PIPS": statistics.fmean(values),
        "MEDIAN_PIPS": statistics.median(values),
        "WIN_RATE": sum(1 for v in values if v > 0) / n,
        "STD": statistics.stdev(values) if n > 1 else 0.0,
    }


def run_event_study(bars, signal=None, signal_name="EMA_BASE_CORE_V1"):
    eng = ResearchEngine(
        instrument=__import__("research_engine").get_instrument("EURUSD"),
        costs=CostModel(spread_pips=1.0),
        sizing=SizingConfig(mode="fixed_lot", fixed_lot=0.01),
    )
    collector = SignalCollector(signal)
    eng.run(bars, collector)          # decisions at open[i]; no trades

    opens = [b.open for b in bars]
    n_bars = len(bars)

    per_event = []                    # event rows for CSV
    horizon_returns = {h: [] for h in HORIZONS}
    horizon_long = {h: [] for h in HORIZONS}
    horizon_short = {h: [] for h in HORIZONS}

    for i, ts, side in collector.events:
        entry = opens[i]
        sign = 1.0 if side == "LONG" else -1.0
        row = {"bar_index": i, "decision_ts": ts.isoformat(), "side": side}
        for h in HORIZONS:
            j = i + h
            if j >= n_bars:
                row[f"ret_{HORIZONS[h]}"] = None
                continue
            r = sign * (opens[j] - entry) / PIP
            row[f"ret_{HORIZONS[h]}"] = round(r, 3)
            horizon_returns[h].append(r)
            (horizon_long if side == "LONG" else horizon_short)[h].append(r)
        per_event.append(row)

    report = {
        "signal": signal_name,
        "data_start": DATA_START.isoformat(),
        "data_end_exclusive": DATA_END.isoformat(),
        "n_bars_processed": n_bars,
        "first_decision_ts": collector.events[0][1].isoformat() if collector.events else None,
        "N_SIGNALS": len(collector.events),
        "N_LONG": sum(1 for _, _, s in collector.events if s == "LONG"),
        "N_SHORT": sum(1 for _, _, s in collector.events if s == "SHORT"),
        # overlapping definition: decision bars closer than the max horizon (16)
        "N_OVERLAPPING_EVENTS": sum(
            1 for a, b in zip(collector.events, collector.events[1:])
            if b[0] - a[0] < 16),
        "horizons": {},
    }
    for h, name in HORIZONS.items():
        report["horizons"][name] = {
            "ALL": stats_block(horizon_returns[h]),
            "LONG": stats_block(horizon_long[h]),
            "SHORT": stats_block(horizon_short[h]),
        }

    # per-year means at each horizon (stability only)
    years = {}
    for row in per_event:
        y = row["decision_ts"][:4]
        years.setdefault(y, []).append(row)
    report["per_year"] = {}
    for y in sorted(years):
        rows = years[y]
        entry = {"N": len(rows)}
        for h, name in HORIZONS.items():
            vals = [r[f"ret_{name}"] for r in rows if r[f"ret_{name}"] is not None]
            entry[f"MEAN_{name}"] = round(statistics.fmean(vals), 3) if vals else None
        report["per_year"][y] = entry

    return report, per_event


def main():
    csv_path, out_json = sys.argv[1], sys.argv[2]
    out_csv = sys.argv[3] if len(sys.argv) > 3 else None
    print(f"Loading {csv_path} ...")
    bars = load_filtered_bars(csv_path)
    print(f"Filtered window: {bars[0].dt} .. {bars[-1].dt}  ({len(bars)} bars)")
    print("Running frozen EMA_BASE_CORE_V1 through the causal engine ...")
    report, per_event = run_event_study(bars)
    with open(out_json, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)
    if out_csv:
        with open(out_csv, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(per_event[0].keys()))
            writer.writeheader()
            writer.writerows(per_event)
    print(json.dumps(report["horizons"], indent=2))
    print(f"N_SIGNALS={report['N_SIGNALS']}  "
          f"(L={report['N_LONG']} S={report['N_SHORT']})  "
          f"overlap16={report['N_OVERLAPPING_EVENTS']}")


if __name__ == "__main__":
    main()
