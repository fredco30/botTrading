#!/usr/bin/env python3
"""FAMILY G deep pass — USDJPY prior-day-HIGH break, long side.

Per-event statistics for the one surviving screen cell:
  - per-event 24h drift: mean/median/win/SE/bootstrap-CI/remove-best-1%
  - by-year and by-block (D21/V23/R25)
  - net after NORMAL and STRESS cost scenarios (single entry + single exit)
  - MFE/MAE structure for exit design
  - marginal vs unconditional baseline on identical bars
"""
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import tmlab as T

HZ = 24
START, END = "2020-01-01", "2025-12-31 23:59"
SPREAD = T.SPREAD_PIPS["USDJPY"]          # 0.9 pip, crossed on entry+exit
SLIP_STRESS = T.SLIP_STRESS_PIPS          # 0.5 pip per side, stress


def main():
    df5 = T.load_5m("USDJPY", START, END)
    h1 = T.resample_ohlcv(df5, "1h")
    h = h1["high"].to_numpy(); l = h1["low"].to_numpy()
    c = h1["close"].to_numpy()
    idx = h1.index
    pip = T.PIP["USDJPY"]
    n = len(c)
    day = np.array([ts.date() for ts in idx])
    yrs = np.array([ts.year for ts in idx])

    pdh = np.full(n, np.nan)
    for d in sorted(set(day)):
        m = day == d
        ii = np.nonzero(m)[0]
        prev = np.max(h[day != d][np.isin(np.arange(len(c)), np.nonzero(day != d)[0])]) if False else None
    # simpler: recompute prior-day extremes day by day
    dates = sorted(set(day))
    prev_h = np.nan
    pdh = np.full(n, np.nan)
    for d in dates:
        m = day == d
        ii = np.nonzero(m)[0]
        pdh[ii] = prev_h
        prev_h = np.max(h[m])

    ev = []
    for d in dates:
        ii = np.nonzero(day == d)[0]
        if len(ii) < 4 or not np.isfinite(pdh[ii[0]]):
            continue
        for i in ii:
            if h[i] > pdh[i]:
                ev.append(i)
                break
    ev = np.array(ev, "int64")
    j_ok = ev + HZ < n
    ev = ev[j_ok]
    r = np.log(c[ev + HZ] / c[ev]) * c[ev] / pip
    # baseline on identical bars minus events? Use unconditional same-horizon:
    jj = np.arange(n - HZ)
    base = np.log(c[jj + HZ] / c[jj]) * c[jj] / pip

    st = T.stats_bucket(np.log(c[ev + HZ] / c[ev]), c[ev], pip)
    yrs_e = yrs[ev]
    print(f"USDJPY PDH-break LONG, n={len(ev)} "
          f"({len(ev)/313.2:.1f}/week), horizon {HZ}h")
    print(f"  gross: mean={st['mean_pips']:+.2f} med={st['median_pips']:+.2f} "
          f"win={st['win_rate']:.3f} se={st['se_pips']:.2f} "
          f"ci95=[{st['ci95'][0]:+.2f},{st['ci95'][1]:+.2f}] "
          f"rb1%={st['rm_best1pct']:+.2f}")
    print(f"  baseline same-horizon: {np.mean(base):+.2f} pips -> "
          f"marginal {st['mean_pips'] - np.mean(base):+.2f}")
    cost_norm = SPREAD                     # entry crosses spread, exit assumed mid
    cost_stress = SPREAD + 2 * SLIP_STRESS
    print(f"  net NORMAL (-{cost_norm:.1f}): {st['mean_pips'] - cost_norm:+.2f} | "
          f"net STRESS (-{cost_stress:.1f}): {st['mean_pips'] - cost_stress:+.2f}")
    print(f"  net rb1% NORMAL: {st['rm_best1pct'] - cost_norm:+.2f}")
    byy = {int(y): (float(np.mean(r[yrs_e == y])), int((yrs_e == y).sum()),
                    float(np.mean(r[yrs_e == y] > 0)))
           for y in range(2020, 2026)}
    for y, (mu, cnt, w) in byy.items():
        print(f"    {y}: n={cnt:>3} mean={mu:+7.2f} net_norm={mu-cost_norm:+7.2f} win={w:.3f}")
    blocks = {"D_2020_2021": (yrs_e <= 2021), "V_2022_2023": ((yrs_e >= 2022) & (yrs_e <= 2023)),
              "R_2024_2025": (yrs_e >= 2024)}
    for b, m in blocks.items():
        print(f"    {b}: mean={np.mean(r[m]):+.2f} net={np.mean(r[m])-cost_norm:+.2f}")

    # MFE/MAE for exit design (pips)
    mfe = np.full(len(ev), np.nan); mae = np.full(len(ev), np.nan)
    for k, i in enumerate(ev):
        j = i + HZ
        mfe[k] = (np.max(h[i + 1:j + 1]) - c[i]) / pip
        mae[k] = (np.min(l[i + 1:j + 1]) - c[i]) / pip
    print(f"  MFE: mean={np.mean(mfe):+.1f} med={np.median(mfe):+.1f} | "
          f"MAE: mean={np.mean(mae):+.1f} med={np.median(mae):+.1f}")
    print(f"  corr(mfe,mae)={np.corrcoef(mfe, mae)[0,1]:+.2f}")

    # concentration: top-5 events
    order = np.argsort(r)[::-1]
    print("  top-5 events (date, pips):")
    for k in order[:5]:
        print(f"    {idx[ev[k]]}  {r[k]:+.1f}")
    print(f"  sum top-5 / sum positive = "
          f"{np.sum(r[order[:5]]) / np.sum(r[r > 0]):.2%}")

    out = {"n": int(len(ev)), "stats": st,
           "baseline": float(np.mean(base)),
           "by_year": {str(k): v for k, v in byy.items()},
           "mfe_mean": float(np.mean(mfe)), "mae_mean": float(np.mean(mae))}
    with open(os.path.join(HERE, "PDH_BREAK_DEEP_USDJPY.json"), "w") as f:
        json.dump(out, f, indent=1, default=float)
    print("saved PDH_BREAK_DEEP_USDJPY.json")


if __name__ == "__main__":
    main()
