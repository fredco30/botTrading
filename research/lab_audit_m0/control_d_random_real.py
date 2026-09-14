#!/usr/bin/python3
"""LAB_AUDIT_M0 — Control D: randomized real-market signals (spec section 4).

Fixed causal timestamps: 10:00 Europe/London, every Mon-Fri 2010-01-04 ..
2018-12-31 (same frozen list as controls E/F). Baseline execution semantics:
real BID/ASK, 5 s entry delay (30 s fill bound), side-correct exit at
decision+65 min (60 s quote bound), NO artificial slippage.

100 direction randomizations, seeds 4200..4299 (frozen in spec):
perm i uses np.random.default_rng(4200+i), direction drawn per eligible day
in chronological order.

Pre-registered PASS gates: grand mean < 0 pips; P95 of perm means <= +0.5
pips; #perms with PF > 1.20 <= 15 (of 100).

This script also validates the fast quote extractor against PO3.execute()
on every 11th eligible day, both directions, far stop (frozen rule) —
a production-vs-audit cross-check reported as extractor_validation.
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
SEC = AL.SEC
PIP_GATE = 3.0          # oracle materiality (E/F), frozen in spec
FAR_STOP_PIPS = 500.0   # validation far stop


def collect_quotes():
    days = PO3.discovery_dates()          # 2010-01-04..2018-12-31 Mon-Fri
    elig_days, elig_q = AL.day_eligibility_and_quotes(days)
    return elig_days, elig_q


def validate_extractor(days, quotes, every=11):
    """Cross-check extractor vs PO3.execute() on a frozen 1-in-11 subsample
    (deterministic: eligible-day index % 11 == 0), both directions. Days are
    chronological; the covering month partition is (re)loaded on change."""
    n_checked = 0
    mism = []
    cur_mkey = None
    ts = bid = ask = None
    for idx, (d, q) in enumerate(zip(days, quotes)):
        if idx % every != 0:
            continue
        mkey = (d.year, d.month)
        if mkey != cur_mkey:
            m0 = int(np.datetime64(f"{d.year:04d}-{d.month:02d}", "M")
                     .astype("datetime64[ns]").astype(np.int64))
            m1 = int((np.datetime64(f"{d.year:04d}-{d.month:02d}", "M")
                      + np.timedelta64(1, "M")).astype("datetime64[ns]")
                     .astype(np.int64)) - 1
            ts, bid, ask = AL.load_range(m0, m1)
            cur_mkey = mkey
        dec = AL.london_ns(d, 10, 0)
        if len(ts) == 0:
            continue
        for drc in (+1, -1):
            stop = (q["bid_e"] - FAR_STOP_PIPS * PIP) if drc > 0 else \
                   (q["ask_e"] + FAR_STOP_PIPS * PIP)
            ex = PO3.execute(ts, bid, ask, drc, stop, dec,
                             AL.ENTRY_DELAY_NS, dec + AL.EXIT_REF_NS)
            ok = (ex.status == "TRADE" and ex.entry_ts == q["entry_ts"]
                  and ex.exit_ts == q["exit_ts"])
            if drc > 0:
                ok = ok and ex.entry_px == q["ask_e"] and ex.exit_px == q["bid_x"]
            else:
                ok = ok and ex.entry_px == q["bid_e"] and ex.exit_px == q["ask_x"]
            if not ok:
                mism.append({"day": str(d), "dir": drc, "status": ex.status})
        n_checked += 1
    return {"n_days_checked": n_checked, "n_mismatches": len(mism),
            "mismatches": mism[:10], "PASS": len(mism) == 0}


def main() -> dict:
    days, quotes = collect_quotes()
    ask_e = np.array([q["ask_e"] for q in quotes])
    bid_e = np.array([q["bid_e"] for q in quotes])
    ask_x = np.array([q["ask_x"] for q in quotes])
    bid_x = np.array([q["bid_x"] for q in quotes])
    mid_e = 0.5 * (ask_e + bid_e)
    mid_x = 0.5 * (ask_x + bid_x)
    n = len(days)

    long_net = (bid_x - ask_e) / PIP
    short_net = (bid_e - ask_x) / PIP

    val = validate_extractor(days, quotes)

    # ---- 100 direction randomizations ----
    perm_means, perm_pfs, perm_profit = [], [], []
    for i in range(100):
        rng = np.random.default_rng(4200 + i)
        dirs = np.where(rng.integers(0, 2, size=n) == 1, 1, -1)
        nets = np.where(dirs > 0, long_net, short_net)
        perm_means.append(float(nets.mean()))
        perm_pfs.append(PO3.profit_factor(nets))
        perm_profit.append(bool(nets.mean() > 0))
    perm_means = np.array(perm_means)
    perm_pfs = np.array(perm_pfs)

    d_res = {
        "control": "D_random_real",
        "n_days_discovery": len(PO3.discovery_dates()),
        "n_eligible_days": n,
        "seeds": [4200 + i for i in range(100)],
        "n_perms": 100,
        "mean_of_perm_means_pips": float(perm_means.mean()),
        "median_of_perm_means_pips": float(np.median(perm_means)),
        "p05_of_perm_means_pips": float(np.percentile(perm_means, 5)),
        "p95_of_perm_means_pips": float(np.percentile(perm_means, 95)),
        "mean_pf": float(perm_pfs.mean()),
        "median_pf": float(np.median(perm_pfs)),
        "max_pf": float(perm_pfs.max()),
        "n_profitable_perms": int(sum(perm_profit)),
        "n_pf_gt_1p20": int((perm_pfs > 1.20).sum()),
        "avg_spread_at_entry_pips": float(((ask_e - bid_e) / PIP).mean()),
        "gates": {
            "grand_mean_negative": bool(perm_means.mean() < 0),
            "p95_le_0p5_pip": bool(np.percentile(perm_means, 95) <= 0.5),
            "n_pf_gt_1p20_le_15": bool((perm_pfs > 1.20).sum() <= 15),
        },
        "PASS": False,
    }
    d_res["PASS"] = all(d_res["gates"].values())

    # ---- E/F oracle (same frozen timestamps; separate oracle function) ----
    move = mid_x - mid_e
    gate3 = np.abs(move) >= PIP_GATE * PIP
    oracle_dir = np.where(move > 0, 1, -1)

    def oracle_nets(directions):
        nets = np.where(directions > 0, long_net, short_net)
        keep = gate3.copy()
        return nets[keep], int(keep.sum())

    e_nets, n_e = oracle_nets(oracle_dir)
    f_nets, n_f = oracle_nets(-oracle_dir)

    e_res = {
        "control": "E_lookahead_oracle (ORACLE_LOOKAHEAD_INVALID)",
        "pip_gate": PIP_GATE,
        "n_days_used": n_e,
        "mean_pips": float(e_nets.mean()),
        "median_pips": float(np.median(e_nets)),
        "profit_factor": PO3.profit_factor(e_nets),
        "win_rate": float((e_nets > 0).mean()),
        "gates": {
            "mean_gt_5_pips": bool(e_nets.mean() > 5.0),
            "pf_gt_2": bool(PO3.profit_factor(e_nets) > 2.0),
        },
        "PASS": False,
    }
    e_res["PASS"] = all(e_res["gates"].values())

    f_res = {
        "control": "F_anti_oracle",
        "n_days_used": n_f,
        "mean_pips": float(f_nets.mean()),
        "median_pips": float(np.median(f_nets)),
        "profit_factor": PO3.profit_factor(f_nets),
        "win_rate": float((f_nets > 0).mean()),
        "gates": {
            "mean_lt_minus5_pips": bool(f_nets.mean() < -5.0),
            "pf_lt_0p5": bool(PO3.profit_factor(f_nets) < 0.5),
        },
        "PASS": False,
    }
    f_res["PASS"] = all(f_res["gates"].values())

    return {"D": d_res, "E": e_res, "F": f_res,
            "extractor_validation": val,
            "PASS": bool(d_res["PASS"] and e_res["PASS"] and f_res["PASS"]
                         and val["PASS"])}


if __name__ == "__main__":
    r = main()
    (Path(__file__).parent / "RESULTS_def.json").write_text(json.dumps(r, indent=1))
    print(json.dumps(r, indent=1))
    print("CONTROL_DEF_PASS" if r["PASS"] else "CONTROL_DEF_FAIL")
