#!/usr/bin/env python3
"""
GBPUSD V5 Analysis — 63 live trades from the current V4 preset.
Goal: find what distinguishes winners from losers and propose
concrete, data-driven filters to push PF from 1.46 toward 1.8+.
"""

import csv
from datetime import datetime, timedelta
from collections import defaultdict
from statistics import mean, median, stdev

TRADE_FILE = "/home/user/botTrading/historique trade gbpusd 3ansV5.txt"
H1_FILE = "/home/user/botTrading/GBPUSD60_cut.csv"
M15_FILE = "/home/user/botTrading/GBPUSD15_cut.csv"
PIP = 0.0001
INITIAL_BALANCE = 10000.0


# ============================================================
# LOAD DATA
# ============================================================
def load_ohlc(path):
    data = {}
    keys = []
    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            p = line.split(",")
            if len(p) < 6:
                continue
            try:
                dt = datetime.strptime(f"{p[0]},{p[1]}", "%Y.%m.%d,%H:%M")
                o, h, l, c = map(float, p[2:6])
                data[dt] = (o, h, l, c)
                keys.append(dt)
            except Exception:
                continue
    return data, keys


def load_trade_lines(path):
    lines = []
    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            p = line.split("\t")
            if len(p) < 10:
                continue
            try:
                lines.append(
                    {
                        "seq": int(p[0]),
                        "dt": datetime.strptime(p[1], "%Y.%m.%d %H:%M"),
                        "action": p[2].strip().lower(),
                        "ticket": int(p[3]),
                        "lots": float(p[4]),
                        "price": float(p[5]),
                        "sl": float(p[6]),
                        "tp": float(p[7]),
                        "profit": float(p[8]),
                        "balance": float(p[9]),
                    }
                )
            except Exception:
                continue
    return lines


def reconstitute_trades(lines):
    by_ticket = defaultdict(list)
    for r in lines:
        by_ticket[r["ticket"]].append(r)

    trades = []
    for ticket, rows in by_ticket.items():
        rows.sort(key=lambda x: x["dt"])
        open_row = next((r for r in rows if r["action"] in ("buy", "sell")), None)
        close_row = next((r for r in rows if r["action"] in ("s/l", "t/p", "close")), None)
        if not open_row or not close_row:
            continue
        trades.append(
            {
                "ticket": ticket,
                "open_dt": open_row["dt"],
                "close_dt": close_row["dt"],
                "side": open_row["action"],
                "open_price": open_row["price"],
                "sl": open_row["sl"],
                "tp": open_row["tp"],
                "exit_price": close_row["price"],
                "exit_type": close_row["action"],  # s/l or t/p
                "profit": close_row["profit"],
                "lots": open_row["lots"],
            }
        )

    trades.sort(key=lambda t: t["open_dt"])
    return trades


# ============================================================
# INDICATORS (EMA, ATR, RSI) computed on demand up to a given time
# ============================================================
def ema_series(h1_data, h1_keys, up_to_dt, period):
    """Return EMA value at the H1 bar immediately at or before up_to_dt."""
    subset_keys = [k for k in h1_keys if k <= up_to_dt]
    if len(subset_keys) < period + 2:
        return None
    closes = [h1_data[k][3] for k in subset_keys]
    k = 2 / (period + 1)
    ema = sum(closes[:period]) / period
    for c in closes[period:]:
        ema = c * k + ema * (1 - k)
    return ema


def ema_value_and_slope(h1_data, h1_keys, up_to_dt, period=50, slope_bars=5):
    """Compute EMA at up_to_dt and slope_bars ago."""
    subset = [k for k in h1_keys if k <= up_to_dt]
    if len(subset) < period + slope_bars + 2:
        return None, None
    closes = [h1_data[k][3] for k in subset]
    k = 2 / (period + 1)
    ema = sum(closes[:period]) / period
    ema_history = [ema]
    for c in closes[period:]:
        ema = c * k + ema * (1 - k)
        ema_history.append(ema)
    ema_now = ema_history[-1]
    ema_prev = ema_history[-1 - slope_bars] if len(ema_history) > slope_bars else None
    return ema_now, ema_prev


def atr_value(h1_data, h1_keys, up_to_dt, period=14):
    subset = [k for k in h1_keys if k <= up_to_dt]
    if len(subset) < period + 2:
        return None
    ohlcs = [h1_data[k] for k in subset]
    trs = []
    for i in range(1, len(ohlcs)):
        o, h, l, c = ohlcs[i]
        pc = ohlcs[i - 1][3]
        tr = max(h - l, abs(h - pc), abs(l - pc))
        trs.append(tr)
    if len(trs) < period:
        return None
    atr = sum(trs[:period]) / period
    for tr in trs[period:]:
        atr = (atr * (period - 1) + tr) / period
    return atr


def rsi_value(m15_data, m15_keys, up_to_dt, period=14):
    subset = [k for k in m15_keys if k < up_to_dt]
    if len(subset) < period + 2:
        return None
    closes = [m15_data[k][3] for k in subset]
    gains, losses = [], []
    for i in range(1, len(closes)):
        d = closes[i] - closes[i - 1]
        gains.append(max(d, 0))
        losses.append(max(-d, 0))
    if len(gains) < period:
        return None
    avg_g = sum(gains[:period]) / period
    avg_l = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        avg_g = (avg_g * (period - 1) + gains[i]) / period
        avg_l = (avg_l * (period - 1) + losses[i]) / period
    if avg_l == 0:
        return 100
    rs = avg_g / avg_l
    return 100 - (100 / (1 + rs))


# ============================================================
# ENRICH TRADES WITH MARKET CONTEXT
# ============================================================
def enrich(trade, h1_data, h1_keys, m15_data, m15_keys):
    """Compute H1 and M15 context at trade open."""
    dt = trade["open_dt"]
    # Round down to H1 bar
    h1_bar = dt.replace(minute=0, second=0, microsecond=0)
    # Round down to M15 bar
    m15_bar = dt.replace(minute=(dt.minute // 15) * 15, second=0, microsecond=0)

    ema50_now, ema50_prev = ema_value_and_slope(h1_data, h1_keys, h1_bar, 50, 5)
    atr = atr_value(h1_data, h1_keys, h1_bar, 14)
    rsi = rsi_value(m15_data, m15_keys, m15_bar, 14)

    h1_close = h1_data[h1_bar][3] if h1_bar in h1_data else None

    ema50_dist_pips = None
    if ema50_now and h1_close:
        ema50_dist_pips = abs(h1_close - ema50_now) / PIP

    atr_pips = atr / PIP if atr else None

    sl_dist_pips = abs(trade["open_price"] - trade["sl"]) / PIP

    ema50_slope_pips = None
    if ema50_now and ema50_prev:
        ema50_slope_pips = (ema50_now - ema50_prev) / PIP

    trade["atr_pips"] = atr_pips
    trade["rsi"] = rsi
    trade["ema50_dist_pips"] = ema50_dist_pips
    trade["ema50_slope_pips"] = ema50_slope_pips
    trade["sl_dist_pips"] = sl_dist_pips
    trade["hour"] = dt.hour
    trade["dow"] = dt.weekday()  # 0=Mon, 4=Fri
    trade["month"] = dt.month
    trade["year"] = dt.year

    # Win classification
    if trade["exit_type"] == "t/p":
        trade["outcome"] = "WIN"
    elif trade["profit"] > 0:
        trade["outcome"] = "BE"  # BE+spread = small positive
    else:
        trade["outcome"] = "LOSS"

    return trade


# ============================================================
# BUCKET ANALYZER
# ============================================================
def bucket(trades, keyfn, label):
    groups = defaultdict(list)
    for t in trades:
        k = keyfn(t)
        if k is None:
            continue
        groups[k].append(t)

    print(f"\n=== {label} ===")
    print(f"{'Bucket':<20} {'N':>4} {'WIN':>4} {'BE':>4} {'SL':>4} "
          f"{'WR%':>6} {'Net$':>10} {'PF':>6}")
    rows = []
    for k in sorted(groups.keys()):
        g = groups[k]
        wins = [t for t in g if t["outcome"] == "WIN"]
        be = [t for t in g if t["outcome"] == "BE"]
        losses = [t for t in g if t["outcome"] == "LOSS"]
        gross_w = sum(t["profit"] for t in wins + be if t["profit"] > 0)
        gross_l = -sum(t["profit"] for t in losses)
        net = sum(t["profit"] for t in g)
        wr = (len(wins) + len(be)) / len(g) * 100
        pf = gross_w / gross_l if gross_l > 0 else float("inf")
        print(f"{str(k):<20} {len(g):>4} {len(wins):>4} {len(be):>4} "
              f"{len(losses):>4} {wr:>5.1f}% {net:>10.2f} {pf:>6.2f}")
        rows.append((k, len(g), net, pf, wr))
    return rows


# ============================================================
# SIMULATE WITH FILTER
# ============================================================
def simulate_with_filter(trades, name, keep_fn):
    kept = [t for t in trades if keep_fn(t)]
    rejected = [t for t in trades if not keep_fn(t)]
    net = sum(t["profit"] for t in kept)
    wins = sum(1 for t in kept if t["outcome"] in ("WIN", "BE"))
    losses = sum(1 for t in kept if t["outcome"] == "LOSS")
    gross_w = sum(t["profit"] for t in kept if t["profit"] > 0)
    gross_l = -sum(t["profit"] for t in kept if t["profit"] < 0)
    pf = gross_w / gross_l if gross_l > 0 else float("inf")
    wr = (wins / len(kept) * 100) if kept else 0
    rejected_net = sum(t["profit"] for t in rejected)
    print(
        f"{name:<50} kept={len(kept):>3}  "
        f"net={net:>+8.2f}  PF={pf:>4.2f}  WR={wr:>4.1f}%  "
        f"rejected_net={rejected_net:>+8.2f}"
    )
    return kept


# ============================================================
# MAIN
# ============================================================
def main():
    print("Loading H1 data...")
    h1_data, h1_keys = load_ohlc(H1_FILE)
    print(f"  {len(h1_data)} H1 bars loaded")

    print("Loading M15 data...")
    m15_data, m15_keys = load_ohlc(M15_FILE)
    print(f"  {len(m15_data)} M15 bars loaded")

    print("Loading trades...")
    lines = load_trade_lines(TRADE_FILE)
    trades = reconstitute_trades(lines)
    print(f"  {len(trades)} trades reconstituted")

    print("Enriching trades with market context...")
    for t in trades:
        enrich(t, h1_data, h1_keys, m15_data, m15_keys)

    # Overview
    wins = [t for t in trades if t["outcome"] == "WIN"]
    be = [t for t in trades if t["outcome"] == "BE"]
    losses = [t for t in trades if t["outcome"] == "LOSS"]
    net = sum(t["profit"] for t in trades)
    gross_w = sum(t["profit"] for t in trades if t["profit"] > 0)
    gross_l = -sum(t["profit"] for t in trades if t["profit"] < 0)
    pf = gross_w / gross_l if gross_l > 0 else float("inf")

    print("\n" + "=" * 70)
    print("OVERVIEW (V4 preset, live data)")
    print("=" * 70)
    print(f"Trades:    {len(trades)}")
    print(f"TP wins:   {len(wins)} ({len(wins)/len(trades)*100:.1f}%)")
    print(f"BE exits:  {len(be)} ({len(be)/len(trades)*100:.1f}%)")
    print(f"SL losses: {len(losses)} ({len(losses)/len(trades)*100:.1f}%)")
    print(f"Net:       {net:+.2f}")
    print(f"Gross W:   {gross_w:+.2f}")
    print(f"Gross L:   {gross_l:+.2f}")
    print(f"PF:        {pf:.2f}")

    # Buckets
    bucket(trades, lambda t: t["side"], "BY DIRECTION")
    bucket(trades, lambda t: t["year"], "BY YEAR")
    bucket(trades, lambda t: t["hour"], "BY HOUR")
    bucket(trades, lambda t: ["Mon", "Tue", "Wed", "Thu", "Fri"][t["dow"]] if t["dow"] < 5 else None, "BY DAY")
    bucket(trades, lambda t: (["Mon", "Tue", "Wed", "Thu", "Fri"][t["dow"]], t["hour"]) if t["dow"] < 5 else None, "BY DOW×HOUR")

    # Continuous bins
    def bin_sl(t):
        s = t["sl_dist_pips"]
        if s < 18:  return "<18"
        if s < 20:  return "18-20"
        if s < 22:  return "20-22"
        if s < 24:  return "22-24"
        return ">=24"
    bucket(trades, bin_sl, "BY SL DIST (pips)")

    def bin_atr(t):
        a = t["atr_pips"]
        if a is None: return None
        if a < 10:  return "<10"
        if a < 13:  return "10-13"
        if a < 16:  return "13-16"
        if a < 20:  return "16-20"
        return ">=20"
    bucket(trades, bin_atr, "BY H1 ATR (pips)")

    def bin_ema50_dist(t):
        d = t["ema50_dist_pips"]
        if d is None: return None
        if d < 15:  return "<15"
        if d < 30:  return "15-30"
        if d < 45:  return "30-45"
        if d < 60:  return "45-60"
        return ">=60"
    bucket(trades, bin_ema50_dist, "BY EMA50 DIST (pips)")

    def bin_slope(t):
        s = t["ema50_slope_pips"]
        if s is None: return None
        # Signed slope is meaningful w.r.t. trade direction
        if t["side"] == "buy":
            s = s  # want positive slope
        else:
            s = -s  # for sells, invert so positive = aligned
        if s < 5:   return "a<5"
        if s < 10:  return "b:5-10"
        if s < 20:  return "c:10-20"
        if s < 30:  return "d:20-30"
        return "e:>=30"
    bucket(trades, bin_slope, "BY EMA50 SLOPE aligned (pips over 5 H1 bars)")

    def bin_rsi(t):
        r = t["rsi"]
        if r is None: return None
        if r < 30:  return "a:<30"
        if r < 40:  return "b:30-40"
        if r < 50:  return "c:40-50"
        if r < 60:  return "d:50-60"
        if r < 70:  return "e:60-70"
        return "f:>=70"
    bucket(trades, bin_rsi, "BY M15 RSI")

    # SELL vs BUY split on the most interesting metrics
    print("\n=== EMA50 DISTANCE — BUYS ONLY ===")
    bucket([t for t in trades if t["side"] == "buy"], bin_ema50_dist, "BUYS: EMA50 DIST")
    print("\n=== EMA50 DISTANCE — SELLS ONLY ===")
    bucket([t for t in trades if t["side"] == "sell"], bin_ema50_dist, "SELLS: EMA50 DIST")

    print("\n=== H1 ATR — BUYS ONLY ===")
    bucket([t for t in trades if t["side"] == "buy"], bin_atr, "BUYS: ATR")
    print("\n=== H1 ATR — SELLS ONLY ===")
    bucket([t for t in trades if t["side"] == "sell"], bin_atr, "SELLS: ATR")

    # Simulate candidate filters
    print("\n" + "=" * 70)
    print("CANDIDATE FILTERS — cumulative simulation on V5 trades")
    print("=" * 70)
    print(f"Baseline: kept=63 net=+1540.86 PF=1.46")

    simulate_with_filter(trades, "Block hour 09", lambda t: t["hour"] != 9)
    simulate_with_filter(trades, "Block hour 11", lambda t: t["hour"] != 11)
    simulate_with_filter(trades, "Block hour 14", lambda t: t["hour"] != 14)
    simulate_with_filter(trades, "Block hour 16", lambda t: t["hour"] != 16)

    simulate_with_filter(trades, "Buys only: EMA50 dist < 30", lambda t: not (t["side"] == "buy" and (t["ema50_dist_pips"] or 0) > 30))
    simulate_with_filter(trades, "All: EMA50 dist < 30", lambda t: (t["ema50_dist_pips"] or 0) < 30)
    simulate_with_filter(trades, "All: EMA50 dist < 40", lambda t: (t["ema50_dist_pips"] or 0) < 40)

    simulate_with_filter(trades, "ATR 10-20 pips", lambda t: 10 <= (t["atr_pips"] or 0) <= 20)
    simulate_with_filter(trades, "ATR 12-22 pips", lambda t: 12 <= (t["atr_pips"] or 0) <= 22)
    simulate_with_filter(trades, "ATR >= 12",     lambda t: (t["atr_pips"] or 0) >= 12)

    simulate_with_filter(trades, "Slope aligned >= 10 pips",
                         lambda t: ((t["ema50_slope_pips"] or 0) * (1 if t["side"] == "buy" else -1)) >= 10)
    simulate_with_filter(trades, "Slope aligned >= 15 pips",
                         lambda t: ((t["ema50_slope_pips"] or 0) * (1 if t["side"] == "buy" else -1)) >= 15)

    simulate_with_filter(trades, "Buys: RSI 40-65", lambda t: not (t["side"] == "buy" and not (40 <= (t["rsi"] or 50) <= 65)))
    simulate_with_filter(trades, "Sells: RSI 35-60", lambda t: not (t["side"] == "sell" and not (35 <= (t["rsi"] or 50) <= 60)))

    simulate_with_filter(trades, "SL dist >= 20", lambda t: t["sl_dist_pips"] >= 20)
    simulate_with_filter(trades, "SL dist 20-24", lambda t: 20 <= t["sl_dist_pips"] <= 24)

    # Combined: most promising stack
    print("\n--- STACKED FILTERS ---")
    simulate_with_filter(
        trades,
        "Block 14h + Block 11h",
        lambda t: t["hour"] not in (11, 14),
    )
    simulate_with_filter(
        trades,
        "Block 14h + slope>=10 aligned",
        lambda t: t["hour"] != 14 and ((t["ema50_slope_pips"] or 0) * (1 if t["side"] == "buy" else -1)) >= 10,
    )
    simulate_with_filter(
        trades,
        "Block 14h + 11h + ATR>=12",
        lambda t: t["hour"] not in (11, 14) and (t["atr_pips"] or 0) >= 12,
    )

    # Year-by-year dump to see regime stability
    print("\n=== YEAR × SIDE ===")
    for year in sorted(set(t["year"] for t in trades)):
        for side in ("buy", "sell"):
            g = [t for t in trades if t["year"] == year and t["side"] == side]
            if not g:
                continue
            net = sum(t["profit"] for t in g)
            wins = sum(1 for t in g if t["outcome"] == "WIN")
            be = sum(1 for t in g if t["outcome"] == "BE")
            print(f"  {year} {side}: n={len(g):>2}  TP={wins}  BE={be}  "
                  f"SL={len(g)-wins-be}  net={net:>+8.2f}")


if __name__ == "__main__":
    main()
