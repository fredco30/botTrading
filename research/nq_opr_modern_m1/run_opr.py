#!/usr/bin/env python3
"""Run one OPR fold: Phase A raw event study + canonical strategy (frozen).

Usage: python run_opr.py DISCOVERY|VALIDATION|REPLICATION
Writes research/nq_opr_modern_m1/results/opr_<fold>.json
"""
import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import nq_lib as N  # noqa: E402
from nq_lib import ET  # noqa: E402

HERE = Path(__file__).parent
OUT = HERE / "results"
HORIZONS = (1, 3, 6, 12, 24)  # 5/15/30/60/120 min


def daily_atr14(df):
    """Causal 14-day ATR of RTH daily bars (prior days only, no same-day leak)."""
    local = df.index.tz_convert(ET)
    d = pd.Series(local.date, index=df.index)
    hm = local.hour * 100 + local.minute
    rth = df[(hm >= 930) & (hm < 1600)]
    g = rth.groupby(d[rth.index.map(lambda x: x)])
    daily = pd.DataFrame({"high": g["high"].max(), "low": g["low"].min(),
                          "close": g["close"].last()})
    tr = pd.concat([
        daily["high"] - daily["low"],
        (daily["high"] - daily["close"].shift()).abs(),
        (daily["low"] - daily["close"].shift()).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(14).mean().shift(1)  # usable only AFTER the day closes


def phase_a(df, events, fold_lo, fold_hi):
    """Raw phenomenon measurement (no entry optimization)."""
    atr = daily_atr14(df)
    atr_d = {d: v for d, v in atr.items()}
    rows = []
    for e in events:
        if not (fold_lo <= e.entry_ts < fold_hi):
            continue
        i = {ts: k for k, ts in enumerate(df.index)}.get(e.entry_ts)
        if i is None:
            continue
        win = df["open"].iloc[i:i + 25].to_numpy()
        h = df["high"].iloc[i:i + 25].to_numpy()
        l = df["low"].iloc[i:i + 25].to_numpy()
        if len(win) < 25:
            pad = 25 - len(win)
            win = np.concatenate([win, np.full(pad, np.nan)])
            h = np.concatenate([h, np.full(pad, np.nan)])
            l = np.concatenate([l, np.full(pad, np.nan)])
        fav = np.nanmax(np.maximum(e.side * (h - e.fill), e.side * (l - e.fill)))
        adv = np.nanmax(np.maximum(e.side * (e.fill - h), e.side * (e.fill - l)))
        a = atr_d.get(e.day, np.nan)
        rows.append({
            "day": str(e.day), "side": e.side, "variant": e.variant,
            "entry_ts": e.entry_ts, "fill": e.fill, "level": e.level,
            "break_dist_atr": abs(e.fill - e.level) / a if a and a == a else np.nan,
            "MFE_120m": float(fav), "MAE_120m": float(adv),
            **{f"ret_h{hh * 5}m": e.side * (float(df['open'].iloc[i + hh]) - e.fill)
               if i + hh < len(df) else np.nan for hh in HORIZONS},
        })
    return pd.DataFrame(rows)


def summarize_phase_a(pa: pd.DataFrame):
    out = {}
    if pa.empty:
        return {"N": 0}
    for hh in HORIZONS:
        col = f"ret_h{hh * 5}m"
        r = pa[col].dropna().to_numpy()
        if len(r) == 0:
            continue
        lm = (pa.loc[pa[col].notna(), "side"] == 1).to_numpy()
        yrs = pd.DatetimeIndex(pa.loc[pa[col].notna(), "entry_ts"]).tz_convert("UTC").tz_convert(N.ET).year
        out[col] = {
            "N": int(len(r)), "MEAN_PTS": round(float(np.mean(r)), 4),
            "MEDIAN_PTS": round(float(np.median(r)), 4),
            "WIN_RATE": round(float(np.mean(r > 0)), 4),
            "MFE_MEAN": round(float(pa.loc[pa[col].notna(), "MFE_120m"].mean()), 4),
            "MAE_MEAN": round(float(pa.loc[pa[col].notna(), "MAE_120m"].mean()), 4),
            "MEAN_LONG": round(float(np.mean(r[lm])), 4) if lm.any() else None,
            "MEAN_SHORT": round(float(np.mean(r[~lm])), 4) if (~lm).any() else None,
            "BY_YEAR": {int(y): round(float(np.mean(r[np.asarray(yrs == y)])), 4)
                        for y in sorted(set(yrs))},
        }
    bd = pa["break_dist_atr"].dropna()
    out["BREAK_DIST_ATR"] = {"MEAN": round(float(bd.mean()), 3),
                             "MEDIAN": round(float(bd.median()), 3)} if len(bd) else None
    out["N_EVENTS"] = int(len(pa))
    return out


def full_strategy_metrics(df, tf, events, fold_lo, fold_hi):
    m = N.trade_measurements(df, tf)
    net = m["net"].to_numpy()
    pf_pos = net[net > 0].sum()
    pf_neg = -net[net < 0].sum()
    sr = np.sort(net)[::-1]
    top = max(1, int(round(0.01 * len(net))))
    dd_pts, eq_end = N.drawdown_metrics(net)
    local_day = N._to_et(m["entry_ts"]).date
    per_day = m.groupby(local_day)["net"].sum()
    yrs = N._to_et(m["entry_ts"]).year
    rm = N.frequency_metrics(df, events, tf, fold_lo, fold_hi)
    out = {
        "TRADING_DAYS": rm["ELIGIBLE_SESSIONS"],
        "SIGNALS": rm["BREAKOUT_SESSIONS"],
        "RETEST_SESSIONS": rm["RETEST_TRADE_SESSIONS"],
        "TRADES": int(len(m)),
        "TRADES_PER_WEEK": round(rm["TRADES_PER_WEEK"], 3),
        "GROSS_POINTS_PER_TRADE": round(float(m["gross"].mean()), 4),
        "NET_POINTS_PER_TRADE": round(float(net.mean()), 4),
        "NET_TICKS_PER_TRADE": round(float(net.mean()) / N.TICK_SIZE, 2),
        "NET_USD_PER_CONTRACT": round(float(net.mean()) * N.POINT_VALUE_USD, 2),
        "PF": round(float(pf_pos / pf_neg), 4) if pf_neg > 0 else None,
        "EXPECTANCY_R": round(float(m["R_MULT"].mean()), 4) if m["R_MULT"].notna().any() else None,
        "WIN_RATE": round(float((net > 0).mean()), 4),
        "AVG_WIN": round(float(net[net > 0].mean()), 4) if (net > 0).any() else None,
        "MEDIAN_WIN": round(float(np.median(net[net > 0])), 4) if (net > 0).any() else None,
        "MAX_WIN": round(float(net.max()), 4),
        "AVG_LOSS": round(float(net[net <= 0].mean()), 4) if (net <= 0).any() else None,
        "MEDIAN_LOSS": round(float(np.median(net[net <= 0])), 4) if (net <= 0).any() else None,
        "MAX_LOSS": round(float(net.min()), 4),
        "MFE_MEAN": round(float(m["MFE"].mean()), 4),
        "MAE_MEAN": round(float(m["MAE"].mean()), 4),
        "PROFIT_CAPTURED_OVER_MFE": round(float((m["net"] / m["MFE"].replace(0, np.nan)).median()), 4),
        "REMOVE_BEST_1_PERCENT": round(float(sr[top:].mean()), 4),
        "MAX_DRAWDOWN_POINTS": round(dd_pts, 3),
        "MAX_DRAWDOWN_USD_1_NQ": round(dd_pts * N.POINT_VALUE_USD, 2),
        "WORST_DAY_USD": round(float(per_day.min()) * N.POINT_VALUE_USD, 2),
        "WORST_TRADE_USD": round(float(net.min()) * N.POINT_VALUE_USD, 2),
        "LONG_N": int((m["side"] == 1).sum()),
        "SHORT_N": int((m["side"] == -1).sum()),
        "LONG_NET_MEAN": round(float(m.loc[m["side"] == 1, "net"].mean()), 4) if (m["side"] == 1).any() else None,
        "SHORT_NET_MEAN": round(float(m.loc[m["side"] == -1, "net"].mean()), 4) if (m["side"] == -1).any() else None,
        "EXIT_REASON_BREAKDOWN": {k: int(v) for k, v in m["exit_reason"].value_counts().items()},
        "BY_YEAR_NET_MEAN_PTS": {int(y): round(float(m.loc[np.asarray(yrs) == y, "net"].mean()), 4)
                                 for y in sorted(set(yrs))},
        "BY_YEAR_N": {int(y): int((np.asarray(yrs) == y).sum()) for y in sorted(set(yrs))},
        "HOLD_MEDIAN_MIN": round(float(m["HOLD_MIN"].median()), 1),
    }
    return out


def main() -> int:
    fold = sys.argv[1]
    lo, hi = N.FOLDS[fold]
    df = N.load_5m()
    OUT.mkdir(exist_ok=True)
    results = {"FOLD": fold, "WINDOW": [str(lo), str(hi)],
               "DATA_ROWS_5M": int(len(df)),
               "DATA_SPAN": [str(df.index[0]), str(df.index[-1])]}
    for variant in ("LEVEL", "VWAP"):
        name = {"LEVEL": "P000A_LEVEL", "VWAP": "P000B_VWAP"}[variant]
        events = N.split_events_by_entry(N.detect_us_events(df, variant=variant), fold)
        res = {"N_EVENTS": len(events)}
        pa = phase_a(df, events, lo, hi)
        res["PHASE_A"] = summarize_phase_a(pa)
        strat = {}
        for cost_name, cost in N.NQ_COSTS.items():
            tf = N.trades_frame(N.simulate_strategy(df, events, cost, N.ET, 1600))
            strat[cost_name] = full_strategy_metrics(df, tf, events, lo, hi) \
                if not tf.empty else {"N": 0}
        res["STRATEGY"] = strat
        results[name] = res
        print(fold, name, "events:", len(events),
              "NORMAL net/trade:", strat["NORMAL"].get("NET_POINTS_PER_TRADE"),
              "PF:", strat["NORMAL"].get("PF"))
    out = OUT / f"opr_{fold.lower()}.json"
    out.write_text(json.dumps(results, indent=1, default=str))
    print("WROTE", out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
