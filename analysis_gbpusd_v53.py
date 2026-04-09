#!/usr/bin/env python3
"""V5.3 result analysis — find remaining alpha in the 29 surviving trades."""
import sys
sys.path.insert(0, "/home/user/botTrading")
from analysis_gbpusd_v5 import (
    load_ohlc, load_trade_lines, reconstitute_trades, enrich,
    H1_FILE, M15_FILE,
)
from collections import defaultdict

TRADE_FILE = "/home/user/botTrading/historique trade gbpusd V53.txt"


def bucket(trades, keyfn, label):
    groups = defaultdict(list)
    for t in trades:
        k = keyfn(t)
        if k is None:
            continue
        groups[k].append(t)
    print(f"\n=== {label} ===")
    print(f"{'Bucket':<22} {'N':>3} {'TP':>3} {'BE':>3} {'SL':>3} "
          f"{'WR%':>6} {'Net$':>10} {'PF':>6}")
    for k in sorted(groups.keys(), key=str):
        g = groups[k]
        tp = sum(1 for t in g if t["outcome"] == "WIN")
        be = sum(1 for t in g if t["outcome"] == "BE")
        sl = sum(1 for t in g if t["outcome"] == "LOSS")
        net = sum(t["profit"] for t in g)
        gw = sum(t["profit"] for t in g if t["profit"] > 0)
        gl = -sum(t["profit"] for t in g if t["profit"] < 0)
        pf = gw / gl if gl > 0 else float("inf")
        wr = (tp + be) / len(g) * 100
        print(f"{str(k):<22} {len(g):>3} {tp:>3} {be:>3} {sl:>3} "
              f"{wr:>5.1f}% {net:>10.2f} {pf:>6.2f}")


def show_losers(trades):
    print("\n=== THE 10 LOSERS — context ===")
    print(f"{'Date':<17} {'Side':<5} {'Hr':>3} {'DOW':<4} "
          f"{'ATR':>5} {'EMA50d':>7} {'RSI':>5} {'SL_pips':>8} {'P&L':>9}")
    losers = [t for t in trades if t["outcome"] == "LOSS"]
    for t in sorted(losers, key=lambda x: x["open_dt"]):
        dow = ["Mon", "Tue", "Wed", "Thu", "Fri"][t["dow"]]
        print(f"{t['open_dt']} {t['side']:<5} {t['hour']:>3} {dow:<4} "
              f"{t['atr_pips'] or 0:>5.1f} {t['ema50_dist_pips'] or 0:>7.1f} "
              f"{t['rsi'] or 0:>5.1f} {t['sl_dist_pips']:>8.1f} {t['profit']:>+9.2f}")


def show_winners(trades):
    print("\n=== THE 13 TP WINNERS — context ===")
    print(f"{'Date':<17} {'Side':<5} {'Hr':>3} {'DOW':<4} "
          f"{'ATR':>5} {'EMA50d':>7} {'RSI':>5} {'SL_pips':>8} {'P&L':>9}")
    winners = [t for t in trades if t["outcome"] == "WIN"]
    for t in sorted(winners, key=lambda x: x["open_dt"]):
        dow = ["Mon", "Tue", "Wed", "Thu", "Fri"][t["dow"]]
        print(f"{t['open_dt']} {t['side']:<5} {t['hour']:>3} {dow:<4} "
              f"{t['atr_pips'] or 0:>5.1f} {t['ema50_dist_pips'] or 0:>7.1f} "
              f"{t['rsi'] or 0:>5.1f} {t['sl_dist_pips']:>8.1f} {t['profit']:>+9.2f}")


def simulate(trades, name, fn):
    kept = [t for t in trades if fn(t)]
    rej = [t for t in trades if not fn(t)]
    net = sum(t["profit"] for t in kept)
    gw = sum(t["profit"] for t in kept if t["profit"] > 0)
    gl = -sum(t["profit"] for t in kept if t["profit"] < 0)
    pf = gw / gl if gl > 0 else float("inf")
    tp = sum(1 for t in kept if t["outcome"] == "WIN")
    be = sum(1 for t in kept if t["outcome"] == "BE")
    sl = sum(1 for t in kept if t["outcome"] == "LOSS")
    wr = (tp + be) / len(kept) * 100 if kept else 0
    rej_net = sum(t["profit"] for t in rej)
    print(f"{name:<55} n={len(kept):>3} TP={tp} BE={be} SL={sl} "
          f"WR={wr:>5.1f}% net={net:>+8.2f} PF={pf:>5.2f} "
          f"(dropped: {len(rej)}, their net: {rej_net:>+7.2f})")


def main():
    h1, h1k = load_ohlc(H1_FILE)
    m15, m15k = load_ohlc(M15_FILE)
    raw = load_trade_lines(TRADE_FILE)
    trades = reconstitute_trades(raw)
    for t in trades:
        enrich(t, h1, h1k, m15, m15k)

    # Overview
    tp = sum(1 for t in trades if t["outcome"] == "WIN")
    be = sum(1 for t in trades if t["outcome"] == "BE")
    sl = sum(1 for t in trades if t["outcome"] == "LOSS")
    net = sum(t["profit"] for t in trades)
    gw = sum(t["profit"] for t in trades if t["profit"] > 0)
    gl = -sum(t["profit"] for t in trades if t["profit"] < 0)
    pf = gw / gl if gl > 0 else float("inf")
    print("=" * 75)
    print("V5.3 LIVE BACKTEST RESULT")
    print("=" * 75)
    print(f"Trades: {len(trades)}  TP: {tp}  BE: {be}  SL: {sl}")
    print(f"Net: +${net:.2f}  PF: {pf:.2f}  WR: {(tp+be)/len(trades)*100:.1f}%")

    show_losers(trades)
    show_winners(trades)

    bucket(trades, lambda t: t["side"], "BY SIDE")
    bucket(trades, lambda t: t["year"], "BY YEAR")
    bucket(trades, lambda t: t["hour"], "BY HOUR")
    bucket(trades, lambda t: ["Mon", "Tue", "Wed", "Thu", "Fri"][t["dow"]] if t["dow"] < 5 else None, "BY DAY")

    def atr_bin(t):
        a = t["atr_pips"] or 0
        if a < 12:  return "a<12"
        if a < 15:  return "b:12-15"
        if a < 18:  return "c:15-18"
        if a < 22:  return "d:18-22"
        return "e:>=22"
    bucket(trades, atr_bin, "BY ATR")

    def ema_bin(t):
        d = t["ema50_dist_pips"] or 0
        if d < 10:  return "a<10"
        if d < 20:  return "b:10-20"
        if d < 30:  return "c:20-30"
        return "d:30-40"
    bucket(trades, ema_bin, "BY EMA50 DIST")

    def rsi_bin(t):
        r = t["rsi"] or 50
        if r < 40: return "a<40"
        if r < 50: return "b:40-50"
        if r < 60: return "c:50-60"
        if r < 70: return "d:60-70"
        return "e>=70"
    bucket(trades, rsi_bin, "BY RSI")

    print("\n" + "=" * 75)
    print("CANDIDATE TIGHTENINGS")
    print("=" * 75)
    simulate(trades, "Baseline V5.3", lambda t: True)
    simulate(trades, "MaxSL<=22", lambda t: t["sl_dist_pips"] <= 22)
    simulate(trades, "MaxSL<=21", lambda t: t["sl_dist_pips"] <= 21)
    simulate(trades, "ATR<=18", lambda t: (t["atr_pips"] or 0) <= 18)
    simulate(trades, "ATR<=16", lambda t: (t["atr_pips"] or 0) <= 16)
    simulate(trades, "ATR 11-18", lambda t: 11 <= (t["atr_pips"] or 0) <= 18)
    simulate(trades, "EMA50 dist<30", lambda t: (t["ema50_dist_pips"] or 0) < 30)
    simulate(trades, "Year >= 2024 only", lambda t: t["year"] >= 2024)
    simulate(trades, "Block Thu", lambda t: t["dow"] != 3)
    simulate(trades, "Block hour 11", lambda t: t["hour"] != 11)
    simulate(trades, "Block hour 16", lambda t: t["hour"] != 16)
    simulate(trades, "RSI 40-65 (all)", lambda t: 40 <= (t["rsi"] or 50) <= 65)
    simulate(trades, "RSI 35-65 (all)", lambda t: 35 <= (t["rsi"] or 50) <= 65)
    simulate(trades, "Buys only", lambda t: t["side"] == "buy")
    simulate(trades, "Sells only", lambda t: t["side"] == "sell")

    # Combined
    print("\n--- Stacked candidates ---")
    simulate(trades, "MaxSL<=22 + ATR<=18",
             lambda t: t["sl_dist_pips"] <= 22 and (t["atr_pips"] or 0) <= 18)
    simulate(trades, "MaxSL<=22 + ATR<=18 + EMA50<30",
             lambda t: t["sl_dist_pips"] <= 22 and (t["atr_pips"] or 0) <= 18
                       and (t["ema50_dist_pips"] or 0) < 30)
    simulate(trades, "MaxSL<=22 + RSI 35-65",
             lambda t: t["sl_dist_pips"] <= 22 and 35 <= (t["rsi"] or 50) <= 65)


if __name__ == "__main__":
    main()
