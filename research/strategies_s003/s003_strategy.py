#!/usr/bin/env python3
"""S003 — EURUSD P034 compression -> confirmed H1 breakout. Discovery only.

Reuses the EXACT P034 compression definition (phase2_lib.p034_compression):
5m bars, hi12 = rolling(144) high-low range, normalized by its rolling
30*288-bar median, event = run-start of comp < 0.60 (frozen threshold),
5000-bar warmup inherited. Sampled at H1 closes; HIGH/LOW frozen at the
compression H1 close. Discovery 2010-01-01..2019-01-01 UTC, nothing later
is ever loaded into the simulation.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
PARQUET = os.path.join(ROOT, "data_raw", "parquet")

PIP = 0.0001
RATIO = 0.60            # P034 frozen threshold (see S003_FROZEN_SPEC.md)
WIN = 144               # P034: 144 5m bars = 12h
MED_WIN = 30 * 288      # P034: 30-day rolling median of hi12
WARMUP = 5000           # P034 warmup, inherited
DISC_START = pd.Timestamp("2010-01-01", tz="UTC")
DISC_END = pd.Timestamp("2019-01-01", tz="UTC")
BREAKOUT_WINDOW = pd.Timedelta(hours=12)
TIME_EXIT = pd.Timedelta(hours=12)
TP_R = 1.5
COST_NORMAL, COST_STRESS = 2.0, 4.0


def load_5m_discovery():
    df = pd.read_parquet(os.path.join(PARQUET, "EURUSD_5m.parquet"))
    # keep pre-2010 bars ONLY for P034 warmup; simulation never sees them
    df = df[df.index < DISC_END]
    return df


def h1_bars(df5):
    """Causal H1 OHLC, bucket-START timestamp; bar known at ts+1h."""
    o = df5["open"].resample("1h").first()
    h = df5["high"].resample("1h").max()
    l = df5["low"].resample("1h").min()
    c = df5["close"].resample("1h").last()
    n = df5["n"].resample("1h").sum()
    df = pd.DataFrame({"open": o, "high": h, "low": l, "close": c, "n": n})
    return df.dropna(subset=["open", "high", "low", "close"])


def p034_compression_5m(df5):
    """Exact P034 quantities on the 5m series (causal, backward-looking)."""
    hi12 = df5["high"].rolling(WIN).max() - df5["low"].rolling(WIN).min()
    med = hi12.rolling(MED_WIN, min_periods=WARMUP).median()
    comp = hi12 / med
    return hi12, comp


def compression_events(df5, hi12, comp, h1):
    """H1-sampled P034 events: comp < RATIO at H1 close T (comp taken at the
    last 5m bar closed by T), run-start vs the previous H1 close. Returns
    list of (T, compression_high, compression_low) with P034's 144-bar
    trailing range as the frozen range."""
    pos = {ts: i for i, ts in enumerate(df5.index)}
    events, prev_flag = [], False
    for T, h1row in h1.iterrows():
        i = pos.get(T - pd.Timedelta(minutes=5))  # last 5m bar closed by T
        if i is None or i < max(WIN, WARMUP):
            prev_flag = False
            continue
        c = comp.iloc[i]
        flag = bool(np.isfinite(c) and c < RATIO)
        if flag and not prev_flag:
            j0 = i - WIN + 1
            events.append((T, float(df5["high"].iloc[j0:i + 1].max()),
                           float(df5["low"].iloc[j0:i + 1].min())))
        prev_flag = flag
    return events


def simulate(events, h1):
    """One position at a time; frozen entry/stop/target/time-exit rules."""
    idx = {ts: i for i, ts in enumerate(h1.index)}
    trades, skipped_overlap = [], 0
    in_pos_until = None  # entry bar ts of the open position

    for (T, chigh, clow) in events:
        e = idx[T] + 1  # first H1 bar after the compression close
        if in_pos_until is not None and T <= in_pos_until:
            skipped_overlap += 1
            continue
        # breakout search: H1 bars CLOSED within 12h after the compression
        signal = None
        while e < len(h1) and h1.index[e] + pd.Timedelta(hours=1) <= T + BREAKOUT_WINDOW:
            row = h1.iloc[e]
            if row.close > chigh:
                signal = (e, +1); break
            if row.close < clow:
                signal = (e, -1); break
            e += 1
        if signal is None:
            continue
        e, side = signal
        if e + 1 >= len(h1):
            continue  # next open unavailable in Discovery -> NO TRADE
        erow = h1.iloc[e + 1]
        entry = float(erow.open)
        stop = clow if side > 0 else chigh
        risk = (entry - stop) * side / PIP
        if risk <= 0:
            continue  # invalid trade
        target = entry + side * TP_R * risk * PIP
        gross_pips, exit_ts, reason = None, None, None
        for k in range(e + 1, len(h1)):
            row = h1.iloc[k]
            ts = h1.index[k]
            hit_stop = (row.low <= stop) if side > 0 else (row.high >= stop)
            hit_tgt = (row.high >= target) if side > 0 else (row.low <= target)
            if hit_stop:  # STOP-FIRST
                fill = stop
                if side > 0 and row.open < stop:  # adverse gap
                    fill = row.open
                elif side < 0 and row.open > stop:
                    fill = row.open
                gross_pips = (fill - entry) * side / PIP
                exit_ts, reason = ts, "STOP"
                break
            if hit_tgt:
                fill = target
                if side > 0 and row.open > target:  # favorable gap: cap at target
                    fill = target
                elif side < 0 and row.open < target:
                    fill = target
                gross_pips = (fill - entry) * side / PIP
                exit_ts, reason = ts, "TARGET"
                break
            if ts >= h1.index[e + 1] + TIME_EXIT:
                gross_pips = (row.open - entry) * side / PIP
                exit_ts, reason = ts, "TIME"
                break
        if gross_pips is None:  # frontier reached with position open
            last = h1.iloc[-1]
            gross_pips = (last.close - entry) * side / PIP
            exit_ts, reason = h1.index[-1], "FRONTIER"
        in_pos_until = exit_ts
        trades.append({"entry_ts": h1.index[e + 1], "exit_ts": exit_ts,
                       "side": side, "reason": reason, "risk_pips": risk,
                       "gross_pips": gross_pips,
                       "net_normal": gross_pips - COST_NORMAL,
                       "net_stress": gross_pips - COST_STRESS,
                       "comp_ts": T})
    return trades, skipped_overlap


def metrics(trades):
    t = pd.DataFrame(trades)
    if not len(t):
        return {"N_TRADES": 0}, t
    t["year"] = t["exit_ts"].dt.year
    net = t["net_normal"].to_numpy()
    gross = t["gross_pips"].to_numpy()
    wins, losses = net[net > 0], net[net <= 0]
    pf = wins.sum() / abs(losses.sum()) if losses.sum() != 0 else float("inf")
    eq = np.cumsum(net)
    dd = float((np.maximum.accumulate(eq) - eq).max()) if len(eq) else 0.0
    streak = best = 0
    for x in net:
        streak = streak + 1 if x <= 0 else 0
        best = max(best, streak)
    by_year = {}
    for y, g in t.groupby("year"):
        w = g.net_normal[g.net_normal > 0].sum()
        l = g.net_normal[g.net_normal <= 0].sum()
        by_year[int(y)] = {"N": int(len(g)), "NET_PIPS": round(float(g.net_normal.sum()), 2),
                           "MEAN_NET": round(float(g.net_normal.mean()), 3),
                           "PF": round(float(w / abs(l)), 3) if l != 0 else None}
    rng = np.random.default_rng(42)
    boots = np.array([rng.choice(net, len(net), replace=True).mean() for _ in range(2000)])
    # REMOVE_BEST_1_PERCENT: mean after dropping the top 1% of trades by net
    k = max(1, int(np.ceil(len(net) * 0.01)))
    rm1 = float(np.sort(net)[:-k].mean())
    return {
        "N_TRADES": int(len(t)),
        "TRADE_RATE": round(len(t) / len(t), 4),
        "TRADES_PER_YEAR": round(len(t) / 9.0, 2),
        "GROSS_MEAN_PIPS": round(float(gross.mean()), 3),
        "NET_NORMAL_MEAN_PIPS": round(float(net.mean()), 3),
        "NET_STRESS_MEAN_PIPS": round(float(t.net_stress.mean()), 3),
        "MEDIAN_NET": round(float(np.median(net)), 3),
        "WIN_RATE": round(float((net > 0).mean()), 4),
        "AVG_WIN": round(float(wins.mean()), 3) if len(wins) else 0.0,
        "AVG_LOSS": round(float(losses.mean()), 3) if len(losses) else 0.0,
        "PROFIT_FACTOR_NORMAL": round(float(pf), 3),
        "EXPECTANCY_R_NORMAL": round(float((net / t.risk_pips.to_numpy()).mean()), 4),
        "TOTAL_NET_PIPS": round(float(net.sum()), 2),
        "MAX_DRAWDOWN_PIPS": round(dd, 2),
        "MAX_CONSECUTIVE_LOSSES": int(best),
        "POSITIVE_YEARS": int(sum(1 for v in by_year.values() if v["NET_PIPS"] > 0)),
        "BY_YEAR": by_year,
        "REMOVE_BEST_1_PERCENT_NET_MEAN": round(rm1, 3),
        "CI95_MEAN_NET_NORMAL": [round(float(np.percentile(boots, 2.5)), 3),
                                 round(float(np.percentile(boots, 97.5)), 3)],
    }, t


def run():
    df5 = load_5m_discovery()
    hi12, comp = p034_compression_5m(df5)
    h1 = h1_bars(df5)
    events = compression_events(df5, hi12, comp, h1)
    trades, skipped = simulate(events, h1)
    m, tdf = metrics(trades)
    m["N_COMPRESSION_EVENTS"] = len(events)
    m["SKIPPED_OVERLAP_EVENTS"] = skipped
    return m, tdf, events, h1


if __name__ == "__main__":
    m, tdf, _, _ = run()
    import json
    print(json.dumps(m, indent=2))
    if len(tdf):
        tdf.to_csv(os.path.join(HERE, "s003_trades.csv"), index=False)
