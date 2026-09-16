#!/usr/bin/env python3
"""FX_CURRENCY_NETWORK_M1 library.

Multi-currency relative-strength / lead-lag discovery over the COMPLETE
4-currency network EUR-GBP-USD-JPY (6 pairs: EURUSD GBPUSD USDJPY EURJPY
GBPJPY EURGBP). Changes the information set vs FX_CROSS_ASSET_RV_M1: no
rates input, network-internal features only.

Data layer: Dukascopy 5m BID parquet (data_raw/parquet/<SYM>_5m.parquet),
same store and same audited fill semantics as fx_multipair_swing_m1 /
fx_cross_asset_rv_m1. Crosses verified REAL quotes (not derived): deviation
from leg-implied ~1 pip at 5m, so residuals are informative.

Folds (mission 11, calendar-aligned):
  DISCOVERY   2010-01-04 .. 2015-01-01
  VALIDATION  2015-01-01 .. 2017-01-01
  REPLICATION 2017-01-01 .. 2019-01-01
2019+ hard-forbidden in the loader.

All features causal: bars COMPLETED and close-time labelled
(bucket=(ct-1)//tf); decisions at bar close T, entry on the NEXT 5m open;
feature values during a trade are only read once their grid bar has CLOSED
(mapped via close times <= 5m bar close), exit executed at the NEXT 5m open.

Costs MODELED_EXECUTION, pre-registered conservative spreads (pips, per
round trip, bid layer + per-side crossing, identical model to the audited
engine): EURUSD 0.6, GBPUSD 1.0, USDJPY 0.9, EURJPY 1.2, GBPJPY 2.0,
EURGBP 0.8. Stress = +0.5 pip adverse per side. TICK_EXACT BID/ASK ticks
exist for EURUSD 2010-2018 only (E: store) - reserved for final survivor
audit. No purchase.

Pair selection (mission 15, pre-registered BEFORE any PnL):
  * strength families trade ONLY the single extreme strongest-vs-weakest
    currency pair per decision time (no duplicated macro bet);
  * lead-lag legs trade both legs of the identified cross (that IS the
    mechanism's bet);
  * occupancy: one open position per pair at a time.

Budget: 10 families / 60 experiments (CN_E001..CN_E060).
"""
import csv
import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
M2DIR = os.path.join(REPO, "research", "autonomous_edge_discovery_m2")
SWDIR = os.path.join(REPO, "research", "fx_multipair_swing_m1")
for p in (M2DIR, SWDIR):
    if p not in sys.path:
        sys.path.append(p)   # APPEND: legacy dirs must never shadow locals

from m2lib import agg_metrics, year_table, survival_veto   # audited metrics
import swing_lib as SW                                      # pooled_metrics

NS = 10 ** 9
CACHE = os.path.join(HERE, "cache")
os.makedirs(CACHE, exist_ok=True)
FX_DIR = os.path.join(REPO, "data_raw", "parquet")

PAIRS = ("EURUSD", "GBPUSD", "USDJPY", "EURJPY", "GBPJPY", "EURGBP")
CURR = ("EUR", "GBP", "USD", "JPY")
BASE = {"EURUSD": "EUR", "GBPUSD": "GBP", "USDJPY": "USD",
        "EURJPY": "EUR", "GBPJPY": "GBP", "EURGBP": "EUR"}
QUOTE = {"EURUSD": "USD", "GBPUSD": "USD", "USDJPY": "JPY",
         "EURJPY": "JPY", "GBPJPY": "JPY", "EURGBP": "GBP"}
PIP = {"EURUSD": 1e-4, "GBPUSD": 1e-4, "EURGBP": 1e-4,
       "USDJPY": 1e-2, "EURJPY": 1e-2, "GBPJPY": 1e-2}
SPREAD = {"EURUSD": 0.6, "GBPUSD": 1.0, "USDJPY": 0.9,
          "EURJPY": 1.2, "GBPJPY": 2.0, "EURGBP": 0.8}     # pips, conserv.
SLIP_STRESS = 0.5                                        # pips per side
CROSS_LEGS = {"EURJPY": ("EURUSD", "USDJPY"),
              "GBPJPY": ("GBPUSD", "USDJPY"),
              "EURGBP": ("EURUSD", "GBPUSD")}
# currency factor signs: +1 if currency is the pair base, -1 if quote
CSIGN = {c: {p: (1 if BASE[p] == c else -1) for p in PAIRS
             if c in (BASE[p], QUOTE[p])} for c in CURR}

FOLDS = {"DISCOVERY": ("2010-01-04", "2015-01-01"),
         "VALIDATION": ("2015-01-01", "2017-01-01"),
         "REPLICATION": ("2017-01-01", "2019-01-01")}
T_LO = int(pd.Timestamp("2010-01-04", tz="UTC").value)
T_HI = int(pd.Timestamp("2019-01-01", tz="UTC").value)   # 2019+ FORBIDDEN

LEDGER = os.path.join(HERE, "RESEARCH_LEDGER_CN.csv")
COUNTER = os.path.join(HERE, "EXPERIMENT_COUNTER_CN.txt")
FAMCOUNTER = os.path.join(HERE, "FAMILY_COUNTER_CN.txt")
FAMFILE = os.path.join(HERE, "FAMILIES_USED_CN.json")
MAX_EXP, MAX_FAM = 60, 10
TF_MIN = {"M15": 15, "H1": 60, "H4": 240}


def experiments_used():
    return int(open(COUNTER).read()) if os.path.exists(COUNTER) else 0


def next_exp_id():
    n = experiments_used() + 1
    assert n <= MAX_EXP, "EXPERIMENT BUDGET EXCEEDED"
    open(COUNTER, "w").write(str(n))
    return f"CN_E{n:03d}"


def register_family(fam):
    u = json.load(open(FAMFILE)) if os.path.exists(FAMFILE) else {}
    u[fam] = u.get(fam, 0) + 1
    json.dump(u, open(FAMFILE, "w"), indent=1)
    n = (int(open(FAMCOUNTER).read()) if os.path.exists(FAMCOUNTER) else 0) + 1
    open(FAMCOUNTER, "w").write(str(n))


def log(fam, mech, params, m, tpw, stress_mean, status, reason=""):
    rows = []
    if os.path.exists(LEDGER):
        rows = list(csv.DictReader(open(LEDGER)))
    rows.append({"experiment_id": next_exp_id(), "family_id": fam,
                 "mechanism": mech, "parameters": json.dumps(params),
                 "N": m.get("N"), "trades_per_week": tpw,
                 "mean_pips": m.get("mean_pips"), "PF": m.get("PF"),
                 "expectancy_r": m.get("expectancy_r"),
                 "remove_best": m.get("remove_best"),
                 "stress_mean": stress_mean, "status": status,
                 "reason": reason})
    with open(LEDGER, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)
    print(f"[{rows[-1]['experiment_id']}] {fam} {mech} {params} -> "
          f"N={m.get('N')} tpw={tpw} pips={m.get('mean_pips')} "
          f"PF={m.get('PF')} expR={m.get('expectancy_r')} {status}")


# ------------------------------------------------------------------ data

def load_fx(sym):
    """5m BID OHLCV, open-time ns ts, [2010-01-04, 2019-01-01). 2019+ refused."""
    p = os.path.join(CACHE, f"fx5m_{sym}.npz")
    if os.path.exists(p):
        z = np.load(p)
        return {k: z[k] for k in z.files}
    df = pd.read_parquet(f"{FX_DIR}/{sym}_5m.parquet")
    df = df[(df.index.view("int64") >= T_LO) & (df.index.view("int64") < T_HI)]
    if df.index.max().value >= T_HI:
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
    """Close-time-labelled bars from 5m (audited reduceat idiom)."""
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


def bars(sym, tf):
    key = (sym, tf)
    if key not in _BARS:
        d5 = load_fx(sym)
        _BARS[key] = {"5m": d5, tf: htf_bars(d5, TF_MIN[tf])}
    return _BARS[key]


def atr_pips_arr(sym, tf, n=14):
    """Rolling ATR in pips on decision-tf bars (causal, incl. current bar)."""
    b = bars(sym, tf)[tf]
    h, l, c = b["high"], b["low"], b["close"]
    pc = np.roll(c, 1); pc[0] = c[0]
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    return pd.Series(tr).rolling(n, min_periods=n).mean().to_numpy() / PIP[sym]


# ------------------------------------------------------------- grid layer

class Grid:
    """Common close-time grid = INNER JOIN of all 6 pairs' tf bar close
    times (complete network observable at every decision). Holds close
    prices and log returns over n grid steps."""

    def __init__(self, tf):
        self.tf = tf
        bt = [bars(s, tf)[tf] for s in PAIRS]
        g = bt[0]["close_time"]
        for b in bt[1:]:
            g = np.intersect1d(g, b["close_time"])
        self.t = g
        self.px = pd.DataFrame(
            {s: b["close"][np.searchsorted(b["close_time"], g)]
             for s, b in zip(PAIRS, bt)}, index=g)
        self._pos = {s: np.searchsorted(bars(s, tf)[tf]["close_time"], g)
                     for s in PAIRS}
        self._atr = {s: atr_pips_arr(s, tf) for s in PAIRS}
        self._ret = {}
        self._gm = {}

    def ret(self, n=1):
        """log return over n grid steps, causal (uses closes <= t)."""
        if n not in self._ret:
            self._ret[n] = np.log(self.px).diff(n)
        return self._ret[n]

    def atr_of(self, sym, times):
        a = self._atr[sym]
        pos = self._pos[sym]
        return a[pos[np.searchsorted(self.t, times)]]

    def gm_map(self, ts5):
        """For each 5m bar index: latest grid position whose close time is
        known at that 5m bar's close (causal visibility map)."""
        key = (id(ts5), self.tf)
        if key not in self._gm:
            ct = ts5 + 300 * NS
            self._gm[key] = np.searchsorted(self.t, ct, side="right") - 1
        return self._gm[key]

    def strength(self, n):
        """Currency strength S_c(n): mean signed n-step log return of the 3
        pairs containing c. Sum over currencies == 0 by construction."""
        R = self.ret(n)
        S = pd.DataFrame(index=self.t, columns=list(CURR), dtype=float)
        for c in CURR:
            acc = np.zeros(len(R))
            for p, sg in CSIGN[c].items():
                acc += sg * R[p].to_numpy()
            S[c] = acc / len(CSIGN[c])
        return S

    def zstrength(self, n, zwin):
        """Causally normalized strength z-scores: S / trailing std(zwin)."""
        S = self.strength(n)
        sd = S.rolling(zwin, min_periods=zwin).std(ddof=1)
        return S / sd


GRID = {}


def grid(tf):
    if tf not in GRID:
        GRID[tf] = Grid(tf)
    return GRID[tf]


# ---------------------------------------------------------------- replay

def replay(sym, tf, cands, stop_mult, trail_mult, exit_t, exit_v, exit_fn,
           max_hold_h, exit_name="SIGNAL_EXIT", stress=False, atr_mult=1.0):
    """Fill/fill-cost semantics IDENTICAL to the audited engine (bid layer +
    per-side spread crossing). cands: (dec_ts[], side[], stop_pips[]).
    Trail (trend families): chandelier trail_mult*ATR(dec tf) from best
    price since entry, updated at each 5m close, effective NEXT bar.
    exit_t/exit_v: grid close-time series of a causal exit statistic;
    exit_fn(side, v) -> True when the mechanism-specific exit fires; the
    exit executes at the NEXT 5m open after the statistic's bar closes.
    Initial protective stop: stop_mult*ATR at entry; 1R = that distance."""
    d5 = bars(sym, tf)["5m"]
    ts5, o5, h5, l5, c5 = (d5["ts"], d5["open"], d5["high"], d5["low"],
                           d5["close"])
    pip = PIP[sym]
    sp = SPREAD[sym] * pip
    slip = (SLIP_STRESS * pip) if stress else 0.0
    gm = grid(tf).gm_map(ts5)
    has_exit = exit_t is not None
    if has_exit:
        gi0 = np.searchsorted(exit_t, cands["ts"])          # dec grid pos
    hold_ns = int(max_hold_h * 3600 * NS)
    trades = []
    last_exit = -1
    for j in range(len(cands["ts"])):
        d = int(cands["ts"][j])
        if d < last_exit:
            continue
        s = int(cands["side"][j])
        sd = float(cands["stop_pips"][j]) * pip
        if not np.isfinite(sd) or sd <= 0:
            continue   # data hygiene: no tradable stop (e.g. flat-feed hole)
        k = int(np.searchsorted(ts5, d, side="left"))
        if k >= len(ts5) - 1:
            break
        m_end = int(np.searchsorted(ts5, d + hold_ns, side="right")) - 1
        m_end = min(m_end, len(ts5) - 1)
        if s == 1:
            entry = float(o5[k]) + sp + slip
            stop0 = entry - sd
            stop = stop0
            best = entry
        else:
            entry = float(o5[k]) - slip
            stop0 = entry + sd - sp          # bid level triggering the stop
            stop = stop0
            worst = entry
        tr = trail_mult * float(cands["atr_pips"][j]) * pip * atr_mult \
            if trail_mult else 0.0
        gprev = int(gi0[j]) if has_exit else -1
        exit_px = exit_ts = None
        reason = "OPEN"
        m = k + 1
        while m <= m_end:
            # 1) protective/trailing stop first (conservative)
            if s == 1 and l5[m] <= stop:
                exit_px = min(stop, float(o5[m])) - slip
                reason = "TRAIL" if (trail_mult and stop > stop0) else "STOP"
                exit_ts = int(ts5[m])
                break
            if s == -1 and h5[m] >= stop:
                exit_px = max(stop, float(o5[m])) + sp + slip
                reason = "TRAIL" if (trail_mult and stop < stop0) else "STOP"
                exit_ts = int(ts5[m])
                break
            # 2) mechanism exit: statistic known at close of bar m
            if has_exit:
                g = int(gm[m])
                if g > gprev:
                    v = float(exit_v[g])
                    if np.isfinite(v) and exit_fn(s, v):
                        if m < m_end:
                            exit_px = (float(o5[m + 1]) - slip if s == 1
                                       else float(o5[m + 1]) + sp + slip)
                            exit_ts = int(ts5[m + 1])
                            reason = exit_name
                            break
                        exit_px = (float(c5[m]) - slip if s == 1
                                   else float(c5[m]) + sp + slip)
                        exit_ts = int(ts5[m]) + 300 * NS
                        reason = exit_name
                        break
                    gprev = g
            # 3) trail update at close, effective next bar
            if tr:
                if s == 1:
                    best = max(best, float(h5[m]))
                    stop = max(stop, best - tr)
                else:
                    worst = min(worst, float(l5[m]))
                    stop = min(stop, worst + tr - sp)
            # 4) max time stop
            if m == m_end:
                exit_px = (float(c5[m]) - slip if s == 1
                           else float(c5[m]) + sp + slip)
                exit_ts = int(ts5[m]) + 300 * NS
                reason = "TIME"
                break
            m += 1
        if exit_px is None:   # data ended inside the trade
            m = m_end
            exit_px = (float(c5[m]) - slip if s == 1
                       else float(c5[m]) + sp + slip)
            exit_ts = int(ts5[m]) + 300 * NS
            reason = "TIME"
        trades.append({"sym": sym, "decision_ts": d, "side": s,
                       "entry_ts": int(ts5[k]), "entry": float(entry),
                       "exit_ts": int(exit_ts), "exit_px": float(exit_px),
                       "reason": reason,
                       "net_pips": s * (exit_px - entry) / pip,
                       "r": s * (exit_px - entry) / sd,
                       "risk_pips": sd / pip})
        last_exit = int(exit_ts)
    return trades


# -------------------------------------------------- fold evaluation/gates

def fold_mask(trades, fold):
    t0 = int(pd.Timestamp(FOLDS[fold][0], tz="UTC").value)
    t1 = int(pd.Timestamp(FOLDS[fold][1], tz="UTC").value)
    return [t for t in trades if t0 <= t["entry_ts"] < t1]


def weeks(fold):
    a, b = FOLDS[fold]
    return (pd.Timestamp(b) - pd.Timestamp(a)).days / 7.0


def summarize(trades, fold, label=""):
    ft = fold_mask(trades, fold)
    m = SW.pooled_metrics(ft, label or fold)
    m["TRADES_PER_WEEK"] = round(m.get("N", 0) / weeks(fold), 2) \
        if m.get("N") else 0.0
    m["stress_mean_pips"] = None
    return m, ft


def exit_breakdown(ft):
    return {k: sum(1 for t in ft if t["reason"] == k)
            for k in sorted({t["reason"] for t in ft})}


def discovery_gate(m):
    """Mission 16 gate on DISCOVERY fold metrics dict."""
    ok = (m.get("N", 0) >= 2 * weeks("DISCOVERY")
          and m.get("mean_pips", -9) > 0
          and m.get("PF", 0) >= 1.20
          and m.get("expectancy_r", -9) >= 0.05
          and m.get("remove_best", -9) > 0)
    return ok


def report(trades, label):
    """Full multi-fold report for one candidate rule."""
    out = {}
    for fold in FOLDS:
        m, ft = summarize(trades, fold, label)
        m["exit_breakdown"] = exit_breakdown(ft)
        out[fold] = m
    return out
