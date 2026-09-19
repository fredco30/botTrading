#!/usr/bin/env python3
"""FX_PDH_002 LAB — shared causal engine (USDJPY H1, sealed local data).

Generalizes the FROZEN FX_PDH_001 strict replay
(../forex_modern_trend_magic_lab/audit/replay_strict.py) along exactly the
axes the protocol pre-registers:

  * side          LONG (001) or the exact SHORT mirror (002A);
  * entry signal  first-touch / C1 close-confirm / C2 close-retest /
                  C3 strong-break (002C);
  * exit arch     orig trail / 4.5 trail / daily chandelier / 5-bar
                  structure exit (002D).

Everything else inherits STRICT V1 verbatim: one spread round-trip, initial
stop active from the fill (entry bar can stop out), trailing level for bar i
from information completed at the close of bar i-1 only, conservative
intrabar fills, no same-bar re-entry, one position at a time, one first-break
signal per UTC day, days with < 4 completed H1 bars skipped.

All data flows through tmlab.load_5m, which hard-seals 2026.
"""
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = HERE
while _ROOT != os.path.dirname(_ROOT) and not os.path.isdir(
        os.path.join(_ROOT, "forex_modern_trend_magic_lab")):
    _ROOT = os.path.dirname(_ROOT)
LAB1 = os.path.join(_ROOT, "forex_modern_trend_magic_lab")
sys.path.insert(0, LAB1)
import tmlab as T                                  # sealed data layer

PIP = 1e-2                          # USDJPY pip
SPREAD = 0.9                        # pips, NORMAL
SLIP_STRESS = 0.5                   # pips per side, STRESS
STOP_ATR, TRAIL_ATR, MAX_HOLD = 1.0, 3.0, 48
ATR_N = 14
CAPITAL, MIN_LOT, LOT_STEP = 500.0, 0.01, 0.01
RISK = 0.005                        # 0.5% target risk per layer
START, END = "2020-01-01", "2025-12-31 23:59"
N_WEEKS = 313.2
MIN_DAY_BARS = 4                    # frozen engine holiday rule


def atr14_rma(h, l, c):
    """Wilder RMA ATR14 on completed bars; atr[i] known at the close of i."""
    tr = T.true_range(h, l, c)
    out = np.full(len(c), np.nan)
    acc, s, cnt = np.nan, 0.0, 0
    for i, v in enumerate(tr):
        if np.isnan(acc):
            s += v
            cnt += 1
            if cnt == ATR_N:
                acc = s / ATR_N
        else:
            acc = (acc * (ATR_N - 1) + v) / ATR_N
        out[i] = acc
    return out


def ema(x, n):
    return T._ema(np.asarray(x, "float64"), n)


def prepare():
    """Sealed H1 frame + prior-completed-day PDH/PDL/close + ATR14.

    Day boundaries follow the frozen engine exactly: the 'previous day' is
    the previous UTC calendar day THAT HAS BARS (weekend gaps collapse),
    which is how replay_strict builds PDH.
    """
    df5 = T.load_5m("USDJPY", START, END)
    h1 = T.resample_ohlcv(df5, "1h")
    o = h1["open"].to_numpy(); h = h1["high"].to_numpy()
    l = h1["low"].to_numpy(); c = h1["close"].to_numpy()
    idx = h1.index
    n = len(c)
    day = np.array([ts.date() for ts in idx])
    days = sorted(set(day))
    day_pos = np.empty(n, "int64")
    pdh = np.full(n, np.nan); pdl = np.full(n, np.nan)
    prev_close = np.full(n, np.nan)
    day_first = np.full(n, -1, "int64")
    d_open = np.empty(len(days)); d_high = np.empty(len(days))
    d_low = np.empty(len(days)); d_close = np.empty(len(days))
    for p, d in enumerate(days):
        m = day == d
        ii = np.nonzero(m)[0]
        day_pos[ii] = p
        day_first[ii] = ii[0]
        d_open[p], d_high[p] = o[ii[0]], np.max(h[ii])
        d_low[p], d_close[p] = np.min(l[ii]), c[ii[-1]]
        if p > 0:
            pdh[ii] = d_high[p - 1]
            pdl[ii] = d_low[p - 1]
            prev_close[ii] = d_close[p - 1]
    d_atr = atr14_rma(d_high, d_low, d_close)      # daily Wilder ATR14
    D = dict(o=o, h=h, l=l, c=c, idx=idx, day=day, day_pos=day_pos,
             day_first=day_first, days=days, d_high=d_high, d_low=d_low,
             d_close=d_close, d_open=d_open, d_atr=d_atr,
             atr=atr14_rma(h, l, c), pdh=pdh, pdl=pdl, prev_close=prev_close,
             ema20=ema(c, 20))
    D["n_bars"] = n
    D["no_2026"] = bool(idx.max() <= pd.Timestamp("2025-12-31 23:59", tz="UTC"))
    return D


# ------------------------------------------------------------------ signals
def signals(D, kind):
    """Pre-registered entry-signal kinds -> sorted array of signal bar idx.

    long_touch  = 001/C0: first H1 of day with high > PDH
    short_touch = 002A  : first H1 of day with low  < PDL
    C1          = first H1 of day with close > PDH
    C2          = close arms the day; first LATER bar same day with
                  low <= PDH and close > PDH
    C3          = first touch bar, only if close-location >= 0.70
    """
    o, h, l, c = D["o"], D["h"], D["l"], D["c"]
    pdh, pdl, day = D["pdh"], D["pdl"], D["day"]
    sig = []
    for d in D["days"]:
        ii = np.nonzero(day == d)[0]
        if len(ii) < MIN_DAY_BARS:
            continue
        if kind in ("long_touch", "C1", "C3") and not np.isfinite(pdh[ii[0]]):
            continue
        if kind == "short_touch" and not np.isfinite(pdl[ii[0]]):
            continue
        if kind == "long_touch":
            brk = ii[h[ii] > pdh[ii]]
            if len(brk):
                sig.append(brk[0])
        elif kind == "short_touch":
            brk = ii[l[ii] < pdl[ii]]
            if len(brk):
                sig.append(brk[0])
        elif kind == "C1":
            brk = ii[c[ii] > pdh[ii]]
            if len(brk):
                sig.append(brk[0])
        elif kind == "C2":
            armed = -1
            for j in ii:
                if c[j] > pdh[j]:
                    armed = j
                    break
            if armed < 0:
                continue
            for j in ii[ii > armed]:
                if l[j] <= pdh[j] and c[j] > pdh[j]:
                    sig.append(j)
                    break
        elif kind == "C3":
            brk = ii[h[ii] > pdh[ii]]
            if len(brk):
                j = brk[0]
                rng = h[j] - l[j]
                loc = 0.5 if rng < 1e-12 else (c[j] - l[j]) / rng
                if loc >= 0.70:
                    sig.append(j)
        else:
            raise ValueError(kind)
    return np.array(sig, "int64")


# ------------------------------------------------------------------- replay
def replay(D, sig, side=1, exit_arch="orig", trail_mult=TRAIL_ATR, slip=0.0):
    """One-position strict replay, generalized per pre-registration.

    exit_arch: 'orig' (hh/ll extreme +/- trail_mult*ATR14(i-1)),
               'daily_chand' (daily-high anchored, 3x daily ATR14, active
               after the first completed day boundary post-entry),
               'struct5' (no trail; H1 close beyond the previous 5-bar
               extreme exits at that close).
    """
    assert side in (1, -1)
    o, h, l, c = D["o"], D["h"], D["l"], D["c"]
    atr, n = D["atr"], D["n_bars"]
    spread_abs = SPREAD * PIP
    slip_abs = slip * PIP
    day_pos, d_high, d_atr = D["day_pos"], D["d_high"], D["d_atr"]
    trades = []
    pos = None
    for i in range(n):
        if pos is not None:
            k, s = pos["k"], side
            if i == k:                               # entry bar: init stop only
                hit = (l[i] <= pos["stop"]) if s > 0 else (h[i] >= pos["stop"])
                if hit:
                    px = (min(o[i], pos["stop"]) - slip_abs if s > 0
                          else max(o[i], pos["stop"]) + slip_abs)
                    trades.append((k, i, px, "stop", pos["sig"]))
                    pos = None
                    continue
                if exit_arch == "struct5":           # 5 prior bars exist pre-entry
                    ext = np.min(l[i - 5:i]) if s > 0 else np.max(h[i - 5:i])
                    if (c[i] < ext) if s > 0 else (c[i] > ext):
                        px = c[i] - slip_abs if s > 0 else c[i] + slip_abs
                        trades.append((k, i, px, "struct", pos["sig"]))
                        pos = None
                        continue
                pos["hh"] = max(pos["hh"], h[i]) if s > 0 else min(pos["hh"], l[i])
                continue
            eff_stop = pos["stop"]
            reason = "stop"
            if exit_arch == "orig":
                a = atr[i - 1]
                if np.isfinite(a):
                    eff_stop = (max(pos["stop"], pos["hh"] - trail_mult * a)
                                if s > 0 else
                                min(pos["stop"], pos["hh"] + trail_mult * a))
            elif exit_arch == "daily_chand":
                p, p0 = day_pos[i], day_pos[k]
                if p > p0 and np.isfinite(d_atr[p - 1]):
                    # completed days since entry: p0 .. p-1
                    seg_hi = np.max(d_high[p0:p]) if s > 0 else np.min(d_low[p0:p])
                    eff_stop = (max(pos["stop"], seg_hi - 3.0 * d_atr[p - 1])
                                if s > 0 else
                                min(pos["stop"], seg_hi + 3.0 * d_atr[p - 1]))
            elif exit_arch == "struct5":
                ext = np.min(l[i - 5:i]) if s > 0 else np.max(h[i - 5:i])
                if (c[i] < ext) if s > 0 else (c[i] > ext):
                    px = c[i] - slip_abs if s > 0 else c[i] + slip_abs
                    trades.append((k, i, px, "struct", pos["sig"]))
                    pos = None
                    continue
            else:
                raise ValueError(exit_arch)
            hit = (l[i] <= eff_stop) if s > 0 else (h[i] >= eff_stop)
            if hit:
                px = (min(o[i], eff_stop) - slip_abs if s > 0
                      else max(o[i], eff_stop) + slip_abs)
                trades.append((k, i, px, "stop", pos["sig"]))
                pos = None
                continue
            if (i - k) >= MAX_HOLD:
                px = c[i] - slip_abs if s > 0 else c[i] + slip_abs
                trades.append((k, i, px, "time", pos["sig"]))
                pos = None
                continue
            pos["hh"] = max(pos["hh"], h[i]) if s > 0 else min(pos["hh"], l[i])
        if pos is None:
            j = np.searchsorted(sig, i, side="right") - 1
            if j >= 0 and sig[j] == i and i + 1 < n and np.isfinite(atr[i]):
                k = i + 1
                entry = (o[k] + spread_abs + slip_abs if side > 0
                         else o[k] - spread_abs - slip_abs)
                stop = entry - side * STOP_ATR * atr[i]
                pos = {"k": k, "entry": entry, "stop": stop,
                       "hh": h[k] if side > 0 else l[k], "sig": i}
    tr = pd.DataFrame(trades, columns=["entry_i", "exit_i", "exit_px",
                                       "reason", "sig_i"])
    if len(tr) == 0:
        return tr.assign(gross_pips=[], net_pips=[], entry_fill=[], r_mult=[])
    ei = tr["entry_i"].to_numpy()
    op = o[ei]
    tr = tr.assign(
        entry_fill=(op + side * (spread_abs + slip_abs)),
        gross_pips=(tr["exit_px"].to_numpy() - op) / PIP * side,
    )
    tr["net_pips"] = tr["gross_pips"] - SPREAD - slip
    stop_price = STOP_ATR * atr[tr["sig_i"].to_numpy()]     # price units
    tr["r_mult"] = tr["net_pips"].to_numpy() * PIP / stop_price
    tr["stop_pips"] = stop_price / PIP
    return tr


# ------------------------------------------------------------------ metrics
def summarize(D, tr, slip=0.0, label=""):
    """Headline metrics on net pips (PF/t/RB1 convention of the vault)."""
    r = tr["net_pips"].to_numpy()
    if len(r) == 0:
        return {"label": label, "n": 0}
    wins, losses = r[r > 0], r[r <= 0]
    pf = float(wins.sum() / -losses.sum()) if losses.sum() else float("inf")
    se = float(np.std(r, ddof=1) / np.sqrt(len(r)))
    k = max(1, int(round(0.01 * len(r))))
    rb1 = float(np.mean(np.sort(r)[:-k]))
    yrs = np.array([D["idx"][i].year for i in tr["entry_i"]])
    ysum = {int(y): float(np.sum(r[yrs == y])) for y in sorted(set(yrs))}
    total = float(r.sum())
    cum = np.cumsum(tr["r_mult"].to_numpy())
    dd_r = float(np.max(np.maximum.accumulate(cum) - cum)) if len(cum) else 0.0
    return {
        "label": label, "slip": slip, "n": int(len(r)),
        "trades_per_week": float(len(r) / N_WEEKS),
        "net_pips_per_trade": float(np.mean(r)),
        "total_net_pips": total,
        "pf": pf, "win_rate": float(np.mean(r > 0)),
        "expectancy_r": float(np.mean(tr["r_mult"])),
        "t_stat": float(np.mean(r)) / se if se > 0 else float("nan"),
        "remove_best_1pct": rb1, "max_dd_r": dd_r,
        "by_year": {int(y): float(np.mean(r[yrs == y]))
                    for y in sorted(set(yrs))},
        "year_sums": ysum,
        "y2022_profit_share_pct": float(100 * ysum.get(2022, 0.0) / total),
        "exits": {kk: int(v) for kk, v in tr["reason"].value_counts().items()},
        "last_exit": str(D["idx"][int(tr["exit_i"].max())]),
        "no_2026": bool(D["idx"][int(tr["exit_i"].max())].year <= 2025),
    }


def eur500_sim(D, tr, risk=RISK, slip=0.0, capital=CAPITAL):
    """EUR500 account at target risk with 0.01-lot floor rounding.

    Sizing identical to the frozen engine convention: target risk uses FIXED
    initial capital (no compounding of the position size); the equity path
    accumulates realized trade PnL. Returns gate dict + per-trade frame.
    """
    idx = D["idx"]
    eur5 = T.load_5m("EURUSD", START, END)             # sealed
    euri, eurc = eur5.index, eur5["close"].to_numpy()
    ei = tr["entry_i"].to_numpy().astype(int)
    stop_pips = tr["stop_pips"].to_numpy()
    # JPY pip value -> USD: 1000 units * pip / USDJPY ; then USD -> EUR
    j, _ = np.searchsorted(euri, idx[ei], side="right") - 1, None
    usdjpy = D["c"][ei]
    pip_eur = 1000.0 * PIP / usdjpy * eurc[j]
    target_lot = risk * capital / (stop_pips * pip_eur * 100.0)
    lots = np.maximum(MIN_LOT, np.floor(target_lot / LOT_STEP) * LOT_STEP)
    risk_eur = stop_pips * pip_eur * (lots / MIN_LOT)
    pnl = tr["r_mult"].to_numpy() * risk_eur
    ex = tr["exit_i"].to_numpy().astype(int)
    times = idx[ex]
    eq = capital + np.cumsum(pnl)
    peak = np.maximum.accumulate(eq)
    dd = peak - eq
    # losing streak
    lose = pnl <= 0
    streak = best = 0
    for v in lose:
        streak = streak + 1 if v else 0
        best = max(best, streak)
    # worst calendar year (% vs capital at year start) + rolling 12m
    yr = np.array([t.year for t in times])
    year_ret = {}
    for y in sorted(set(yr)):
        m = yr == y
        start_eq = eq[np.nonzero(m)[0][0]] - pnl[np.nonzero(m)[0][0]]
        year_ret[int(y)] = float(100 * (eq[m][-1] - start_eq) / start_eq)
    roll = np.full(len(eq), np.nan)
    for a in range(len(eq)):
        b = np.searchsorted(times, times[a] - pd.Timedelta(days=365),
                            side="right") - 1
        if b >= 0:
            roll[a] = 100 * (eq[a] - eq[b]) / eq[b]
    notional_eur = lots * 100000.0 * eurc[j]   # lot*100k USD units -> EUR
    lev = notional_eur / eq
    out = {
        "ending_equity": float(eq[-1]),
        "max_dd_percent": float(100 * np.max(dd / peak)),
        "max_dd_eur": float(np.max(dd)),
        "max_losing_streak": int(best),
        "year_returns_pct": year_ret,
        "worst_year_pct": float(min(year_ret.values())),
        "worst_rolling_12m_pct": float(np.nanmin(roll)),
        "median_risk_eur_minlot": float(np.median(stop_pips * pip_eur)),
        "median_lot": float(np.median(lots)),
        "peak_leverage": float(np.max(lev)),
        "peak_margin_eur_at_1to30": float(np.max(notional_eur) / 30.0),
    }
    gate = {
        "VETO": bool(out["max_dd_percent"] >= 50 or out["ending_equity"] <= 250
                     or out["worst_year_pct"] <= -40
                     or out["worst_rolling_12m_pct"] <= -40),
        "WARN": bool(out["max_dd_percent"] >= 30 or out["worst_year_pct"] <= -25),
    }
    detail = pd.DataFrame({"time": times, "equity": eq, "lot": lots,
                           "pnl_eur": pnl, "risk_eur": risk_eur})
    return out, gate, detail
