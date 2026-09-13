#!/usr/bin/env python3
"""TICK-M1 STAGE A Discovery screen.

Runs EXACTLY the 13 frozen configurations of TICK_M1_FROZEN_HYPOTHESES.md
(6 hypotheses, no others) over the Discovery window 2010-01 .. 2018-12,
month by month, and writes tick_m1_results.json with ALL configurations
reported (no cherry-picking), BH-FDR sanity q-values, and gate decisions.
"""
import argparse
import json
import os
import subprocess
import sys
import time

import numpy as np

import data_root
import microstructure_lib as ml

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

# FROZEN inventory — the complete and only set (see hypotheses doc, section
# "Configuration inventory"). Modifying this list violates the freeze.
CONFIGS = [
    ("H1a", {"kind": "H1", "horizon_ns": ml.S10}),
    ("H1b", {"kind": "H1", "horizon_ns": ml.S30}),
    ("H1c", {"kind": "H1", "horizon_ns": ml.S60}),
    ("H2a", {"kind": "H2", "horizon_ns": ml.S30}),
    ("H2b", {"kind": "H2", "horizon_ns": ml.S60}),
    ("H3a", {"kind": "H3", "horizon_ns": ml.S30}),
    ("H3b", {"kind": "H3", "horizon_ns": ml.S60}),
    ("H4a", {"kind": "H4", "horizon_ns": ml.S30}),
    ("H4b", {"kind": "H4", "horizon_ns": ml.S60}),
    ("H5a", {"kind": "H5", "horizon_ns": ml.S30}),
    ("H5b", {"kind": "H5", "horizon_ns": ml.S60}),
    ("H6a", {"kind": "H6", "horizon_ns": ml.S30}),
    ("H6b", {"kind": "H6", "horizon_ns": ml.S60}),
]


def iter_months(start=(2010, 1), end_excl=(2019, 1)):
    y, m = start
    while (y, m) < end_excl:
        yield y, m
        m += 1
        if m == 13:
            y, m = y + 1, 1


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--symbol", default="EURUSD")
    ap.add_argument("--start", default="2010-01")
    ap.add_argument("--end", default="2019-01", help="YYYY-MM exclusive")
    ap.add_argument("--data-root", default=None)
    ap.add_argument("--out", default=os.path.join(os.path.dirname(__file__),
                                                  "tick_m1_results.json"))
    args = ap.parse_args()

    root = data_root.resolve_data_root(args.data_root)
    pdir = os.path.join(root, "parquet")
    sy, sm = (int(x) for x in args.start.split("-"))
    ey, em = (int(x) for x in args.end.split("-"))
    assert (sy, sm) >= (2010, 1) and (ey, em) <= (2019, 1), \
        "discovery window must stay inside 2010-01 .. 2019-01 exclusive"

    acc = {name: {"net": [], "gross": [], "year": [], "tod": [], "is_long": [],
                  "n_raw": 0, "n_skipped": 0} for name, _ in CONFIGS}
    t0 = time.time()
    months_done = 0
    for (y, m) in iter_months((sy, sm), (ey, em)):
        d = ml.load_month_padded(pdir, args.symbol, y, m)
        if d["ts"].size:
            feat = ml.compute_features(d)
            for name, cfg in CONFIGS:
                ev = ml.build_events(feat, d, cfg)
                a = acc[name]
                if ev is None:
                    continue
                a["n_raw"] += ev["n_raw"]
                a["n_skipped"] += ev.get("n_skipped_no_exit", 0)
                if ev["n_nonoverlap"]:
                    a["net"].append(ev["net"])
                    a["gross"].append(ev["gross"])
                    a["year"].append(ev["year"])
                    a["tod"].append(ev["tod"])
                    a["is_long"].append(ev["is_long"])
            months_done += 1
            print(f"{y}-{m:02d}: ticks={d['ts'].size} elapsed={time.time()-t0:.0f}s",
                  flush=True)
        del d

    results = []
    for name, cfg in CONFIGS:
        a = acc[name]
        if a["net"]:
            ev = {"n_raw": a["n_raw"], "n_skipped_no_exit": a["n_skipped"],
                  "n_nonoverlap": sum(len(x) for x in a["net"]),
                  "net": np.concatenate(a["net"]),
                  "gross": (np.concatenate(a["gross"])
                            if any(g is not None for g in a["gross"]) else None),
                  "year": np.concatenate(a["year"]),
                  "tod": np.concatenate(a["tod"]),
                  "is_long": np.concatenate(a["is_long"])}
        else:
            ev = {"n_raw": a["n_raw"], "n_skipped_no_exit": a["n_skipped"],
                  "n_nonoverlap": 0}
        results.append(ml.config_metrics(name, cfg, ev))

    # multiple-testing sanity check across ALL tested configs
    pvals = [r.get("one_sided_p", 1.0) for r in results]
    qvals = ml.bh_fdr(pvals)
    for r, q in zip(results, qvals):
        r["bh_q"] = round(float(q), 5)

    passing = [r for r in results if r["pass_gate"]]
    passing.sort(key=lambda r: (-r["mean_net_pips"], -r["positive_years"],
                                -r["n_nonoverlap"]))
    ranked = sorted(results, key=lambda r: -r["mean_net_pips"])

    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO,
                          capture_output=True, text=True).stdout.strip()
    out = {
        "mission": "TICK_M1_MICROSTRUCTURE_DISCOVERY",
        "stage": "A",
        "symbol": args.symbol,
        "data_root": root,
        "discovery_range": [args.start, args.end + " (exclusive)"],
        "git_head": head,
        "frozen_hypotheses": "research/tick_m1_microstructure/TICK_M1_FROZEN_HYPOTHESES.md",
        "n_configs": len(CONFIGS),
        "months_processed": months_done,
        "elapsed_sec": round(time.time() - t0, 1),
        "results": results,
        "ranked_by_mean_net": [r["config"] for r in ranked],
        "candidates_passing_gate": [r["config"] for r in passing],
        "final_status": ("CANDIDATES_FOUND" if passing
                         else "NO_MICROSTRUCTURE_CANDIDATE"),
    }
    with open(args.out, "w") as f:
        json.dump(out, f, indent=2)
    print("\n=== RANKED (all configs, frozen primary metric = mean net pips) ===")
    for r in ranked:
        gate = "PASS" if r["pass_gate"] else "-"
        print(f"{r['config']:>4} net={r.get('mean_net_pips', float('nan')):+.3f} "
              f"posYr={r.get('positive_years', '-')}/9 N={r.get('n_nonoverlap', 0)} "
              f"rb1%={r.get('remove_best_1pct_mean', float('nan')):+.3f} "
              f"s010={r.get('stress_net_010_per_side', float('nan')):+.3f} "
              f"p={r.get('one_sided_p', 1.0):.2g} q={r.get('bh_q', 1.0):.2g} {gate}")
    print("FINAL_STATUS =", out["final_status"])
    print("CANDIDATES  =", out["candidates_passing_gate"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
