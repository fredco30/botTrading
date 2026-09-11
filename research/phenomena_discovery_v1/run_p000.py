#!/usr/bin/env python3
"""Run the full P000 analysis (signal raw + strategy + variants + splits).

Outputs (research/phenomena_discovery_v1/):
  video_strategy_results.json
  video_strategy_report.md
"""
import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import p000_lib as P  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))

US_SYMBOLS = ["USA500IDXUSD"]
US_UNIT = {"USA500IDXUSD": ("index pts", 1.0)}
FX_SYMBOLS = ["EURUSD", "GBPUSD", "USDJPY"]
HORIZONS = (1, 3, 6, 12, 24)   # 5m/15m/30m/1h/2h


def scale_rets(df_rets, scale):
    out = df_rets.copy()
    out["ret"] = out["ret"] * scale
    return out


def run_us(sym, results):
    unit, scale = US_UNIT[sym]
    df = P.load_5m(sym)
    print(f"{sym}: {len(df)} 5m bars {df.index[0]} -> {df.index[-1]}")
    for variant in ("LEVEL", "VWAP"):
        events = P.detect_us_events(df, variant=variant)
        name = {"LEVEL": "P000A_LEVEL_RETEST", "VWAP": "P000B_VWAP_RETEST"}[variant]
        res = {"N_EVENTS_ALL": len(events)}
        years = pd.DatetimeIndex([e.entry_ts for e in events]).year
        res["EVENTS_BY_SPLIT"] = {}
        for sp in ("DISCOVERY", "V1", "V2"):
            ev_sp = P.split_events_by_entry(events, sp)
            res["EVENTS_BY_SPLIT"][sp] = len(ev_sp)
            rets = P.raw_forward_returns(df, ev_sp, HORIZONS, split=P.SPLITS[sp])
            key = {"DISCOVERY": "DISCOVERY", "V1": "V1", "V2": "V2"}[sp]
            for hh in HORIZONS:
                sub = rets[rets["h"] == hh]
                res.setdefault(key, {})[f"h{hh*5}m"] = P.event_stats(sub, scale)
            # strategy
            for cost_name, cost in P.US_COSTS.items():
                trades = P.simulate_strategy(df, ev_sp, cost, P.ET, 1600)
                tf = P.trades_frame(trades)
                res.setdefault(key, {}).setdefault("STRATEGY", {})[cost_name] = \
                    P.summarize_trades(tf, scale)
        results[name] = res
    return df


def run_fx(sym, results):
    df = P.load_5m(sym)
    pip = P.PIP[sym]
    print(f"{sym}: {len(df)} 5m bars {df.index[0]} -> {df.index[-1]}")
    events = P.detect_fx_events(df)
    res = {"N_EVENTS_ALL": len(events), "UNIT": "pips"}
    for sp in ("DISCOVERY", "V1", "V2"):
        ev_sp = P.split_events_by_entry(events, sp)
        res.setdefault("EVENTS_BY_SPLIT", {})[sp] = len(ev_sp)
        rets = P.raw_forward_returns(df, ev_sp, HORIZONS, split=P.SPLITS[sp])
        for hh in HORIZONS:
            sub = rets[rets["h"] == hh]
            res.setdefault(sp, {})[f"h{hh*5}m"] = P.event_stats(sub, 1.0 / pip)
        for cost_name, cost in P.FX_COSTS.items():
            trades = P.simulate_strategy(df, ev_sp, cost * pip, "UTC", 1600)
            tf = P.trades_frame(trades)
            res.setdefault(sp, {}).setdefault("STRATEGY", {})[cost_name] = \
                P.summarize_trades(tf, 1.0 / pip)
    results[f"P000C_TRANSFER_{sym}"] = res


def main():
    results = {}
    for sym in US_SYMBOLS:
        run_us(sym, results)
    for sym in FX_SYMBOLS:
        run_fx(sym, results)
    out = os.path.join(HERE, "video_strategy_results.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=1, default=str)
    print("WROTE", out)


if __name__ == "__main__":
    main()
