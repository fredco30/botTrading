#!/usr/bin/env python3
"""Calibrate the Python engine against an MT4 Strategy Tester run.

The engine is only useful if it reproduces MT4 closely enough that a parameter
sweep in Python means something in the terminal. This script quantifies the gap
on the overlapping period and prints where the two disagree.

Usage:
    python3 calibrate_pullback_pyramid.py
    python3 calibrate_pullback_pyramid.py --mults 1.0 1.5 2.25 --show 20
    python3 calibrate_pullback_pyramid.py --infer-mults
"""

import argparse
import sys

import numpy as np

from engine import core, data, report
from engine.core import T_BALANCE, T_PNL
from engine.params import PYRAMID_MODES, Params

DEFAULT_M15 = "EURUSD15_cut.csv"
DEFAULT_H1 = "EURUSD60_cut.csv"
DEFAULT_REPORT = "resultats_martingale_EMAPullback3ans.txt"


def parse_args(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--m15", default=DEFAULT_M15)
    ap.add_argument("--h1", default=DEFAULT_H1)
    ap.add_argument("--report", default=DEFAULT_REPORT,
                    help="MT4 trade list to calibrate against")
    ap.add_argument("--mode", choices=sorted(PYRAMID_MODES), default=None,
                    help="named pyramid preset")
    ap.add_argument("--mults", nargs=3, type=float, metavar=("L0", "L1", "L2"),
                    default=None, help="explicit pyramid multipliers")
    ap.add_argument("--spread", type=float, default=2.0,
                    help="tester spread in points (5-digit)")
    ap.add_argument("--balance", type=float, default=10000.0)
    ap.add_argument("--start", default=None, help="YYYY.MM.DD")
    ap.add_argument("--end", default=None, help="YYYY.MM.DD")
    ap.add_argument("--show", type=int, default=10,
                    help="how many mismatching trades to print")
    ap.add_argument("--infer-mults", action="store_true",
                    help="recover L0/L1/L2 from the MT4 report and exit")
    ap.add_argument("--tolerance", type=float, default=None, metavar="PCT",
                    help="exit non-zero if |net error| exceeds PCT %% or if any "
                         "trade fails to match; use it as a regression test")
    return ap.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)

    mt4_trades = report.parse_mt4_report(args.report, args.balance)
    if not mt4_trades:
        print(f"no trades parsed from {args.report}", file=sys.stderr)
        return 1

    if args.infer_mults:
        brackets = report.infer_pyramid_multipliers(mt4_trades)
        print(f"Pyramid multipliers recovered from {args.report}")
        for lv in (0, 1, 2):
            lo, hi = brackets[lv]
            print(f"  L{lv}: [{lo:.4f} .. {hi:.4f}]  -> {round((lo + hi) / 2, 2)}")
        return 0

    params = Params(initial_balance=args.balance, spread_points=args.spread)
    if args.mode:
        params = params.with_mode(args.mode)
    if args.mults:
        params.l0_mult, params.l1_mult, params.l2_mult = args.mults

    md = data.build(args.m15, args.h1,
                    entry_ema_period=params.entry_ema_period,
                    rsi_period=params.rsi_period,
                    trend_ema_period=params.trend_ema_period,
                    trend_bars=params.trend_bars,
                    atr_period=params.atr_period)

    # Restrict to the window both sides actually cover. The M15 export is
    # capped at 65535 bars by MT4, so it usually ends well before the report.
    m15_start = report._fmt(md.ts[0])[:10]
    m15_end = report._fmt(md.ts[-1])[:10]
    start = args.start or max(m15_start, mt4_trades[0]["entry_time"][:10])
    end = args.end or min(m15_end, mt4_trades[-1]["exit_time"][:10])

    md = data.slice_period(md, start, end)
    window = [t for t in mt4_trades
              if start <= t["entry_time"][:10] <= end and t["exit_time"][:10] <= end]

    print("=" * 74)
    print(f"CALIBRATION  {args.m15} + {args.h1}  vs  {args.report}")
    print(f"window       {start} -> {end}   ({md.ts.size} M15 bars)")
    print(f"pyramid      L0={params.l0_mult} L1={params.l1_mult} L2={params.l2_mult}"
          f"   spread={args.spread} pts   risk={params.risk_percent}%")
    if md.n_unaligned:
        print(f"warning      {md.n_unaligned} M15 bars had no matching H1 bar")
    print("=" * 74)

    trades = core.run(md, params)
    recs = report.to_records(trades, md)

    eng_m = report.metrics(trades[:, T_PNL], trades[:, T_BALANCE], args.balance)
    mt4_pnl = np.array([t["pnl"] for t in window])
    mt4_bal = np.array([t["balance"] for t in window])
    # MT4 balances are absolute; rebase them so both sides start at `balance`.
    mt4_bal = args.balance + np.cumsum(mt4_pnl)
    mt4_m = report.metrics(mt4_pnl, mt4_bal, args.balance)

    print(f"\n{'metric':<12}{'ENGINE':>14}{'MT4':>14}{'delta':>14}")
    for key in ("trades", "net", "pf", "wr", "dd_pct", "final"):
        e, m = eng_m[key], mt4_m[key]
        if key == "trades":
            print(f"{key:<12}{e:>14d}{m:>14d}{e - m:>+14d}")
        else:
            rel = (e - m) / abs(m) * 100.0 if m else 0.0
            print(f"{key:<12}{e:>14.2f}{m:>14.2f}{rel:>+13.1f}%")

    matched, engine_only, mt4_only, diffs = report.compare(recs, window)
    n_ref = max(len(window), 1)
    print(f"\nmatched      {len(matched)}/{len(window)} MT4 trades "
          f"({len(matched) / n_ref * 100:.1f}%)")
    print(f"engine only  {len(engine_only)}")
    print(f"MT4 only     {len(mt4_only)}")

    if diffs:
        entry_err = np.array([abs(d["entry_pips"]) for d in diffs])
        sl_err = np.array([abs(d["sl_pips"]) for d in diffs])
        tp_err = np.array([abs(d["tp_pips"]) for d in diffs])
        lot_err = np.array([abs(d["lots"]) for d in diffs])
        same_exit = sum(d["same_exit"] for d in diffs)
        same_sign = sum(
            (r["pnl"] > 0) == (t["pnl"] > 0) for r, t in matched
        )
        print("\non matched trades:")
        print(f"  entry price  max {entry_err.max():.2f} pips   "
              f"mean {entry_err.mean():.3f}")
        print(f"  SL price     max {sl_err.max():.2f} pips   mean {sl_err.mean():.3f}")
        print(f"  TP price     max {tp_err.max():.2f} pips   mean {tp_err.mean():.3f}")
        print(f"  lot size     max {lot_err.max():.2f}        mean {lot_err.mean():.3f}")
        print(f"  same exit    {same_exit}/{len(diffs)} "
              f"({same_exit / len(diffs) * 100:.1f}%)")
        print(f"  same outcome {same_sign}/{len(matched)} "
              f"({same_sign / len(matched) * 100:.1f}%)")

        worst = sorted(zip(diffs, matched), key=lambda x: -abs(x[0]["pnl"]))
        shown = [w for w in worst if abs(w[0]["pnl"]) > 0.01][:args.show]
        if shown:
            print(f"\nlargest P&L divergences (engine - MT4):")
            print(f"  {'entry time':<18}{'dir':>5}{'eng pnl':>11}{'mt4 pnl':>11}"
                  f"{'delta':>11}{'eng lots':>10}{'mt4 lots':>10}")
            for d, (r, t) in shown:
                print(f"  {d['time']:<18}{'buy' if r['dir'] == 1 else 'sell':>5}"
                      f"{r['pnl']:>11.2f}{t['pnl']:>11.2f}{d['pnl']:>11.2f}"
                      f"{r['lots']:>10.2f}{t['lots']:>10.2f}")

    if args.show:
        if mt4_only:
            print(f"\nMT4 trades the engine missed (first {args.show}):")
            for t in mt4_only[:args.show]:
                print(f"  {t['entry_time']}  {'buy ' if t['dir'] == 1 else 'sell'}"
                      f"  lots {t['lots']:<6} entry {t['entry']:.5f}"
                      f"  sl {t['sl']:.5f}  pnl {t['pnl']:>9.2f}")
        if engine_only:
            print(f"\nEngine trades MT4 did not take (first {args.show}):")
            for r in engine_only[:args.show]:
                print(f"  {r['entry_time']}  {'buy ' if r['dir'] == 1 else 'sell'}"
                      f"  lots {r['lots']:<6} entry {r['entry']:.5f}"
                      f"  sl {r['sl']:.5f}  pnl {r['pnl']:>9.2f}")

    print("\nper level (engine):")
    print(f"  {'lvl':<5}{'n':>6}{'WR%':>9}{'net':>13}{'PF':>8}")
    for row in report.level_breakdown(trades):
        print(f"  L{row['level']:<4}{row['n']:>6}{row['wr']:>9.1f}"
              f"{row['net']:>13.2f}{row['pf']:>8.2f}")

    if args.tolerance is not None:
        net_err = abs(eng_m["net"] - mt4_m["net"]) / abs(mt4_m["net"]) * 100.0
        failures = []
        if net_err > args.tolerance:
            failures.append(f"net error {net_err:.3f}% > {args.tolerance}%")
        if engine_only or mt4_only:
            failures.append(
                f"{len(engine_only)} engine-only and {len(mt4_only)} MT4-only trades"
            )
        if failures:
            print("\nFAIL: " + "; ".join(failures))
            return 1
        print(f"\nPASS: net error {net_err:.3f}% within {args.tolerance}%, "
              f"all {len(matched)} trades matched")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
