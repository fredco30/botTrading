#!/usr/bin/env python3
"""TRI-TICK-M0 feasibility run: EURUSD/GBPUSD/EURGBP reference week
2018-06-04 00:00 .. 2018-06-09 00:00 UTC (exclusive).

Data-only diagnostics: feed quality, causal synchronization on fixed UTC
grids, triangular mid residual, executable cycle bounds, descriptive
lead/lag cross-correlations, event-level sanity examples. No strategy,
no PnL, no 2019+ access.

Usage:
  BOTTRADING_TICK_DATA_ROOT=E:/ResearchData/botTrading/ticks \
      python run_feasibility.py [--out-dir <dir>]
"""
import argparse
import json
import os
import sys
from datetime import date

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tri_lib
from tri_lib import (MS, PIP, SYMBOLS, build_snapshots, grid_series,
                     load_symbol_week, pct)

DAYS = [(2018, 6, d) for d in (4, 5, 6, 7, 8)]
START_NS = tri_lib.hour_start_ns(2018, 6, 4, 0)
END_NS = tri_lib.hour_start_ns(2018, 6, 9, 0)
GRIDS_MS = [100, 250, 500, 1000]
AGE_BUCKETS_MS = [100, 250, 500, 1000]
LAGS_MS = [-2000, -1000, -500, -250, -100, 0, 100, 250, 500, 1000, 2000]
N_HOURS_EXPECTED = len(DAYS) * 24


def feed_quality(sym, arrays, audit, point):
    ts = arrays["timestamp_ns"]
    spread = tri_lib.spread_stats_pips(arrays["bid"], arrays["ask"])
    tpm = tri_lib.ticks_per_min_stats(ts)
    n_ok = sum(1 for e in audit if e["status"] == "ok")
    ask_lt_bid = int(np.sum(arrays["ask"] < arrays["bid"])) if len(ts) else 0
    non_mono = int(np.sum(np.diff(ts) < 0)) if len(ts) > 1 else 0
    neg_vol = int(np.sum((arrays["ask_volume"] < 0) | (arrays["bid_volume"] < 0))) if len(ts) else 0
    lo, hi = tri_lib.PLAUSIBLE[sym]
    invalid_px = int(np.sum((arrays["bid"] < lo) | (arrays["bid"] > hi))) if len(ts) else 0
    return {
        "symbol": sym,
        "point_scaling": point,
        "N_TICKS": int(len(ts)),
        "FIRST_TICK_UTC": np.datetime_as_string(ts[:1].astype("datetime64[ns]")[0], unit="ms").astype(str) if len(ts) else None,
        "LAST_TICK_UTC": np.datetime_as_string(ts[-1:].astype("datetime64[ns]")[0], unit="ms").astype(str) if len(ts) else None,
        "HOURLY_FILES_EXPECTED": N_HOURS_EXPECTED,
        "HOURLY_FILES_PRESENT": n_ok + sum(1 for e in audit if e["status"] == "empty"),
        "EMPTY_MARKERS": sum(1 for e in audit if e["status"] == "empty"),
        "MISSING_FILES": sum(1 for e in audit if e["status"] == "missing"),
        "CORRUPT_FILES": sum(1 for e in audit if e["status"] == "corrupt"),
        "MEDIAN_SPREAD_PIPS": spread["median"],
        "P95_SPREAD_PIPS": spread["p95"],
        "P99_SPREAD_PIPS": spread["p99"],
        "MAX_SPREAD_PIPS": spread["max"],
        "MEDIAN_TICKS_PER_MINUTE": tpm["median"],
        "P95_TICKS_PER_MINUTE": tpm["p95"],
        "ASK_LT_BID_COUNT": ask_lt_bid,
        "NON_MONOTONIC_TS_COUNT": non_mono,
        "NEGATIVE_VOLUME_COUNT": neg_vol,
        "INVALID_PRICE_COUNT": invalid_px,
    }


def sync_stats(snap):
    ages = snap["max_age_ms"]
    out = {
        "N_SNAPSHOTS": int(len(ages)),
        "P50_MAX_QUOTE_AGE_MS": pct(ages, 50),
        "P95_MAX_QUOTE_AGE_MS": pct(ages, 95),
        "P99_MAX_QUOTE_AGE_MS": pct(ages, 99),
        "fraction_all_age_le": {
            str(b): float(np.mean(ages <= b)) for b in AGE_BUCKETS_MS},
        "per_pair": {
            s: {
                "P50_AGE_MS": pct(snap[f"age_{s}_ms"], 50),
                "P95_AGE_MS": pct(snap[f"age_{s}_ms"], 95),
                "frac_age_le_500ms": float(np.mean(snap[f"age_{s}_ms"] <= 500)),
            } for s in SYMBOLS},
        "in_session_frac_max_age_le_60s": float(np.mean(ages <= 60_000)),
        "in_session_fraction_all_age_le": {
            str(b): float(np.mean(ages[ages <= 60_000] <= b)) for b in AGE_BUCKETS_MS},
    }
    return out


def lead_lag_series(snap, full_grid):
    """Place snapshot mids on the full uniform grid; NaN where missing."""
    idx = np.searchsorted(full_grid, snap["grid_ns"])
    valid = (idx < len(full_grid)) & (snap["grid_ns"] == full_grid[np.clip(idx, 0, len(full_grid) - 1)])
    s = {k: np.full(len(full_grid), np.nan) for k in ("mid_EURUSD", "mid_GBPUSD", "mid_EURGBP", "max_age_ms")}
    iv = idx[valid]
    for k in s:
        s[k][iv] = snap[k][np.flatnonzero(valid)]
    return s


def diff_valid(x):
    """Diff where both endpoints are finite, else NaN (keeps grid alignment)."""
    d = np.full(len(x), np.nan)
    m = np.isfinite(x[:-1]) & np.isfinite(x[1:])
    d[1:][m] = x[1:][m] - x[:-1][m]
    return d


def pick_events(snap, top=10, min_gap_s=60, max_age=250):
    r = np.abs(snap["resid_pips"])
    cand = np.flatnonzero((snap["max_age_ms"] <= max_age))
    cand = cand[np.argsort(-r[cand], kind="stable")]
    chosen = []
    for i in cand:
        if all(abs(snap["grid_ns"][i] - snap["grid_ns"][j]) >= min_gap_s * 1_000_000_000
               for j in chosen):
            chosen.append(int(i))
        if len(chosen) == top:
            break
    out = []
    for i in chosen:
        out.append({
            "timestamp_utc": str(np.datetime_as_string(snap["grid_ns"][i].astype("datetime64[ns]"), unit="ms")),
            "EURUSD_bid": snap["bid_EURUSD"][i], "EURUSD_ask": snap["ask_EURUSD"][i],
            "GBPUSD_bid": snap["bid_GBPUSD"][i], "GBPUSD_ask": snap["ask_GBPUSD"][i],
            "EURGBP_bid": snap["bid_EURGBP"][i], "EURGBP_ask": snap["ask_EURGBP"][i],
            "AGE_EURUSD_MS": snap["age_EURUSD_ms"][i], "AGE_GBPUSD_MS": snap["age_GBPUSD_ms"][i],
            "AGE_EURGBP_MS": snap["age_EURGBP_ms"][i],
            "TRI_RESIDUAL_MID_PIPS": snap["resid_pips"][i],
            "CYCLE_A": snap["cycle_A"][i], "CYCLE_B": snap["cycle_B"][i],
        })
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-root", default=None)
    ap.add_argument("--out-dir", default=os.path.dirname(os.path.abspath(__file__)))
    args = ap.parse_args()
    root = os.path.abspath(args.data_root or os.environ["BOTTRADING_TICK_DATA_ROOT"])
    print(f"data_root={root}", flush=True)

    feeds, quality, points = {}, {}, {}
    for sym in SYMBOLS:
        t, audit, pt = load_symbol_week(root, sym, DAYS)
        feeds[sym] = t
        points[sym] = pt
        quality[sym] = feed_quality(sym, t, audit, pt)
        print(f"{sym}: n={quality[sym]['N_TICKS']} point={pt} "
              f"missing={quality[sym]['MISSING_FILES']} corrupt={quality[sym]['CORRUPT_FILES']} "
              f"empty={quality[sym]['EMPTY_MARKERS']}", flush=True)

    # ---------------------------------------------- synchronization grids ---
    sync_results, resid_results, cycle_results, episode_results = {}, {}, {}, {}
    snaps = {}
    for step in GRIDS_MS:
        grid = grid_series(START_NS, END_NS, step)
        snap = build_snapshots(feeds, grid)
        snaps[step] = snap
        sync_results[step] = sync_stats(snap)
        resid_results[step] = {"ALL": tri_lib.resid_stats_pips(snap["resid_pips"])}
        for b in AGE_BUCKETS_MS:
            m = snap["max_age_ms"] <= b
            resid_results[step][f"age_le_{b}ms"] = tri_lib.resid_stats_pips(snap["resid_pips"], m)
        cycle_results[step] = {}
        for label, m in [("ALL", np.ones(len(snap["grid_ns"]), dtype=bool))] + \
                        [(f"age_le_{b}ms", snap["max_age_ms"] <= b) for b in AGE_BUCKETS_MS]:
            cycle_results[step][label] = {
                "A": tri_lib.cycle_stats_bp(snap["cycle_A"], m),
                "B": tri_lib.cycle_stats_bp(snap["cycle_B"], m),
            }
        if step in (100, 250):
            episode_results[step] = {
                "A": tri_lib.positive_episode_durations_ns(snap["cycle_A"], snap["grid_ns"]),
                "B": tri_lib.positive_episode_durations_ns(snap["cycle_B"], snap["grid_ns"]),
            }
        print(f"grid {step}ms: n={sync_results[step]['N_SNAPSHOTS']} "
              f"p95age={sync_results[step]['P95_MAX_QUOTE_AGE_MS']:.0f}ms", flush=True)

    # ---------------------------------------------------------- lead/lag ---
    full100 = grid_series(START_NS, END_NS, 100)
    s = lead_lag_series(snaps[100], full100)
    d = {k: diff_valid(s[k]) for k in ("mid_EURUSD", "mid_GBPUSD", "mid_EURGBP")}
    synth = s["mid_EURGBP"] * s["mid_GBPUSD"]
    d["SYNTH"] = diff_valid(synth)
    pair_defs = [
        ("dEURUSD_vs_dSYNTH", "mid_EURUSD", "SYNTH"),
        ("dEURUSD_vs_dGBPUSD", "mid_EURUSD", "mid_GBPUSD"),
        ("dEURUSD_vs_dEURGBP", "mid_EURUSD", "mid_EURGBP"),
        ("dGBPUSD_vs_dEURGBP", "mid_GBPUSD", "mid_EURGBP"),
    ]
    leadlag = {}
    for name, a, b in pair_defs:
        leadlag[name] = [{"lag_ms": lag, "corr": c, "n": n}
                         for lag, c, n in tri_lib.lead_lag_corr(d[a], d[b], LAGS_MS, 100)]
    main_tbl = leadlag["dEURUSD_vs_dSYNTH"]
    finite = [r for r in main_tbl if np.isfinite(r["corr"])]
    strongest = max(finite, key=lambda r: abs(r["corr"])) if finite else {"lag_ms": None, "corr": None}

    # ------------------------------------------------------------- events --
    events = pick_events(snaps[250])

    # --------------------------------------------------------------- gate --
    bad_files = {sym: quality[sym]["MISSING_FILES"] + quality[sym]["CORRUPT_FILES"]
                 for sym in SYMBOLS}
    feed_pass = {sym: (quality[sym]["CORRUPT_FILES"] == 0
                       and quality[sym]["ASK_LT_BID_COUNT"] == 0
                       and quality[sym]["NON_MONOTONIC_TS_COUNT"] == 0
                       and quality[sym]["NEGATIVE_VOLUME_COUNT"] == 0
                       and quality[sym]["INVALID_PRICE_COUNT"] == 0)
                 for sym in SYMBOLS}
    bad_rate = max(bad_files.values()) / N_HOURS_EXPECTED
    sync250 = sync_results[250]
    frac500 = sync250["fraction_all_age_le"]["500"]
    resid_all = resid_results[250]["ALL"]["p95_abs"]
    resid_250 = resid_results[250]["age_le_250ms"]["p95_abs"]
    tight_naturally = resid_all <= 1.0  # "already naturally tight" (<1 pip p95)
    residual_ok = (resid_250 < resid_all) or tight_naturally
    # coherence: no persistent absurd cycle return (> 50bp typical = scale bug)
    cycA = cycle_results[250]["ALL"]["A"]
    cycB = cycle_results[250]["ALL"]["B"]
    coherent = abs(cycA["max_bp"]) < 50 and abs(cycB["max_bp"]) < 50
    gate_pass = all(feed_pass.values()) and bad_rate <= 0.01 and frac500 >= 0.50 \
        and residual_ok and coherent

    results = {
        "mission": "TRI_TICK_M0_FEASIBILITY",
        "base_head": "def3a943dfdd9ee0c59249080e5c1318815b11ae",
        "sample_range_utc": ["2018-06-04T00:00:00Z", "2018-06-09T00:00:00Z"],
        "data_root": root,
        "feed_quality": quality,
        "sync": {str(k): v for k, v in sync_results.items()},
        "residual_pips": {str(k): v for k, v in resid_results.items()},
        "cycles_bp": {str(k): v for k, v in cycle_results.items()},
        "episodes": {str(step): {c: {
            "count": int(len(episode_results[step][c])),
            "median_ms": pct(episode_results[step][c], 50) / 1e6 if len(episode_results[step][c]) else None,
            "p95_ms": pct(episode_results[step][c], 95) / 1e6 if len(episode_results[step][c]) else None,
            "max_ms": float(episode_results[step][c].max()) / 1e6 if len(episode_results[step][c]) else None,
        } for c in ("A", "B")} for step in episode_results},
        "lead_lag_100ms": leadlag,
        "lead_lag_sign_convention": "corr(dLEG1[t], dLEG2[t+lag]); lag>0 => LEG1 leads LEG2",
        "lead_lag_strongest_fixed_lag": strongest,
        "events_top10_abs_resid": events,
        "gate": {
            "feed_pass": feed_pass,
            "bad_file_rate": bad_rate,
            "frac_all_age_le_500ms_250grid": frac500,
            "resid_p95_abs_all_250grid": resid_all,
            "resid_p95_abs_age_le_250ms_250grid": resid_250,
            "residual_shrinks_with_staleness_control": bool(resid_250 < resid_all),
            "cycles_coherent": bool(coherent),
            "TRI_TICK_M0_PASS": bool(gate_pass),
        },
        "2019_plus_accessed": False,
        "protected_oos_accessed": False,
    }
    out_json = os.path.join(args.out_dir, "tri_tick_m0_results.json")
    with open(out_json, "w") as f:
        json.dump(results, f, indent=2, default=float)
    print(f"wrote {out_json}", flush=True)
    print("GATE " + json.dumps(results["gate"]), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
