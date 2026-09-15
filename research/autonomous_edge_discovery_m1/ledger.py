import numpy as np
#!/usr/bin/env python3
"""AUTONOMOUS_EDGE_DISCOVERY_M1 — ledger with HARD budget counter on disk.
Budget: 150 experiments / 20 families (mission 10). Experiment #150 allowed,
#151 never executed."""
import csv
import os

HERE = os.path.dirname(os.path.abspath(__file__))
LEDGER = os.path.join(HERE, "RESEARCH_LEDGER.csv")
COUNTER = os.path.join(HERE, "EXPERIMENT_COUNTER.txt")
FAMILY_COUNTER = os.path.join(HERE, "FAMILY_COUNTER.txt")
MAX_EXP = 150
MAX_FAMILIES = 20

COLUMNS = ["experiment_id", "family_id", "mechanism", "feature_causality_pass",
           "parameters", "N", "mean_pips", "PF", "expectancy_R", "stress_pips",
           "remove_best_pips", "status", "reason"]


def _count(path):
    return int(open(path).read().strip()) if os.path.exists(path) else 0


def next_exp_id():
    n = _count(COUNTER) + 1
    if n > MAX_EXP:
        raise RuntimeError(f"HARD BUDGET STOP: experiment #{n} > {MAX_EXP}")
    with open(COUNTER, "w") as f:
        f.write(str(n))
    return f"E{n:03d}"


def register_family(family_id):
    fams = set()
    if os.path.exists(FAMILY_COUNTER):
        fams = set(open(FAMILY_COUNTER).read().split())
    if family_id not in fams:
        if len(fams) >= MAX_FAMILIES:
            raise RuntimeError(f"HARD BUDGET STOP: family {family_id} exceeds {MAX_FAMILIES}")
        fams.add(family_id)
        with open(FAMILY_COUNTER, "w") as f:
            f.write("\n".join(sorted(fams)))
    return len(fams)


def experiments_used():
    return _count(COUNTER)


def log(family_id, mechanism, causality_pass, parameters, N=np.nan,
        mean_pips=np.nan, PF=np.nan, expectancy_R=np.nan, stress_pips=np.nan,
        remove_best_pips=np.nan, status="SCREEN", reason=""):
    row = dict(experiment_id=next_exp_id(), family_id=family_id,
               mechanism=mechanism, feature_causality_pass=causality_pass,
               parameters=parameters, N=N, mean_pips=_r(mean_pips), PF=_r(PF),
               expectancy_R=_r(expectancy_R), stress_pips=_r(stress_pips),
               remove_best_pips=_r(remove_best_pips), status=status,
               reason=reason)
    new = not os.path.exists(LEDGER)
    with open(LEDGER, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        if new:
            w.writeheader()
        w.writerow(row)
    return row


def _r(x):
    try:
        if x is None:
            return ""
        v = float(x)
        if v != v or v in (float("inf"), float("-inf")):
            return ""
        return round(v, 4)
    except (TypeError, ValueError):
        return x
