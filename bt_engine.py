#!/usr/bin/env python3
"""Vectorized backtest engine for EMA_Pullback_pyramid_v2 (EURUSD M15+H1).

Reproduces the MQL4 v2 logic with fidelity:
  - H1 EMA50 trend (price above + EMA rising over TrendBars)
  - M15 EMA20 pullback + rejection (body>=60% range, body1>body2)
  - RSI(14) M15 filter, ATR(14) H1 band, EMA50 distance filter
  - Session (London 8-12, NY 13-17), blocked hours, toxic combos, Friday
  - Anti-martingale pyramid L0/L1/L2 with streak
  - Reverse trade on SL (L0 after N consec losses, L2 when cold)
  - Breakeven at BE_Trigger_R, Thursday risk reduction, Max trades/day
  - Bar-level execution: SL/TP checked on M15 OHLC, SL priority on same bar

Speed: indicators precomputed; entry loop is over M15 bars.
"""
import math, time
import numpy as np
import pandas as pd

PIP = 0.0001
PIP_VALUE_PER_LOT = 10.0  # $ per pip per standard lot (EURUSD, USD account)


# ----------------------------------------------------------------------
# DATA
# ----------------------------------------------------------------------
def load_mt4_csv(path):
    df = pd.read_csv(path, header=None,
                     names=["date", "time", "open", "high", "low", "close", "vol"])
    df["dt"] = pd.to_datetime(df["date"] + " " + df["time"], format="%Y.%m.%d %H:%M")
    return df[["dt", "open", "high", "low", "close", "vol"]].reset_index(drop=True)


def ema(arr, period):
    """EMA matching MQL4 iMA (seeded with SMA of first `period` values)."""
    n = len(arr)
    out = np.full(n, np.nan)
    if n < period:
        return out
    alpha = 2.0 / (period + 1.0)
    out[period - 1] = np.mean(arr[:period])
    for i in range(period, n):
        out[i] = alpha * arr[i] + (1.0 - alpha) * out[i - 1]
    return out


def atr(df, period):
    """ATR matching MQL4 iATR (Wilder)."""
    high, low, close = df["high"].values, df["low"].values, df["close"].values
    n = len(df)
    tr = np.full(n, np.nan)
    tr[0] = high[0] - low[0]
    for i in range(1, n):
        tr[i] = max(high[i] - low[i], abs(high[i] - close[i - 1]), abs(low[i] - close[i - 1]))
    out = np.full(n, np.nan)
    if n < period:
        return out
    out[period - 1] = np.nanmean(tr[:period])
    for i in range(period, n):
        out[i] = (out[i - 1] * (period - 1) + tr[i]) / period
    return out


def rsi_wilder(close, period=14):
    """RSI matching MQL4 iRSI (Wilder)."""
    n = len(close)
    out = np.full(n, np.nan)
    if n < period + 1:
        return out
    delta = np.diff(close)
    gain = np.where(delta > 0, delta, 0.0)
    loss = np.where(delta < 0, -delta, 0.0)
    ag = np.full(n, np.nan)
    al = np.full(n, np.nan)
    ag[period] = np.mean(gain[:period])
    al[period] = np.mean(loss[:period])
    for i in range(period + 1, n):
        ag[i] = (ag[i - 1] * (period - 1) + gain[i - 1]) / period
        al[i] = (al[i - 1] * (period - 1) + loss[i - 1]) / period
    rs = np.where(al == 0, np.inf, ag / al)
    return 100.0 - 100.0 / (1.0 + rs)


def build_h1(df15):
    d = df15.copy()
    d["hour"] = d["dt"].dt.floor("h")
    g = d.groupby("hour").agg(open=("open", "first"), high=("high", "max"),
                              low=("low", "min"), close=("close", "last")).reset_index()
    return g.rename(columns={"hour": "dt"})


# ----------------------------------------------------------------------
# DEFAULT PARAMS (v2 Test04 config, SAFE mode)
# ----------------------------------------------------------------------
def default_params():
    return {
        "RiskPercent": 1.0, "MinRR": 2.5, "MinSL_Pips": 15.0, "MaxSL_Pips": 25.0,
        "UsePyramid": True, "L0_LotMult": 1.0, "L1_LotMult": 4.0, "L2_LotMult": 2.5,
        "MaxStreakLevel": 2,
        "UseReverseTrade": True, "UseReverseOnL0": True, "UseReverseOnL2": True,
        "UseRevLotFromLevel": True, "RevLotMult": 1.0, "RevMaxSL_Pips": 25.0,
        "RevMinConsecLosses": 3,
        "RollingWR_Window": 5, "RollingWR_Threshold": 40.0,
        "TrendEMA_Period": 50, "TrendBars": 5, "EntryEMA_Period": 20,
        "SL_SwingBars": 3, "RSI_Period": 14, "RSI_OB": 70, "RSI_OS": 30,
        "LondonStartHour": 8, "LondonEndHour": 12, "NYStartHour": 13, "NYEndHour": 17,
        "UseBreakeven": True, "BE_Trigger_R": 1.5, "MaxTradesPerDay": 4,
        "UseATRFilter": True, "ATR_Period": 14, "ATR_MinPips": 9.0, "ATR_MaxPips": 19.0,
        "UseEMA50DistFilter": True, "MaxEMA50DistPips": 30.0,
        "BlockFriday": True, "BlockHour13": True, "BlockedHoursList": [13],
        "BlockToxicCombos": True, "ReduceThursdayRisk": True, "ThursdayRiskMult": 0.5,
    }


# ----------------------------------------------------------------------
# PRECOMPUTE (once per dataset; independent of params we sweep)
# ----------------------------------------------------------------------
def precompute(df15):
    o, h, l, c = (df15["open"].values, df15["high"].values,
                  df15["low"].values, df15["close"].values)
    ts = df15["dt"]
    n = len(df15)
    ema20 = ema(c, 20)
    rsi14 = rsi_wilder(c, 14)
    dfh = build_h1(df15)
    ema50_h1 = ema(dfh["close"].values, 50)
    atr_h1 = atr(dfh, 14)
    h1_dt = dfh["dt"].values
    m15_hour = ts.dt.floor("h").values
    h1_index = np.searchsorted(h1_dt, m15_hour, side="right") - 1
    h1_prev = np.clip(h1_index - 1, 0, len(h1_dt) - 1)
    hour = ts.dt.hour.values
    dow_mql = ((ts.dt.dayofweek.values + 1) % 7)
    return {
        "o": o, "h": h, "l": l, "c": c, "ts": ts, "n": n,
        "ema20": ema20, "rsi14": rsi14,
        "ema50_now": ema50_h1[h1_prev],
        "ema50_h1": ema50_h1, "h1_prev": h1_prev,
        "h1_close": dfh["close"].values[h1_prev],
        "atr_now": atr_h1[h1_prev],
        "hour": hour, "dow_mql": dow_mql,
        "day_key": ts.dt.floor("D").values,
    }


# ----------------------------------------------------------------------
# BACKTEST
# ----------------------------------------------------------------------
def run_backtest(D, P, start, end, initial_balance=10000.0):
    o, h, l, c, n = D["o"], D["h"], D["l"], D["c"], D["n"]
    ts, hour, dow = D["ts"], D["hour"], D["dow_mql"]
    ema20, rsi14 = D["ema20"], D["rsi14"]
    ema50_now, h1_close, atr_now = D["ema50_now"], D["h1_close"], D["atr_now"]
    ema50_h1, h1_prev = D["ema50_h1"], D["h1_prev"]
    day_key = D["day_key"]

    tb = P["TrendBars"]
    ema50_prev = ema50_h1[np.clip(h1_prev - tb, 0, len(ema50_h1) - 1)]

    sess = ((hour >= P["LondonStartHour"]) & (hour < P["LondonEndHour"])) | \
           ((hour >= P["NYStartHour"]) & (hour < P["NYEndHour"]))
    friday = (dow == 5)
    blocked = np.zeros(n, dtype=bool)
    if P["BlockHour13"]:
        blocked |= (hour == 13)
    for bh in P["BlockedHoursList"]:
        blocked |= (hour == bh)
    if P["BlockToxicCombos"]:
        blocked |= ((hour == 14) & (dow == 2)) | ((hour == 11) & (dow == 1)) | \
                   ((hour == 14) & (dow == 4)) | ((hour == 16) & (dow == 1))
    in_window = (ts >= start) & (ts <= end)
    in_window = in_window.values if hasattr(in_window, "values") else in_window

    balance = initial_balance
    peak = initial_balance
    max_dd = max_dd_pct = 0.0
    streak = consec_losses = 0
    rolling = []
    last_rev = False
    last_lvl = 0
    last_type = 0
    pos = None
    daily_count = 0
    cur_day = None
    trades = []

    def get_lot(risk_dist, mult):
        rm = balance * P["RiskPercent"] / 100.0 * mult
        lots = rm / (risk_dist / PIP * PIP_VALUE_PER_LOT)
        lots = math.floor(lots / 0.01) * 0.01
        return round(max(0.01, min(100.0, lots)), 2)

    i = 60
    while i < n - 1:
        if pos is not None:
            rd = pos["risk_dist"]
            if P["UseBreakeven"] and not pos["be_done"]:
                if pos["dir"] == 1 and (h[i] - pos["entry"]) >= rd * P["BE_Trigger_R"]:
                    pos["sl"] = pos["entry"] + PIP; pos["be_done"] = True
                elif pos["dir"] == -1 and (pos["entry"] - l[i]) >= rd * P["BE_Trigger_R"]:
                    pos["sl"] = pos["entry"] - PIP; pos["be_done"] = True
            closed = False
            xp = None
            if pos["dir"] == 1:
                if l[i] <= pos["sl"]: xp, closed = pos["sl"], True
                elif h[i] >= pos["tp"]: xp, closed = pos["tp"], True
            else:
                if h[i] >= pos["sl"]: xp, closed = pos["sl"], True
                elif l[i] <= pos["tp"]: xp, closed = pos["tp"], True
            if closed:
                pnl = (xp - pos["entry"]) / PIP * pos["dir"] * PIP_VALUE_PER_LOT * pos["lots"]
                balance += pnl
                win = pnl > 0
                if not last_rev:
                    if last_lvl == 0:
                        rolling.append(1 if win else 0)
                        if len(rolling) > P["RollingWR_Window"]:
                            rolling.pop(0)
                    if win:
                        streak = min(streak + 1, P["MaxStreakLevel"]); consec_losses = 0
                    else:
                        pl, pt = last_lvl, last_type
                        streak = 0; consec_losses += 1
                        if P["UseReverseTrade"]:
                            should = False
                            if pl == 0 and P["UseReverseOnL0"]:
                                should = (P["RevMinConsecLosses"] <= 0 or
                                          consec_losses >= P["RevMinConsecLosses"])
                            elif pl == 2 and P["UseReverseOnL2"]:
                                wr = (sum(rolling) / len(rolling) * 100.0) if rolling else 50.0
                                should = wr <= P["RollingWR_Threshold"]
                            if should and daily_count < P["MaxTradesPerDay"]:
                                rd2 = -pt
                                rh = hour[i]
                                if not (13 <= rh <= 14) and rh < 17:
                                    if rd2 == -1:
                                        sref = max(h[i - P["SL_SwingBars"]:i + 1]) + 2 * PIP
                                        sld = (sref - c[i]) / PIP
                                    else:
                                        sref = min(l[i - P["SL_SwingBars"]:i + 1]) - 2 * PIP
                                        sld = (c[i] - sref) / PIP
                                    if sld > 0 and (P["RevMaxSL_Pips"] <= 0 or sld <= P["RevMaxSL_Pips"]):
                                        rm = (P["L2_LotMult"] if pl == 2 else P["L0_LotMult"]) \
                                             if P["UseRevLotFromLevel"] else P["RevLotMult"]
                                        if P["ReduceThursdayRisk"] and dow[i] == 4:
                                            rm *= P["ThursdayRiskMult"]
                                        ent = c[i]
                                        rsl = ent - rd2 * sld * PIP
                                        rtp = ent + rd2 * sld * PIP * P["MinRR"]
                                        pos = {"dir": rd2, "entry": ent, "sl": rsl, "tp": rtp,
                                               "lots": get_lot(sld * PIP, rm), "risk_dist": sld * PIP,
                                               "be_done": False, "open_i": i}
                                        last_rev, last_lvl, last_type = True, 0, rd2
                                        daily_count += 1
                                        if balance > peak: peak = balance
                                        dd = peak - balance
                                        if dd > max_dd: max_dd, max_dd_pct = dd, dd / peak * 100.0
                                        trades.append({"dt": ts[i], "pnl": pnl, "balance": balance,
                                                       "win": win, "level": pl, "is_rev": False,
                                                       "year": ts[i].year})
                                        i += 1
                                        continue
                if balance > peak: peak = balance
                dd = peak - balance
                if dd > max_dd: max_dd, max_dd_pct = dd, dd / peak * 100.0
                trades.append({"dt": ts[i], "pnl": pnl, "balance": balance, "win": win,
                               "level": 0 if last_rev else last_lvl, "is_rev": last_rev,
                               "year": ts[i].year})
                pos = None
            i += 1
            continue

        dk = day_key[i]
        if cur_day is None or dk != cur_day:
            cur_day = dk; daily_count = 0
        if not in_window[i] or not sess[i] or friday[i] or blocked[i]:
            i += 1; continue
        if daily_count >= P["MaxTradesPerDay"]:
            i += 1; continue
        if P["UseATRFilter"]:
            a = atr_now[i] / PIP
            if np.isnan(a) or a < P["ATR_MinPips"] or (P["ATR_MaxPips"] > 0 and a > P["ATR_MaxPips"]):
                i += 1; continue
        if P["UseEMA50DistFilter"]:
            dp = abs(c[i] - ema50_now[i]) / PIP
            if np.isnan(dp) or dp > P["MaxEMA50DistPips"]:
                i += 1; continue

        trend = 0
        if not (np.isnan(ema50_now[i]) or np.isnan(ema50_prev[i])):
            if h1_close[i] > ema50_now[i] and ema50_now[i] > ema50_prev[i]:
                trend = 1
            elif h1_close[i] < ema50_now[i] and ema50_now[i] < ema50_prev[i]:
                trend = -1
        if trend == 0:
            i += 1; continue

        b1, b2 = i - 1, i - 2
        if b2 < 1:
            i += 1; continue
        o1, c1, h1, l1 = o[b1], c[b1], h[b1], l[b1]
        o2, c2, l2b, h2b = o[b2], c[b2], l[b2], h[b2]
        e1, e2 = ema20[b1], ema20[b2]
        if np.isnan(e1) or np.isnan(e2):
            i += 1; continue
        body1, range1, body2 = abs(c1 - o1), h1 - l1, abs(c2 - o2)
        rv = rsi14[b1]
        if np.isnan(rv):
            i += 1; continue

        if trend == 1:
            if rv > P["RSI_OB"] or l2b > e2 or c1 <= e1 or c1 <= o1:
                i += 1; continue
            if (range1 > 0 and body1 / range1 < 0.6) or body1 <= body2:
                i += 1; continue
            direction = 1
        else:
            if rv < P["RSI_OS"] or h2b < e2 or c1 >= e1 or c1 >= o1:
                i += 1; continue
            if (range1 > 0 and body1 / range1 < 0.6) or body1 <= body2:
                i += 1; continue
            direction = -1

        if direction == 1:
            sref = l1
            for k in range(1, P["SL_SwingBars"] + 1):
                if l[b1 - k] < sref: sref = l[b1 - k]
            sl = sref - 2 * PIP
            entry = c[i]
            sld = (entry - sl) / PIP
        else:
            sref = h1
            for k in range(1, P["SL_SwingBars"] + 1):
                if h[b1 - k] > sref: sref = h[b1 - k]
            sl = sref + 2 * PIP
            entry = c[i]
            sld = (sl - entry) / PIP
        if sld < P["MinSL_Pips"] or sld > P["MaxSL_Pips"]:
            i += 1; continue
        tp = entry + direction * sld * PIP * P["MinRR"]

        rmult = 1.0
        if P["ReduceThursdayRisk"] and dow[i] == 4:
            rmult *= P["ThursdayRiskMult"]
        if P["UsePyramid"]:
            rmult *= P["L0_LotMult"] if streak == 0 else (P["L1_LotMult"] if streak == 1 else P["L2_LotMult"])
        lots = get_lot(sld * PIP, rmult)
        pos = {"dir": direction, "entry": entry, "sl": sl, "tp": tp, "lots": lots,
               "risk_dist": sld * PIP, "be_done": False, "open_i": i}
        last_rev, last_lvl, last_type = False, streak, direction
        daily_count += 1
        i += 1

    if pos is not None:
        xp = c[n - 1]
        pnl = (xp - pos["entry"]) / PIP * pos["dir"] * PIP_VALUE_PER_LOT * pos["lots"]
        balance += pnl
        if balance > peak: peak = balance
        dd = peak - balance
        if dd > max_dd: max_dd, max_dd_pct = dd, dd / peak * 100.0
        trades.append({"dt": ts[n - 1], "pnl": pnl, "balance": balance, "win": pnl > 0,
                       "level": 0 if last_rev else last_lvl, "is_rev": last_rev,
                       "year": ts[n - 1].year})

    return {"balance": balance, "net": balance - initial_balance,
            "max_dd": max_dd, "max_dd_pct": max_dd_pct, "trades": trades,
            "n_trades": len(trades)}


# ----------------------------------------------------------------------
if __name__ == "__main__":
    t0 = time.time()
    print("Loading M15 data...")
    df = load_mt4_csv("EURUSD15.csv")
    print(f"  {len(df)} bars {df['dt'].iloc[0]} -> {df['dt'].iloc[-1]}")
    print("Precomputing indicators...")
    D = precompute(df)
    print(f"  precompute done ({time.time()-t0:.1f}s)")
    P = default_params()
    res = run_backtest(D, P, pd.Timestamp("2010-01-01"), pd.Timestamp("2026-04-08"))
    print(f"\n=== RESULT ({time.time()-t0:.1f}s) ===")
    print(f"Net: ${res['net']:,.0f}  Balance: ${res['balance']:,.0f}")
    print(f"Max DD: ${res['max_dd']:,.0f} ({res['max_dd_pct']:.1f}%)  Trades: {res['n_trades']}")
    yr = {}
    for t in res["trades"]:
        yr[t["year"]] = yr.get(t["year"], 0.0) + t["pnl"]
    neg = 0
    print("\nPer-year net:")
    for y in sorted(yr):
        if yr[y] < 0: neg += 1
        print(f"  {y}: ${yr[y]:+,.0f}{'  <-- NEG' if yr[y] < 0 else ''}")
    print(f"\nNegative years: {neg}")
