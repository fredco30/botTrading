#!/usr/bin/env python3
"""MACRO-TICK-M1 discovery runner (frozen spec §16, §22).

Loads ONLY event-adjacent tick windows through the validated month
partition TickStore (2010..2018 hard guard; 2019+ is never opened) and
runs the three frozen strategies A/B/C on every primary-eligible NFP/CPI
event. Writes small JSON results + trade records next to this script.

Run:  python research/macro_tick_m1_event_strategies/run_discovery.py
"""
import json
import os
import sys

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.normpath(os.path.join(_HERE, "..", ".."))
sys.path.insert(0, _HERE)
sys.path.insert(0, _REPO)

import macro_lib as L  # noqa: E402
import mtf_lib as MTF  # noqa: E402

TICK_PARQUET = os.environ.get(
    "RESEARCH_TICK_PARQUET",
    r"E:\ResearchData\botTrading\ticks\parquet")
EVENTS_CSV = os.path.join(_REPO, "research", "macro_tick_m0", "data",
                          "macro_events_2010_2018_aligned.csv")
OUT_RESULTS = os.path.join(_HERE, "macro_m1_results.json")
OUT_TRADES = os.path.join(_HERE, "macro_m1_trades.json")
OUT_EVENTS = os.path.join(_HERE, "macro_m1_events.json")


def main():
    events = L.load_events(EVENTS_CSV)
    store = MTF.TickStore(TICK_PARQUET, symbol="EURUSD", max_months=4)
    all_trades, setup_rows, event_rows = [], [], []
    exclusions = {}
    for ev in events:
        t0 = ev["t0_ns"]
        ts, bid, ask = store.get_range(t0 - L.EVENT_WIN_PRE_NS,
                                       t0 + L.EVENT_WIN_POST_NS)
        res = L.run_event_on_window(ev, ts, bid, ask)
        if res["exclusion"]:
            exclusions[res["exclusion"]] = exclusions.get(res["exclusion"], 0) + 1
        event_rows.append(res)
        for k in "ABC":
            setup_rows.append(res["setups"].get(k, {}).get("status",
                                                           "NOT_RUN"))
        all_trades.extend(res["trades"])
    n_eligible = sum(1 for r in event_rows if not r["exclusion"])
    n_qual = sum(1 for r in event_rows if r.get("qualifying"))
    by_family = {}
    for r in event_rows:
        if not r["exclusion"]:
            by_family[r["family"]] = by_family.get(r["family"], 0) + 1
    metrics = {}
    for k in "ABC":
        trades_k = [t for t in all_trades if t["strategy"] == k]
        setups_k = [res["setups"][k]["status"] for res in event_rows
                    if k in res["setups"]]
        metrics[k] = L.compute_metrics(k, trades_k, setups_k, n_eligible,
                                       n_qual)
    results = {
        "mission": "MACRO_TICK_M1_EVENT_STRATEGY_DISCOVERY",
        "frozen_spec": "MACRO_TICK_M1_FROZEN_SPEC.md (commit b701d95)",
        "discovery": "2010-01-01..2019-01-01 exclusive",
        "events_nfp": by_family.get("NFP", 0),
        "events_cpi": by_family.get("CPI", 0),
        "events_primary_valid": n_eligible,
        "events_exclusions": exclusions,
        "qualifying_shocks_pooled": n_qual,
        "metrics": metrics,
        "fomc_primary_research": "DEFERRED",
    }
    with open(OUT_RESULTS, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=1)
    with open(OUT_TRADES, "w", encoding="utf-8") as f:
        json.dump(all_trades, f, indent=1)
    slim = []
    for r in event_rows:
        slim.append({k: v for k, v in r.items() if k != "trades"})
    with open(OUT_EVENTS, "w", encoding="utf-8") as f:
        json.dump(slim, f, indent=1)
    print(json.dumps(results, indent=1))


if __name__ == "__main__":
    main()
