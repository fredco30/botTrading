#!/usr/bin/env python3
"""FX_PDH_001 — STRICT CAUSAL REPLAY (the only 2026-eligible version).

Corrects the two causal/execution defects of the original frozen replay
(found in the independent audit, 2026-09-19):

  D1  the entry H1 bar was never checked for an initial-stop touch;
  D2  the trailing stop used the CURRENT bar's ATR14 (intra-bar lookahead —
      a bar's own range set its own stop).

Strict rules (see ../candidates/FX_PDH_001/FROZEN_SPEC_STRICT_V1.md):
  * initial stop = entry_fill - 1.0 * ATR14(signal bar), active from the
    entry fill; the entry bar CAN stop out;
  * trailing level for bar i = max(high since entry .. bar i-1)
                                 - 3.0 * ATR14(bar i-1)
    (ATR14(i-1) is fully known at the close of bar i-1);
  * conservative intrabar fills: stop fills at min(open, stop_level) - slip
    (if the bar opens below the stop level, the worse open price is taken);
  * a bar that exits a position cannot also trigger a new entry;
  * one position at a time, one first-break signal per day, no pyramiding.

Parameters are FROZEN: stop 1.0 / trail 3.0 / hold 48 H1 bars, spread
0.9 pip (NORMAL) or 0.9+2x0.5 (STRESS). No tuning is permitted here.
"""
import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
LAB = os.path.dirname(HERE)
sys.path.insert(0, LAB)
import tmlab as T

PAIR = "USDJPY"
PIP = 1e-2                       # USDJPY pip = 0.01 JPY
SPREAD = 0.9                     # pips, NORMAL
SLIP_STRESS = 0.5                # pips per side, STRESS scenario
STOP_ATR, TRAIL_ATR, MAX_HOLD = 1.0, 3.0, 48
ATR_N = 14
CAPITAL, MIN_LOT, LOT_STEP = 500.0, 0.01, 0.01
START, END = "2020-01-01", "2025-12-31 23:59"


def atr14_rma(h: np.ndarray, l: np.ndarray, c: np.ndarray) -> np.ndarray:
    """Wilder RMA ATR14 on completed bars; atr[i] known at close of bar i."""
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


def prepare():
    """Load sealed data, build H1 frame, PDH, ATR, first-break signals."""
    df5 = T.load_5m(PAIR, START, END)          # hard 2026 seal inside
    h1 = T.resample_ohlcv(df5, "1h")
    o = h1["open"].to_numpy(); h = h1["high"].to_numpy()
    l = h1["low"].to_numpy(); c = h1["close"].to_numpy()
    idx = h1.index
    day = np.array([ts.date() for ts in idx])
    pdh = np.full(len(c), np.nan)
    prev = np.nan
    for d in sorted(set(day)):
        m = day == d
        ii = np.nonzero(m)[0]
        pdh[ii] = prev                          # prior COMPLETED day's high
        prev = np.max(h[m])
    sig = []
    for d in sorted(set(day)):
        ii = np.nonzero(day == d)[0]
        if len(ii) < 4 or not np.isfinite(pdh[ii[0]]):
            continue
        brk = ii[h[ii] > pdh[ii]]               # first break touch of the day
        if len(brk):
            sig.append(brk[0])
    return dict(o=o, h=h, l=l, c=c, idx=idx, day=day,
                atr=atr14_rma(h, l, c),
                sig=np.array(sig, "int64"))


def replay(D: dict, strict: bool = True, slip: float = 0.0) -> pd.DataFrame:
    """One-position replay. strict=True implements the causal corrections;
    strict=False reproduces the ORIGINAL frozen 2020-2025 replay (entry bar
    not stop-checked, trail uses current-bar ATR) for audit comparison."""
    o, h, l, c = D["o"], D["h"], D["l"], D["c"]
    atr, sig, n = D["atr"], D["sig"], len(c)
    spread_abs = SPREAD * PIP
    slip_abs = slip * PIP
    trades = []
    pos = None
    for i in range(n):
        if pos is not None:
            k = pos["k"]
            if i == k:
                if strict:                       # D1: entry bar can stop out
                    if l[i] <= pos["stop"]:
                        px = min(o[i], pos["stop"]) - slip_abs
                        trades.append((k, i, px, "stop", pos["sig"]))
                        pos = None
                        continue
                continue                         # original: no check at all
            hh = pos["hh"]
            a = atr[i - 1] if strict else atr[i]  # D2
            eff_stop = pos["stop"]
            if np.isfinite(a):
                eff_stop = max(pos["stop"], hh - TRAIL_ATR * a)
            if l[i] <= eff_stop:
                px = min(o[i], eff_stop) - slip_abs
                trades.append((k, i, px, "stop", pos["sig"]))
                pos = None
                continue                          # no same-bar re-entry
            if (i - k) >= MAX_HOLD:
                trades.append((k, i, c[i] - slip_abs, "time", pos["sig"]))
                pos = None
                continue
            pos["hh"] = max(pos["hh"], h[i])
        if pos is None:
            j = np.searchsorted(sig, i, side="right") - 1
            if j >= 0 and sig[j] == i and i + 1 < n and np.isfinite(atr[i]):
                k = i + 1                         # fill at next bar open
                entry = o[k] + spread_abs + slip_abs
                pos = {"k": k, "entry": entry,
                       "stop": entry - STOP_ATR * atr[i],   # known pre-entry
                       "hh": h[k], "sig": i}
    return pd.DataFrame(trades, columns=["entry_i", "exit_i", "exit_px",
                                         "reason", "sig_i"]).assign(
        # exit_px already carries the exit-side slip; the entry-side slip is
        # charged once more below so stress = spread + 2 x slip (per frozen spec)
        gross_pips=lambda d: (d["exit_px"] - o[d["entry_i"]]) / PIP,
        net_pips=lambda d: d["gross_pips"] - SPREAD - slip,
    )


def equity_sim(tr: pd.DataFrame, D: dict, risk: float = 0.005) -> dict:
    """EUR 500 equity path with realistic floor-rounded lots (section 33)."""
    o, c, idx = D["o"], D["c"], D["idx"]
    eur5 = T.load_5m("EURUSD", START, END)
    euri, eurc = eur5.index, eur5["close"].to_numpy()
    ei = tr["entry_i"].to_numpy().astype(int)
    stop_pips = STOP_ATR * D["atr"][tr["sig_i"].to_numpy().astype(int)] / PIP
    pip_eur = 1000.0 * PIP / c[ei] * eurc[np.searchsorted(euri, idx[ei],
                                                          side="right") - 1]
    lots = np.maximum(MIN_LOT, np.floor(
        (risk * CAPITAL / (stop_pips * pip_eur * 100.0)) / LOT_STEP) * LOT_STEP)
    r_mult = tr["net_pips"].to_numpy() / stop_pips
    pnl = r_mult * stop_pips * pip_eur * (lots / MIN_LOT)
    eq = CAPITAL + np.cumsum(pnl)
    peak = np.maximum.accumulate(eq)
    return {"ending_equity": float(eq[-1]),
            "max_dd_percent": float(100 * np.max((peak - eq) / peak)),
            "max_dd_eur": float(np.max(peak - eq))}


def run(slip: float = 0.0) -> dict:
    D = prepare()
    tr = replay(D, strict=True, slip=slip)
    r = tr["net_pips"].to_numpy()
    wins, losses = r[r > 0], r[r <= 0]
    pf = float(wins.sum() / -losses.sum())
    se = float(np.std(r, ddof=1) / np.sqrt(len(r)))
    k = max(1, int(round(0.01 * len(r))))
    rb1 = float(np.mean(np.sort(r)[:-k]))
    yrs = np.array([D["idx"][i].year for i in tr["entry_i"]])
    by_year = {int(y): float(np.mean(r[yrs == y])) for y in sorted(set(yrs))}
    ysum = {int(y): float(np.sum(r[yrs == y])) for y in sorted(set(yrs))}
    eq = equity_sim(tr, D)
    return {
        "params": {"pair": PAIR, "side": "LONG", "tf": "H1",
                   "stop_atr": STOP_ATR, "trail_atr": TRAIL_ATR,
                   "max_hold_bars": MAX_HOLD, "spread_pips": SPREAD,
                   "slip_pips_per_side": slip, "period": "2020-2025"},
        "n": int(len(r)), "pf": pf,
        "net_pips_per_trade": float(np.mean(r)),
        "expectancy_r": float(np.mean(r / (STOP_ATR * D["atr"][tr["sig_i"]] / PIP))),
        "win_rate": float(np.mean(r > 0)),
        "t_stat": float(np.mean(r)) / se,
        "remove_best_1pct": rb1,
        "trades_per_week": float(len(r) / 313.2),
        "by_year": by_year,
        "y2022_profit_share_pct": float(100 * ysum.get(2022, 0.0) / r.sum()),
        "equity_500_at_05pct": eq,
        "exits": {k2: int(v) for k2, v in tr["reason"].value_counts().items()},
        "last_exit": str(D["idx"][int(tr["exit_i"].max())]),
        "no_2026": bool(D["idx"][int(tr["exit_i"].max())].year <= 2025),
    }


if __name__ == "__main__":
    normal = run(slip=0.0)
    stress = run(slip=SLIP_STRESS)
    normal["stress_net_pips_per_trade"] = stress["net_pips_per_trade"]
    normal["stress_pf"] = stress["pf"]
    normal["stress_remove_best_1pct"] = stress["remove_best_1pct"]
    normal["stress_by_year"] = stress["by_year"]
    out = os.path.join(HERE, "FX_PDH_001_STRICT_RESULTS.json")
    with open(out, "w") as f:
        json.dump(normal, f, indent=1, default=float)
    print(json.dumps(normal, indent=1, default=float))
    print(f"\nsaved {out}")
