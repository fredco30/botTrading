#!/usr/bin/env python3
"""RV screens: cheap causal screens on the DISCOVERY fold (2010-06..2015-01).

All signals continuous (no rare-extreme gates). Stop=target=2.5xATR(H4,14),
hold 24h for screens, MODELED_EXECUTION, one position per pair.
Screen promote bar (mission 17): pooled discovery N>=468 (>=2/wk),
PF>=1.20, expR>=+0.05, mean>=+3 pips, remove_best>0, stress>0.
"""
import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "fx_macro_rates_swing_m1"))
import rvlib as RV
import mrlib as MR
import swing_lib as SW

PIP = RV.PIP
TF = "H4"
HOLD = 24
FOLD = "DISCOVERY"
OUT = {}


def ctx(sym):
    bd = RV.bars(sym, TF)
    b = bd[TF]
    ct = b["close_time"]
    c = b["close"]
    atr = RV.atr_pips(sym, b)
    y24 = np.full(len(c), np.nan)
    y24[6:] = np.log(c[6:] / c[:-6])
    x24 = MR.rsum(ct, "ZN", 24)
    resz, beta = RV.roll_resid_z(y24, x24, 360)
    return {"b": b, "b5": bd["5m"], "ct": ct, "c": c, "atr": atr,
            "y24": y24, "x24": x24, "resz": resz, "beta": beta}


CTX = {s: ctx(s) for s in RV.PAIRS}


def decisions(sym, side, X):
    b = X["b"]; ct = X["ct"]; atr = X["atr"]
    ok = np.isfinite(atr) & (atr > 0)
    idx = np.flatnonzero(side != 0)
    idx = idx[ok[idx]]
    return {"ts": ct[idx], "side": side[idx]}, \
        np.maximum(atr[idx] * 2.5, 5.0)


def run(fam, mech, per_pair_side, hold=HOLD, rank=False):
    """per_pair_side: sym -> side array; rank=True keeps only max-|signal|
    pair per timestamp (cross-pair relative value)."""
    RV.register_family(fam)
    all_tr = []
    all_st = []
    cand = {}
    for sym in RV.PAIRS:
        X = CTX[sym]
        side = per_pair_side[sym]
        ok = np.isfinite(X["atr"]) & (X["atr"] > 0)
        idx = np.flatnonzero(side != 0)
        idx = idx[ok[idx]]
        for i in idx:
            cand.setdefault(int(X["ct"][i]), []).append(
                (sym, i, int(side[i]), abs(float(side[i]))))
    if rank:
        keep = {}
        for d in sorted(cand):
            best = max(cand[d], key=lambda t: t[3])
            keep.setdefault(best[0], []).append((d, best[1], best[2]))
    else:
        keep = {}
        for d, lst in cand.items():
            for sym, i, s, _ in lst:
                keep.setdefault(sym, []).append((d, i, s))
    for sym, lst in keep.items():
        X = CTX[sym]
        lst.sort()
        dec = {"ts": np.array([t[0] for t in lst]),
               "side": np.array([t[2] for t in lst], dtype=int)}
        dist = np.array([max(X["atr"][t[1]] * 2.5, 5.0) for t in lst])
        all_tr += RV.replay(sym, X["b5"], dec, dist, hold, stress=False)
        all_st += RV.replay(sym, X["b5"], dec, dist, hold, stress=True)
    m, ft = RV.summarize(all_tr, FOLD, mech)
    ms, _ = RV.summarize(all_st, FOLD, mech + "+stress")
    freq_ok = m["TRADES_PER_WEEK"] >= 2.0
    promote = (freq_ok and m.get("PF", 0) >= 1.20
               and m.get("expectancy_r", 0) >= 0.05
               and m.get("mean_pips", 0) >= 3
               and m.get("remove_best", 0) > 0
               and ms.get("mean_pips", -1) > 0)
    per = {s: RV.summarize([t for t in all_tr if t["sym"] == s], FOLD, s)[0]
           for s in RV.PAIRS}
    status = "PROMOTE" if promote else (
        "low_freq" if not freq_ok else "screen_reject")
    RV.log(fam, mech, {"hold": hold, "tf": TF}, m, ms.get("mean_pips"),
           status)
    OUT[mech] = {"m": m, "stress": ms.get("mean_pips"), "per_pair": per,
                 "years": SW.year_table(ft)}
    print(f"{fam}/{mech} N={m.get('N')} wk={m['TRADES_PER_WEEK']} "
          f"mean={m.get('mean_pips')} PF={m.get('PF')} "
          f"expR={m.get('expectancy_r')} rb={m.get('remove_best')} "
          f"stress={ms.get('mean_pips')} -> {status}")
    return m


# ----------------------------------------------------------- A: residual
for sym in RV.PAIRS:
    X = CTX[sym]
    fade = np.where(X["resz"] >= 1.5, -1,
                    np.where(X["resz"] <= -1.5, 1, 0))
    cont = np.where(X["resz"] >= 1.5, 1,
                    np.where(X["resz"] <= -1.5, -1, 0))
    CTX[sym]["fade"] = fade
    CTX[sym]["cont"] = cont
run("A", "resid_fade_1.5", {s: CTX[s]["fade"] for s in RV.PAIRS})
run("A", "resid_cont_1.5", {s: CTX[s]["cont"] for s in RV.PAIRS})
fade2 = {s: np.where(CTX[s]["resz"] >= 2.0, -1,
                     np.where(CTX[s]["resz"] <= -2.0, 1, 0)) for s in RV.PAIRS}
run("A", "resid_fade_2.0", fade2)

# ------------------------------------------------- D: partial adjustment
sideD = {}
for sym in RV.PAIRS:
    X = CTX[sym]
    m = X["beta"] * X["x24"]
    msig = m / np.maximum(pd.Series(m).rolling(360).std(ddof=1).to_numpy(),
                          1e-12)
    partial = np.abs(y := X["y24"]) < 0.5 * np.abs(m)
    fire = (np.abs(msig) >= 1.0) & partial & (np.abs(m) > 0)
    sideD[sym] = np.where(fire, np.sign(m), 0)
run("D", "partial_adj_1.0", sideD)

# ----------------------------------------------------------- B: curve
for sym in RV.PAIRS:
    X = CTX[sym]
    zt = MR.rz(X["ct"], "ZT", 24)
    zn = MR.rz(X["ct"], "ZN", 24)
    zf = MR.rz(X["ct"], "ZF", 24)
    X["slope"] = zt - zn
    X["level"] = (zt + zf + zn) / 3.0
run("B", "slope_up_usdup", {s: np.where(CTX[s]["slope"] >= 1.0, -1,
                                        np.where(CTX[s]["slope"] <= -1.0, 1, 0))
                            for s in RV.PAIRS})
run("B", "slope_dn_usdup", {s: np.where(CTX[s]["slope"] >= 1.0, 1,
                                        np.where(CTX[s]["slope"] <= -1.0, -1, 0))
                            for s in RV.PAIRS})
run("B", "level_usddir", {s: np.where(CTX[s]["level"] >= 1.0, -1,
                                      np.where(CTX[s]["level"] <= -1.0, 1, 0))
                          for s in RV.PAIRS})

# --------------------------------------- C: common USD factor + lag
usd_dir = {s: np.where(CTX[s]["resz"].astype(float) * 0 +
                       MR.rz(CTX[s]["ct"], "ZN", 24) >= 1.0, -1,
                       np.where(MR.rz(CTX[s]["ct"], "ZN", 24) <= -1.0, 1, 0))
           for s in RV.PAIRS}
# common USD 24h move on the EURUSD grid
base_ct = CTX["EURUSD"]["ct"]
common = np.zeros(len(base_ct))
for sym in RV.PAIRS:
    yi = np.interp(base_ct, CTX[sym]["ct"],
                   np.nan_to_num(-CTX[sym]["y24"] if sym != "USDJPY"
                                 else CTX[sym]["y24"]))
    common += yi
common /= 3.0
sideC = {}
for sym in RV.PAIRS:
    X = CTX[sym]
    pair_usd = np.nan_to_num(-X["y24"] if sym != "USDJPY" else X["y24"])
    common_p = np.interp(X["ct"], base_ct, common)
    lag = pair_usd - common_p
    d0 = usd_dir[sym]
    sideC[sym] = np.where((d0 != 0) & (lag * d0 < 0), d0, 0)
run("C", "common_usd_lag_z1.0", sideC)

# ------------------------------------------------- E: dynamic beta regime
sideE = {}
for sym in RV.PAIRS:
    X = CTX[sym]
    bf = RV.roll_beta(X["y24"], X["x24"], 90)
    xsig = X["x24"] / np.maximum(pd.Series(X["x24"]).rolling(360).std(ddof=1)
                                 .to_numpy(), 1e-12)
    fire = np.abs(xsig) >= 1.0
    sideE[sym] = np.where(fire, np.sign(np.nan_to_num(bf) * X["x24"]), 0)
run("E", "beta_regime_1.0", sideE)

# ------------------------------------------- H: response speed (4h)
sideH = {}
for sym in RV.PAIRS:
    X = CTX[sym]
    x4 = MR.rz(X["ct"], "ZN", 4)
    c = X["c"]; atr = X["atr"]
    fx4 = np.zeros(len(c))
    fx4[1:] = (c[1:] / c[:-1] - 1.0) / np.maximum(atr[1:] * PIP[sym], 1e-12)
    fire = (np.abs(x4) >= 1.0) & (fx4 * np.sign(x4) < 0.25)
    sideH[sym] = np.where(fire, -np.sign(x4), 0)
run("H", "speed_4h_0.25atr", sideH)

# --------------------------------------------- F: curve slope + pullback
sideF = {}
for sym in RV.PAIRS:
    X = CTX[sym]
    c = X["c"]
    pull = np.zeros(len(c), dtype=bool)
    pull[1:] = c[1:] < c[:-1]
    up = (X["slope"] >= 1.0) & pull
    dn = (X["slope"] <= -1.0) & ~pull
    sideF[sym] = np.where(up, -1, np.where(dn, 1, 0))
run("F", "slope_pullback", sideF)

# ---------------- frequency plateau cells for the two live directions
acont1 = {s: np.where(CTX[s]["resz"] >= 1.0, 1,
                      np.where(CTX[s]["resz"] <= -1.0, -1, 0))
          for s in RV.PAIRS}
run("A", "resid_cont_1.0", acont1)
acont075 = {s: np.where(CTX[s]["resz"] >= 0.75, 1,
                        np.where(CTX[s]["resz"] <= -0.75, -1, 0))
            for s in RV.PAIRS}
run("A", "resid_cont_0.75", acont075)

sideD2 = {}
for sym in RV.PAIRS:
    X = CTX[sym]
    m = X["beta"] * X["x24"]
    msig = m / np.maximum(pd.Series(m).rolling(360).std(ddof=1).to_numpy(),
                          1e-12)
    fire = (np.abs(msig) >= 0.75) & (np.abs(X["y24"]) < 0.6 * np.abs(m))
    sideD2[sym] = np.where(fire, np.sign(m), 0)
run("D", "partial_adj_0.75_0.6", sideD2)

# ------------------------------------------------- G: cross-pair ranking
run("G", "resid_rank_1.5", {s: CTX[s]["fade"] for s in RV.PAIRS}, rank=True)

json.dump(OUT, open(os.path.join(HERE, "cache", "rv_screens.json"), "w"),
          indent=1, default=str)
print(f"\nEXPERIMENTS={RV.experiments_used()}")
