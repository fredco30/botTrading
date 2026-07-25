#!/usr/bin/env python3
"""Fast parallel optimizer using the Numba engine (bt_fast).

Target: 10k -> 100k on 2010-2026, 0 negative years, DD% minimized (<=40).
Coarse-to-fine multi-stage sweep, multiprocessing across cores.
"""
import itertools, time, json
from multiprocessing import Pool, cpu_count
import numpy as np
import pandas as pd
from bt_engine import load_mt4_csv, precompute, default_params
from bt_fast import pack_data, run_fast

START = pd.Timestamp("2010-01-01")
END = pd.Timestamp("2026-04-08")

_PKD = None


def _init(df_path):
    global _PKD
    df = load_mt4_csv(df_path)
    D = precompute(df)
    _PKD = pack_data(D, START, END)


def _eval(overrides_base):
    overrides, base = overrides_base
    P = dict(base)
    P.update(overrides)
    r = run_fast(_PKD, P)
    neg = sum(1 for y in r["year_pnl"] if r["year_pnl"][y] < 0)
    score = (r["balance"]
             - 40000.0 * neg
             - 30000.0 * max(0.0, r["max_dd_pct"] - 40.0))
    return score, r["balance"], r["max_dd_pct"], neg, r["n_trades"], overrides


def run_stage(base, grids, procs, topn=15):
    keys = list(grids.keys())
    combos = [dict(zip(keys, c)) for c in itertools.product(*[grids[k] for k in keys])]
    tasks = [(ov, base) for ov in combos]
    with Pool(procs, initializer=_init, initargs=("EURUSD15.csv",)) as pool:
        res = pool.map(_eval, tasks, chunksize=16)
    res.sort(key=lambda x: -x[0])
    return res[:topn], len(combos)


def show(top, label):
    print(f"  {label} top:")
    for s, bal, dd, neg, ntr, ov in top:
        print(f"   bal=${bal:9,.0f} dd={dd:4.1f}% neg={neg} n={ntr:4d} | {ov}")


def main():
    t0 = time.time()
    ncpu = max(1, cpu_count() - 1)
    print(f"Using {ncpu} workers")
    base = default_params()

    # STAGE 1: pyramid multipliers + RR + main filters
    g1 = {
        "L1_LotMult": [3.0, 4.0, 5.0, 6.0, 8.0],
        "L2_LotMult": [1.5, 2.5, 3.5, 5.0],
        "MinRR": [2.0, 2.5, 3.0, 3.5],
        "ATR_MaxPips": [17, 19, 22, 26],
        "MaxEMA50DistPips": [25, 30, 40, 55],
        "RevMinConsecLosses": [0, 2, 3],
        "MaxTradesPerDay": [3, 4],
    }
    print(f"STAGE 1: {int(np.prod([len(v) for v in g1.values()]))} combos")
    top1, _ = run_stage(base, g1, ncpu, 12)
    show(top1, f"S1 ({time.time()-t0:.0f}s)")

    # STAGE 2: risk + SL/BE + reverse around best
    b1 = dict(base); b1.update(top1[0][5])
    g2 = {
        "RiskPercent": [1.0, 1.5, 2.0, 2.5],
        "L0_LotMult": [0.5, 1.0, 1.5],
        "BE_Trigger_R": [1.0, 1.5, 2.0],
        "MinSL_Pips": [12, 15, 18],
        "MaxSL_Pips": [20, 25, 30],
        "RevMaxSL_Pips": [15, 20, 25, 30],
        "RollingWR_Threshold": [30, 40, 50],
    }
    print(f"\nSTAGE 2: {int(np.prod([len(v) for v in g2.values()]))} combos")
    top2, _ = run_stage(b1, g2, ncpu, 15)
    show(top2, f"S2 ({time.time()-t0:.0f}s)")

    # STAGE 3: structure/session around top-3
    print("\nSTAGE 3: structure/session refine")
    g3 = {
        "TrendBars": [3, 5, 7],
        "SL_SwingBars": [2, 3, 4],
        "ATR_MinPips": [7, 9, 11],
        "LondonEndHour": [11, 12, 13],
        "NYEndHour": [16, 17, 18],
    }
    best_all = []
    for _, _, _, _, _, ov2 in top2[:3]:
        cb = dict(b1); cb.update(ov2)
        t3, _ = run_stage(cb, g3, ncpu, 3)
        # reconstruct full overrides relative to base for scoring record
        best_all.extend(t3)
    best_all.sort(key=lambda x: -x[0])
    show(best_all[:10], f"S3 ({time.time()-t0:.0f}s)")

    # CHAMPION: rebuild by applying top1 -> top2 -> top3 is ambiguous; instead
    # take the single best full param set by re-running best overrides chain.
    # We'll capture the best by re-evaluating candidates built cumulatively.
    # Simplest robust approach: local search from the best known config.
    print("\nSTAGE 4: coordinate local search from best config...")
    champ = dict(base)
    champ.update(top1[0][5])
    # apply best stage-2 overrides found for that base
    champ.update(top2[0][5])
    # apply best stage-3 overrides (they were run on b1+ov2 bases; take global best)
    champ.update(best_all[0][5])

    def score_of(P):
        r = run_fast(_PKD_local(), P)
        neg = sum(1 for y in r["year_pnl"] if r["year_pnl"][y] < 0)
        return (r["balance"] - 40000.0 * neg - 30000.0 * max(0.0, r["max_dd_pct"] - 40.0)), r, neg

    # coordinate descent over a focused neighborhood
    neighborhood = {
        "RiskPercent": [1.0, 1.25, 1.5, 1.75, 2.0, 2.5],
        "L0_LotMult": [0.5, 0.75, 1.0, 1.25, 1.5],
        "L1_LotMult": [3.0, 4.0, 5.0, 6.0, 7.0, 8.0],
        "L2_LotMult": [1.5, 2.0, 2.5, 3.0, 4.0, 5.0],
        "MinRR": [2.0, 2.25, 2.5, 2.75, 3.0, 3.5],
        "MinSL_Pips": [12, 14, 15, 16, 18],
        "MaxSL_Pips": [20, 22, 25, 28, 30],
        "RevMaxSL_Pips": [15, 20, 25, 30],
        "ATR_MinPips": [7, 8, 9, 10, 11],
        "ATR_MaxPips": [17, 19, 21, 24, 26],
        "MaxEMA50DistPips": [25, 30, 35, 40, 50],
        "BE_Trigger_R": [1.0, 1.25, 1.5, 1.75, 2.0],
        "RollingWR_Threshold": [30, 35, 40, 45, 50],
    }
    best_score, best_r, best_neg = score_of(champ)
    improved = True
    rounds = 0
    while improved and rounds < 4:
        improved = False
        rounds += 1
        for k, vals in neighborhood.items():
            cur = champ[k]
            for v in vals:
                if v == cur:
                    continue
                trial = dict(champ); trial[k] = v
                s, r, neg = score_of(trial)
                if s > best_score:
                    best_score, best_r, best_neg = s, r, neg
                    champ = trial
                    improved = True
        print(f"  round {rounds}: score={best_score:.0f} bal=${best_r['balance']:,.0f} "
              f"dd={best_r['max_dd_pct']:.1f}% neg={best_neg} ({time.time()-t0:.0f}s)")

    # FINAL REPORT
    r = run_fast(_PKD_local(), champ)
    neg = sum(1 for y in r["year_pnl"] if r["year_pnl"][y] < 0)
    print("\n" + "=" * 62)
    print("CHAMPION CONFIG")
    print("=" * 62)
    for k in sorted(champ):
        print(f"  {k} = {champ[k]}")
    print(f"\nBalance: ${r['balance']:,.0f}  Net: ${r['balance']-10000:,.0f}")
    print(f"Max DD: ${r['max_dd']:,.0f} ({r['max_dd_pct']:.1f}%)  Trades: {r['n_trades']}")
    print(f"Negative years: {neg}")
    print("\nPer-year net:")
    for y in sorted(r["year_pnl"]):
        v = r["year_pnl"][y]
        print(f"  {y}: ${v:+,.0f}{'  <-- NEG' if v < 0 else ''}")
    with open("champion_config.json", "w") as f:
        json.dump(champ, f, indent=2)
    print(f"\nTotal elapsed: {time.time()-t0:.0f}s")


_LOCAL_PKD = None
def _PKD_local():
    global _LOCAL_PKD
    if _LOCAL_PKD is None:
        df = load_mt4_csv("EURUSD15.csv")
        D = precompute(df)
        _LOCAL_PKD = pack_data(D, START, END)
    return _LOCAL_PKD


if __name__ == "__main__":
    main()
