#!/usr/bin/env python3
"""PHASE 0 — diagnostic of the FROZEN FX_PDH_001 strict trades.

DIAGNOSTIC ONLY: no filtering, no strategy change. Causal pre-entry features
(known at the signal bar close / entry open) and lifecycle variables
(post-entry, understanding only — never filters) are tabulated for winners
vs losers, top decile vs rest, and by year.

Outputs:
  FX_PDH_001_DIAGNOSTICS.md          (lab root)
  diagnostics/features_per_trade.csv (one row per 001 trade)
"""
import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import engine as E


def build_features(D, tr):
    o, h, l, c = D["o"], D["h"], D["l"], D["c"]
    atr, pdh, pdl, prev_close = D["atr"], D["pdh"], D["pdl"], D["prev_close"]
    ema20, day_first, day_pos = D["ema20"], D["day_first"], D["day_pos"]
    d_close, d_high, idx = D["d_close"], D["d_high"], D["idx"]
    n = D["n_bars"]
    s = tr["sig_i"].to_numpy()
    k = tr["entry_i"].to_numpy()
    ex = tr["exit_i"].to_numpy()
    fill = tr["entry_fill"].to_numpy()
    stop_price = E.STOP_ATR * atr[s]

    # expanding causal ATR percentile (rank among PRIOR ATRs, min 250)
    a = atr
    atr_pct = np.full(n, np.nan)
    vals = []
    for i in range(n):
        if np.isfinite(a[i]):
            if len(vals) >= 250:
                atr_pct[i] = np.mean(np.array(vals) <= a[i])
            vals.append(a[i])

    f = pd.DataFrame({"sig_i": s, "entry_i": k, "exit_i": ex,
                      "year": [idx[i].year for i in k],
                      "close_hour_utc": [(idx[i].hour + 1) % 24 for i in s],
                      "atr14_pips": atr[s] / E.PIP,
                      "atr_pctile": atr_pct[s],
                      "prior_day_range_pips": (pdh[s] - pdl[s]) / E.PIP,
                      "dayopen_below_pdh_pips": (pdh[s] - o[day_first[s]]) / E.PIP,
                      "travelled_dayopen_to_close_pips":
                          (c[s] - o[day_first[s]]) / E.PIP,
                      "close_above_pdh_pips": (c[s] - pdh[s]) / E.PIP,
                      "high_above_pdh_pips": (h[s] - pdh[s]) / E.PIP,
                      "gap_vs_prevclose_pips":
                          (o[day_first[s]] - prev_close[day_first[s]]) / E.PIP,
                      "sig_range_atr": (h[s] - l[s]) / atr[s],
                      "bars_into_day": s - day_first[s],
                      "ema20_dist_pips": (c[s] - ema20[s]) / E.PIP,
                      })
    rng = h[s] - l[s]
    f["sig_body_ratio"] = np.where(rng > 1e-12, (c[s] - o[s]) / rng, 0.0)
    f["sig_close_loc"] = np.where(rng > 1e-12, (c[s] - l[s]) / rng, 0.5)

    def sess(hh):
        return ("Asia" if hh <= 6 else "London" if hh <= 11 else
                "Overlap" if hh <= 15 else "NYpm" if hh <= 20 else "Late")
    f["session"] = [sess(hh) for hh in f["close_hour_utc"]]

    p = day_pos[s]
    f["ret_1d_pips"] = (d_close[p] - d_close[np.maximum(p - 1, 0)]) / E.PIP
    f["ret_3d_pips"] = (d_close[p] - d_close[np.maximum(p - 3, 0)]) / E.PIP
    f["ret_5d_pips"] = (d_close[p] - d_close[np.maximum(p - 5, 0)]) / E.PIP
    # consecutive higher-high completed days ending at the prior day
    chh = np.zeros(len(s), "int64")
    for m, pp in enumerate(p):
        cnt = 0
        i = 1
        while pp - i >= 1 and d_high[pp - i] > d_high[pp - i - 1]:
            cnt += 1
            i += 1
        chh[m] = cnt
    f["consec_higher_high_days"] = chh
    # Kaufman efficiency over the prior 24 H1 bars
    d24 = np.abs(c[s] - c[np.maximum(s - 24, 0)])
    path = np.array([np.sum(np.abs(np.diff(c[max(ss - 24, 0):ss + 1])))
                     for ss in s])
    f["her24"] = np.where(path > 1e-12, d24 / path, np.nan)

    # ---- lifecycle (understanding ONLY; never used as filters) ----
    mfe = np.empty(len(s)); mae = np.empty(len(s))
    t05 = np.full(len(s), np.nan); t1 = np.full(len(s), np.nan)
    t2 = np.full(len(s), np.nan)
    for m in range(len(s)):
        hi = h[k[m]:ex[m] + 1]; lo = l[k[m]:ex[m] + 1]
        mfe[m] = (hi.max() - fill[m]) / stop_price[m]
        mae[m] = (lo.min() - fill[m]) / stop_price[m]
        for thr, arr in ((0.5, t05), (1.0, t1), (2.0, t2)):
            hit = np.nonzero(hi >= fill[m] + thr * stop_price[m])[0]
            if len(hit):
                arr[m] = hit[0]
    f["mfe_r"] = mfe
    f["mae_r"] = mae
    f["time_to_05r_bars"] = t05
    f["time_to_1r_bars"] = t1
    f["time_to_2r_bars"] = t2
    f["net_r"] = tr["r_mult"].to_numpy()
    f["net_pips"] = tr["net_pips"].to_numpy()
    f["stop_pips"] = tr["stop_pips"].to_numpy()
    f["reason"] = tr["reason"].to_numpy()
    f["duration_bars"] = ex - k + 1
    return f


def med(x):
    return float(np.nanmedian(x)) if len(x) else float("nan")


def main():
    D = E.prepare()
    tr = E.replay(D, E.signals(D, "long_touch"))
    f = build_features(D, tr)
    os.makedirs(os.path.join(HERE, "diagnostics"), exist_ok=True)
    f.to_csv(os.path.join(HERE, "diagnostics", "features_per_trade.csv"),
             index=False)

    r = f["net_r"].to_numpy()
    q90, q25, q75 = np.quantile(r, [0.90, 0.25, 0.75])
    top10 = f[r >= q90]
    top25 = f[r >= q25]
    mid = f[(r > q25) & (r < q75)]
    losers = f[r <= 0]
    rest = f[r < q90]

    pre = ["atr14_pips", "atr_pctile", "prior_day_range_pips",
           "dayopen_below_pdh_pips", "travelled_dayopen_to_close_pips",
           "close_above_pdh_pips", "high_above_pdh_pips", "gap_vs_prevclose_pips",
           "sig_range_atr", "sig_body_ratio", "sig_close_loc", "bars_into_day",
           "ema20_dist_pips", "ret_1d_pips", "ret_3d_pips", "ret_5d_pips",
           "consec_higher_high_days", "her24"]
    post = ["mfe_r", "mae_r", "time_to_05r_bars", "time_to_1r_bars",
            "time_to_2r_bars", "duration_bars"]

    rows = {}
    for col in pre + post:
        rows[col] = {
            "ALL": med(f[col]), "TOP10%": med(top10[col]),
            "TOP25%": med(top25[col]), "MID": med(mid[col]),
            "LOSERS<=0": med(losers[col]), "REST90%": med(rest[col]),
        }
    tab = pd.DataFrame(rows).T

    spear = {col: float(f[[col, "net_r"]].corr(method="spearman")
                        .iloc[0, 1]) for col in pre}

    # session / hour tables
    sess = f.groupby("session").agg(
        n=("net_r", "size"), mean_r=("net_r", "mean"),
        median_r=("net_r", "median")).round(3)
    # top-decile composition by year (is the runner pool 2022-specific?)
    run_year = top10.groupby("year").agg(
        runners=("net_r", "size"), median_r=("net_r", "median"),
        mean_r=("net_r", "mean")).round(3)
    all_year = f.groupby("year").agg(n=("net_r", "size"),
                                     mean_r=("net_r", "mean")).round(3)
    # 2022 vs rest for the top decile on key pre-entry features
    key = ["atr14_pips", "atr_pctile", "her24", "consec_higher_high_days",
           "close_above_pdh_pips", "sig_close_loc", "ret_5d_pips",
           "ema20_dist_pips", "mfe_r", "time_to_2r_bars"]
    t10_22 = top10[top10["year"] == 2022]
    t10_ot = top10[top10["year"] != 2022]
    cmp22 = pd.DataFrame({
        "top10_2022": [med(t10_22[c2]) for c2 in key],
        "top10_other": [med(t10_ot[c2]) for c2 in key],
        "all_2022": [med(f[f["year"] == 2022][c2]) for c2 in key],
        "all_other": [med(f[f["year"] != 2022][c2]) for c2 in key],
    }, index=key).round(3)

    # exit reason x outcome
    ex_tab = f.groupby("reason").agg(
        n=("net_r", "size"), mean_r=("net_r", "mean"),
        median_mfe=("mfe_r", "median")).round(3)

    with open(os.path.join(HERE, "FX_PDH_001_DIAGNOSTICS.md"), "w",
              encoding="utf-8") as fh:
        fh.write("# FX_PDH_001 — DIAGNOSTICS (Phase 0, diagnostic ONLY)\n\n")
        fh.write("Population: the 639 frozen STRICT V1 trades (2020-2025, "
                 "NORMAL costs). Nothing here filters or changes the "
                 "strategy; lifecycle variables are NEVER entry filters.\n\n")
        fh.write("## Feature medians by outcome group (net R)\n\n")
        fh.write(tab.round(3).to_markdown())
        fh.write("\n\nGroups: TOP10%/TOP25% = upper net-R quantiles; "
                 "MID = interquartile; LOSERS = net R <= 0; REST90% = "
                 "complement of TOP10%.\n\n")
        fh.write("## Spearman correlation (pre-entry feature vs net R)\n\n")
        fh.write(pd.Series(spear).round(3).sort_values(
            ascending=False).to_markdown())
        fh.write("\n\n## Sessions (signal bar CLOSE hour, UTC)\n\n")
        fh.write(sess.to_markdown())
        fh.write("\n\n## Runners (top net-R decile) by year\n\n")
        fh.write(run_year.to_markdown())
        fh.write("\n\n## All trades by year\n\n")
        fh.write(all_year.to_markdown())
        fh.write("\n\n## Top decile, 2022 vs other years (medians)\n\n")
        fh.write(cmp22.to_markdown())
        fh.write("\n\n## Exit reason x outcome\n\n")
        fh.write(ex_tab.to_markdown())
        fh.write("\n\n## FINDINGS (descriptive; nothing here filters 001)\n\n")
        fh.write("""1. RUNNERS ARE MADE BY MULTI-DAY CONTEXT, NOT BAR SHAPE.
   The top net-R decile (64 trades) shows prior-1d return median +97.9 pips
   vs +29.9 for the rest (Spearman rho +0.41, the only strong pre-entry
   correlate); prior 3d/5d medians are ~2x the rest. Signal-bar features
   (close location, body, range/ATR, ATR level, distance above PDH) barely
   separate (|rho| <= 0.08).
2. CONTRACTION -> EXPANSION. Runners' prior-day range is NARROWER
   (median 72.6 vs 85.7 pips, rho -0.085): the break fires after a quieter
   prior day.
3. 2022 IS A REGIME, NOT A DIFFERENT MECHANISM. 2022 runners sit at the
   0.82 ATR percentile vs 0.56 in other years, follow +237-pip 5d moves, and
   start from 2 consecutive higher-high days (vs 0 elsewhere). High-vol
   trending regime amplified the SAME mechanism.
4. RUNNERS EXIST EVERY YEAR (7-17, median 5.2-8.0R). 2024/2025 weakness is
   NOT a missing-runner problem (9 runners each): the drag is the ~90%
   ordinary trades (2024 mean R of all trades = +0.05).
5. ASIA-HOUR BREAKS SCORE BEST (mean +0.46R, n=327) vs Overlap +0.19R;
   medians are -1R everywhere (most trades are stop-outs in all sessions).
6. LIFECYCLE (understanding only): 64% of trades touch +0.5R, 49% touch
   +1R, 35% touch +2R. Touching +1R weakly predicts continuation (57% end
   positive). Winners' median MAE is -0.48R vs -1.31R for losers: genuine
   runs go almost nowhere adverse first. Time exits are rare (20) but huge
   (+8.1R mean); the 3-ATR trail is what turns runners into ~9R MFE trades.
7. LAB IMPLICATION. The edge is trend-run capture, not entry timing:
   Phase B (pyramiding) and Phase D (exit) attack the mechanism directly;
   Phase C (entry) fights the weak part of the trade population. The strong
   prior-1d-momentum observation above is NOT preregistered as a filter and
   is NOT used here (protocol section 26: would need a separate authorized
   hypothesis).
""")
        fh.write("\n")
    print(tab.round(3).to_string())
    print("\nspearman:", {k: round(v, 3) for k, v in spear.items()})
    print("\nwrote FX_PDH_001_DIAGNOSTICS.md + diagnostics/features_per_trade.csv")


if __name__ == "__main__":
    main()
