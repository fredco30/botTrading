#!/usr/bin/env python3
"""HISTORICAL_SIGNAL_EXIT_AUDIT_M1 library.

REPRODUCIBILITY RULE (mission §2): historical campaign modules are NOT
imported (m2lib/m3lib mutate sys.path and can shadow legacy modules).
Everything needed is copied VERBATIM from the source commits into this file,
marked [VERBATIM <file>@<commit>]. Only mechanical adaptations: `L.`/`S.`
prefixes resolved to this module's identical copies, plus two audited
additions: (1) an `occupancy` flag on the replay engines (default True ==
historical one-position behavior; False == mission §7A event-level replay);
(2) MFE/MAE tracking (reported only, never used in exit logic).

Sources:
  families_m3.py @ 29dfb7b (MULTITIMEFRAME_DISCOVERY_M1) — F04b/F08 entries
  m3lib.py       @ 29dfb7b — bars_from_m1, hhmm, indicators, mtf_replay
  m2lib.py       @ 0a4eb55 — pf_of, remove_best_1pct, agg_metrics,
                             survival_veto, veto_fail
  families_sw.py @ 7e3bd46 (FX_MULTIPAIR_SWING_DISCOVERY_M1) — G10 entry,
                             scan_signal
  swing_lib.py   @ 7e3bd46 — PIP/SPREAD constants, bars_from_5m, atr,
                             bar_replay

New code (pre-registered in EXIT_PREREGISTRATION.md BEFORE any PnL):
  replay_trail_ticks  — NEW EXIT A (F08): 2xATR(H1,14) stop + 3xATR(H1,14)
                        Chandelier trail + 24h max hold
  replay_trail_bars   — NEW EXIT B (G10): 2xATR(H4,14) stop + 3xATR(H4,14)
                        Chandelier trail + D1 regime exit + 240h max hold
  (NEW EXIT C uses mtf_replay verbatim with per-decision tp_levels = frozen
   previous-day midpoint; stop 20 pips; T240 unchanged.)

Data (all previously validated, all local):
  EURUSD ticks  : research/autonomous_edge_discovery_m1/cache/ticks_YYYY.npz
  MTF bars      : research/mtf_discovery_m1/cache/mtfbars_YYYY.npz
  Swing 5m/bars : research/fx_multipair_swing_m1/cache/*.npz
Units: int64 ns UTC, float64 prices, 1 pip = 1e-4 (A/C) or per-pair dict (B).
"""
import hashlib
import json
import os

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
M1CACHE = os.path.join(REPO, "research", "autonomous_edge_discovery_m1", "cache")
M3CACHE = os.path.join(REPO, "research", "mtf_discovery_m1", "cache")
SWCACHE = os.path.join(REPO, "research", "fx_multipair_swing_m1", "cache")
OUT = HERE

NS = 10 ** 9                                   # [VERBATIM infra_lib@29dfb7b]
PIP = 1e-4
DISCOVERY_YEARS = list(range(2010, 2018))      # [VERBATIM m3lib@29dfb7b]
PIP_SW = {"EURUSD": 1e-4, "GBPUSD": 1e-4, "USDJPY": 1e-2}
SPREAD_PIPS = {"EURUSD": 0.6, "GBPUSD": 1.0}   # [VERBATIM swing_lib@7e3bd46]
SLIP_STRESS_PIPS = 0.5
DISCOVERY_PAIRS = ("EURUSD", "GBPUSD")


# ------------------------------------------------------------------ data

def load_ticks(year):
    z = np.load(os.path.join(M1CACHE, f"ticks_{year}.npz"))
    return z["ts"], z["bid"], z["ask"]


def load_mtfbars(year):
    z = np.load(os.path.join(M3CACHE, f"mtfbars_{year}.npz"))
    return {k: z[k] for k in z.files}


def load_swing(sym):
    z = np.load(os.path.join(SWCACHE, f"bars_{sym}_2010_2017.npz"))
    return {k: z[k] for k in z.files}


# ---------------------------------------------------- m3lib@29dfb7b (verbatim)

def bars_from_m1(m1, tf_min):
    tf = tf_min * 60 * NS
    ct = m1["close_time"]
    g = (ct - 1) // tf
    ug, first = np.unique(g, return_index=True)
    idx = np.searchsorted(g, ug, side="right") - 1
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


def hhmm(ct):
    return ((ct // NS // 3600) % 24).astype(np.int64) * 100 \
        + ((ct // NS % 3600) // 60)


def sma(x, n):
    return pd.Series(x).rolling(n).mean().to_numpy()


def std(x, n):
    return pd.Series(x).rolling(n).std(ddof=0).to_numpy()


def ema(x, n):
    return pd.Series(x).ewm(span=n, adjust=False).mean().to_numpy()


def atr(high, low, close, n):
    """[VERBATIM m3lib@29dfb7b] ATR in pips (PIP=1e-4)."""
    pc = np.roll(close, 1); pc[0] = close[0]
    tr = np.maximum(high - low, np.maximum(np.abs(high - pc), np.abs(low - pc)))
    return pd.Series(tr).rolling(n).mean().to_numpy() / PIP


def donhi(close, n):
    return pd.Series(close).rolling(n).max().shift(1).to_numpy()


def donlo(close, n):
    return pd.Series(close).rolling(n).min().shift(1).to_numpy()


def day_groups(ct):
    d = pd.to_datetime(ct, unit="ns", utc=True).floor("D")
    return d.to_numpy()


def mtf_replay(ts, bid, ask, decisions, sl_pips, tp_pips, t_exit_min,
               latency_ns=5 * NS, slip_pips=0.0, wait_ns=30 * NS,
               tp_levels=None, sl_levels=None, occupancy=True):
    """[VERBATIM m3lib@29dfb7b mtf_replay] + MFE/MAE tracking (reported
    only) + `occupancy` flag (default True == historical)."""
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
        if occupancy and d < last_exit_ts:
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
                m = m0 + i_t                       # (named for MFE window)
                exit_ts = int(ts[m0 + i_t])
                exit_px = float(tgt) - slip if side == 1 else float(tgt) + slip
                reason = "TARGET"
            else:
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
        px = (bid if side == 1 else ask)
        seg_px = px[m0:min(m, nts - 1) + 1]
        best = float(seg_px.max()) if len(seg_px) else entry
        worst = float(seg_px.min()) if len(seg_px) else entry
        if side == 1:
            mfe = (best - entry) / PIP
            mae = (worst - entry) / PIP
        else:
            mfe = (entry - worst) / PIP
            mae = (entry - best) / PIP
        net = side * (exit_px - entry) / PIP
        risk_pips = (abs(entry - float(sl_levels[j])) / PIP
                     if sl_levels is not None else sl_pips)
        trades.append({"j": int(j), "side": side, "decision_ts": d,
                       "entry_idx": int(k), "entry_ts": int(ts[k]),
                       "entry": entry, "exit_ts": exit_ts, "exit_px": exit_px,
                       "reason": reason, "net_pips": float(net),
                       "r": float(net / risk_pips),
                       "risk_pips": float(risk_pips),
                       "mfe": float(mfe), "mae": float(mae)})
        last_exit_ts = exit_ts
    return trades, no_fill


# --------------------------------------------- families_m3@29dfb7b

def f04_prev_day(mode="break"):
    """[VERBATIM families_m3@29dfb7b f04_prev_day] + frozen-midpoint capture
    for the audit (NEW EXIT C target): mid[i] = (PDH+PDL)/2 of the previous
    UTC day at every firing bar, captured inside the SAME loop with the SAME
    conditions — no entry-logic change. Returns (side, mid)."""
    def sig(bars, year):
        c = bars["M15_close"]; h = bars["M15_high"]; l = bars["M15_low"]
        ct = bars["M15_close_time"]
        t = hhmm(ct)
        days = day_groups(ct)
        ud = np.unique(days)
        n = len(c)
        side = np.zeros(n, dtype=np.int8)
        mid = np.full(n, np.nan)
        for di in range(1, len(ud)):
            prev = days == ud[di - 1]
            cur = days == ud[di]
            if prev.sum() < 10:
                continue
            pdh, pdl = h[prev].max(), l[prev].min()
            m = (pdh + pdl) / 2.0
            ids = np.flatnonzero(cur & (t >= 700) & (t <= 1700))
            cc = c[ids]
            if mode == "break":
                up = np.flatnonzero(cc > pdh)
                dn = np.flatnonzero(cc < pdl)
                if len(up):
                    side[ids[up[0]]] = 1
                if len(dn):
                    side[ids[dn[0]]] = -1
            else:  # fade: first close above PDH then a close back below it
                fired_up = fired_dn = False
                above = False
                below = False
                for k, i in enumerate(ids):
                    if not fired_up:
                        if not above and cc[k] > pdh:
                            above = True
                        elif above and cc[k] < pdh:
                            side[i] = -1
                            mid[i] = m
                            fired_up = True
                    if not fired_dn:
                        if not below and cc[k] < pdl:
                            below = True
                        elif below and cc[k] > pdl:
                            side[i] = 1
                            mid[i] = m
                            fired_dn = True
                    if fired_up and fired_dn:
                        break
        side[:40] = 0
        mid[:40] = np.nan
        return side, mid
    sig.signal_tf = "M15"
    sig.desc = f"Prev-day H/L {mode} (M15 trigger 07-17h)"
    return sig


def f08_asia_transfer(mode="continuation", min_move=10.0):
    """[VERBATIM families_m3@29dfb7b]."""
    def sig(bars, year):
        c = bars["M15_close"]
        ct = bars["M15_close_time"]
        t = hhmm(ct)
        days = day_groups(ct)
        ud = np.unique(days)
        side = np.zeros(len(c), dtype=np.int8)
        for di in range(1, len(ud)):
            cur = days == ud[di]
            ids = np.flatnonzero(cur)
            b0 = ids[(t[ids] == 0)][0] if (t[ids] == 0).any() else None
            aend = ids[(t[ids] == 645)]
            if b0 is None or not len(aend):
                continue
            aret = (c[aend[0]] - c[b0]) / PIP
            tok = ids[(t[ids] == 700)]
            if not len(tok) or abs(aret) < min_move:
                continue
            sgn = 1 if aret > 0 else -1
            side[tok[0]] = sgn if mode == "continuation" else -sgn
        side[:40] = 0
        return side
    sig.signal_tf = "M15"
    sig.desc = f"London 07:00 {mode} of Asia move (|move|>={min_move}p)"
    return sig


# --------------------------------------------- families_sw@7e3bd46

def sig_tf(tf):
    def deco(fn):
        fn.signal_tf = tf
        return fn
    return deco


@sig_tf("H4")
def g10_state_machine(bars, sym, p):
    """[VERBATIM families_sw@7e3bd46 g10_state_machine]."""
    dc = bars["D1_close"]; dct = bars["D1_close_time"]
    h4c = bars["H4_close"]; h4ct = bars["H4_close_time"]
    ema_f, ema_s = ema(dc, p["fast"]), ema(dc, p["slow"])
    idx = np.searchsorted(dct, h4ct, side="right") - 1
    bull = (ema_f > ema_s)[idx]
    hi, lo = donhi(h4c, p["break_n"]), donlo(h4c, p["break_n"])
    side = np.zeros(len(h4c), dtype=np.int8)
    side[bull & (h4c > hi)] = 1
    side[~bull & (h4c < lo)] = -1
    return side


def g10_bull_d1(bars, p):
    """D1 trend state (same EMA pair as the entry, on completed D1 bars) for
    the NEW EXIT B regime test."""
    dc = bars["D1_close"]
    return ema(dc, p["fast"]) > ema(dc, p["slow"])


def scan_signal(sym, signal_fn, params, horizons):
    """[VERBATIM families_sw@7e3bd46 scan_signal] — identity check only."""
    bars = load_swing(sym)
    side = signal_fn(bars, sym, params)
    tf = signal_fn.signal_tf
    b = {k: bars[f"{tf}_{k}"] for k in ("open", "high", "low", "close")}
    opn, close, n = b["open"], b["close"], len(b["close"])
    pip = PIP_SW[sym]
    out = {}
    for h in horizons:
        rets = []
        last = -10 ** 9
        for i in np.flatnonzero(side != 0):
            if i <= last or i + 1 >= n:
                continue
            j = min(i + h, n - 1)
            rets.append(side[i] * (close[j] - opn[i + 1]) / pip)
            last = j
        out[h] = np.asarray(rets)
    return out, int((side != 0).sum())


# --------------------------------------------- swing_lib@7e3bd46

def bars_from_5m(d5, tf_min):
    tf = tf_min * 60 * NS
    ct = d5["ts"] + 5 * 60 * NS
    g = (ct - 1) // tf
    ug = np.unique(g)
    fid = np.searchsorted(g, ug, side="left")
    idx = np.searchsorted(g, ug, side="right") - 1
    lo = np.minimum.reduceat(d5["low"], fid)
    hi = np.maximum.reduceat(d5["high"], fid)
    return {
        "start": (ug * tf).astype(np.int64),
        "close_time": ((ug + 1) * tf).astype(np.int64),
        "open": d5["open"][fid],
        "high": hi, "low": lo,
        "close": d5["close"][idx],
    }


def atr_sw(sym, high, low, close, n):
    """[VERBATIM swing_lib@7e3bd46 atr] ATR in instrument pips."""
    pip = PIP_SW[sym]
    pc = np.roll(close, 1); pc[0] = close[0]
    tr = np.maximum(high - low, np.maximum(np.abs(high - pc), np.abs(low - pc)))
    return pd.Series(tr).rolling(n).mean().to_numpy() / pip


def bar_replay(sym, sig_ct, decisions, stop_dist, tp_dist, hold_hours,
               stress=False, occupancy=True):
    """[VERBATIM swing_lib@7e3bd46 bar_replay] + MFE/MAE tracking (reported
    only) + `occupancy` flag (default True == historical per-pair replay)."""
    bars = load_swing(sym)
    ts5 = bars["5m_ts"]; o5 = bars["5m_open"]; h5 = bars["5m_high"]
    l5 = bars["5m_low"]; c5 = bars["5m_close"]
    pip = PIP_SW[sym]
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
        if occupancy and d < last_exit_ts:
            continue
        k = int(np.searchsorted(ts5, d, side="left"))
        if k >= n5 - 1:
            break
        sd = float(stop_dist[j]) * pip
        td = float(tp_dist[j]) * pip
        if side == 1:
            entry = float(o5[k]) + spread + slip
            stop = entry - sd
            tgt = entry + td
        else:
            entry = float(o5[k]) - slip
            stop_bid = entry + sd - spread
            stop = entry + sd
            tgt_bid = entry - td - spread
            tgt = entry - td
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
                    exit_px = min(stop, float(os_[i_s])) - slip
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
        hi_m = m0 if m_end < m0 else m
        if hi_m >= m0:
            best = float(h5[m0:hi_m + 1].max())
            worst = float(l5[m0:hi_m + 1].min())
        else:
            best = worst = entry
        if side == 1:
            mfe = (best - entry) / pip
            mae = (worst - entry) / pip
        else:
            mfe = (entry - worst) / pip
            mae = (entry - best) / pip
        net = side * (exit_px - entry) / pip
        risk = sd / pip
        trades.append({"j": int(j), "sym": sym, "side": side,
                       "decision_ts": d, "entry_ts": int(ts5[k]),
                       "entry": entry, "exit_ts": int(exit_ts),
                       "exit_px": float(exit_px), "reason": reason,
                       "net_pips": float(net), "r": float(net / risk),
                       "risk_pips": float(risk),
                       "mfe": float(mfe), "mae": float(mae)})
        last_exit_ts = int(exit_ts)
    return trades


# ------------------------------------------------ NEW EXIT A (F08, §8)

def atr0_at(ct_arr, atr_arr, t):
    """Frozen ATR (pips) from the last COMPLETED bar with close_time <= t."""
    k = int(np.searchsorted(ct_arr, t, side="right")) - 1
    if k < 0:
        return np.nan
    return float(atr_arr[k])


def replay_trail_ticks(ts, bid, ask, decisions, h1_ct, h1_high, h1_low,
                       h1_atr, sl_mult=2.0, trail_mult=3.0, max_hold_min=1440,
                       latency_ns=5 * NS, slip_pips=0.0, wait_ns=30 * NS,
                       occupancy=True):
    """NEW EXIT A (pre-registered): initial stop 2xATR(H1,14) frozen at
    decision; Chandelier trail 3xATR(H1,14) updated at COMPLETED H1 closes
    only (anchor = H1 extreme since entry), tighten-only, effective for
    ticks with ts >= update close time; no target; max hold from entry tick;
    time exit = first tick strictly after t_end (mtf_replay idiom).
    decisions['atr0'] = ATR(H1,14) pips as of each decision timestamp."""
    n = len(decisions["ts"])
    trades = []
    no_fill = 0
    last_exit_ts = -1
    slip = slip_pips * PIP
    nts = len(ts)
    sr_end = None
    for j in range(n):
        side = int(decisions["side"][j])
        if side == 0:
            continue
        d = int(decisions["ts"][j])
        if occupancy and d < last_exit_ts:
            continue
        atr0 = float(decisions["atr0"][j])
        if not np.isfinite(atr0) or atr0 <= 0:
            no_fill += 1
            continue
        i0 = int(np.searchsorted(ts, d + latency_ns, side="left"))
        i1 = int(np.searchsorted(ts, d + latency_ns + wait_ns, side="left"))
        if i0 >= i1:
            no_fill += 1
            continue
        k = i0
        entry = float(ask[k] if side == 1 else bid[k]) + (slip if side == 1 else -slip)
        stop = entry - side * sl_mult * atr0 * PIP
        trailed = False
        t_end = int(ts[k]) + max_hold_min * 60 * NS
        e_end = int(np.searchsorted(ts, t_end, side="right"))  # first tick > t_end
        u0 = int(np.searchsorted(h1_ct, int(ts[k]), side="right"))
        u1 = int(np.searchsorted(h1_ct, t_end, side="right"))
        px = bid if side == 1 else ask
        exit_ts = exit_px = reason = None
        m_best = entry
        m_worst = entry
        cur = k + 1
        for ui in range(u0, u1 + 1):
            t_upd = int(h1_ct[ui]) if ui < u1 else t_end + 1
            hi_m = int(np.searchsorted(ts, t_upd, side="left"))  # first tick >= t_upd
            e = min(hi_m, e_end)                       # exclusive scan bound
            if cur < e:
                seg = px[cur:e]
                m_best = max(m_best, float(seg.max()))
                m_worst = min(m_worst, float(seg.min()))
                hit = np.flatnonzero(seg <= stop) if side == 1 \
                    else np.flatnonzero(seg >= stop)
                if len(hit):
                    m = cur + int(hit[0])
                    seg2 = px[cur:m + 1]
                    m_best = max(m_best, float(seg2.max()))
                    m_worst = min(m_worst, float(seg2.min()))
                    exit_ts = int(ts[m])
                    exit_px = float(px[m]) - slip if side == 1 else float(px[m]) + slip
                    reason = "TRAIL" if trailed else "STOP_INIT"
                    break
                cur = e
            else:
                cur = max(cur, e)
            if cur >= e_end:
                break
            if ui < u1:                                # completed-H1 update
                a = float(h1_atr[ui])
                if np.isfinite(a) and a > 0:
                    if side == 1:
                        anchor = float(h1_high[u0:ui + 1].max())
                        cand = anchor - trail_mult * a * PIP
                        if cand > stop:
                            stop = cand
                            trailed = True
                    else:
                        anchor = float(h1_low[u0:ui + 1].min())
                        cand = anchor + trail_mult * a * PIP
                        if cand < stop:
                            stop = cand
                            trailed = True
        if exit_ts is None:
            m = e_end if e_end < nts else nts - 1
            exit_ts = int(ts[m])
            exit_px = float(px[m]) + (-slip if side == 1 else slip)
            reason = "TIME"
        net = side * (exit_px - entry) / PIP
        if side == 1:
            mfe = (m_best - entry) / PIP
            mae = (m_worst - entry) / PIP
        else:
            mfe = (entry - m_worst) / PIP
            mae = (entry - m_best) / PIP
        trades.append({"j": int(j), "side": side, "decision_ts": d,
                       "entry_ts": int(ts[k]), "entry": entry,
                       "exit_ts": exit_ts, "exit_px": exit_px,
                       "reason": reason, "net_pips": float(net),
                       "r": float(net / (sl_mult * atr0)),
                       "risk_pips": float(sl_mult * atr0),
                       "mfe": float(mfe), "mae": float(mae),
                       "trailed": bool(trailed)})
        last_exit_ts = exit_ts
    return trades, no_fill


# ------------------------------------------------ NEW EXIT B (G10, §9)

def replay_trail_bars(sym, bars, decisions, bull_d1, d1_ct,
                      sl_mult=2.0, trail_mult=3.0, max_hold_hours=240,
                      stress=False, occupancy=True):
    """NEW EXIT B (pre-registered): initial stop 2xATR(H4,14) at decision;
    no TP; Chandelier trail 3xATR(H4,14) updated at COMPLETED H4 closes
    (anchor = H4 extreme since entry), tighten-only, effective for 5m bars
    whose open ts >= the H4 close time; REGIME exit at the first 5m open at/
    after a completed D1 close whose trend state no longer supports the
    trade; max hold 240h (time exit = 5m close granularity, bar_replay
    idiom). Fill conventions identical to swing_lib.bar_replay."""
    ts5 = bars["5m_ts"]; o5 = bars["5m_open"]; h5 = bars["5m_high"]
    l5 = bars["5m_low"]; c5 = bars["5m_close"]
    h4ct = bars["H4_close_time"]; h4h = bars["H4_high"]; h4l = bars["H4_low"]
    h4c = bars["H4_close"]
    atr_h4 = atr_sw(sym, h4h, h4l, h4c, 14)
    pip = PIP_SW[sym]
    spread = SPREAD_PIPS[sym] * pip
    slip = (SLIP_STRESS_PIPS * pip) if stress else 0.0
    n5 = len(ts5)
    trades = []
    last_exit_ts = -1
    for j in range(len(decisions["ts"])):
        side = int(decisions["side"][j])
        if side == 0:
            continue
        d = int(decisions["ts"][j])
        if occupancy and d < last_exit_ts:
            continue
        atr0 = float(decisions["atr0"][j])
        if not np.isfinite(atr0) or atr0 <= 0:
            continue
        k = int(np.searchsorted(ts5, d, side="left"))
        if k >= n5 - 1:
            break
        sd = sl_mult * atr0 * pip
        if side == 1:
            entry = float(o5[k]) + spread + slip
            stop_trig = entry - sd                   # bid stop level/trigger
        else:
            entry = float(o5[k]) - slip
            stop_trig = entry + sd - spread          # bid trigger of ask-stop
        trailed = False
        t_end = int(ts5[k]) + int(max_hold_hours * 3600 * NS)
        m_end = int(np.searchsorted(ts5, t_end, side="right")) - 1
        u0 = int(np.searchsorted(h4ct, int(ts5[k]), side="right"))
        u1 = int(np.searchsorted(h4ct, t_end, side="right"))
        di0 = int(np.searchsorted(d1_ct, int(ts5[k]), side="right"))
        flips = []
        for di in range(di0, len(d1_ct)):
            if int(d1_ct[di]) > t_end:
                break
            b = bool(bull_d1[di])
            if (side == 1 and not b) or (side == -1 and b):
                flips.append(int(d1_ct[di]))
        fi = 0
        exit_ts = exit_px = reason = None
        best = entry
        worst = entry
        anchor_hi = -np.inf
        anchor_lo = np.inf
        for cur in range(k + 1, m_end + 1):
            t_open = int(ts5[cur])
            # REGIME exit at this bar's open (checked before intrabar stop)
            if fi < len(flips) and flips[fi] <= t_open:
                if side == 1:
                    exit_px = float(o5[cur]) - slip
                else:
                    exit_px = float(o5[cur]) + spread + slip
                exit_ts = t_open
                reason = "REGIME"
                break
            # completed-H4 trail updates effective at this bar's open
            # (trail bookkeeping entirely in BID space: long trigger = bid
            # chandelier level; short trigger = bid low + 3ATR, ask fill =
            # trigger + spread)
            while u0 < u1 and int(h4ct[u0]) <= t_open:
                a = float(atr_h4[u0])
                if np.isfinite(a) and a > 0:
                    if side == 1:
                        anchor_hi = max(anchor_hi, float(h4h[u0]))
                        cand = anchor_hi - trail_mult * a * pip
                        if cand > stop_trig:
                            stop_trig = cand
                            trailed = True
                    else:
                        anchor_lo = min(anchor_lo, float(h4l[u0]))
                        cand = anchor_lo + trail_mult * a * pip
                        if cand < stop_trig:
                            stop_trig = cand
                            trailed = True
                u0 += 1
            if (l5[cur] <= stop_trig) if side == 1 else (h5[cur] >= stop_trig):
                if side == 1:
                    exit_px = min(stop_trig, float(o5[cur])) - slip
                else:
                    exit_px = max(stop_trig, float(o5[cur])) + spread + slip
                exit_ts = t_open
                reason = "TRAIL" if trailed else "STOP_INIT"
                break
            best = max(best, float(h5[cur]))
            worst = min(worst, float(l5[cur]))
        if exit_ts is None:
            cur = max(m_end, min(k + 1, n5 - 1))
            if side == 1:
                exit_px = float(c5[cur]) - slip
            else:
                exit_px = float(c5[cur]) + spread + slip
            exit_ts = int(ts5[cur]) + 5 * 60 * NS
            reason = "TIME"
        net = side * (exit_px - entry) / pip
        if side == 1:
            mfe = (best - entry) / pip
            mae = (worst - entry) / pip
        else:
            mfe = (entry - worst) / pip
            mae = (entry - best) / pip
        trades.append({"j": int(j), "sym": sym, "side": side,
                       "decision_ts": d, "entry_ts": int(ts5[k]),
                       "entry": entry, "exit_ts": int(exit_ts),
                       "exit_px": float(exit_px), "reason": reason,
                       "net_pips": float(net), "r": float(net * pip / sd),
                       "risk_pips": float(sd / pip),
                       "mfe": float(mfe), "mae": float(mae),
                       "trailed": bool(trailed)})
        last_exit_ts = exit_ts
    return trades


# ------------------------------------------------------- m2lib metrics

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
    """[VERBATIM m2lib@0a4eb55 agg_metrics]."""
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


def survival_veto(trades, start_capital=500.0, risk_frac=0.005):
    """[VERBATIM m2lib@0a4eb55 survival_veto]."""
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


# ------------------------------------------------------------ reporting

def full_metrics(trades, label):
    """Mission §15 metric table on a trade list."""
    if not trades:
        return {"label": label, "N": 0}
    tr = sorted(trades, key=lambda t: t["entry_ts"])
    net = np.array([t["net_pips"] for t in tr])
    r = np.array([t["r"] for t in tr])
    dur_h = np.array([(t["exit_ts"] - t["entry_ts"]) / 3.6e12 for t in tr])
    win = net[net > 0]
    los = net[net < 0]
    mfe = np.array([t.get("mfe", np.nan) for t in tr])
    mae = np.array([t.get("mae", np.nan) for t in tr])
    pos_mfe = np.where(np.isfinite(mfe) & (mfe > 0), mfe, 0.0)
    cap = (float(np.sum(net) / np.sum(pos_mfe))
           if np.sum(pos_mfe) > 0 else None)
    exits = {}
    for t in tr:
        exits[t["reason"]] = exits.get(t["reason"], 0) + 1
    weeks = max((tr[-1]["entry_ts"] - tr[0]["entry_ts"]) / (7 * 86400.0 * NS),
                1e-9)
    m = agg_metrics(tr, label)
    m["exits"] = exits
    m.update({
        "trades_per_week": round(len(tr) / weeks, 3),
        "avg_winner": round(float(win.mean()), 3) if len(win) else None,
        "median_winner": round(float(np.median(win)), 3) if len(win) else None,
        "largest_winner": round(float(win.max()), 3) if len(win) else None,
        "avg_loser": round(float(los.mean()), 3) if len(los) else None,
        "median_loser": round(float(np.median(los)), 3) if len(los) else None,
        "avg_duration_h": round(float(dur_h.mean()), 2),
        "median_duration_h": round(float(np.median(dur_h)), 2),
        "mfe_mean": round(float(np.nanmean(mfe)), 3),
        "mae_mean": round(float(np.nanmean(mae)), 3),
        "capture_ratio": round(cap, 3) if cap is not None else None,
        "exits_pct": {k: round(100.0 * v / len(tr), 1)
                      for k, v in sorted(exits.items(), key=lambda kv: -kv[1])},
    })
    return m


def stress_pair(base, stress):
    """Common-key pairing on (sym, decision_ts, side)."""
    def key(t):
        return (t.get("sym", ""), int(t["decision_ts"]), int(t["side"]))
    bmap = {key(t): t for t in base}
    smap = {key(t): t for t in stress}
    keys = sorted(set(bmap) & set(smap))
    return [bmap[k] for k in keys], [smap[k] for k in keys]


def stress_stats(base, stress):
    b, s = stress_pair(base, stress)
    if not s:
        return {"n_common": 0}
    ns = np.array([t["net_pips"] for t in s])
    nb = np.array([t["net_pips"] for t in b])
    return {"n_common": len(s),
            "base_mean_common": round(float(nb.mean()), 3),
            "stress_mean": round(float(ns.mean()), 3),
            "stress_PF": round(pf_of(ns), 3),
            "stress_remove_best": round(remove_best_1pct(ns), 3)}


def common_intersection(set_a, set_b):
    """Trade lists restricted to the common (decision_ts, side[, sym]) keys."""
    def key(t):
        return (t.get("sym", ""), int(t["decision_ts"]), int(t["side"]))
    ka = {key(t) for t in set_a}
    kb = {key(t) for t in set_b}
    common = ka & kb
    return ([t for t in set_a if key(t) in common],
            [t for t in set_b if key(t) in common])


def block_metrics(trades):
    """Mission §16 frozen-exit stability blocks (2018 not covered by the
    historical signal period; blocks reported where coverage permits)."""
    out = {}
    for name, y0, y1 in (("2010-2014", 2010, 2015),
                         ("2015-2016", 2015, 2017),
                         ("2017", 2017, 2018)):
        blk = [t for t in trades
               if y0 <= pd.Timestamp(t["entry_ts"], unit="ns", tz="UTC").year < y1]
        m = full_metrics(blk, name)
        out[name] = {k: m.get(k) for k in
                     ("N", "mean_pips", "PF", "expectancy_r", "win_rate",
                      "pos_years", "total_pips")}
    return out


def event_hash(events_ts, events_side, pairs=None):
    h = hashlib.sha256()
    h.update(np.ascontiguousarray(np.asarray(events_ts, dtype=np.int64)).tobytes())
    h.update(np.ascontiguousarray(np.asarray(events_side, dtype=np.int8)).tobytes())
    if pairs is not None:
        h.update("".join(pairs).encode())
    return h.hexdigest()


def save(obj, name):
    p = os.path.join(OUT, name)
    with open(p, "w") as f:
        json.dump(obj, f, indent=1, default=float)
    return p
