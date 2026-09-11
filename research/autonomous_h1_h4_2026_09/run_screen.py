#!/usr/bin/env python3
"""Autonomous H1/H4 mission — DISCOVERY screen (2010-01-01 .. 2018-12-31).

Screens families F1..F8 with small parameter grids on all 3 pairs, both
timeframes, and reports forward-return statistics at mission horizons.
Selection criteria (mission §13) are computed per row; candidate flags are
derived afterwards.  VALIDATION windows are never touched here.
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
DISCOVERY_END = pd.Timestamp("2019-01-01 00:00")


def load(pair, tf, end):
    df = pd.read_parquet(os.path.join(CACHE_DIR, f"{pair}_{tf}.parquet"))
    return df[df.index < end]


def study(df, raw_side, horizons, pip):
    """raw_side = RAW generator output (signal known at its close).
    THE single execution shift of the DISCOVERY path is applied here.
    """
    side = to_executable_side(raw_side)
    opens = df["open"].values
    years = df.index.year.values
    rows = []
    for h in horizons:
        if len(opens) <= h:
            continue
        base = opens[:-h]
        fwd = opens[h:]
        sign = np.sign(side[:len(base)])
        r = sign * (fwd - base) / pip
        ev = sign != 0
        rr = r[ev]
        if len(rr) < 30:
            continue
        yr = years[:len(base)][ev]
        yr_means = pd.Series(rr).groupby(pd.Series(yr)).mean()
        ex99 = rr[rr <= np.quantile(rr, 0.99)]
        longs = rr[sign[ev] > 0]
        shorts = rr[sign[ev] < 0]
        rows.append({
            "horizon_bars": h,
            "N": int(len(rr)),
            "MEAN": float(rr.mean()),
            "MEDIAN": float(np.median(rr)),
            "WIN": float((rr > 0).mean()),
            "STD": float(rr.std(ddof=1)),
            "MEAN_LOW": float(rr.mean() - COSTS["LOW"]),
            "MEAN_NORMAL": float(rr.mean() - COSTS["NORMAL"]),
            "MEAN_STRESS": float(rr.mean() - COSTS["STRESS"]),
            "MEAN_EX99": float(ex99.mean()) if len(ex99) else np.nan,
            "MEAN_LONG": float(longs.mean()) if len(longs) else np.nan,
            "MEAN_SHORT": float(shorts.mean()) if len(shorts) else np.nan,
            "N_LONG": int(len(longs)), "N_SHORT": int(len(shorts)),
            "YEARS_POS_NORMAL": int((yr_means > COSTS["NORMAL"]).sum()),
            "N_YEARS": int(len(yr_means)),
        })
    return rows


def grids(tf):
    if tf == "H1":
        horizons = [4, 12, 24, 48]
        g = ([("F1_tsmom", dict(lookback=L)) for L in (24, 48, 96, 192)]
             + [("F2_donchian", dict(lookback=L)) for L in (20, 40, 80)]
             + [("F3_trend_pullback", dict(fast=f, slow=s)) for f, s in ((20, 100), (50, 200))]
             + [("F5_vol_compress_breakout", dict(lookback=L, ratio=r)) for L in (20, 40) for r in (0.75, 0.85)]
             + [("F6_mean_reversion", dict(sma_len=s, z=z)) for s in (20, 50) for z in (1.5, 2.0, 2.5)]
             + [("F7_trend_strength", dict(fast=20, slow=100, band=b)) for b in (1.0, 1.5)]
             + [("F8_breakout_expansion", dict(lookback=L, ratio=0.9)) for L in (20, 40)])
    else:
        horizons = [3, 6, 12, 24]
        g = ([("F1_tsmom", dict(lookback=L)) for L in (6, 12, 24, 48)]
             + [("F2_donchian", dict(lookback=L)) for L in (20, 40)]
             + [("F3_trend_pullback", dict(fast=f, slow=s)) for f, s in ((20, 100), (50, 200))]
             + [("F5_vol_compress_breakout", dict(lookback=20, ratio=r)) for r in (0.75, 0.85)]
             + [("F6_mean_reversion", dict(sma_len=s, z=z)) for s in (20, 50) for z in (1.5, 2.0)]
             + [("F7_trend_strength", dict(fast=20, slow=100, band=b)) for b in (1.0, 1.5)]
             + [("F8_breakout_expansion", dict(lookback=20, ratio=0.9))])
    return horizons, g


FAMILY_FN = {
    "F1_tsmom": f1_tsmom,
    "F2_donchian": f2_donchian,
    "F3_trend_pullback": f3_trend_pullback,
    "F5_vol_compress_breakout": f5_vol_compress_breakout,
    "F6_mean_reversion": f6_mean_reversion,
    "F7_trend_strength": f7_trend_strength,
    "F8_breakout_expansion": f8_breakout_expansion,
}


def main():
    out_dir = _HERE
    all_rows = []
    n_configs = 0
    for tf in ("H1", "H4"):
        horizons, grid = grids(tf)
        for pair in PAIRS:
            df_full = load(pair, tf, DISCOVERY_END)
            pip = PIP_SIZE[pair]
            # F4 needs both timeframes
            h4_full = load(pair, "H4", DISCOVERY_END) if tf == "H1" else None
            configs = list(grid)
            if tf == "H1":
                configs += [("F4_h4trend_h1entry", dict(ema_h4=e)) for e in (20, 50)]
            for family, params in configs:
                n_configs += 1
                if family == "F4_h4trend_h1entry":
                    side = f4_h4_trend_h1_entry(df_full, h4_full,
                                                ema_h4=params["ema_h4"])
                else:
                    side = FAMILY_FN[family](df_full, **params)
                for row in study(df_full, side, horizons, pip):
                    all_rows.append({"family": family, "tf": tf, "pair": pair,
                                     "params": json.dumps(params), **row})
        print(f"{tf} done ({n_configs} configs so far)", flush=True)

    df = pd.DataFrame(all_rows)
    df.to_csv(os.path.join(out_dir, "family_screen.csv"), index=False)
    with open(os.path.join(out_dir, "family_screen.json"), "w", encoding="utf-8") as fh:
        json.dump(all_rows, fh, indent=2)
    print(f"total configs screened: {n_configs}")
    print(f"rows: {len(df)}")
    # quick view: best rows by NORMAL-cost expectancy with N>=150
    ok = df[(df["N"] >= 150) & (df["MEAN_NORMAL"] > 0)].sort_values(
        "MEAN_NORMAL", ascending=False)
    cols = ["family", "tf", "pair", "params", "horizon_bars", "N",
            "MEAN_NORMAL", "WIN", "MEAN_EX99", "YEARS_POS_NORMAL", "N_YEARS"]
    print(ok[cols].head(25).to_string(index=False))
    if len(ok) == 0:
        print("NO row beats NORMAL_COST on DISCOVERY with N>=150")


if __name__ == "__main__":
    main()
