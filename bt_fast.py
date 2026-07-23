#!/usr/bin/env python3
"""Numba-JIT backtest engine for EMA_Pullback_pyramid_v2.

Same logic as bt_engine.py but with the hot loop compiled via @njit.
~100x faster, enabling coarse-to-fine optimization in minutes.

Params passed as a flat float array for JIT friendliness.
"""
import math, time
import numpy as np
import pandas as pd
from numba import njit
from bt_engine import load_mt4_csv, precompute, default_params

PIP = 0.0001
PIP_VALUE_PER_LOT = 10.0

# Parameter index map (order matters)
PARAM_KEYS = [
    "RiskPercent", "MinRR", "MinSL_Pips", "MaxSL_Pips",
    "L0_LotMult", "L1_LotMult", "L2_LotMult", "MaxStreakLevel",
    "UseReverseTrade", "UseReverseOnL0", "UseReverseOnL2",
    "UseRevLotFromLevel", "RevLotMult", "RevMaxSL_Pips", "RevMinConsecLosses",
    "RollingWR_Window", "RollingWR_Threshold",
    "TrendBars", "SL_SwingBars", "RSI_OB", "RSI_OS",
    "LondonStartHour", "LondonEndHour", "NYStartHour", "NYEndHour",
    "UseBreakeven", "BE_Trigger_R", "MaxTradesPerDay",
    "UseATRFilter", "ATR_MinPips", "ATR_MaxPips",
    "UseEMA50DistFilter", "MaxEMA50DistPips",
    "UsePyramid", "ReduceThursdayRisk", "ThursdayRiskMult",
]


def params_to_array(P):
    return np.array([float(P[k]) for k in PARAM_KEYS], dtype=np.float64)


def pack_data(D, start, end):
    """Extract only arrays needed by the JIT loop, plus the entry window."""
    ts = D["ts"]
    in_window = ((ts >= start) & (ts <= end)).values.astype(np.bool_)
    # blocked mask (session/friday/blocked hours) precomputed per-bar
    hour = D["hour"]
    dow = D["dow_mql"]
    sess = ((hour >= 8) & (hour < 18)).astype(np.bool_)  # wide; refined inside by params
    return {
        "o": D["o"], "h": D["h"], "l": D["l"], "c": D["c"],
        "ema20": D["ema20"], "rsi14": D["rsi14"],
        "ema50_now": D["ema50_now"],
        "h1_close": D["h1_close"],
        "atr_now": D["atr_now"],
        "hour": D["hour"].astype(np.int64),
        "dow": D["dow_mql"].astype(np.int64),
        "year": D["ts"].dt.year.values.astype(np.int64),
        "day_ord": D["ts"].dt.floor("D").astype("int64").values,
        "in_window": in_window,
        "ema50_h1": D["ema50_h1"],
        "h1_prev": D["h1_prev"].astype(np.int64),
        "n": D["n"],
    }


@njit(cache=True, fastmath=True)
def _bt(o, h, l, c, ema20, rsi14, ema50_now, ema50_prev, h1_close, atr_now,
        hour, dow, year, day_ord, in_window, n, P, initial_balance):
    # Unpack params
    RiskPercent = P[0]; MinRR = P[1]; MinSL = P[2]; MaxSL = P[3]
    L0m = P[4]; L1m = P[5]; L2m = P[6]; MaxStreak = int(P[7])
    UseRev = P[8] > 0.5; UseRevL0 = P[9] > 0.5; UseRevL2 = P[10] > 0.5
    UseRevFromLvl = P[11] > 0.5; RevLotMult = P[12]; RevMaxSL = P[13]
    RevMinConsec = int(P[14]); RollingWin = int(P[15]); RollingThresh = P[16]
    SL_Swing = int(P[18]); RSI_OB = P[19]; RSI_OS = P[20]
    LonS = int(P[21]); LonE = int(P[22]); NYS = int(P[23]); NYE = int(P[24])
    UseBE = P[25] > 0.5; BE_R = P[26]; MaxDay = int(P[27])
    UseATR = P[28] > 0.5; ATRmin = P[29]; ATRmax = P[30]
    UseEMA50 = P[31] > 0.5; EMA50dist = P[32]
    UsePyr = P[33] > 0.5; UseThu = P[34] > 0.5; ThuMult = P[35]

    balance = initial_balance
    peak = initial_balance
    max_dd = 0.0
    max_dd_pct = 0.0
    streak = 0
    consec = 0
    # rolling buffer (max 20)
    roll = np.zeros(20)
    roll_cnt = 0
    roll_idx = 0
    last_rev = False
    last_lvl = 0
    last_type = 0
    # position state
    has_pos = False
    pdir = 0
    pentry = 0.0
    psl = 0.0
    ptp = 0.0
    plots = 0.0
    prisk = 0.0
    pbe = False
    daily = 0
    cur_day = np.int64(-1)
    n_trades = 0
    year_pnl = np.zeros(2100 - 2009, dtype=np.float64)

    i = 60
    while i < n - 1:
        if has_pos:
            # breakeven
            if UseBE and not pbe:
                if pdir == 1 and (h[i] - pentry) >= prisk * BE_R:
                    psl = pentry + PIP; pbe = True
                elif pdir == -1 and (pentry - l[i]) >= prisk * BE_R:
                    psl = pentry - PIP; pbe = True
            closed = False
            xp = 0.0
            if pdir == 1:
                if l[i] <= psl: xp = psl; closed = True
                elif h[i] >= ptp: xp = ptp; closed = True
            else:
                if h[i] >= psl: xp = psl; closed = True
                elif l[i] <= ptp: xp = ptp; closed = True
            if closed:
                pnl = (xp - pentry) / PIP * pdir * PIP_VALUE_PER_LOT * plots
                balance += pnl
                win = pnl > 0
                yy = year[i] - 2010
                if 0 <= yy < len(year_pnl):
                    year_pnl[yy] += pnl
                n_trades += 1
                if not last_rev:
                    if last_lvl == 0:
                        w = RollingWin if RollingWin < 20 else 20
                        roll[roll_idx] = 1.0 if win else 0.0
                        roll_idx = (roll_idx + 1) % w
                        if roll_cnt < w: roll_cnt += 1
                    if win:
                        streak += 1
                        if streak > MaxStreak: streak = MaxStreak
                        consec = 0
                    else:
                        pl = last_lvl; pt = last_type
                        streak = 0; consec += 1
                        if UseRev:
                            should = False
                            if pl == 0 and UseRevL0:
                                should = (RevMinConsec <= 0 or consec >= RevMinConsec)
                            elif pl == 2 and UseRevL2:
                                wr = 50.0
                                if roll_cnt > 0:
                                    s = 0.0
                                    for k in range(roll_cnt): s += roll[k]
                                    wr = s / roll_cnt * 100.0
                                should = wr <= RollingThresh
                            if should and daily < MaxDay:
                                rd2 = -pt
                                rh = hour[i]
                                if not (rh >= 13 and rh <= 14) and rh < 17:
                                    sld = 0.0
                                    if rd2 == -1:
                                        sref = h[i - SL_Swing]
                                        for k in range(i - SL_Swing, i + 1):
                                            if h[k] > sref: sref = h[k]
                                        sref += 2 * PIP
                                        sld = (sref - c[i]) / PIP
                                    else:
                                        sref = l[i - SL_Swing]
                                        for k in range(i - SL_Swing, i + 1):
                                            if l[k] < sref: sref = l[k]
                                        sref -= 2 * PIP
                                        sld = (c[i] - sref) / PIP
                                    if sld > 0 and (RevMaxSL <= 0 or sld <= RevMaxSL):
                                        rm = (L2m if pl == 2 else L0m) if UseRevFromLvl else RevLotMult
                                        if UseThu and dow[i] == 4: rm *= ThuMult
                                        ent = c[i]
                                        # new reverse position
                                        pdir = rd2; pentry = ent
                                        psl = ent - rd2 * sld * PIP
                                        ptp = ent + rd2 * sld * PIP * MinRR
                                        rmoney = balance * RiskPercent / 100.0 * rm
                                        lots = rmoney / (sld * PIP_VALUE_PER_LOT)
                                        lots = math.floor(lots / 0.01) * 0.01
                                        if lots < 0.01: lots = 0.01
                                        if lots > 100.0: lots = 100.0
                                        plots = lots
                                        prisk = sld * PIP; pbe = False
                                        has_pos = True
                                        last_rev = True; last_lvl = 0; last_type = rd2
                                        daily += 1
                                        if balance > peak: peak = balance
                                        dd = peak - balance
                                        if dd > max_dd:
                                            max_dd = dd; max_dd_pct = dd / peak * 100.0
                                        i += 1
                                        continue
                if balance > peak: peak = balance
                dd = peak - balance
                if dd > max_dd:
                    max_dd = dd; max_dd_pct = dd / peak * 100.0
                has_pos = False
            i += 1
            continue

        # no open position
        dk = day_ord[i]
        if dk != cur_day:
            cur_day = dk; daily = 0
        if not in_window[i]:
            i += 1; continue
        hh = hour[i]; dd2 = dow[i]
        # session
        in_sess = ((hh >= LonS and hh < LonE) or (hh >= NYS and hh < NYE))
        if not in_sess or dd2 == 5:
            i += 1; continue
        # blocked hours
        blk = (hh == 13)
        if hh == 14 and dd2 == 2: blk = True
        if hh == 11 and dd2 == 1: blk = True
        if hh == 14 and dd2 == 4: blk = True
        if hh == 16 and dd2 == 1: blk = True
        if blk:
            i += 1; continue
        if daily >= MaxDay:
            i += 1; continue
        # ATR
        if UseATR:
            a = atr_now[i] / PIP
            if not (a == a) or a < ATRmin or (ATRmax > 0 and a > ATRmax):
                i += 1; continue
        # EMA50 dist
        if UseEMA50:
            dp = abs(c[i] - ema50_now[i]) / PIP
            if not (dp == dp) or dp > EMA50dist:
                i += 1; continue
        # trend
        trend = 0
        en = ema50_now[i]; ep = ema50_prev[i]
        if en == en and ep == ep:
            if h1_close[i] > en and en > ep: trend = 1
            elif h1_close[i] < en and en < ep: trend = -1
        if trend == 0:
            i += 1; continue
        # pullback
        b1 = i - 1; b2 = i - 2
        if b2 < 1:
            i += 1; continue
        o1 = o[b1]; c1 = c[b1]; h1 = h[b1]; l1 = l[b1]
        o2 = o[b2]; c2 = c[b2]; l2b = l[b2]; h2b = h[b2]
        e1 = ema20[b1]; e2 = ema20[b2]
        if not (e1 == e1) or not (e2 == e2):
            i += 1; continue
        body1 = abs(c1 - o1); range1 = h1 - l1; body2 = abs(c2 - o2)
        rv = rsi14[b1]
        if not (rv == rv):
            i += 1; continue
        direction = 0
        if trend == 1:
            if rv > RSI_OB or l2b > e2 or c1 <= e1 or c1 <= o1:
                i += 1; continue
            if (range1 > 0 and body1 / range1 < 0.6) or body1 <= body2:
                i += 1; continue
            direction = 1
        else:
            if rv < RSI_OS or h2b < e2 or c1 >= e1 or c1 >= o1:
                i += 1; continue
            if (range1 > 0 and body1 / range1 < 0.6) or body1 <= body2:
                i += 1; continue
            direction = -1
        # SL from swing
        if direction == 1:
            sref = l1
            for k in range(1, SL_Swing + 1):
                if l[b1 - k] < sref: sref = l[b1 - k]
            sl = sref - 2 * PIP
            entry = c[i]
            sld = (entry - sl) / PIP
        else:
            sref = h1
            for k in range(1, SL_Swing + 1):
                if h[b1 - k] > sref: sref = h[b1 - k]
            sl = sref + 2 * PIP
            entry = c[i]
            sld = (sl - entry) / PIP
        if sld < MinSL or sld > MaxSL:
            i += 1; continue
        tp = entry + direction * sld * PIP * MinRR
        rmult = 1.0
        if UseThu and dd2 == 4: rmult *= ThuMult
        if UsePyr:
            if streak == 0: rmult *= L0m
            elif streak == 1: rmult *= L1m
            else: rmult *= L2m
        rmoney = balance * RiskPercent / 100.0 * rmult
        lots = rmoney / (sld * PIP_VALUE_PER_LOT)
        lots = math.floor(lots / 0.01) * 0.01
        if lots < 0.01: lots = 0.01
        if lots > 100.0: lots = 100.0
        pdir = direction; pentry = entry; psl = sl; ptp = tp
        plots = lots; prisk = sld * PIP; pbe = False
        has_pos = True
        last_rev = False; last_lvl = streak; last_type = direction
        daily += 1
        i += 1

    # force close at end
    if has_pos:
        xp = c[n - 1]
        pnl = (xp - pentry) / PIP * pdir * PIP_VALUE_PER_LOT * plots
        balance += pnl
        yy = year[n - 1] - 2010
        if 0 <= yy < len(year_pnl): year_pnl[yy] += pnl
        n_trades += 1
        if balance > peak: peak = balance
        dd = peak - balance
        if dd > max_dd:
            max_dd = dd; max_dd_pct = dd / peak * 100.0

    return balance, max_dd, max_dd_pct, n_trades, year_pnl


def run_fast(PKD, P, initial_balance=10000.0):
    Parr = params_to_array(P)
    ema50_prev = PKD["ema50_h1"][np.clip(PKD["h1_prev"] - int(P["TrendBars"]), 0,
                                          len(PKD["ema50_h1"]) - 1)]
    bal, mdd, mddp, ntr, ypnl = _bt(
        PKD["o"], PKD["h"], PKD["l"], PKD["c"], PKD["ema20"], PKD["rsi14"],
        PKD["ema50_now"], ema50_prev, PKD["h1_close"], PKD["atr_now"],
        PKD["hour"], PKD["dow"], PKD["year"], PKD["day_ord"], PKD["in_window"],
        PKD["n"], Parr, initial_balance)
    years = {2010 + k: ypnl[k] for k in range(len(ypnl)) if abs(ypnl[k]) > 1e-9}
    return {"balance": bal, "max_dd": mdd, "max_dd_pct": mddp,
            "n_trades": ntr, "year_pnl": years}


if __name__ == "__main__":
    t0 = time.time()
    print("Loading + precomputing...")
    df = load_mt4_csv("EURUSD15.csv")
    D = precompute(df)
    PKD = pack_data(D, pd.Timestamp("2010-01-01"), pd.Timestamp("2026-04-08"))
    P = default_params()
    print("Compiling JIT (first run slow)...")
    r = run_fast(PKD, P)
    print(f"  compile+run: {time.time()-t0:.1f}s")
    # timing on subsequent runs
    t1 = time.time()
    reps = 20
    for _ in range(reps):
        r = run_fast(PKD, P)
    dt = (time.time() - t1) / reps
    print(f"\n=== RESULT (SAFE+Rev config) ===  [{dt*1000:.0f} ms/backtest]")
    print(f"Balance: ${r['balance']:,.0f}  Max DD: ${r['max_dd']:,.0f} ({r['max_dd_pct']:.1f}%)")
    print(f"Trades: {r['n_trades']}")
    neg = sum(1 for y in r['year_pnl'] if r['year_pnl'][y] < 0)
    print(f"Negative years: {neg}")
    for y in sorted(r['year_pnl']):
        print(f"  {y}: ${r['year_pnl'][y]:+,.0f}{'  <-- NEG' if r['year_pnl'][y] < 0 else ''}")
