#!/usr/bin/env python3
"""Autonomous H1/H4 mission — selection + frozen validation pipeline.

1. Reads family_screen.csv (DISCOVERY 2010-2018).
2. Applies mission §13 selection criteria per (family, tf, params, horizon).
3. Freezes at most 5 candidates; runs them unchanged on VALIDATION_1
   (2019-2022); applies the §15 gate; at most 3 pass to VALIDATION_2
   (2023-01-01 .. 2026-04-08), tested exactly once.

Signals are generated ONCE on the full allowed history (features are
strictly causal / backward-looking) and events are then bucketed by
decision timestamp into the three periods — so indicators never re-warm
artificially inside a validation window.
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from h1h4_lib import (COSTS, PIP_SIZE, f1_tsmom, f2_donchian, f3_trend_pullback,  # noqa: E402
                      f4_h4_trend_h1_entry, f5_vol_compress_breakout,
                      f6_mean_reversion, f7_trend_strength,
                      f8_breakout_expansion, to_executable_side)

CACHE_DIR = r"C:\Users\Fred\.zcode\tmp\autonomous\h1h4"
PAIRS = ["EURUSD", "GBPUSD", "USDJPY"]
DATA_START = pd.Timestamp("2010-01-01 00:00")
DATA_END = pd.Timestamp("2026-04-09 00:00")
V1 = (pd.Timestamp("2019-01-01"), pd.Timestamp("2023-01-01"))
V2 = (pd.Timestamp("2023-01-01"), DATA_END)
MAX_HORIZON = 48

FAMILY_FN = {
    "F1_tsmom": f1_tsmom,
    "F2_donchian": f2_donchian,
    "F3_trend_pullback": f3_trend_pullback,
    "F4_h4trend_h1entry": lambda df, h4df, **kw: f4_h4_trend_h1_entry(df, h4df, **kw),
    "F5_vol_compress_breakout": f5_vol_compress_breakout,
    "F6_mean_reversion": f6_mean_reversion,
    "F7_trend_strength": f7_trend_strength,
    "F8_breakout_expansion": f8_breakout_expansion,
}


def load(pair, tf):
    return pd.read_parquet(os.path.join(CACHE_DIR, f"{pair}_{tf}.parquet"))


def load_h4(pair):
    return load(pair, "H4")


def event_returns(df, side, horizon, pip, start, end):
    """Returns array of signed pips for events with decision ts in [start,end)."""
    opens = df["open"].values
    n = len(opens)
    side_exec = to_executable_side(side)          # causal execution
    idx = np.where(side_exec != 0)[0]
    if len(idx) == 0:
        return np.array([]), np.array([]), np.array([])
    ts = df.index.values
    in_win = (ts[idx] >= np.datetime64(start)) & (ts[idx] < np.datetime64(end))
    idx = idx[in_win]
    keep = idx[idx + horizon < n]
    if len(keep) == 0:
        return np.array([]), np.array([]), np.array([])
    sign = side_exec[keep]
    r = sign * (opens[keep + horizon] - opens[keep]) / pip
    return r, sign, ts[keep]


def stats(r, costs=("LOW", "NORMAL", "STRESS")):
    if len(r) == 0:
        return {"N": 0}
    out = {
        "N": int(len(r)),
        "MEAN_PIPS": round(float(np.mean(r)), 3),
        "MEDIAN_PIPS": round(float(np.median(r)), 3),
        "WIN_RATE": round(float(np.mean(r > 0)), 4),
        "STD_PIPS": round(float(np.std(r, ddof=1)), 2),
    }
    for c in costs:
        out[f"AFTER_{c}"] = round(float(np.mean(r)) - COSTS[c], 3)
    ex99 = r[r <= np.quantile(r, 0.99)]
    out["MEAN_EX99"] = round(float(np.mean(ex99)), 3) if len(ex99) else None
    return out


def year_stability(r, ts, cost=COSTS["NORMAL"]):
    if len(r) == 0:
        return {}
    s = pd.Series(r, index=pd.DatetimeIndex(ts))
    m = s.groupby(s.index.year).mean()
    return {int(k): round(float(v) - cost, 3) for k, v in m.items()}


def side_for(pair, tf, family, params, frames):
    df = frames[(pair, tf)]
    if family == "F4_h4trend_h1entry":
        return FAMILY_FN[family](df, frames[(pair, "H4")], **params)
    return FAMILY_FN[family](df, **params)


def evaluate_candidate(name, family, tf, params, horizon, frames):
    """Aggregate evaluation of a frozen candidate over a window."""
    per_pair = {}
    rets_all, ts_all = [], []
    for pair in PAIRS:
        df = frames[(pair, tf)]
        r, sign, ts = event_returns(df, side_for(pair, tf, family, params, frames),
                                    horizon, PIP_SIZE[pair], DATA_START, DATA_END)
        per_pair[pair] = stats(r)
        per_pair[pair]["years"] = year_stability(r, ts)
        rets_all.append(r)
        ts_all.append(ts)
    r_all = np.concatenate(rets_all)
    agg = stats(r_all)
    n_pos_pairs = sum(1 for p in per_pair.values()
                      if p.get("N", 0) >= 100 and p.get("AFTER_NORMAL", -9) > 0)
    agg["PAIRS_POS"] = n_pos_pairs
    agg["PER_PAIR"] = per_pair
    agg["NAME"] = name
    agg["FAMILY"] = family
    agg["TF"] = tf
    agg["PARAMS"] = params
    agg["HORIZON_BARS"] = horizon
    return agg


def main():
    # ---- selection on DISCOVERY -----------------------------------------
    # §13 criteria: expectancy after NORMAL > 0 per pair where present;
    # >= 2/3 pairs positive; outlier-robust (ex99 > 0) on >= 2 pairs;
    # no single-year dependence (min years-after-cost >= 4 of 9, agg >= 5);
    # reasonable sample (total N >= 500).  Selection is aggregate across
    # pairs — no per-pair cherry-picking.
    screen = pd.read_csv(os.path.join(_HERE, "family_screen.csv"))
    disc = screen[screen["N"] >= 100].copy()
    groups = disc.groupby(["family", "tf", "params", "horizon_bars"])
    candidates = []
    for (family, tf, params, horizon), g in groups:
        if len(g) < 2:
            continue
        pos_pairs = int((g["MEAN_NORMAL"] > 0).sum())
        ex_ok = int((g["MEAN_EX99"] > 0).sum())
        min_years = int(g["YEARS_POS_NORMAL"].min())
        agg_mean = float(np.average(g["MEAN_NORMAL"], weights=g["N"]))
        n_tot = int(g["N"].sum())
        if pos_pairs >= 2 and ex_ok >= 2 and min_years >= 4 and n_tot >= 500 \
                and agg_mean > 0:
            candidates.append({
                "family": family, "tf": tf, "params": json.loads(params),
                "horizon": int(horizon), "agg_mean_normal": round(agg_mean, 3),
                "pos_pairs": pos_pairs, "n_total": n_tot,
                "min_years_pos": min_years,
            })
    candidates.sort(key=lambda c: -c["agg_mean_normal"])
    candidates = candidates[:5]
    print(f"candidates passing DISCOVERY criteria: {len(candidates)}")
    for c in candidates:
        print("  ", c)

    frames = {}
    for pair in PAIRS:
        for tf in ("H1", "H4"):
            frames[(pair, tf)] = load(pair, tf)

    # ---- VALIDATION_1 (frozen) -------------------------------------------
    v1_out = []
    passed_v1 = []
    for c in candidates:
        r = evaluate_candidate(f"{c['family']}-{c['tf']}-{c['params']}-{c['horizon']}",
                               c["family"], c["tf"], c["params"], c["horizon"], frames)
        # restrict to V1 window
        r_v1 = evaluate_window(c, frames, *V1)
        v1_out.append(r_v1)
        gate = (r_v1["AFTER_NORMAL"] > 0 and r_v1["PAIRS_POS"] >= 2
                and r_v1["N"] >= 300)
        print(f"\nV1 {r_v1['NAME']}: {json.dumps({k: v for k, v in r_v1.items() if k != 'PER_PAIR'})}")
        for p, s in r_v1["PER_PAIR"].items():
            print(f"   {p}: {json.dumps({k: v for k, v in s.items() if k != 'years'})}")
        if gate:
            passed_v1.append(c)
            print("   -> GATE PASS")
        else:
            print("   -> GATE FAIL")

    # ---- VALIDATION_2 (frozen, once) --------------------------------------
    v2_out = []
    for c in passed_v1[:3]:
        r_v2 = evaluate_window(c, frames, *V2)
        v2_out.append(r_v2)
        print(f"\nV2 {r_v2['NAME']}: {json.dumps({k: v for k, v in r_v2.items() if k != 'PER_PAIR'})}")
        for p, s in r_v2["PER_PAIR"].items():
            print(f"   {p}: {json.dumps({k: v for k, v in s.items() if k != 'years'})}")

    with open(os.path.join(_HERE, "validation_results.json"), "w",
              encoding="utf-8") as fh:
        json.dump({"discovery_candidates": candidates,
                   "validation1": v1_out, "validation2": v2_out}, fh, indent=2,
                  default=str)
    print("\nsaved validation_results.json")


def evaluate_window(c, frames, start, end):
    """Frozen candidate evaluation restricted to a decision-time window."""
    per_pair = {}
    rets_all = []
    for pair in PAIRS:
        df = frames[(pair, c["tf"])]
        side = to_executable_side(side_for(pair, c["tf"], c["family"],
                                           c["params"], frames))
        r, sign, ts = event_returns(df, side, c["horizon"], PIP_SIZE[pair],
                                    start, end)
        per_pair[pair] = stats(r)
        per_pair[pair]["years"] = year_stability(r, ts)
        rets_all.append(r)
    r_all = np.concatenate([x for x in rets_all if len(x)]) if any(
        len(x) for x in rets_all) else np.array([])
    agg = stats(r_all)
    n_pos = sum(1 for p in per_pair.values()
                if p.get("N", 0) >= 50 and p.get("AFTER_NORMAL", -9) > 0)
    agg["PAIRS_POS"] = n_pos
    agg["PER_PAIR"] = per_pair
    agg["NAME"] = f"{c['family']}-{c['tf']}-{json.dumps(c['params'])}-{c['horizon']}"
    return agg


if __name__ == "__main__":
    main()
