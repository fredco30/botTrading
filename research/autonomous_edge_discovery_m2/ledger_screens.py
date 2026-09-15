#!/usr/bin/env python3
"""Recompute side-weighted pooled screen stats from screen_results.json
(the first run stored unweighted means; per-side cells are exact) and
ledger every screened config as an M2 experiment."""
import json

import numpy as np

import m2lib as M

R = json.load(open("screen_results.json"))
H = ("30", "60", "240")


def corrected(years):
    out = {}
    for h in H:
        cells = years[h]
        rows = []
        for y, c in cells.items():
            if not c or c["N"] < 5:
                continue
            nL, mL = c["L"]; nS, mS = c["S"]
            n = c["N"]
            mean_sw = ((nL * mL + nS * mS) / n) if (nL + nS) else np.nan
            rows.append((int(y), n, round(mean_sw, 3), mL, mS))
        if not rows:
            continue
        means = [m for _, _, m, _, _ in rows]
        nts = sum(n for _, n, _, _, _ in rows)
        pos = sum(1 for m in means if m > 0)
        Ls = [mL for _, _, _, mL, _ in rows if mL is not None]
        Ss = [mS for _, _, _, _, mS in rows if mS is not None]
        out[h] = {"N": nts, "posYR": f"{pos}/{len(means)}",
                  "meanYR": round(float(np.mean(means)), 3),
                  "minYR": round(float(np.min(means)), 3),
                  "maxYR": round(float(np.max(means)), 3),
                  "Lmean": round(float(np.mean(Ls)), 3) if Ls else None,
                  "Smean": round(float(np.mean(Ss)), 3) if Ss else None}
    return out


verdicts = {
    "F14a": ("REJECT", "mean ~0/neg, 3-4/8 pos years, L/S split sign-flips; sub-cost"),
    "F14b": ("REJECT", "mean neg at 30/60; h240 L/S opposite signs; not robust"),
    "F15a": ("REJECT", "negative all horizons, 2/8 pos years"),
    "F15b": ("REJECT", "N too small (437@30m), year means -3.6..+5.1, L/S sign flips by horizon"),
    "F16a": ("WEAK", "h240 ~+0.6p gross 5/8yr but year dispersion -4.1..+6.6 and S>>L; backup only"),
    "F17a": ("REJECT", "negative all horizons (mirror of F17b win = mechanism coherent)"),
    "F17b": ("ADVANCE", "h240 both sides +, 7/8 pos years, minYR -0.36; tick-exact replay next"),
    "F18a": ("REJECT", "mean ~0, 3-5/8, decays with horizon"),
    "F19a": ("REJECT", "h240 BOTH sides negative; adverse drift either way"),
    "F19b": ("REJECT", "h240 BOTH sides negative; same condition mirrored"),
    "F20a": ("REJECT", "mean ~0/neg, 2-4/8 pos years"),
}

for name, d in R["screen"].items():
    corr = corrected(d["years"])
    key = name.split()[0]
    status, reason = verdicts[key]
    h240 = corr.get("240", {})
    h30 = corr.get("30", {})
    M.log(d["mech"].split()[0].upper() if False else key,
          d["mech"], "PASS",
          f"{name}; screen fwd-mid h=30/60/240",
          N=h240.get("N", h30.get("N", np.nan)),
          mean_pips=h240.get("meanYR", np.nan),
          PF=np.nan, expectancy_R=np.nan,
          remove_best_pips=np.nan,
          status=status, reason=reason + f" | h240={h240} h30={h30}")

print("LEDGERED", M.experiments_used(), "experiments")
print("families:", M.families_used())
