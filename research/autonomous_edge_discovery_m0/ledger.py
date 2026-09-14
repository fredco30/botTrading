#!/usr/bin/env python3
"""Shared ledger + screen reporting for AUTONOMOUS_EDGE_DISCOVERY_M0."""
import csv
import os
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
LEDGER = os.path.join(HERE, "RESEARCH_LEDGER.csv")
COUNTER = os.path.join(HERE, "experiment_counter.txt")

COLUMNS = ["experiment_id", "family_id", "mechanism", "parameters", "N",
           "mean_pips", "PF", "expectancy_R", "stress_R", "remove_best",
           "status", "reason"]


def next_exp_id():
    n = 1
    if os.path.exists(COUNTER):
        with open(COUNTER) as f:
            n = int(f.read().strip()) + 1
    with open(COUNTER, "w") as f:
        f.write(str(n))
    return f"E{n:03d}"


def log(family_id, mechanism, parameters, N, mean_pips, PF=np.nan,
        expectancy_R=np.nan, stress_R=np.nan, remove_best=np.nan,
        status="SCREEN", reason=""):
    row = dict(experiment_id=next_exp_id(), family_id=family_id,
               mechanism=mechanism, parameters=parameters, N=N,
               mean_pips=_r(mean_pips), PF=_r(PF), expectancy_R=_r(expectancy_R),
               stress_R=_r(stress_R), remove_best=_r(remove_best),
               status=status, reason=reason)
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
        if np.isnan(v) or np.isinf(v):
            return ""
        return round(v, 4)
    except (TypeError, ValueError):
        return x


def fwd_table(cond, b, horizons=(15, 30, 60, 120), label="", min_pips=None,
              nonoverlap=True, cost_rt=0.7):
    """Vectorized conditional forward-return screen.
    cond: bool array over M1 bars (decision at bar close, causal).
    Entry proxy: next bar open. Exit: close of bar i+h. Mid-to-mid.
    Returns {h: (n, mean, t, n_no, mean_no, t_no)} with optional
    non-overlapping greedy subsample."""
    close, opn = b["close"], b["open"]
    n = len(close)
    idx = np.flatnonzero(cond)
    res = {}
    for h in horizons:
        j0 = np.minimum(idx + 1, n - 1)
        j1 = np.minimum(idx + h, n - 1)
        r = (close[j1] - opn[j0]) / 1e-4
        if nonoverlap:
            keep = []
            last = -10**9
            for k, i in enumerate(idx):
                if i >= last + h:
                    keep.append(k)
                    last = i
            keep = np.array(keep, dtype=int)
        else:
            keep = np.arange(len(idx))
        rr, r_keep = r, r[keep]
        res[h] = _stats(idx, r_keep)
    return res


def _stats(idx, r):
    n = len(r)
    if n == 0:
        return (0, np.nan, np.nan)
    mean = float(r.mean())
    sd = float(r.std(ddof=1))
    t = mean / (sd / np.sqrt(n)) if n > 1 and sd > 0 else np.nan
    return (n, round(mean, 3), round(float(t), 2))


def show(res, label):
    print(f"--- {label}")
    for h, (n, m, t) in res.items():
        print(f"  h={h:4d}m  N={n:6d}  mean={m if m is not None else float('nan'):8.3f}p  t={t}")
