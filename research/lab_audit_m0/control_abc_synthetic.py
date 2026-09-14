#!/usr/bin/python3
"""LAB_AUDIT_M0 — Controls A/B/C: synthetic positive / negative / zero edge
(spec sections 3 + frozen expectation table).

Pre-registered (spec, BEFORE execution):
  A: N=1000, p=0.65 -> net EV +0.22 R (+-0.08), PF > 1, CI95 lower > 0
  B: N=1000, p=0.35 -> net EV -0.38 R (+-0.08), PF < 1, CI95 upper < 0
  C: N=5000, p=0.50 -> net EV -0.08 R (+-0.04), PF < 1, est < 0
The normal pipeline (PO3.execute + PO3 metrics) must recover these.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import lab_audit_lib as AL
import po3_base_m0_lib as PO3


def run_control(name, n_trades, p_win, seed=42):
    ts, bid, ask, meta = AL.build_synthetic_stream(n_trades, p_win, seed=seed)
    nets, exit_types, statuses = [], {}, {}
    for m in meta:
        r = AL.run_synthetic_trade(ts, bid, ask, m)
        statuses[r["status"]] = statuses.get(r["status"], 0) + 1
        if r["status"] == "TRADE":
            nets.append(r["r_mult"])
            exit_types[r["exit_type"]] = exit_types.get(r["exit_type"], 0) + 1
    nets = np.array(nets)
    lo, hi = PO3.bootstrap_ci95_mean(nets)
    return {
        "control": name,
        "n_requested": n_trades,
        "n_traded": int(len(nets)),
        "status_counts": statuses,
        "exit_type_counts": exit_types,
        "p_win_design": p_win,
        "mean_r": float(nets.mean()),
        "median_r": float(np.median(nets)),
        "total_r": float(nets.sum()),
        "win_rate": float((nets > 0).mean()),
        "profit_factor": PO3.profit_factor(nets),
        "bootstrap_ci95": [lo, hi],
        "se_theoretical": 1.0 / np.sqrt(n_trades),
    }


def gate(name, r, ev_expected, tol, pf_is_gt, need_ci_lower_pos, need_est_negative):
    est = r["mean_r"]
    checks = {
        "n_all_traded": r["n_traded"] == r["n_requested"],
        "all_time_exits": set(r["exit_type_counts"]) == {"TIME"},
        "sign_correct": (est > 0) if ev_expected > 0 else (est < 0),
        f"within_tol_{tol}": abs(est - ev_expected) <= tol,
        "pf_sign": (r["profit_factor"] > 1) if pf_is_gt else (r["profit_factor"] < 1),
        "ci_lower_positive": r["bootstrap_ci95"][0] > 0 if need_ci_lower_pos else True,
        "ci_upper_negative": r["bootstrap_ci95"][1] < 0 if ev_expected < 0 and need_est_negative else True,
    }
    return checks


def main() -> dict:
    A = run_control("A_synthetic_positive", 1000, 0.65)
    B = run_control("B_synthetic_negative", 1000, 0.35)
    C = run_control("C_synthetic_zero", 5000, 0.50)

    ga = gate("A", A, +0.22, 0.08, True, True, False)
    gb = gate("B", B, -0.38, 0.08, False, False, True)
    gc = gate("C", C, -0.08, 0.04, False, False, True)

    A["gates"], B["gates"], C["gates"] = ga, gb, gc
    A["PASS"], B["PASS"], C["PASS"] = all(ga.values()), all(gb.values()), all(gc.values())
    return {
        "A": A, "B": B, "C": C,
        "PASS": bool(A["PASS"] and B["PASS"] and C["PASS"]),
    }


if __name__ == "__main__":
    r = main()
    (Path(__file__).parent / "RESULTS_abc.json").write_text(json.dumps(r, indent=1))
    print(json.dumps(r, indent=1))
    print("CONTROL_ABC_PASS" if r["PASS"] else "CONTROL_ABC_FAIL")
