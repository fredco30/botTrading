#!/usr/bin/env python3
"""FX_MACRO_RATES_SWING_M1 library.

Macro/rates -> FX multi-hour/multi-day swing discovery. Reuses the audited
FX_MULTIPAIR toolchain (swing_lib -> m2lib/m3lib) for FX bars, replay,
metrics and causality gating, and adds a causal US rates layer:

  * ZT/ZF/ZN 1m futures (Databento GLBX.MDP3, RATES-DATA-M0 store), 1m bars
    labelled by ts_event; features use bars with close_time <= decision T;
  * continuous prices are additively back-adjusted via roll_map.csv so
    horizon log-returns are roll-safe;
  * horizon returns are vol-normalized by a trailing 30-day rolling std of
    the same-horizon return computed on the rates grid (trailing only);
  * NFP/CPI surprises use ALFRED real-time initial vintages vs previous
    published values, standardized by the std of PRIOR surprises only.

Discovery window 2010-06-07..2018-01-01 (rates coverage start caps it).
Sealed: USDJPY, EURUSD 2018H2, 2019+. Budget 10 families / 60 experiments.
"""
import csv
import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
SWDIR = os.path.join(REPO, "research", "fx_multipair_swing_m1")
if SWDIR not in sys.path:
    sys.path.append(SWDIR)

import swing_lib as SW                       # audited FX layer (bars/replay)
from m2lib import agg_metrics, year_table, survival_veto

# m2lib does sys.path.insert(0, M1DIR) at import: re-assert THIS dir so the
# legacy campaign scripts (which run at import time) can never shadow us.
sys.path.insert(0, HERE)

NS = SW.NS
CACHE = os.path.join(HERE, "cache")
os.makedirs(CACHE, exist_ok=True)
RATES_DIR = "E:/ResearchData/botTrading/rates/databento/parquet"
ROLL_MAP = os.path.join(HERE, "roll_map.csv")
EVENTS = os.path.join(HERE, "macro_events_2010_2018_aligned.csv")

RATE_SYMS = ("ZT", "ZF", "ZN")
HOURS = (1, 4, 24, 48, 120)
VOL_DAYS = 30                                 # trailing window for z vol
VOL_BARS = VOL_DAYS * 1440                    # ~calendar days on 1m grid
T0_NS, T1_NS = SW.window_ns("2010-06-07", "2018-01-01")

WINDOW_TAG = ""          # suffix for cache files; set by set_window()


def set_window(t0, t1):
    """Validation-stage rates window (e.g. 2018H2 burn-in). Rates data is
    not part of the protected FX windows; FX access stays sentinel-gated."""
    global T0_NS, T1_NS, _GRIDS, _SAVE, WINDOW_TAG
    T0_NS = int(pd.Timestamp(t0, tz="UTC").value)
    T1_NS = int(pd.Timestamp(t1, tz="UTC").value)
    _GRIDS, _SAVE = {}, None
    WINDOW_TAG = f"{t0}_{t1}".replace("-", "").replace(":", "")


LEDGER = os.path.join(HERE, "RESEARCH_LEDGER_MR.csv")
EXP_COUNTER = os.path.join(HERE, "EXPERIMENT_COUNTER_MR.txt")
FAM_COUNTER = os.path.join(HERE, "FAMILY_COUNTER_MR.txt")
MAX_EXP = 60
MAX_FAMILIES = 10


# --------------------------------------------------------------- budget

def experiments_used():
    return int(open(EXP_COUNTER).read().strip()) if os.path.exists(EXP_COUNTER) else 0


def families_used():
    return int(open(FAM_COUNTER).read().strip()) if os.path.exists(FAM_COUNTER) else 0


def next_exp_id():
    n = experiments_used() + 1
    open(EXP_COUNTER, "w").write(str(n))
    return f"MR_E{n:03d}"


def register_family(family_id):
    p = os.path.join(HERE, "FAMILIES_USED_MR.json")
    used = json.load(open(p)) if os.path.exists(p) else {}
    used[family_id] = used.get(family_id, 0) + 1
    json.dump(used, open(p, "w"), indent=1)
    n = families_used() + 1
    open(FAM_COUNTER, "w").write(str(n))
    return used[family_id]


def log(family_id, mechanism, causality_pass, parameters, N=np.nan,
        mean_pips=np.nan, PF=np.nan, expectancy_r=np.nan, stress_pips=np.nan,
        remove_best_pips=np.nan, status="SCREENED", reason=""):
    rows = []
    if os.path.exists(LEDGER):
        rows = list(csv.DictReader(open(LEDGER)))
    eid = next_exp_id()
    rows.append({"experiment_id": eid, "family_id": family_id,
                 "mechanism": mechanism,
                 "feature_causality_pass": str(causality_pass),
                 "parameters": json.dumps(parameters),
                 "N": N, "mean_pips": mean_pips, "PF": PF,
                 "expectancy_r": expectancy_r, "stress_pips": stress_pips,
                 "remove_best_pips": remove_best_pips,
                 "status": status, "reason": reason})
    with open(LEDGER, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    return eid


# ------------------------------------------------------- rates data layer

def _roll_end_ns():
    out = {"ZT": [], "ZF": [], "ZN": []}
    for r in csv.DictReader(open(ROLL_MAP)):
        out[r["symbol"]].append(
            int(pd.Timestamp(r["end_date"], tz="UTC").value) + 86399 * NS)
    return {k: np.array(sorted(v), dtype="int64") for k, v in out.items()}


def load_rates(sym):
    """Back-adjusted 1m rates series on the discovery window (cached).

    ct = 1m bar CLOSE times (ns UTC); cs = cumsum of 1m log-returns of the
    additively back-adjusted close (roll-safe horizon returns)."""
    p = os.path.join(CACHE, f"rates_{sym}{WINDOW_TAG}.npz")
    if os.path.exists(p):
        z = np.load(p)
        return {k: z[k] for k in z.files}
    df = pd.read_parquet(f"{RATES_DIR}/{sym}.parquet")
    ts = df.index.view("int64")
    close = df["close"].to_numpy(float)
    m = (ts >= T0_NS) & (ts < T1_NS)
    ts, close = ts[m], close[m]
    end_ns = _roll_end_ns()[sym]
    cidx = np.searchsorted(end_ns, ts, side="left")
    adj = close.copy()
    shift = 0.0
    for i in range(1, len(ts)):
        if cidx[i] != cidx[i - 1]:
            shift += close[i - 1] - close[i]     # make series continuous
        adj[i] = close[i] + shift
    ct = ts + 60 * NS                            # bar close time
    cs = np.concatenate(([0.0], np.cumsum(np.diff(np.log(adj)))))
    np.savez_compressed(p, ct=ct, close=adj, cs=cs)
    return {"ct": ct, "close": adj, "cs": cs}


_GRIDS = {}          # name -> {"ct": arr, "z": {h: arr}, "hsum": {h: arr}}
_ROLL_VOLS = {}      # name -> {h: rolling std array} (never truncated)


def _make_grid(name, cs, ct):
    p = os.path.join(CACHE, f"grid_{name.replace('-', '_')}{WINDOW_TAG}.npz")
    if os.path.exists(p):
        z = np.load(p)
        g = {"ct": z["ct"],
             "z": {int(k[1:]): z[k] for k in z.files if k.startswith("z")},
             "hsum": {int(k[1:]): z[k] for k in z.files if k.startswith("h")}}
        _GRIDS[name] = g
        return g
    g = {"ct": ct, "z": {}, "hsum": {}}
    for h in HOURS:
        ns_h = h * 3600 * NS
        s = np.searchsorted(ct, ct - ns_h, side="left")
        e = np.arange(len(ct))
        lo = np.where(s > 0, cs[s - 1], 0.0)
        hs = cs[e] - lo                          # hret ending at each bar
        v = pd.Series(hs).rolling(VOL_BARS).std(ddof=0).to_numpy()
        g["hsum"][h] = hs
        g["z"][h] = np.where(v > 0, hs / v, np.nan)
    np.savez_compressed(p, ct=ct, **{f"z{h}": g["z"][h] for h in HOURS},
                        **{f"h{h}": g["hsum"][h] for h in HOURS})
    _GRIDS[name] = g
    return g


def _grid(name):
    if name not in _GRIDS:
        if "-" in name:
            a, b = name.split("-")
            da, db = load_rates(a), load_rates(b)
            common = np.intersect1d(da["ct"], db["ct"])
            ia = np.searchsorted(da["ct"], common)
            ib = np.searchsorted(db["ct"], common)
            _make_grid(name, da["cs"][ia] - db["cs"][ib], common)
        else:
            d = load_rates(name)
            _make_grid(name, d["cs"], d["ct"])
    return _GRIDS[name]


def rz(Ts, name, h):
    """Vol-normalized h-hour rates (or curve a-b) return at decision Ts.

    Uses only grid entries with close_time <= T (searchsorted 'right'-1):
    the z value at that entry is built from a trailing window only."""
    g = _grid(name)
    e = np.searchsorted(g["ct"], Ts, side="right") - 1
    out = np.full(len(Ts), np.nan)
    ok = e >= 0
    out[ok] = g["z"][h][e[ok]]
    return out


def rsum(Ts, name, h):
    """Raw h-hour log-return (single instrument) at decision Ts."""
    d = load_rates(name)
    e = np.searchsorted(d["ct"], Ts, side="right") - 1
    s = np.searchsorted(d["ct"], Ts - h * 3600 * NS, side="left")
    out = np.full(len(Ts), np.nan)
    ok = (e >= 0) & (e >= s)
    lo = np.where(s[ok] > 0, d["cs"][s[ok] - 1], 0.0)
    out[ok] = d["cs"][e[ok]] - lo
    return out


def curve_z(Ts, sym_a="ZN", sym_b="ZT", h=24):
    """Balanced curve-change z: z(a,h) - z(b,h). Each leg is divided by its
    own trailing vol first, so front-end and long-end contribute equally
    (a raw price-point diff is dominated by the long leg)."""
    return rz(Ts, sym_a, h) - rz(Ts, sym_b, h)


# ------------------------------------------------------------- macro events

def events():
    """Event table with ns release times and causal surprise z-scores."""
    df = pd.read_csv(EVENTS)
    df["release_ns"] = pd.to_datetime(df["release_timestamp_utc"],
                                      format="ISO8601", utc=True
                                      ).view("int64")
    df["surprise_raw"] = np.nan
    nfp = df["family"] == "NFP"
    cpi = df["family"] == "CPI"
    df.loc[nfp, "surprise_raw"] = (df.loc[nfp, "actual_initial_payems_thousands"]
                                   - df.loc[nfp, "previous_published_payems_thousands"])
    df.loc[cpi, "surprise_raw"] = (df.loc[cpi, "actual_initial_cpiaucsl_index"]
                                   - df.loc[cpi, "previous_published_cpiaucsl_index"])
    df["surprise_z"] = np.nan
    for fam in ("NFP", "CPI"):
        m = df["family"] == fam
        idx = df.index[m]
        s = df.loc[idx, "surprise_raw"].to_numpy(float)
        z = np.full(len(s), np.nan)
        for i in range(len(s)):
            past = s[:i]
            past = past[~np.isnan(past)]
            if len(past) >= 8 and np.std(past) > 0:
                z[i] = s[i] / np.std(past)
        df.loc[idx, "surprise_z"] = z
    return df[df["release_ns"] < T1_NS].reset_index(drop=True)


# ------------------------------------------------- rates causality gating
# The FX-side T1/T2/T3 gate lives in swing_lib.causality_gate. Here we prove
# the same three identities for the RATES layer:
#   T1r: every rates grid entry any feature reads closes <= decision T;
#   T2r: truncating the grids at T reproduces the identical side;
#   T3r: mutating all post-T rates values cannot change the side at T.

_SAVE = None


def _cap_grids(T, mutate=False):
    """Swap every grid for a truncated (optionally post-T-mutated) view."""
    global _SAVE
    _SAVE = {}
    for name, g in _GRIDS.items():
        e = int(np.searchsorted(g["ct"], T, side="right"))
        _SAVE[name] = g
        z = {}
        for h, a in g["z"].items():
            if mutate and len(a) > e:
                a = a.copy()
                a[e:] = a[e:] * 1.10 + 1.0
            z[h] = a[:e] if not mutate else a
        hs = {h: a[:e] for h, a in g["hsum"].items()}
        _GRIDS[name] = {"ct": g["ct"][:e], "z": z, "hsum": hs}
    # rz() only reads g["z"], so mutation of z beyond e is sufficient


def _restore_grids():
    global _GRIDS, _SAVE
    if _SAVE:
        _GRIDS = dict(_SAVE)
        _SAVE = None


def rates_gate(family, signal_fn, params, pairs=SW.DISCOVERY_PAIRS,
               year=2011, n_samples=24, seed=20260916):
    """Full causality proof for a rates+FX signal: swing_lib FX T1/T2/T3
    plus rates-layer T1r/T2r/T3r on the same sampled decisions."""
    rng_master = np.random.default_rng(seed + 7)
    ok_all = True
    trace = []
    t1 = t2 = t3 = True
    for sym in pairs:
        bars = SW.build_discovery_bars(sym)
        side = signal_fn(bars, sym, params)
        tf = signal_fn.signal_tf
        ct = bars[f"{tf}_close_time"]
        fire = np.flatnonzero(side != 0)
        picks = list(rng_master.permutation(fire)[:n_samples])
        if len(fire) < n_samples:
            print(f"  GATE {family}/{sym}: only {len(fire)} fires")
        for j in picks:
            T = int(ct[j])
            used_max = 0
            for name in list(_GRIDS):
                g = _grid(name)
                e = int(np.searchsorted(g["ct"], T, side="right")) - 1
                if e >= 0:
                    used_max = max(used_max, int(g["ct"][e]))
            if used_max > T:
                t1 = False
                print(f"  T1r FAIL {family}/{sym} j={j}: {used_max} > {T}")
            _cap_grids(T)
            side_t = signal_fn(bars, sym, params)
            _restore_grids()
            if int(side_t[j]) != int(side[j]):
                t2 = False
                print(f"  T2r FAIL {family}/{sym} j={j}")
            _cap_grids(T, mutate=True)
            side_m = signal_fn(bars, sym, params)
            _restore_grids()
            if int(side_m[j]) != int(side[j]):
                t3 = False
                print(f"  T3r FAIL {family}/{sym} j={j}")
            trace.append({"sym": sym, "j": int(j), "decision_ts": T,
                          "max_rates_input": used_max, "side": int(side[j])})
        print(f"RATES GATE {family}/{sym}: T1r={'P' if t1 else 'F'} "
              f"T2r={'P' if t2 else 'F'} T3r={'P' if t3 else 'F'} "
              f"({len(picks)} traces)")
    fx_ok, fx_trace = SW.causality_gate(family, signal_fn, params,
                                        pairs=pairs, year=year,
                                        n_samples=n_samples)
    trace += fx_trace
    SW.save_trace(family, trace)
    ok = ok_all and t1 and t2 and t3 and fx_ok
    print(f"GATE {family}: {'PASS' if ok else 'CAUSALITY_FAIL'}")
    return ok, trace
