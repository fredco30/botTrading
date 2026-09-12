#!/usr/bin/env python3
"""Versioned gate checks + P013R JPY-cross replication (Discovery only).

Part A — reproduces the P013 month-end gate checks (ME / NORMAL / DIFF /
bootstrap CI / BOOT_P / BY_YEAR_DIFF) for the two a-priori pairings
(ON_DAY = return OF the month-end day; NEXT_DAY = close of month-end day to
close of the next trading day) on USDJPY/EURUSD/GBPUSD.

Part B — P013R, preregistered in hypothesis_ledger.csv BEFORE computation:
exact rule = LAST FX trading day of the month, LONG XJPY, entry at the daily
close (same definition as P013), exit at the close of the next trading day,
NORMAL cost 2 pips round trip, Discovery 2010-2018, moving-block-free
bootstrap (2000 draws, seed 42). Pairs tested EXACTLY: USDJPY, EURJPY,
GBPJPY. Equal-weighted pooling across pairs. No other parameters. Stays
DISCOVERY — V1/V2 remain locked (gate.py).

Writes phase2_gate_checks.json and p013r_replication.json.
"""
import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import phase2_lib as Q  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))


def _last_n_trading_days(all_days, n):
    """Last n trading days of each calendar month (a-priori definition)."""
    s = pd.Series(sorted(all_days))
    out = set()
    for _, g in s.groupby([pd.to_datetime(s).dt.year, pd.to_datetime(s).dt.month]):
        for d in list(g)[-n:]:
            out.add(d)
    return out


def month_end_split(sym, n_last=2):
    df = Q.discovery(Q.load(sym))
    px = df["close"].resample("1D").last().dropna()
    day = np.asarray(px.index.date)
    last_n = _last_n_trading_days(set(day), n_last)
    return px, day, last_n


def diff_stats(vals, lab, seed=42, n_boot=2000):
    me_v, no_v = vals[lab], vals[~lab]
    diff = float(me_v.mean() - no_v.mean())
    rng = np.random.default_rng(seed)
    boots = []
    for _ in range(n_boot):
        sel = rng.integers(0, len(vals), len(vals))
        a = vals[sel][lab[sel]]
        b = vals[sel][~lab[sel]]
        if len(a) > 3 and len(b) > 3:
            boots.append(a.mean() - b.mean())
    lo, hi = np.percentile(boots, [2.5, 97.5])
    p = 2 * min(float(np.mean(np.array(boots) <= 0)),
                float(np.mean(np.array(boots) >= 0)))
    return {"ME": round(float(me_v.mean()), 2), "NORMAL": round(float(no_v.mean()), 2),
            "N_ME": int(labs_sum(lab)), "N_NORMAL": int((~lab).sum()),
            "DIFF": round(diff, 2), "CI95": [round(float(lo), 2), round(float(hi), 2)],
            "BOOT_P": round(min(p, 1.0), 3)}


def labs_sum(lab):
    return int(lab.sum())


def part_a():
    """P013 gate checks (both a-priori pairings)."""
    out = {"PROTOCOL": "P013 month-end gate checks; DIFF = ME - NORMAL daily "
                       "returns; bootstrap 2000, seed 42; Discovery only."}
    for pairing in ("ON_DAY", "NEXT_DAY"):
        for sym in ("USDJPY", "EURUSD", "GBPUSD"):
            px, day, last2 = month_end_split(sym)
            if pairing == "ON_DAY":
                s = px.diff().dropna() / Q.PIP[sym]
                vals = s.to_numpy()
                days = np.asarray(s.index.date)
                lab = np.array([d in last2 for d in days])
            else:
                v = ((px.shift(-1) - px) / Q.PIP[sym]).to_numpy()[:-1]
                days = np.asarray(px.index.date)[:-1]
                lab = np.array([d in last2 for d in days])
                vals = v
            years = np.array([d.year for d in days])
            st = diff_stats(vals, lab)
            by = {int(y): round(float(np.mean(vals[(years == y) & lab]) -
                                       np.mean(vals[(years == y) & ~lab])), 1)
                  for y in sorted(set(years))
                  if ((years == y) & lab).sum() > 2 and ((years == y) & ~lab).sum() > 2}
            st["BY_YEAR_DIFF"] = by
            st["POSITIVE_YEARS"] = f"{sum(1 for x in by.values() if x > 0)}/{len(by)}"
            out[f"{pairing}_{sym}"] = st
    return out


def part_b_p013r():
    """P013R — preregistered replication (LAST trading day of month only)."""
    res = {}
    pair_series = {}
    for sym in ("USDJPY", "EURJPY", "GBPJPY"):
        px, day, last1 = month_end_split(sym, n_last=1)   # preregistered: LAST day only
        # entry at close of last trading day of month; exit at close of the
        # next trading day
        vals = []
        years = []
        idx = px.index
        for i in range(len(px) - 1):
            if day[i] in last1:
                vals.append(float(px.iloc[i + 1] - px.iloc[i]) / Q.PIP[sym])
                years.append(idx[i + 1].year)
        vals = np.array(vals)
        years = np.array(years)
        gross_mean = float(vals.mean())
        net_mean = gross_mean - 2.0                    # NORMAL cost 2 pips RT
        rng = np.random.default_rng(42)
        boots = np.array([vals[rng.integers(0, len(vals), len(vals))].mean()
                          for _ in range(2000)])
        lo, hi = np.percentile(boots, [2.5, 97.5])
        p = 2 * min(float(np.mean(boots <= 0)), float(np.mean(boots >= 0)))
        by_year = {int(y): round(float(np.mean(vals[years == y])), 1)
                   for y in sorted(set(years))}
        res[sym] = {
            "N": int(len(vals)),
            "GROSS_MEAN_PIPS": round(gross_mean, 2),
            "NET_NORMAL_PIPS": round(net_mean, 2),
            "CI95_GROSS": [round(float(lo), 2), round(float(hi), 2)],
            "BOOT_P_GROSS": round(min(p, 1.0), 3),
            "POSITIVE_YEARS_GROSS": f"{sum(1 for v in by_year.values() if v > 0)}/{len(by_year)}",
            "BY_YEAR_GROSS": by_year,
        }
        pair_series[sym] = vals

    # equal-weighted pooled statistics (each pair counts once)
    rng = np.random.default_rng(42)
    pooled_gross, pooled_boot = [], []
    for _ in range(2000):
        means = []
        for sym, vals in pair_series.items():
            sel = vals[rng.integers(0, len(vals), len(vals))]
            means.append(sel.mean())
        pooled_boot.append(np.mean(means))
    for sym, vals in pair_series.items():
        pooled_gross.append(vals.mean())
    pooled_gross = float(np.mean(pooled_gross))
    plo, phi = np.percentile(pooled_boot, [2.5, 97.5])
    p = 2 * min(float(np.mean(np.array(pooled_boot) <= 0)),
                float(np.mean(np.array(pooled_boot) >= 0)))
    res["POOLED_EQUAL_WEIGHT"] = {
        "POOLED_GROSS": round(pooled_gross, 2),
        "POOLED_NET_NORMAL": round(pooled_gross - 2.0, 2),
        "POOLED_CI95_GROSS": [round(float(plo), 2), round(float(phi), 2)],
        "POOLED_P_GROSS": round(min(p, 1.0), 3),
        "PAIRS_POSITIVE_GROSS": f"{sum(1 for s in ('USDJPY','EURJPY','GBPJPY') if res[s]['GROSS_MEAN_PIPS'] > 0)}/3",
    }
    res["_RULE"] = ("PREREGISTERED (ledger P013R, registered BEFORE computation): "
                    "last FX trading day of month, LONG XJPY, close-to-next-close, "
                    "NORMAL 2 pips, Discovery 2010-2018, bootstrap 2000 seed 42; "
                    "equal-weight pooling; DISCOVERY ONLY — V1/V2 remain locked")
    return res


if __name__ == "__main__":
    a = part_a()
    with open(os.path.join(HERE, "phase2_gate_checks.json"), "w", encoding="utf-8") as f:
        json.dump(a, f, indent=1, default=str)
    print("WROTE phase2_gate_checks.json")
    for k, v in a.items():
        if isinstance(v, dict):
            print(f"  {k}: DIFF={v['DIFF']} p={v['BOOT_P']} CI={v['CI95']} pos_years={v.get('POSITIVE_YEARS')}")
    b = part_b_p013r()
    with open(os.path.join(HERE, "p013r_replication.json"), "w", encoding="utf-8") as f:
        json.dump(b, f, indent=1, default=str)
    print("WROTE p013r_replication.json")
    for sym in ("USDJPY", "EURJPY", "GBPJPY"):
        v = b[sym]
        print(f"  P013R {sym}: N={v['N']} GROSS={v['GROSS_MEAN_PIPS']} NET={v['NET_NORMAL_PIPS']} "
              f"CI={v['CI95_GROSS']} p={v['BOOT_P_GROSS']} pos_years={v['POSITIVE_YEARS_GROSS']}")
    print("  POOLED:", b["POOLED_EQUAL_WEIGHT"])
