#!/usr/bin/env python3
"""FX_MULTIPAIR_SWING_DISCOVERY_M1 library.

Multi-pair H1/H4/D1 swing strategy discovery on EURUSD + GBPUSD (discovery
2010-2017), USDJPY 2010-2017 as sealed cross-pair holdout, EURUSD 2018H2 as
sealed temporal holdout. Reuses the audited metrics layer (m2lib via m3lib)
and mirrors m3lib's causal conventions:

  * bars are COMPLETED and close-time labelled (bucket = (ct-1)//tf);
  * decisions happen at bar close T, entries execute on the NEXT 5m bar;
  * features may only read bars closing <= T.

Data layer: Dukascopy BID 1-min candles aggregated to 5m OHLCV
(data_raw/parquet/<SYM>_5m.parquet, built by phenomena_discovery_v1/
build_5m.py; cross-validated 0.0-pip against the LAB_PASS tick store on
EURUSD 2015-03-02 hourly BID closes). BID-only implies a per-side fill
model: long entries cross the spread (fill at BID + SPREAD), short exits
cross it back (fill at BID-exit + SPREAD). Validated BID/ASK ticks exist
only for EURUSD 2010-2018H1 (E: store) and are used for tick-exact replay
of any serious candidate on that pair via m3lib.mtf_replay.

BUDGET: 80 experiments / 12 families, IDs SW_E001..SW_E080.
Units: ns UTC timestamps, float64 BID prices; 1 pip = 1e-4 (EURUSD/GBPUSD)
or 1e-2 (USDJPY); 1R = stop distance in pips.
"""
import csv
import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
RESEARCH = os.path.join(HERE, "..")
M1DIR = os.path.join(RESEARCH, "autonomous_edge_discovery_m1")
M2DIR = os.path.join(RESEARCH, "autonomous_edge_discovery_m2")
M3DIR = os.path.join(RESEARCH, "mtf_discovery_m1")
for p in (M1DIR, M2DIR, M3DIR):
    if p not in sys.path:
        sys.path.append(p)   # APPEND: legacy dirs must never shadow locals

import infra_lib as I   # validated EURUSD tick layer (load_year, m1_bars)
import m2lib            # metrics/survival reused verbatim
import m3lib            # mtf_replay tick-exact engine + metrics re-exports

NS = I.NS
CACHE = os.path.join(HERE, "cache")
os.makedirs(CACHE, exist_ok=True)

PARQUET_DIR = os.path.abspath(os.path.join(RESEARCH, "..", "data_raw", "parquet"))

PIP = {"EURUSD": 1e-4, "GBPUSD": 1e-4, "USDJPY": 1e-2,
       "EURJPY": 1e-2, "GBPJPY": 1e-2}
# Full spread crossed by long entry / short exit (pips). EURUSD = measured
# Dukascopy tick median (see measure_spread below); GBPUSD/USDJPY
# conservative majors estimates (no local ticks).
SPREAD_PIPS = {"EURUSD": 0.6, "GBPUSD": 1.0, "USDJPY": 0.9}
SLIP_STRESS_PIPS = 0.5           # per side, stress scenario
DISCOVERY_PAIRS = ("EURUSD", "GBPUSD")
HOLDOUT_PAIR = "USDJPY"

TFS = {"H1": 60, "H4": 240, "D1": 1440}   # minutes; UTC grid
DISCOVERY_YEARS = list(range(2010, 2018))

# --------------------------------------------------------------- budget

LEDGER = os.path.join(HERE, "RESEARCH_LEDGER_SW.csv")
EXP_COUNTER = os.path.join(HERE, "EXPERIMENT_COUNTER_SW.txt")
FAM_COUNTER = os.path.join(HERE, "FAMILY_COUNTER_SW.txt")
MAX_EXP = 80
MAX_FAMILIES = 12
COLUMNS = ["experiment_id", "family_id", "mechanism", "feature_causality_pass",
           "parameters", "N", "mean_pips", "PF", "expectancy_R", "stress_pips",
           "remove_best_pips", "status", "reason"]


def _count(path):
    return int(open(path).read().strip()) if os.path.exists(path) else 0


def experiments_used():
    return _count(EXP_COUNTER)


def families_used():
    s = open(FAM_COUNTER).read().split() if os.path.exists(FAM_COUNTER) else []
    return sorted(set(s))


def family_configs_used(family_id):
    if not os.path.exists(LEDGER):
        return 0
    df = pd.read_csv(LEDGER)
    return int((df["family_id"] == family_id).sum())


def next_exp_id():
    n = experiments_used() + 1
    if n > MAX_EXP:
        raise RuntimeError(f"HARD BUDGET STOP: experiment #{n} > {MAX_EXP}")
    with open(EXP_COUNTER, "w") as f:
        f.write(str(n))
    return f"SW_E{n:03d}"


def register_family(family_id):
    fams = families_used()
    if family_id not in fams:
        if len(fams) >= MAX_FAMILIES:
            raise RuntimeError(
                f"HARD BUDGET STOP: family {family_id} exceeds {MAX_FAMILIES}")
        fams.append(family_id)
        with open(FAM_COUNTER, "w") as f:
            f.write("\n".join(sorted(fams)))
    return len(fams)


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


def log(family_id, mechanism, causality_pass, parameters, N=np.nan,
        mean_pips=np.nan, PF=np.nan, expectancy_R=np.nan, stress_pips=np.nan,
        remove_best_pips=np.nan, status="SCREEN", reason=""):
    if family_configs_used(family_id) >= 8:
        raise RuntimeError(f"FAMILY BUDGET STOP: {family_id} already used 8")
    register_family(family_id)
    row = dict(experiment_id=next_exp_id(), family_id=family_id,
               mechanism=mechanism, feature_causality_pass=causality_pass,
               parameters=parameters, N=N, mean_pips=_r(mean_pips),
               PF=_r(PF), expectancy_R=_r(expectancy_R),
               stress_pips=_r(stress_pips), remove_best_pips=_r(remove_best_pips),
               status=status, reason=str(reason)[:400])
    new = not os.path.exists(LEDGER)
    with open(LEDGER, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        if new:
            w.writeheader()
        w.writerow(row)
    print(f"LEDGER {row['experiment_id']} {family_id} {status} "
          f"N={row['N']} mean={row['mean_pips']} PF={row['PF']} "
          f"expR={row['expectancy_R']} :: {str(reason)[:120]}")
    return row


# ------------------------------------------------------------------ data

ACCESS_LOG = os.path.join(HERE, "DATA_ACCESS_LOG.md")
STAGE_A_SENTINEL = os.path.join(HERE, "STAGE_A_UNLOCKED")
STAGE_B_SENTINEL = os.path.join(HERE, "STAGE_B_UNLOCKED")


def _audit(sym, a, b, n, tag):
    with open(ACCESS_LOG, "a") as f:
        f.write(f"- {pd.Timestamp.now(tz='UTC'):%Y-%m-%d %H:%M:%SZ} {tag} {sym} "
                f"[{pd.Timestamp(a, unit='ns', tz='UTC'):%Y-%m-%d}, "
                f"{pd.Timestamp(b, unit='ns', tz='UTC'):%Y-%m-%d}) rows={n}\n")


def window_ns(a: str, b: str):
    return int(pd.Timestamp(a, tz="UTC").value), int(pd.Timestamp(b, tz="UTC").value)


def load_5m(sym, t0_ns, t1_ns, tag):
    """5m BID OHLCV rows (bar-OPEN ts) with ts in [t0_ns, t1_ns). Hard guards:
    >= 2019-01-01 refused unconditionally; USDJPY any-window requires the
    STAGE_A sentinel; EURUSD 2018H2 requires the STAGE_B sentinel."""
    if t1_ns >= int(pd.Timestamp("2019-01-01", tz="UTC").value):
        raise PermissionError(">=2019 data is FORBIDDEN (mission 7)")
    b = pd.Timestamp(t1_ns, unit="ns", tz="UTC")
    a = pd.Timestamp(t0_ns, unit="ns", tz="UTC")
    if sym == "USDJPY" and not os.path.exists(STAGE_A_SENTINEL):
        raise PermissionError(f"{sym} is the cross-pair holdout: STAGE_A "
                              f"sentinel missing (mission 22)")
    if sym == "EURUSD" and b > pd.Timestamp("2018-01-01", tz="UTC"):
        if not (a >= pd.Timestamp("2018-07-01", tz="UTC")
                and b <= pd.Timestamp("2019-01-01", tz="UTC")):
            raise PermissionError("EURUSD beyond 2018H1 outside discovery "
                                  "window refused")
        if not os.path.exists(STAGE_B_SENTINEL):
            raise PermissionError("EURUSD 2018H2 is SEALED: STAGE_B sentinel "
                                  "missing (mission 25)")
    df = pd.read_parquet(os.path.join(PARQUET_DIR, f"{sym}_5m.parquet"))
    df = df[(df.index >= a) & (df.index < b)]
    df = df[df["low"] > 0]                      # placeholder prints dropped
    out = {"ts": df.index.view("int64").astype(np.int64),
           "open": df["open"].to_numpy(np.float64),
           "high": df["high"].to_numpy(np.float64),
           "low": df["low"].to_numpy(np.float64),
           "close": df["close"].to_numpy(np.float64)}
    _audit(sym, t0_ns, t1_ns, len(out["ts"]), tag)
    return out


def discovery_window_ns():
    return window_ns("2010-01-04", "2018-01-01")


def load_discovery(sym):
    """Full discovery 5m window for one pair (2010-01-04 .. 2017-12-31)."""
    p = os.path.join(CACHE, f"5m_{sym}_2010_2017.npz")
    if os.path.exists(p):
        z = np.load(p)
        return {k: z[k] for k in z.files}
    a, b = discovery_window_ns()
    d = load_5m(sym, a, b, "DISCOVERY")
    np.savez_compressed(p, **d)
    return d


def load_eurusd_2018h2():
    """Stage B only (sentinel-gated)."""
    a, b = window_ns("2018-07-01", "2019-01-01")
    return load_5m("EURUSD", a, b, "STAGE_B")


# ------------------------------------------------------------------ bars

def bars_from_5m(d5, tf_min):
    """Completed higher-TF bars from 5m bars (close-time labelled, same
    idiom as m3lib.bars_from_m1: bucket = (close_time-1)//tf)."""
    tf = tf_min * 60 * NS
    ct = d5["ts"] + 5 * 60 * NS
    g = (ct - 1) // tf
    ug = np.unique(g)
    fid = np.searchsorted(g, ug, side="left")           # first 5m in bucket
    idx = np.searchsorted(g, ug, side="right") - 1      # last 5m in bucket
    lo = np.minimum.reduceat(d5["low"], fid)
    hi = np.maximum.reduceat(d5["high"], fid)
    return {
        "start": (ug * tf).astype(np.int64),
        "close_time": ((ug + 1) * tf).astype(np.int64),
        "open": d5["open"][fid],
        "high": hi, "low": lo,
        "close": d5["close"][idx],
    }


BAR_KEYS = ("start", "close_time", "open", "high", "low", "close")


def build_discovery_bars(sym):
    """Cached H1/H4/D1 bars + 5m execution frame for one pair."""
    p = os.path.join(CACHE, f"bars_{sym}_2010_2017.npz")
    if os.path.exists(p):
        z = np.load(p)
        return {k: z[k] for k in z.files}
    d5 = load_discovery(sym)
    out = {"5m_" + k: d5[k] for k in ("ts", "open", "high", "low", "close")}
    for name, tf in TFS.items():
        b = bars_from_5m(d5, tf)
        for k in BAR_KEYS:
            out[f"{name}_{k}"] = b[k]
    np.savez_compressed(p, **out)
    return out


# ------------------------------------------------------------- indicators
# All causal: value at bar i uses bars 0..i (bar i completed at decision T).

def sma(x, n):
    return pd.Series(x).rolling(n).mean().to_numpy()


def std(x, n):
    return pd.Series(x).rolling(n).std(ddof=0).to_numpy()


def ema(x, n):
    return pd.Series(x).ewm(span=n, adjust=False).mean().to_numpy()


def atr(sym, high, low, close, n):
    """ATR in instrument PIPS (causal rolling mean of true range)."""
    pip = PIP[sym]
    pc = np.roll(close, 1); pc[0] = close[0]
    tr = np.maximum(high - low, np.maximum(np.abs(high - pc), np.abs(low - pc)))
    return pd.Series(tr).rolling(n).mean().to_numpy() / pip


def zsc(x, n):
    m, s = sma(x, n), std(x, n)
    return np.where(s > 0, (x - m) / s, np.nan)


def donhi(close, n):
    return pd.Series(close).rolling(n).max().shift(1).to_numpy()


def donlo(close, n):
    return pd.Series(close).rolling(n).min().shift(1).to_numpy()


def adx(high, low, close, n):
    """Classic Wilder ADX (causal, needs 2n bars)."""
    up = np.diff(high, prepend=high[0])
    dn = -np.diff(low, prepend=low[0])
    plus_dm = np.where((up > dn) & (up > 0), up, 0.0)
    minus_dm = np.where((dn > up) & (dn > 0), dn, 0.0)
    tr = np.maximum(high - low, np.maximum(np.abs(high - np.roll(close, 1)),
                                           np.abs(low - np.roll(close, 1))))
    tr[0] = high[0] - low[0]
    atrw = pd.Series(tr).ewm(alpha=1 / n, adjust=False).mean().to_numpy()
    pdi = 100 * pd.Series(plus_dm).ewm(alpha=1 / n, adjust=False).mean().to_numpy() / atrw
    mdi = 100 * pd.Series(minus_dm).ewm(alpha=1 / n, adjust=False).mean().to_numpy() / atrw
    dx = 100 * np.abs(pdi - mdi) / np.maximum(pdi + mdi, 1e-12)
    return pd.Series(dx).ewm(alpha=1 / n, adjust=False).mean().to_numpy()


def ret(x, n):
    """n-bar log return."""
    lx = np.log(x)
    out = np.full(len(x), np.nan)
    out[n:] = lx[n:] - lx[:-n]
    return out


# ---------------------------------------------------------------- replay

def bar_replay(sym, sig_ct, decisions, stop_dist, tp_dist, hold_hours,
               stress=False):
    """Bar-based replay on the 5m BID frame with a per-side spread model.

    decisions: sorted 'ts' (completed signal-bar close times, ns) + 'side'.
    stop_dist / tp_dist: per-decision distances in PIPS (from the frozen
    rule, typically ATR multiples computed at decision time).
    hold_hours: time exit after entry (5m close granularity).
    Entry: first 5m bar with OPEN time >= decision ts (strictly next bar);
    the 5m bar OPENING at/just after an H1/H4/D1 boundary IS the next bar.

    Fills (BID candles; m3lib conventions adapted to BID-only data):
      long : entry = bid_open + SPREAD + slip (ask side crossed);
             exits at BID: stop = min(stop, bar open if gapped) - slip,
             target = tgt - slip, time = close - slip.
      short: entry = bid_open - slip;
             exits at ASK = BID + SPREAD + slip: the ask-stop at entry+sd
             triggers when bid high >= entry+sd-SPREAD, ask fill =
             max(entry+sd, trigger/gap) + slip; ask-target at entry-td
             triggers when bid low <= entry-td-SPREAD, fill = entry-td;
             time exit at close + SPREAD + slip.
    Stress: slip = 0.5 pip per side on every fill (entry and exit).
    One position at a time: decisions inside an open trade are skipped
    (m3lib last_exit_ts idiom).
    """
    bars = build_discovery_bars(sym)
    ts5 = bars["5m_ts"]; o5 = bars["5m_open"]; h5 = bars["5m_high"]
    l5 = bars["5m_low"]; c5 = bars["5m_close"]
    pip = PIP[sym]
    spread = SPREAD_PIPS[sym] * pip
    slip = (SLIP_STRESS_PIPS * pip) if stress else 0.0

    trades = []
    last_exit_ts = -1
    n5 = len(ts5)
    for j in range(len(decisions["ts"])):
        side = int(decisions["side"][j])
        if side == 0:
            continue
        d = int(decisions["ts"][j])
        if d < last_exit_ts:
            continue
        k = int(np.searchsorted(ts5, d, side="left"))    # first open >= d
        if k >= n5 - 1:
            break
        sd = float(stop_dist[j]) * pip
        td = float(tp_dist[j]) * pip
        if side == 1:
            entry = float(o5[k]) + spread + slip
            stop = entry - sd                            # bid stop level
            tgt = entry + td                             # bid target level
        else:
            entry = float(o5[k]) - slip
            stop_bid = entry + sd - spread               # bid trigger of ask-stop
            stop = entry + sd                            # ask stop level (fill)
            tgt_bid = entry - td - spread                # bid trigger of ask-TP
            tgt = entry - td                             # ask target fill
        t_end = int(ts5[k]) + int(hold_hours * 3600 * NS)
        m_end = int(np.searchsorted(ts5, t_end, side="right")) - 1
        m0 = k + 1
        exit_ts = exit_px = None
        reason = "OPEN"
        if m_end >= m0:
            hs = h5[m0:m_end + 1]; ls = l5[m0:m_end + 1]; os_ = o5[m0:m_end + 1]
            if side == 1:
                i_s = np.flatnonzero(ls <= stop)
                i_t = np.flatnonzero(hs >= tgt)
            else:
                i_s = np.flatnonzero(hs >= stop_bid)
                i_t = np.flatnonzero(ls <= tgt_bid)
            i_s = int(i_s[0]) if len(i_s) else 10 ** 12
            i_t = int(i_t[0]) if len(i_t) else 10 ** 12
            if i_s <= i_t and i_s < 10 ** 12:              # stop priority
                m = m0 + i_s
                if side == 1:
                    exit_px = min(stop, float(os_[i_s])) - slip  # gap-through
                else:
                    exit_px = max(stop, float(os_[i_s]) + spread) + slip
                exit_ts = int(ts5[m]); reason = "STOP"
            elif i_t < 10 ** 12:
                m = m0 + i_t
                if side == 1:
                    exit_px = float(tgt) - slip
                else:
                    exit_px = float(tgt) + slip
                exit_ts = int(ts5[m]); reason = "TARGET"
            else:
                m = m_end
                if side == 1:
                    exit_px = float(c5[m]) - slip
                else:
                    exit_px = float(c5[m]) + spread + slip
                exit_ts = int(ts5[m]) + 5 * 60 * NS; reason = "TIME"
        else:
            m = min(m_end, n5 - 1)
            if side == 1:
                exit_px = float(c5[m]) - slip
            else:
                exit_px = float(c5[m]) + spread + slip
            exit_ts = int(ts5[m]) + 5 * 60 * NS; reason = "TIME"
        net = side * (exit_px - entry) / pip
        risk = sd / pip
        trades.append({"j": int(j), "sym": sym, "side": side,
                       "decision_ts": d, "entry_ts": int(ts5[k]),
                       "entry": entry, "exit_ts": int(exit_ts),
                       "exit_px": float(exit_px), "reason": reason,
                       "net_pips": float(net), "r": float(net / risk),
                       "risk_pips": float(risk)})
        last_exit_ts = int(exit_ts)
    return trades


def run_pooled(signal_fn, params, stop_fn, tp_fn, hold_hours, pairs=DISCOVERY_PAIRS,
               stress=False):
    """Run one frozen rule over the discovery pairs; returns pooled trades.
    signal_fn(bars, sym, params) -> side array on its chosen signal TF (with
    attribute signal_tf); stop_fn/tp_fn(bars, i, sym, params) -> pip distances
    at decision bar i. Decisions = completed signal-TF bars with side != 0."""
    all_trades = []
    for sym in pairs:
        bars = build_discovery_bars(sym)
        side = signal_fn(bars, sym, params)
        tf = signal_fn.signal_tf
        ct = bars[f"{tf}_close_time"]
        idx = np.flatnonzero(side != 0)
        dec = {"ts": ct[idx], "side": side[idx]}
        stop_d = np.array([stop_fn(bars, i, sym, params) for i in idx])
        tp_d = np.array([tp_fn(bars, i, sym, params) for i in idx])
        all_trades += bar_replay(sym, ct, dec, stop_d, tp_d, hold_hours, stress)
    return all_trades


def pooled_metrics(trades, label):
    m = agg_metrics(trades, label)
    return m


# ------------------------------------------------------------- causality

def causality_gate(family, signal_fn, params, pairs=DISCOVERY_PAIRS,
                   year=2010, n_samples=24, seed=20260916):
    """T1/T2/T3 gate on discovery year(s) `year` (int or list), per pair.
    D1-scale strategies may fire < 20 times in one calendar year, so fire
    indices are POOLED across the listed years before sampling 24 traces;
    the verdict bar is >= 20 pooled traces per pair.
    T1: every feature input bar close <= decision T (provenance chain).
    T2: bars rebuilt from 5m rows truncated at T reproduce the same side.
    T3: shifting all 5m rows closing after T by +1% does not change the side.
    """
    years = list(year) if isinstance(year, (list, tuple)) else [year]
    ok_all = True
    trace = []
    for sym in pairs:
        d5_full = load_discovery(sym)
        bars = build_discovery_bars(sym)
        side = signal_fn(bars, sym, params)
        tf = signal_fn.signal_tf
        ct = bars[f"{tf}_close_time"]
        fire = np.zeros(len(ct), dtype=bool)
        for y in years:
            y0, y1 = window_ns(f"{y}-01-01", f"{y+1}-01-01")
            fire |= (ct >= y0) & (ct < y1 - 48 * 3600 * NS)
        fire = np.flatnonzero(fire & (side != 0))
        rng = np.random.default_rng(seed + hash(sym) % 1000)
        picks = list(rng.permutation(fire)[:n_samples]) if len(fire) > n_samples else list(fire)
        t1 = t2 = t3 = True
        for j in picks:
            T = int(ct[j])
            chain = [T]
            if j >= 1:
                chain.append(int(ct[j - 1]))
            for other in TFS:
                o = bars[f"{other}_close_time"]
                k = int(np.searchsorted(o, T, side="right")) - 1
                if k >= 0:
                    chain.append(int(o[k]))
            if max(chain) > T:
                t1 = False
                print(f"  T1 FAIL {family}/{sym} j={j}: max_input={max(chain)} T={T}")
            # T2: truncate 5m at T (5m bars complete at ts+5min <= T)
            ct5 = d5_full["ts"] + 5 * 60 * NS
            m = int(np.searchsorted(ct5, T, side="right"))
            d5t = {k: v[:m] for k, v in d5_full.items()}
            bart = {"5m_" + k: d5t[k] for k in ("ts", "open", "high", "low", "close")}
            for name, tfm in TFS.items():
                bb = bars_from_5m(d5t, tfm)
                for kk in BAR_KEYS:
                    bart[f"{name}_{kk}"] = bb[kk]
            sidet = signal_fn(bart, sym, params)
            ctt = bart[f"{tf}_close_time"]
            jt = int(np.searchsorted(ctt, T))
            if not (jt < len(ctt) and ctt[jt] == T
                    and int(sidet[jt]) == int(side[j])):
                t2 = False
                print(f"  T2 FAIL {family}/{sym} j={j}: side={side[j]} "
                      f"rebuilt={sidet[jt] if jt < len(sidet) else 'OOB'}")
            # T3: mutate all 5m rows closing after T by +1%
            d5m = {k: v.copy() for k, v in d5_full.items()}
            mut = ct5 > T
            for kk in ("open", "high", "low", "close"):
                d5m[kk][mut] *= 1.01
            barm = {"5m_" + k: d5m[k] for k in ("ts", "open", "high", "low", "close")}
            for name, tfm in TFS.items():
                bb = bars_from_5m(d5m, tfm)
                for kk in BAR_KEYS:
                    barm[f"{name}_{kk}"] = bb[kk]
            sidem = signal_fn(barm, sym, params)
            ctm = barm[f"{tf}_close_time"]
            jm = int(np.searchsorted(ctm, T))
            if not (jm < len(ctm) and ctm[jm] == T
                    and int(sidem[jm]) == int(side[j])):
                t3 = False
                print(f"  T3 FAIL {family}/{sym} j={j}: side mutated")
            trace.append({"sym": sym, "j": int(j), "decision_ts": T,
                          "max_input_ts": max(chain), "side": int(side[j])})
        ok = t1 and t2 and t3 and len(picks) >= 20
        ok_all = ok_all and ok
        print(f"GATE {family}/{sym}: T1={'PASS' if t1 else 'FAIL'} "
              f"T2={'PASS' if t2 else 'FAIL'} T3={'PASS' if t3 else 'FAIL'} "
              f"({len(picks)} tested) -> {'PASS' if ok else 'CAUSALITY_FAIL'}")
    return ok_all, trace


def save_trace(family, trace):
    p = os.path.join(CACHE, f"gate_trace_{family}.json")
    json.dump(trace, open(p, "w"), indent=1)
    return p


# ------------------------------------------------------------- reports

def report_trades(trades, label):
    m = pooled_metrics(trades, label)
    print_metrics(m)
    return m


# re-exported audited metrics/survival/veto
pf_of = m3lib.pf_of
remove_best_1pct = m3lib.remove_best_1pct
agg_metrics = m3lib.agg_metrics
year_table = m3lib.year_table
survival_veto = m3lib.survival_veto
veto_fail = m3lib.veto_fail
veto_warn = m3lib.veto_warn
stress_common = m3lib.stress_common
print_metrics = m3lib.print_metrics
mtf_replay = m3lib.mtf_replay            # tick-exact engine (EURUSD only)
