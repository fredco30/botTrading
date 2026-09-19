#!/usr/bin/env python3
"""EXPERIMENT B0 — H1-state conditional drift screen (gates Experiment B).

Question: conditional on the latest CLOSED H1 Trend Magic state (+1/-1),
do next-bar M15/H1 returns drift in the state direction?

If per-bar conditional drift is ~0 (or negative) net of nothing, no
continuation entry family that only samples inside the state (B1-B5) can
manufacture a net-of-cost edge from drift; the filter family dies here
(credit discipline, protocol section 35).

Also reports multi-bar holding drifts (4h/8h/24h in H1 bars) since a filter
could still add value at longer holding horizons.
"""
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import tmlab as T

START, END = "2020-01-01", "2025-12-31 23:59"


def run(sym: str) -> dict:
    df5 = T.load_5m(sym, START, END)
    h1 = T.resample_ohlcv(df5, "1h")
    m15 = T.resample_ohlcv(df5, "15min")
    pip = T.PIP[sym]
    out = {}
    for tf, df in (("H1", h1), ("M15", m15)):
        h = df["high"].to_numpy(); l = df["low"].to_numpy()
        c = df["close"].to_numpy()
        mt, d, cc, vol = T.trend_magic(h, l, c)
        # state known at close of bar i (decisions use bar i, returns bar i+1)
        r1 = np.full(len(c), np.nan)
        r1[:-1] = np.log(c[1:] / c[:-1])
        yrs = np.array([ts.year for ts in df.index])
        res = {"bars": int(len(c)),
               "pct_time_bull": float(np.nanmean(d > 0)),
               "pct_time_bear": float(np.nanmean(d < 0)),
               "pct_time_zero": float(np.nanmean(d == 0))}
        for state, side in ((1, "bull_long"), (-1, "bear_short")):
            m = (d == state)
            m = m.copy()
            m[-1] = False                      # need a next bar
            px = c[np.nonzero(m)[0]]
            rr2 = r1[m] * state                # signed by trade direction
            st = T.stats_bucket(rr2, px, pip)
            res[side] = st
            res[side + "_by_year"] = {}
            for y in range(2020, 2026):
                mm = m & (yrs == y)
                rr3 = r1[mm] * state
                res[side + "_by_year"][str(y)] = T.stats_bucket(rr3, c[np.nonzero(mm)[0]], pip)
        # longer holding on H1 only
        if tf == "H1":
            for hz in (4, 8, 24):
                rh = np.full(len(c), np.nan)
                j = np.arange(len(c) - hz)
                rh[j] = np.log(c[j + hz] / c[j])
                for state, side in ((1, "bull_long"), (-1, "bear_short")):
                    m = (d == state)
                    m[m.shape[0] - hz:] = False
                    mm = m.copy()
                    mm[:hz] = False
                    idx = np.nonzero(mm)[0]
                    st = T.stats_bucket(rh[idx] * state, c[idx], pip)
                    res[f"{side}_{hz}h"] = st
        out[tf] = res
    return out


def main():
    results = {}
    for sym in T.PAIRS:
        print(f"[B0] {sym} ...", flush=True)
        results[sym] = run(sym)

    print("\n=== STATE DRIFT (per bar, pips; signed so >0 = edge) ===")
    for sym in T.PAIRS:
        for tf in ("H1", "M15"):
            r = results[sym][tf]
            for side in ("bull_long", "bear_short"):
                st = r[side]
                yrs = r[side + "_by_year"]
                ym = " ".join(f"{y}:{(yrs[y].get('mean_pips') or 0):+.3f}"
                              for y in sorted(yrs) if yrs[y].get("n"))
                print(f"{sym} {tf} {side:11} n={st.get('n',0):>6} "
                      f"mean={st.get('mean_pips',0):+.3f} win={st.get('win_rate',0):.3f} "
                      f"se={st.get('se_pips',0):.3f} | {ym}")
            if tf == "H1":
                for hz in (4, 8, 24):
                    for side in ("bull_long", "bear_short"):
                        st = r[f"{side}_{hz}h"]
                        print(f"   hold {hz:>2}h {side:11} n={st.get('n',0):>5} "
                              f"mean={st.get('mean_pips',0):+.3f} win={st.get('win_rate',0):.3f}")

    with open(os.path.join(HERE, "STATE_DRIFT_RESULTS.json"), "w") as f:
        json.dump(results, f, indent=1, default=float)
    print("\nsaved STATE_DRIFT_RESULTS.json")


if __name__ == "__main__":
    main()
