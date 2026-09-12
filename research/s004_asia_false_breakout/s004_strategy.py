#!/usr/bin/env python3
"""S004 — EURUSD Asia false breakout -> range reversion. Discovery only.

Frozen spec: research/s004_asia_false_breakout/S004_FROZEN_SPEC.md
5m bars, Europe/London tz. Asian range 00:00-07:00 London; breakout window
08:00-11:00; reentry within 60 min; entry next bar open; stop = breakout
extreme; target = range midpoint; time exit 12:00 London. Discovery
2010-01-01..2019-01-01 (UTC); nothing at or after 2019 is ever loaded.
"""
from __future__ import annotations

import json
import os

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
PARQUET = os.path.join(ROOT, "data_raw", "parquet")

PIP = 0.0001
LON = "Europe/London"
DISC_START = pd.Timestamp("2010-01-01", tz="UTC")
DISC_END = pd.Timestamp("2019-01-01", tz="UTC")   # exclusive; hard data cut
COST_NORMAL, COST_STRESS = 2.0, 4.0
REENTRY_MAX = pd.Timedelta(minutes=60)
BOOT_N, BOOT_SEED = 2000, 42


def load_5m_discovery():
    df = pd.read_parquet(os.path.join(PARQUET, "EURUSD_5m.parquet"))
    df = df[df.index < DISC_END]                 # never load 2019+
    df = df[df.index >= DISC_START]
    df = df[["open", "high", "low", "close"]].sort_index()
    return df


def simulate():
    df = load_5m_discovery()
    lon_date = pd.Series(df.index.tz_convert(LON).date, index=df.index)
    lon_time = df.index.tz_convert(LON)

    # per-day asian range (vectorized): bars in London [00:00, 07:00)
    lon_time = df.index.tz_convert(LON)
    t0 = pd.Timestamp("00:00").time(); t7 = pd.Timestamp("07:00").time()
    in_asia = (lon_time.time >= t0) & (lon_time.time < t7)
    asia = df[in_asia]
    rng = asia.groupby(asia.index.tz_convert(LON).date).agg(
        ah=("high", "max"), al=("low", "min"))
    df = df.join(rng, on=lon_date.rename("d"))

    o = df.open.values; h = df.high.values; l = df.low.values
    c = df.close.values
    dts = df.index
    lon_t = lon_time.time
    dates = lon_date.values
    ah = df.ah.values; al = df.al.values
    mid = (ah + al) / 2.0

    t8 = pd.Timestamp("08:00").time(); t11 = pd.Timestamp("11:00").time()
    t12 = pd.Timestamp("12:00").time()

    trades = []
    n_breakouts = 0
    n_false = 0
    n_days = len(np.unique(dates))

    i = 0
    n = len(df)
    while i < n:
        day = dates[i]
        done_day = False
        # scan breakout window [08:00, 11:00) of this day
        j = i
        while j < n and dates[j] == day and lon_t[j] < t8:
            j += 1
        # j = first bar of breakout window
        k = j
        brk = None   # (index, side)
        while k < n and dates[k] == day and lon_t[k] < t11:
            if ah[k] == ah[k] and al[k] == al[k]:  # range present
                if c[k] > ah[k]:
                    brk = (k, "LONG"); break
                if c[k] < al[k]:
                    brk = (k, "SHORT"); break
            k += 1
        if brk is None:
            # advance to next day
            while i < n and dates[i] == day:
                i += 1
            continue
        n_breakouts += 1
        bk, side = brk
        # reentry search: bars closed strictly after breakout bar,
        # within 60 min of breakout bar close
        reentry = None
        m = bk + 1
        while m < n and dates[m] == day and dts[m] < dts[bk] + pd.Timedelta(minutes=5) + REENTRY_MAX:
            if side == "LONG" and c[m] < ah[m]:
                reentry = m; break
            if side == "SHORT" and c[m] > al[m]:
                reentry = m; break
            m += 1
        if reentry is None:
            while i < n and dates[i] == day:
                i += 1
            continue
        n_false += 1
        rk = reentry
        # stop extreme: breakout bar .. reentry bar inclusive.
        # breakout LONG -> trade SHORT -> stop = highest high of the sequence
        if side == "LONG":
            stop = h[bk:rk + 1].max()
        else:
            stop = l[bk:rk + 1].min()
        # entry: open of bar after reentry
        ek = rk + 1
        if ek >= n or dates[ek] != day or lon_t[ek] >= t12:
            while i < n and dates[i] == day:
                i += 1
            continue
        entry = o[ek]
        target = mid[rk]  # midpoint known before entry (pre-07:00 data)
        if side == "LONG":
            direction = -1.0             # breakout LONG -> trade SHORT
            tgt_ok = target < entry      # midpoint must remain beyond entry
        else:
            direction = 1.0              # breakout SHORT -> trade LONG
            tgt_ok = target > entry
        risk_pips = abs(entry - stop) / PIP
        if risk_pips <= 0 or not tgt_ok:
            while i < n and dates[i] == day:
                i += 1
            continue
        # manage position from entry bar
        exit_price = None; exit_reason = None
        p = ek
        while p < n and dates[p] == day:
            # stop-first semantics within the bar
            if direction > 0:
                if l[p] <= stop:
                    # adverse gap: fill at real open
                    exit_price = o[p] if o[p] < stop else stop
                    exit_reason = "STOP"; break
                if h[p] >= target:
                    # favorable gap: credit capped at target
                    exit_price = target
                    exit_reason = "TARGET"; break
            else:
                if h[p] >= stop:
                    exit_price = o[p] if o[p] > stop else stop
                    exit_reason = "STOP"; break
                if l[p] <= target:
                    exit_price = target
                    exit_reason = "TARGET"; break
            p += 1
        if exit_price is None:
            # time exit at open of first bar >= 12:00 London
            while p < n and dates[p] == day and lon_t[p] < t12:
                p += 1
            if p >= n or dates[p] != day:
                p -= 1  # should not happen; last bar of day fallback
            exit_price = o[p]; exit_reason = "TIME"
        gross = direction * (exit_price - entry) / PIP
        trades.append({
            "date": day, "side": side, "entry": entry, "stop": stop,
            "target": target, "exit": exit_price, "reason": exit_reason,
            "risk_pips": risk_pips, "gross_pips": gross,
            "net_normal_pips": gross - COST_NORMAL,
            "net_stress_pips": gross - COST_STRESS,
        })
        done_day = True
        while i < n and dates[i] == day:
            i += 1
        _ = done_day
    return pd.DataFrame(trades), n_breakouts, n_false, n_days


def metrics(tr: pd.DataFrame, n_breakouts, n_false, n_days):
    out = {}
    out["N_BREAKOUTS"] = n_breakouts
    out["N_FALSE_BREAKOUTS"] = n_false
    out["FALSE_BREAKOUT_RATE"] = round(n_false / n_breakouts, 4) if n_breakouts else None
    out["N_TRADES"] = len(tr)
    years = 9.0
    out["TRADES_PER_YEAR"] = round(len(tr) / years, 2)
    out["GROSS_MEAN_PIPS"] = round(tr.gross_pips.mean(), 3)
    out["NET_NORMAL_MEAN_PIPS"] = round(tr.net_normal_pips.mean(), 3)
    out["NET_STRESS_MEAN_PIPS"] = round(tr.net_stress_pips.mean(), 3)
    out["MEDIAN_NET"] = round(tr.net_normal_pips.median(), 3)
    wr = (tr.net_normal_pips > 0).mean()
    out["WIN_RATE"] = round(wr, 4)
    wins = tr.net_normal_pips[tr.net_normal_pips > 0]
    losses = tr.net_normal_pips[tr.net_normal_pips <= 0]
    out["AVG_WIN"] = round(wins.mean(), 3) if len(wins) else 0.0
    out["AVG_LOSS"] = round(losses.mean(), 3) if len(losses) else 0.0
    pf = wins.sum() / abs(losses.sum()) if losses.sum() != 0 else float("inf")
    out["PROFIT_FACTOR_NORMAL"] = round(pf, 4)
    out["EXPECTANCY_R_NORMAL"] = round(tr.net_normal_pips.mean() / tr.risk_pips.mean(), 4)
    out["TOTAL_NET_PIPS"] = round(tr.net_normal_pips.sum(), 2)
    eq = tr.net_normal_pips.cumsum()
    out["MAX_DRAWDOWN_PIPS"] = round((eq - eq.cummax()).min(), 2)
    ml = mx = 0
    for v in tr.net_normal_pips:
        ml = ml + 1 if v <= 0 else 0
        mx = max(mx, ml)
    out["MAX_CONSECUTIVE_LOSSES"] = mx
    tr["year"] = pd.to_datetime(tr.date).dt.year
    by_year = {}
    for y, gy in tr.groupby("year"):
        w = gy.net_normal_pips[gy.net_normal_pips > 0].sum()
        lo = abs(gy.net_normal_pips[gy.net_normal_pips <= 0].sum())
        by_year[int(y)] = {
            "N": len(gy), "NET_PIPS": round(gy.net_normal_pips.sum(), 2),
            "MEAN_NET": round(gy.net_normal_pips.mean(), 3),
            "PF": round(w / lo, 3) if lo else None,
        }
    out["BY_YEAR"] = by_year
    out["POSITIVE_YEARS"] = sum(1 for v in by_year.values() if v["NET_PIPS"] > 0)
    s = np.sort(tr.net_normal_pips.values)
    k = max(1, int(np.ceil(len(s) * 0.01)))
    out["REMOVE_BEST_1_PERCENT_NET_MEAN"] = round(s[:-k].mean(), 3)
    rng = np.random.default_rng(BOOT_SEED)
    boots = np.array([rng.choice(tr.net_normal_pips.values, len(tr), replace=True).mean()
                      for _ in range(BOOT_N)])
    out["CI95_MEAN_NET_NORMAL"] = [round(np.percentile(boots, 2.5), 3),
                                   round(np.percentile(boots, 97.5), 3)]
    return out


def main():
    tr, nb, nf, ndays = simulate()
    if len(tr) == 0:
        print("NO TRADES"); return
    m = metrics(tr, nb, nf, ndays)
    gate = (m["NET_NORMAL_MEAN_PIPS"] > 2 and m["PROFIT_FACTOR_NORMAL"] >= 1.20
            and m["EXPECTANCY_R_NORMAL"] > 0.10 and m["POSITIVE_YEARS"] >= 6
            and m["REMOVE_BEST_1_PERCENT_NET_MEAN"] > 0 and m["TOTAL_NET_PIPS"] > 0)
    fail = (m["NET_NORMAL_MEAN_PIPS"] <= 0 or m["PROFIT_FACTOR_NORMAL"] <= 1.0
            or m["REMOVE_BEST_1_PERCENT_NET_MEAN"] <= 0)
    m["GATE_PROMISING"] = bool(gate)
    m["FAIL_FAST_REJECT"] = bool(fail)
    m["CLASSIFICATION"] = "S004_DISCOVERY_PROMISING" if gate else "S004_DISCOVERY_REJECT"
    m["REASON_STATS"] = {
        "N_BREAKOUTS_SCAN": nb, "N_DAYS_WITH_RANGE": ndays,
        "exit_reasons": tr.reason.value_counts().to_dict(),
        "side_counts": tr.side.value_counts().to_dict(),
    }
    tr.to_csv(os.path.join(HERE, "s004_trades.csv"), index=False)
    with open(os.path.join(HERE, "s004_results.json"), "w") as f:
        json.dump(m, f, indent=2)
    print(json.dumps(m, indent=2))


if __name__ == "__main__":
    main()
