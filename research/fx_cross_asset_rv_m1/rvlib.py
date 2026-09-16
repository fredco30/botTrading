#!/usr/bin/env python3
"""FX_CROSS_ASSET_RELATIVE_VALUE_M1 library.

Continuous rates/FX relative-value discovery. All 2010-2018 local data is
research data, split into sequential folds:
  DISCOVERY   2010-06-07 .. 2015-01-01
  VALIDATION  2015-01-01 .. 2017-01-01
  REPLICATION 2017-01-01 .. 2019-01-01
2019+ is hard-forbidden (loader guard). 2026 forbidden.

FX layer: Dukascopy 5m BID parquet -> H1/H4 close-labelled bars, own loader
(2019+ guard). Replay: the semantics PROVEN identical to the audited engine
on 121/121 trades (run_final_audit.py), generalized to arbitrary windows.
Rates layer: mrlib (ZT/ZF/ZN 1m, roll-safe back-adjustment, causal
trailing vol normalization) with the research window 2010-06-07..2019-01-01.

Budget: 10 families / 60 experiments (RV_E001..RV_E060).
"""
import csv
import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
MRDIR = os.path.join(REPO, "research", "fx_macro_rates_swing_m1")
if MRDIR not in sys.path:
    sys.path.append(MRDIR)

import mrlib as MR                            # rates layer (causal)
import swing_lib as SW                        # metrics only
from m2lib import agg_metrics, year_table, survival_veto

NS = 10 ** 9
CACHE = os.path.join(HERE, "cache")
os.makedirs(CACHE, exist_ok=True)
FX_DIR = os.path.join(REPO, "data_raw", "parquet")

MR.set_window("2010-06-07", "2019-01-01")     # research rates window
T0, T1 = MR.T0_NS, MR.T1_NS
PIP = {"EURUSD": 1e-4, "GBPUSD": 1e-4, "USDJPY": 1e-2}
SPREAD = {"EURUSD": 0.6, "GBPUSD": 1.0, "USDJPY": 0.9}   # pips, conservative
SLIP_STRESS = 0.5                              # pips per side
PAIRS = ("EURUSD", "GBPUSD", "USDJPY")
FOLDS = {"DISCOVERY": ("2010-06-07", "2015-01-01"),
         "VALIDATION": ("2015-01-01", "2017-01-01"),
         "REPLICATION": ("2017-01-01", "2019-01-01")}

LEDGER = os.path.join(HERE, "RESEARCH_LEDGER_RV.csv")
COUNTER = os.path.join(HERE, "EXPERIMENT_COUNTER_RV.txt")
FAMCOUNTER = os.path.join(HERE, "FAMILY_COUNTER_RV.txt")
MAX_EXP, MAX_FAM = 60, 10


def experiments_used():
    return int(open(COUNTER).read()) if os.path.exists(COUNTER) else 0


def next_exp_id():
    n = experiments_used() + 1
    open(COUNTER, "w").write(str(n))
    return f"RV_E{n:03d}"


def register_family(fam):
    p = os.path.join(HERE, "FAMILIES_USED_RV.json")
    u = json.load(open(p)) if os.path.exists(p) else {}
    u[fam] = u.get(fam, 0) + 1
    json.dump(u, open(p, "w"), indent=1)
    n = (int(open(FAMCOUNTER).read()) if os.path.exists(FAMCOUNTER) else 0) + 1
    open(FAMCOUNTER, "w").write(str(n))


def log(fam, mech, params, m, stress_mean, status, reason=""):
    rows = []
    if os.path.exists(LEDGER):
        rows = list(csv.DictReader(open(LEDGER)))
    rows.append({"experiment_id": next_exp_id(), "family_id": fam,
                 "mechanism": mech, "parameters": json.dumps(params),
                 "N": m.get("N"), "mean_pips": m.get("mean_pips"),
                 "PF": m.get("PF"), "expectancy_r": m.get("expectancy_r"),
                 "remove_best": m.get("remove_best"),
                 "stress_mean": stress_mean, "status": status,
                 "reason": reason})
    with open(LEDGER, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)


# ------------------------------------------------------------- FX layer

def load_fx(sym):
    """5m BID OHLCV, open-time ts, [2010-01-04, 2019-01-01). 2019+ refused."""
    p = os.path.join(CACHE, f"fx5m_{sym}.npz")
    if os.path.exists(p):
        z = np.load(p)
        return {k: z[k] for k in z.files}
    df = pd.read_parquet(f"{FX_DIR}/{sym}_5m.parquet")
    t0 = int(pd.Timestamp("2010-01-04", tz="UTC").value)
    t1 = int(pd.Timestamp("2019-01-01", tz="UTC").value)
    df = df[(df.index.view("int64") >= t0) & (df.index.view("int64") < t1)]
    if df.index.max().value >= t1:
        raise PermissionError("2019+ FORBIDDEN")
    df = df[df["low"] > 0]
    out = {"ts": np.asarray(df.index.view("int64")),
           "open": np.asarray(df["open"], float),
           "high": np.asarray(df["high"], float),
           "low": np.asarray(df["low"], float),
           "close": np.asarray(df["close"], float)}
    np.savez_compressed(p, **out)
    return out


def htf_bars(d5, tf_min):
    """Close-time-labelled H1/H4 bars from 5m (reduceat idiom, proven equal
    to the audited engine's bars_from_5m)."""
    tf = tf_min * 60 * NS
    ctns = d5["ts"] + 300 * NS
    bucket = (ctns - 1) // tf
    ug = np.unique(bucket)
    fid = np.searchsorted(bucket, ug, side="left")
    lid = np.searchsorted(bucket, ug, side="right") - 1
    return {"close_time": (ug + 1) * tf,
            "open": d5["open"][fid],
            "high": np.maximum.reduceat(d5["high"], fid),
            "low": np.minimum.reduceat(d5["low"], fid),
            "close": d5["close"][lid]}


_BARS = {}
TF_MIN = {"H1": 60, "H4": 240}


def bars(sym, tf):
    key = (sym, tf)
    if key not in _BARS:
        d5 = load_fx(sym)
        _BARS[key] = {"5m": d5, tf: htf_bars(d5, TF_MIN[tf])}
    return _BARS[key]


def atr_pips(sym, b, n=14):
    h, l, c = b["high"], b["low"], b["close"]
    pc = np.roll(c, 1); pc[0] = c[0]
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    return pd.Series(tr).rolling(n).mean().to_numpy() / PIP[sym]


def replay(sym, d5, decisions, dist_pips, hold_h, stress=False):
    """Frozen fill model (bid layer + per-side spread), occupancy
    one-position-at-a-time per pair; semantics identical to the audited
    engine (see run_final_audit.py: 121/121 exact)."""
    ts5, o5 = d5["ts"], d5["open"]
    h5, l5, c5 = d5["high"], d5["low"], d5["close"]
    pip = PIP[sym]
    spread = SPREAD[sym] * pip
    slip = (SLIP_STRESS * pip) if stress else 0.0
    trades = []
    last_exit = -1
    for j in range(len(decisions["ts"])):
        s = int(decisions["side"][j])
        if s == 0:
            continue
        d = int(decisions["ts"][j])
        if d < last_exit:
            continue
        k = int(np.searchsorted(ts5, d, side="left"))
        if k >= len(ts5) - 1:
            break
        sd = float(dist_pips[j]) * pip
        if s == 1:
            entry = float(o5[k]) + spread + slip
            stop = entry - sd; tgt = entry + sd
        else:
            entry = float(o5[k]) - slip
            stop_bid = entry + sd - spread; stop = entry + sd
            tgt_bid = entry - sd - spread; tgt = entry - sd
        m_end = int(np.searchsorted(ts5, int(ts5[k]) + hold_h * 3600 * NS,
                                    side="right")) - 1
        m0 = k + 1
        exit_px = exit_ts = None; reason = "OPEN"
        if m_end >= m0:
            i_s = np.flatnonzero(l5[m0:m_end + 1] <= stop) if s == 1 \
                else np.flatnonzero(h5[m0:m_end + 1] >= stop_bid)
            i_t = np.flatnonzero(h5[m0:m_end + 1] >= tgt) if s == 1 \
                else np.flatnonzero(l5[m0:m_end + 1] <= tgt_bid)
            i_s = int(i_s[0]) if len(i_s) else 10 ** 12
            i_t = int(i_t[0]) if len(i_t) else 10 ** 12
            if i_s <= i_t and i_s < 10 ** 12:
                m = m0 + i_s
                exit_px = (min(stop, float(o5[m0 + i_s])) - slip if s == 1
                           else max(stop, float(o5[m0 + i_s]) + spread) + slip)
                exit_ts = int(ts5[m]); reason = "STOP"
            elif i_t < 10 ** 12:
                m = m0 + i_t
                exit_px = float(tgt) - slip if s == 1 else float(tgt) + slip
                exit_ts = int(ts5[m]); reason = "TARGET"
            else:
                m = m_end
                exit_px = (float(c5[m]) - slip if s == 1
                           else float(c5[m]) + spread + slip)
                exit_ts = int(ts5[m]) + 300 * NS; reason = "TIME"
        else:
            m = min(m_end, len(ts5) - 1)
            exit_px = (float(c5[m]) - slip if s == 1
                       else float(c5[m]) + spread + slip)
            exit_ts = int(ts5[m]) + 300 * NS; reason = "TIME"
        trades.append({"sym": sym, "decision_ts": d, "side": s,
                       "entry_ts": int(ts5[k]), "entry": float(entry),
                       "exit_ts": int(exit_ts), "exit_px": float(exit_px),
                       "reason": reason, "net_pips": s * (exit_px - entry) / pip,
                       "r": s * (exit_px - entry) / sd,
                       "risk_pips": sd / pip})
        last_exit = int(exit_ts)
    return trades


# ------------------------------------------------- causal rolling features

def roll_beta(y, x, win):
    """Trailing OLS beta cov(x,y)/var(x), window ends at each bar (causal)."""
    cm = pd.Series(x).rolling(win).cov(pd.Series(y))
    vx = pd.Series(x).rolling(win).var(ddof=1)
    return (cm / vx).to_numpy()


def roll_resid_z(y, x, win):
    """residual = y - beta*x; z vs trailing std of residuals (causal)."""
    b = roll_beta(y, x, win)
    res = y - b * x
    sd = pd.Series(res).rolling(win).std(ddof=1).to_numpy()
    return np.where(sd > 0, res / sd, np.nan), b


# ------------------------------------------------------- fold evaluation

def fold_mask(trades, fold):
    t0 = int(pd.Timestamp(FOLDS[fold][0], tz="UTC").value)
    t1 = int(pd.Timestamp(FOLDS[fold][1], tz="UTC").value)
    return [t for t in trades if t0 <= t["entry_ts"] < t1]


def weeks(span_tuple):
    a, b = FOLDS[span_tuple]
    return (pd.Timestamp(b) - pd.Timestamp(a)).days / 7.0


def summarize(trades, fold, label=""):
    ft = fold_mask(trades, fold)
    m = SW.pooled_metrics(ft, label or fold)
    m["TRADES_PER_WEEK"] = round(m.get("N", 0) / weeks(fold), 2) \
        if m.get("N") else 0.0
    return m, ft
