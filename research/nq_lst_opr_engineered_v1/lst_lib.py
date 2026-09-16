#!/usr/bin/env python3
"""LST_OPR_ENGINEERED_V1 — frozen engine (H1 flow / M15 OPR / M5 execution).

Per-day two-phase walk (causal):
  phase 1: setup detection on COMPLETED M5 bars in [09:45, 11:30) ET; a valid
           retest arms a market entry AT THE NEXT M5 OPEN (after A obstacle /
           B RR gates evaluated on the retest-bar close, per spec R2);
  phase 2: from the fill bar on: hard stops (touch; worse open on gap), A:
           close-back-inside-OPR invalidation, BE hard stop armed by a
           completed close >= +1R (active next bar), EMA8-M5 trail armed by a
           completed close >= +2R; B: limit target at the opposite boundary
           (better open honored); both: force-flat at the last 15:55 ET bar.
One attempt per strategy per day; C = first valid entry wins (A precedence).
Costs (unit-audited): NORMAL 1.5 / STRESS 3.0 INDEX POINTS RT (USD 30/60).
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "nq_opr_modern_m1"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "nq_modern_strategy_lab"))
import lab_lib as L  # noqa: E402
import nq_lib as N  # noqa: E402

ET = N.ET
COSTS = {"LOW": 0.75, "NORMAL": 1.5, "STRESS": 3.0}   # index points RT
POINT_USD = 20.0
TICK = 0.25


def build_h1(df5: pd.DataFrame) -> pd.DataFrame:
    """1h bars (bucket START labels) from 5m; completed-data aggregates."""
    b = df5.index.floor("1h")
    h1 = df5.assign(b=b).groupby("b").agg(
        open=("open", "first"), high=("high", "max"),
        low=("low", "min"), close=("close", "last")).reset_index()
    h1 = h1.rename(columns={"b": "ts"})
    h1["ema20"] = h1["close"].ewm(span=20, adjust=False).mean()
    h1["ema50"] = h1["close"].ewm(span=50, adjust=False).mean()
    tr = pd.concat([h1["high"] - h1["low"],
                    (h1["high"] - h1["close"].shift()).abs(),
                    (h1["low"] - h1["close"].shift()).abs()], axis=1).max(axis=1)
    h1["atr14"] = tr.rolling(14).mean()
    return h1.set_index("ts")


@dataclass
class DayCtx:
    side: int          # 1 bull, -1 bear, 0 neutral
    atr: float
    oh: float          # OPR high
    ol: float          # OPR low


class LstCtx:
    """Frozen per-day context (flow, ATR, OPR) known at the 09:30 open."""

    def __init__(self, x: L.Ctx):
        self.x = x
        h1 = build_h1(x.df)
        self.h1_starts = h1.index.asi8
        self.h1 = h1
        self.days = {}
        ns_h = 3600 * 10 ** 9
        for gi, g in enumerate(x.groups):
            first = x.sess_pos[g[0]]
            day_open = int(x.df.index[first].value)
            t_start = (day_open // ns_h - 1) * ns_h
            pos = self.h1_starts.searchsorted(t_start)
            side, atr = 0, np.nan
            if pos < len(self.h1_starts) and self.h1_starts[pos] == t_start and pos >= 14:
                row = h1.iloc[pos]
                em50_5 = h1["ema50"].iloc[pos - 5]
                em50, em20, a = row["ema50"], row["ema20"], row["atr14"]
                if all(v == v for v in (em50, em20, em50_5, a)):
                    if row["close"] > em50 and em20 > em50 and em50 > em50_5:
                        side = 1
                    elif row["close"] < em50 and em20 < em50 and em50 < em50_5:
                        side = -1
                    atr = float(a)
            if side == 0 or atr != atr:
                self.days[gi] = DayCtx(0 if side == 0 else side, atr if atr == atr else np.nan, np.nan, np.nan)
                continue
            sp = x.sess_pos[g[:3]]
            if len(sp) == 3 and list(x.hm[sp]) == [930, 935, 940]:
                oh, ol = float(x.h[sp].max()), float(x.l[sp].min())
            else:
                oh = ol = np.nan
            self.days[gi] = DayCtx(side, atr, oh, ol)


@dataclass
class Pos:
    kind: str
    side: int
    entry: float
    stop: float
    target: float       # np.nan for A
    r: float
    be_armed: bool = False
    ema_armed: bool = False
    entry_i: int = -1       # global bar index of the fill bar


@dataclass
class Machine:
    """Per-day setup state machine for one strategy."""
    kind: str
    side: int
    phase: str = "IDLE"
    bars: int = 0
    ext: float = np.nan
    ref: float = np.nan
    stop_level: float = np.nan
    retest_close: float = np.nan
    retest_ext: float = np.nan
    dead: bool = False
    armed: bool = False      # a fill is armed for the next bar
    sig: dict = field(default_factory=dict)


def run_lst(x: L.Ctx, lc: LstCtx, variant: str, cost: float):
    trades = []
    stats = {"DAYS_FLOW_BULL": 0, "DAYS_FLOW_BEAR": 0, "DAYS_FLOW_NEUTRAL": 0,
             "RANGE_FILTER_REJECTS": 0, "TOTAL_ELIGIBLE_DAYS": 0}
    for gi, g in enumerate(x.groups):
        d = lc.days[gi]
        if d.side == 0 or d.atr != d.atr:
            stats["DAYS_FLOW_NEUTRAL"] += 1
            continue
        stats["DAYS_FLOW_BULL" if d.side == 1 else "DAYS_FLOW_BEAR"] += 1
        oh, ol, atr = d.oh, d.ol, d.atr
        if oh != oh:
            stats["DAYS_FLOW_NEUTRAL"] += 1
            continue
        if not (0.25 * atr <= (oh - ol) <= 1.00 * atr):
            stats["RANGE_FILTER_REJECTS"] += 1
            continue
        stats["TOTAL_ELIGIBLE_DAYS"] += 1
        want = ["A", "B"] if variant == "C" else [variant]
        mach = {k: Machine(k, d.side) for k in want}
        pos = None
        done = False
        for k in range(3, len(g)):
            i = x.sess_pos[g[k]]
            o, h_, l_, c_ = x.o[i], x.h[i], x.l[i], x.c[i]
            # 1) fill any armed entry at this bar's open
            if pos is None and not done:
                for kk in want:
                    m = mach[kk]
                    if m.armed:
                        m.armed = False
                        fill = float(o)
                        if m.kind == "A":
                            stop = m.retest_ext
                            if (m.side == 1 and fill <= stop) or \
                               (m.side == -1 and fill >= stop):
                                trades.append(_rec(x, gi, m, fill, fill, i, "GAP_STOP", cost, stop))
                                done = True
                                break
                            if fill - stop < 0 and m.side == -1:
                                stop = m.retest_ext
                            dist = (fill - stop) if m.side == 1 else (stop - fill)
                            if dist < 0.30 * atr:
                                stop = fill - 0.30 * atr if m.side == 1 else fill + 0.30 * atr
                            pos = Pos("A", m.side, fill, stop, np.nan, abs(fill - stop), entry_i=i)
                        else:
                            stop = m.stop_level
                            dist = (fill - stop) if m.side == 1 else (stop - fill)
                            if dist < 0.30 * atr:
                                stop = fill - 0.30 * atr if m.side == 1 else fill + 0.30 * atr
                            target = oh if m.side == 1 else ol
                            if (m.side == 1 and fill >= target) or \
                               (m.side == -1 and fill <= target):
                                trades.append(_rec(x, gi, m, fill, fill, i, "GAP_TARGET", cost, stop))
                                done = True
                                break
                            pos = Pos("B", m.side, fill, stop, target, abs(fill - stop), entry_i=i)
                        for kk2 in want:
                            if kk2 != kk:
                                mach[kk2].dead = True
                        break
            if done:
                break
            # 2) manage an open position on this bar
            if pos is not None:
                exit_info = _manage(x, gi, pos, i, oh, ol, k == len(g) - 1)
                if exit_info is not None:
                    px, reason = exit_info
                    trades.append(_rec_from_pos(x, gi, pos, px, i, reason, cost))
                    done = True
                elif k == len(g) - 1:
                    trades.append(_rec_from_pos(x, gi, pos, c_, i, "EOD", cost))
                    done = True
                continue
            if done:
                break
            # 3) setup detection on this completed bar (decision window)
            if x.hm[i] >= 1130:
                continue
            for kk in want:
                m = mach[kk]
                if m.dead or m.armed:
                    continue
                _step(x, m, i, oh, ol, atr, gi)
                if m.armed and variant == "C":
                    for kk2 in want:
                        if kk2 != kk:
                            mach[kk2].dead = True
        # end of day: any surviving position force-flattens at the last bar
        if pos is not None and not done:
            i = x.sess_pos[g[-1]]
            trades.append(_rec_from_pos(x, gi, pos, x.c[i], i, "EOD", cost))
    return trades, stats


def _step(x: L.Ctx, m: Machine, i, oh, ol, atr, gi):
    side = m.side
    hm = x.hm[i]
    if hm >= 1130:
        return
    if m.kind == "A":
        if m.phase == "IDLE":
            if (side == 1 and x.c[i] > oh) or (side == -1 and x.c[i] < ol):
                m.phase = "RETEST"
                m.bars = 0
            return
        if m.phase == "RETEST":
            m.bars += 1
            if side == 1:
                if x.h[i] >= oh + atr:
                    m.dead = True
                    return
                if x.l[i] <= oh and x.c[i] >= oh:
                    m.retest_ext, m.retest_close = x.l[i], x.c[i]
                    if _a_obstacle_ok(x, gi, side, m.retest_close, m.retest_ext, atr):
                        m.armed = True
                    else:
                        m.dead = True
                    return
            else:
                if x.l[i] <= ol - atr:
                    m.dead = True
                    return
                if x.h[i] >= ol and x.c[i] <= ol:
                    m.retest_ext, m.retest_close = x.h[i], x.c[i]
                    if _a_obstacle_ok(x, gi, side, m.retest_close, m.retest_ext, atr):
                        m.armed = True
                    else:
                        m.dead = True
                    return
            if m.bars >= 6:
                m.dead = True
        return
    # ---- B ----
    if m.phase == "IDLE":
        if (side == 1 and x.l[i] < ol) or (side == -1 and x.h[i] > oh):
            m.phase = "REINT"
            m.ext = x.l[i] if side == 1 else x.h[i]
        return
    if m.phase == "REINT":
        if side == 1:
            m.ext = min(m.ext, x.l[i])
            if x.c[i] > ol:
                m.phase, m.bars, m.ref, m.stop_level = "PULL", 0, x.c[i], m.ext
        else:
            m.ext = max(m.ext, x.h[i])
            if x.c[i] < oh:
                m.phase, m.bars, m.ref, m.stop_level = "PULL", 0, x.c[i], m.ext
        return
    if m.phase == "PULL":
        m.bars += 1
        proj_r = max(abs(m.ref - m.stop_level), 0.30 * atr)
        if side == 1:
            if x.h[i] >= m.ref + proj_r or x.c[i] < ol:
                m.dead = True
                return
            if x.l[i] <= ol and x.c[i] >= ol:
                m.retest_close = x.c[i]
                r_proj = max(abs(m.retest_close - m.stop_level), 0.30 * atr)
                rr = abs(oh - m.retest_close) / r_proj
                if rr >= 2.0:
                    m.armed = True
                else:
                    m.dead = True
                return
        else:
            if x.l[i] <= m.ref - proj_r or x.c[i] > oh:
                m.dead = True
                return
            if x.h[i] >= oh and x.c[i] <= oh:
                m.retest_close = x.c[i]
                r_proj = max(abs(m.stop_level - m.retest_close), 0.30 * atr)
                rr = abs(m.retest_close - ol) / r_proj
                if rr >= 2.0:
                    m.armed = True
                else:
                    m.dead = True
                return
        if m.bars >= 6:
            m.dead = True


def _a_obstacle_ok(x: L.Ctx, gi, side, proj_entry, retest_ext, atr):
    proj_r = max(abs(proj_entry - retest_ext), 0.30 * atr)
    if side == 1:
        obs = [lv for lv in (x.pdh[gi], x.onh[gi]) if lv == lv and lv > proj_entry]
        return (not obs) or (min(obs) - proj_entry >= proj_r)
    obs = [lv for lv in (x.pdl[gi], x.onl[gi]) if lv == lv and lv < proj_entry]
    return (not obs) or (proj_entry - max(obs) >= proj_r)


def _manage(x: L.Ctx, gi, p: Pos, i, oh, ol, is_last):
    """One bar of position management. Returns (px, reason) or None."""
    o, h_, l_, c_ = x.o[i], x.h[i], x.l[i], x.c[i]
    side = p.side
    # 1) hard stop (initial or BE once armed)
    if side == 1 and l_ <= p.stop:
        return (min(o, p.stop), "STOP")
    if side == -1 and h_ >= p.stop:
        return (max(o, p.stop), "STOP")
    if p.kind == "A":
        # 2) close back inside the OPR
        if (side == 1 and c_ < oh) or (side == -1 and c_ > ol):
            return (c_, "OPR_BACK")
        # 3) EMA8 trail once armed
        if p.ema_armed and ((side == 1 and c_ < x.ema8[i]) or
                            (side == -1 and c_ > x.ema8[i])):
            return (c_, "EMA8")
        # 4) arming on completed close (BE then EMA)
        prog = side * (c_ - p.entry)
        if not p.be_armed and prog >= p.r:
            p.be_armed = True
            p.stop = p.entry
        if not p.ema_armed and prog >= 2 * p.r:
            p.ema_armed = True
    else:
        # target limit (better open honored)
        if p.target == p.target:
            if side == 1 and h_ >= p.target:
                return (max(o, p.target), "TARGET")
            if side == -1 and l_ <= p.target:
                return (min(o, p.target), "TARGET")
    return None


def _rec(x, gi, m, fill, px, i, reason, cost, stop):
    gross = m.side * (px - fill)
    return {"day": x.day_of[gi], "kind": m.kind, "side": m.side,
            "entry_ts": x.df.index[i], "exit_ts": x.df.index[i],
            "fill": fill, "exit_px": px, "level": stop, "target": np.nan,
            "gross": gross, "net": gross - cost, "exit_reason": reason,
            "R0": abs(fill - stop) if stop == stop else np.nan,
            "R_MULT": (gross - cost) / abs(fill - stop)
            if stop == stop and abs(fill - stop) > 0 else np.nan,
            "HOLD_MIN": 0.0}


def _rec_from_pos(x, gi, p: Pos, px, i, reason, cost):
    gross = p.side * (px - p.entry)
    return {"day": x.day_of[gi], "kind": p.kind, "side": p.side,
            "entry_ts": x.df.index[p.entry_i],
            "exit_ts": x.df.index[i],
            "fill": p.entry, "exit_px": px, "level": p.stop, "target": p.target,
            "gross": gross, "net": gross - cost, "exit_reason": reason,
            "R0": p.r, "R_MULT": (gross - cost) / p.r if p.r else np.nan,
            "HOLD_MIN": float((x.df.index[i] - x.df.index[p.entry_i]) /
                              np.timedelta64(1, "m"))}
