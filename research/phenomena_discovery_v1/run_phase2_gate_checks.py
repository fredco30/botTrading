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
    res["POOLED_EQUAL_WEIGHT"]["STATUS"] = "SUPERSEDED_BY_PAIRED_BOOTSTRAP"
    res["POOLED_EQUAL_WEIGHT"]["NOTE"] = ("per-pair independent resampling "
        "understates family uncertainty (same month-end dates, shared JPY, "
        "correlated returns); superseded by the dependence audit "
        "(p013r_dependence_audit.json). Historical values kept.")
    return res




def part_c_dependence_audit(cost_normal=2.0, cost_stress=4.0):
    """P013R family inference on the COMMON event table (audit v4).

    One row per common month-end event (dates valid for ALL three pairs);
    paired bootstrap resamples whole rows; year-block bootstrap resamples
    calendar years as blocks. The rule is UNCHANGED (same P013R definition,
    NORMAL 2 pips, Discovery 2010-2018)."""
    pairs = ("USDJPY", "EURJPY", "GBPJPY")
    ret_by_date = {}
    for sym in pairs:
        # each pair uses ITS OWN daily calendar for its last-trading-day and
        # next-day return; the common table then keeps only dates valid for
        # all three (causal alignment — never index one pair with another
        # pair's calendar)
        px, day, last1_pair = month_end_split(sym, n_last=1)
        rets = {}
        for i in range(len(px) - 1):
            if day[i] in last1_pair:
                rets[day[i]] = float(px.iloc[i + 1] - px.iloc[i]) / Q.PIP[sym]
        ret_by_date[sym] = rets
    common = sorted(set(ret_by_date[pairs[0]])
                    & set(ret_by_date[pairs[1]])
                    & set(ret_by_date[pairs[2]]))
    dates = common
    mat = np.array([[ret_by_date[s][d] for s in pairs] for d in dates])
    years = np.array([d.year for d in dates])
    pooled_gross = mat.mean(axis=1)
    pooled_net = pooled_gross - cost_normal
    pooled_stress = pooled_gross - cost_stress

    pb_gross = Q.paired_bootstrap_means(mat, 2000, 42)
    pb_net = pb_gross - cost_normal
    yb_gross = Q.year_block_bootstrap_means(mat, years, 2000, 42)
    yb_net = yb_gross - cost_normal

    def ci(a):
        return [round(float(np.percentile(a, 2.5)), 2),
                round(float(np.percentile(a, 97.5)), 2)]

    def pval(a):
        return round(2 * min(float(np.mean(a <= 0)), float(np.mean(a >= 0))), 3)

    sr = np.sort(pooled_gross)[::-1]
    srn = np.sort(pooled_net)[::-1]
    yrs_u = np.unique(years)
    by_year_gross = {int(y): round(float(pooled_gross[years == y].mean()), 2)
                     for y in yrs_u}
    by_year_net = {int(y): round(float(pooled_net[years == y].mean()), 2)
                   for y in yrs_u}
    corr = np.corrcoef(mat, rowvar=False)
    out = {
        "PROTOCOL": ("dependence audit: common month-end event table, paired "
                     "bootstrap (rows resampled as units, 2000, seed 42) + "
                     "year-block bootstrap; rule UNCHANGED; Discovery only"),
        "N_COMMON": int(len(dates)),
        "EVENT_DATES_RANGE": f"{dates[0]} -> {dates[-1]}",
        "PAIR_CORRELATIONS": {"_ORDER": list(pairs),
                              "_MATRIX": np.round(corr, 3).tolist()},
        "USDJPY_GROSS": round(float(mat[:, 0].mean()), 2),
        "EURJPY_GROSS": round(float(mat[:, 1].mean()), 2),
        "GBPJPY_GROSS": round(float(mat[:, 2].mean()), 2),
        "PAIRS_GROSS_POSITIVE": f"{int((mat.mean(axis=0) > 0).sum())}/3",
        "PAIRED_POOLED_GROSS": round(float(pooled_gross.mean()), 2),
        "PAIRED_POOLED_NET_NORMAL": round(float(pooled_net.mean()), 2),
        "PAIRED_POOLED_NET_STRESS": round(float(pooled_stress.mean()), 2),
        "PAIRED_CI95_GROSS": ci(pb_gross),
        "PAIRED_CI95_NET": ci(pb_net),
        "PAIRED_P_GROSS": pval(pb_gross),
        "PAIRED_P_NET": pval(pb_net),
        "YEAR_BLOCK_GROSS_MEAN": round(float(yb_gross.mean()), 2),
        "YEAR_BLOCK_NET_MEAN": round(float(yb_net.mean()), 2),
        "YEAR_BLOCK_CI95_GROSS": ci(yb_gross),
        "YEAR_BLOCK_CI95_NET": ci(yb_net),
        "MEDIAN_GROSS": round(float(np.median(pooled_gross)), 2),
        "MEDIAN_NET": round(float(np.median(pooled_net)), 2),
        "WIN_RATE_GROSS": round(float((pooled_gross > 0).mean()), 3),
        "WIN_RATE_NET": round(float((pooled_net > 0).mean()), 3),
        "REMOVE_BEST_EVENT_GROSS": round(float(sr[1:].mean()), 2),
        "REMOVE_BEST_EVENT_NET": round(float(srn[1:].mean()), 2),
        "REMOVE_BEST_3_EVENTS_GROSS": round(float(sr[3:].mean()), 2),
        "REMOVE_BEST_3_EVENTS_NET": round(float(srn[3:].mean()), 2),
        "BY_YEAR_POOLED_GROSS": by_year_gross,
        "BY_YEAR_POOLED_NET": by_year_net,
        "POSITIVE_YEARS_GROSS": f"{sum(1 for v in by_year_gross.values() if v > 0)}/{len(by_year_gross)}",
        "POSITIVE_YEARS_NET": f"{sum(1 for v in by_year_net.values() if v > 0)}/{len(by_year_net)}",
    }
    # classification per mission criteria (no magic p threshold)
    crit = {
        "pooled_gross_gt_0": pooled_gross.mean() > 0,
        "pooled_net_normal_gt_0": pooled_net.mean() > 0,
        "pairs_2of3_positive": (mat.mean(axis=0) > 0).sum() >= 2,
        "majority_years_net_positive": sum(1 for v in by_year_net.values() if v > 0) > len(by_year_net) / 2,
        "remove_best3_net_gt_0": float(sr[3:].mean() - cost_normal) > 0
        if False else float(srn[3:].mean()) > 0,
        "paired_ci_excludes_0_net": ci(pb_net)[0] > 0 or ci(pb_net)[1] < 0,
    }
    out["CRITERIA"] = {k: bool(v) for k, v in crit.items()}
    if all(crit.values()):
        out["P013R_DISCOVERY_CLASSIFICATION"] = "P013R_DISCOVERY_STRONG"
    elif pooled_gross.mean() > 0 and pooled_net.mean() > 0:
        out["P013R_DISCOVERY_CLASSIFICATION"] = "P013R_DISCOVERY_WEAK"
    else:
        out["P013R_DISCOVERY_CLASSIFICATION"] = "P013R_REJECT"
    return out


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
    c = part_c_dependence_audit()
    with open(os.path.join(HERE, "p013r_dependence_audit.json"), "w", encoding="utf-8") as f:
        json.dump(c, f, indent=1, default=str)
    print("WROTE p013r_dependence_audit.json")
    for k in ("N_COMMON", "PAIRED_POOLED_GROSS", "PAIRED_POOLED_NET_NORMAL",
              "PAIRED_POOLED_NET_STRESS", "PAIRED_CI95_GROSS", "PAIRED_CI95_NET",
              "PAIRED_P_GROSS", "PAIRED_P_NET", "YEAR_BLOCK_CI95_GROSS",
              "YEAR_BLOCK_CI95_NET", "MEDIAN_GROSS", "MEDIAN_NET",
              "WIN_RATE_NET", "REMOVE_BEST_EVENT_NET",
              "REMOVE_BEST_3_EVENTS_NET", "POSITIVE_YEARS_NET",
              "PAIR_CORRELATIONS", "CRITERIA",
              "P013R_DISCOVERY_CLASSIFICATION"):
        print(f"  {k}: {c[k]}")
