#!/usr/bin/env python3
"""P013R V1 frozen validation library.

Rule is FROZEN (P013R_V1_FROZEN_SPEC.md): last FX trading day of each month,
LONG XJPY, entry = daily close of that day, exit = daily close of the next
trading day, costs NORMAL 2 pips / STRESS 4 pips round trip, equal-weight
pooling on the COMMON event table, USDJPY+EURJPY+GBPJPY.

Window V1 = [2019-01-01 00:00 UTC, 2023-01-01 00:00 UTC) — STRICT frontier
censoring: an event whose exit close falls at/after the V1 end (e.g. the
December 2022 month-end exiting in January 2023) is DROPPED. No V2 price may
contribute.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
for _p in (HERE, _ROOT,
           os.path.join(_ROOT, "research", "phenomena_discovery_v1")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import p000_lib as P            # noqa: E402  (OOS-defensive loader, pip sizes)
import phase2_lib as P2         # noqa: E402  (paired/year-block bootstraps)

V1_START = pd.Timestamp("2019-01-01 00:00", tz="UTC")
V1_END = pd.Timestamp("2023-01-01 00:00", tz="UTC")      # exclusive
COST_NORMAL = 2.0
COST_STRESS = 4.0
PAIRS = ("USDJPY", "EURJPY", "GBPJPY")


def v1_daily_close(sym):
    """Daily closes STRICTLY inside V1 (load_5m enforces the OOS protection;
    here we additionally drop everything at/after V1_END)."""
    df = P.load_5m(sym)
    df = df[(df.index >= V1_START) & (df.index < V1_END)]
    return df["close"].resample("1D").last().dropna()


def month_end_events(px, pip):
    """Per-pair month-end returns with STRICT frontier censoring.

    An event is kept only if BOTH the entry close and the exit close are
    strictly inside V1 — a December month-end whose next trading day falls in
    January 2023 is censored (dropped)."""
    day = np.asarray(px.index.date)
    out = []
    for i in range(len(px) - 1):
        same_month = (px.index[i + 1].year, px.index[i + 1].month) == \
                     (px.index[i].year, px.index[i].month)
        if same_month:
            continue                          # not the last day of the month
        if not (px.index[i] >= V1_START and px.index[i + 1] < V1_END):
            continue                          # frontier censored
        out.append({"event_date": day[i], "exit_date": day[i + 1],
                    "gross": float(px.iloc[i + 1] - px.iloc[i]) / pip})
    return out


def per_pair_event_map(sym):
    """{event_date: event dict} for one pair, using ITS OWN calendar."""
    evs = month_end_events(v1_daily_close(sym), P.PIP[sym])
    return {e["event_date"]: e for e in evs}


def build_common_table():
    """Common event table: dates valid for ALL three pairs (own calendars,
    dates intersected — never index one pair with another pair's calendar)."""
    maps = {s: per_pair_event_map(s) for s in PAIRS}
    common = sorted(set(maps[PAIRS[0]]) & set(maps[PAIRS[1]]) & set(maps[PAIRS[2]]))
    rows = []
    for d in common:
        row = {"event_date": d, "exit_date": maps[PAIRS[0]][d]["exit_date"]}
        for s in PAIRS:
            g = maps[s][d]["gross"]
            row[f"{s}_GROSS"] = g
            row[f"{s}_NET_NORMAL"] = g - COST_NORMAL
            row[f"{s}_NET_STRESS"] = g - COST_STRESS
        row["POOLED_GROSS"] = float(np.mean([row[f"{s}_GROSS"] for s in PAIRS]))
        row["POOLED_NET_NORMAL"] = row["POOLED_GROSS"] - COST_NORMAL
        row["POOLED_NET_STRESS"] = row["POOLED_GROSS"] - COST_STRESS
        rows.append(row)
    return pd.DataFrame(rows)


def paired_stats(mat, cost=COST_NORMAL, n_boot=2000, seed=42):
    """Paired bootstrap (unit = whole event row, 2000, seed 42).
    Returns pooled means, CIs (gross + net at `cost`), and p-values."""
    pb = P2.paired_bootstrap_means(mat, n_boot, seed)
    pb_net = pb - cost
    p_gross = 2 * min(float(np.mean(pb <= 0)), float(np.mean(pb >= 0)))
    p_net = 2 * min(float(np.mean(pb_net <= 0)), float(np.mean(pb_net >= 0)))
    return {
        "gross_mean": round(float(mat.mean()), 2),
        "ci95_gross": [round(float(np.percentile(pb, 2.5)), 2),
                       round(float(np.percentile(pb, 97.5)), 2)],
        "ci95_net": [round(float(np.percentile(pb_net, 2.5)), 2),
                     round(float(np.percentile(pb_net, 97.5)), 2)],
        "p_gross": round(min(p_gross, 1.0), 3),
        "p_net": round(min(p_net, 1.0), 3),
    }


def year_block_ci(mat, years, cost=COST_NORMAL, n_boot=2000, seed=42):
    yb = P2.year_block_bootstrap_means(mat, years, n_boot, seed)
    return {"ci95_gross": [round(float(np.percentile(yb, 2.5)), 2),
                           round(float(np.percentile(yb, 97.5)), 2)],
            "ci95_net": [round(float(np.percentile(yb, 2.5)) - cost, 2),
                         round(float(np.percentile(yb, 97.5)) - cost, 2)]}


def frozen_classify(pooled_net_normal, pairs_gross_positive,
                    remove_best_event_net, ci_low_net_normal):
    """FROZEN verdict criteria (P013R_V1_FROZEN_SPEC.md — written before the
    V1 run; do not modify)."""
    structural_ok = (pooled_net_normal > 0 and pairs_gross_positive >= 2
                     and remove_best_event_net > 0)
    if not structural_ok:
        return "V1_REJECT"
    if ci_low_net_normal > 0:
        return "V1_STRONG_CONFIRMATION"
    return "V1_SUPPORTIVE_BUT_WEAK"
