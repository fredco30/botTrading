#!/usr/bin/env python3
"""Robustness analysis for the balanced champion config.
  1. Parameter sensitivity (perturb each key knob +/-)
  2. Walk-forward split (2010-2017 vs 2018-2026)
  3. Alternate starting capital
  4. Trade stats (WR, PF, avg win/loss, by level, by reverse)
"""
import json, time
import numpy as np
import pandas as pd
from bt_engine import load_mt4_csv, precompute, default_params
from bt_fast import pack_data, run_fast

START = pd.Timestamp("2010-01-01")
END = pd.Timestamp("2026-04-08")


def metrics(r):
    neg = sum(1 for y in r["year_pnl"] if r["year_pnl"][y] < 0)
    return r["balance"], r["max_dd_pct"], neg


def main():
    t0 = time.time()
    print("Loading + precomputing...")
    df = load_mt4_csv("EURUSD15.csv")
    D = precompute(df)
    PKD = pack_data(D, START, END)
    champ = json.load(open("champion_balanced.json"))

    # --- detailed trade stats need per-trade data; run_fast only returns year PnL.
    # For WR/PF we re-run the slow engine with identical params to get trade list.
    from bt_engine import run_backtest
    print("Running detailed engine for trade stats...")
    res = run_backtest(D, champ, START, END)
    tr = res["trades"]
    wins = [t for t in tr if t["win"]]
    losses = [t for t in tr if not t["win"]]
    gp = sum(t["pnl"] for t in wins)
    gl = -sum(t["pnl"] for t in losses)
    pf = gp / gl if gl > 0 else float("inf")
    wr = len(wins) / len(tr) * 100 if tr else 0
    avg_w = np.mean([t["pnl"] for t in wins]) if wins else 0
    avg_l = np.mean([t["pnl"] for t in losses]) if losses else 0
    print("\n=== TRADE STATS (champion) ===")
    print(f"Trades: {len(tr)}  WR: {wr:.1f}%  PF: {pf:.2f}")
    print(f"Avg win: ${avg_w:,.0f}  Avg loss: ${avg_l:,.0f}")
    # by level / reverse
    from collections import defaultdict
    agg = defaultdict(lambda: [0, 0.0])
    for t in tr:
        key = "REV" if t["is_rev"] else f"L{t['level']}"
        agg[key][0] += 1
        agg[key][1] += t["pnl"]
    print("\nBy category (n, net):")
    for k in sorted(agg):
        print(f"  {k:5s}: n={agg[k][0]:4d}  net=${agg[k][1]:+,.0f}")

    # --- 1. Parameter sensitivity ---
    print("\n=== PARAMETER SENSITIVITY (balance / dd% / neg) ===")
    base_bal, base_dd, base_neg = metrics(run_fast(PKD, champ))
    print(f"BASE: bal=${base_bal:,.0f} dd={base_dd:.1f}% neg={base_neg}")
    sens = {
        "RiskPercent": [1.0, 1.25, 1.75, 2.0],
        "L0_LotMult": [0.15, 0.35, 0.5],
        "L1_LotMult": [4.0, 5.0, 7.0, 8.0],
        "L2_LotMult": [2.0, 2.5, 3.5, 4.0],
        "MinRR": [1.75, 2.25, 2.5],
        "ATR_MinPips": [6, 8, 9],
        "ATR_MaxPips": [17, 21, 24],
        "MaxEMA50DistPips": [25, 35, 40],
        "RevMaxSL_Pips": [15, 25, 30],
        "RollingWR_Threshold": [20, 30, 35],
    }
    for k, vals in sens.items():
        row = []
        for v in vals:
            P = dict(champ); P[k] = v
            b, d, n = metrics(run_fast(PKD, P))
            row.append(f"{v}: ${b:,.0f}/{d:.0f}%/{n}")
        print(f"  {k:22s} " + " | ".join(row))

    # --- 2. Walk-forward split ---
    print("\n=== WALK-FORWARD SPLIT ===")
    for lo, hi, lbl in [("2010-01-01", "2017-12-31", "2010-2017 (OOS-early)"),
                        ("2018-01-01", "2026-04-08", "2018-2026 (recent)")]:
        PKD2 = pack_data(D, pd.Timestamp(lo), pd.Timestamp(hi))
        r = run_fast(PKD2, champ)
        neg = sum(1 for y in r["year_pnl"] if r["year_pnl"][y] < 0)
        print(f"  {lbl}: bal=${r['balance']:,.0f} net=${r['balance']-10000:,.0f} "
              f"dd={r['max_dd_pct']:.1f}% neg={neg} trades={r['n_trades']}")

    # --- 3. Alternate starting capital ---
    print("\n=== STARTING CAPITAL ===")
    for cap in [5000, 10000, 25000, 50000]:
        r = run_fast(PKD, champ, initial_balance=float(cap))
        neg = sum(1 for y in r["year_pnl"] if r["year_pnl"][y] < 0)
        print(f"  ${cap:>6,}: final=${r['balance']:,.0f} dd={r['max_dd_pct']:.1f}% neg={neg}")

    print(f"\nDone ({time.time()-t0:.0f}s)")


if __name__ == "__main__":
    main()
