#!/usr/bin/env python3
"""NQ MODERN STRATEGY LAB — generic causal engine for day-local mechanisms.

Causality contract (same discipline as nq_lib / p000):
  * 5m bars carry bucket-START labels; a bar is known only at label+5min.
  * Entry decisions are taken at a bar CLOSE and fill at the NEXT bar OPEN
    (market-at-signal). No same-bar decision+fill.
  * Daily context variables (PDH/PDL, ONH/ONL, ATR14, OR, gap, overnight
    stats...) only use data strictly BEFORE the 09:30 session bar (or prior
    RTH days). Structural by construction here.
  * Exits: hard stops fill at stop (worse open on gap); close-stops and trail
    exits fill at the bar close; targets are limits (better open honored);
    SAME-BAR pessimistic rule: stop checked before target; EOD flatten at the
    last session bar close; max ONE trade/day.
Costs: preregistered NQ frictions (points RT): LOW 0.75 / NORMAL 1.5 / STRESS 3.0.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "nq_opr_modern_m1"))
import nq_lib as N  # noqa: E402

ET = N.ET
NQ_COSTS = N.NQ_COSTS
# 1 NQ index point = USD 20 (tick 0.25 pt = USD 5). Unit audit 2026-09-16:
# was 5.0 (tick value) — reporting-only bug, corrected; decisions never used it.
POINT_USD = 20.0


# ---------------------------------------------------------------------------
# Context
# ---------------------------------------------------------------------------
class Ctx:
    pass


def _et64(df):
    return df.index.tz_convert(ET).asi8


def build_ctx(df: pd.DataFrame) -> Ctx:
    x = Ctx()
    x.df = df
    x.o = df["open"].to_numpy(float)
    x.h = df["high"].to_numpy(float)
    x.l = df["low"].to_numpy(float)
    x.c = df["close"].to_numpy(float)
    x.v = df["volume"].to_numpy(float)
    idx_et = df.index.tz_convert(ET)
    x.hm = (idx_et.hour * 100 + idx_et.minute).to_numpy()
    x.et64 = idx_et.asi8
    x.date = idx_et.date
    x.day_ids = N._et_day_ids(df.index)

    sess = (x.hm >= 930) & (x.hm < 1600)
    x.sess_pos = np.where(sess)[0]
    x.groups = N._consecutive_day_groups(x.day_ids[x.sess_pos])

    # per-RTH-day table
    day_of, first_i, last_i = [], [], []
    for g in x.groups:
        day_of.append(x.date[x.sess_pos[g[0]]])
        first_i.append(g[0])
        last_i.append(g[-1])
    x.day_of = np.array(day_of)
    x.first_i = np.array([x.sess_pos[g[0]] for g in x.groups])
    x.last_i = np.array([x.sess_pos[g[-1]] for g in x.groups])
    nd = len(x.groups)
    d_hi = np.array([x.h[x.sess_pos[g]].max() for g in x.groups])
    d_lo = np.array([x.l[x.sess_pos[g]].min() for g in x.groups])
    d_cl = np.array([x.c[x.sess_pos[g][-1]] for g in x.groups])
    d_op = np.array([x.o[x.sess_pos[g[0]]] for g in x.groups])
    tr = np.maximum(d_hi - d_lo,
         np.maximum(np.abs(d_hi - np.roll(d_cl, 1)),
                    np.abs(d_lo - np.roll(d_cl, 1))))
    tr[0] = d_hi[0] - d_lo[0]
    atr = pd.Series(tr).rolling(14).mean().shift(1).to_numpy()  # causal: prior days
    x.atr14 = {d: (atr[k] if atr[k] == atr[k] else np.nan)
               for k, d in enumerate(x.day_of)}
    x.pdh = {k: (d_hi[k - 1] if k else np.nan) for k in range(nd)}
    x.pdl = {k: (d_lo[k - 1] if k else np.nan) for k in range(nd)}
    x.pd_close = {k: (d_cl[k - 1] if k else np.nan) for k in range(nd)}
    x.pd_range = {k: (d_hi[k - 1] - d_lo[k - 1] if k else np.nan) for k in range(nd)}
    x.d_op = {k: d_op[k] for k in range(nd)}
    x.d_range = {k: d_hi[k] - d_lo[k] for k in range(nd)}

    # overnight window [09:30 - 15.5h, 09:30) per day; ON return vs prior close
    x.onh, x.onl, x.on_ret, x.on_range = {}, {}, {}, {}
    for k in range(nd):
        if k == 0:
            x.onh[k] = x.onl[k] = x.on_ret[k] = x.on_range[k] = np.nan
            continue
        end_ts = x.et64[x.first_i[k]]
        start_ts = end_ts - int(15.5 * 3600 * 1e9)
        a = np.searchsorted(x.et64, start_ts)
        b = np.searchsorted(x.et64, end_ts)
        if b - a < 60:
            x.onh[k] = x.onl[k] = x.on_ret[k] = x.on_range[k] = np.nan
            continue
        x.onh[k] = float(x.h[a:b].max())
        x.onl[k] = float(x.l[a:b].min())
        x.on_range[k] = x.onh[k] - x.onl[k]
        x.on_ret[k] = d_op[k] / d_cl[k - 1] - 1.0 if d_cl[k - 1] > 0 else np.nan
    onr = np.array([x.on_ret[k] for k in range(nd)], float)
    m20 = pd.Series(onr).rolling(20).mean().shift(1).to_numpy()
    s20 = pd.Series(onr).rolling(20).std().shift(1).to_numpy()
    x.on_z = {k: ((onr[k] - m20[k]) / s20[k] if s20[k] and s20[k] == s20[k] else np.nan)
              for k in range(nd)}

    # intraday windows per day
    def win_hl(g, lo_hm, hi_hm):
        sel = g[(x.hm[x.sess_pos[g]] >= lo_hm) & (x.hm[x.sess_pos[g]] < hi_hm)]
        if len(sel) == 0:
            return np.nan, np.nan
        return x.h[x.sess_pos[sel]].max(), x.l[x.sess_pos[sel]].min()
    x.or15h, x.or15l, x.or30h, x.or30l = {}, {}, {}, {}
    x.lunh, x.lunl, x.eff10 = {}, {}, {}
    for k, g in enumerate(x.groups):
        sp = x.sess_pos[g]
        hmv = x.hm[sp]
        m15 = (hmv >= 930) & (hmv < 945)
        m30 = (hmv >= 930) & (hmv < 1000)
        ml = (hmv >= 1200) & (hmv < 1330)
        x.or15h[k] = x.h[sp[m15]].max() if m15.any() else np.nan
        x.or15l[k] = x.l[sp[m15]].min() if m15.any() else np.nan
        x.or30h[k] = x.h[sp[m30]].max() if m30.any() else np.nan
        x.or30l[k] = x.l[sp[m30]].min() if m30.any() else np.nan
        x.lunh[k] = x.h[sp[ml]].max() if ml.any() else np.nan
        x.lunl[k] = x.l[sp[ml]].min() if ml.any() else np.nan
        if m30.any():
            r30 = x.h[sp[m30]].max() - x.l[sp[m30]].min()
            net30 = x.c[sp[m30][-1]] - x.o[sp[m30][0]]
            x.eff10[k] = net30 / r30 if r30 > 0 else np.nan
        else:
            x.eff10[k] = np.nan
    f5 = np.array([ (x.h[x.sess_pos[g[0]]] - x.l[x.sess_pos[g[0]]]) if len(g) else np.nan
                    for g in x.groups ])
    f5m = pd.Series(f5).rolling(20).mean().shift(1).to_numpy()
    x.f5 = {k: f5[k] for k in range(nd)}
    x.f5_avg = {k: (f5m[k] if f5m[k] == f5m[k] else np.nan) for k in range(nd)}

    # global arrays
    x.vwap = N.vwap_rth(df).to_numpy()
    x.ema8 = df["close"].ewm(span=8, adjust=False).mean().to_numpy()
    x.ema20 = df["close"].ewm(span=20, adjust=False).mean().to_numpy()
    rhi, rlo = N.running_day_extremes(df, ET)
    x.run_hi = rhi.to_numpy()
    x.run_lo = rlo.to_numpy()
    x.day_index = {d: k for k, d in enumerate(x.day_of)}
    return x


# ---------------------------------------------------------------------------
# Signals / walk
# ---------------------------------------------------------------------------
@dataclass
class Sig:
    side: int
    stop: float
    stop_kind: str = "hard"      # 'hard' touch | 'close' close-through
    target: float = np.nan       # limit level
    trail: str = "none"          # none|ema8|ema20|chand
    trail_k: float = 1.0         # chandelier ATR multiple
    time_stop: int = 0           # bars (0 = none)
    tag: str = ""



def _manage(x, s, fill, j, g, atr0, pos_in_g):
    """Causal position management from the fill bar (position pos_in_g in g)
    to day end. Priority per bar: stop -> target (pessimistic) -> trail."""
    side = s.side
    run_hi = fill
    run_lo = fill
    for kk in range(pos_in_g, len(g)):
        i = x.sess_pos[g[kk]]
        o, h, l, c = x.o[i], x.h[i], x.l[i], x.c[i]
        run_hi = max(run_hi, h)
        run_lo = min(run_lo, l)
        if s.stop_kind == "hard":
            if side == 1 and l <= s.stop:
                return (min(o, s.stop), "STOP", i)
            if side == -1 and h >= s.stop:
                return (max(o, s.stop), "STOP", i)
        else:
            if side == 1 and c < s.stop:
                return (c, "STOP", i)
            if side == -1 and c > s.stop:
                return (c, "STOP", i)
        if s.target == s.target:
            if side == 1 and h >= s.target:
                return (max(o, s.target), "TARGET", i)
            if side == -1 and l <= s.target:
                return (min(o, s.target), "TARGET", i)
        if s.trail == "chand" and atr0 == atr0:
            tr = (run_hi - s.trail_k * atr0) if side == 1 else (run_lo + s.trail_k * atr0)
            if side == 1 and c < tr:
                return (c, "TRAIL", i)
            if side == -1 and c > tr:
                return (c, "TRAIL", i)
        if s.trail == "ema8" and (side == 1 and c < x.ema8[i] or
                                  side == -1 and c > x.ema8[i]):
            return (c, "TRAIL", i)
        if s.trail == "ema20" and (side == 1 and c < x.ema20[i] or
                                   side == -1 and c > x.ema20[i]):
            return (c, "TRAIL", i)
        if s.time_stop and (kk - pos_in_g) >= s.time_stop:
            return (c, "TIME", i)
        if kk == len(g) - 1:
            return (c, "EOD", i)
    return None


def run_experiment_full(x, entry_fn, cost_rt):
    """Same as run_experiment but with correct entry_ts / n_bars bookkeeping."""
    trades = []
    for gi, g in enumerate(x.groups):
        day = x.day_of[gi]
        atr0 = x.atr14[day]
        done = False
        pending = None
        entry_dec_i = None
        for k in range(len(g)):
            i = x.sess_pos[g[k]]
            if pending is None and not done:
                s = entry_fn(x, gi, g, k)
                if s is not None and k + 1 < len(g):
                    pending = (s, x.sess_pos[g[k + 1]])
                    entry_dec_i = i
                continue
            if pending is not None:
                s, j = pending
                fill = float(x.o[j])
                pending = None
                if (s.side == 1 and fill <= s.stop) or (s.side == -1 and fill >= s.stop):
                    trades.append(_mk2(x, day, s, entry_dec_i, fill, fill, j, j,
                                       "GAP_STOP", cost_rt))
                    done = True
                    continue
                r = _manage(x, s, fill, j, g, atr0, k + 1)
                px, reason, last = (r if r else (fill, "ERR", j))
                trades.append(_mk2(x, day, s, entry_dec_i, fill, px, j, last,
                                   reason, cost_rt))
                done = True
    return trades


def _mk2(x, day, s, dec_i, fill, px, j, last_i, reason, cost_rt):
    gross = s.side * (px - fill)
    r0 = abs(fill - s.stop) if s.stop == s.stop else np.nan
    hold = (x.df.index[last_i] - x.df.index[j]) / np.timedelta64(1, "m")
    return {"day": day, "side": s.side, "variant": s.tag,
            "entry_ts": x.df.index[j], "exit_ts": x.df.index[last_i],
            "fill": fill, "exit_px": px, "level": s.stop,
            "gross": gross, "net": gross - cost_rt,
            "exit_reason": reason, "n_bars": int(reason != "ERR"),
            "R0": r0, "HOLD_MIN": float(hold)}


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------
def fold_of(ts):
    ts = pd.Timestamp(ts)
    for name, (lo, hi) in N.FOLDS.items():
        if lo <= ts < hi:
            return name
    return "?"


def metrics(tf: pd.DataFrame, weeks: float):
    if tf is None or tf.empty:
        return {"N": 0}
    net = tf["net"].to_numpy()
    pos, neg = net[net > 0].sum(), -net[net < 0].sum()
    sr = np.sort(net)[::-1]
    top = max(1, int(round(0.01 * len(net))))
    dd, _ = N.drawdown_metrics(net)
    yrs = N._to_et(tf["entry_ts"]).year
    per_day = tf.groupby(N._to_et(tf["entry_ts"]).date)["net"].sum()
    folds = tf["entry_ts"].map(fold_of)
    byfold = {f: round(float(net[np.asarray(folds) == f].mean()), 3)
              for f in sorted(set(folds))}
    out = {
        "N": int(len(net)),
        "TPW": round(len(net) / weeks, 2),
        "NET": round(float(net.mean()), 3),
        "NET_USD": round(float(net.mean()) * POINT_USD, 2),
        "PF": round(float(pos / neg), 3) if neg > 0 else None,
        "WR": round(float((net > 0).mean()), 3),
        "EXP_R": round(float((tf["net"] / tf["R0"].replace(0, np.nan)).mean()), 3),
        "AVG_WIN": round(float(net[net > 0].mean()), 2) if (net > 0).any() else None,
        "AVG_LOSS": round(float(net[net <= 0].mean()), 2) if (net <= 0).any() else None,
        "RM_BEST1": round(float(sr[top:].mean()), 3),
        "MAXDD_USD": round(dd * POINT_USD, 1),
        "WORSTDAY_USD": round(float(per_day.min()) * POINT_USD, 2),
        "BY_YEAR": {int(y): round(float(net[np.asarray(yrs) == y].mean()), 3)
                    for y in sorted(set(yrs))},
        "BY_YEAR_N": {int(y): int((np.asarray(yrs) == y).sum()) for y in sorted(set(yrs))},
        "BY_FOLD": byfold,
        "EXITS": {k: int(v) for k, v in tf["exit_reason"].value_counts().items()},
    }
    return out


def gate_check(m: dict) -> tuple[bool, list]:
    fails = []
    if m.get("N", 0) < 40:
        fails.append(f"N={m.get('N')}<40")
    if not (m.get("NET", 0) > 0):
        fails.append("net<=0")
    pf = m.get("PF")
    if pf is None or pf < 1.15:
        fails.append(f"PF={pf}")
    if not (m.get("RM_BEST1", -1) > 0):
        fails.append("rm_best<=0")
    byy = m.get("BY_YEAR", {})
    pos_years = sum(1 for v in byy.values() if v > 0)
    if pos_years < 4:
        fails.append(f"pos_years={pos_years}")
    tot = sum(byy.values())
    if tot > 0 and max(byy.values()) / tot > 0.60:
        fails.append("year_concentration>60%")
    return (len(fails) == 0, fails)
