#!/usr/bin/env python3
"""Anchored walk-forward on the parameter *selection*, not on one config.

Every backtest in this project so far - including the v2 breakout - answers
"does this parameter set work on the data I have?". That question is
contaminated: the parameters were chosen while looking at that same data.

This answers a different and much harder question:

    If, at some date in the past, I had picked parameters using ONLY the data
    available up to that date, and then traded them untouched for five years,
    what would have happened?

That is the honest simulation of the whole process. The parameters are re-chosen
at every anchor from history alone, and every result is on data that did not
exist when the choice was made.

The baseline it is measured against is the fixed 2880/3/5 config, which was
picked with full hindsight. If the anchored version lands anywhere near it, the
process is sound. If it collapses, the v2 numbers are an illusion in the same
way the EMA-pullback presets were.

Usage:
    python3 walkforward_trend.py
    python3 walkforward_trend.py --risk 2 --oos-years 5
"""

import argparse
import itertools

import numpy as np

from engine import instruments as I, portfolio as P, report

SYMBOLS = ("EURUSD", "GBPUSD", "USDJPY", "XAUUSD")
CRYPTO = ("BTCUSD", "ETHUSD", "BNBUSD", "SOLUSD",
          "XRPUSD", "ADAUSD", "LTCUSD", "LINKUSD")
DATA_START = {"EURUSD": "1999.01.01"}
CORR_GROUPS = {"EURUSD": "USD_EUROPE", "GBPUSD": "USD_EUROPE",
               "BTCUSD": "CRYPTO", "ETHUSD": "CRYPTO", "BNBUSD": "CRYPTO",
               "SOLUSD": "CRYPTO", "XRPUSD": "CRYPTO", "ADAUSD": "CRYPTO",
               "LTCUSD": "CRYPTO", "LINKUSD": "CRYPTO"}

# Deliberately small. A wide grid searched on limited in-sample data is exactly
# how the EMA-pullback presets were produced.
GRID_ENTRY = (1440, 2160, 2880, 3600)
GRID_STOP = (2.0, 3.0, 4.0)
GRID_TRAIL = (4.0, 5.0, 6.0)

YEAR = 365.25 * 86400
MAXC = [4]
MAXG = [99]


def slice_from(series, start):
    if not start:
        return series
    t0 = np.datetime64(start.replace(".", "-"), "s").astype("int64")
    mask = series["ts"] >= t0
    n = series["ts"].size
    return {k: (v[mask] if isinstance(v, np.ndarray) and v.size == n else v)
            for k, v in series.items()}


def build_all(verbose=True):
    """Pre-compute R-multiple rows for every grid point, once."""
    combos = list(itertools.product(GRID_ENTRY, GRID_STOP, GRID_TRAIL))
    table = {}
    for idx, (entry, stop, trail) in enumerate(combos):
        rows = []
        for sym in SYMBOLS:
            s = slice_from(
                I.load_h1(sym, entry_period=entry, exit_period=max(20, entry // 3)),
                DATA_START.get(sym))
            t = I.run(s, risk_pct=1.0, atr_stop_mult=stop, atr_trail_mult=trail)
            rows += P.to_r_multiples(t, s["ts"], sym)
        table[(entry, stop, trail)] = sorted(rows, key=lambda r: r[0])
        if verbose:
            print(f"\r  pre-calcul {idx + 1}/{len(combos)}", end="", flush=True)
    if verbose:
        print()
    return table


def score_in_sample(rows, cutoff, risk_pct, oos_years, max_dd=None):
    """Rank a config on history only, up to `cutoff`.

    Scored on the 25th percentile of rolling-window multiples rather than the
    median: a config that is merely lucky on average scores badly here, and one
    that produces a losing window is penalised where it hurts.

    `max_dd` disqualifies a config whose worst historical drawdown breaches the
    budget. Without it the search drifts towards tighter stops, which is simply
    more leverage - it lifts the multiple and the drawdown together, and the
    drawdown is the constraint that actually ends live trading.
    """
    hist = [r for r in rows if r[1] <= cutoff]
    if len(hist) < 60:
        return None
    W = P.rolling_windows(hist, years=oos_years, step_months=6,
                          risk_pct=risk_pct, initial=10000.0,
                          max_concurrent=MAXC[0], corr_groups=CORR_GROUPS,
                          max_group_concurrent=MAXG[0])
    if len(W) < 4:
        return None
    if max_dd is not None:
        worst = max(w[2].max_dd_pct for w in W)
        if worst > max_dd:
            return None
    m = np.array([w[2].final / 10000.0 for w in W])
    return float(np.percentile(m, 25))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--symbols", default=None,
                    help="liste, ou 'crypto', ou 'all' (12 instruments)")
    ap.add_argument("--risk", type=float, default=2.0)
    ap.add_argument("--oos-years", type=float, default=5.0)
    ap.add_argument("--min-history", type=float, default=7.0,
                    help="years of history required before the first anchor")
    ap.add_argument("--max-group", type=int, default=99,
                    help="positions simultanees max dans un groupe correle")
    ap.add_argument("--max-concurrent", type=int, default=4)
    ap.add_argument("--max-dd", type=float, default=None,
                    help="reject configs whose worst in-sample 5y DD exceeds this %%")
    args = ap.parse_args(argv)

    print("=" * 78)
    print("WALK-FORWARD ANCRE SUR LE CHOIX DES PARAMETRES")
    print(f"grille {len(GRID_ENTRY)}x{len(GRID_STOP)}x{len(GRID_TRAIL)} = "
          f"{len(GRID_ENTRY)*len(GRID_STOP)*len(GRID_TRAIL)} configs   "
          f"risque {args.risk}%   OOS {args.oos_years:.0f} ans"
          + (f"   budget DD {args.max_dd:.0f}%" if args.max_dd else ""))
    print("=" * 78)

    global SYMBOLS
    if args.symbols:
        if args.symbols.lower() == "crypto":
            SYMBOLS = CRYPTO
        elif args.symbols.lower() == "all":
            SYMBOLS = SYMBOLS + CRYPTO
        else:
            SYMBOLS = tuple(s.strip().upper() for s in args.symbols.split(","))
    MAXC[0] = args.max_concurrent
    MAXG[0] = args.max_group
    print(f"instruments    {len(SYMBOLS)} : {', '.join(SYMBOLS)}")

    table = build_all()
    fixed = (2880, 3.0, 5.0)
    all_rows = table[fixed]
    t_first = all_rows[0][0]
    t_last = max(r[1] for r in all_rows)

    anchors = []
    a = t_first + int(args.min_history * YEAR)
    while a + args.oos_years * YEAR <= t_last:
        anchors.append(a)
        a += int(YEAR)

    print(f"\n{'ancre':<9}{'params choisis':<22}{'x OOS':>8}{'DD OOS':>8}"
          f"{'x fixe':>8}{'DD fixe':>9}")
    picked, oos_mult, oos_dd, ref_mult, ref_dd = [], [], [], [], []

    for anchor in anchors:
        best, best_score = None, -1e9
        for key, rows in table.items():
            sc = score_in_sample(rows, anchor, args.risk, args.oos_years,
                                 max_dd=args.max_dd)
            if sc is not None and sc > best_score:
                best_score, best = sc, key
        if best is None:
            continue

        end = anchor + int(args.oos_years * YEAR)
        res_rows = [r for r in table[best] if anchor <= r[0] and r[1] <= end]
        ref_rows = [r for r in table[fixed] if anchor <= r[0] and r[1] <= end]
        if len(res_rows) < 15 or len(ref_rows) < 15:
            continue
        res = P.simulate(res_rows, risk_pct=args.risk, initial=10000.0,
                         max_concurrent=args.max_concurrent,
                         corr_groups=CORR_GROUPS,
                         max_group_concurrent=args.max_group)
        ref = P.simulate(ref_rows, risk_pct=args.risk, initial=10000.0,
                         max_concurrent=args.max_concurrent,
                         corr_groups=CORR_GROUPS,
                         max_group_concurrent=args.max_group)

        picked.append(best)
        oos_mult.append(res.final / 10000.0)
        oos_dd.append(res.max_dd_pct)
        ref_mult.append(ref.final / 10000.0)
        ref_dd.append(ref.max_dd_pct)
        print(f"{report.fmt_ts(anchor)[:7]:<9}"
              f"{f'{best[0]} / {best[1]:g} / {best[2]:g}':<22}"
              f"{res.final/10000:>8.2f}{res.max_dd_pct:>8.1f}"
              f"{ref.final/10000:>8.2f}{ref.max_dd_pct:>9.1f}")

    if not oos_mult:
        print("\npas assez d'historique pour un seul ancrage")
        return 1

    om = np.array(oos_mult)
    rm = np.array(ref_mult)
    print(f"\n{'':<9}{'MEDIANE':<22}{np.median(om):>8.2f}"
          f"{np.median(oos_dd):>8.1f}{np.median(rm):>8.2f}{np.median(ref_dd):>9.1f}")
    print(f"{'':<9}{'PIRE':<22}{om.min():>8.2f}{max(oos_dd):>8.1f}"
          f"{rm.min():>8.2f}{max(ref_dd):>9.1f}")
    print(f"\nfenetres OOS perdantes : {(om < 1).sum()}/{om.size} "
          f"(config fixe : {(rm < 1).sum()}/{rm.size})")

    from collections import Counter
    print("\nparametres choisis par l'historique seul :")
    for k, v in Counter(picked).most_common():
        print(f"  {k[0]} / {k[1]:g} / {k[2]:g}   {v}x")

    gap = (np.median(om) / np.median(rm) - 1) * 100
    print(f"\nEcart mediane anticipe vs retrospectif : {gap:+.0f}%")
    print("Un ecart proche de zero veut dire que le retrospectif ne trichait pas.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
