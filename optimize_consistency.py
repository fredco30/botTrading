#!/usr/bin/env python3
"""Consistency-first optimizer: find configs with the FEWEST negative years,
then maximize balance subject to DD<=40 and balance>=100k.

Two-phase:
  Phase A: broad random/grid search minimizing (neg_years, -balance) with DD cap.
  Phase B: coordinate refinement on the most consistent configs.
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


def _metrics(r):
    neg = sum(1 for y in r["year_pnl"] if r["year_pnl"][y] < 0)
    # worst year and number of years below +500
    worst = min(r["year_pnl"].values()) if r["year_pnl"] else 0.0
    return neg, worst


def _eval(overrides_base):
    overrides, base = overrides_base
    P = dict(base); P.update(overrides)
    r = run_fast(_PKD, P)
    neg, worst = _metrics(r)
    dd = r["max_dd_pct"]
    bal = r["balance"]
    # Consistency-first score: heavily reward few neg years & high worst-year,
    # require balance>=100k and DD<=40 to count as "good".
    meets = (bal >= 100000.0 and dd <= 40.0)
    score = (-neg * 1e6) + (worst) + (bal / 1000.0) - max(0.0, dd - 40.0) * 5000.0
    if not meets:
        score -= 5e5  # deprioritize configs that miss the core targets
    return score, bal, dd, neg, worst, r["n_trades"], overrides


def run_grid(base, grids, procs, topn=20):
    keys = list(grids.keys())
    combos = [dict(zip(keys, c)) for c in itertools.product(*[grids[k] for k in keys])]
    tasks = [(ov, base) for ov in combos]
    with Pool(procs, initializer=_init, initargs=("EURUSD15.csv",)) as pool:
        res = pool.map(_eval, tasks, chunksize=16)
    res.sort(key=lambda x: -x[0])
    return res[:topn], len(combos)


def main():
    t0 = time.time()
    ncpu = max(1, cpu_count() - 1)
    print(f"Using {ncpu} workers")
    base = default_params()

    # Broad grid: emphasize filters that control consistency (hours, ATR, trend)
    g = {
        "L1_LotMult": [3.0, 5.0, 7.0],
        "L2_LotMult": [1.5, 2.5, 4.0],
        "L0_LotMult": [0.5, 1.0],
        "MinRR": [2.0, 2.5, 3.0],
        "ATR_MinPips": [8, 9, 10, 11],
        "ATR_MaxPips": [15, 17, 19],
        "TrendBars": [5, 7, 9],
        "LondonEndHour": [11, 12],
        "NYEndHour": [16, 17],
        "MaxTradesPerDay": [2, 3],
    }
    print(f"Phase A: {int(np.prod([len(v) for v in g.values()]))} combos")
    topA, _ = run_grid(base, g, ncpu, 25)
    print(f"  done ({time.time()-t0:.0f}s). Top by consistency-score:")
    for s, bal, dd, neg, worst, ntr, ov in topA:
        print(f"   neg={neg} worst=${worst:8,.0f} bal=${bal:9,.0f} dd={dd:4.1f}% n={ntr:4d}")

    # Phase B: refine the 3 most consistent configs
    print("\nPhase B: refine consistent configs")
    refine = {
        "RiskPercent": [0.75, 1.0, 1.5, 2.0],
        "MinSL_Pips": [14, 15, 16, 18],
        "MaxSL_Pips": [20, 22, 25],
        "RevMaxSL_Pips": [15, 20, 25],
        "MaxEMA50DistPips": [20, 25, 30],
        "BE_Trigger_R": [1.5, 2.0, 2.5],
        "RollingWR_Threshold": [35, 45, 55],
        "RevMinConsecLosses": [2, 3, 4],
    }
    allB = []
    for _, _, _, _, _, _, ovA in topA[:3]:
        cb = dict(base); cb.update(ovA)
        tB, _ = run_grid(cb, refine, ncpu, 5)
        allB.extend(tB)
    allB.sort(key=lambda x: -x[0])
    print(f"  done ({time.time()-t0:.0f}s). Top refined:")
    for s, bal, dd, neg, worst, ntr, ov in allB[:15]:
        print(f"   neg={neg} worst=${worst:8,.0f} bal=${bal:9,.0f} dd={dd:4.1f}% n={ntr:4d}")

    # Reconstruct champion from the best refined candidate
    # find base used: re-evaluate by merging topA base + best refine overrides
    best = allB[0]
    # Rebuild: the refine overrides were applied on a topA base; but allB only
    # stores the refine overrides. Re-run coordinate merge: start from the
    # topA config that yields fewest neg years, then apply best refine ov.
    champ = dict(base)
    champ.update(topA[0][6])   # best consistency base from phase A
    champ.update(best[6])      # refined overrides
    r = run_fast(_local_pkd(), champ)
    neg, worst = _metrics(r)
    print("\n" + "=" * 62)
    print("CONSISTENCY CHAMPION")
    print("=" * 62)
    for k in sorted(champ):
        print(f"  {k} = {champ[k]}")
    print(f"\nBalance: ${r['balance']:,.0f}  Net: ${r['balance']-10000:,.0f}")
    print(f"Max DD: ${r['max_dd']:,.0f} ({r['max_dd_pct']:.1f}%)  Trades: {r['n_trades']}")
    print(f"Negative years: {neg}   Worst year: ${worst:,.0f}")
    print("\nPer-year net:")
    for y in sorted(r["year_pnl"]):
        v = r["year_pnl"][y]
        print(f"  {y}: ${v:+,.0f}{'  <-- NEG' if v < 0 else ''}")
    with open("champion_consistency.json", "w") as f:
        json.dump(champ, f, indent=2)
    print(f"\nTotal elapsed: {time.time()-t0:.0f}s")


_LPKD = None
def _local_pkd():
    global _LPKD
    if _LPKD is None:
        df = load_mt4_csv("EURUSD15.csv")
        D = precompute(df)
        _LPKD = pack_data(D, START, END)
    return _LPKD


if __name__ == "__main__":
    main()
