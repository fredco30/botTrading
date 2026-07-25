#!/usr/bin/env python3
"""Grid search over EMA_Pullback_pyramid parameters, with walk-forward split.

Each backtest costs ~0.7 ms once the JIT is warm, so a 10k combination sweep
finishes in about ten seconds - the same sweep in the MT4 optimiser is an
afternoon.

The engine re-derives the signal from bars, so changing a filter correctly
re-orders wins and losses and therefore re-derives every pyramid streak. That
is the whole reason this exists; the older simul_*.py scripts replayed a fixed
MT4 trade list and could not do that.

Ranking defaults to `robust`: min(return/DD on the first half, return/DD on the
second half). A config that only works on one half scores near zero, which is
the walk-forward discipline CLAUDE.md asks for, enforced mechanically.

Examples:
    # pyramid multipliers
    python3 optimize_pullback_pyramid.py \
        --grid l1_mult=1,1.5,2,2.5,3,3.5,4,5,6,7 \
        --grid l2_mult=1,1.5,2,2.5,3,4

    # entry filters, ranked on the full period instead
    python3 optimize_pullback_pyramid.py \
        --grid min_sl_pips=12,15,18 --grid max_sl_pips=22,25,28,32 \
        --grid be_trigger_r=1.0,1.5,2.0 --rank ret_dd
"""

import argparse
import itertools
import sys
import time
from dataclasses import replace

import numpy as np

from engine import core, data, report
from engine.core import T_BALANCE, T_CONFLICT, T_PNL
from engine.params import PAIR_DATA, PAIR_PRESETS, PYRAMID_MODES, Params

DEFAULT_M15 = "EURUSD15_cut.csv"
DEFAULT_H1 = "EURUSD60_cut.csv"


def parse_value(text):
    low = text.strip().lower()
    if low in ("true", "false"):
        return low == "true"
    try:
        return int(text) if "." not in text and "e" not in low else float(text)
    except ValueError:
        return text.strip()   # string-valued fields, e.g. intrabar_model


def parse_grid(specs):
    grid = {}
    for spec in specs:
        if "=" not in spec:
            raise SystemExit(f"bad --grid '{spec}', expected name=v1,v2,...")
        name, values = spec.split("=", 1)
        name = name.strip()
        if not hasattr(Params(), name):
            raise SystemExit(f"unknown parameter '{name}'")
        grid[name] = [parse_value(v) for v in values.split(",") if v.strip()]
    return grid


def parse_args(argv=None):
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--pair", default="EURUSD", choices=sorted(PAIR_PRESETS))
    ap.add_argument("--m15", default=None)
    ap.add_argument("--h1", default=None)
    ap.add_argument("--set", action="append", default=[], metavar="NAME=VALUE",
                    dest="overrides", help="repeatable; fixed override, not swept")
    ap.add_argument("--grid", action="append", default=[],
                    metavar="NAME=V1,V2", help="repeatable; sweeps one parameter")
    ap.add_argument("--mode", choices=sorted(PYRAMID_MODES), default=None,
                    help="pyramid preset applied before the grid")
    ap.add_argument("--balance", type=float, default=10000.0)
    ap.add_argument("--spread", type=float, default=None)
    ap.add_argument("--start", default=None)
    ap.add_argument("--end", default=None)
    ap.add_argument("--split", default=None,
                    help="walk-forward cut date YYYY.MM.DD (default: midpoint)")
    ap.add_argument("--rank", default="robust",
                    choices=["robust", "ret_dd", "pf", "net", "oos_net"])
    ap.add_argument("--top", type=int, default=15)
    ap.add_argument("--min-trades", type=int, default=20,
                    help="discard configs with fewer trades on the full period")
    ap.add_argument("--max-dd", type=float, default=100.0,
                    help="discard configs whose full-period DD exceeds this %%")
    ap.add_argument("--max-conflict", type=float, default=100.0,
                    help="discard configs where more than this %% of trades were "
                         "decided by the intrabar model")
    return ap.parse_args(argv)


def evaluate(md, params):
    trades = core.run(md, params)
    if trades.shape[0] == 0:
        return None
    m = report.metrics(trades[:, T_PNL], trades[:, T_BALANCE],
                       params.initial_balance)
    # Share of trades whose outcome was decided by the intrabar model rather
    # than by the data. A config that leans on these is not a real edge.
    m["conflict_pct"] = float(trades[:, T_CONFLICT].sum() / len(trades) * 100.0)
    return m


def main(argv=None):
    args = parse_args(argv)
    grid = parse_grid(args.grid)
    if not grid:
        raise SystemExit("nothing to sweep: pass at least one --grid NAME=V1,V2")

    base = Params.for_pair(args.pair, initial_balance=args.balance)
    if args.spread is not None:
        base.spread_points = args.spread
    for spec in args.overrides:
        name, _, raw = spec.partition("=")
        name = name.strip()
        if not hasattr(base, name):
            raise SystemExit(f"unknown parameter '{name}'")
        setattr(base, name, parse_value(raw))
    if args.mode:
        base = base.with_mode(args.mode)
    m15_path = args.m15 or PAIR_DATA[args.pair][0]
    h1_path = args.h1 or PAIR_DATA[args.pair][1]

    md_full = data.build(m15_path, h1_path,
                         entry_ema_period=base.entry_ema_period,
                         rsi_period=base.rsi_period,
                         trend_ema_period=base.trend_ema_period,
                         trend_bars=base.trend_bars,
                         atr_period=base.atr_period)
    md_full = data.slice_period(md_full, args.start, args.end)

    cut = args.split
    if cut is None:
        cut = report._fmt(md_full.ts[md_full.ts.size // 2])[:10]
    md_is = data.slice_period(md_full, None, cut)
    md_oos = data.slice_period(md_full, cut, None)

    names = list(grid)
    combos = list(itertools.product(*(grid[n] for n in names)))

    print("=" * 92)
    print(f"GRID SEARCH   {args.pair}: {len(combos)} combinations over "
          f"{md_full.ts.size} M15 bars")
    print(f"full          {report._fmt(md_full.ts[0])[:10]} -> "
          f"{report._fmt(md_full.ts[-1])[:10]}")
    print(f"walk-forward  IS {report._fmt(md_is.ts[0])[:10]} -> {cut}   |   "
          f"OOS {cut} -> {report._fmt(md_oos.ts[-1])[:10]}")
    print(f"sweeping      " + "  ".join(f"{n}({len(grid[n])})" for n in names))
    print("=" * 92)

    # Warm the JIT before timing, otherwise the one-off compilation (~2.5 s)
    # is amortised across the sweep and the reported ms/run is meaningless.
    t_jit = time.time()
    for md in (md_full, md_is, md_oos):
        evaluate(md, base)
    print(f"jit warmup    {time.time() - t_jit:.1f}s")

    rows = []
    t0 = time.time()
    for idx, values in enumerate(combos):
        params = replace(base, **dict(zip(names, values)))
        full = evaluate(md_full, params)
        if full is None or full["trades"] < args.min_trades:
            continue
        if full["dd_pct"] > args.max_dd:
            continue
        if full["conflict_pct"] > args.max_conflict:
            continue
        m_is = evaluate(md_is, params)
        m_oos = evaluate(md_oos, params)
        if m_is is None or m_oos is None:
            continue

        robust = min(m_is["ret_dd"], m_oos["ret_dd"])
        rows.append(
            {
                "values": values,
                "full": full,
                "is": m_is,
                "oos": m_oos,
                "robust": robust,
            }
        )
        if (idx + 1) % 500 == 0:
            print(f"  ... {idx + 1}/{len(combos)}", file=sys.stderr)

    elapsed = time.time() - t0
    if not rows:
        print("\nno configuration passed the filters")
        return 1

    keyfn = {
        "robust": lambda r: r["robust"],
        "ret_dd": lambda r: r["full"]["ret_dd"],
        "pf": lambda r: r["full"]["pf"],
        "net": lambda r: r["full"]["net"],
        "oos_net": lambda r: r["oos"]["net"],
    }[args.rank]
    rows.sort(key=keyfn, reverse=True)

    print(f"\n{len(rows)}/{len(combos)} configs kept   "
          f"({elapsed:.1f}s, {elapsed / max(len(combos), 1) * 1000:.2f} ms/run)")
    print(f"ranked by: {args.rank}\n")

    head = "  ".join(f"{n[:11]:>11}" for n in names)
    print(f"{head}  {'trades':>7}{'net':>11}{'PF':>6}{'DD%':>7}{'R/DD':>7}"
          f"{'IS net':>10}{'OOS net':>10}{'robust':>8}{'amb%':>7}")
    print("-" * (len(head) + 73))
    for r in rows[:args.top]:
        vals = "  ".join(f"{v:>11}" for v in r["values"])
        f, i, o = r["full"], r["is"], r["oos"]
        print(f"{vals}  {f['trades']:>7}{f['net']:>11.0f}{f['pf']:>6.2f}"
              f"{f['dd_pct']:>7.1f}{f['ret_dd']:>7.0f}"
              f"{i['net']:>10.0f}{o['net']:>10.0f}{r['robust']:>8.0f}"
              f"{f['conflict_pct']:>7.1f}")

    best = rows[0]
    print("\nbest config:")
    for n, v in zip(names, best["values"]):
        print(f"  {n:<24}= {v}")
    print(f"  full   net {best['full']['net']:>10.0f}  PF {best['full']['pf']:.2f}"
          f"  DD {best['full']['dd_pct']:.1f}%  {best['full']['trades']} trades")
    print(f"  IS     net {best['is']['net']:>10.0f}  PF {best['is']['pf']:.2f}"
          f"  DD {best['is']['dd_pct']:.1f}%  {best['is']['trades']} trades")
    print(f"  OOS    net {best['oos']['net']:>10.0f}  PF {best['oos']['pf']:.2f}"
          f"  DD {best['oos']['dd_pct']:.1f}%  {best['oos']['trades']} trades")
    print("\nReminder: a config that only shines on one half is overfit. "
          "Confirm the winner in MT4 before trusting it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
