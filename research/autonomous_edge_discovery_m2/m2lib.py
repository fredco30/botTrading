#!/usr/bin/env python3
"""AUTONOMOUS_EDGE_DISCOVERY_M2 library.

Reuses ONLY the validated generic infrastructure from
research/autonomous_edge_discovery_m1 (LAB_AUDIT_M0 LAB_PASS data layer,
audited replay-engine logic — copied here with execution parameters made
explicit). No signal logic is imported from any prior campaign.

Units: int64 ns UTC timestamps, float64 prices, 1 pip = 1e-4, 1R = SL pips.

Budget: 69 experiments / 7 families (mission 2). IDs M2_E001..M2_E069.
"""
import csv
import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
M1DIR = os.path.join(HERE, "..", "autonomous_edge_discovery_m1")
sys.path.insert(0, M1DIR)
import infra_lib as I            # validated data layer (load_year, m1_bars)

NS = I.NS
PIP = I.PIP
CACHE = os.path.join(HERE, "cache")
os.makedirs(CACHE, exist_ok=True)

DISCOVERY_YEARS = list(range(2010, 2018))   # 2010-01-04 .. 2017-12-31
SEALED_YEARS = (2018,)                      # only months 7-12, after freeze

# ------------------------------------------------------------------ ledger

LEDGER = os.path.join(HERE, "RESEARCH_LEDGER_M2.csv")
EXP_COUNTER = os.path.join(HERE, "EXPERIMENT_COUNTER_M2.txt")
FAM_COUNTER = os.path.join(HERE, "FAMILY_COUNTER_M2.txt")
MAX_EXP = 69          # mission 2: no experiment #70
MAX_FAMILIES = 7      # mission 2: no family #8
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


def next_exp_id():
    n = experiments_used() + 1
    if n > MAX_EXP:
        raise RuntimeError(f"HARD BUDGET STOP: M2 experiment #{n} > {MAX_EXP}")
    with open(EXP_COUNTER, "w") as f:
        f.write(str(n))
    return f"M2_E{n:03d}"


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


# ------------------------------------------------- bars + tick extras

def add_n_ticks(ts, bars):
    """Tick counts per M1 bar (causal; part of bar construction)."""
    tf = 60 * NS
    ids = ts // tf
    bounds = np.flatnonzero(np.diff(ids)) + 1
    si = np.concatenate(([0], bounds))
    ei = np.concatenate((bounds, [len(ts)]))
    bars = dict(bars)
    bars["n_ticks"] = (ei - si).astype(np.int64)
    return bars


def extras_from_ticks(ts, bid, ask):
    """M1 bars + per-bar tick microstructure extras from raw tick arrays.
    All extras aggregate ONLY within-bar tick moves (boundary diffs excluded).
    Vectorized with add.reduceat: segment b of `arr` sums arr[si[b]:ei[b]-1],
    which is exactly the diffs internal to bar b."""
    bars = add_n_ticks(ts, I.m1_bars(ts, bid, ask))
    tf = 60 * NS
    ids = ts // tf
    bounds = np.flatnonzero(np.diff(ids)) + 1
    si = np.concatenate(([0], bounds))
    ei = np.concatenate((bounds, [len(ts)]))
    nb = len(bars["close"])
    mid = (bid + ask) / 2.0
    spr = (ask - bid) / PIP
    bd = np.diff(mid)
    valid = np.ones(len(bd), dtype=bool)
    valid[bounds - 1] = False        # diffs crossing into the next bar
    w = np.where(valid, bd, 0.0)
    # a truncated tail can leave a bar whose first tick is the last tick:
    # its segment start is out of range for bd (no internal moves) -> zeros
    keep = si < len(bd)
    si_ok = si[keep]
    up = np.zeros(len(si)); dn = np.zeros(len(si)); path = np.zeros(len(si))
    up[keep] = np.add.reduceat((w > 0).astype(np.float64), si_ok)
    dn[keep] = np.add.reduceat((w < 0).astype(np.float64), si_ok)
    path[keep] = np.add.reduceat(np.abs(w) / PIP, si_ok)
    mean_spr = np.add.reduceat(spr, si) / bars["n_ticks"]
    c_spr = spr[ei - 1]
    ex = {
        "n_ticks": bars["n_ticks"].astype(np.float64),
        "up": up, "dn": dn, "path": path,
        "mean_spr": mean_spr, "c_spr": c_spr,
        "start": bars["start"], "close_time": bars["close_time"],
        "open": bars["open"], "high": bars["high"], "low": bars["low"],
        "close": bars["close"], "last_tick_ts": bars["last_tick_ts"],
    }
    return ex


def build_year(year):
    """Cached per-year extras (base + rolling) for a discovery year."""
    f = os.path.join(CACHE, f"m2x_{year}.npz")
    if os.path.exists(f):
        z = np.load(f)
        ex = {k: z[k] for k in z.files}
        return ex
    ex = extras_from_ticks(*I.load_year(year))
    np.savez_compressed(f, **ex)
    return ex


def roll(arr, w, fn):
    return getattr(pd.Series(arr).rolling(w), fn)().to_numpy()


def rolling_extras(ex, year):
    """Bar-level causal rolling aggregates shared by the families.
    Every window ends at the current completed bar (no shift needed beyond
    the caller's explicit conventions); NaN until full."""
    close, path, nt = ex["close"], ex["path"], ex["n_ticks"]
    out = dict(ex)
    s_close = pd.Series(close)
    for w in (15, 30, 60, 120, 240):
        netp = (s_close - s_close.shift(w)).abs().to_numpy() / PIP  # pips
        pth = pd.Series(path).rolling(w).sum().to_numpy()
        out[f"er{w}"] = np.where(pth > 0, netp / np.maximum(pth, 1e-12), np.nan)
        ntw = pd.Series(nt).rolling(w).sum().to_numpy()
        out[f"dpt{w}"] = np.where(ntw > 0, netp / np.maximum(ntw, 1), np.nan)
        out[f"net{w}"] = (s_close - s_close.shift(w)).to_numpy() / PIP
    out["rv30"] = pd.Series(close).diff().abs().rolling(30).mean().to_numpy() / PIP
    out["rv1440"] = pd.Series(close).diff().abs().rolling(1440).mean().to_numpy() / PIP
    out["volratio"] = np.where(out["rv1440"] > 0, out["rv30"] / out["rv1440"], np.nan)
    out["spr_med24"] = pd.Series(ex["c_spr"]).rolling(1440).median().to_numpy()
    out["spr_q10_24"] = pd.Series(ex["c_spr"]).rolling(1440).quantile(0.10).to_numpy()
    out["spr_q90_24"] = pd.Series(ex["c_spr"]).rolling(1440).quantile(0.90).to_numpy()
    out["month"] = pd.to_datetime(ex["close_time"], utc=True).month.to_numpy()
    out["yearv"] = pd.to_datetime(ex["close_time"], utc=True).year.to_numpy()
    out["hhmm"] = ((ex["close_time"] // NS // 3600) % 24).astype(np.int64) * 100 \
        + ((ex["close_time"] // NS % 3600) // 60)
    return out


# ---------------------------------------------------- execution (validated
# logic, parameters explicit — mirrors infra_lib.replay exactly otherwise)

def m2_replay(ts, bid, ask, bars, sig, sl_pips, tp_pips, t_exit_min,
              latency_ns=5 * NS, slip_pips=0.0, wait_ns=30 * NS):
    """Entry: first tick in [decision+latency, decision+latency+wait) on the
    execution side (LONG ASK / SHORT BID) + adverse slip. Exit: first event
    wins, STOP priority; gap-through stop fills at the actual adverse tick;
    target capped; time exit on the executable side; every fill pays adverse
    slip. One position at a time (signals while open ignored). 1R = sl_pips."""
    slip = slip_pips * PIP
    n = len(bars["close"])
    trades = []
    no_fill = 0
    last_exit_ts = -1
    for j in range(n):
        side = int(sig[j])
        if side == 0:
            continue
        d = int(bars["close_time"][j])
        if d < last_exit_ts:
            continue
        i0 = int(np.searchsorted(ts, d + latency_ns, side="left"))
        i1 = int(np.searchsorted(ts, d + latency_ns + wait_ns, side="left"))
        if i0 >= i1:
            no_fill += 1
            continue
        k = i0
        entry = float(ask[k] if side == 1 else bid[k]) + (slip if side == 1 else -slip)
        stop = entry - side * sl_pips * PIP
        tgt = entry + side * tp_pips * PIP
        t_end = int(ts[k]) + t_exit_min * 60 * NS
        m = k + 1
        nts = len(ts)
        exit_ts = None
        while m < nts and ts[m] <= t_end:
            if side == 1:
                if bid[m] <= stop:
                    exit_ts, exit_px, reason = int(ts[m]), float(bid[m]) - slip, "STOP"
                    break
                if bid[m] >= tgt:
                    exit_ts, exit_px, reason = int(ts[m]), float(tgt) - slip, "TARGET"
                    break
            else:
                if ask[m] >= stop:
                    exit_ts, exit_px, reason = int(ts[m]), float(ask[m]) + slip, "STOP"
                    break
                if ask[m] <= tgt:
                    exit_ts, exit_px, reason = int(ts[m]), float(tgt) + slip, "TARGET"
                    break
            m += 1
        if exit_ts is None:
            if m >= nts:
                m = nts - 1
            exit_ts = int(ts[m])
            exit_px = float(bid[m] if side == 1 else ask[m])
            exit_px += -slip if side == 1 else slip
            reason = "TIME"
        net = side * (exit_px - entry) / PIP
        trades.append({"j": int(j), "side": side, "decision_ts": d,
                       "entry_idx": int(k), "entry_ts": int(ts[k]),
                       "entry": entry, "exit_ts": exit_ts, "exit_px": exit_px,
                       "reason": reason, "net_pips": float(net),
                       "r": float(net / sl_pips)})
        last_exit_ts = exit_ts
    return trades, no_fill


def common_sample(base_trades, stress_trades):
    bmap = {t["j"]: t for t in base_trades}
    smap = {t["j"]: t for t in stress_trades}
    keys = sorted(set(bmap) & set(smap))
    return [bmap[k] for k in keys], [smap[k] for k in keys]


# ---------------------------------------------------------------- metrics

def pf_of(net):
    wins = net[net > 0]
    losses = net[net < 0]
    if len(losses) and losses.sum() != 0:
        return float(min(wins.sum() / abs(losses.sum()), 999.0))
    return 999.0


def remove_best_1pct(x):
    x = np.sort(np.asarray(x, dtype=np.float64))
    n = len(x)
    k = max(1, int(np.ceil(0.01 * n)))
    if k >= n:
        return float("nan")
    return float(x[:n - k].mean())


def agg_metrics(trades, label):
    """Multi-year pooled metrics (mission 14 fields)."""
    if not trades:
        return {"label": label, "N": 0, "VERDICT": "NO_TRADES"}
    trades = sorted(trades, key=lambda t: t["entry_ts"])
    net = np.array([t["net_pips"] for t in trades])
    r = np.array([t["r"] for t in trades])
    yrs = np.array([pd.Timestamp(t["entry_ts"], unit="ns", tz="UTC").year
                    for t in trades])
    yms = pd.to_datetime([t["entry_ts"] for t in trades], unit="ns", utc=True)
    ym = yms.to_period("M").astype(str).to_numpy()
    dfm = pd.Series(r, index=ym).groupby(level=0).sum()
    mp = dfm.rolling(12).sum().dropna()
    yearly = pd.Series(r, index=yrs).groupby(level=0).sum()
    pos_years = int((pd.Series(net, index=yrs).groupby(level=0).sum() > 0).sum())
    dfd = pd.Series(net, index=ym).groupby(level=0).sum()
    pos_months = int((dfd > 0).sum())
    lr = r[[i for i, t in enumerate(trades) if t["side"] == 1]]
    sr = r[[i for i, t in enumerate(trades) if t["side"] == -1]]
    cum = np.cumsum(r)
    peak = np.maximum.accumulate(cum)
    return {"label": label, "N": len(trades),
            "trades_per_month": round(len(trades) / max(len(dfm), 1), 2),
            "mean_pips": round(float(net.mean()), 3),
            "median_pips": round(float(np.median(net)), 3),
            "total_pips": round(float(net.sum()), 2),
            "PF": round(pf_of(net), 3),
            "expectancy_r": round(float(r.mean()), 4),
            "win_rate": round(float((net > 0).mean()), 4),
            "long_r": round(float(lr.mean()), 4) if len(lr) else None,
            "short_r": round(float(sr.mean()), 4) if len(sr) else None,
            "pos_months": pos_months, "n_months": len(dfm),
            "pos_years": f"{pos_years}/{len(yearly)}",
            "yearly_r": {int(k): round(float(v), 2) for k, v in yearly.items()},
            "yearly_pips": {int(k): round(float(v), 1) for k, v in
                            pd.Series(net, index=yrs).groupby(level=0).sum().items()},
            "remove_best": round(remove_best_1pct(net), 3),
            "max_dd_r": round(float((peak - cum).max()) if len(cum) else 0.0, 2),
            "worst_year_r": round(float(yearly.min()), 2),
            "worst_rolling12m_r": round(float(mp.min()), 2),
            "exits": {s: sum(1 for t in trades if t["reason"] == s)
                      for s in ("STOP", "TARGET", "TIME")}}


def year_table(trades):
    """Per-calendar-year breakdown for a trade list."""
    out = {}
    for t in trades:
        y = pd.Timestamp(t["entry_ts"], unit="ns", tz="UTC").year
        d = out.setdefault(y, {"N": 0, "pips": 0.0, "r": 0.0, "wins": 0})
        d["N"] += 1
        d["pips"] += t["net_pips"]
        d["r"] += t["r"]
        d["wins"] += 1 if t["net_pips"] > 0 else 0
    return {y: {"N": d["N"], "mean_pips": round(d["pips"] / d["N"], 3),
                "PF": None, "pips": round(d["pips"], 1), "r": round(d["r"], 2),
                "win_rate": round(d["wins"] / d["N"], 3)}
            for y, d in sorted(out.items())}


def survival_veto(trades, start_capital=500.0, risk_frac=0.005):
    """Mission 16 diagnostic capital path. NOT an optimization: fixed 0.5%
    of CURRENT equity risked per trade, r multiples applied multiplicatively."""
    if not trades:
        return {"FINAL_CAPITAL": start_capital}
    trades = sorted(trades, key=lambda t: t["entry_ts"])
    eq = start_capital
    peak = start_capital
    max_dd = 0.0
    lowest = start_capital
    peak_ts = trades[0]["entry_ts"]
    longest_dd_days = 0.0
    for t in trades:
        eq *= (1.0 + risk_frac * t["r"])
        lowest = min(lowest, eq)
        dd = 1.0 - eq / peak
        if dd > max_dd:
            max_dd = dd
        if eq > peak:
            peak = eq
            peak_ts = t["entry_ts"]
        cur_dd_days = ((t["entry_ts"] - peak_ts) / 86400.0 / NS)
        longest_dd_days = max(longest_dd_days, cur_dd_days)
    # proper per-period products
    yr = {}
    for t in trades:
        y = pd.Timestamp(t["entry_ts"], unit="ns", tz="UTC").year
        yr.setdefault(y, []).append(t["r"])
    year_ret = {y: float(np.prod([1 + risk_frac * x for x in v]) - 1)
                for y, v in yr.items()}
    mr = {}
    for t in trades:
        m = pd.Timestamp(t["entry_ts"], unit="ns", tz="UTC").to_period("M")
        mr.setdefault(m, []).append(t["r"])
    mret = pd.Series({m: float(np.prod([1 + risk_frac * x for x in v]) - 1)
                      for m, v in mr.items()}).sort_index()
    roll12 = mret.rolling(12).apply(lambda x: float(np.prod(1 + x) - 1), raw=True).dropna()
    return {"FINAL_CAPITAL": round(eq, 2),
            "MAX_DRAWDOWN_PERCENT": round(max_dd * 100, 2),
            "WORST_CALENDAR_YEAR_PERCENT": round(min(year_ret.values()) * 100, 2),
            "WORST_ROLLING_12M_PERCENT": round(float(roll12.min()) * 100, 2)
                if len(roll12) else None,
            "LOWEST_EQUITY": round(lowest, 2),
            "LONGEST_DRAWDOWN_DURATION_DAYS": round(float(longest_dd_days), 1),
            "yearly_returns_percent": {y: round(v * 100, 2)
                                       for y, v in sorted(year_ret.items())}}


def veto_fail(s):
    return (s["MAX_DRAWDOWN_PERCENT"] >= 50.0
            or s["LOWEST_EQUITY"] <= 250.0
            or s["WORST_CALENDAR_YEAR_PERCENT"] <= -40.0
            or (s["WORST_ROLLING_12M_PERCENT"] is not None
                and s["WORST_ROLLING_12M_PERCENT"] <= -40.0))


def veto_warn(s):
    return (s["MAX_DRAWDOWN_PERCENT"] >= 30.0
            or s["WORST_CALENDAR_YEAR_PERCENT"] <= -25.0)


# ------------------------------------------------------------ gate (§8)

def causality_gate(family, feat_fn, n_samples=24, seed=20260915):
    """Runs on discovery year 2010 (multi-year campaign; all discovery years
    are inspectable). feat_fn(bars, extras, j) -> dict(value|None, input_ts,
    aux?). T1 max input ts <= decision T; T2 truncation identity; T3
    future-mutation identity; >=20 firing timestamps with recorded trace."""
    ts, bid, ask = I.load_year(2010)
    bars = add_n_ticks(ts, I.m1_bars(ts, bid, ask))
    extras = rolling_extras(extras_from_ticks(ts, bid, ask), 2010)
    n = len(bars["close"])
    rng = np.random.default_rng(seed)
    finite = []
    for j in range(500, n):
        f = feat_fn(bars, extras, j)
        if f is not None and f["value"] is not None and np.isfinite(f["value"]):
            finite.append(j)
    picks = list(rng.permutation(finite)[:n_samples]) if len(finite) > n_samples else finite
    t1 = t2 = t3 = True
    tested = 0
    trace = []
    for j in picks:
        T = int(bars["close_time"][j])
        f = feat_fn(bars, extras, int(j))
        if f is None or f["value"] is None or not np.isfinite(f["value"]):
            continue
        tested += 1
        its = [int(x) for x in f["input_ts"]]
        aux = f.get("aux")
        if not all(x <= T for x in its):
            t1 = False
            print(f"  T1 FAIL {family} j={j}: max_input={max(its)} T={T}")
        m = int(np.searchsorted(ts, T, side="right"))
        bars_t = add_n_ticks(ts[:m], I.m1_bars(ts[:m], bid[:m], ask[:m]))
        extras_t = rolling_extras(extras_from_ticks(ts[:m], bid[:m], ask[:m]), 2010)
        jt = int(np.searchsorted(bars_t["close_time"], T, side="left"))
        f2 = feat_fn(bars_t, extras_t, jt) if (
            jt < len(bars_t["close_time"])
            and bars_t["close_time"][jt] == T) else None
        if (f2 is None or f2["value"] is None
                or f2["value"] != f["value"]
                or [int(x) for x in f2["input_ts"]] != its
                or f2.get("aux") != aux):
            t2 = False
            print(f"  T2 FAIL {family} j={j}: {f} vs {f2}")
        bid3, ask3 = bid.copy(), ask.copy()
        mut = ts > T
        bid3[mut] += 50 * PIP
        ask3[mut] += 50 * PIP
        bars_m = add_n_ticks(ts, I.m1_bars(ts, bid3, ask3))
        extras_m = rolling_extras(extras_from_ticks(ts, bid3, ask3), 2010)
        f3 = feat_fn(bars_m, extras_m, int(j))
        if (f3 is None or f3["value"] is None
                or f3["value"] != f["value"]
                or [int(x) for x in f3["input_ts"]] != its
                or f3.get("aux") != aux):
            t3 = False
            print(f"  T3 FAIL {family} j={j}: {f} vs {f3}")
        trace.append({"j": int(j), "decision_ts": T,
                      "max_input_ts": max(its) if its else None,
                      "input_ts": its, "value": f["value"], "aux": aux})
    ok = t1 and t2 and t3 and tested >= 20
    print(f"GATE {family}: T1={'PASS' if t1 else 'FAIL'} "
          f"T2={'PASS' if t2 else 'FAIL'} T3={'PASS' if t3 else 'FAIL'} "
          f"({tested} tested) -> {'PASS' if ok else 'CAUSALITY_FAIL'}")
    return ok, tested, trace


def save_trace(family, trace):
    p = os.path.join(CACHE, f"gate_trace_{family}.json")
    json.dump(trace, open(p, "w"), indent=1)
    return p


# --------------------------------------------------- cheap multi-year screen

def screen_years(cond_fn, years=DISCOVERY_YEARS, horizons=(30, 60, 120, 240)):
    """cond_fn(extras dict-of-arrays, year) -> boolean vector. Non-overlapping
    conditional forward returns per year (entry next-bar open, exit close+h).
    Returns {h: {year: (N, mean_pips, t)}}, plus pooled per-h totals."""
    out = {h: {} for h in horizons}
    for y in years:
        ex = rolling_extras(build_year(y), y)
        cond = cond_fn(ex, y)
        close, opn = ex["close"], ex["open"]
        n = len(close)
        idx = np.flatnonzero(cond)
        if len(idx) == 0:
            for h in horizons:
                out[h][y] = (0, np.nan, np.nan)
            continue
        j0 = np.minimum(idx + 1, n - 1)
        for h in horizons:
            j1 = np.minimum(idx + h, n - 1)
            r = (close[j1] - opn[j0]) / PIP
            keep, last = [], -10 ** 9
            for k, i in enumerate(idx):
                if i >= last + h:
                    keep.append(k)
                    last = i
            rr = r[np.array(keep)]
            if len(rr) < 2:
                out[h][y] = (len(rr), np.nan, np.nan)
                continue
            mean = float(rr.mean())
            t = mean / (rr.std(ddof=1) / np.sqrt(len(rr)))
            out[h][y] = (len(rr), round(mean, 3), round(float(t), 2))
    return out


def print_screen(title, res, horizons=(30, 60, 120, 240)):
    print(f"--- {title} ---")
    for h in horizons:
        cells = {y: res[h][y] for y in res[h]}
        nn = sum(v[0] for v in cells.values())
        means = [v[1] for v in cells.values() if v[0] >= 5 and np.isfinite(v[1])]
        pos = sum(1 for m in means if m > 0)
        pooled = float(np.mean([v[1] for v in cells.values()
                                if v[0] >= 5 and np.isfinite(v[1])])) if means else np.nan
        print(f"h={h:>3} N_tot={nn:>5} posYR={pos}/{len(means)} "
              f"meanYR={pooled:+.3f} | " +
              " ".join(f"{y}:{cells[y][0]}({cells[y][1]:+.2f})" if cells[y][0] and np.isfinite(cells[y][1])
                       else f"{y}:0" for y in sorted(cells)))
