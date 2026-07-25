#!/usr/bin/env python3
"""Balanced optimizer: keep the post-2019 profit engine (modern hours/ATR),
push balance toward 100k+ while minimizing negative years and DD<=40.

Removes the 'misses target' penalty cliff and instead uses a smooth objective:
   score = log(balance) - 2.5*neg_years - 3.0*max(0, dd-40)/10
Then reports the best config reaching bal>=100k with fewest neg years.
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


def _eval(ob):
    overrides, base = ob
    P = dict(base); P.update(overrides)
    r = run_fast(_PKD, P)
    neg = sum(1 for y in r["year_pnl"] if r["year_pnl"][y] < 0)
    bal = r["balance"]; dd = r["max_dd_pct"]
    # smooth objective: reward balance, penalize neg years and DD breach
    score = np.log(max(bal, 1.0)) - 1.6 * neg - 0.08 * max(0.0, dd - 40.0)
    return score, bal, dd, neg, r["n_trades"], overrides


def run_grid(base, grids, procs, topn=20):
    keys = list(grids.keys())
    combos = [dict(zip(keys, c)) for c in itertools.product(*[grids[k] for k in keys])]
    tasks = [(ov, base) for ov in combos]
    with Pool(procs, initializer=_init, initargs=("EURUSD15.csv",)) as pool:
        res = pool.map(_eval, tasks, chunksize=16)
    res.sort(key=lambda x: -x[0])
    return res[:topn]


def main():
    t0 = time.time()
    ncpu = max(1, cpu_count() - 1)
    print(f"Using {ncpu} workers")
    base = default_params()
    # Anchor to the profit-engine era (modern hours + ATR band) from stage-3 winner
    anchor = dict(base)
    anchor.update({"LondonEndHour": 11, "NYEndHour": 18, "ATR_MinPips": 7,
                   "ATR_MaxPips": 19, "SL_SwingBars": 2, "TrendBars": 5,
                   "MinRR": 2.0, "MaxTradesPerDay": 3, "BE_Trigger_R": 2.0,
                   "MinSL_Pips": 15, "MaxSL_Pips": 25, "MaxEMA50DistPips": 30,
                   "RevMinConsecLosses": 3, "RollingWR_Threshold": 30})

    g = {
        "RiskPercent": [1.0, 1.5, 2.0, 2.5],
        "L0_LotMult": [0.25, 0.5, 0.75, 1.0],
        "L1_LotMult": [4.0, 6.0, 8.0, 10.0],
        "L2_LotMult": [2.0, 3.0, 4.0, 6.0],
        "RevMaxSL_Pips": [15, 20, 25],
        "RollingWR_Threshold": [25, 30, 35],
    }
    print(f"Grid: {int(np.prod([len(v) for v in g.values()]))} combos")
    top = run_grid(anchor, g, ncpu, 30)
    print(f"done ({time.time()-t0:.0f}s). Top 20 by balanced score:")
    for s, bal, dd, neg, ntr, ov in top[:20]:
        flag = "OK" if (bal >= 100000 and dd <= 40) else "  "
        print(f"   [{flag}] neg={neg} bal=${bal:9,.0f} dd={dd:4.1f}% n={ntr:4d} | "
              f"R={ov['RiskPercent']} L0={ov['L0_LotMult']} L1={ov['L1_LotMult']} "
              f"L2={ov['L2_LotMult']} revSL={ov['RevMaxSL_Pips']} wr={ov['RollingWR_Threshold']}")

    # Pick best config with bal>=100k, dd<=40, fewest neg years
    feas = [x for x in top if x[1] >= 100000 and x[2] <= 40]
    if feas:
        feas.sort(key=lambda x: (x[3], -x[1]))
        chosen = feas[0]
    else:
        chosen = top[0]
    champ = dict(anchor); champ.update(chosen[5])
    r = run_fast(_lpkd(), champ)
    neg = sum(1 for y in r["year_pnl"] if r["year_pnl"][y] < 0)
    print("\n" + "=" * 62)
    print("BALANCED CHAMPION")
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
    with open("champion_balanced.json", "w") as f:
        json.dump(champ, f, indent=2)
    print(f"\nTotal elapsed: {time.time()-t0:.0f}s")


_LPKD = None
def _lpkd():
    global _LPKD
    if _LPKD is None:
        df = load_mt4_csv("EURUSD15.csv")
        _LPKD = pack_data(precompute(df), START, END)
    return _LPKD


if __name__ == "__main__":
    main()
