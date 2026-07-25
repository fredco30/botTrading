#!/usr/bin/env python3
"""Coarse-to-fine optimizer for EMA_Pullback_pyramid_v2 toward:
   10k -> 100k on 2010-2026, 0 negative years, DD% as low as possible.

Objective (lexicographic via penalty):
   score = final_balance
           - 30000 * n_negative_years
           - 25000 * max(0, max_dd_pct - 40)
   then tie-break toward lower DD.
"""
import itertools, time, sys
import numpy as np
import pandas as pd
from bt_engine import load_mt4_csv, precompute, run_backtest, default_params

START = pd.Timestamp("2010-01-01")
END = pd.Timestamp("2026-04-08")


def evaluate(D, P):
    res = run_backtest(D, P, START, END)
    yr = {}
    for t in res["trades"]:
        yr[t["year"]] = yr.get(t["year"], 0.0) + t["pnl"]
    neg = sum(1 for y in yr if yr[y] < 0)
    score = (res["balance"]
             - 30000.0 * neg
             - 25000.0 * max(0.0, res["max_dd_pct"] - 40.0))
    return score, res, neg


def main():
    t0 = time.time()
    print("Loading + precomputing (one-time)...")
    df = load_mt4_csv("EURUSD15.csv")
    D = precompute(df)
    print(f"  done ({time.time()-t0:.1f}s)\n")

    base = default_params()

    # ---- STAGE 1: coarse sweep over the highest-leverage knobs ----
    grid = {
        "L1_LotMult": [2.0, 3.0, 4.0, 5.0, 6.0],
        "L2_LotMult": [1.5, 2.5, 3.5, 5.0],
        "MinRR": [2.0, 2.5, 3.0, 3.5],
        "ATR_MaxPips": [15, 17, 19, 22, 26],
        "MaxEMA50DistPips": [20, 25, 30, 40, 55],
        "RevMinConsecLosses": [0, 2, 3],
        "MaxTradesPerDay": [2, 3, 4],
    }
    keys = list(grid.keys())
    combos = list(itertools.product(*[grid[k] for k in keys]))
    print(f"STAGE 1: {len(combos)} combos...")
    best = []
    for ci, combo in enumerate(combos):
        P = dict(base)
        for k, v in zip(keys, combo):
            P[k] = v
        score, res, neg = evaluate(D, P)
        best.append((score, res["balance"], res["max_dd_pct"], neg, combo))
        if (ci + 1) % 1000 == 0:
            print(f"  {ci+1}/{len(combos)} ({time.time()-t0:.0f}s)")
    best.sort(key=lambda x: -x[0])
    print(f"\nSTAGE 1 done ({time.time()-t0:.0f}s). Top 12:")
    for s, bal, dd, neg, combo in best[:12]:
        cfg = " ".join(f"{k}={v}" for k, v in zip(keys, combo))
        print(f"  score={s:9.0f} bal=${bal:9,.0f} dd={dd:4.1f}% neg={neg} | {cfg}")

    # ---- STAGE 2: refine around the best stage-1 config ----
    top = best[0][4]
    P2 = dict(base)
    for k, v in zip(keys, top):
        P2[k] = v
    refine = {
        "RiskPercent": [1.0, 1.5, 2.0],
        "L0_LotMult": [0.5, 1.0, 1.5],
        "BE_Trigger_R": [1.0, 1.5, 2.0],
        "MinSL_Pips": [12, 15, 18],
        "MaxSL_Pips": [20, 25, 30],
        "RevMaxSL_Pips": [15, 20, 25, 30],
        "RollingWR_Threshold": [30, 40, 50],
        "ATR_MinPips": [7, 9, 11],
    }
    rkeys = list(refine.keys())
    rcombos = list(itertools.product(*[refine[k] for k in rkeys]))
    print(f"\nSTAGE 2: {len(rcombos)} combos around stage-1 best...")
    best2 = []
    for ci, combo in enumerate(rcombos):
        P = dict(P2)
        for k, v in zip(rkeys, combo):
            P[k] = v
        score, res, neg = evaluate(D, P)
        best2.append((score, res["balance"], res["max_dd_pct"], neg, dict(zip(rkeys, combo))))
        if (ci + 1) % 1000 == 0:
            print(f"  {ci+1}/{len(rcombos)} ({time.time()-t0:.0f}s)")
    best2.sort(key=lambda x: -x[0])
    print(f"\nSTAGE 2 done ({time.time()-t0:.0f}s). Top 15:")
    for s, bal, dd, neg, cfg in best2[:15]:
        print(f"  score={s:9.0f} bal=${bal:9,.0f} dd={dd:4.1f}% neg={neg} | {cfg}")

    # ---- BEST overall: full report ----
    champ = dict(P2)
    champ.update(best2[0][4])
    score, res, neg = evaluate(D, champ)
    print("\n" + "=" * 60)
    print("CHAMPION CONFIG")
    print("=" * 60)
    for k in sorted(champ):
        print(f"  {k} = {champ[k]}")
    print(f"\nBalance: ${res['balance']:,.0f}  Net: ${res['net']:,.0f}")
    print(f"Max DD: ${res['max_dd']:,.0f} ({res['max_dd_pct']:.1f}%)  Trades: {res['n_trades']}")
    print(f"Negative years: {neg}")
    yr = {}
    for t in res["trades"]:
        yr[t["year"]] = yr.get(t["year"], 0.0) + t["pnl"]
    print("\nPer-year net:")
    for y in sorted(yr):
        print(f"  {y}: ${yr[y]:+,.0f}{'  <-- NEG' if yr[y] < 0 else ''}")
    # Save champion trades
    import json
    with open("champion_config.json", "w") as f:
        json.dump({k: champ[k] for k in champ}, f, indent=2)
    print(f"\nTotal elapsed: {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
