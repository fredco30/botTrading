#!/usr/bin/python3
"""LEGACY_REVERSE_M1 discovery runner — executes the frozen spec scenarios:
  H1 REVERSE_AFTER_STOP_RAW (base / latency30 / stress)
  H2 DIRECT_SIGNAL_INVERSION (base / latency30 / stress)
  T4 TEST04_LEGACY (base / stress) — historical benchmark only
Writes results JSON + per-trade CSVs. No parameter search. 2019+/OOS guarded.
"""
from __future__ import annotations

import csv
import json
import math
import sys
import time
from pathlib import Path

import numpy as np

import legacy_reverse_m1_lib as L
import po3_base_m0_lib as PO3

HERE = Path(__file__).parent
PF_CAP = 999.0


def scenario_metrics(records, original_r=None):
    tr = [r for r in records if r["status"] == "TRADE"]
    n = len(tr)
    out = {
        "TRIGGERS": len(records),
        "N_TRADES": n,
        "status_counts": {},
    }
    for r in records:
        out["status_counts"][r["status"]] = out["status_counts"].get(r["status"], 0) + 1
    if n == 0:
        return out
    pips = np.array([r["res"].net_pips for r in tr])
    rr = np.array([r["res"].r for r in tr])
    dirs = np.array([r["dir"] for r in tr])
    yrs = np.array([L.ns_to_server(r["res"].entry_ts).year for r in tr])
    wins = pips[pips > 0]
    losses = pips[pips <= 0]
    gross = float(wins.sum())
    loss_sum = float(losses.sum())
    years_eligible = sorted(set(int(y) for y in yrs))
    pos_years = sum(1 for y in years_eligible if float(pips[yrs == y].sum()) > 0)
    consec = mx = 0
    for p in pips:
        if p <= 0:
            consec += 1
            mx = max(mx, consec)
        else:
            consec = 0
    eq = np.cumsum(rr)
    peak = np.maximum.accumulate(np.concatenate(([0.0], eq)))
    dd = float(np.min(np.concatenate(([0.0], eq)) - peak))
    out.update({
        "TRADES_PER_MONTH": round(n / 108.0, 3),
        "TRADES_PER_YEAR": round(n / 9.0, 2),
        "WIN_RATE": round(100.0 * len(wins) / n, 2),
        "MEAN_NET_PIPS": round(float(pips.mean()), 3),
        "MEDIAN_NET_PIPS": round(float(np.median(pips)), 3),
        "TOTAL_NET_PIPS": round(float(pips.sum()), 2),
        "PROFIT_FACTOR": round(min(gross / abs(loss_sum), PF_CAP) if loss_sum != 0 else PF_CAP, 4),
        "EXPECTANCY_R": round(float(rr.mean()), 4),
        "AVG_WIN_R": round(float(rr[pips > 0].mean()) if len(wins) else 0.0, 4),
        "AVG_LOSS_R": round(float(rr[pips <= 0].mean()) if len(losses) else 0.0, 4),
        "MAX_DRAWDOWN_R": round(dd, 3),
        "MAX_CONSECUTIVE_LOSSES": mx,
        "POSITIVE_YEARS": pos_years,
        "YEARS_ELIGIBLE": len(years_eligible),
        "POSITIVE_YEAR_RATIO": round(pos_years / len(years_eligible), 3) if years_eligible else 0.0,
        "REMOVE_BEST_1_PERCENT_EXPECTANCY_R": round(PO3.remove_best_1pct_mean(rr), 4),
        "LONG_EXPECTANCY_R": round(float(rr[dirs > 0].mean()), 4) if (dirs > 0).any() else None,
        "SHORT_EXPECTANCY_R": round(float(rr[dirs < 0].mean()), 4) if (dirs < 0).any() else None,
    })
    lo, hi = PO3.bootstrap_ci95_mean(rr)
    out["BOOTSTRAP_CI95_EXPECTANCY_R"] = [round(lo, 4), round(hi, 4)]
    if original_r is not None and len(original_r) == n:
        a = np.asarray(original_r)
        if np.std(a) > 0 and np.std(rr) > 0:
            pear = float(np.corrcoef(a, rr)[0, 1])
            ra = np.argsort(np.argsort(a)).astype(float)
            rb = np.argsort(np.argsort(rr)).astype(float)
            spear = float(np.corrcoef(ra, rb)[0, 1])
        else:
            pear = spear = None
        out["CORRELATION_ORIGINAL_VS_INVERTED_OUTCOMES"] = {
            "pearson": None if pear is None else round(pear, 4),
            "spearman": None if spear is None else round(spear, 4),
            "note": "paired on executed trades only (NO_FILL excluded)",
        }
    return out


def candidate_gate(m):
    req = {
        "N>=100": m.get("N_TRADES", 0) >= 100,
        "E[R]>=+0.10": m.get("EXPECTANCY_R", -9) >= 0.10,
        "PF>=1.20": m.get("PROFIT_FACTOR", 0) >= 1.20,
        "TOTAL_NET_PIPS>0": m.get("TOTAL_NET_PIPS", -1) > 0,
        "POS_YEARS>=0.67": m.get("POSITIVE_YEAR_RATIO", 0) >= 0.67,
        "REMOVE_BEST>0": (m.get("REMOVE_BEST_1_PERCENT_EXPECTANCY_R") or -9) > 0,
        "LONG_R>0": (m.get("LONG_EXPECTANCY_R") is not None and m["LONG_EXPECTANCY_R"] > 0),
        "SHORT_R>0": (m.get("SHORT_EXPECTANCY_R") is not None and m["SHORT_EXPECTANCY_R"] > 0),
    }
    if "LATENCY_30S_EXPECTANCY_R" in m:
        req["LATENCY_30S>0"] = m["LATENCY_30S_EXPECTANCY_R"] > 0
    if "REALISTIC_STRESS_EXPECTANCY_R" in m:
        req["STRESS>0"] = m["REALISTIC_STRESS_EXPECTANCY_R"] > 0
    return req, all(req.values())


def trades_csv(path, records):
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["status", "dir", "orig_entry_time", "orig_exit_time", "orig_dir",
                    "t_stop_ns", "stop_confirmed", "entry_ts_ns", "entry_ref_px",
                    "entry_fill_px", "sl", "tp", "risk_pips", "exit_type",
                    "exit_ts_ns", "exit_px", "net_pips", "r", "be_moved"])
        for r in records:
            t0 = r["trigger"]["trade"]
            res = r.get("res")
            if res is None or res.entry_ts is None:
                w.writerow([r["status"], "", t0.entry_time, t0.exit_time, t0.dir,
                            r.get("t_stop_ns", ""), "", "", "", "", "", "", "",
                            "", "", "", "", "", ""])
                continue
            risk_pips = round(res.risk_dist / L.PIP, 2) if res.risk_dist else ""
            w.writerow([r["status"], r.get("dir", ""), t0.entry_time, t0.exit_time,
                        t0.dir, r.get("t_stop_ns", ""), r.get("confirmed", ""),
                        res.entry_ts, res.entry_px, res.entry_px_eff,
                        res.sl, res.tp, risk_pips,
                        res.exit_type, res.exit_ts, res.exit_px,
                        round(res.net_pips, 3) if res.net_pips is not None else "",
                        round(res.r, 5) if res.r is not None else "", res.be_moved])


def main():
    t0 = time.time()
    store = L.TickStore()
    ctx, base, pyr = L.build_canonical_streams()
    ident = L.verify_against_frozen_csv(base, pyr)
    print("identity:", ident, flush=True)
    if not (ident["baseline_identity"] and ident["pyramid_identity"]
            and 428 <= ident["n_baseline"] <= 430):
        print("FATAL: canonical stream does not match the frozen prior result "
              "(expected ~428-430 executed baseline trades). STOP AND DIAGNOSE.")
        sys.exit(2)

    h1_trg = L.h1_triggers(base)
    h2_trg = L.h2_triggers(base)
    t4_trg = L.t4_triggers(pyr)
    print(f"triggers: H1 L0-stops={len(h1_trg)}  H2 signals={len(h2_trg)}  "
          f"T4 pool={len(t4_trg)}", flush=True)

    results = {
        "SOURCE_SIGNALS": ident["n_baseline"],
        "identity_checks": ident,
        "H1_TRIGGERS": len(h1_trg),
        "H2_TRIGGERS": len(h2_trg),
        "T4_TRIGGERS": len(t4_trg),
    }

    original_r_hist = [t.r_mult for t in base.trades]
    VARIANTS = [("base", L.DELAY_BASE_NS, 0.0),
                ("lat30", L.DELAY_LATENCY_NS, 0.0),
                ("stress", L.DELAY_LATENCY_NS, L.SLIP_STRESS_PIPS)]

    # ---- H1 ----
    h1_runs = L.run_h1(store, ctx, h1_trg, base.trades, VARIANTS)
    m_base = scenario_metrics(h1_runs["base"])
    m_lat = scenario_metrics(h1_runs["lat30"])
    m_str = scenario_metrics(h1_runs["stress"])
    fills = [r["res"].entry_ts - r["t_stop_ns"] for r in h1_runs["base"]
             if r["status"] == "TRADE"]
    fallbacks = sum(1 for r in h1_runs["base"] if r["status"] == "TRADE"
                    and not r.get("confirmed", True))
    h1 = dict(m_base)
    h1["ORIGINAL_STOPPED_L0_N"] = len(h1_trg)
    h1["PCT_OF_STOPPED_L0_REVERSED"] = round(100.0 * m_base["N_TRADES"] / len(h1_trg), 2)
    h1["TIME_STOP_TO_REVERSE_FILL_MEDIAN_SEC"] = round(float(np.median(fills)) / 1e9, 3) if fills else None
    h1["STOP_TICK_FALLBACK_N"] = fallbacks
    h1["LATENCY_30S_EXPECTANCY_R"] = m_lat.get("EXPECTANCY_R")
    h1["LATENCY_30S_N"] = m_lat.get("N_TRADES")
    h1["REALISTIC_STRESS_EXPECTANCY_R"] = m_str.get("EXPECTANCY_R")
    h1["REALISTIC_STRESS_N"] = m_str.get("N_TRADES")
    results["H1_REVERSE_AFTER_STOP_RAW"] = h1
    results["H1_LATENCY_30S"] = m_lat
    results["H1_STRESS"] = m_str
    trades_csv(HERE / "h1_trades.csv", h1_runs["base"])
    print("H1 done:", json.dumps(h1, default=str)[:600], flush=True)

    # ---- H2 ----
    h2_runs = L.run_h2(store, h2_trg, VARIANTS)
    hm_base = scenario_metrics(h2_runs["base"], original_r=original_r_hist)
    hm_lat = scenario_metrics(h2_runs["lat30"])
    hm_str = scenario_metrics(h2_runs["stress"])
    h2 = dict(hm_base)
    h2["ORIGINAL_SIGNAL_EXPECTANCY_R"] = round(float(np.mean(original_r_hist)), 4)
    h2["INVERTED_SIGNAL_EXPECTANCY_R"] = hm_base.get("EXPECTANCY_R")
    h2["LATENCY_30S_EXPECTANCY_R"] = hm_lat.get("EXPECTANCY_R")
    h2["LATENCY_30S_N"] = hm_lat.get("N_TRADES")
    h2["REALISTIC_STRESS_EXPECTANCY_R"] = hm_str.get("EXPECTANCY_R")
    h2["REALISTIC_STRESS_N"] = hm_str.get("N_TRADES")
    results["H2_DIRECT_INVERSION"] = h2
    results["H2_LATENCY_30S"] = hm_lat
    results["H2_STRESS"] = hm_str
    trades_csv(HERE / "h2_trades.csv", h2_runs["base"])
    print("H2 done:", json.dumps(h2, default=str)[:600], flush=True)

    # ---- Test04 benchmark ----
    t4_runs = L.run_h1(store, ctx, t4_trg, pyr.trades, VARIANTS,
                       rev_max_sl_pips=25.0, consec_gate=3)
    tm_base = scenario_metrics(t4_runs["base"])
    tm_str = scenario_metrics(t4_runs["stress"])
    t4 = dict(tm_base)
    t4["REALISTIC_STRESS_EXPECTANCY_R"] = tm_str.get("EXPECTANCY_R")
    t4["REALISTIC_STRESS_PF"] = tm_str.get("PROFIT_FACTOR")
    t4["REALISTIC_STRESS_N"] = tm_str.get("N_TRADES")
    l0_rev = sum(1 for r in t4_runs["base"] if r["status"] == "TRADE" and r.get("level") == 0)
    l2_rev = sum(1 for r in t4_runs["base"] if r["status"] == "TRADE" and r.get("level") == 2)
    t4["L0_REVERSES"] = l0_rev
    t4["L2_REVERSES"] = l2_rev
    results["TEST04_LEGACY"] = t4
    trades_csv(HERE / "t4_trades.csv", t4_runs["base"])
    print("T4 done:", json.dumps(t4, default=str)[:600], flush=True)

    # ---- gates ----    (LATENCY/STRESS already injected above)
    for key in ("H1_REVERSE_AFTER_STOP_RAW", "H2_DIRECT_INVERSION"):
        m = results[key]
        req, passed = candidate_gate(m)
        m["GATE"] = {"requirements": req, "PASS": passed}
    results["H1_REVERSE_AFTER_STOP_RAW"]["VERDICT"] = \
        "REVERSE_AFTER_STOP_CANDIDATE" if results["H1_REVERSE_AFTER_STOP_RAW"]["GATE"]["PASS"] else "GATE_FAIL"
    results["H2_DIRECT_INVERSION"]["VERDICT"] = \
        "DIRECT_INVERSION_CANDIDATE" if results["H2_DIRECT_INVERSION"]["GATE"]["PASS"] else "GATE_FAIL"

    out = HERE / "legacy_reverse_m1_results.json"
    out.write_text(json.dumps(results, indent=1, default=str))
    print("wrote", out, f"elapsed {time.time()-t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
