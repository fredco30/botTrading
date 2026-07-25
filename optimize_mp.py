#!/usr/bin/env python3
"""Parallel coarse-to-fine optimizer for EMA_Pullback_pyramid_v2.

Target: 10k -> 100k on 2010-2026, 0 negative years, DD% minimized (<=40).
Uses multiprocessing across CPU cores. Reuses precomputed indicator arrays.
"""
import itertools, time, json, os
from multiprocessing import Pool, cpu_count
import numpy as np
import pandas as pd
from bt_engine import load_mt4_csv, precompute, run_backtest, default_params

START = pd.Timestamp("2010-01-01")
END = pd.Timestamp("2026-04-08")

# Global per-worker precomputed dict (set by initializer)
_D = None


def _init(df_path):
    global _D
    df = load_mt4_csv(df_path)
    _D = precompute(df)


def _eval_combo(args):
    overrides, base = args
    P = dict(base)
    P.update(overrides)
    res = run_backtest(_D, P, START, END)
    yr = {}
    for t in res["trades"]:
        yr[t["year"]] = yr.get(t["year"], 0.0) + t["pnl"]
    neg = sum(1 for y in yr if yr[y] < 0)
    score = (res["balance"]
             - 30000.0 * neg
             - 25000.0 * max(0.0, res["max_dd_pct"] - 40.0))
    return score, res["balance"], res["max_dd_pct"], neg, overrides


def run_stage(D_path, base, grids, topn=15, procs=None):
    keys = list(grids.keys())
    combos = [dict(zip(keys, c)) for c in itertools.product(*[grids[k] for k in keys])]
    tasks = [(ov, base) for ov in combos]
    procs = procs or max(1, cpu_count() - 1)
    with Pool(procs, initializer=_init, initargs=(D_path,)) as pool:
        results = pool.map(_eval_combo, tasks, chunksize=8)
    results.sort(key=lambda x: -x[0])
    return results[:topn], len(combos)


def main():
    t0 = time.time()
    df_path = "EURUSD15.csv"
    ncpu = max(1, cpu_count() - 1)
    print(f"CPUs: {cpu_count()}, using {ncpu} workers")
    base = default_params()

    # STAGE 1: coarse sweep over highest-leverage knobs
    g1 = {
        "L1_LotMult": [3.0, 4.0, 5.0, 6.0],
        "L2_LotMult": [1.5, 2.5, 3.5, 5.0],
        "MinRR": [2.0, 2.5, 3.0, 3.5],
        "ATR_MaxPips": [17, 19, 22, 26],
        "MaxEMA50DistPips": [25, 30, 40, 55],
        "RevMinConsecLosses": [0, 2, 3],
        "MaxTradesPerDay": [3, 4],
    }
    n1 = int(np.prod([len(v) for v in g1.values()]))
    print(f"STAGE 1: {n1} combos...")
    top1, _ = run_stage(df_path, base, g1, topn=12, procs=ncpu)
    print(f"  done ({time.time()-t0:.0f}s). Top:")
    for s, bal, dd, neg, ov in top1:
        print(f"   bal=${bal:9,.0f} dd={dd:4.1f}% neg={neg} | {ov}")

    # STAGE 2: refine around best stage-1
    b1 = dict(base); b1.update(top1[0][4])
    g2 = {
        "RiskPercent": [1.0, 1.5, 2.0],
        "L0_LotMult": [0.5, 1.0, 1.5],
        "BE_Trigger_R": [1.0, 1.5, 2.0],
        "MinSL_Pips": [12, 15, 18],
        "MaxSL_Pips": [20, 25, 30],
        "RevMaxSL_Pips": [15, 20, 25, 30],
        "RollingWR_Threshold": [30, 40, 50],
    }
    n2 = int(np.prod([len(v) for v in g2.values()]))
    print(f"\nSTAGE 2: {n2} combos around stage-1 best...")
    top2, _ = run_stage(df_path, b1, g2, topn=15, procs=ncpu)
    print(f"  done ({time.time()-t0:.0f}s). Top:")
    for s, bal, dd, neg, ov in top2:
        print(f"   bal=${bal:9,.0f} dd={dd:4.1f}% neg={neg} | {ov}")

    # STAGE 3: micro-refine top-3 stage-2 around neighborhoods
    print(f"\nSTAGE 3: micro-refine...")
    candidates = []
    for _, _, _, _, ov2 in top2[:3]:
        c = dict(b1); c.update(ov2)
        candidates.append(c)
    g3 = {
        "TrendBars": [3, 5, 7],
        "SL_SwingBars": [2, 3, 4],
        "ATR_MinPips": [7, 9, 11],
        "LondonEndHour": [11, 12, 13],
        "NYEndHour": [16, 17, 18],
    }
    best_all = []
    for cbase in candidates:
        top3, _ = run_stage(df_path, cbase, g3, topn=3, procs=ncpu)
        best_all.extend(top3)
    best_all.sort(key=lambda x: -x[0])
    print(f"  done ({time.time()-t0:.0f}s). Top:")
    for s, bal, dd, neg, ov in best_all[:10]:
        print(f"   bal=${bal:9,.0f} dd={dd:4.1f}% neg={neg} | {ov}")

    # CHAMPION full report
    champ = dict(base)
    champ.update(top1[0][4])
    # find which candidate base the best stage-3 came from is complex; rebuild:
    # re-run best overrides on top of the union. Simpler: take best stage-3
    # overrides and apply onto b1 + its stage-2 overrides.
    print("\nReconstructing champion for full report...")
    # Evaluate top stage-3 override merged onto b1+stage2 best
    best_ov3 = best_all[0][4]
    final = dict(b1); final.update(top2[0][4]); final.update(best_ov3)
    res = run_backtest(load_and_precompute(df_path), final, START, END)
    yr = {}
    for t in res["trades"]:
        yr[t["year"]] = yr.get(t["year"], 0.0) + t["pnl"]
    neg = sum(1 for y in yr if yr[y] < 0)
    print("\n" + "=" * 60)
    print("CHAMPION CONFIG")
    print("=" * 60)
    for k in sorted(final):
        print(f"  {k} = {final[k]}")
    print(f"\nBalance: ${res['balance']:,.0f}  Net: ${res['net']:,.0f}")
    print(f"Max DD: ${res['max_dd']:,.0f} ({res['max_dd_pct']:.1f}%)  Trades: {res['n_trades']}")
    print(f"Negative years: {neg}")
    print("\nPer-year net:")
    for y in sorted(yr):
        print(f"  {y}: ${yr[y]:+,.0f}{'  <-- NEG' if yr[y] < 0 else ''}")
    with open("champion_config.json", "w") as f:
        json.dump(final, f, indent=2)
    print(f"\nTotal elapsed: {time.time()-t0:.0f}s")


_PCACHE = {}
def load_and_precompute(path):
    if path not in _PCACHE:
        _PCACHE[path] = precompute(load_mt4_csv(path))
    return _PCACHE[path]


if __name__ == "__main__":
    main()
