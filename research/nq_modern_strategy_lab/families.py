#!/usr/bin/env python3
"""NQ MODERN STRATEGY LAB — 15 families / 27 preregistered experiments.

All cells are defined BEFORE any PnL (mechanism -> entry -> exit). Entries:
decision at bar close, fill at NEXT bar open. Exits: mechanism-matched
(trend = trailing; reversion = equilibrium target + time stop), EOD always.
No pyramiding/averaging; one base position; one trade/day.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "nq_opr_modern_m1"))
import lab_lib as L  # noqa: E402
import nq_lib as N  # noqa: E402


def build_extras(x: L.Ctx):
    """Additional causal per-day series computed once (before any experiment)."""
    nd = len(x.groups)
    x.atr_k = {k: x.atr14[x.day_of[k]] for k in range(nd)}
    pdr = np.array([x.d_range[k] for k in range(nd)])
    m20 = pd.Series(pdr).rolling(20).mean().shift(1).to_numpy()
    x.pdr20 = {k: (m20[k] if m20[k] == m20[k] else np.nan) for k in range(nd)}
    lv = N.premarket_levels(x.df)
    x.pm_range = {}
    for k in range(nd):
        v = lv.get(x.day_of[k])
        x.pm_range[k] = (v[0] - v[1]) if v else np.nan
    return x


# ---------------------------------------------------------------------------
# entry-hook helpers (stateful per day via dict keyed by gi)
# ---------------------------------------------------------------------------
def once(state, gi, key):
    if key not in state:
        state[key] = True
        return True
    return False


def bar_of(hm_val):
    def f(x, gi, g, k):
        return k if x.hm[x.sess_pos[g[k]]] == hm_val else None
    return f


# ---------------------------------------------------------------------------
# EXPERIMENTS — each returns entry_fn(x, gi, g, k) -> Sig|None
# ---------------------------------------------------------------------------
def A01(state):
    """A01 OPENING DRIVE 0.5 ATR — mechanism: opening auction repricing +
    institutional flow persistence; a >=0.5 ATR first-15m impulse continues."""
    def fn(x, gi, g, k):
        i = x.sess_pos[g[k]]
        if x.hm[i] != 940:
            return None
        atr = x.atr_k[gi]
        if atr != atr:
            return None
        sp = x.sess_pos[g[:k + 1]]
        net = x.c[i] - x.o[sp[0]]
        if abs(net) < 0.5 * atr:
            return None
        side = 1 if net > 0 else -1
        stop = x.l[sp].min() if side == 1 else x.h[sp].max()
        return L.Sig(side, stop, "hard", np.nan, "chand", 1.0, 0, "A01")
    return fn


def A02(state):
    """A02 OPENING DRIVE 1.0 ATR — strong-impulse cell of the same mechanism."""
    def fn(x, gi, g, k):
        i = x.sess_pos[g[k]]
        if x.hm[i] != 940:
            return None
        atr = x.atr_k[gi]
        if atr != atr:
            return None
        sp = x.sess_pos[g[:k + 1]]
        net = x.c[i] - x.o[sp[0]]
        if abs(net) < 1.0 * atr:
            return None
        side = 1 if net > 0 else -1
        stop = x.l[sp].min() if side == 1 else x.h[sp].max()
        return L.Sig(side, stop, "hard", np.nan, "chand", 1.0, 0, "A02")
    return fn


def _or_break(state, tag, orh_key, orl_key, min_hm):
    """first 5m CLOSE beyond the opening range -> continuation, EMA8 trail."""
    def fn(x, gi, g, k):
        i = x.sess_pos[g[k]]
        hm = x.hm[i]
        if hm < min_hm:
            return None
        orh, orl = getattr(x, orh_key)[gi], getattr(x, orl_key)[gi]
        if orh != orh:
            return None
        key = f"{tag}{gi}"
        if key in state:
            return None
        atr = x.atr_k[gi]
        if atr != atr:
            return None
        if x.c[i] > orh:
            state[key] = (1, x.l[i], hm)
        elif x.c[i] < orl:
            state[key] = (-1, x.h[i], hm)
        else:
            return None
        if state[key][2] > 1130:   # no late-day breakout 'continuation' noise
            return None
        side, stop, _ = state[key]
        return L.Sig(side, stop, "hard", np.nan, "ema8", 0, 0, tag)
    return fn


def B01(state):
    """B01 OR15 BREAKOUT — mechanism: initial-balance liquidity break expands."""
    return _or_break(state, "B01", "or15h", "or15l", 945)


def B02(state):
    """B02 OR30 BREAKOUT — slower initial balance, same mechanism."""
    return _or_break(state, "B02", "or30h", "or30l", 1000)


def B03(state):
    """B03 OR15 FAILED BREAKOUT -> reversal — mechanism: stop-run beyond the
    initial balance fails; trapped breakout traders unwind."""
    def fn(x, gi, g, k):
        i = x.sess_pos[g[k]]
        hm = x.hm[i]
        if hm < 945 or hm > 1200:
            return None
        orh, orl = x.or15h[gi], x.or15l[gi]
        if orh != orh:
            return None
        key = f"B03{gi}"
        st = state.get(key)
        if st is None:
            if x.c[i] > orh:
                state[key] = {"side": 1}
            elif x.c[i] < orl:
                state[key] = {"side": -1}
            return None
        s = st["side"]
        # failure = close back inside the OR
        inside = (x.c[i] < orh) if s == 1 else (x.c[i] > orl)
        if not inside:
            st["ext"] = max(st.get("ext", x.h[i]), x.h[i]) if s == 1 else \
                        min(st.get("ext", x.l[i]), x.l[i])
            return None
        ext = st.get("ext", x.h[i] if s == 1 else x.l[i])
        stop = ext if s == 1 else ext
        target = orl if s == 1 else orh
        return L.Sig(-s, stop, "hard", target, "none", 0, 12, "B03")
    return fn


def C01(state):
    """C01 OVERNIGHT HIGH/LOW BREAK — mechanism: overnight positioning
    confirmed by RTH break; continuation with the inventory flow."""
    return _or_break(state, "C01", "onh", "onl", 930)


def C02(state):
    """C02 ON-LEVEL SWEEP REJECTION — mechanism: liquidity sweep above/below
    the overnight extreme trapped traders; price reverts to VWAP."""
    def fn(x, gi, g, k):
        i = x.sess_pos[g[k]]
        hm = x.hm[i]
        if hm < 935 or hm > 1200:
            return None
        onh, onl = x.onh[gi], x.onl[gi]
        if onh != onh:
            return None
        key = f"C02{gi}"
        if key in state:
            return None
        if x.h[i] > onh and x.c[i] < onh:
            state[key] = True
            return L.Sig(-1, x.h[i], "hard", x.vwap[i], "none", 0, 12, "C02")
        if x.l[i] < onl and x.c[i] > onl:
            state[key] = True
            return L.Sig(1, x.l[i], "hard", x.vwap[i], "none", 0, 12, "C02")
        return None
    return fn


def D01(state):
    """D01 PDH/PDL BREAK — mechanism: prior-day reference levels are where
    passive orders rest; a decisive break continues into trend."""
    return _or_break(state, "D01", "pdh", "pdl", 930)


def D02(state):
    """D02 PD-LEVEL REJECT — break of PDH/PDL then close back inside the
    prior range -> fade back toward VWAP."""
    def fn(x, gi, g, k):
        i = x.sess_pos[g[k]]
        hm = x.hm[i]
        if hm < 930 or hm > 1330:
            return None
        pdh, pdl = x.pdh[gi], x.pdl[gi]
        if pdh != pdh:
            return None
        key = f"D02{gi}"
        st = state.get(key)
        if st is None:
            if x.c[i] > pdh:
                state[key] = {"side": 1, "ext": x.h[i]}
            elif x.c[i] < pdl:
                state[key] = {"side": -1, "ext": x.l[i]}
            return None
        s = st["side"]
        if s == 1:
            st["ext"] = max(st["ext"], x.h[i])
            if x.c[i] < pdh:
                return L.Sig(-1, st["ext"], "hard", x.vwap[i], "none", 0, 12, "D02")
        else:
            st["ext"] = min(st["ext"], x.l[i])
            if x.c[i] > pdl:
                return L.Sig(1, st["ext"], "hard", x.vwap[i], "none", 0, 12, "D02")
        return None
    return fn


def E01(state):
    """E01 GAP CONTINUATION — mechanism: overnight news repricing persists;
    gaps >= 0.25 ATR continue with the open drive."""
    def fn(x, gi, g, k):
        i = x.sess_pos[g[k]]
        if x.hm[i] != 935:
            return None
        atr, pdc = x.atr_k[gi], x.pd_close[gi]
        if atr != atr or pdc != pdc:
            return None
        gap = x.d_op[gi] - pdc
        if abs(gap) < 0.25 * atr:
            return None
        sp = x.sess_pos[g[:k + 1]]
        side = 1 if gap > 0 else -1
        stop = x.l[sp].min() if side == 1 else x.h[sp].max()
        return L.Sig(side, stop, "hard", np.nan, "chand", 1.0, 0, "E01")
    return fn


def E02(state):
    """E02 GAP FILL FADE — larger gaps (>= 0.5 ATR) overextend the overnight
    repricing; first-15m stall then revert to the prior close."""
    def fn(x, gi, g, k):
        i = x.sess_pos[g[k]]
        if x.hm[i] != 945:
            return None
        atr, pdc = x.atr_k[gi], x.pd_close[gi]
        if atr != atr or pdc != pdc:
            return None
        gap = x.d_op[gi] - pdc
        if abs(gap) < 0.5 * atr:
            return None
        sp = x.sess_pos[g[:k + 1]]
        side = -1 if gap > 0 else 1
        stop = x.h[sp].max() if side == 1 else x.l[sp].min()
        # fade only if the first 15m failed to extend the gap by >= 0.1 ATR
        ext = (x.h[sp].max() - x.d_op[gi]) if gap > 0 else (x.d_op[gi] - x.l[sp].min())
        if ext >= 0.5 * atr:
            return None
        return L.Sig(side, stop, "hard", pdc, "none", 0, 18, "E02")
    return fn


def F_cell(zthr, fade, tag):
    def fn(x, gi, g, k):
        i = x.sess_pos[g[k]]
        if x.hm[i] != 935:
            return None
        z = x.on_z[gi]
        if z != z or abs(z) < zthr:
            return None
        sp = x.sess_pos[g[:k + 1]]
        base = 1 if z > 0 else -1
        side = -base if fade else base
        if fade:
            stop = x.h[sp].max() if base == 1 else x.l[sp].min()
            return L.Sig(side, stop, "hard", x.vwap[i], "none", 0, 12, tag)
        stop = x.l[sp].min() if side == 1 else x.h[sp].max()
        return L.Sig(side, stop, "hard", np.nan, "chand", 1.0, 0, tag)
    return fn


def F01(state):
    """F01 OVERNIGHT INVENTORY CONTINUATION — |z|>=1.5 overnight return
    continues after the open (positioning persistence)."""
    return F_cell(1.5, False, "F01")


def F02(state):
    """F02 OVERNIGHT INVENTORY FADE — extreme overnight return reverts after
    the open (trapped overnight crowd). Separate hypothesis."""
    return F_cell(1.5, True, "F02")


def G01(state):
    """G01 VWAP RECLAIM — mechanism: opening sellers exhaust; first decisive
    reclaim of the RTH VWAP pulls mean-reverting flow back up."""
    def fn(x, gi, g, k):
        i = x.sess_pos[g[k]]
        hm = x.hm[i]
        if hm < 1000 or hm > 1400:
            return None
        key = f"G01{gi}"
        st = state.setdefault(key, {"above": 0, "below": 0})
        vw = x.vwap[i]
        if vw != vw:
            return None
        if x.c[i] > vw:
            if st["below"] > 0 and once(state, gi, f"done{gi}"):
                return L.Sig(1, x.l[i], "hard", np.nan, "ema8", 0, 0, "G01")
            st["above"] += 1
        elif x.c[i] < vw:
            if st["above"] > 0 and once(state, gi, f"done{gi}"):
                return L.Sig(-1, x.h[i], "hard", np.nan, "ema8", 0, 0, "G01")
            st["below"] += 1
        return None
    return fn


def G02(state):
    """G02 VWAP FIRST PULLBACK — after a real opening drive above VWAP, the
    first touch of VWAP is a trend continuation entry (market-makers refill)."""
    def fn(x, gi, g, k):
        i = x.sess_pos[g[k]]
        hm = x.hm[i]
        if hm < 935 or hm > 1400:
            return None
        atr = x.atr_k[gi]
        vw = x.vwap[i]
        if atr != atr or vw != vw:
            return None
        key = f"G02{gi}"
        st = state.setdefault(key, {"drive": 0, "done": False})
        if st["done"]:
            return None
        if hm <= 1000:
            if x.c[i] > vw + 0.25 * atr:
                st["drive"] = 1
            return None
        if st["drive"]:
            if x.l[i] <= vw <= x.c[i]:
                st["done"] = True
                stop = x.l[x.sess_pos[g[:k + 1]]].min()
                return L.Sig(1, stop, "hard", np.nan, "ema8", 0, 0, "G02")
            if x.h[i] >= vw >= x.c[i]:
                st["done"] = True
                stop = x.h[x.sess_pos[g[:k + 1]]].max()
                return L.Sig(-1, stop, "hard", np.nan, "ema8", 0, 0, "G02")
        return None
    return fn


def H_cell(eff_thr, tag):
    """TREND DAY EARLY DETECTION — opening range expansion + directional
    efficiency identifies trend sessions early; ride with a chandelier."""
    def fn(x, gi, g, k):
        i = x.sess_pos[g[k]]
        if x.hm[i] != 1000:
            return None
        atr = x.atr_k[gi]
        eff = x.eff10[gi]
        if atr != atr or eff != eff:
            return None
        sp = x.sess_pos[g[:k + 1]]
        r30 = x.h[sp].max() - x.l[sp].min()
        if abs(eff) < eff_thr or r30 < 0.5 * atr:
            return None
        side = 1 if eff > 0 else -1
        stop = x.l[sp].min() if side == 1 else x.h[sp].max()
        return L.Sig(side, stop, "hard", np.nan, "chand", 1.0, 0, tag)
    return fn


def H01(state):
    """H01 TREND-DAY EARLY eff>=0.4."""
    return H_cell(0.4, "H01")


def H02(state):
    """H02 TREND-DAY EARLY eff>=0.6 (strong cell)."""
    return H_cell(0.6, "H02")


def I_cell(state, mode, tag):
    """VOLATILITY COMPRESSION -> EXPANSION: tight structure then a decisive
    OR15 break follows the actual breakout (entry AFTER expansion starts)."""
    def fn(x, gi, g, k):
        i = x.sess_pos[g[k]]
        hm = x.hm[i]
        if hm < 945 or hm > 1130:
            return None
        atr = x.atr_k[gi]
        if atr != atr:
            return None
        if mode == "pd":
            comp = x.pdr20[gi] == x.pdr20[gi] and x.pd_range[gi] <= 0.7 * x.pdr20[gi]
        else:
            comp = x.on_range[gi] == x.on_range[gi] and x.on_range[gi] <= 0.6 * atr
        if not comp:
            return None
        orh, orl = x.or15h[gi], x.or15l[gi]
        if orh != orh:
            return None
        key = f"{tag}{gi}"
        if key in state:
            return None
        if x.c[i] > orh:
            return L.Sig(1, x.l[i], "hard", np.nan, "ema8", 0, 0, tag)
        if x.c[i] < orl:
            return L.Sig(-1, x.h[i], "hard", np.nan, "ema8", 0, 0, tag)
        return None
    return fn


def I01(state):
    """I01 PRIOR-DAY-RANGE COMPRESSION -> OR15 expansion."""
    return I_cell(state, "pd", "I01")


def I02(state):
    """I02 OVERNIGHT-RANGE COMPRESSION -> OR15 expansion."""
    return I_cell(state, "on", "I02")


def J_cell(fade, tag):
    """VOLATILITY SHOCK: first 5m bar 1.5x its 20d average range. Continuation
    vs exhaustion are separate preregistered hypotheses."""
    def fn(x, gi, g, k):
        i = x.sess_pos[g[k]]
        if x.hm[i] != 935:
            return None
        avg = x.f5_avg[gi]
        f5 = x.f5[gi]
        if avg != avg or f5 < 1.5 * avg:
            return None
        sp = x.sess_pos[g[:k + 1]]
        net = x.c[i] - x.o[sp[0]]
        if abs(net) < 1.0 * avg:
            return None
        base = 1 if net > 0 else -1
        if fade:
            side = -base
            stop = x.h[sp].max() if base == 1 else x.l[sp].min()
            return L.Sig(side, stop, "hard", x.vwap[i], "none", 0, 12, tag)
        side = base
        stop = x.l[sp].min() if side == 1 else x.h[sp].max()
        return L.Sig(side, stop, "hard", np.nan, "chand", 1.0, 0, tag)
    return fn


def J01(state):
    """J01 SHOCK CONTINUATION."""
    return J_cell(False, "J01")


def J02(state):
    """J02 SHOCK EXHAUSTION FADE."""
    return J_cell(True, "J02")


def K_cell(state, level_kind, tag):
    """FAILED AUCTION: wick beyond a reference level with a close back inside;
    fade to the causal midpoint. Distinct levels: prior-day vs opening range."""
    def fn(x, gi, g, k):
        i = x.sess_pos[g[k]]
        hm = x.hm[i]
        if hm < 930 or hm > 1100:
            return None
        if level_kind == "pd":
            hi, lo = x.pdh[gi], x.pdl[gi]
            mid = (hi + lo) / 2.0
        else:
            hi, lo = x.or15h[gi], x.or15l[gi]
            mid = (hi + lo) / 2.0
        if hi != hi:
            return None
        key = f"{tag}{gi}"
        if key in state:
            return None
        if x.h[i] > hi and x.c[i] < hi:
            state[key] = True
            return L.Sig(-1, x.h[i], "hard", mid, "none", 0, 18, tag)
        if x.l[i] < lo and x.c[i] > lo:
            state[key] = True
            return L.Sig(1, x.l[i], "hard", mid, "none", 0, 18, tag)
        return None
    return fn


def K01(state):
    """K01 PD-LEVEL FAILED AUCTION."""
    return K_cell(state, "pd", "K01")


def K02(state):
    """K02 OPENING-RANGE FAILED AUCTION (after 09:45)."""
    return K_cell(state, "or", "K02")


def L01(state):
    """L01 FIRST PULLBACK — after a causal opening impulse (>=0.5 ATR, efficient),
    first touch of EMA20(5m) resumes the trend."""
    def fn(x, gi, g, k):
        i = x.sess_pos[g[k]]
        hm = x.hm[i]
        if hm < 935 or hm > 1130:
            return None
        atr = x.atr_k[gi]
        if atr != atr:
            return None
        key = f"L01{gi}"
        st = state.setdefault(key, {"side": 0})
        sp = x.sess_pos[g[:k + 1]]
        if st["side"] == 0:
            net = x.c[i] - x.o[sp[0]]
            rng = x.h[sp].max() - x.l[sp].min()
            if abs(net) >= 0.5 * atr and rng > 0 and abs(net) / rng >= 0.5:
                st["side"] = 1 if net > 0 else -1
            return None
        s = st["side"]
        e20 = x.ema20[i]
        if s == 1 and x.l[i] <= e20:
            st["side"] = 2
            stop = x.l[sp].min()
            return L.Sig(1, stop, "hard", np.nan, "ema8", 0, 0, "L01")
        if s == -1 and x.h[i] >= e20:
            st["side"] = 2
            stop = x.h[sp].max()
            return L.Sig(-1, stop, "hard", np.nan, "ema8", 0, 0, "L01")
        return None
    return fn


def M01(state):
    """M01 LUNCH BREAKOUT — lunch compression resolves; post-13:30 expansion
    follows the break direction into the close."""
    def fn(x, gi, g, k):
        i = x.sess_pos[g[k]]
        hm = x.hm[i]
        if hm < 1335:
            return None
        lh, ll = x.lunh[gi], x.lunl[gi]
        if lh != lh:
            return None
        key = f"M01{gi}"
        if key in state:
            return None
        if x.c[i] > lh:
            state[key] = True
            return L.Sig(1, ll, "hard", np.nan, "chand", 0.7, 0, "M01")
        if x.c[i] < ll:
            state[key] = True
            return L.Sig(-1, lh, "hard", np.nan, "chand", 0.7, 0, "M01")
        return None
    return fn


def N01(state):
    """N01 POWER HOUR — first late-day (>=15:00) 5m close making a new running
    day extreme: closing-relevant flow continues into the close."""
    def fn(x, gi, g, k):
        i = x.sess_pos[g[k]]
        hm = x.hm[i]
        if hm < 1500:
            return None
        key = f"N01{gi}"
        if key in state:
            return None
        rh, rl = x.run_hi[i], x.run_lo[i]
        if rh != rh:
            return None
        sp = x.sess_pos[g[max(0, k - 5):k + 1]]
        if x.c[i] > rh:
            state[key] = True
            return L.Sig(1, x.l[sp].min(), "hard", np.nan, "none", 0, 0, "N01")
        if x.c[i] < rl:
            state[key] = True
            return L.Sig(-1, x.h[sp].max(), "hard", np.nan, "none", 0, 0, "N01")
        return None
    return fn


def O01(state):
    """O01 OVERNIGHT->RTH TRANSFER — overnight drift with a NARROW premarket
    (no reversal structure) transfers into the RTH session."""
    def fn(x, gi, g, k):
        i = x.sess_pos[g[k]]
        if x.hm[i] != 935:
            return None
        z, onr = x.on_z[gi], x.on_range[gi]
        pmr = x.pm_range[gi]
        if z != z or onr != onr or pmr != pmr:
            return None
        if abs(z) < 1.0 or pmr > 0.5 * onr:
            return None
        sp = x.sess_pos[g[:k + 1]]
        side = 1 if z > 0 else -1
        stop = x.l[sp].min() if side == 1 else x.h[sp].max()
        return L.Sig(side, stop, "hard", np.nan, "chand", 1.0, 0, "O01")
    return fn


EXPERIMENTS = [
    ("A01", "A_OPENING_DRIVE", "opening auction repricing + flow persistence",
     "first-15m impulse >=0.5 ATR at 09:40 close", "hard stop @ first-15m extreme + chandelier 1.0 ATR + EOD", A01),
    ("A02", "A_OPENING_DRIVE", "same, strong impulse cell",
     "first-15m impulse >=1.0 ATR", "same as A01", A02),
    ("B01", "B_ORB", "initial-balance break expansion",
     "first 5m close beyond OR15 (<=11:30)", "hard stop @ breakout bar extreme + EMA8 + EOD", B01),
    ("B02", "B_ORB", "same, 30m initial balance",
     "first 5m close beyond OR30 (<=11:30)", "same as B01 with OR30", B02),
    ("B03", "B_ORB", "failed breakout unwind (trapped traders)",
     "close back inside OR15 after a break", "hard stop beyond post-break extreme + target opposite OR side + time 12", B03),
    ("C01", "C_OVERNIGHT_LEVELS", "overnight positioning confirmed at RTH",
     "first 5m close beyond ONH/ONL", "hard stop @ bar extreme + EMA8 + EOD", C01),
    ("C02", "C_OVERNIGHT_LEVELS", "sweep of ON extreme trapped traders",
     "wick beyond ONH/ONL, close back inside (<=12:00)", "hard stop @ sweep extreme + target VWAP + time 12", C02),
    ("D01", "C_PRIOR_DAY", "prior-day level break continues",
     "first 5m close beyond PDH/PDL", "hard stop @ bar extreme + EMA8 + EOD", D01),
    ("D02", "C_PRIOR_DAY", "prior-day level reject fades",
     "break then close back inside prior range", "hard stop beyond post-break extreme + target VWAP + time 12", D02),
    ("E01", "E_GAP", "overnight repricing persists",
     "|gap|>=0.25 ATR at 09:35, with the gap", "hard stop @ first-10m extreme + chandelier 1.0 + EOD", E01),
    ("E02", "E_GAP", "large gap overextends; revert to prior close",
     "|gap|>=0.5 ATR, first 15m fails to extend", "hard stop beyond 15m extreme + target prior close + time 18", E02),
    ("F01", "F_ON_INVENTORY", "extreme overnight return continues",
     "overnight z>=1.5 at 09:35, with the z sign", "hard stop @ first-10m extreme + chandelier 1.0 + EOD", F01),
    ("F02", "F_ON_INVENTORY", "extreme overnight crowd trapped; reverts",
     "overnight z>=1.5, against the z sign", "hard stop beyond 10m extreme + target VWAP + time 12", F02),
    ("G01", "G_VWAP", "opening flow exhaustion -> VWAP reclaim",
     "first opposite-side close vs VWAP after a drift (10:00-14:00)", "hard stop @ bar extreme + EMA8 + EOD", G01),
    ("G02", "G_VWAP", "trend refill at VWAP after opening drive",
     "drive >=VWAP+0.25ATR then first VWAP touch", "hard stop @ day extreme so far + EMA8 + EOD", G02),
    ("H01", "H_TREND_DAY", "early trend-state identification",
     "10:00: |efficiency|>=0.4 and range30>=0.5 ATR", "hard stop @ first-30m extreme + chandelier 1.0 + EOD", H01),
    ("H02", "H_TREND_DAY", "same, strong cell",
     "10:00: |efficiency|>=0.6 and range30>=0.5 ATR", "same as H01", H02),
    ("I01", "I_COMPRESSION", "prior-day compression coiled; break expands",
     "pd_range<=0.7x20d avg then first close beyond OR15", "hard stop @ bar extreme + EMA8 + EOD", I01),
    ("I02", "I_COMPRESSION", "overnight coil -> expansion",
     "on_range<=0.6 ATR then first close beyond OR15", "same as I01", I02),
    ("J01", "J_VOL_SHOCK", "opening shock continues",
     "first 5m range>=1.5x20d avg and net>=1x avg", "hard stop @ shock extreme + chandelier 1.0 + EOD", J01),
    ("J02", "J_VOL_SHOCK", "opening shock exhausts",
     "same trigger, opposite side", "hard stop beyond shock extreme + target VWAP + time 12", J02),
    ("K01", "K_FAILED_AUCTION", "prior-day level failed auction",
     "wick beyond PDH/PDL + close back inside (<=11:00)", "hard stop @ sweep extreme + target PD midpoint + time 18", K01),
    ("K02", "K_FAILED_AUCTION", "opening-range failed auction",
     "wick beyond OR15 + close back inside", "hard stop @ sweep extreme + target OR midpoint + time 18", K02),
    ("L01", "L_FIRST_PULLBACK", "trend refill after impulse at EMA20",
     "impulse>=0.5 ATR & eff>=0.5 then first EMA20 touch", "hard stop @ impulse extreme + EMA8 + EOD", L01),
    ("M01", "M_LUNCH", "lunch compression resolves into afternoon trend",
     "first 5m close beyond lunch range after 13:30", "hard stop @ opposite lunch side + chandelier 0.7 + EOD", M01),
    ("N01", "N_POWER_HOUR", "closing flow continues into the close",
     "first >=15:00 close at new running day extreme", "hard stop @ last-30m opposite extreme + EOD only", N01),
    ("O01", "O_ON_TRANSFER", "overnight drift transfers when premarket is narrow",
     "ON z>=1.0 and pm_range<=0.5x ON range at 09:35", "hard stop @ premarket/10m extreme + chandelier 1.0 + EOD", O01),
]
