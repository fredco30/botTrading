#!/usr/bin/env python3
"""AUTONOMOUS_EDGE_DISCOVERY_M2 — phase 2: tick-exact multi-year replay of
promising screened configs over 2010-2017 (mission 14 evidence), baseline
5s latency / 0 slip; stress 30s + 0.5 pip/side; common-sample reporting
(mission 22). Strategy = complete rule set built on the gated family feature.

Usage: run_deepen_m2.py <config-name>  — configs registered in STRATEGIES.
"""
import json
import os
import sys
import time

import numpy as np
import pandas as pd

import m2lib as M
import families_m2 as F

RESULTS = {}


def run_strategy(name, sig_fn, sl_pips, tp_pips, t_exit_min, years):
    """sig_fn(ex, y) -> signed int8 vector per completed bar (decision at
    bar close). Full tick-exact replay per year + pooled aggregate."""
    out = {"name": name, "sl": sl_pips, "tp": tp_pips, "tmin": t_exit_min,
           "years": {}}
    all_b, all_s, all_bc, all_sc = [], [], [], []
    for y in years:
        t0 = time.time()
        ex = M.rolling_extras(M.build_year(y), y)
        sig = np.asarray(sig_fn(ex, y))
        ts, bid, ask = M.I.load_year(y)
        bars = M.add_n_ticks(ts, M.I.m1_bars(ts, bid, ask))
        base, _ = M.m2_replay(ts, bid, ask, bars, sig, sl_pips, tp_pips,
                              t_exit_min, latency_ns=5 * M.NS, slip_pips=0.0)
        stress, _ = M.m2_replay(ts, bid, ask, bars, sig, sl_pips, tp_pips,
                                t_exit_min, latency_ns=30 * M.NS, slip_pips=0.50)
        bc, sc = M.common_sample(base, stress)
        all_b += base; all_s += stress; all_bc += bc; all_sc += sc
        mb = M.agg_metrics(base, f"{y}")
        ms_ = M.agg_metrics(sc, f"{y}-SC")
        out["years"][y] = {"base": mb, "stress_common": ms_,
                           "base_years": M.year_table(base)}
        print(f"  {y}: N={mb.get('N')} mean={mb.get('mean_pips')} "
              f"PF={mb.get('PF')} expR={mb.get('expectancy_r')} "
              f"L={mb.get('long_r')} S={mb.get('short_r')} "
              f"SCmean={ms_.get('mean_pips')} ({time.time()-t0:.0f}s)")
    out["agg_base"] = M.agg_metrics(all_b, "AGG BASE")
    out["agg_stress"] = M.agg_metrics(all_s, "AGG STRESS")
    out["agg_base_common"] = M.agg_metrics(all_bc, "AGG BASE-COMMON")
    out["agg_stress_common"] = M.agg_metrics(all_sc, "AGG STRESS-COMMON")
    out["years_table_base"] = M.year_table(all_b)
    out["survival_base"] = M.survival_veto(all_b)
    out["survival_stress_common"] = M.survival_veto(all_sc)
    return out, all_b, all_sc


def report(out):
    a = out["agg_base"]
    sc = out["agg_stress_common"]
    print(f"\n==== {out['name']} (SL{out['sl']}/TP{out['tp']}/T{out['tmin']}) "
          f"2010-2017 ====")
    print(f"BASE   : N={a['N']} {a['trades_per_month']}/mo mean={a['mean_pips']}p "
          f"med={a['median_pips']} PF={a['PF']} expR={a['expectancy_r']} "
          f"tot={a['total_pips']}p posYR={a['pos_years']} posMON={a['pos_months']}/{a['n_months']}")
    print(f"         L={a['long_r']}R S={a['short_r']}R remove_best={a['remove_best']}p "
          f"maxDD={a['max_dd_r']}R worstYR={a['worst_year_r']}R worst12m={a['worst_rolling12m_r']}R")
    print(f"         exits={a['exits']} yearlyR={a['yearly_r']}")
    print(f"STRESSC: N={sc['N']} mean={sc['mean_pips']}p PF={sc['PF']} expR={sc['expectancy_r']} "
          f"remove_best={sc['remove_best']}p posYR={sc['pos_years']}")
    for lbl, key in (("SURVIVAL base", "survival_base"),
                     ("SURVIVAL stress-common", "survival_stress_common")):
        s = out[key]
        print(f"{lbl}: final={s['FINAL_CAPITAL']} maxDD%={s['MAX_DRAWDOWN_PERCENT']} "
              f"worstYR%={s['WORST_CALENDAR_YEAR_PERCENT']} "
              f"worst12m%={s.get('WORST_ROLLING_12M_PERCENT')} "
              f"low={s['LOWEST_EQUITY']} longestDD_days={s['LONGEST_DRAWDOWN_DURATION_DAYS']} "
              f"VETO={'FAIL' if M.veto_fail(s) else ('WARN' if M.veto_warn(s) else 'ok')}")


if __name__ == "__main__":
    name = sys.argv[1]
    import strategies_m2 as S
    cfg = S.STRATEGIES[name]
    out, all_b, all_sc = run_strategy(name, cfg["sig_fn"], cfg["sl"],
                                      cfg["tp"], cfg["tmin"],
                                      cfg.get("years", M.DISCOVERY_YEARS))
    report(out)
    fn = f"deepen_{name}.json"
    json.dump(out, open(fn, "w"), indent=1, default=str)
    print(f"saved {fn}")
