#!/usr/bin/env python3
"""Full dossier for one pair + config: the checks to run before touching MT4.

A grid search returns the config that scored best on the data it was given.
That is not the same as an edge. This prints the four things that separate the
two:

  1. year by year - one lucky year carrying the whole curve is the classic
     overfit signature, and a headline PF hides it completely
  2. in-sample vs out-of-sample halves, each re-run from a flat balance
  3. the L0 / L1 / L2 breakdown - the pyramid only pays if L1 is genuinely
     stronger than L0, otherwise it is just leverage
  4. the share of trades decided by the intrabar model rather than by data

Usage:
    python3 validate_pair.py --pair GBPUSD --set max_ema50_dist_pips=30 ...
    python3 validate_pair.py --pair USDJPY --champion
"""

import argparse

import numpy as np

from engine import core, data, report
from engine.core import T_BALANCE, T_CONFLICT, T_LEVEL, T_PNL
from engine.params import CHAMPION_OVERRIDES, PAIR_DATA, PAIR_PRESETS, Params


def parse_value(text):
    low = text.strip().lower()
    if low in ("true", "false"):
        return low == "true"
    try:
        return int(text) if "." not in text and "e" not in low else float(text)
    except ValueError:
        return text.strip()


def parse_args(argv=None):
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pair", default="EURUSD", choices=sorted(PAIR_PRESETS))
    ap.add_argument("--champion", action="store_true",
                    help="apply the tuned champion overrides for this pair")
    ap.add_argument("--no-pyramid", action="store_true")
    ap.add_argument("--set", action="append", default=[], dest="overrides",
                    metavar="NAME=VALUE")
    ap.add_argument("--m15", default=None, help="override the preset M15 CSV")
    ap.add_argument("--h1", default=None, help="override the preset H1 CSV")
    ap.add_argument("--balance", type=float, default=10000.0)
    ap.add_argument("--split", default=None, help="walk-forward cut YYYY.MM.DD")
    return ap.parse_args(argv)


def run_window(md, params, start=None, end=None):
    """Metrics for one window, always restarted from a flat balance."""
    sub = data.slice_period(md, start, end) if (start or end) else md
    trades = core.run(sub, params)
    if trades.shape[0] == 0:
        return None, trades
    m = report.metrics(trades[:, T_PNL], trades[:, T_BALANCE],
                       params.initial_balance)
    m["conflict"] = int(trades[:, T_CONFLICT].sum())
    return m, trades


def main(argv=None):
    args = parse_args(argv)

    params = Params.for_pair(args.pair, initial_balance=args.balance)
    if args.champion:
        for k, v in CHAMPION_OVERRIDES[args.pair].items():
            setattr(params, k, v)
    if args.no_pyramid:
        params.use_pyramid = False
    for spec in args.overrides:
        name, _, raw = spec.partition("=")
        name = name.strip()
        if not hasattr(params, name):
            raise SystemExit(f"unknown parameter '{name}'")
        setattr(params, name, parse_value(raw))

    m15_path = args.m15 or PAIR_DATA[args.pair][0]
    h1_path = args.h1 or PAIR_DATA[args.pair][1]
    md = data.build(m15_path, h1_path,
                    entry_ema_period=params.entry_ema_period,
                    rsi_period=params.rsi_period,
                    trend_ema_period=params.trend_ema_period,
                    trend_bars=params.trend_bars,
                    atr_period=params.atr_period)

    first, last = report.fmt_ts(md.ts[0])[:10], report.fmt_ts(md.ts[-1])[:10]
    pyr = (f"L0={params.l0_mult} L1={params.l1_mult} L2={params.l2_mult}"
           if params.use_pyramid else "OFF")

    print("=" * 78)
    print(f"{args.pair}   {first} -> {last}   ({md.ts.size} M15 bars)")
    print(f"pyramid {pyr}   risk {params.risk_percent}%   "
          f"spread {params.spread_points} pts")
    print(f"SL {params.min_sl_pips:g}-{params.max_sl_pips:g}  RR {params.min_rr:g}  "
          f"BE {params.be_trigger_r:g}R  EMA50dist {params.max_ema50_dist_pips:g}  "
          f"swing {params.sl_swing_bars}  RSI {params.rsi_os:g}/{params.rsi_ob:g}")
    print("=" * 78)

    full, trades = run_window(md, params)
    if full is None:
        print("no trades")
        return 1

    print(f"\nFULL   {full['trades']:>4} trades   net {full['net']:>10,.0f}   "
          f"PF {full['pf']:.2f}   WR {full['wr']:.1f}%   DD {full['dd_pct']:.1f}%   "
          f"R/DD {full['ret_dd']:.1f}")
    amb = full["conflict"] / full["trades"] * 100.0
    print(f"       ambiguous SL+TP bars: {full['conflict']}/{full['trades']} "
          f"({amb:.1f}%)")

    # --- walk-forward halves ---
    cut = args.split or report.fmt_ts(md.ts[md.ts.size // 2])[:10]
    is_m, _ = run_window(md, params, None, cut)
    oos_m, _ = run_window(md, params, cut, None)
    print(f"\nWALK-FORWARD (each half restarted from {args.balance:,.0f})")
    print(f"  {'window':<24}{'n':>5}{'net':>11}{'PF':>7}{'WR%':>7}{'DD%':>7}")
    for label, m in ((f"IS   {first} -> {cut}", is_m),
                     (f"OOS  {cut} -> {last}", oos_m)):
        if m:
            print(f"  {label:<24}{m['trades']:>5}{m['net']:>11,.0f}"
                  f"{m['pf']:>7.2f}{m['wr']:>7.1f}{m['dd_pct']:>7.1f}")

    # --- year by year ---
    years = sorted({report.fmt_ts(t)[:4] for t in md.ts})
    print(f"\nYEAR BY YEAR (each year restarted from {args.balance:,.0f})")
    print(f"  {'year':<6}{'n':>5}{'net':>11}{'PF':>7}{'WR%':>7}{'DD%':>7}")
    pos = neg = 0
    for y in years:
        try:
            m, _ = run_window(md, params, f"{y}.01.01", f"{y}.12.31")
        except ValueError:
            continue
        if m is None or m["trades"] == 0:
            print(f"  {y:<6}{0:>5}{'-':>11}")
            continue
        pos, neg = (pos + 1, neg) if m["net"] > 0 else (pos, neg + 1)
        print(f"  {y:<6}{m['trades']:>5}{m['net']:>11,.0f}{m['pf']:>7.2f}"
              f"{m['wr']:>7.1f}{m['dd_pct']:>7.1f}")
    print(f"  -> {pos} positive / {neg} negative")

    # --- pyramid levels ---
    if params.use_pyramid:
        print("\nPYRAMID LEVELS (full period)")
        print(f"  {'lvl':<5}{'n':>5}{'WR%':>8}{'net':>12}{'PF':>7}{'share':>8}")
        rows = report.level_breakdown(trades)
        total = sum(abs(r["net"]) for r in rows) or 1.0
        for r in rows:
            print(f"  L{r['level']:<4}{r['n']:>5}{r['wr']:>8.1f}{r['net']:>12,.0f}"
                  f"{r['pf']:>7.2f}{r['net'] / total * 100:>7.0f}%")
        lv = {r["level"]: r for r in rows}
        if 0 in lv and 1 in lv:
            verdict = ("L1 stronger than L0 - the pyramid is amplifying a real "
                       "clustering effect"
                       if lv[1]["pf"] > lv[0]["pf"] else
                       "L1 NOT stronger than L0 - the pyramid is adding leverage, "
                       "not edge")
            print(f"  -> {verdict}")

    # --- direction split, a cheap sanity check on swap-driven bias ---
    dirs = trades[:, core.T_DIR]
    for d, label in ((1, "long"), (-1, "short")):
        sel = trades[dirs == d]
        if sel.shape[0]:
            pnl = sel[:, T_PNL]
            win = pnl[pnl > 0].sum()
            loss = -pnl[pnl < 0].sum()
            print(f"\n{label:<6}{sel.shape[0]:>4} trades  net {pnl.sum():>10,.0f}  "
                  f"PF {win / loss if loss else float('inf'):.2f}  "
                  f"WR {(pnl > 0).sum() / len(pnl) * 100:.1f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
