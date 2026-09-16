#!/usr/bin/env python3
"""LST_OPR_CANONICAL_V2 — faithful Masterclass automation (frozen).

Differences from V1 (per LST_OPR_CANONICAL_V2_FROZEN_SPEC.md):
  * NO OPR-width gate; NO 6-bar timeout; NO 0.30-ATR stop minimum;
    NO BE@1R; NO EMA8; NO OPR_BACK invalidation.
  * A: stop = retest-bar extreme; TARGET = entry + 2R exactly;
       cancel = completed bar touching OPR_HIGH + 1.0*ATR_H1 before fill.
  * B: stop = false-break structure extreme (tracks the whole structure incl.
       the retest bar); TARGET = opposite OPR boundary; RR >= 2.0 gate;
       cancel = +1R from the latest reintegration close before fill;
       a close back through the boundary re-forms the cycle (no invented cancel).
  * C: first valid entry wins; tie -> A.
Causality: decisions on completed bars only; entries fill at the NEXT M5 open;
stop before target on same-bar conflicts (pessimistic); force-flat 15:55 ET.
Costs (unit-audited): NORMAL 1.5 / STRESS 3.0 INDEX POINTS RT ($30/$60).
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "nq_opr_modern_m1"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "nq_modern_strategy_lab"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "nq_lst_opr_engineered_v1"))
import lab_lib as L  # noqa: E402
import nq_lib as N  # noqa: E402

from lst_lib import build_h1  # frozen, tested H1 construction (utility only)

ET = N.ET
COSTS = {"LOW": 0.75, "NORMAL": 1.5, "STRESS": 3.0}   # index points RT
POINT_USD = 20.0
TICK = 0.25


@dataclass
class DayCtx:
    side: int
    atr: float
    oh: float
    ol: float


class V2Ctx:
    def __init__(self, x: L.Ctx):
        self.x = x
        h1 = build_h1(x.df)
        self.h1_starts = h1.index.asi8
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
            oh = ol = np.nan
            if side != 0 and atr == atr:
                sp = x.sess_pos[g[:3]]
                if len(sp) == 3 and list(x.hm[sp]) == [930, 935, 940]:
                    oh, ol = float(x.h[sp].max()), float(x.l[sp].min())
            self.days[gi] = DayCtx(side, atr, oh, ol)


@dataclass
class Pos:
    kind: str
    side: int
    entry: float
    stop: float
    target: float
    r: float
    entry_i: int = -1


@dataclass
class Machine:
    kind: str
    side: int
    phase: str = "IDLE"
    ext: float = np.nan
    ref: float = np.nan
    stop_level: float = np.nan
    retest_close: float = np.nan
    retest_ext: float = np.nan
    dead: bool = False
    dead_reason: str = ""
    armed: bool = False


def run_v2(x: L.Ctx, vc: V2Ctx, variant: str, cost: float):
    xx = x
    trades = []
    stats = {"ELIGIBLE_DIRECTIONAL_DAYS": 0, "SETUPS_A": 0, "SETUPS_B": 0,
             "CANCELLED_ATR": 0, "CANCELLED_1R": 0, "OBSTACLE_REJECTS": 0,
             "RR_REJECTS": 0}
    for gi, g in enumerate(xx.groups):
        d = vc.days[gi]
        if d.side == 0 or d.atr != d.atr or d.oh != d.oh:
            continue
        stats["ELIGIBLE_DIRECTIONAL_DAYS"] += 1
        oh, ol, atr = d.oh, d.ol, d.atr
        want = ["A", "B"] if variant == "C" else [variant]
        mach = {k: Machine(k, d.side) for k in want}
        pos = None
        done = False
        for k in range(3, len(g)):
            i = xx.sess_pos[g[k]]
            o, h_, l_, c_ = xx.o[i], xx.h[i], xx.l[i], xx.c[i]
            # 1) fill armed entries at this bar's open
            if pos is None and not done:
                for kk in want:
                    m = mach[kk]
                    if not m.armed:
                        continue
                    m.armed = False
                    fill = float(o)
                    if m.kind == "A":
                        stop = m.retest_ext
                        if (m.side == 1 and fill <= stop) or \
                           (m.side == -1 and fill >= stop):
                            trades.append(_rec(x, gi, m, fill, fill, i, "GAP_STOP", cost, stop))
                            done = True
                            break
                        r = abs(fill - stop)
                        target = fill + 2 * r if m.side == 1 else fill - 2 * r
                        pos = Pos("A", m.side, fill, stop, target, r, entry_i=i)
                    else:
                        stop = m.stop_level
                        r = abs(fill - stop)
                        target = oh if m.side == 1 else ol
                        if (m.side == 1 and fill >= target) or \
                           (m.side == -1 and fill <= target):
                            trades.append(_rec(x, gi, m, fill, fill, i, "GAP_TARGET", cost, stop))
                            done = True
                            break
                        pos = Pos("B", m.side, fill, stop, target, r, entry_i=i)
                    for kk2 in want:
                        if kk2 != kk:
                            mach[kk2].dead = True
                    break
            if done:
                break
            # 2) manage open position (stop -> target -> EOD)
            if pos is not None:
                exit_info = _manage(xx, pos, i, k == len(g) - 1)
                if exit_info is not None:
                    px, reason = exit_info
                    trades.append(_rec_pos(x, gi, pos, px, i, reason, cost))
                    done = True
                continue
            if done:
                break
            # 3) setup detection on this completed bar
            if xx.hm[i] >= 1130:
                continue
            for kk in want:
                m = mach[kk]
                if m.dead or m.armed:
                    continue
                _step(xx, m, i, oh, ol, atr, gi, stats)
                if m.armed and variant == "C":
                    for kk2 in want:
                        if kk2 != kk:
                            mach[kk2].dead = True
        if pos is not None and not done:
            i = xx.sess_pos[g[-1]]
            trades.append(_rec_pos(x, gi, pos, xx.c[i], i, "EOD", cost))
    return trades, stats


def _step(xx, m: Machine, i, oh, ol, atr, gi, stats):
    side = m.side
    if xx.hm[i] >= 1130:
        return
    if m.kind == "A":
        if m.phase == "IDLE":
            if (side == 1 and xx.c[i] > oh) or (side == -1 and xx.c[i] < ol):
                stats["SETUPS_A"] += 1
                # runaway checked on the breakout bar itself (price already
                # travelled 1 ATR by confirmation -> cancel)
                if (side == 1 and xx.h[i] >= oh + atr) or \
                   (side == -1 and xx.l[i] <= ol - atr):
                    m.dead = True
                    stats["CANCELLED_ATR"] += 1
                    return
                m.phase = "RETEST"
            return
        if m.phase == "RETEST":
            # runaway cancel BEFORE retest validity on the same bar
            if (side == 1 and xx.h[i] >= oh + atr) or \
               (side == -1 and xx.l[i] <= ol - atr):
                m.dead = True
                stats["CANCELLED_ATR"] += 1
                return
            if side == 1:
                if xx.l[i] <= oh and xx.c[i] >= oh:
                    m.retest_ext, m.retest_close = xx.l[i], xx.c[i]
                    if _a_obstacle_ok(xx, gi, side, m.retest_close, m.retest_ext):
                        m.armed = True
                    else:
                        m.dead = True
                        stats["OBSTACLE_REJECTS"] += 1
                    return
            else:
                if xx.h[i] >= ol and xx.c[i] <= ol:
                    m.retest_ext, m.retest_close = xx.h[i], xx.c[i]
                    if _a_obstacle_ok(xx, gi, side, m.retest_close, m.retest_ext):
                        m.armed = True
                    else:
                        m.dead = True
                        stats["OBSTACLE_REJECTS"] += 1
                    return
        return
    # ---- B ----
    if m.phase == "IDLE":
        if (side == 1 and xx.l[i] < ol) or (side == -1 and xx.h[i] > oh):
            m.phase = "REINT"
            m.ext = xx.l[i] if side == 1 else xx.h[i]
        return
    if m.phase == "REINT":
        if side == 1:
            m.ext = min(m.ext, xx.l[i])
            if xx.c[i] > ol:
                stats["SETUPS_B"] += 1
                m.ref = xx.c[i]
                m.stop_level = m.ext
                r_proj = abs(m.ref - m.stop_level)
                if xx.h[i] >= m.ref + r_proj:      # +1R on the reintegration bar
                    m.dead = True
                    stats["CANCELLED_1R"] += 1
                    return
                m.phase = "PULL"
        else:
            m.ext = max(m.ext, xx.h[i])
            if xx.c[i] < oh:
                stats["SETUPS_B"] += 1
                m.ref = xx.c[i]
                m.stop_level = m.ext
                r_proj = abs(m.stop_level - m.ref)
                if xx.l[i] <= m.ref - r_proj:
                    m.dead = True
                    stats["CANCELLED_1R"] += 1
                    return
                m.phase = "PULL"
        return
    if m.phase == "PULL":
        # structure extreme keeps tracking (incl. this bar)
        m.ext = min(m.ext, xx.l[i]) if side == 1 else max(m.ext, xx.h[i])
        r_proj = abs(m.ref - m.stop_level)
        # +1R runaway before pullback entry
        if (side == 1 and xx.h[i] >= m.ref + r_proj) or \
           (side == -1 and xx.l[i] <= m.ref - r_proj):
            m.dead = True
            stats["CANCELLED_1R"] += 1
            return
        # a close back through the boundary re-forms the cycle (no cancel)
        if (side == 1 and xx.c[i] < ol) or (side == -1 and xx.c[i] > oh):
            m.phase = "REINT"
            return
        if side == 1:
            if xx.l[i] <= ol and xx.c[i] >= ol:
                rr_r = max(abs(xx.c[i] - m.ext), 1e-9)
                rr = abs(oh - xx.c[i]) / rr_r
                if rr < 2.0:
                    m.dead = True
                    stats["RR_REJECTS"] += 1
                    return
                m.retest_close = xx.c[i]
                m.stop_level = m.ext
                m.armed = True
                return
        else:
            if xx.h[i] >= oh and xx.c[i] <= oh:
                rr_r = max(abs(m.ext - xx.c[i]), 1e-9)
                rr = abs(xx.c[i] - ol) / rr_r
                if rr < 2.0:
                    m.dead = True
                    stats["RR_REJECTS"] += 1
                    return
                m.retest_close = xx.c[i]
                m.stop_level = m.ext
                m.armed = True
                return


def _a_obstacle_ok(xx, gi, side, proj_entry, retest_ext):
    r_proj = abs(proj_entry - retest_ext)
    if side == 1:
        obs = [lv for lv in (xx.pdh[gi], xx.onh[gi]) if lv == lv and lv > proj_entry]
        return (not obs) or (min(obs) - proj_entry >= r_proj)
    obs = [lv for lv in (xx.pdl[gi], xx.onl[gi]) if lv == lv and lv < proj_entry]
    return (not obs) or (proj_entry - max(obs) >= r_proj)


def _manage(xx, p: Pos, i, is_last):
    o, h_, l_, c_ = xx.o[i], xx.h[i], xx.l[i], xx.c[i]
    side = p.side
    if side == 1 and l_ <= p.stop:
        return (min(o, p.stop), "STOP")
    if side == -1 and h_ >= p.stop:
        return (max(o, p.stop), "STOP")
    if side == 1 and h_ >= p.target:
        return (max(o, p.target), "2R_TARGET" if p.kind == "A" else "OPPOSITE_OPR_TARGET")
    if side == -1 and l_ <= p.target:
        return (min(o, p.target), "2R_TARGET" if p.kind == "A" else "OPPOSITE_OPR_TARGET")
    if is_last:
        return (c_, "EOD")
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


def _rec_pos(x, gi, p: Pos, px, i, reason, cost):
    gross = p.side * (px - p.entry)
    return {"day": x.day_of[gi], "kind": p.kind, "side": p.side,
            "entry_ts": x.df.index[p.entry_i], "exit_ts": x.df.index[i],
            "fill": p.entry, "exit_px": px, "level": p.stop, "target": p.target,
            "gross": gross, "net": gross - cost, "exit_reason": reason,
            "R0": p.r, "R_MULT": (gross - cost) / p.r if p.r else np.nan,
            "HOLD_MIN": float((x.df.index[i] - x.df.index[p.entry_i]) /
                              np.timedelta64(1, "m"))}
