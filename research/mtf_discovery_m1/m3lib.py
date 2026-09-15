#!/usr/bin/env python3
"""MULTITIMEFRAME_DISCOVERY_M1 library.

Signals on M5/M15/H1/H4 completed bars; ticks only for execution.
Reuses the LAB-audited data layer (infra_lib.load_year / m1_bars) and the
m2lib metrics/survival/veto blocks verbatim. Execution semantics mirror
m2lib.m2_replay exactly (verified by equivalence test) with a vectorized
exit search so multi-day holds stay tractable.

Units: int64 ns UTC timestamps, float64 prices, 1 pip = 1e-4, 1R = SL pips.
Budget: 80 experiments / 12 families. IDs M3_E001..M3_E080.
"""
import csv
import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
M1DIR = os.path.join(HERE, "..", "autonomous_edge_discovery_m1")
M2DIR = os.path.join(HERE, "..", "autonomous_edge_discovery_m2")
for p in (M1DIR, M2DIR):
    if p not in sys.path:
        sys.path.append(p)   # APPEND: legacy dirs must never shadow locals
import infra_lib as I            # validated data layer (load_year, m1_bars)
import m2lib                     # metrics/survival/veto reused verbatim

NS = I.NS
PIP = I.PIP
CACHE = os.path.join(HERE, "cache")
os.makedirs(CACHE, exist_ok=True)

DISCOVERY_YEARS = list(range(2010, 2018))   # 2010-01-04 .. 2017-12-31 only
TFS = {"M5": 5, "M15": 15, "H1": 60, "H4": 240}   # minutes

# ------------------------------------------------------------------ ledger

LEDGER = os.path.join(HERE, "RESEARCH_LEDGER_M3.csv")
EXP_COUNTER = os.path.join(HERE, "EXPERIMENT_COUNTER_M3.txt")
FAM_COUNTER = os.path.join(HERE, "FAMILY_COUNTER_M3.txt")
MAX_EXP = 80          # mission 11: hard stop at #80
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
    """Configs already burned inside one family (<= 8 per mission 11)."""
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
    return f"M3_E{n:03d}"


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


# ------------------------------------------------------------------- bars

def bars_from_m1(m1, tf_min):
    """Completed higher-TF bars from M1 bars (close-time labelled).
    Bucket id = (close_time-1)//tf  (an M1 bar closing exactly on the tf
    boundary belongs to the tf bar ending there, same idiom as
    infra_lib.h4_closes). Bars exist only where ticks exist (observed bars)."""
    tf = tf_min * 60 * NS
    ct = m1["close_time"]
    g = (ct - 1) // tf
    ug, first = np.unique(g, return_index=True)
    idx = np.searchsorted(g, ug, side="right") - 1          # last M1 in bucket
    # per-bucket first M1 index:
    fid = np.searchsorted(g, ug, side="left")
    lo = np.minimum.reduceat(m1["low"], fid)
    hi = np.maximum.reduceat(m1["high"], fid)
    return {
        "start": (ug * tf).astype(np.int64),
        "close_time": ((ug + 1) * tf).astype(np.int64),
        "open": m1["open"][fid],
        "high": hi, "low": lo,
        "close": m1["close"][idx],
        "n_m1": (idx - fid + 1).astype(np.int64),
        "last_tick_ts": m1["last_tick_ts"][idx],
    }


def build_year(year):
    """Cached M1 + M5/M15/H1/H4 bars for one discovery year."""
    f = os.path.join(CACHE, f"mtfbars_{year}.npz")
    if os.path.exists(f):
        z = np.load(f)
        return {k: z[k] for k in z.files}
    ts, bid, ask = I.load_year(year)
    m1 = I.m1_bars(ts, bid, ask)
    out = {"m1_" + k: m1[k] for k in
           ("start", "close_time", "open", "high", "low", "close")}
    for name, tf in TFS.items():
        b = bars_from_m1(m1, tf)
        for k in ("start", "close_time", "open", "high", "low", "close"):
            out[f"{name}_{k}"] = b[k]
    np.savez_compressed(f, **out)
    return out


def hhmm(ct):
    return ((ct // NS // 3600) % 24).astype(np.int64) * 100 \
        + ((ct // NS % 3600) // 60)


# ------------------------------------------------------------- indicators
# All causal: value at bar i uses bars 0..i (bar i is completed at decision).

def sma(x, n):
    return pd.Series(x).rolling(n).mean().to_numpy()


def std(x, n):
    return pd.Series(x).rolling(n).std(ddof=0).to_numpy()


def ema(x, n):
    return pd.Series(x).ewm(span=n, adjust=False).mean().to_numpy()


def atr(high, low, close, n):
    pc = np.roll(close, 1); pc[0] = close[0]
    tr = np.maximum(high - low, np.maximum(np.abs(high - pc), np.abs(low - pc)))
    return pd.Series(tr).rolling(n).mean().to_numpy() / PIP   # pips


def zsc(x, n):
    m, s = sma(x, n), std(x, n)
    return np.where(s > 0, (x - m) / s, np.nan)


def donhi(close, n):
    """Highest close of the previous n bars (bars i-n..i-1; bar i excluded so
    'close breaks the n-bar extreme' is a same-bar event, not a tautology)."""
    return pd.Series(close).rolling(n).max().shift(1).to_numpy()


def donlo(close, n):
    return pd.Series(close).rolling(n).min().shift(1).to_numpy()


def adx(high, low, close, n):
    """Classic Wilder ADX (causal, NaN until 2n bars)."""
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


# ---------------------------------------------------------------- screen

def sig_bars(bars, tf):
    """Extract plain {open,high,low,close,close_time} for one signal TF."""
    return {k: bars[f"{tf}_{k}"] for k in
            ("open", "high", "low", "close", "close_time")}


def screen_year(bars, side, horizons):
    """Gross mid-price forward returns for one year's signal bars.
    side: int8 array on the signal TF (+1/-1/0). Entry = next bar open,
    exit = close[i+h] (mid). Non-overlapping per side in time order.
    Returns {h: (list of (year, side, ret_pips))}."""
    opn, close, n = bars["open"], bars["close"], len(bars["close"])
    out = {h: [] for h in horizons}
    for h in horizons:
        last = -10 ** 9
        for i in np.flatnonzero(side != 0):
            if i <= last or i + 1 >= n:
                continue
            j = min(i + h, n - 1)
            ret = side[i] * (close[j] - opn[i + 1]) / PIP
            out[h].append(ret)
            last = j
    return out


def screen_years(sig_fn, years=DISCOVERY_YEARS, horizons=(6, 12, 18, 24)):
    """sig_fn(bars, year) -> side array on the signal TF. Pools per-year
    non-overlapping trades. Returns {h: {'all': arr, 'y': {yr: arr}}}. Flattens
    sides (both) — callers log side splits separately when needed."""
    out = {h: {"y": {}} for h in horizons}
    for y in years:
        bars = build_year(y)
        side = sig_fn(bars, y)
        res = screen_year(sig_bars(bars, sig_fn.signal_tf), side, horizons)
        for h in horizons:
            out[h]["y"][y] = np.asarray(res[h])
    for h in horizons:
        out[h]["all"] = np.concatenate([out[h]["y"][y] for y in years]) \
            if all(len(out[h]["y"][y]) for y in years) else \
            np.concatenate([out[h]["y"][y] for y in years])
    return out


def summarize(title, res, horizons):
    print(f"--- {title} ---")
    rows = []
    for h in horizons:
        per = res[h]["y"]
        nn = sum(len(v) for v in per.values())
        means = {y: (float(v.mean()) if len(v) >= 5 else np.nan)
                 for y, v in per.items()}
        pos = sum(1 for m in means.values() if np.isfinite(m) and m > 0)
        pool = res[h]["all"]
        mean = float(pool.mean()) if len(pool) else np.nan
        sd = float(pool.std(ddof=1)) if len(pool) > 1 else np.nan
        t = mean / (sd / np.sqrt(len(pool))) if len(pool) > 2 and sd > 0 else np.nan
        print(f"h={h:>3} N={nn:>5} posYR={pos}/8 pooled={mean:+.2f}p t={t:+.1f} | "
              + " ".join(f"{y}:{means[y]:+.1f}" for y in sorted(per)
                         if np.isfinite(means[y])))
        rows.append((h, nn, pos, mean, t))
    return rows


# ---------------------------------------------------------------- replay

def mtf_replay(ts, bid, ask, decisions, sl_pips, tp_pips, t_exit_min,
               latency_ns=5 * NS, slip_pips=0.0, wait_ns=30 * NS,
               tp_levels=None, sl_levels=None):
    """Tick-exact replay; semantics identical to m2lib.m2_replay (verified by
    tests/test_replay_equivalence.py) with the exit scan vectorized.
    decisions: dict with sorted 'ts' (ns) and 'side' arrays.
    sl_pips/tp_pips: float pips; OR per-decision absolute levels via
    tp_levels / sl_levels (structure exits frozen at decision time)."""
    n = len(decisions["ts"])
    trades = []
    no_fill = 0
    last_exit_ts = -1
    slip = slip_pips * PIP
    nts = len(ts)
    for j in range(n):
        side = int(decisions["side"][j])
        if side == 0:
            continue
        d = int(decisions["ts"][j])
        if d < last_exit_ts:
            continue
        i0 = int(np.searchsorted(ts, d + latency_ns, side="left"))
        i1 = int(np.searchsorted(ts, d + latency_ns + wait_ns, side="left"))
        if i0 >= i1:
            no_fill += 1
            continue
        k = i0
        entry = float(ask[k] if side == 1 else bid[k]) + (slip if side == 1 else -slip)
        if sl_levels is not None:
            stop = float(sl_levels[j])
        else:
            stop = entry - side * sl_pips * PIP
        tgt = (float(tp_levels[j]) if tp_levels is not None
               else entry + side * tp_pips * PIP)
        t_end = int(ts[k]) + t_exit_min * 60 * NS
        m_end = int(np.searchsorted(ts, t_end, side="right")) - 1
        m0 = k + 1
        exit_ts = None
        if m_end >= m0:
            px = bid if side == 1 else ask
            seg = px[m0:m_end + 1]
            hit_stop = np.flatnonzero(seg <= stop) if side == 1 \
                else np.flatnonzero(seg >= stop)
            hit_tgt = np.flatnonzero(seg >= tgt) if side == 1 \
                else np.flatnonzero(seg <= tgt)
            i_s = int(hit_stop[0]) if len(hit_stop) else 10 ** 12
            i_t = int(hit_tgt[0]) if len(hit_tgt) else 10 ** 12
            if i_s < i_t:                                   # stop priority
                m = m0 + i_s
                exit_ts = int(ts[m])
                exit_px = float(px[m]) - slip if side == 1 else float(px[m]) + slip
                reason = "STOP"
            elif i_t < 10 ** 12:
                exit_ts = int(ts[m0 + i_t])
                exit_px = float(tgt) - slip if side == 1 else float(tgt) + slip
                reason = "TARGET"
            else:
                # m2 semantics: time exit at the FIRST tick strictly after
                # t_end (loop exits when ts[m] > t_end); clamp to last tick.
                m = m_end + 1 if m_end + 1 < nts else nts - 1
                exit_ts = int(ts[m])
                exit_px = float(px[m]) + (-slip if side == 1 else slip)
                reason = "TIME"
        else:
            m = m_end + 1 if m_end + 1 < nts else nts - 1
            exit_ts = int(ts[m])
            exit_px = float(bid[m] if side == 1 else ask[m])
            exit_px += -slip if side == 1 else slip
            reason = "TIME"
        net = side * (exit_px - entry) / PIP
        risk_pips = (abs(entry - float(sl_levels[j])) / PIP
                     if sl_levels is not None else sl_pips)
        trades.append({"j": int(j), "side": side, "decision_ts": d,
                       "entry_idx": int(k), "entry_ts": int(ts[k]),
                       "entry": entry, "exit_ts": exit_ts, "exit_px": exit_px,
                       "reason": reason, "net_pips": float(net),
                       "r": float(net / risk_pips),
                       "risk_pips": float(risk_pips)})
        last_exit_ts = exit_ts
    return trades, no_fill


def stress_common(base_trades, stress_trades):
    """Multi-year-safe: key on (decision_ts, side), not per-year j."""
    bmap = {(t["decision_ts"], t["side"]): t for t in base_trades}
    smap = {(t["decision_ts"], t["side"]): t for t in stress_trades}
    keys = sorted(set(bmap) & set(smap))
    return [bmap[k] for k in keys], [smap[k] for k in keys]


# Reused verbatim from m2lib: pf_of, remove_best_1pct, agg_metrics,
# year_table, survival_veto, veto_fail, veto_warn.
pf_of = m2lib.pf_of
remove_best_1pct = m2lib.remove_best_1pct
agg_metrics = m2lib.agg_metrics
year_table = m2lib.year_table
survival_veto = m2lib.survival_veto
veto_fail = m2lib.veto_fail
veto_warn = m2lib.veto_warn


def replay_metrics(trades, label):
    m = agg_metrics(trades, label)
    m["stress_common_ev"] = None
    return m


def print_metrics(m):
    if m.get("N", 0) == 0:
        print("NO_TRADES")
        return
    print(f"N={m['N']} tpm={m['trades_per_month']} mean={m['mean_pips']}p "
          f"med={m['median_pips']}p PF={m['PF']} expR={m['expectancy_r']} "
          f"win={m['win_rate']} posYR={m['pos_years']} posM={m['pos_months']}/{m['n_months']}")
    print(f"  L={m['long_r']}R S={m['short_r']}R remove_best={m['remove_best']}p "
          f"maxDD={m['max_dd_r']}R worstYR={m['worst_year_r']}R "
          f"worst12m={m['worst_rolling12m_r']}R exits={m['exits']}")
    print(f"  yearlyR={m['yearly_r']}")


def save_trades(trades, name):
    p = os.path.join(CACHE, name)
    json.dump(trades, open(p, "w"))
    return p


# ---------------------------------------------------------------- gate

def mtf_causality_gate(family, sig_fn, n_samples=24, seed=20260915):
    """T1/T2/T3 gate for an MTF signal, run on discovery year 2010.
    sig_fn(bars_mtf, year) -> side array on signal TF (vectorized path).
    We verify the DECISION RECONSTRUCTION property: for sampled firing bars,
    rebuilding all bars from truncated ticks (only ticks <= decision T) must
    reproduce the same side at the same bar, and mutating all ticks after T
    must not change it. bars_mtf is built by build_bars_truncated below so the
    gate exercises the production bar builder, not a parallel one."""
    ts, bid, ask = I.load_year(2010)
    full = build_year(2010)
    side = sig_fn(full, 2010)
    tf_key = sig_fn.signal_tf            # e.g. "M15"
    ct = full[f"{tf_key}_close_time"]
    fire = np.flatnonzero(side != 0)
    fire = fire[ct[fire] < ct[-1] - 3600 * NS]   # need room after decision
    rng = np.random.default_rng(seed)
    picks = list(rng.permutation(fire)[:n_samples]) if len(fire) > n_samples else list(fire)
    t1 = t2 = t3 = True
    tested = 0
    trace = []
    for j in picks:
        T = int(ct[j])
        its = last_input_ts(full, tf_key, j)          # provenance: bar close of every input
        if not all(x <= T for x in its):
            t1 = False
            print(f"  T1 FAIL {family} j={j}: max_input={max(its)} T={T}")
        # T2 truncation: rebuild bars from ticks <= T only
        m = int(np.searchsorted(ts, T, side="right"))
        m1 = I.m1_bars(ts[:m], bid[:m], ask[:m])
        part = mtf_from_m1(m1)
        sidep = sig_fn(part, 2010)
        ctp = part[f"{tf_key}_close_time"]
        jp = int(np.searchsorted(ctp, T))
        ok2 = (jp < len(ctp) and ctp[jp] == T and int(sidep[jp]) == int(side[j]))
        if not ok2:
            t2 = False
            print(f"  T2 FAIL {family} j={j}: side={side[j]} rebuilt="
                  f"{sidep[jp] if jp < len(sidep) else 'OOB'}")
        # T3 future mutation: shift all ticks after T by +50 pips
        bid3, ask3 = bid.copy(), ask.copy()
        mut = ts > T
        bid3[mut] += 50 * PIP
        ask3[mut] += 50 * PIP
        m1b = I.m1_bars(ts, bid3, ask3)
        partb = mtf_from_m1(m1b)
        sideb = sig_fn(partb, 2010)
        ctb = partb[f"{tf_key}_close_time"]
        jb = int(np.searchsorted(ctb, T))
        ok3 = (jb < len(ctb) and ctb[jb] == T and int(sideb[jb]) == int(side[j]))
        if not ok3:
            t3 = False
            print(f"  T3 FAIL {family} j={j}: side mutated")
        tested += 1
        trace.append({"j": int(j), "decision_ts": T,
                      "max_input_ts": max(its) if its else None,
                      "n_inputs": len(its), "side": int(side[j])})
    ok = t1 and t2 and t3 and tested >= 20
    print(f"GATE {family}: T1={'PASS' if t1 else 'FAIL'} "
          f"T2={'PASS' if t2 else 'FAIL'} T3={'PASS' if t3 else 'FAIL'} "
          f"({tested} tested) -> {'PASS' if ok else 'CAUSALITY_FAIL'}")
    return ok, tested, trace


def mtf_from_m1(m1):
    out = {"m1_" + k: m1[k] for k in
           ("start", "close_time", "open", "high", "low", "close")}
    for name, tf in TFS.items():
        b = bars_from_m1(m1, tf)
        for k in ("start", "close_time", "open", "high", "low", "close"):
            out[f"{name}_{k}"] = b[k]
    return out


def last_input_ts(bars, tf_key, j):
    """Timestamp provenance for decision j. Every feature input is a COMPLETED
    signal-TF/context bar; the latest such bar closes exactly at the decision
    timestamp T, earlier inputs close strictly before it. We verify and record
    the local chain (decision bar close, previous bar close, and the close of
    the decision bar of the coarsest context TF) so max_input <= T is checked
    on real timestamps, not asserted."""
    ct = bars[f"{tf_key}_close_time"]
    T = int(ct[j])
    chain = [T]
    if j >= 1:
        chain.append(int(ct[j - 1]))
    for other in TFS:
        o = bars[f"{other}_close_time"]
        k = int(np.searchsorted(o, T, side="right")) - 1
        if k >= 0:
            chain.append(int(o[k]))
    return chain


def save_trace(family, trace):
    p = os.path.join(CACHE, f"gate_trace_{family}.json")
    json.dump(trace, open(p, "w"), indent=1)
    return p
