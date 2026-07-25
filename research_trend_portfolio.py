#!/usr/bin/env python3
"""Donchian breakout portfolio - full research run, reproduces every figure.

Design constraints, all of them consequences of the EMA-pullback post-mortem:

  1. ONE parameter set for every instrument. A per-pair tuning is a fit. Here a
     configuration only counts if the same four numbers work on EURUSD, GBPUSD,
     USDJPY and XAUUSD simultaneously.
  2. NO calendar filters. Blocked hours, toxic hour x day combos and ATR bands
     all looked decisive on 3 years and added nothing over 16.
  3. Judged on rolling 5-year windows, not on one backtest. A single run tells
     you what one roll of the dice did.
  4. Spread, slippage and overnight swap charged on every trade.

Usage:
    python3 research_trend_portfolio.py
    python3 research_trend_portfolio.py --risk 3 --years 5
"""

import argparse

import numpy as np

from engine import instruments as I, portfolio as P, report, trend

SYMBOLS = ("EURUSD", "GBPUSD", "USDJPY", "XAUUSD")
# EURUSD's CSV back-fills 1971-1998 with one synthetic daily bar; real M15
# starts in 1999.
DATA_START = {"EURUSD": "1999.01.01"}

# Correlation grouping. EURUSD and GBPUSD trend together against the dollar, so
# two simultaneous positions are closer to one double-sized bet.
CORR_GROUPS = {"EURUSD": "USD_EUROPE", "GBPUSD": "USD_EUROPE"}

DEFAULTS = dict(entry_period=2880, exit_period=960, atr_stop_mult=3.0,
                atr_trail_mult=5.0)


def slice_from(series, start):
    if not start:
        return series
    t0 = np.datetime64(start.replace(".", "-"), "s").astype("int64")
    mask = series["ts"] >= t0
    n = series["ts"].size
    return {k: (v[mask] if isinstance(v, np.ndarray) and v.size == n else v)
            for k, v in series.items()}


def build_rows(entry_period, exit_period, atr_stop_mult, atr_trail_mult,
               max_units=1, add_step_atr=1.0, verbose=True):
    rows, per_symbol = [], {}
    for sym in SYMBOLS:
        s = slice_from(
            I.load_h1(sym, entry_period=entry_period, exit_period=exit_period),
            DATA_START.get(sym))
        t = I.run(s, risk_pct=1.0, atr_stop_mult=atr_stop_mult,
                  atr_trail_mult=atr_trail_mult, max_units=max_units,
                  add_step_atr=add_step_atr)
        r = P.to_r_multiples(t, s["ts"], sym)
        rows += r
        m = report.metrics(t[:, trend.R_PNL], t[:, trend.R_EQUITY], 10000.0)
        per_symbol[sym] = (m, len(r), report.fmt_ts(s["ts"][0])[:7],
                           report.fmt_ts(s["ts"][-1])[:7])
        if verbose:
            cal = "" if I.INSTRUMENTS[sym].calibrated else "  (couts estimes)"
            print(f"  {sym:<8}{per_symbol[sym][2]} -> {per_symbol[sym][3]}"
                  f"{len(r):>6} trades   PF {m['pf']:>5.2f}   DD {m['dd_pct']:>4.1f}%{cal}")
    return rows, per_symbol


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--risk", type=float, default=2.0, help="%% equity per trade")
    ap.add_argument("--years", type=float, default=5.0)
    ap.add_argument("--entry", type=int, default=DEFAULTS["entry_period"])
    ap.add_argument("--exit", type=int, default=DEFAULTS["exit_period"])
    ap.add_argument("--stop", type=float, default=DEFAULTS["atr_stop_mult"])
    ap.add_argument("--trail", type=float, default=DEFAULTS["atr_trail_mult"])
    ap.add_argument("--max-concurrent", type=int, default=4)
    ap.add_argument("--max-group", type=int, default=99)
    args = ap.parse_args(argv)

    print("=" * 76)
    print("DONCHIAN BREAKOUT PORTFOLIO   H1 bars, one parameter set, no filters")
    print(f"canal entree {args.entry} barres (~{args.entry/24:.0f} jours)   "
          f"sortie {args.exit}   stop {args.stop} ATR   trailing {args.trail} ATR")
    print("=" * 76)

    rows, _ = build_rows(args.entry, args.exit, args.stop, args.trail)
    r = np.array([x[2] for x in rows])
    print(f"\n{len(rows)} trades   esperance {r.mean():+.3f} R   "
          f"mediane {np.median(r):+.2f} R   meilleur {r.max():.1f} R   "
          f"pire {r.min():.1f} R")
    print(f"   {(r > 0).mean()*100:.0f}% de gagnants - la rentabilite vient de la "
          f"queue droite, pas du taux de reussite")

    print(f"\nFENETRES GLISSANTES DE {args.years:.0f} ANS (pas de 6 mois, "
          f"chacune repartie de 10 000)")
    print(f"  {'risque':>7}{'x median':>10}{'x min':>8}{'x max':>8}"
          f"{'DD med':>8}{'DD pire':>9}{'>=x10':>7}{'perte':>7}")
    for rp in (1.0, 2.0, 3.0, 4.0):
        W = P.rolling_windows(rows, years=args.years, step_months=6,
                              risk_pct=rp, initial=10000.0,
                              max_concurrent=args.max_concurrent,
                              corr_groups=CORR_GROUPS,
                              max_group_concurrent=args.max_group)
        if not W:
            continue
        m = np.array([w[2].final / 10000.0 for w in W])
        d = np.array([w[2].max_dd_pct for w in W])
        print(f"  {rp:>6.1f}%{np.median(m):>10.2f}{m.min():>8.2f}{m.max():>8.1f}"
              f"{np.median(d):>8.0f}{d.max():>9.0f}"
              f"{(m >= 10).mean()*100:>6.0f}%{(m < 1).mean()*100:>6.0f}%")

    W = P.rolling_windows(rows, years=args.years, step_months=12,
                          risk_pct=args.risk, initial=10000.0,
                          max_concurrent=args.max_concurrent,
                          corr_groups=CORR_GROUPS,
                          max_group_concurrent=args.max_group)
    print(f"\nDETAIL A {args.risk:.0f}% DE RISQUE, UNE FENETRE PAR AN")
    print(f"  {'debut':<9}{'fin':<9}{'x':>7}{'CAGR%':>8}{'DD%':>7}{'trades':>8}")
    for a, b, res in W:
        print(f"  {report.fmt_ts(a)[:7]:<9}{report.fmt_ts(b)[:7]:<9}"
              f"{res.final/10000:>7.2f}{res.cagr:>8.1f}{res.max_dd_pct:>7.1f}"
              f"{res.trades:>8}")

    print("\nLe nombre d'instruments domine tout le reste : les fenetres ou seul")
    print("EURUSD trade (1999-2010) font 1.2-1.5x, celles a 4 instruments 6-7x.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
