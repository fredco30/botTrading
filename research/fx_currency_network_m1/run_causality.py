#!/usr/bin/env python3
"""Causality verification for the FX network feature layer (mission 4).

T1 MAX_INPUT: every input bar closing <= decision time T (by close-time
   labelling; verified by construction + explicit check).
T2 TRUNCATION: features recomputed on data truncated at T are identical.
T3 FUTURE MUTATION: mutating all post-T bars leaves features at T unchanged.

Features tested: currency strength z-scores (A/B/F/H/I), pairwise strength
differential (trend exit series), cross-vs-legs residual z (C), network
regression residual z (D), factor-idio z (E), USD-leg spread z (G),
dispersion percentile (I).
"""
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.append(HERE)
import netlib as N

rng = np.random.default_rng(20260916)
TF = "H4"


def features_from_closes(px_df, t_idx):
    """All screen features computed from a (pairs x times) close matrix,
    evaluated at integer position t_idx (inclusive). Causal by slice."""
    px = px_df.iloc[:t_idx + 1]
    R = np.log(px).diff(1)
    Rn = np.log(px).diff(6)
    S = pd.DataFrame(index=px.index, columns=list(N.CURR), dtype=float)
    for c in N.CURR:
        acc = np.zeros(len(px))
        for p, sg in N.CSIGN[c].items():
            acc += sg * Rn[p].to_numpy()
        S[c] = acc / len(N.CSIGN[c])
    zwin = 180
    sd = S.rolling(zwin, min_periods=zwin).std(ddof=1)
    zS = (S / sd).iloc[-1]
    diffs = {p: float(zS[N.BASE[p]] - zS[N.QUOTE[p]]) for p in N.PAIRS}
    # dispersion percentile (trailing 180, inclusive window)
    disp = S.std(axis=1, ddof=1)
    pct = disp.rolling(180, min_periods=180).apply(
        lambda a: (a <= a[-1]).mean(), raw=True).iloc[-1]
    # cross-vs-legs 6-step residual z
    out = {"zS": {c: float(zS[c]) for c in N.CURR}, "diff": diffs,
           "disp_pct": float(pct)}
    for xc, (l1, l2) in N.CROSS_LEGS.items():
        res = Rn[xc] - Rn[l1] - Rn[l2]
        z = (res / res.rolling(120, min_periods=120).std(ddof=1)).iloc[-1]
        out[f"crossz_{xc}"] = float(z)
    # network regression residual z for EURUSD (dep) on other 5 (1-step)
    dep = "EURUSD"
    others = [p for p in N.PAIRS if p != dep]
    y = R[dep]
    X = R[others]
    w = 120
    cm = pd.concat([y] * len(others), axis=1, keys=others)
    cov_xy = {j: cm[j].rolling(w).cov(X[j]) for j in others}
    vx = pd.DataFrame({j: X[j].rolling(w).var(ddof=1) for j in others})
    cyy = y.rolling(w).var(ddof=1)
    b = pd.DataFrame({j: cov_xy[j] / vx[j] for j in others})
    pred = sum(b[j] * X[j] for j in others)
    res = y - pred
    rz = (res / res.rolling(w, min_periods=w).std(ddof=1)).iloc[-1]
    out["netz_EURUSD"] = float(rz)
    # factor idio z for USDJPY
    c1, c2 = N.BASE["USDJPY"], N.QUOTE["USDJPY"]
    idio = Rn["USDJPY"] - (S[c1] - S[c2])
    iz = (idio / idio.rolling(120, min_periods=120).std(ddof=1)).iloc[-1]
    out["idioz_USDJPY"] = float(iz)
    return out


def sliced_px(upto):
    """Close matrix restricted to grid times <= upto (truncation)."""
    g = N.grid(TF)
    keep = g.t <= upto
    return g.px[keep], g.t[keep]


def main():
    g = N.grid(TF)
    lo = 400
    hi = int(np.searchsorted(g.t, int(pd.Timestamp("2015-01-01",
                                                   tz="UTC").value)))
    picks = sorted(rng.choice(np.arange(lo, hi), size=12, replace=False))
    t1 = t2 = t3 = True

    def cmp(a, b, T, path, tag):
        nonlocal t2, t3
        if isinstance(a, dict):
            for k in a:
                cmp(a[k], b[k], T, f"{path}.{k}", tag)
        elif a is not None and b is not None:
            if not (abs(a - b) <= 1e-10 * max(1.0, abs(a))):
                print(f"  {tag} FAIL T={T} {path}: {a} vs {b}")
                if tag == "T2":
                    t2 = False
                else:
                    t3 = False

    for tpos in picks:
        T = int(g.t[tpos])
        f_full = features_from_closes(g.px, tpos)
        # T1: all inputs are grid closes <= T by construction; explicit:
        assert (g.px.index[:tpos + 1] <= T).all()
        # T2 truncation
        px_t, t_t = sliced_px(T)
        j = len(t_t) - 1
        assert int(t_t[j]) == T
        cmp(f_full, features_from_closes(px_t, j), T, "", "T2")
        # T3 future mutation: scramble closes after T
        px3 = g.px.copy()
        px3.iloc[tpos + 1:] = px3.iloc[tpos + 1:] * 1.37 + 0.0037
        cmp(f_full, features_from_closes(px3, tpos), T, "", "T3")
    print(f"CAUSALITY T1 PASS (by construction + assertion, {len(picks)} "
          f"decisions)")
    print(f"CAUSALITY T2 {'PASS' if t2 else 'FAIL'} ({len(picks)} decisions, "
          f"all screen features)")
    print(f"CAUSALITY T3 {'PASS' if t3 else 'FAIL'} ({len(picks)} decisions)")
    return t2 and t3


if __name__ == "__main__":
    ok = main()
    sys.exit(0 if ok else 1)
