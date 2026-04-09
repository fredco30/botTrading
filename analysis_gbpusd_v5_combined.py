#!/usr/bin/env python3
"""
GBPUSD V5 — Combined filter simulations.
Reuses the enrichment logic from analysis_gbpusd_v5 and tests stacks.
"""

import sys
sys.path.insert(0, "/home/user/botTrading")
from analysis_gbpusd_v5 import (
    load_ohlc, load_trade_lines, reconstitute_trades, enrich,
    H1_FILE, M15_FILE, TRADE_FILE
)


def stats(trades, label):
    if not trades:
        print(f"{label:<60} EMPTY")
        return
    wins = sum(1 for t in trades if t["outcome"] in ("WIN", "BE"))
    tp = sum(1 for t in trades if t["outcome"] == "WIN")
    be = sum(1 for t in trades if t["outcome"] == "BE")
    losses = sum(1 for t in trades if t["outcome"] == "LOSS")
    net = sum(t["profit"] for t in trades)
    gw = sum(t["profit"] for t in trades if t["profit"] > 0)
    gl = -sum(t["profit"] for t in trades if t["profit"] < 0)
    pf = gw / gl if gl > 0 else float("inf")
    wr = wins / len(trades) * 100
    print(f"{label:<60} n={len(trades):>3} TP={tp:>2} BE={be:>2} SL={losses:>2} "
          f"WR={wr:>5.1f}% net={net:>+9.2f} PF={pf:>5.2f}")


def main():
    h1_data, h1_keys = load_ohlc(H1_FILE)
    m15_data, m15_keys = load_ohlc(M15_FILE)
    lines = load_trade_lines(TRADE_FILE)
    trades = reconstitute_trades(lines)
    for t in trades:
        enrich(t, h1_data, h1_keys, m15_data, m15_keys)

    print("=" * 78)
    print("BASELINE")
    print("=" * 78)
    stats(trades, "V4 preset (current)")

    print("\n" + "=" * 78)
    print("SINGLE FILTERS — ranked by net profit improvement")
    print("=" * 78)

    filters = [
        ("MaxSL <= 23 pips (kill 24+)", lambda t: t["sl_dist_pips"] <= 23),
        ("MaxSL <= 24 pips", lambda t: t["sl_dist_pips"] <= 24),
        ("Block hour 14h", lambda t: t["hour"] != 14),
        ("EMA50 dist < 30 pips (all)", lambda t: (t["ema50_dist_pips"] or 999) < 30),
        ("EMA50 dist < 40 pips (all)", lambda t: (t["ema50_dist_pips"] or 999) < 40),
        ("Directional EMA50: buys <15, sells 15-45",
         lambda t: (t["side"] == "buy" and (t["ema50_dist_pips"] or 999) < 15) or
                   (t["side"] == "sell" and 15 <= (t["ema50_dist_pips"] or 0) <= 45)),
        ("Block 2023 year (regime)", lambda t: t["year"] >= 2024),
        ("Block (Thu, 14h) combo", lambda t: not (t["dow"] == 3 and t["hour"] == 14)),
        ("Block (Tue, 16h) combo", lambda t: not (t["dow"] == 1 and t["hour"] == 16)),
        ("Block (Wed, 11h) combo", lambda t: not (t["dow"] == 2 and t["hour"] == 11)),
    ]

    results = []
    for name, fn in filters:
        kept = [t for t in trades if fn(t)]
        net = sum(t["profit"] for t in kept)
        stats(kept, name)
        results.append((name, fn, net, kept))

    print("\n" + "=" * 78)
    print("STACKED FILTERS — incremental")
    print("=" * 78)

    def stack(name, fns):
        kept = [t for t in trades if all(f(t) for f in fns)]
        stats(kept, name)
        return kept

    stack("V5.1: MaxSL<=23", [
        lambda t: t["sl_dist_pips"] <= 23,
    ])

    stack("V5.2: MaxSL<=23 + block 14h", [
        lambda t: t["sl_dist_pips"] <= 23,
        lambda t: t["hour"] != 14,
    ])

    stack("V5.3: MaxSL<=23 + block 14h + EMA50<40", [
        lambda t: t["sl_dist_pips"] <= 23,
        lambda t: t["hour"] != 14,
        lambda t: (t["ema50_dist_pips"] or 999) < 40,
    ])

    stack("V5.4: MaxSL<=23 + block 14h + EMA50<30", [
        lambda t: t["sl_dist_pips"] <= 23,
        lambda t: t["hour"] != 14,
        lambda t: (t["ema50_dist_pips"] or 999) < 30,
    ])

    stack("V5.5: V5.4 + block Thu 14h combo (already covered)", [
        lambda t: t["sl_dist_pips"] <= 23,
        lambda t: t["hour"] != 14,
        lambda t: (t["ema50_dist_pips"] or 999) < 30,
    ])

    stack("V5.6: MaxSL<=23 + block 14h + directional EMA50", [
        lambda t: t["sl_dist_pips"] <= 23,
        lambda t: t["hour"] != 14,
        lambda t: (t["side"] == "buy" and (t["ema50_dist_pips"] or 999) < 15) or
                  (t["side"] == "sell" and (t["ema50_dist_pips"] or 0) < 45),
    ])

    stack("V5.7: MaxSL<=23 + block 14h + directional EMA50 tight", [
        lambda t: t["sl_dist_pips"] <= 23,
        lambda t: t["hour"] != 14,
        lambda t: (t["side"] == "buy" and (t["ema50_dist_pips"] or 999) < 15) or
                  (t["side"] == "sell" and 10 <= (t["ema50_dist_pips"] or 0) <= 45),
    ])

    stack("V5.8: V5.7 + block 11h", [
        lambda t: t["sl_dist_pips"] <= 23,
        lambda t: t["hour"] not in (11, 14),
        lambda t: (t["side"] == "buy" and (t["ema50_dist_pips"] or 999) < 15) or
                  (t["side"] == "sell" and 10 <= (t["ema50_dist_pips"] or 0) <= 45),
    ])

    # Year split of the best candidate
    print("\n" + "=" * 78)
    print("YEAR SPLIT FOR V5.4 (leading candidate)")
    print("=" * 78)

    v54 = [t for t in trades if t["sl_dist_pips"] <= 23
           and t["hour"] != 14
           and (t["ema50_dist_pips"] or 999) < 30]
    for year in sorted(set(t["year"] for t in v54)):
        yg = [t for t in v54 if t["year"] == year]
        stats(yg, f"V5.4 {year}")

    print("\n" + "=" * 78)
    print("YEAR SPLIT FOR V5.6 (directional candidate)")
    print("=" * 78)

    v56 = [t for t in trades if t["sl_dist_pips"] <= 23
           and t["hour"] != 14
           and ((t["side"] == "buy" and (t["ema50_dist_pips"] or 999) < 15) or
                (t["side"] == "sell" and (t["ema50_dist_pips"] or 0) < 45))]
    for year in sorted(set(t["year"] for t in v56)):
        yg = [t for t in v56 if t["year"] == year]
        stats(yg, f"V5.6 {year}")

    # Side split
    print("\n" + "=" * 78)
    print("DIRECTION SPLIT FOR V5.4 vs V5.6")
    print("=" * 78)
    for label, base in [("V5.4", v54), ("V5.6", v56)]:
        stats([t for t in base if t["side"] == "buy"], f"{label} BUYS")
        stats([t for t in base if t["side"] == "sell"], f"{label} SELLS")

    # DD estimation for candidates — track running drawdown
    print("\n" + "=" * 78)
    print("MAX CONSECUTIVE LOSSES & EST. DD (sorted by open_dt)")
    print("=" * 78)

    def max_consec_losses_and_dd(trades_sorted):
        if not trades_sorted:
            return 0, 0.0
        consec = 0
        max_consec = 0
        equity = 0.0
        peak = 0.0
        max_dd = 0.0
        for t in sorted(trades_sorted, key=lambda x: x["open_dt"]):
            equity += t["profit"]
            peak = max(peak, equity)
            dd = peak - equity
            max_dd = max(max_dd, dd)
            if t["outcome"] == "LOSS":
                consec += 1
                max_consec = max(max_consec, consec)
            else:
                consec = 0
        return max_consec, max_dd

    for label, base in [("V4 baseline", trades), ("V5.4", v54), ("V5.6", v56)]:
        mc, mdd = max_consec_losses_and_dd(base)
        print(f"{label:<20} trades={len(base):>3}  max_consec_SL={mc}  estimated_DD=${mdd:.2f}")


if __name__ == "__main__":
    main()
