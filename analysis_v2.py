#!/usr/bin/env python3
"""
EMA Pullback EA v2 - Comprehensive Backtest Analysis
Analyzes 527 trades from Apr 2023 to Apr 2026
"""

import csv
from datetime import datetime, timedelta
from collections import defaultdict
import math

# =============================================================================
# CONFIG
# =============================================================================
TRADE_FILE = r"C:\Users\projets\botTrading\historique trade 3ansV2.txt"
M15_FILE = r"C:\Users\projets\botTrading\EURUSD15_cut.csv"
H1_FILE = r"C:\Users\projets\botTrading\EURUSD60.csv"
PIP = 0.0001  # EURUSD pip value

# =============================================================================
# HELPERS
# =============================================================================
def fmt_money(v):
    return f"${v:,.2f}" if v >= 0 else f"-${abs(v):,.2f}"

def fmt_pct(v):
    return f"{v:.1f}%"

def fmt_pf(wins, losses):
    """Profit factor = gross wins / gross losses"""
    if losses == 0:
        return "INF" if wins > 0 else "N/A"
    return f"{wins / losses:.2f}"

def print_separator(char="=", width=120):
    print(char * width)

def print_header(title):
    print()
    print_separator()
    print(f"  {title}")
    print_separator()

def print_subheader(title):
    print()
    print(f"  --- {title} ---")

def print_table(headers, rows, col_widths=None):
    """Print a formatted table"""
    if not rows:
        print("  (no data)")
        return
    if col_widths is None:
        col_widths = []
        for i, h in enumerate(headers):
            max_w = len(str(h))
            for r in rows:
                if i < len(r):
                    max_w = max(max_w, len(str(r[i])))
            col_widths.append(max_w + 2)

    # Header
    line = "  "
    for i, h in enumerate(headers):
        w = col_widths[i] if i < len(col_widths) else 12
        line += str(h).rjust(w)
    print(line)
    print("  " + "-" * sum(col_widths))

    # Rows
    for r in rows:
        line = "  "
        for i, val in enumerate(r):
            w = col_widths[i] if i < len(col_widths) else 12
            line += str(val).rjust(w)
        print(line)

# =============================================================================
# A. PARSE TRADES
# =============================================================================
def parse_trades():
    """Parse trade history into complete trades"""
    lines = []
    with open(TRADE_FILE, "r", encoding="utf-8") as f:
        for raw_line in f:
            raw_line = raw_line.strip()
            if not raw_line:
                continue
            parts = raw_line.split("\t")
            if len(parts) < 10:
                continue
            try:
                # Format: LineNum, DateTime, Action, Ticket, Lots, Price, SL, TP, Profit, Balance
                line_num = int(parts[0])
                dt_str = parts[1].strip()
                action = parts[2].strip().lower()
                ticket = int(parts[3])
                lots = float(parts[4])
                price = float(parts[5])
                sl = float(parts[6])
                tp = float(parts[7])
                profit = float(parts[8])
                balance = float(parts[9])

                dt = datetime.strptime(dt_str, "%Y.%m.%d %H:%M")

                lines.append({
                    "line": line_num, "seq": line_num, "dt": dt, "action": action,
                    "ticket": ticket, "lots": lots, "price": price,
                    "sl": sl, "tp": tp, "profit": profit, "balance": balance
                })
            except (ValueError, IndexError):
                continue

    # Group by ticket
    ticket_groups = defaultdict(list)
    for l in lines:
        ticket_groups[l["ticket"]].append(l)

    trades = []
    for ticket in sorted(ticket_groups.keys()):
        events = sorted(ticket_groups[ticket], key=lambda x: x["seq"])

        entry = None
        modify = None
        exit_ev = None

        for ev in events:
            if ev["action"] in ("buy", "sell"):
                entry = ev
            elif ev["action"] == "modify":
                modify = ev
            elif ev["action"] in ("s/l", "t/p"):
                exit_ev = ev

        if entry is None or exit_ev is None:
            continue

        direction = entry["action"]  # buy or sell
        entry_time = entry["dt"]
        exit_time = exit_ev["dt"]
        duration_min = (exit_time - entry_time).total_seconds() / 60.0

        day_of_week = entry_time.weekday()  # Mon=0..Fri=4
        hour = entry_time.hour

        # Session
        if 8 <= hour < 12:
            session = "London"
        elif 13 <= hour <= 17:
            session = "NY"
        elif hour == 12:
            session = "London"  # 12:xx is end of London
        else:
            session = "Off"

        # SL and TP distances in pips
        if direction == "buy":
            sl_dist = (entry["price"] - entry["sl"]) / PIP
            tp_dist = (entry["tp"] - entry["price"]) / PIP
            profit_dist = (exit_ev["price"] - entry["price"]) / PIP
        else:  # sell
            sl_dist = (entry["sl"] - entry["price"]) / PIP
            tp_dist = (entry["price"] - entry["tp"]) / PIP
            profit_dist = (entry["price"] - exit_ev["price"]) / PIP

        sl_dist = abs(sl_dist)
        tp_dist = abs(tp_dist)

        planned_rr = tp_dist / sl_dist if sl_dist > 0 else 0
        actual_rr = profit_dist / sl_dist if sl_dist > 0 else 0

        had_modify = modify is not None

        # Result category
        if exit_ev["action"] == "t/p":
            result = "WIN"
        elif exit_ev["action"] == "s/l":
            if had_modify and abs(exit_ev["profit"]) < 15:  # small profit/loss after BE move
                result = "BREAKEVEN"
            else:
                result = "LOSS"
        else:
            result = "UNKNOWN"

        profit_dollars = exit_ev["profit"]
        balance_after = exit_ev["balance"]

        # Month key
        month_key = entry_time.strftime("%Y-%m")

        trades.append({
            "ticket": ticket,
            "direction": direction,
            "entry_time": entry_time,
            "exit_time": exit_time,
            "duration_min": duration_min,
            "day_of_week": day_of_week,
            "hour": hour,
            "session": session,
            "lots": entry["lots"],
            "entry_price": entry["price"],
            "exit_price": exit_ev["price"],
            "sl_price": entry["sl"],
            "tp_price": entry["tp"],
            "sl_dist_pips": sl_dist,
            "tp_dist_pips": tp_dist,
            "profit_dist_pips": profit_dist,
            "planned_rr": planned_rr,
            "actual_rr": actual_rr,
            "had_modify": had_modify,
            "result": result,
            "profit": profit_dollars,
            "balance_after": balance_after,
            "month_key": month_key,
        })

    return trades

# =============================================================================
# LOAD CANDLE DATA
# =============================================================================
def load_h1_data():
    """Load H1 candles, return dict keyed by (date, hour)"""
    candles = []
    with open(H1_FILE, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        for row in reader:
            if len(row) < 7:
                continue
            try:
                dt_str = row[0].strip() + " " + row[1].strip()
                dt = datetime.strptime(dt_str, "%Y.%m.%d %H:%M")
                if dt.year < 2023:
                    continue
                o, h, l, c = float(row[2]), float(row[3]), float(row[4]), float(row[5])
                candles.append({"dt": dt, "open": o, "high": h, "low": l, "close": c})
            except (ValueError, IndexError):
                continue

    candles.sort(key=lambda x: x["dt"])
    return candles

def load_m15_data():
    """Load M15 candles, return list sorted by time"""
    candles = []
    with open(M15_FILE, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        for row in reader:
            if len(row) < 7:
                continue
            try:
                dt_str = row[0].strip() + " " + row[1].strip()
                dt = datetime.strptime(dt_str, "%Y.%m.%d %H:%M")
                o, h, l, c = float(row[2]), float(row[3]), float(row[4]), float(row[5])
                candles.append({"dt": dt, "open": o, "high": h, "low": l, "close": c, "range": h - l})
            except (ValueError, IndexError):
                continue

    candles.sort(key=lambda x: x["dt"])
    return candles

def compute_h1_atr(h1_candles, target_dt, period=14):
    """Compute ATR(14) on H1 data at the given datetime"""
    # Find candles up to target_dt
    relevant = [c for c in h1_candles if c["dt"] <= target_dt]
    if len(relevant) < period + 1:
        return None

    recent = relevant[-(period + 1):]

    trs = []
    for i in range(1, len(recent)):
        prev_close = recent[i-1]["close"]
        curr = recent[i]
        tr = max(
            curr["high"] - curr["low"],
            abs(curr["high"] - prev_close),
            abs(curr["low"] - prev_close)
        )
        trs.append(tr)

    if len(trs) < period:
        return None

    return sum(trs[-period:]) / period

def find_m15_range(m15_candles, target_dt):
    """Find M15 candle range at entry time"""
    # Find closest M15 candle at or before target_dt
    best = None
    # Binary search approach
    lo, hi = 0, len(m15_candles) - 1
    while lo <= hi:
        mid = (lo + hi) // 2
        if m15_candles[mid]["dt"] <= target_dt:
            best = mid
            lo = mid + 1
        else:
            hi = mid - 1

    if best is not None:
        return m15_candles[best]["range"]
    return None

# =============================================================================
# ANALYSIS FUNCTIONS
# =============================================================================
def compute_group_stats(trades_subset):
    """Compute stats for a group of trades"""
    if not trades_subset:
        return {"count": 0, "wins": 0, "losses": 0, "bes": 0, "winrate": 0,
                "net": 0, "gross_win": 0, "gross_loss": 0, "pf": "N/A"}

    wins = [t for t in trades_subset if t["result"] == "WIN"]
    losses = [t for t in trades_subset if t["result"] == "LOSS"]
    bes = [t for t in trades_subset if t["result"] == "BREAKEVEN"]

    gross_win = sum(t["profit"] for t in wins) + sum(t["profit"] for t in bes if t["profit"] > 0)
    gross_loss = abs(sum(t["profit"] for t in losses) + sum(t["profit"] for t in bes if t["profit"] < 0))
    net = sum(t["profit"] for t in trades_subset)

    count = len(trades_subset)
    wr = len(wins) / count * 100 if count > 0 else 0

    return {
        "count": count,
        "wins": len(wins),
        "losses": len(losses),
        "bes": len(bes),
        "winrate": wr,
        "net": net,
        "gross_win": gross_win,
        "gross_loss": gross_loss,
        "pf": fmt_pf(gross_win, gross_loss)
    }

def consecutive_analysis(trades):
    """Find consecutive win/loss streaks"""
    max_wins = 0
    max_losses = 0
    curr_wins = 0
    curr_losses = 0

    losing_streaks = []  # list of (start_idx, length, trades)
    current_streak_start = None

    for i, t in enumerate(trades):
        if t["result"] == "WIN":
            curr_wins += 1
            if curr_losses > 0:
                if curr_losses >= 4:
                    streak_trades = trades[current_streak_start:i]
                    losing_streaks.append((current_streak_start, curr_losses, streak_trades))
                curr_losses = 0
            if curr_wins == 1:
                pass  # start of potential win streak
            max_wins = max(max_wins, curr_wins)
        elif t["result"] == "LOSS":
            curr_losses += 1
            if curr_wins > 0:
                curr_wins = 0
            if curr_losses == 1:
                current_streak_start = i
            max_losses = max(max_losses, curr_losses)
        else:  # BE
            # BEs break streaks
            if curr_losses >= 4:
                streak_trades = trades[current_streak_start:i]
                losing_streaks.append((current_streak_start, curr_losses, streak_trades))
            curr_wins = 0
            curr_losses = 0

    # Check final streak
    if curr_losses >= 4:
        streak_trades = trades[current_streak_start:len(trades)]
        losing_streaks.append((current_streak_start, curr_losses, streak_trades))

    return max_wins, max_losses, losing_streaks

# =============================================================================
# MAIN ANALYSIS
# =============================================================================
def main():
    print()
    print("=" * 120)
    print("  EMA PULLBACK EA v2 - COMPREHENSIVE BACKTEST ANALYSIS")
    print("  527 trades | Apr 2023 - Apr 2026 | EURUSD")
    print("=" * 120)

    # Parse trades
    trades = parse_trades()
    print(f"\n  Parsed {len(trades)} complete trades from history file")

    # Load candle data
    print("  Loading H1 candle data...")
    h1_candles = load_h1_data()
    print(f"  Loaded {len(h1_candles)} H1 candles (from 2023+)")

    print("  Loading M15 candle data...")
    m15_candles = load_m15_data()
    print(f"  Loaded {len(m15_candles)} M15 candles")

    # Compute ATR for each trade
    print("  Computing H1 ATR(14) for each trade...")
    for t in trades:
        t["h1_atr"] = compute_h1_atr(h1_candles, t["entry_time"])
        t["h1_atr_pips"] = t["h1_atr"] / PIP if t["h1_atr"] else None
        t["m15_range"] = find_m15_range(m15_candles, t["entry_time"])
        t["m15_range_pips"] = t["m15_range"] / PIP if t["m15_range"] else None

    # =========================================================================
    # B. GLOBAL STATS
    # =========================================================================
    print_header("B. GLOBAL STATISTICS")

    wins = [t for t in trades if t["result"] == "WIN"]
    losses = [t for t in trades if t["result"] == "LOSS"]
    bes = [t for t in trades if t["result"] == "BREAKEVEN"]

    total = len(trades)
    net_profit = sum(t["profit"] for t in trades)
    gross_win = sum(t["profit"] for t in wins)
    gross_loss = abs(sum(t["profit"] for t in losses))

    avg_win = gross_win / len(wins) if wins else 0
    avg_loss = -gross_loss / len(losses) if losses else 0
    avg_be = sum(t["profit"] for t in bes) / len(bes) if bes else 0

    planned_rrs = [t["planned_rr"] for t in trades]
    actual_rrs = [t["actual_rr"] for t in trades if t["result"] == "WIN"]

    print(f"  Total trades:       {total}")
    print(f"  Wins:               {len(wins)} ({len(wins)/total*100:.1f}%)")
    print(f"  Losses:             {len(losses)} ({len(losses)/total*100:.1f}%)")
    print(f"  Breakevens:         {len(bes)} ({len(bes)/total*100:.1f}%)")
    print(f"  Win rate:           {len(wins)/total*100:.1f}%")
    print(f"  Win rate (excl BE): {len(wins)/(len(wins)+len(losses))*100:.1f}%")
    print()
    print(f"  Starting balance:   $10,000.00")
    print(f"  Final balance:      {fmt_money(trades[-1]['balance_after'])}")
    print(f"  Net profit:         {fmt_money(net_profit)}")
    print(f"  Gross wins:         {fmt_money(gross_win)}")
    print(f"  Gross losses:       {fmt_money(gross_loss)}")
    print(f"  Profit factor:      {fmt_pf(gross_win, gross_loss)}")
    print()
    print(f"  Avg win:            {fmt_money(avg_win)}")
    print(f"  Avg loss:           {fmt_money(avg_loss)}")
    print(f"  Avg breakeven:      {fmt_money(avg_be)}")
    print()
    print(f"  Avg planned RR:     {sum(planned_rrs)/len(planned_rrs):.2f}")
    print(f"  Avg actual RR (W):  {sum(actual_rrs)/len(actual_rrs):.2f}" if actual_rrs else "  Avg actual RR: N/A")
    print(f"  Min planned RR:     {min(planned_rrs):.2f}")
    print(f"  Max planned RR:     {max(planned_rrs):.2f}")

    # Planned RR distribution
    print_subheader("Planned RR Distribution")
    rr_buckets = defaultdict(int)
    for rr in planned_rrs:
        bucket = f"{int(rr*2)/2:.1f}-{int(rr*2)/2+0.5:.1f}"
        if rr < 2.0:
            bucket = "<2.0"
        elif rr < 2.5:
            bucket = "2.0-2.5"
        elif rr < 3.0:
            bucket = "2.5-3.0"
        elif rr < 3.5:
            bucket = "3.0-3.5"
        else:
            bucket = "3.5+"
        rr_buckets[bucket] += 1

    for bucket in ["<2.0", "2.0-2.5", "2.5-3.0", "3.0-3.5", "3.5+"]:
        count = rr_buckets.get(bucket, 0)
        print(f"    {bucket:>8}: {count:>4} trades ({count/total*100:.1f}%)")

    # Consecutive analysis
    print_subheader("Consecutive Wins/Losses")
    max_w, max_l, _ = consecutive_analysis(trades)
    print(f"  Max consecutive wins:   {max_w}")
    print(f"  Max consecutive losses: {max_l}")

    # =========================================================================
    # C. TEMPORAL ANALYSIS
    # =========================================================================
    print_header("C. TEMPORAL ANALYSIS")

    # --- By Hour ---
    print_subheader("By Hour of Entry")
    headers = ["Hour", "Trades", "Wins", "Losses", "BEs", "WinRate", "Net $", "PF"]
    rows = []
    hour_stats = {}
    for h in range(0, 24):
        subset = [t for t in trades if t["hour"] == h]
        if not subset:
            continue
        s = compute_group_stats(subset)
        hour_stats[h] = s
        rows.append([
            f"{h:02d}:00", s["count"], s["wins"], s["losses"], s["bes"],
            fmt_pct(s["winrate"]), fmt_money(s["net"]), s["pf"]
        ])
    print_table(headers, rows, [8, 8, 8, 8, 6, 10, 12, 8])

    # Worst hours
    print_subheader("WORST Hours (by net profit)")
    sorted_hours = sorted(hour_stats.items(), key=lambda x: x[1]["net"])
    for h, s in sorted_hours[:5]:
        if s["net"] < 0:
            print(f"    {h:02d}:00  ->  {fmt_money(s['net']):>10}  |  {s['count']} trades, WR={fmt_pct(s['winrate'])}, PF={s['pf']}")

    # --- By Day of Week ---
    print_subheader("By Day of Week")
    day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    headers = ["Day", "Trades", "Wins", "Losses", "BEs", "WinRate", "Net $", "PF"]
    rows = []
    day_stats = {}
    for d in range(5):  # Mon-Fri
        subset = [t for t in trades if t["day_of_week"] == d]
        if not subset:
            continue
        s = compute_group_stats(subset)
        day_stats[d] = s
        rows.append([
            day_names[d], s["count"], s["wins"], s["losses"], s["bes"],
            fmt_pct(s["winrate"]), fmt_money(s["net"]), s["pf"]
        ])
    print_table(headers, rows, [8, 8, 8, 8, 6, 10, 12, 8])

    # --- By Month ---
    print_subheader("By Calendar Month (Jan-Dec)")
    headers = ["Month", "Trades", "Wins", "Losses", "BEs", "WinRate", "Net $", "PF"]
    rows = []
    month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    for m in range(1, 13):
        subset = [t for t in trades if t["entry_time"].month == m]
        if not subset:
            continue
        s = compute_group_stats(subset)
        rows.append([
            month_names[m-1], s["count"], s["wins"], s["losses"], s["bes"],
            fmt_pct(s["winrate"]), fmt_money(s["net"]), s["pf"]
        ])
    print_table(headers, rows, [8, 8, 8, 8, 6, 10, 12, 8])

    # --- By Session ---
    print_subheader("By Session")
    headers = ["Session", "Trades", "Wins", "Losses", "BEs", "WinRate", "Net $", "PF"]
    rows = []
    for sess in ["London", "NY", "Off"]:
        subset = [t for t in trades if t["session"] == sess]
        if not subset:
            continue
        s = compute_group_stats(subset)
        rows.append([
            sess, s["count"], s["wins"], s["losses"], s["bes"],
            fmt_pct(s["winrate"]), fmt_money(s["net"]), s["pf"]
        ])
    print_table(headers, rows, [10, 8, 8, 8, 6, 10, 12, 8])

    # --- Heatmap: Hour x Day ---
    print_subheader("Profit Heatmap: Hour x Day")
    # Header row
    line = "          "
    for d in range(5):
        line += f"{day_names[d]:>10}"
    line += f"{'TOTAL':>12}"
    print(line)
    print("  " + "-" * 74)

    for h in range(0, 24):
        any_trades = any(t for t in trades if t["hour"] == h)
        if not any_trades:
            continue
        line = f"  {h:02d}:00   "
        row_total = 0
        for d in range(5):
            subset = [t for t in trades if t["hour"] == h and t["day_of_week"] == d]
            if subset:
                net = sum(t["profit"] for t in subset)
                row_total += net
                line += f"{net:>10.0f}"
            else:
                line += f"{'---':>10}"
        line += f"{row_total:>12.0f}"
        print(line)

    # Day totals
    line = "  TOTAL   "
    for d in range(5):
        subset = [t for t in trades if t["day_of_week"] == d]
        net = sum(t["profit"] for t in subset)
        line += f"{net:>10.0f}"
    line += f"{sum(t['profit'] for t in trades):>12.0f}"
    print("  " + "-" * 74)
    print(line)

    # Worst heatmap cells
    print_subheader("WORST Hour x Day Combos (net < -$100)")
    heatmap_cells = []
    for h in range(0, 24):
        for d in range(5):
            subset = [t for t in trades if t["hour"] == h and t["day_of_week"] == d]
            if subset:
                net = sum(t["profit"] for t in subset)
                s = compute_group_stats(subset)
                heatmap_cells.append((h, d, net, s))
    heatmap_cells.sort(key=lambda x: x[2])
    headers = ["Hour", "Day", "Trades", "WR", "Net $", "PF"]
    rows = []
    for h, d, net, s in heatmap_cells:
        if net < -100:
            rows.append([f"{h:02d}:00", day_names[d], s["count"], fmt_pct(s["winrate"]), fmt_money(net), s["pf"]])
    print_table(headers, rows, [8, 8, 8, 10, 12, 8])

    # BEST heatmap cells
    print_subheader("BEST Hour x Day Combos (net > $500)")
    headers = ["Hour", "Day", "Trades", "WR", "Net $", "PF"]
    rows = []
    for h, d, net, s in sorted(heatmap_cells, key=lambda x: -x[2]):
        if net > 500:
            rows.append([f"{h:02d}:00", day_names[d], s["count"], fmt_pct(s["winrate"]), fmt_money(net), s["pf"]])
    print_table(headers, rows, [8, 8, 8, 10, 12, 8])

    # =========================================================================
    # D. VOLATILITY ANALYSIS
    # =========================================================================
    print_header("D. VOLATILITY ANALYSIS (H1 ATR)")

    trades_with_atr = [t for t in trades if t["h1_atr_pips"] is not None]
    print(f"  Trades with ATR data: {len(trades_with_atr)} / {len(trades)}")

    if trades_with_atr:
        atrs = sorted([t["h1_atr_pips"] for t in trades_with_atr])
        q1 = atrs[len(atrs)//4]
        q2 = atrs[len(atrs)//2]
        q3 = atrs[3*len(atrs)//4]

        print(f"  ATR(14) H1 range: {min(atrs):.1f} - {max(atrs):.1f} pips")
        print(f"  Quartiles: Q1={q1:.1f}, Q2={q2:.1f}, Q3={q3:.1f}")

        print_subheader("ATR Quartile Analysis")
        headers = ["Quartile", "ATR Range", "Trades", "Wins", "Losses", "BEs", "WinRate", "Net $", "PF"]
        rows = []
        quartile_bounds = [(0, q1, "Q1 (Low)"), (q1, q2, "Q2"), (q2, q3, "Q3"), (q3, 9999, "Q4 (High)")]
        for lo, hi, label in quartile_bounds:
            subset = [t for t in trades_with_atr if lo <= t["h1_atr_pips"] < hi]
            if label == "Q4 (High)":
                subset = [t for t in trades_with_atr if t["h1_atr_pips"] >= lo]
            s = compute_group_stats(subset)
            atr_range = f"{lo:.0f}-{hi:.0f}" if hi < 9999 else f"{lo:.0f}+"
            rows.append([
                label, atr_range, s["count"], s["wins"], s["losses"], s["bes"],
                fmt_pct(s["winrate"]), fmt_money(s["net"]), s["pf"]
            ])
        print_table(headers, rows, [12, 12, 8, 8, 8, 6, 10, 12, 8])

        # Find optimal ATR threshold - scan actual range
        atr_min_int = int(min(atrs))
        atr_max_int = int(max(atrs)) + 1

        print_subheader("ATR Threshold Optimization (filter OUT trades below threshold)")
        headers = ["Min ATR", "Trades", "Wins", "WinRate", "Net $", "PF", "Excluded", "Excl Net $"]
        rows = []
        best_pf_atr = 0
        best_pf_val = 0
        for threshold_10 in range(atr_min_int * 10, min(atr_max_int * 10, 500), 5):  # step 0.5 pips
            threshold = threshold_10 / 10.0
            included = [t for t in trades_with_atr if t["h1_atr_pips"] >= threshold]
            excluded = [t for t in trades_with_atr if t["h1_atr_pips"] < threshold]
            if not included or len(included) < 50:
                continue
            s_in = compute_group_stats(included)
            s_ex = compute_group_stats(excluded)
            try:
                pf_val = s_in["gross_win"] / s_in["gross_loss"] if s_in["gross_loss"] > 0 else 99
            except:
                pf_val = 0
            if pf_val > best_pf_val:
                best_pf_val = pf_val
                best_pf_atr = threshold
            # Only print every 1 pip for readability
            if threshold_10 % 10 == 0:
                rows.append([
                    f"{threshold:.0f} pips", s_in["count"], s_in["wins"], fmt_pct(s_in["winrate"]),
                    fmt_money(s_in["net"]), s_in["pf"], s_ex["count"], fmt_money(s_ex["net"])
                ])
        print_table(headers, rows, [10, 8, 8, 10, 12, 8, 10, 12])
        print(f"\n  >>> Best min ATR threshold (min 50 trades): {best_pf_atr:.1f} pips (PF={best_pf_val:.2f})")
        best_pf_atr_saved = best_pf_atr

        # Also show what excluding ABOVE a threshold does
        print_subheader("ATR Threshold Optimization (filter OUT trades ABOVE threshold)")
        headers = ["Max ATR", "Trades", "Wins", "WinRate", "Net $", "PF", "Excluded", "Excl Net $"]
        rows = []
        best_max_pf_atr = 999
        best_max_pf_val = 0
        for threshold_10 in range(atr_min_int * 10 + 20, atr_max_int * 10, 10):
            threshold = threshold_10 / 10.0
            included = [t for t in trades_with_atr if t["h1_atr_pips"] <= threshold]
            excluded = [t for t in trades_with_atr if t["h1_atr_pips"] > threshold]
            if not included or len(included) < 50:
                continue
            s_in = compute_group_stats(included)
            s_ex = compute_group_stats(excluded)
            try:
                pf_val = s_in["gross_win"] / s_in["gross_loss"] if s_in["gross_loss"] > 0 else 99
            except:
                pf_val = 0
            if pf_val > best_max_pf_val:
                best_max_pf_val = pf_val
                best_max_pf_atr = threshold
            rows.append([
                f"{threshold:.0f} pips", s_in["count"], s_in["wins"], fmt_pct(s_in["winrate"]),
                fmt_money(s_in["net"]), s_in["pf"], s_ex["count"], fmt_money(s_ex["net"])
            ])
        print_table(headers, rows, [10, 8, 8, 10, 12, 8, 10, 12])
        print(f"\n  >>> Best max ATR threshold (min 50 trades): {best_max_pf_atr:.0f} pips (PF={best_max_pf_val:.2f})")

        # Combined ATR band analysis
        print_subheader("ATR Band Analysis (keep only trades in band)")
        headers = ["ATR Band", "Trades", "Wins", "WinRate", "Net $", "PF"]
        rows = []
        best_band = None
        best_band_pf = 0
        for lo_10 in range(60, 160, 10):
            for hi_10 in range(lo_10 + 30, 420, 10):
                lo_v = lo_10 / 10.0
                hi_v = hi_10 / 10.0
                subset = [t for t in trades_with_atr if lo_v <= t["h1_atr_pips"] <= hi_v]
                if len(subset) < 100:
                    continue
                s = compute_group_stats(subset)
                try:
                    pf = s["gross_win"] / s["gross_loss"] if s["gross_loss"] > 0 else 99
                except:
                    pf = 0
                if pf > best_band_pf:
                    best_band_pf = pf
                    best_band = (lo_v, hi_v, s)
        if best_band:
            lo_v, hi_v, s = best_band
            print(f"  Best ATR band: {lo_v:.1f} - {hi_v:.1f} pips")
            print(f"  Trades: {s['count']}, WR={fmt_pct(s['winrate'])}, PF={s['pf']}, Net={fmt_money(s['net'])}")

    # M15 range analysis
    print_subheader("M15 Candle Range at Entry")
    trades_with_m15 = [t for t in trades if t["m15_range_pips"] is not None]
    if trades_with_m15:
        win_ranges = [t["m15_range_pips"] for t in trades_with_m15 if t["result"] == "WIN"]
        loss_ranges = [t["m15_range_pips"] for t in trades_with_m15 if t["result"] == "LOSS"]
        be_ranges = [t["m15_range_pips"] for t in trades_with_m15 if t["result"] == "BREAKEVEN"]
        print(f"  Avg M15 range (wins):   {sum(win_ranges)/len(win_ranges):.1f} pips" if win_ranges else "  No win data")
        print(f"  Avg M15 range (losses): {sum(loss_ranges)/len(loss_ranges):.1f} pips" if loss_ranges else "  No loss data")
        print(f"  Avg M15 range (BEs):    {sum(be_ranges)/len(be_ranges):.1f} pips" if be_ranges else "  No BE data")

    # =========================================================================
    # E. TRADE DURATION ANALYSIS
    # =========================================================================
    print_header("E. TRADE DURATION ANALYSIS")

    win_durations = [t["duration_min"] for t in wins]
    loss_durations = [t["duration_min"] for t in losses]
    be_durations = [t["duration_min"] for t in bes]

    print(f"  Avg duration (all):    {sum(t['duration_min'] for t in trades)/len(trades):.0f} min")
    print(f"  Avg duration (wins):   {sum(win_durations)/len(win_durations):.0f} min" if win_durations else "")
    print(f"  Avg duration (losses): {sum(loss_durations)/len(loss_durations):.0f} min" if loss_durations else "")
    print(f"  Avg duration (BEs):    {sum(be_durations)/len(be_durations):.0f} min" if be_durations else "")

    # Quick vs slow wins
    print_subheader("Win Duration Buckets")
    duration_buckets = [
        ("<30 min", 0, 30),
        ("30-60 min", 30, 60),
        ("1-2h", 60, 120),
        ("2-4h", 120, 240),
        ("4-8h", 240, 480),
        (">8h", 480, 99999)
    ]
    headers = ["Duration", "All", "Wins", "Losses", "BEs", "WinRate", "Net $", "PF"]
    rows = []
    for label, lo, hi in duration_buckets:
        subset = [t for t in trades if lo <= t["duration_min"] < hi]
        if not subset:
            continue
        s = compute_group_stats(subset)
        rows.append([
            label, s["count"], s["wins"], s["losses"], s["bes"],
            fmt_pct(s["winrate"]), fmt_money(s["net"]), s["pf"]
        ])
    print_table(headers, rows, [12, 8, 8, 8, 6, 10, 12, 8])

    # Key finding: quick trades (<1h) are devastating
    quick_trades = [t for t in trades if t["duration_min"] < 60]
    slow_trades = [t for t in trades if t["duration_min"] >= 60]
    s_quick = compute_group_stats(quick_trades)
    s_slow = compute_group_stats(slow_trades)
    print(f"\n  KEY FINDING:")
    print(f"    Trades <1h:  {s_quick['count']} trades, WR={fmt_pct(s_quick['winrate'])}, PF={s_quick['pf']}, Net={fmt_money(s_quick['net'])}")
    print(f"    Trades >=1h: {s_slow['count']} trades, WR={fmt_pct(s_slow['winrate'])}, PF={s_slow['pf']}, Net={fmt_money(s_slow['net'])}")
    print(f"    >>> Trades closed in <1h are almost all losses. This suggests quick SL hits.")

    # =========================================================================
    # F. CONSECUTIVE LOSS ANALYSIS
    # =========================================================================
    print_header("F. CONSECUTIVE LOSS ANALYSIS")

    _, _, losing_streaks = consecutive_analysis(trades)

    if losing_streaks:
        print(f"  Found {len(losing_streaks)} losing streaks of 4+ trades:")
        print()
        headers = ["#", "Start Date", "End Date", "Length", "Total Loss", "Sessions", "Directions", "Avg ATR"]
        rows = []
        for idx, (start_i, length, streak_trades) in enumerate(losing_streaks):
            total_loss = sum(t["profit"] for t in streak_trades)
            sessions = set(t["session"] for t in streak_trades)
            directions = set(t["direction"] for t in streak_trades)
            atrs = [t["h1_atr_pips"] for t in streak_trades if t["h1_atr_pips"] is not None]
            avg_atr = sum(atrs)/len(atrs) if atrs else 0

            rows.append([
                idx+1,
                streak_trades[0]["entry_time"].strftime("%Y-%m-%d"),
                streak_trades[-1]["entry_time"].strftime("%Y-%m-%d"),
                length,
                fmt_money(total_loss),
                "/".join(sessions),
                "/".join(directions),
                f"{avg_atr:.1f}"
            ])
        print_table(headers, rows, [4, 14, 14, 8, 12, 14, 14, 10])
    else:
        print("  No losing streaks of 4+ trades found")

    # =========================================================================
    # G. ENTRY DIRECTION ANALYSIS
    # =========================================================================
    print_header("G. ENTRY DIRECTION ANALYSIS")

    headers = ["Direction", "Trades", "Wins", "Losses", "BEs", "WinRate", "Net $", "PF", "Avg Win", "Avg Loss"]
    rows = []
    for dir_name in ["buy", "sell"]:
        subset = [t for t in trades if t["direction"] == dir_name]
        if not subset:
            continue
        s = compute_group_stats(subset)
        dir_wins = [t for t in subset if t["result"] == "WIN"]
        dir_losses = [t for t in subset if t["result"] == "LOSS"]
        avg_w = sum(t["profit"] for t in dir_wins) / len(dir_wins) if dir_wins else 0
        avg_l = sum(t["profit"] for t in dir_losses) / len(dir_losses) if dir_losses else 0
        rows.append([
            dir_name.upper(), s["count"], s["wins"], s["losses"], s["bes"],
            fmt_pct(s["winrate"]), fmt_money(s["net"]), s["pf"],
            fmt_money(avg_w), fmt_money(avg_l)
        ])
    print_table(headers, rows, [10, 8, 8, 8, 6, 10, 12, 8, 10, 10])

    # =========================================================================
    # H. SL DISTANCE ANALYSIS
    # =========================================================================
    print_header("H. SL DISTANCE ANALYSIS")

    sl_buckets = [
        ("<10 pips", 0, 10),
        ("10-15", 10, 15),
        ("15-20", 15, 20),
        ("20-25", 20, 25),
        ("25-30", 25, 30),
        (">30 pips", 30, 999)
    ]
    headers = ["SL Range", "Trades", "Wins", "Losses", "BEs", "WinRate", "Net $", "PF", "Avg SL"]
    rows = []
    for label, lo, hi in sl_buckets:
        subset = [t for t in trades if lo <= t["sl_dist_pips"] < hi]
        if not subset:
            continue
        s = compute_group_stats(subset)
        avg_sl = sum(t["sl_dist_pips"] for t in subset) / len(subset)
        rows.append([
            label, s["count"], s["wins"], s["losses"], s["bes"],
            fmt_pct(s["winrate"]), fmt_money(s["net"]), s["pf"], f"{avg_sl:.1f}"
        ])
    print_table(headers, rows, [12, 8, 8, 8, 6, 10, 12, 8, 8])

    # Overall SL stats
    all_sls = [t["sl_dist_pips"] for t in trades]
    print(f"\n  SL distance: min={min(all_sls):.1f}, max={max(all_sls):.1f}, avg={sum(all_sls)/len(all_sls):.1f}, median={sorted(all_sls)[len(all_sls)//2]:.1f}")

    # =========================================================================
    # I. MONTHLY EQUITY CURVE
    # =========================================================================
    print_header("I. MONTHLY EQUITY CURVE & DRAWDOWN")

    # Group trades by month
    monthly = defaultdict(list)
    for t in trades:
        monthly[t["month_key"]].append(t)

    sorted_months = sorted(monthly.keys())
    headers = ["Month", "Trades", "Wins", "Losses", "BEs", "WR", "Net $", "End Bal", "DD from Peak"]
    rows = []
    peak_balance = 10000

    for mk in sorted_months:
        month_trades = monthly[mk]
        s = compute_group_stats(month_trades)
        end_bal = month_trades[-1]["balance_after"]
        peak_balance = max(peak_balance, end_bal)
        dd = (peak_balance - end_bal) / peak_balance * 100

        rows.append([
            mk, s["count"], s["wins"], s["losses"], s["bes"],
            fmt_pct(s["winrate"]), fmt_money(s["net"]), fmt_money(end_bal),
            f"{dd:.1f}%"
        ])
    print_table(headers, rows, [10, 8, 8, 8, 6, 8, 12, 14, 12])

    # Max drawdown
    print_subheader("Drawdown Analysis")
    running_peak = 10000
    max_dd = 0
    max_dd_peak = 0
    max_dd_trough = 0
    max_dd_peak_date = None
    max_dd_trough_date = None

    for t in trades:
        bal = t["balance_after"]
        if bal > running_peak:
            running_peak = bal
        dd = running_peak - bal
        if dd > max_dd:
            max_dd = dd
            max_dd_peak = running_peak
            max_dd_trough = bal
            max_dd_trough_date = t["exit_time"]

    # Find peak date
    for t in trades:
        if t["balance_after"] >= max_dd_peak:
            max_dd_peak_date = t["exit_time"]
            if t["exit_time"] < max_dd_trough_date:
                break

    print(f"  Max drawdown: {fmt_money(max_dd)} ({max_dd/max_dd_peak*100:.1f}%)")
    print(f"  Peak: {fmt_money(max_dd_peak)} on {max_dd_peak_date.strftime('%Y-%m-%d') if max_dd_peak_date else 'N/A'}")
    print(f"  Trough: {fmt_money(max_dd_trough)} on {max_dd_trough_date.strftime('%Y-%m-%d') if max_dd_trough_date else 'N/A'}")

    # =========================================================================
    # J. SPECIFIC RECOMMENDATIONS
    # =========================================================================
    print_header("J. SPECIFIC RECOMMENDATIONS (RANKED BY ESTIMATED IMPACT)")

    print()
    rec_num = 0

    # 1. Hours to block
    print_subheader("1. Hours to Block")
    bad_hours = [(h, s) for h, s in hour_stats.items() if s["net"] < -50]
    bad_hours.sort(key=lambda x: x[1]["net"])
    total_hour_savings = 0
    for h, s in bad_hours:
        impact = abs(s["net"])
        total_hour_savings += impact
        print(f"    BLOCK {h:02d}:00  ->  Save {fmt_money(impact):>10}  |  {s['count']} trades, WR={fmt_pct(s['winrate'])}, PF={s['pf']}")
    if bad_hours:
        print(f"    >>> TOTAL ESTIMATED SAVINGS: {fmt_money(total_hour_savings)}")
    else:
        print("    No clearly unprofitable hours found (all hours net positive)")
        print("    However, some HOUR+DAY combos are deeply negative:")
        # Show worst hour+day combos
        all_combos = []
        for h in range(0, 24):
            for d in range(5):
                subset = [t for t in trades if t["hour"] == h and t["day_of_week"] == d]
                if subset:
                    net = sum(t["profit"] for t in subset)
                    all_combos.append((h, d, net, len(subset)))
        all_combos.sort(key=lambda x: x[2])
        combo_savings = 0
        for h, d, net, cnt in all_combos[:8]:
            if net < -100:
                print(f"      BLOCK {h:02d}:00/{day_names[d]}  ->  Save {fmt_money(abs(net)):>10}  |  {cnt} trades")
                combo_savings += abs(net)
        if combo_savings > 0:
            print(f"      >>> TOTAL COMBO SAVINGS: {fmt_money(combo_savings)}")

    # 2. Days to block
    print_subheader("2. Days to Block")
    bad_days = [(d, s) for d, s in day_stats.items() if s["net"] < -50]
    bad_days.sort(key=lambda x: x[1]["net"])
    for d, s in bad_days:
        print(f"    BLOCK {day_names[d]}  ->  Save {fmt_money(abs(s['net'])):>10}  |  {s['count']} trades, WR={fmt_pct(s['winrate'])}, PF={s['pf']}")
    if not bad_days:
        # Still show worst day
        worst_day = min(day_stats.items(), key=lambda x: x[1]["net"])
        d, s = worst_day
        print(f"    Worst day: {day_names[d]} ({fmt_money(s['net'])}) - {s['count']} trades, WR={fmt_pct(s['winrate'])}")
        print(f"    No day is clearly loss-making enough to block entirely")

    # 3. Verify Friday is blocked
    print_subheader("3. Friday Filter Verification")
    fri_trades = [t for t in trades if t["day_of_week"] == 4]
    if fri_trades:
        fri_s = compute_group_stats(fri_trades)
        print(f"    Friday trades found: {fri_s['count']} -> Net={fmt_money(fri_s['net'])}")
        # Check temporal distribution
        early_fri = [t for t in fri_trades if t["entry_time"] < datetime(2025, 1, 1)]
        late_fri = [t for t in fri_trades if t["entry_time"] >= datetime(2025, 1, 1)]
        if early_fri:
            print(f"    Before 2025: {len(early_fri)} trades")
        if late_fri:
            print(f"    After 2025:  {len(late_fri)} trades (should be 0 if Friday filter is active)")
    else:
        print(f"    No Friday trades - Friday filter is ACTIVE")

    # 4. ATR threshold
    print_subheader("4. Optimal ATR Threshold")
    if trades_with_atr:
        print(f"    Recommended MIN ATR filter: {best_pf_atr_saved:.1f} pips")
        below = [t for t in trades_with_atr if t["h1_atr_pips"] < best_pf_atr_saved]
        if below:
            s_below = compute_group_stats(below)
            print(f"    Filtering out {s_below['count']} trades below {best_pf_atr_saved:.1f} pips ATR")
            print(f"    Net of excluded trades: {fmt_money(s_below['net'])}")
            if s_below['net'] < 0:
                print(f"    Estimated SAVINGS: {fmt_money(abs(s_below['net']))}")
            else:
                print(f"    WARNING: excluded trades are net positive - filter may hurt performance")

    # 5. SL distance
    print_subheader("5. Optimal SL Distance")
    best_sl_bucket = None
    best_sl_pf = 0
    for label, lo, hi in sl_buckets:
        subset = [t for t in trades if lo <= t["sl_dist_pips"] < hi]
        if not subset or len(subset) < 20:
            continue
        s = compute_group_stats(subset)
        try:
            pf = s["gross_win"] / s["gross_loss"] if s["gross_loss"] > 0 else 99
        except:
            pf = 0
        if pf > best_sl_pf:
            best_sl_pf = pf
            best_sl_bucket = (label, lo, hi, s)

    if best_sl_bucket:
        label, lo, hi, s = best_sl_bucket
        print(f"    Best SL bucket: {label} (PF={s['pf']}, WR={fmt_pct(s['winrate'])}, {s['count']} trades)")
        # Impact of removing worst buckets
        for label2, lo2, hi2 in sl_buckets:
            subset2 = [t for t in trades if lo2 <= t["sl_dist_pips"] < hi2]
            if subset2 and len(subset2) >= 10:
                s2 = compute_group_stats(subset2)
                if s2["net"] < -100:
                    print(f"    Remove SL bucket {label2}: save {fmt_money(abs(s2['net']))}")

    # 6. Direction bias
    print_subheader("6. Direction Analysis")
    buy_trades = [t for t in trades if t["direction"] == "buy"]
    sell_trades = [t for t in trades if t["direction"] == "sell"]
    s_buy = compute_group_stats(buy_trades)
    s_sell = compute_group_stats(sell_trades)
    print(f"    BUY:  {s_buy['count']} trades, WR={fmt_pct(s_buy['winrate'])}, PF={s_buy['pf']}, Net={fmt_money(s_buy['net'])}")
    print(f"    SELL: {s_sell['count']} trades, WR={fmt_pct(s_sell['winrate'])}, PF={s_sell['pf']}, Net={fmt_money(s_sell['net'])}")
    if s_buy["net"] > s_sell["net"] * 1.5:
        print(f"    >>> BUYS significantly outperform SELLS")
    elif s_sell["net"] > s_buy["net"] * 1.5:
        print(f"    >>> SELLS significantly outperform BUYS")
    else:
        print(f"    >>> Both directions perform similarly - no filter needed")

    # 7. BE trigger analysis
    print_subheader("7. Breakeven Move Analysis")
    be_moved = [t for t in trades if t["had_modify"]]
    no_be = [t for t in trades if not t["had_modify"]]
    s_be = compute_group_stats(be_moved)
    s_nobe = compute_group_stats(no_be)
    print(f"    Trades with BE move:    {s_be['count']} | WR={fmt_pct(s_be['winrate'])}, PF={s_be['pf']}, Net={fmt_money(s_be['net'])}")
    print(f"    Trades without BE move: {s_nobe['count']} | WR={fmt_pct(s_nobe['winrate'])}, PF={s_nobe['pf']}, Net={fmt_money(s_nobe['net'])}")

    # How many BEs result in basically flat trades?
    be_flat = [t for t in bes if abs(t["profit"]) < 15]
    be_small_win = [t for t in bes if t["profit"] >= 15]
    print(f"    BE outcomes: {len(be_flat)} flat (|profit| < $15), {len(be_small_win)} small wins")

    # 8. Combined optimization estimate
    print_subheader("8. COMBINED OPTIMIZATION ESTIMATE")
    print()

    # Simulate removing bad hours + bad combos + bad days + ATR filter
    optimized = trades[:]
    removals = {}

    # Remove bad hour+day combos
    bad_combos = []
    for h in range(0, 24):
        for d in range(5):
            subset = [t for t in optimized if t["hour"] == h and t["day_of_week"] == d]
            if subset:
                net = sum(t["profit"] for t in subset)
                if net < -200:  # only block clearly bad combos
                    bad_combos.append((h, d, net, len(subset)))
    bad_combos.sort(key=lambda x: x[2])
    for h, d, net, cnt in bad_combos:
        removed = [t for t in optimized if t["hour"] == h and t["day_of_week"] == d]
        net_removed = sum(t["profit"] for t in removed)
        removals[f"Block {h:02d}:00/{day_names[d]}"] = (len(removed), net_removed)
        optimized = [t for t in optimized if not (t["hour"] == h and t["day_of_week"] == d)]

    # Remove bad hours (full hours)
    for h, s in bad_hours:
        removed = [t for t in optimized if t["hour"] == h]
        if removed:
            net_removed = sum(t["profit"] for t in removed)
            if net_removed < -50:
                removals[f"Block hour {h:02d}:00"] = (len(removed), net_removed)
                optimized = [t for t in optimized if t["hour"] != h]

    # Remove bad days
    for d, s in bad_days:
        removed = [t for t in optimized if t["day_of_week"] == d]
        if removed:
            net_removed = sum(t["profit"] for t in removed)
            if net_removed < -50:
                removals[f"Block {day_names[d]}"] = (len(removed), net_removed)
                optimized = [t for t in optimized if t["day_of_week"] != d]

    # ATR filter
    if best_pf_atr_saved > 0 and trades_with_atr:
        removed = [t for t in optimized if t["h1_atr_pips"] is not None and t["h1_atr_pips"] < best_pf_atr_saved]
        net_removed = sum(t["profit"] for t in removed)
        if net_removed < -50:
            removals[f"ATR filter (min {best_pf_atr_saved:.1f} pips)"] = (len(removed), net_removed)
            optimized = [t for t in optimized if not (t["h1_atr_pips"] is not None and t["h1_atr_pips"] < best_pf_atr_saved)]

    print("    Filter                              Trades Removed    Net of Removed")
    print("    " + "-" * 72)
    total_removed = 0
    total_removed_net = 0
    for name, (count, net) in removals.items():
        print(f"    {name:<36}    {count:>6}          {fmt_money(net):>10}")
        total_removed += count
        total_removed_net += net
    print("    " + "-" * 72)
    print(f"    {'TOTAL':<36}    {total_removed:>6}          {fmt_money(total_removed_net):>10}")

    s_opt = compute_group_stats(optimized)
    s_orig = compute_group_stats(trades)

    print()
    print(f"    ORIGINAL:  {s_orig['count']} trades, WR={fmt_pct(s_orig['winrate'])}, PF={s_orig['pf']}, Net={fmt_money(s_orig['net'])}")
    print(f"    OPTIMIZED: {s_opt['count']} trades, WR={fmt_pct(s_opt['winrate'])}, PF={s_opt['pf']}, Net={fmt_money(s_opt['net'])}")
    print(f"    IMPROVEMENT: +{fmt_money(s_opt['net'] - s_orig['net'])} net profit, {s_opt['pf']} vs {s_orig['pf']} PF")

    # 9. Year-over-year performance
    print_subheader("9. Year-over-Year Performance")
    for year in [2023, 2024, 2025, 2026]:
        subset = [t for t in trades if t["entry_time"].year == year]
        if not subset:
            continue
        s = compute_group_stats(subset)
        months_active = len(set(t["month_key"] for t in subset))
        print(f"    {year}: {s['count']:>4} trades in {months_active} months | WR={fmt_pct(s['winrate'])}, PF={s['pf']}, Net={fmt_money(s['net'])}")

    # 10. Risk of ruin quick estimate
    print_subheader("10. Risk Metrics")
    all_profits = [t["profit"] for t in trades]
    avg_trade = sum(all_profits) / len(all_profits)
    std_dev = (sum((p - avg_trade)**2 for p in all_profits) / len(all_profits)) ** 0.5
    sharpe_like = avg_trade / std_dev if std_dev > 0 else 0

    print(f"    Avg trade:          {fmt_money(avg_trade)}")
    print(f"    Std dev:            {fmt_money(std_dev)}")
    print(f"    Sharpe-like ratio:  {sharpe_like:.3f}")
    print(f"    Max drawdown:       {fmt_money(max_dd)} ({max_dd/max_dd_peak*100:.1f}%)")
    print(f"    Recovery factor:    {net_profit/max_dd:.2f}" if max_dd > 0 else "    Recovery factor: N/A")

    print()
    print_separator()
    print("  END OF ANALYSIS")
    print_separator()
    print()

if __name__ == "__main__":
    main()
