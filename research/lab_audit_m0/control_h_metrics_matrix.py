#!/usr/bin/python3
"""LAB_AUDIT_M0 — Control H: metrics unit test matrix (spec section 7).

Hard-coded trades, all aggregates hand-computed:
  nets R = [+2.0, -1.0, +3.0, -1.0, +0.5, -0.5, +1.0, -1.0, +2.5, -1.0]
  sum = 4.5, mean = 0.45, median = 0.0 (sorted: -1,-1,-1,-1,-.5,.5,1,2,2.5,3)
  PF = 9.0/4.5 = 2.0 ; win rate = 0.5
  cumsum = 2,1,4,3,3.5,3,4,3,5.5,4.5 ; running peak dd path
           0,-1,0,-1,-0.5,-1,0,-1,0,-1  -> max DD = 1.0 R
  remove_best_1%: k = max(1, ceil(0.1)) = 1 -> drop +3.0 ->
           1.5/9 = 0.16666666666666666
  years: first 5 in 2015 (sum 3.5 > 0), last 5 in 2016 (sum 1.0 > 0) -> 2/2
  long/short split: first 5 long mean 0.7, last 5 short mean 0.2
Edge cases: zero losses -> PF = 999.0 cap ; zero wins -> PF = 0.0.
Units: r_mult = net_pips / (risk_price / PIP), verified against a real
recorded PO3 trade. Pip conversion verified against the store's
spread_pips column. Metrics computed by production PO3 functions AND
independent audit implementations (lab_audit_lib.m_*).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import lab_audit_lib as AL
import po3_base_m0_lib as PO3

PIP = AL.PIP
FAILS = []


def eq(name, a, b, tol=1e-9):
    ok = abs(a - b) <= tol
    if not ok:
        FAILS.append(f"{name}: got {a!r} want {b!r}")
    return ok


def main() -> dict:
    nets = np.array([2.0, -1.0, 3.0, -1.0, 0.5, -0.5, 1.0, -1.0, 2.5, -1.0])
    years = np.array([2015] * 5 + [2016] * 5)
    dirs = np.array([1, 1, 1, 1, 1, -1, -1, -1, -1, -1])

    # --- production vs hand-calc ---
    eq("H.mean", float(nets.mean()), 0.45)
    eq("H.median", float(np.median(nets)), 0.0)
    eq("H.total", float(nets.sum()), 4.5)
    eq("H.pf", PO3.profit_factor(nets), 2.0)
    eq("H.winrate", float((nets > 0).mean()), 0.5)
    eq("H.expectancy_r", float(nets.mean()), 0.45)
    eq("H.maxdd", PO3.max_drawdown_r(nets), 1.0)
    eq("H.remove_best_1pct", PO3.remove_best_1pct_mean(nets), 1.5 / 9.0)
    py = PO3.positive_years((years - 1970).astype("datetime64[Y]").astype("datetime64[ns]").astype(np.int64), nets)
    eq("H.positive_years", py[0], 2)
    eq("H.years_eligible", py[1], 2)
    eq("H.long_mean", float(nets[dirs > 0].mean()), 0.7)
    eq("H.short_mean", float(nets[dirs < 0].mean()), 0.2)

    # --- production vs independent implementations ---
    eq("H.ind.mean", AL.m_mean(nets), float(nets.mean()), 1e-12)
    eq("H.ind.median", AL.m_median(nets), float(np.median(nets)), 1e-12)
    eq("H.ind.total", AL.m_total(nets), float(nets.sum()), 1e-12)
    eq("H.ind.pf", AL.m_pf(list(nets)), PO3.profit_factor(nets), 1e-12)
    eq("H.ind.winrate", AL.m_win_rate(nets), float((nets > 0).mean()), 1e-12)
    eq("H.ind.maxdd", AL.m_max_dd(nets), PO3.max_drawdown_r(nets), 1e-12)
    eq("H.ind.remove_best", AL.m_remove_best_1pct(nets), PO3.remove_best_1pct_mean(nets), 1e-12)
    ind_py = AL.m_positive_years(list(years), list(nets))
    eq("H.ind.positive_years", ind_py[0], py[0])
    lo_p, hi_p = PO3.bootstrap_ci95_mean(nets)
    lo_i, hi_i = AL.m_bootstrap_ci(nets)
    eq("H.ind.bootstrap_lo", lo_i, lo_p)
    eq("H.ind.bootstrap_hi", hi_i, hi_p)
    if not (lo_p <= 0.45 <= hi_p):
        FAILS.append(f"H.bootstrap_mean_not_in_CI: [{lo_p}, {hi_p}]")
    # deterministic: identical across calls
    lo2, hi2 = PO3.bootstrap_ci95_mean(nets)
    if not (lo2 == lo_p and hi2 == hi_p):
        FAILS.append("H.bootstrap_not_deterministic")

    # --- PF edge cases ---
    eq("H.pf_zero_losses_cap", PO3.profit_factor(np.array([1.0, 2.0, 0.5])), 999.0)
    eq("H.pf_zero_wins", PO3.profit_factor(np.array([-1.0, -2.0])), 0.0)
    eq("H.ind.pf_zero_losses_cap", AL.m_pf([1.0, 2.0, 0.5]), 999.0)
    eq("H.ind.pf_zero_wins", AL.m_pf([-1.0, -2.0]), 0.0)

    # --- R denominator units + pip conversion on REAL recorded data ---
    trades = json.loads((Path(AL._REPO) / "research" / "po3_base_m0" /
                         "po3_base_m0_trades.json").read_text())
    t0 = trades[0]
    # r_mult must be net_pips / (risk_price / PIP) — i.e. pip units over pip units.
    recomputed = t0["net_pips"] / (t0["r_pips"])
    eq("H.r_mult_units", recomputed, t0["r_mult"], 1e-9)
    # and r_pips itself must be the price distance stop->entry converted at 1 pip = 1e-4
    recomputed_r_pips = abs(t0["entry_px"] - t0["stop"]) / PIP
    eq("H.r_pips_pip_conversion", recomputed_r_pips, t0["r_pips"], 1e-6)

    ts, bid, ask, mid, spread = AL.load_partition_raw(2014, 6)
    i = len(ts) // 2
    eq("H.store_pip_conversion", float((ask[i] - bid[i]) / PIP), float(spread[i]), 1e-9)
    del ts, bid, ask, mid, spread

    return {
        "control": "H_metrics_matrix",
        "failures": FAILS,
        "n_failures": len(FAILS),
        "PASS": len(FAILS) == 0,
    }


if __name__ == "__main__":
    r = main()
    (Path(__file__).parent / "RESULTS_h.json").write_text(json.dumps(r, indent=1))
    print(json.dumps(r, indent=1))
    print("CONTROL_H_PASS" if r["PASS"] else "CONTROL_H_FAIL")
