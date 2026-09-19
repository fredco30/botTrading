#!/usr/bin/env python3
"""FX_PDH_001 STRICT — cross-pair replication runner (REPLICATION ONLY).

Uses the FROZEN strict engine (audit/replay_strict.py) unchanged: the
per-pair module constants (PAIR / PIP / SPREAD) are set before each run so
the identical code object executes for every pair. Only mechanical
instrument quantities vary (pip size, spread; see COST_ASSUMPTIONS.md).

Adds quote-currency-aware EUR pip valuation for the EUR500 practical gate
(USD / JPY / GBP quote currencies handled explicitly) plus MAX_DD_R and
best-year profit share reporting.

2026 sealed by the tmlab loader on every load.
"""
import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
LAB = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(LAB, "audit"))
sys.path.insert(0, LAB)
import replay_strict as R          # frozen strict engine (unchanged)
import tmlab as T

PAIRS = ["EURUSD", "GBPUSD", "USDJPY", "EURJPY", "GBPJPY", "EURGBP"]
PIP_SIZE = {"EURUSD": 1e-4, "GBPUSD": 1e-4, "EURGBP": 1e-4,
            "USDJPY": 1e-2, "EURJPY": 1e-2, "GBPJPY": 1e-2}
SPREAD = {"EURUSD": 0.6, "GBPUSD": 1.0, "USDJPY": 0.9,
          "EURJPY": 1.2, "GBPJPY": 2.0, "EURGBP": 0.8}   # pre-registered
SLIP_STRESS = 0.5
QUOTE = {"EURUSD": "USD", "GBPUSD": "USD", "USDJPY": "JPY",
         "EURJPY": "JPY", "GBPJPY": "JPY", "EURGBP": "GBP"}
BASE = {"EURUSD": "EUR", "GBPUSD": "GBP", "USDJPY": "USD",
        "EURJPY": "EUR", "GBPJPY": "GBP", "EURGBP": "EUR"}
N_WEEKS = 313.2                    # 2020-2025 trading weeks
CAPITAL, MIN_LOT, LOT_STEP, RISK = 500.0, 0.01, 0.01, 0.005


def conversion_closes():
    """Sealed reference closes for currency conversion (EURUSD/GBPUSD/USDJPY)."""
    out = {}
    for sym in ("EURUSD", "GBPUSD", "USDJPY"):
        df = T.load_5m(sym, R.START, R.END)
        out[sym] = (df.index, df["close"].to_numpy())
    return out


def pip_eur_series(sym, entry_times_idx, pair_close, conv):
    """EUR value of 1 pip per 0.01 lot, evaluated causally at each entry."""
    i_e, c_e = conv["EURUSD"]
    j_e = np.searchsorted(i_e, entry_times_idx, side="right") - 1
    notional = 1000.0                                   # units of base per 0.01 lot
    q = QUOTE[sym]
    if q == "USD":
        pip_usd = notional * PIP_SIZE[sym]              # quote is USD
        return pip_usd * c_e[j_e]
    if q == "JPY":
        i_j, c_j = conv["USDJPY"]
        j_j = np.searchsorted(i_j, entry_times_idx, side="right") - 1
        pip_usd = notional * PIP_SIZE[sym] / c_j[j_j]   # JPY -> USD
        return pip_usd * c_e[j_e]
    if q == "GBP":
        i_g, c_g = conv["GBPUSD"]
        j_g = np.searchsorted(i_g, entry_times_idx, side="right") - 1
        pip_usd = notional * PIP_SIZE[sym] * c_g[j_g]   # GBP -> USD
        return pip_usd * c_e[j_e]
    raise ValueError(q)


def collect(sym, conv, slip):
    """Run the frozen strict engine for one pair under a cost scenario."""
    R.PAIR = sym
    R.PIP = PIP_SIZE[sym]
    R.SPREAD = SPREAD[sym]
    D = R.prepare()
    tr = R.replay(D, strict=True, slip=slip)
    r = tr["net_pips"].to_numpy()
    if len(r) == 0:
        return {"pair": sym, "slip": slip, "n": 0}
    wins, losses = r[r > 0], r[r <= 0]
    pf = float(wins.sum() / -losses.sum()) if losses.sum() else float("inf")
    se = float(np.std(r, ddof=1) / np.sqrt(len(r)))
    k = max(1, int(round(0.01 * len(r))))
    rb1 = float(np.mean(np.sort(r)[:-k]))
    yrs = np.array([D["idx"][i].year for i in tr["entry_i"]])
    by_year = {int(y): float(np.mean(r[yrs == y])) for y in sorted(set(yrs))}
    ysum = {int(y): float(np.sum(r[yrs == y])) for y in sorted(set(yrs))}
    total = float(r.sum())
    best_y = max(ysum, key=ysum.get)
    # R-space drawdown
    stop_pips = R.STOP_ATR * D["atr"][tr["sig_i"]] / R.PIP
    rmul = r / stop_pips
    cum = np.cumsum(rmul)
    dd_r = float(np.max(np.maximum.accumulate(cum) - cum))
    # EUR500 gate inputs
    ei = tr["entry_i"].to_numpy()
    times = D["idx"][ei]
    pe = pip_eur_series(sym, times, D["c"], conv)
    eur = equity_gate(stop_pips, rmul, pe)
    out = {
        "pair": sym, "slip": slip, "n": int(len(r)),
        "trades_per_week": float(len(r) / N_WEEKS),
        "gross_pips_per_trade": float(np.mean(tr["gross_pips"] - slip)),
        "net_pips_per_trade": float(np.mean(r)),
        "pf": pf, "win_rate": float(np.mean(r > 0)),
        "expectancy_r": float(np.mean(rmul)),
        "t_stat": float(np.mean(r)) / se,
        "remove_best_1pct": rb1, "max_dd_r": dd_r,
        "total_net_pips": total,
        "best_year": int(best_y),
        "best_year_profit_share": float(ysum[best_y] / total) if total else None,
        "by_year": by_year,
        "year_sums": ysum,
        "median_stop_pips": float(np.median(stop_pips)),
        "p90_stop_pips": float(np.quantile(stop_pips, 0.9)),
        "eur500": eur,
        "exits": {kk: int(v) for kk, v in tr["reason"].value_counts().items()},
        "last_exit": str(D["idx"][int(tr["exit_i"].max())]),
    }
    return out


def equity_gate(stop_pips, rmul, pip_eur):
    """EUR500 practical gate at 0.5% target risk, floor-rounded lots."""
    lot = np.maximum(MIN_LOT, np.floor(
        (RISK * CAPITAL / (stop_pips * pip_eur * 100.0)) / LOT_STEP) * LOT_STEP)
    risk_eur = stop_pips * pip_eur * (lot / MIN_LOT)
    eq = CAPITAL + np.cumsum(rmul * risk_eur)
    peak = np.maximum.accumulate(eq)
    lot_med = float(np.median(lot))
    return {
        "risk_eur_at_0.01_median": float(np.median(stop_pips * pip_eur)),
        "risk_pct_500_median": float(100 * np.median(stop_pips * pip_eur) / CAPITAL),
        "risk_eur_at_0.01_p90": float(np.quantile(stop_pips * pip_eur, 0.9)),
        "risk_pct_500_p90": float(100 * np.quantile(stop_pips * pip_eur, 0.9) / CAPITAL),
        "target_lot_05_median": float(np.median(
            RISK * CAPITAL / (stop_pips * pip_eur * 100.0))),
        "rounded_lot_median": lot_med,
        "ending_equity": float(eq[-1]),
        "max_dd_percent": float(100 * np.max((peak - eq) / peak)),
        "max_dd_eur": float(np.max(peak - eq)),
        "min_lot_risk_pct_median": float(100 * np.median(stop_pips * pip_eur) / CAPITAL),
    }


def main():
    conv = conversion_closes()
    results = {}
    for sym in PAIRS:
        n_res = collect(sym, conv, slip=0.0)
        s_res = collect(sym, conv, slip=SLIP_STRESS)
        n_res["stress_net_pips_per_trade"] = s_res["net_pips_per_trade"]
        n_res["stress_pf"] = s_res["pf"]
        n_res["stress_remove_best_1pct"] = s_res["remove_best_1pct"]
        n_res["stress_by_year"] = s_res["by_year"]
        results[sym] = n_res
        print(f"{sym}: n={n_res['n']} PF={n_res['pf']:.3f} "
              f"net={n_res['net_pips_per_trade']:+.2f} "
              f"stress={n_res['stress_net_pips_per_trade']:+.2f} "
              f"t={n_res['t_stat']:+.2f} rb1={n_res['remove_best_1pct']:+.2f} "
              f"eq={n_res['eur500']['ending_equity']:.0f}", flush=True)
    with open(os.path.join(HERE, "CROSS_PAIR_RESULTS.json"), "w") as f:
        json.dump(results, f, indent=1, default=float)
    print("saved CROSS_PAIR_RESULTS.json")
    return results


if __name__ == "__main__":
    main()
