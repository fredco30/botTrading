#!/usr/bin/env python3
"""Analyse EVENT_STUDY_RESULTS.json: horizon table, significance, stability."""
import json
import os

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
R = json.load(open(os.path.join(HERE, "EVENT_STUDY_RESULTS.json")))

print("=== ALL HORIZONS (all events, by pair/tf) ===")
for key, r in R.items():
    print(f"\n{key}  n={r['n_events']}  ({r['events_per_week']:.1f}/wk)")
    for lab, st in r["by_horizon"].items():
        if st["n"] == 0:
            continue
        ci = st["ci95"]
        sig = "*" if (ci[0] == ci[0] and (ci[0] > 0 or ci[1] < 0)) else " "
        print(f"  {lab:>6}: mean={st['mean_pips']:+7.3f} med={st['median_pips']:+7.3f} "
              f"win={st['win_rate']:.3f} se={st['se_pips']:.3f} "
              f"ci=[{ci[0]:+.2f},{ci[1]:+.2f}]{sig} rb1%={st['rm_best1pct']:+7.3f} "
              f"mfe={st['mfe_pips'] or 0:+7.2f} mae={st['mae_pips'] or 0:+7.2f}")

print("\n=== MID-HORIZON BY YEAR (mean pips) ===")
keys = list(R.keys())
hdr = "key          " + "".join(f"{y:>9}" for y in range(2020, 2026)) + "      D21      V23      R25"
print(hdr)
for key in keys:
    r = R[key]
    row = f"{key:13}"
    for y in range(2020, 2026):
        st = r["by_year_mid"].get(str(y), {})
        m = st.get("mean_pips")
        row += f"{m:+9.3f}" if m is not None else f"{'n/a':>9}"
    b = r["by_block_mid"]
    for blk in ("D_2020_2021", "V_2022_2023", "R_2024_2025"):
        row += f"{b[blk].get('mean_pips', 0):+9.3f}"
    print(row)

print("\n=== MID-HORIZON BY SIDE (mean pips, win) ===")
for key in keys:
    s = R[key]["by_side_mid"]
    lo, sh = s["long"], s["short"]
    print(f"{key:13} long : n={lo.get('n',0):>5} mean={lo.get('mean_pips',0):+.3f} win={lo.get('win_rate',0):.3f}"
          f"   short: n={sh.get('n',0):>5} mean={sh.get('mean_pips',0):+.3f} win={sh.get('win_rate',0):.3f}")

print("\n=== T-STATS at every horizon ===")
for key in keys:
    row = f"{key:13}"
    for lab, st in R[key]["by_horizon"].items():
        if st["n"]:
            t = st["mean_pips"] / st["se_pips"] if st["se_pips"] else 0
            row += f" {lab}:{t:+.2f}"
    print(row)
