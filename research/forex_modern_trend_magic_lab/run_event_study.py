#!/usr/bin/env python3
"""EXPERIMENT A — Trend Magic Enhanced state-change event study (no costs).

Question: does the trendDirection state change (bear<->bull) carry
economically meaningful directional information on modern FX (2020-2025)?

Design (protocol section 11):
  pairs      EURUSD, GBPUSD, USDJPY
  tfs        M5 (native), M15, H1 (causal resample of the 5m BID frame)
  events     trendDirection flips (+1<->-1, incl. first exit from 0)
  horizons   M5  +15m +30m +60m +120m +240m  (3/6/12/24/48 bars)
             M15 +30m +60m +120m +240m +480m (2/4/8/16/32 bars)
             H1  +1h +2h +4h +8h +16h        (1/2/4/8/16 bars)
  measure    forward log-return of BID close, signed by event direction,
             expressed in pips; MFE/MAE over the horizon window
  stats      n, events/week, mean, median, win rate, SE, bootstrap CI95
             (seeded), remove-best-1%, by pair / year / side

NO transaction-cost claim is made here (protocol: no executable-entry
assumption yet). 2026 sealed by tmlab loaders.
"""
import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import tmlab as T

START, END = "2020-01-01", "2025-12-31 23:59"
HORIZONS = {
    "M5": [(3, "+15m"), (6, "+30m"), (12, "+60m"), (24, "+120m"),
           (48, "+240m")],
    "M15": [(2, "+30m"), (4, "+60m"), (8, "+120m"), (16, "+240m"),
            (32, "+480m")],
    "H1": [(1, "+1h"), (2, "+2h"), (4, "+4h"), (8, "+8h"), (16, "+16h")],
}
N_WEEKS = 6 * 365.25 * 1440 / 5 / 288  # ~313.2 trading weeks in 2020-2025


def year_of(idx: pd.DatetimeIndex, ev: np.ndarray) -> np.ndarray:
    return np.array([idx[i].year for i in ev])


def run_pair_tf(sym: str, tf: str) -> dict:
    df5 = T.load_5m(sym, START, END)
    if tf == "M5":
        df = df5
    elif tf == "M15":
        df = T.resample_ohlcv(df5, "15min")
    else:
        df = T.resample_ohlcv(df5, "1h")
    h = df["high"].to_numpy(); l = df["low"].to_numpy()
    c = df["close"].to_numpy()
    mt, d, cc, vol = T.trend_magic(h, l, c)
    ev = T.events_from_direction(d)
    idx = df.index
    sign = d[ev].astype("float64")
    hz_bars = [hb for hb, _ in HORIZONS[tf]]
    fwd = T.forward_returns(c, ev, hz_bars)
    mfe, mae = T.excursions(h, l, c, ev, hz_bars, sign)
    pip = T.PIP[sym]

    out = {"n_events": int(len(ev)), "events_per_week": len(ev) / N_WEEKS,
           "tf": tf, "pair": sym, "n_bars": int(len(c))}
    # primary stats per horizon
    prim = {}
    for hb, label in HORIZONS[tf]:
        r = fwd[hb] * sign                     # signed log-returns
        px = c[ev]
        st = T.stats_bucket(r, px, pip)
        st["horizon"] = label
        st["mfe_pips"] = float(np.nanmean(mfe[hb] * pip ** -1)) if np.isfinite(
            mfe[hb]).any() else None
        st["mae_pips"] = float(np.nanmean(mae[hb] * pip ** -1)) if np.isfinite(
            mae[hb]).any() else None
        prim[label] = st
    out["by_horizon"] = prim

    # breakdowns at the MID horizon (index 2 -> +60m/+120m/+4h)
    hb_mid, lab_mid = HORIZONS[tf][2]
    r_mid = fwd[hb_mid] * sign
    yrs = year_of(idx, ev)
    by_year, by_side = {}, {}
    for y in range(2020, 2026):
        m = yrs == y
        by_year[str(y)] = T.stats_bucket(r_mid[m], c[ev][m], pip)
    for sname, smask in (("long", sign > 0), ("short", sign < 0)):
        by_side[sname] = T.stats_bucket(r_mid[smask], c[ev][smask], pip)
    blocks = {}
    m = yrs <= 2021
    blocks["D_2020_2021"] = T.stats_bucket(r_mid[m], c[ev][m], pip)
    m = (yrs >= 2022) & (yrs <= 2023)
    blocks["V_2022_2023"] = T.stats_bucket(r_mid[m], c[ev][m], pip)
    m = yrs >= 2024
    blocks["R_2024_2025"] = T.stats_bucket(r_mid[m], c[ev][m], pip)
    out["mid_horizon"] = lab_mid
    out["by_year_mid"] = by_year
    out["by_side_mid"] = by_side
    out["by_block_mid"] = blocks
    return out


def main():
    results = {}
    for sym in T.PAIRS:
        for tf in ("M5", "M15", "H1"):
            key = f"{sym}_{tf}"
            print(f"[event-study] {key} ...", flush=True)
            results[key] = run_pair_tf(sym, tf)
            r = results[key]
            mid = r["by_horizon"][r["mid_horizon"]]
            print(f"   n={r['n_events']} ({r['events_per_week']:.1f}/wk) "
                  f"mid {r['mid_horizon']}: mean={mid.get('mean_pips', 0):.3f} "
                  f"pips, win={mid.get('win_rate', 0):.3f}", flush=True)

    with open(os.path.join(HERE, "EVENT_STUDY_RESULTS.json"), "w") as f:
        json.dump(results, f, indent=1, default=float)
    print("saved EVENT_STUDY_RESULTS.json")


if __name__ == "__main__":
    main()
