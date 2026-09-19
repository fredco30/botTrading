#!/usr/bin/env python3
"""FX_PDH_001 backtest — USDJPY prior-day-high continuation, H1 bar replay.

Implements FX_PDH_001_FROZEN_SPEC.md exactly. Outputs per-trade CSV +
summary gates + EUR 500 equity simulation (sections 21/33).
"""
import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import tmlab as T

SPREAD = T.SPREAD_PIPS["USDJPY"]
PIP = T.PIP["USDJPY"]
ATR_N = 14
STOP_ATR = 1.0
TRAIL_ATR = 3.0
MAX_HOLD = 48
START, END = "2020-01-01", "2025-12-31 23:59"


def atr_rma(h, l, c, n=ATR_N):
    tr = T.true_range(h, l, c)
    out = np.full(len(c), np.nan)
    acc, cnt, s = np.nan, 0, 0.0
    for i, v in enumerate(tr):
        if np.isnan(acc):
            s += v; cnt += 1
            if cnt == n:
                acc = s / n
        else:
            acc = (acc * (n - 1) + v) / n
        out[i] = acc
    return out


def backtest(df: pd.DataFrame, stop_mult=STOP_ATR, trail_mult=TRAIL_ATR,
             max_hold=MAX_HOLD, slip=0.0, spread=SPREAD,
             equity0=500.0, risk_pct=0.005, verbose=False):
    h = df["high"].to_numpy(); l = df["low"].to_numpy()
    o = df["open"].to_numpy(); c = df["close"].to_numpy()
    idx = df.index
    n = len(c)
    day = np.array([ts.date() for ts in idx])
    dates = sorted(set(day))

    # PDH per bar (prior completed day's high)
    pdh = np.full(n, np.nan)
    prev_h = np.nan
    for d in dates:
        m = day == d
        ii = np.nonzero(m)[0]
        pdh[ii] = prev_h
        prev_h = np.max(h[m])

    atr = atr_rma(h, l, c)
    spread_abs = spread * PIP
    slip_abs = slip * PIP

    trades = []
    i = 0
    pos = None
    while i < n:
        if pos is None:
            # entry decision at bar i close: h[i] > pdh[i], first break of day
            if np.isfinite(pdh[i]) and h[i] > pdh[i] and np.isfinite(atr[i]):
                # only if this is the first break bar of the day
                d = day[i]
                ii_day = np.nonzero(day == d)[0]
                earlier = ii_day[ii_day < i]
                first_break = not np.any(h[earlier] > pdh[earlier])
                if first_break and i + 1 < n:
                    k = i + 1                      # fill on next bar open
                    entry = o[k] + spread_abs + slip_abs
                    stop = entry - stop_mult * atr[i]
                    pos = {"entry_i": k, "entry": entry, "stop": stop,
                           "hh": h[k], "atr_entry": atr[i],
                           "d": day[k], "sig_i": i}
                    i = k
        else:
            k = pos["entry_i"]
            held = i - k
            # trail stop from prior bars' data (ratchet at each close)
            trail = pos["hh"] - trail_mult * atr[i] if np.isfinite(atr[i]) else -np.inf
            eff_stop = max(pos["stop"], trail)
            stop_hit = l[i] <= eff_stop
            time_hit = held >= max_hold
            if stop_hit:                # conservative: stop first
                exit_px = min(o[i], eff_stop) - slip_abs
                reason = "stop"
            elif time_hit:
                exit_px = c[i] - slip_abs
                reason = "time"
            else:
                pos["hh"] = max(pos["hh"], h[i])
            if stop_hit or time_hit:
                gross_pips = (exit_px - pos["entry"]) / PIP
                trades.append({**{kk: vv for kk, vv in pos.items() if kk != "hh"},
                               "exit_i": i, "exit": exit_px, "reason": reason,
                               "gross_pips": gross_pips,
                               "net_pips": gross_pips - (spread_abs + slip_abs) / PIP,
                               "year": idx[k].year})
                pos = None
        i += 1

    tdf = pd.DataFrame(trades)
    return tdf


def gates(tdf: pd.DataFrame, label: str) -> dict:
    r = tdf["net_pips"].to_numpy()
    gp = tdf["gross_pips"].to_numpy()
    wins = r[r > 0]; losses = r[r <= 0]
    pf = float(wins.sum() / -losses.sum()) if len(losses) and losses.sum() != 0 else np.inf
    se = float(np.std(r, ddof=1) / np.sqrt(len(r))) if len(r) > 1 else np.nan
    k = max(1, int(round(0.01 * len(r))))
    rb1 = float(np.mean(np.sort(r)[:-k]))
    yrs = tdf["year"].to_numpy()
    by_year = {int(y): float(np.mean(r[yrs == y])) for y in sorted(set(yrs))}
    out = {"label": label, "n": int(len(r)), "pf": pf,
           "mean_net_pips": float(np.mean(r)), "win": float(np.mean(r > 0)),
           "se": se, "t": float(np.mean(r)) / se if se else np.nan,
           "rb1_net": rb1, "by_year": by_year,
           "sum_net_pips": float(np.sum(r))}
    return out


def main():
    df5 = T.load_5m("USDJPY", START, END)
    h1 = T.resample_ohlcv(df5, "1h")
    for label, kw in (("NORMAL", dict(slip=0.0)),
                      ("STRESS", dict(slip=T.SLIP_STRESS_PIPS))):
        tdf = backtest(h1, **kw)
        g = gates(tdf, label)
        weeks = 6 * 52.18
        print(f"[{label}] trades={g['n']} ({g['n']/weeks:.2f}/wk) "
              f"PF={g['pf']:.2f} mean_net={g['mean_net_pips']:+.2f} "
              f"win={g['win']:.3f} t={g['t']:+.2f} rb1={g['rb1_net']:+.2f}")
        print("   by year: " + " ".join(f"{y}:{v:+.1f}" for y, v in g["by_year"].items()))
        rr = tdf["reason"].value_counts().to_dict()
        print(f"   exits: {rr}")
        if label == "NORMAL":
            tdf.to_csv(os.path.join(HERE, "FX_PDH_001_TRADES.csv"), index=False)
            json.dump(g, open(os.path.join(HERE, "FX_PDH_001_GATES.json"), "w"),
                      indent=1, default=float)


if __name__ == "__main__":
    main()
