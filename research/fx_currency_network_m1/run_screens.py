#!/usr/bin/env python3
"""FX_CURRENCY_NETWORK_M1 - phase 1 family screens (DISCOVERY fold only).

All parameters below are PRE-REGISTERED before any PnL was seen (broad,
normalized values per mission 13). Exit architecture per family chosen from
the economic mechanism BEFORE seeing PnL (mission 7):
  trend/continuation families  -> initial stop + 3xATR chandelier trail
                                  + signal-deterioration exit + 48h/24h max
  convergence families         -> initial stop + residual/differential
                                  back-to-neutral exit + 24h max
  lead-lag families            -> initial stop + catch-up-complete exit
                                  + short max hold
Families (mission 6): A continuation, B reversal, C lead-lag (2 mechs),
D network residual (2 mechs), E factor idio (2 mechs), F rank momentum,
G corr-break reconvergence, H session transfer, I dispersion regime,
J JPY-shock spillover (invented).
Screens evaluate DISCOVERY (2010-2014) only.
"""
import os
import sys
import time

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.append(HERE)
import netlib as N

CUT_D = int(pd.Timestamp(N.FOLDS["DISCOVERY"][1], tz="UTC").value)


def log_metrics(fam, mech, params, trades, stress_trades=None):
    ft = [t for t in trades if t["entry_ts"] < CUT_D]
    m = N.SW.pooled_metrics(ft, fam + "." + mech)
    tpw = round(m.get("N", 0) / N.weeks("DISCOVERY"), 2) if m.get("N") else 0.0
    stm = None
    if stress_trades is not None:
        fs = [t for t in stress_trades if t["entry_ts"] < CUT_D]
        stm = round(float(np.mean([t["net_pips"] for t in fs])), 3) if fs else None
    gate = N.discovery_gate(m)
    N.log(fam, mech, params, m, tpw, stm,
          "DISCOVERY_PASS" if gate else "DISCOVERY_FAIL")
    return m, ft


def strength_extremes(g, zS):
    vals = zS.to_numpy()
    fin = np.isfinite(vals).all(axis=1)
    amax = np.argmax(np.where(fin[:, None], vals, -9), axis=1)
    amin = np.argmin(np.where(fin[:, None], vals, 9), axis=1)
    ar = np.arange(len(vals))
    return fin, vals[ar, amax], vals[ar, amin], amax, amin


def pair_for(c1, c2):
    for p in N.PAIRS:
        if {N.BASE[p], N.QUOTE[p]} == {c1, c2}:
            return p
    return None


def mk_cand(sym, ts_i, side, g):
    a = float(g.atr_of(sym, np.array([ts_i]))[0])
    return {"ts": np.array([ts_i]), "side": np.array([side]),
            "stop_pips": np.array([2.0 * a]), "atr_pips": np.array([a])}


def merge_cands(blocks):
    out = {}
    for sym, lst in blocks.items():
        out[sym] = {k: np.array([b[k][0] for b in lst])
                    for k in ("ts", "side", "stop_pips", "atr_pips")}
    return out


def run_strength_family(g, zS, mask, fade=False, arch="trend"):
    """A/B/F/I core: extreme strongest-vs-weakest pair; direction or fade.
    Only the single extreme pair (mission 15). arch: 'trend' = stop + 3xATR
    chandelier + differential-sign exit + 48h; 'conv' = stop + differential
    back-to-neutral (|diff|<=0.5) exit + 24h."""
    fin, zmax, zmin, amax, amin = strength_extremes(g, zS)
    blocks = {}
    for i in np.flatnonzero(mask & fin):
        c1, c2 = N.CURR[amax[i]], N.CURR[amin[i]]
        p = pair_for(c1, c2)
        if p is None:
            continue
        s = 1 if N.BASE[p] == c1 else -1
        if fade:
            s = -s
        a = float(g.atr_of(p, np.array([g.t[i]]))[0])
        blocks.setdefault(p, []).append(
            {"ts": [g.t[i]], "side": [s], "stop_pips": [2.0 * a],
             "atr_pips": [a]})
    cands = merge_cands(blocks)
    trades = []
    for p, c in cands.items():
        diff = (zS[N.BASE[p]] - zS[N.QUOTE[p]]).to_numpy()
        if arch == "trend":
            tr = N.replay(p, g.tf, c, 2.0, 3.0, g.t, diff,
                          lambda s, v: (s == 1 and v < 0) or (s == -1 and v > 0),
                          48, "SIGNAL_EXIT")
        else:
            tr = N.replay(p, g.tf, c, 2.0, 0.0, g.t, diff,
                          lambda s, v: abs(v) <= 0.5, 24, "CONV_EXIT")
        trades += tr
    return trades


# ------------------------------------------------------------------ A + F
def screens_strength_continuation(g, zdict):
    for n, thr in ((6, 1.0), (6, 1.5), (12, 1.0), (12, 1.5)):
        zS = zdict[n]
        fin, zmax, zmin, _, _ = strength_extremes(g, zS)
        mask = (zmax >= thr) & (zmin <= -thr)
        tr = run_strength_family(g, zS, mask)
        log_metrics("CN-A", f"cont n={n*4}h thr={thr}",
                    {"lookback_h": n * 4, "z_thr": thr}, tr)


def screens_rank_momentum(g, zdict):
    for n in (6, 18, 36):
        zS = zdict[n]
        fin, zmax, zmin, _, _ = strength_extremes(g, zS)
        tr = run_strength_family(g, zS, fin)
        log_metrics("CN-F", f"rank n={n*4}h", {"lookback_h": n * 4}, tr)


# ------------------------------------------------------------------ B
def screens_strength_reversal(g, zdict):
    for n, thr in ((2, 2.0), (6, 2.5)):
        zS = zdict[n]
        fin, zmax, zmin, _, _ = strength_extremes(g, zS)
        mask = (zmax >= thr) & (zmin <= -thr)
        tr = run_strength_family(g, zS, mask, fade=True, arch="conv")
        log_metrics("CN-B", f"rev n={n*4}h thr={thr}",
                    {"lookback_h": n * 4, "z_thr": thr}, tr)


# ----------------------------------------------------------- residual z's
def roll_z(x, W):
    return x / x.rolling(W, min_periods=W).std(ddof=1)


def net_resid_z(g, W=120):
    """Causal multivariate rolling regression resid-z per pair (padded
    cumsum window sums; warmup rows NaN)."""
    R = g.ret(1)
    out = {}
    k = len(N.PAIRS) - 1
    for p in N.PAIRS:
        others = [q for q in N.PAIRS if q != p]
        # ret(1) warmup row 0 is NaN: zero it for the cumsum window sums,
        # then drop the first full window from the signal (res[:W] = NaN).
        X = np.nan_to_num(R[others].to_numpy(), nan=0.0)
        y = np.nan_to_num(R[p].to_numpy(), nan=0.0)
        T = len(y)
        Sc = np.zeros((T + 1, k, k))
        Sc[1:] = np.cumsum(np.einsum("ti,tj->tij", X, X), axis=0)
        bc = np.zeros((T + 1, k))
        bc[1:] = np.cumsum(X * y[:, None], axis=0)
        idx = np.arange(T)
        w0 = np.maximum(idx + 1 - W, 0)
        ok = idx + 1 >= W
        A = Sc[idx + 1] - Sc[w0]
        b = bc[idx + 1] - bc[w0]
        reg = np.zeros((T, k))
        if ok.any():
            Ai = A[ok]
            ridge = (1e-10 * np.trace(Ai, axis1=1, axis2=2)[:, None, None]
                     / k * np.eye(k))
            reg[ok] = np.linalg.solve(Ai + ridge, b[ok][:, :, None])[..., 0]
        res = y - (X * reg).sum(axis=1)
        res = pd.Series(res, index=g.t)
        res[np.arange(T) < W] = np.nan
        out[p] = roll_z(res, W)
    return out


def idio_z(g, n, W=120):
    Rn = g.ret(n)
    S = g.strength(n)
    out = {}
    for p in N.PAIRS:
        idio = Rn[p] - (S[N.BASE[p]] - S[N.QUOTE[p]])
        out[p] = roll_z(idio, W)
    return out


def run_residual_family(g, zmap, k, mech, fam, max_hold, exit_level=0.5,
                        trend=False, tag=""):
    blocks = {}
    for p, zs in zmap.items():
        v = zs.to_numpy()
        fire = np.isfinite(v) & (np.abs(v) >= k)
        for i in np.flatnonzero(fire):
            s = int(np.sign(v[i]))          # direction of the residual move
            if mech == "conv":
                s = -s
            a = float(g.atr_of(p, np.array([g.t[i]]))[0])
            blocks.setdefault(p, []).append(
                {"ts": [g.t[i]], "side": [s], "stop_pips": [2.0 * a],
                 "atr_pips": [a]})
    trades = []
    for p, c in merge_cands(blocks).items():
        if trend:
            tr = N.replay(p, g.tf, c, 2.0, 3.0, g.t, zmap[p].to_numpy(),
                          lambda s, v: (s == 1 and v < 0) or (s == -1 and v > 0),
                          max_hold, "SIGNAL_EXIT")
        else:
            tr = N.replay(p, g.tf, c, 2.0, 0.0, g.t, zmap[p].to_numpy(),
                          lambda s, v: abs(v) <= exit_level,
                          max_hold, "CONV_EXIT")
        trades += tr
    return trades


# ------------------------------------------------------------------ C
def cross_resid_z(g, n, W=120):
    Rn = g.ret(n)
    out = {}
    for xc, (l1, l2) in N.CROSS_LEGS.items():
        res = Rn[xc] - Rn[l1] - Rn[l2]
        out[xc] = roll_z(res, W)
    return out


def screens_leadlag(gH1):
    for n in (6, 12):
        zc = cross_resid_z(gH1, n)
        # C1: cross overshoot -> converge back to legs
        blocks = {}
        for xc, zs in zc.items():
            v = zs.to_numpy()
            for i in np.flatnonzero(np.isfinite(v) & (np.abs(v) >= 1.5)):
                s = -int(np.sign(v[i]))
                a = float(gH1.atr_of(xc, np.array([gH1.t[i]]))[0])
                blocks.setdefault(xc, []).append(
                    {"ts": [gH1.t[i]], "side": [s], "stop_pips": [2.0 * a],
                     "atr_pips": [a]})
        tr = []
        for p, c in merge_cands(blocks).items():
            tr += N.replay(p, "H1", c, 2.0, 0.0, gH1.t, zc[p].to_numpy(),
                           lambda s, v: abs(v) <= 0.5, 24, "CONV_EXIT")
        log_metrics("CN-C", f"C1 crossconv n={n}h k=1.5", {"n_h": n, "k": 1.5}, tr)
        # C2: cross leads, legs lag -> trade legs in cross direction
        blocks = {}
        for xc, zs in zc.items():
            v = zs.to_numpy()
            for i in np.flatnonzero(np.isfinite(v) & (np.abs(v) >= 1.5)):
                s = int(np.sign(v[i]))
                for leg in N.CROSS_LEGS[xc]:
                    a = float(gH1.atr_of(leg, np.array([gH1.t[i]]))[0])
                    blocks.setdefault(leg, []).append(
                        {"ts": [gH1.t[i]], "side": [s],
                         "stop_pips": [2.0 * a], "atr_pips": [a]})
        tr = []
        for p, c in merge_cands(blocks).items():
            xc = [x for x, lg in N.CROSS_LEGS.items() if p in lg][0]
            tr += N.replay(p, "H1", c, 2.0, 0.0, gH1.t, zc[xc].to_numpy(),
                           lambda s, v: abs(v) <= 0.25 * 1.5, 12, "LAG_EXIT")
        log_metrics("CN-C", f"C2 legslag n={n}h k=1.5", {"n_h": n, "k": 1.5}, tr)


# ------------------------------------------------------------------ G
def screens_corr_break(gH1):
    for n in (12, 24):
        Rn = gH1.ret(n)
        sp = Rn["EURUSD"] - Rn["GBPUSD"]
        z = roll_z(sp, 120)
        v = z.to_numpy()
        blocks = {"EURGBP": []}
        for i in np.flatnonzero(np.isfinite(v) & (np.abs(v) >= 1.5)):
            s = int(np.sign(v[i]))   # EUR outperformed GBP -> EURGBP up
            a = float(gH1.atr_of("EURGBP", np.array([gH1.t[i]]))[0])
            blocks["EURGBP"].append(
                {"ts": [gH1.t[i]], "side": [s], "stop_pips": [2.0 * a],
                 "atr_pips": [a]})
        tr = N.replay("EURGBP", "H1", merge_cands(blocks)["EURGBP"], 2.0,
                      0.0, gH1.t, v, lambda s, vv: abs(vv) <= 0.5, 24,
                      "CONV_EXIT")
        log_metrics("CN-G", f"corrbrk n={n}h", {"n_h": n, "k": 1.5}, tr)


# ------------------------------------------------------------------ H
def screens_session(gH1):
    t = gH1.t
    hrs = (t // (3600 * N.NS)) % 24
    dates = (t // (86400 * N.NS)).astype(int)
    R1 = gH1.ret(1)
    S = gH1.strength(1)
    sess_vals, sess_ts = [], []
    dvals = {}
    for d in np.unique(dates):
        m = (dates == d) & (hrs >= 1) & (hrs <= 7)
        if m.sum() == 7 and (hrs[m] == np.arange(1, 8)).all():
            sv = S[m].sum(axis=0)
            dt = pd.Timestamp(int(t[m][-1]), unit="ns", tz="UTC")
            if dt.weekday() < 5:
                dvals[t[m][-1]] = sv
    sts = np.array(sorted(dvals))
    sdf = pd.DataFrame([dvals[x] for x in sts], index=sts,
                       columns=list(N.CURR))
    z = sdf / sdf.rolling(60, min_periods=60).std(ddof=1)
    zv = z.to_numpy()
    fin = np.isfinite(zv).all(axis=1)
    amax = np.argmax(np.where(fin[:, None], zv, -9), axis=1)
    amin = np.argmin(np.where(fin[:, None], zv, 9), axis=1)
    ar = np.arange(len(zv))
    fire = fin & (zv[ar, amax] >= 1.0) & (zv[ar, amin] <= -1.0)
    for variant, fade in (("cont", False), ("rev", True)):
        blocks = {}
        for i in np.flatnonzero(fire):
            c1, c2 = N.CURR[amax[i]], N.CURR[amin[i]]
            p = pair_for(c1, c2)
            if p is None:
                continue
            s = 1 if N.BASE[p] == c1 else -1
            if fade:
                s = -s
            a = float(gH1.atr_of(p, np.array([sts[i]]))[0])
            blocks.setdefault(p, []).append(
                {"ts": [sts[i]], "side": [s], "stop_pips": [2.0 * a],
                 "atr_pips": [a]})
        tr = []
        for p, c in merge_cands(blocks).items():
            tr += N.replay(p, "H1", c, 2.0, 0.0, None, None, None, 10,
                           "TIME_EXIT")
        log_metrics("CN-H", f"asia_{variant}", {"session": "asia",
                                                "mode": variant}, tr)


# ------------------------------------------------------------------ I
def screens_dispersion(g, zdict):
    n = 6
    S = g.strength(n)
    disp = S.std(axis=1, ddof=1)
    pct = disp.rolling(180, min_periods=180).apply(
        lambda a: (a <= a[-1]).mean(), raw=True)
    pv = pct.to_numpy()
    zS = zdict[n]
    up = np.isfinite(pv) & (pv >= 0.8)
    dn = np.isfinite(pv) & (pv <= 0.2)
    cross_up = up & ~np.roll(up, 1); cross_up[0] = False
    cross_dn = dn & ~np.roll(dn, 1); cross_dn[0] = False
    tr = run_strength_family(g, zS, cross_up)
    log_metrics("CN-I", "disp_hi_cont", {"pct": 0.8}, tr)
    fin, zmax, zmin, amax, amin = strength_extremes(g, zS)
    blocks = {}
    for i in np.flatnonzero(cross_dn & fin):
        c1, c2 = N.CURR[amax[i]], N.CURR[amin[i]]
        p = pair_for(c1, c2)
        if p is None:
            continue
        s = 1 if N.BASE[p] == c1 else -1
        a = float(g.atr_of(p, np.array([g.t[i]]))[0])
        blocks.setdefault(p, []).append(
            {"ts": [g.t[i]], "side": [-s], "stop_pips": [2.0 * a],
             "atr_pips": [a]})
    tr = []
    for p, c in merge_cands(blocks).items():
        diff = (zS[N.BASE[p]] - zS[N.QUOTE[p]]).to_numpy()
        tr += N.replay(p, "H4", c, 2.0, 0.0, g.t, diff,
                       lambda s, v: abs(v) <= 0.5, 24, "CONV_EXIT")
    log_metrics("CN-I", "disp_lo_conv", {"pct": 0.2}, tr)


# ------------------------------------------------------------------ J
def screens_jpy_shock(g):
    R3 = g.ret(3)["USDJPY"]
    sd = R3.rolling(120, min_periods=120).std(ddof=1)
    shock = R3.abs() >= 2.0 * sd
    blocks = {}
    for p in ("EURJPY", "GBPJPY"):
        for i in np.flatnonzero(shock.to_numpy()):
            s = int(np.sign(R3.to_numpy()[i]))
            a = float(g.atr_of(p, np.array([g.t[i]]))[0])
            blocks.setdefault(p, []).append(
                {"ts": [g.t[i]], "side": [s], "stop_pips": [2.0 * a],
                 "atr_pips": [a]})
    tr = []
    for p, c in merge_cands(blocks).items():
        tr += N.replay(p, "H4", c, 2.0, 3.0, g.t, R3.to_numpy(),
                       lambda s, v: (s == 1 and v < 0) or (s == -1 and v > 0),
                       24, "SIGNAL_EXIT")
    log_metrics("CN-J", "jpy_shock_spill", {"n": 3, "k": 2.0}, tr)


def main():
    t0 = time.time()
    g4 = N.grid("H4")
    gH1 = N.grid("H1")
    zdict4 = {n: g4.zstrength(n, 180) for n in (2, 6, 12, 18, 36)}
    print(f"grids ready H4={len(g4.t)} H1={len(gH1.t)} "
          f"({time.time()-t0:.0f}s)", flush=True)
    screens_strength_continuation(g4, zdict4)      # A  (4)
    screens_rank_momentum(g4, zdict4)              # F  (3)
    screens_strength_reversal(g4, zdict4)          # B  (2)
    screens_leadlag(gH1)                           # C  (4)
    znet = net_resid_z(g4)
    for mech in ("cont", "conv"):
        for k in (1.5, 2.0):
            tr = run_residual_family(g4, znet, k, mech, "CN-D",
                                     48 if mech == "cont" else 24,
                                     trend=(mech == "cont"))
            log_metrics("CN-D", f"netresid_{mech} k={k}", {"W": 120, "k": k}, tr)
    zid = idio_z(g4, 6)
    for mech in ("cont", "conv"):
        for k in (1.5, 2.0):
            tr = run_residual_family(g4, zid, k, mech, "CN-E",
                                     48 if mech == "cont" else 24,
                                     trend=(mech == "cont"))
            log_metrics("CN-E", f"idio_{mech} k={k}",
                        {"n": 6, "W": 120, "k": k}, tr)
    screens_corr_break(gH1)                        # G  (2)
    screens_session(gH1)                           # H  (2)
    screens_dispersion(g4, zdict4)                 # I  (2)
    screens_jpy_shock(g4)                          # J  (1)
    print(f"screens done {time.time()-t0:.0f}s, "
          f"experiments used: {N.experiments_used()}")


if __name__ == "__main__":
    main()
