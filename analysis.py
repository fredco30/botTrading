#!/usr/bin/env python3
"""
EMA Pullback EA - Trade History Analysis
Analyzes ~723 trades on EURUSD over 3 years (Apr 2023 - Apr 2026)
"""

import csv
from datetime import datetime, timedelta
from collections import defaultdict
import math

# ============================================================
# 1. PARSE TRADES
# ============================================================

def parse_trade_history(filepath):
    """Parse the trade history file and reconstitute complete trades."""
    lines = []
    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.split('\t')
            if len(parts) < 10:
                continue
            try:
                row = {
                    'line_num': int(parts[0]),
                    'datetime': datetime.strptime(parts[1].strip(), '%Y.%m.%d %H:%M'),
                    'action': parts[2].strip(),
                    'ticket': int(parts[3]),
                    'lots': float(parts[4]),
                    'price': float(parts[5]),
                    'sl': float(parts[6]),
                    'tp': float(parts[7]),
                    'profit': float(parts[8]),
                    'balance': float(parts[9]),
                }
                lines.append(row)
            except (ValueError, IndexError):
                continue
    return lines


def reconstitute_trades(lines):
    """Group lines by ticket and build complete trades."""
    tickets = defaultdict(list)
    for row in lines:
        tickets[row['ticket']].append(row)

    trades = []
    for ticket, rows in sorted(tickets.items()):
        rows.sort(key=lambda r: r['datetime'])
        entry_row = rows[0]
        if entry_row['action'] not in ('buy', 'sell'):
            continue

        direction = entry_row['action']
        entry_time = entry_row['datetime']
        entry_price = entry_row['price']
        initial_sl = entry_row['sl']
        tp = entry_row['tp']
        lots = entry_row['lots']

        # Find modify and exit
        modified = False
        exit_row = None
        exit_type = None
        for row in rows[1:]:
            if row['action'] == 'modify':
                modified = True
            elif row['action'] in ('s/l', 't/p'):
                exit_row = row
                exit_type = row['action']

        if exit_row is None:
            continue

        exit_time = exit_row['datetime']
        exit_price = exit_row['price']
        profit = exit_row['profit']
        balance_after = exit_row['balance']

        # SL distance (always positive)
        if direction == 'buy':
            sl_distance = entry_price - initial_sl
            tp_distance = tp - entry_price
            profit_distance = exit_price - entry_price
        else:
            sl_distance = initial_sl - entry_price
            tp_distance = entry_price - tp
            profit_distance = entry_price - exit_price

        # RR
        rr_planned = tp_distance / sl_distance if sl_distance > 0 else 0
        rr_real = profit_distance / sl_distance if sl_distance > 0 else 0

        # Result classification
        if exit_type == 't/p':
            result = 'win'
        elif exit_type == 's/l' and modified and abs(profit) < lots * 20:
            # SL hit after modify with small profit = breakeven
            result = 'breakeven'
        else:
            result = 'loss'

        # Duration
        duration = exit_time - entry_time
        duration_min = duration.total_seconds() / 60

        # Session
        hour = entry_time.hour
        if 8 <= hour < 12:
            session = 'London'
        elif 13 <= hour < 17:
            session = 'New York'
        elif hour == 12:
            session = 'London'
        else:
            session = 'Off-session'

        day_of_week = entry_time.strftime('%A')

        trades.append({
            'ticket': ticket,
            'direction': direction,
            'entry_time': entry_time,
            'exit_time': exit_time,
            'duration_min': duration_min,
            'day': day_of_week,
            'hour': hour,
            'session': session,
            'entry_price': entry_price,
            'initial_sl': initial_sl,
            'tp': tp,
            'exit_price': exit_price,
            'sl_distance': sl_distance,
            'tp_distance': tp_distance,
            'rr_planned': rr_planned,
            'rr_real': rr_real,
            'result': result,
            'profit': profit,
            'balance_after': balance_after,
            'lots': lots,
            'modified': modified,
            'exit_type': exit_type,
        })

    return trades


# ============================================================
# 2. LOAD MARKET DATA
# ============================================================

def load_m15_data(filepath):
    """Load M15 candle data."""
    candles = []
    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.split(',')
            if len(parts) < 7:
                continue
            try:
                dt = datetime.strptime(parts[0] + ',' + parts[1], '%Y.%m.%d,%H:%M')
                candles.append({
                    'datetime': dt,
                    'open': float(parts[2]),
                    'high': float(parts[3]),
                    'low': float(parts[4]),
                    'close': float(parts[5]),
                    'volume': int(parts[6]),
                })
            except (ValueError, IndexError):
                continue
    return candles


def load_h1_data(filepath):
    """Load H1 candle data (filter from 2023+)."""
    candles = []
    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.split(',')
            if len(parts) < 7:
                continue
            try:
                dt = datetime.strptime(parts[0] + ',' + parts[1], '%Y.%m.%d,%H:%M')
                if dt.year < 2023:
                    continue
                candles.append({
                    'datetime': dt,
                    'open': float(parts[2]),
                    'high': float(parts[3]),
                    'low': float(parts[4]),
                    'close': float(parts[5]),
                    'volume': int(parts[6]),
                })
            except (ValueError, IndexError):
                continue
    return candles


def build_h1_index(h1_candles):
    """Build a dict keyed by date for fast lookup."""
    by_date = defaultdict(list)
    for c in h1_candles:
        by_date[c['datetime'].date()].append(c)
    return by_date


def build_m15_index(m15_candles):
    """Build index by datetime for fast lookup."""
    idx = {}
    for c in m15_candles:
        idx[c['datetime']] = c
    return idx


def calc_atr_h1(h1_by_date, target_date, period=14):
    """Calculate ATR(14) on H1 for a given date using preceding data."""
    # Collect H1 candles from the 14 trading days before target_date
    all_candles = []
    d = target_date - timedelta(days=30)
    while d < target_date:
        if d in h1_by_date:
            all_candles.extend(h1_by_date[d])
        d += timedelta(days=1)
    # Also include target date candles before the entry
    if target_date in h1_by_date:
        all_candles.extend(h1_by_date[target_date])

    if len(all_candles) < period + 1:
        return None

    # True Range for each candle
    trs = []
    for i in range(1, len(all_candles)):
        h = all_candles[i]['high']
        l = all_candles[i]['low']
        prev_c = all_candles[i-1]['close']
        tr = max(h - l, abs(h - prev_c), abs(l - prev_c))
        trs.append(tr)

    if len(trs) < period:
        return None

    # Simple ATR = average of last `period` TRs
    return sum(trs[-period:]) / period


def get_m15_candle_size(m15_index, entry_time):
    """Get the M15 candle size at entry time."""
    # Round down to nearest 15 min
    minute = (entry_time.minute // 15) * 15
    candle_time = entry_time.replace(minute=minute, second=0, microsecond=0)
    candle = m15_index.get(candle_time)
    if candle:
        return candle['high'] - candle['low']
    # Try one candle before
    candle_time -= timedelta(minutes=15)
    candle = m15_index.get(candle_time)
    if candle:
        return candle['high'] - candle['low']
    return None


# ============================================================
# 3. STATISTICS & REPORT
# ============================================================

def fmt_pct(n, total):
    if total == 0:
        return "0.0%"
    return f"{100*n/total:.1f}%"


def fmt_money(v):
    return f"${v:,.2f}"


def print_table(headers, rows, col_widths=None):
    """Print a formatted table."""
    if col_widths is None:
        col_widths = []
        for i, h in enumerate(headers):
            max_w = len(str(h))
            for row in rows:
                max_w = max(max_w, len(str(row[i])))
            col_widths.append(max_w + 2)

    # Header
    header_line = ""
    for i, h in enumerate(headers):
        header_line += str(h).ljust(col_widths[i])
    print(header_line)
    print("-" * sum(col_widths))

    # Rows
    for row in rows:
        line = ""
        for i, val in enumerate(row):
            line += str(val).ljust(col_widths[i])
        print(line)


def analyze_and_report(trades, h1_by_date, m15_index):
    total = len(trades)
    wins = [t for t in trades if t['result'] == 'win']
    losses = [t for t in trades if t['result'] == 'loss']
    bes = [t for t in trades if t['result'] == 'breakeven']

    buys = [t for t in trades if t['direction'] == 'buy']
    sells = [t for t in trades if t['direction'] == 'sell']

    total_profit = sum(t['profit'] for t in trades)
    gross_profit = sum(t['profit'] for t in trades if t['profit'] > 0)
    gross_loss = abs(sum(t['profit'] for t in trades if t['profit'] < 0))

    print("=" * 80)
    print("   EMA PULLBACK EA - EURUSD - TRADE ANALYSIS REPORT")
    print("   Period: {} to {}".format(
        trades[0]['entry_time'].strftime('%Y-%m-%d'),
        trades[-1]['entry_time'].strftime('%Y-%m-%d')
    ))
    print("=" * 80)

    # ----------------------------------------------------------
    # GLOBAL STATS
    # ----------------------------------------------------------
    print("\n" + "=" * 80)
    print("  SECTION 1: GLOBAL STATISTICS")
    print("=" * 80)

    print(f"\n  Total trades:        {total}")
    print(f"  Wins (t/p):          {len(wins)} ({fmt_pct(len(wins), total)})")
    print(f"  Losses (s/l):        {len(losses)} ({fmt_pct(len(losses), total)})")
    print(f"  Breakeven:           {len(bes)} ({fmt_pct(len(bes), total)})")
    print(f"\n  Starting balance:    $10,000.00")
    print(f"  Final balance:       {fmt_money(trades[-1]['balance_after'])}")
    print(f"  Net profit:          {fmt_money(total_profit)}")
    print(f"  Gross profit:        {fmt_money(gross_profit)}")
    print(f"  Gross loss:          {fmt_money(gross_loss)}")
    pf = gross_profit / gross_loss if gross_loss > 0 else float('inf')
    print(f"  Profit factor:       {pf:.2f}")
    print(f"\n  Winrate global:      {fmt_pct(len(wins), total)}")

    # Winrate by direction
    buy_wins = len([t for t in buys if t['result'] == 'win'])
    sell_wins = len([t for t in sells if t['result'] == 'win'])
    print(f"  Winrate BUY:         {fmt_pct(buy_wins, len(buys))} ({buy_wins}/{len(buys)})")
    print(f"  Winrate SELL:        {fmt_pct(sell_wins, len(sells))} ({sell_wins}/{len(sells)})")

    # RR stats
    rr_planned_avg = sum(t['rr_planned'] for t in trades) / total
    rr_real_avg = sum(t['rr_real'] for t in trades) / total
    rr_real_wins = sum(t['rr_real'] for t in wins) / len(wins) if wins else 0
    rr_real_losses = sum(t['rr_real'] for t in losses) / len(losses) if losses else 0

    print(f"\n  Avg RR planned:      {rr_planned_avg:.2f}")
    print(f"  Avg RR real:         {rr_real_avg:.2f}")
    print(f"  Avg RR on wins:      {rr_real_wins:.2f}")
    print(f"  Avg RR on losses:    {rr_real_losses:.2f}")

    # Duration
    avg_dur = sum(t['duration_min'] for t in trades) / total
    avg_dur_wins = sum(t['duration_min'] for t in wins) / len(wins) if wins else 0
    avg_dur_losses = sum(t['duration_min'] for t in losses) / len(losses) if losses else 0
    print(f"\n  Avg duration:        {avg_dur:.0f} min ({avg_dur/60:.1f}h)")
    print(f"  Avg duration wins:   {avg_dur_wins:.0f} min")
    print(f"  Avg duration losses: {avg_dur_losses:.0f} min")

    # ----------------------------------------------------------
    # WINRATE BY SESSION
    # ----------------------------------------------------------
    print("\n" + "-" * 80)
    print("  WINRATE & PROFIT BY SESSION")
    print("-" * 80)

    sessions = ['London', 'New York', 'Off-session']
    rows = []
    for s in sessions:
        st = [t for t in trades if t['session'] == s]
        sw = [t for t in st if t['result'] == 'win']
        sp = sum(t['profit'] for t in st)
        gp = sum(t['profit'] for t in st if t['profit'] > 0)
        gl = abs(sum(t['profit'] for t in st if t['profit'] < 0))
        spf = gp / gl if gl > 0 else 0
        rows.append([s, len(st), fmt_pct(len(sw), len(st)), fmt_money(sp), f"{spf:.2f}"])

    print_table(['Session', 'Trades', 'Winrate', 'Net Profit', 'PF'], rows)

    # ----------------------------------------------------------
    # WINRATE BY DAY
    # ----------------------------------------------------------
    print("\n" + "-" * 80)
    print("  WINRATE & PROFIT BY DAY OF WEEK")
    print("-" * 80)

    days_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']
    rows = []
    for d in days_order:
        dt = [t for t in trades if t['day'] == d]
        dw = [t for t in dt if t['result'] == 'win']
        dp = sum(t['profit'] for t in dt)
        gp = sum(t['profit'] for t in dt if t['profit'] > 0)
        gl = abs(sum(t['profit'] for t in dt if t['profit'] < 0))
        dpf = gp / gl if gl > 0 else 0
        rows.append([d, len(dt), fmt_pct(len(dw), len(dt)), fmt_money(dp), f"{dpf:.2f}"])

    print_table(['Day', 'Trades', 'Winrate', 'Net Profit', 'PF'], rows)

    # ----------------------------------------------------------
    # WINRATE BY HOUR
    # ----------------------------------------------------------
    print("\n" + "-" * 80)
    print("  WINRATE & PROFIT BY ENTRY HOUR")
    print("-" * 80)

    rows = []
    for h in range(24):
        ht = [t for t in trades if t['hour'] == h]
        if not ht:
            continue
        hw = [t for t in ht if t['result'] == 'win']
        hp = sum(t['profit'] for t in ht)
        gp = sum(t['profit'] for t in ht if t['profit'] > 0)
        gl = abs(sum(t['profit'] for t in ht if t['profit'] < 0))
        hpf = gp / gl if gl > 0 else 0
        rows.append([f"{h:02d}:00", len(ht), fmt_pct(len(hw), len(ht)), fmt_money(hp), f"{hpf:.2f}"])

    print_table(['Hour', 'Trades', 'Winrate', 'Net Profit', 'PF'], rows)

    # ----------------------------------------------------------
    # LOSING STREAKS
    # ----------------------------------------------------------
    print("\n" + "-" * 80)
    print("  LOSING STREAKS")
    print("-" * 80)

    streak = 0
    max_streak = 0
    streaks = []
    current_streak_start = None
    for t in trades:
        if t['result'] == 'loss':
            if streak == 0:
                current_streak_start = t['entry_time']
            streak += 1
        else:
            if streak > 0:
                streaks.append((streak, current_streak_start))
            streak = 0
    if streak > 0:
        streaks.append((streak, current_streak_start))

    streaks.sort(key=lambda x: x[0], reverse=True)
    max_streak = streaks[0][0] if streaks else 0

    print(f"\n  Max consecutive losses: {max_streak}")
    print(f"  Total losing streaks (2+): {len([s for s in streaks if s[0] >= 2])}")

    # Distribution of streak lengths
    streak_dist = defaultdict(int)
    for s, _ in streaks:
        if s >= 2:
            streak_dist[s] += 1
    print("\n  Streak length distribution (2+):")
    for length in sorted(streak_dist.keys()):
        print(f"    {length} losses in a row: {streak_dist[length]} times")

    # ----------------------------------------------------------
    # DRAWDOWN ANALYSIS
    # ----------------------------------------------------------
    print("\n" + "-" * 80)
    print("  TOP 5 DRAWDOWN PERIODS")
    print("-" * 80)

    # Calculate running equity curve and find drawdown periods
    peak = 10000.0
    drawdowns = []  # (start_date, end_date, peak, trough, dd_amount, dd_pct, nb_trades)
    dd_start = None
    dd_peak = peak
    dd_trough = peak
    dd_trades = 0

    for t in trades:
        bal = t['balance_after']
        if bal >= peak:
            if dd_start is not None and dd_peak - dd_trough > 0:
                drawdowns.append({
                    'start': dd_start,
                    'end': t['exit_time'],
                    'peak': dd_peak,
                    'trough': dd_trough,
                    'amount': dd_peak - dd_trough,
                    'pct': (dd_peak - dd_trough) / dd_peak * 100,
                    'trades': dd_trades,
                })
            peak = bal
            dd_start = None
            dd_trough = bal
            dd_trades = 0
        else:
            if dd_start is None:
                dd_start = t['entry_time']
                dd_peak = peak
            dd_trough = min(dd_trough, bal)
            dd_trades += 1

    # Handle final open drawdown
    if dd_start is not None and dd_peak - dd_trough > 0:
        drawdowns.append({
            'start': dd_start,
            'end': trades[-1]['exit_time'],
            'peak': dd_peak,
            'trough': dd_trough,
            'amount': dd_peak - dd_trough,
            'pct': (dd_peak - dd_trough) / dd_peak * 100,
            'trades': dd_trades,
        })

    drawdowns.sort(key=lambda x: x['amount'], reverse=True)
    rows = []
    for i, dd in enumerate(drawdowns[:5]):
        rows.append([
            f"#{i+1}",
            dd['start'].strftime('%Y-%m-%d'),
            dd['end'].strftime('%Y-%m-%d'),
            f"{dd['trades']}",
            fmt_money(dd['amount']),
            f"{dd['pct']:.1f}%",
        ])

    print_table(['Rank', 'Start', 'End', 'Trades', 'Loss', 'DD%'], rows)

    # ----------------------------------------------------------
    # MONTHLY EQUITY EVOLUTION
    # ----------------------------------------------------------
    print("\n" + "-" * 80)
    print("  MONTHLY EQUITY EVOLUTION")
    print("-" * 80)

    monthly = defaultdict(lambda: {'trades': 0, 'wins': 0, 'profit': 0, 'balance': 0})
    for t in trades:
        key = t['entry_time'].strftime('%Y-%m')
        monthly[key]['trades'] += 1
        if t['result'] == 'win':
            monthly[key]['wins'] += 1
        monthly[key]['profit'] += t['profit']
        monthly[key]['balance'] = t['balance_after']

    rows = []
    for key in sorted(monthly.keys()):
        m = monthly[key]
        wr = fmt_pct(m['wins'], m['trades'])
        rows.append([key, m['trades'], wr, fmt_money(m['profit']), fmt_money(m['balance'])])

    print_table(['Month', 'Trades', 'Winrate', 'Net P&L', 'Balance'], rows)

    # ----------------------------------------------------------
    # SECTION 3: HEATMAP - PROFIT BY HOUR x DAY
    # ----------------------------------------------------------
    print("\n" + "=" * 80)
    print("  SECTION 3: PROFIT HEATMAP (Hour x Day)")
    print("=" * 80)

    heatmap = defaultdict(float)
    heatmap_count = defaultdict(int)
    for t in trades:
        key = (t['hour'], t['day'])
        heatmap[key] += t['profit']
        heatmap_count[key] += 1

    # Find active hours
    active_hours = sorted(set(t['hour'] for t in trades))

    # Print header
    day_short = {'Monday': 'Mon', 'Tuesday': 'Tue', 'Wednesday': 'Wed', 'Thursday': 'Thu', 'Friday': 'Fri'}
    header = "  Hour  "
    for d in days_order:
        header += f"  {day_short[d]:>12s}"
    print(header)
    print("  " + "-" * 75)

    for h in active_hours:
        line = f"  {h:02d}:00 "
        for d in days_order:
            key = (h, d)
            if heatmap_count[key] > 0:
                p = heatmap[key]
                n = heatmap_count[key]
                sign = "+" if p >= 0 else ""
                line += f"  {sign}{p:>7.0f}({n:>2d})"
            else:
                line += f"  {'---':>12s}"
        print(line)

    # Identify best/worst
    print("\n  BEST hours (by total profit):")
    hour_profits = defaultdict(float)
    hour_counts = defaultdict(int)
    for t in trades:
        hour_profits[t['hour']] += t['profit']
        hour_counts[t['hour']] += 1
    sorted_hours = sorted(hour_profits.items(), key=lambda x: x[1], reverse=True)
    for h, p in sorted_hours[:5]:
        print(f"    {h:02d}:00  -> {fmt_money(p):>12s} ({hour_counts[h]} trades)")

    print("\n  WORST hours (by total profit):")
    for h, p in sorted_hours[-5:]:
        print(f"    {h:02d}:00  -> {fmt_money(p):>12s} ({hour_counts[h]} trades)")

    # Worst day
    day_profits = {}
    for d in days_order:
        day_profits[d] = sum(t['profit'] for t in trades if t['day'] == d)
    worst_day = min(day_profits, key=day_profits.get)
    best_day = max(day_profits, key=day_profits.get)
    print(f"\n  Worst day: {worst_day} ({fmt_money(day_profits[worst_day])})")
    print(f"  Best day:  {best_day} ({fmt_money(day_profits[best_day])})")

    # ----------------------------------------------------------
    # SECTION 4: RR ANALYSIS
    # ----------------------------------------------------------
    print("\n" + "=" * 80)
    print("  SECTION 4: RISK/REWARD ANALYSIS")
    print("=" * 80)

    # RR distribution
    tp_trades = [t for t in trades if t['exit_type'] == 't/p']
    sl_after_modify = [t for t in trades if t['exit_type'] == 's/l' and t['modified']]
    sl_no_modify = [t for t in trades if t['exit_type'] == 's/l' and not t['modified']]

    print(f"\n  Exit type breakdown:")
    print(f"    Take Profit (t/p):           {len(tp_trades):>4d} ({fmt_pct(len(tp_trades), total)})")
    print(f"    Stop Loss after BE modify:   {len(sl_after_modify):>4d} ({fmt_pct(len(sl_after_modify), total)})")
    print(f"    Stop Loss (initial SL):      {len(sl_no_modify):>4d} ({fmt_pct(len(sl_no_modify), total)})")

    # Average RR by exit type
    if tp_trades:
        avg_rr_tp = sum(t['rr_real'] for t in tp_trades) / len(tp_trades)
        print(f"\n  Avg RR on TP hits:             {avg_rr_tp:.2f}")
    if sl_after_modify:
        avg_rr_be = sum(t['rr_real'] for t in sl_after_modify) / len(sl_after_modify)
        avg_profit_be = sum(t['profit'] for t in sl_after_modify) / len(sl_after_modify)
        print(f"  Avg RR on BE (SL after mod):   {avg_rr_be:.2f}")
        print(f"  Avg profit on BE:              {fmt_money(avg_profit_be)}")
    if sl_no_modify:
        avg_rr_sl = sum(t['rr_real'] for t in sl_no_modify) / len(sl_no_modify)
        print(f"  Avg RR on SL (no modify):      {avg_rr_sl:.2f}")

    # RR histogram
    print("\n  RR Real Distribution (histogram):")
    rr_buckets = defaultdict(int)
    for t in trades:
        bucket = round(t['rr_real'] * 2) / 2  # Round to nearest 0.5
        rr_buckets[bucket] += 1

    for bucket in sorted(rr_buckets.keys()):
        count = rr_buckets[bucket]
        bar = "#" * (count // 2)
        print(f"    RR {bucket:>5.1f}: {count:>4d} {bar}")

    # Why RR real ~1.19 when MinRR 2.5?
    print("\n  WHY is avg RR real lower than planned RR?")
    print(f"    - Trades hitting TP (full RR):     {len(tp_trades)} = {fmt_pct(len(tp_trades), total)}")
    print(f"    - Trades hitting BE (~0 RR):       {len(sl_after_modify)} = {fmt_pct(len(sl_after_modify), total)}")
    print(f"    - Trades hitting initial SL (-1R): {len(sl_no_modify)} = {fmt_pct(len(sl_no_modify), total)}")
    print(f"    - BE trades dilute the avg RR heavily.")
    print(f"    - Formula: ({len(tp_trades)}*{avg_rr_tp:.1f} + {len(sl_after_modify)}*~0 + {len(sl_no_modify)}*-1) / {total}")
    expected_rr = (len(tp_trades) * avg_rr_tp + len(sl_no_modify) * (-1)) / total
    print(f"    - Expected avg RR: {expected_rr:.2f} (actual: {rr_real_avg:.2f})")

    # ----------------------------------------------------------
    # SECTION 5: MARKET DATA CROSSOVER
    # ----------------------------------------------------------
    print("\n" + "=" * 80)
    print("  SECTION 5: VOLATILITY ANALYSIS")
    print("=" * 80)

    # Calculate ATR and M15 candle size for each trade
    atr_values = []
    m15_sizes = []
    trades_with_atr = []

    for t in trades:
        atr = calc_atr_h1(h1_by_date, t['entry_time'].date())
        m15_size = get_m15_candle_size(m15_index, t['entry_time'])

        if atr is not None:
            t['atr'] = atr
            atr_values.append(atr)
            trades_with_atr.append(t)
        if m15_size is not None:
            t['m15_size'] = m15_size
            m15_sizes.append(m15_size)

    if atr_values:
        avg_atr = sum(atr_values) / len(atr_values)
        median_atr = sorted(atr_values)[len(atr_values) // 2]

        print(f"\n  ATR H1(14) stats:")
        print(f"    Average:  {avg_atr*10000:.1f} pips")
        print(f"    Median:   {median_atr*10000:.1f} pips")

        # Split by high/low volatility (above/below median)
        high_vol = [t for t in trades_with_atr if t['atr'] >= median_atr]
        low_vol = [t for t in trades_with_atr if t['atr'] < median_atr]

        hv_wins = len([t for t in high_vol if t['result'] == 'win'])
        lv_wins = len([t for t in low_vol if t['result'] == 'win'])
        hv_profit = sum(t['profit'] for t in high_vol)
        lv_profit = sum(t['profit'] for t in low_vol)
        hv_gp = sum(t['profit'] for t in high_vol if t['profit'] > 0)
        hv_gl = abs(sum(t['profit'] for t in high_vol if t['profit'] < 0))
        lv_gp = sum(t['profit'] for t in low_vol if t['profit'] > 0)
        lv_gl = abs(sum(t['profit'] for t in low_vol if t['profit'] < 0))

        print(f"\n  Performance by volatility regime:")
        rows = []
        rows.append([
            'High vol (>median)',
            len(high_vol),
            fmt_pct(hv_wins, len(high_vol)),
            fmt_money(hv_profit),
            f"{hv_gp/hv_gl:.2f}" if hv_gl > 0 else "N/A",
        ])
        rows.append([
            'Low vol (<median)',
            len(low_vol),
            fmt_pct(lv_wins, len(low_vol)),
            fmt_money(lv_profit),
            f"{lv_gp/lv_gl:.2f}" if lv_gl > 0 else "N/A",
        ])
        print_table(['Regime', 'Trades', 'Winrate', 'Net Profit', 'PF'], rows)

        # Split into quartiles for more detail
        sorted_atrs = sorted(atr_values)
        q1 = sorted_atrs[len(sorted_atrs) // 4]
        q3 = sorted_atrs[3 * len(sorted_atrs) // 4]

        print(f"\n  ATR quartiles: Q1={q1*10000:.1f} | Median={median_atr*10000:.1f} | Q3={q3*10000:.1f} pips")

        quartile_labels = ['Q1 (lowest)', 'Q2', 'Q3', 'Q4 (highest)']
        quartile_bounds = [0, q1, median_atr, q3, float('inf')]
        rows = []
        for i in range(4):
            qt = [t for t in trades_with_atr if quartile_bounds[i] <= t['atr'] < quartile_bounds[i+1]]
            if not qt:
                continue
            qw = len([t for t in qt if t['result'] == 'win'])
            qp = sum(t['profit'] for t in qt)
            rows.append([quartile_labels[i], len(qt), fmt_pct(qw, len(qt)), fmt_money(qp)])

        print_table(['Quartile', 'Trades', 'Winrate', 'Net Profit'], rows)

    if m15_sizes:
        avg_m15 = sum(m15_sizes) / len(m15_sizes)
        print(f"\n  Avg M15 candle size at entry: {avg_m15*10000:.1f} pips")

        # High vs low M15 candle size
        median_m15 = sorted(m15_sizes)[len(m15_sizes) // 2]
        trades_with_m15 = [t for t in trades if 'm15_size' in t]
        high_m15 = [t for t in trades_with_m15 if t['m15_size'] >= median_m15]
        low_m15 = [t for t in trades_with_m15 if t['m15_size'] < median_m15]

        print(f"  Median M15 candle size: {median_m15*10000:.1f} pips")

        rows = []
        for label, group in [('Large M15 candles', high_m15), ('Small M15 candles', low_m15)]:
            gw = len([t for t in group if t['result'] == 'win'])
            gp = sum(t['profit'] for t in group)
            rows.append([label, len(group), fmt_pct(gw, len(group)), fmt_money(gp)])

        print_table(['M15 Size', 'Trades', 'Winrate', 'Net Profit'], rows)

    # ----------------------------------------------------------
    # SUMMARY & RECOMMENDATIONS
    # ----------------------------------------------------------
    print("\n" + "=" * 80)
    print("  SUMMARY")
    print("=" * 80)
    print(f"""
  - {total} trades over ~3 years, {fmt_pct(len(wins), total)} winrate
  - Net profit: {fmt_money(total_profit)} ({(total_profit/10000)*100:.1f}% return)
  - Profit factor: {pf:.2f}
  - Average RR real: {rr_real_avg:.2f} (planned: {rr_planned_avg:.2f})
  - {len(sl_after_modify)} trades ({fmt_pct(len(sl_after_modify), total)}) exit at breakeven, diluting avg RR
  - Max losing streak: {max_streak}
  - Worst day: {worst_day}
  - Best session: {'London' if sum(t['profit'] for t in trades if t['session'] == 'London') > sum(t['profit'] for t in trades if t['session'] == 'New York') else 'New York'}
""")


# ============================================================
# MAIN
# ============================================================

if __name__ == '__main__':
    print("Loading trade history...")
    lines = parse_trade_history(r'C:/Users/projets/botTrading/historique trade 3ans.txt')
    trades = reconstitute_trades(lines)
    print(f"  Parsed {len(lines)} lines -> {len(trades)} complete trades")

    print("Loading H1 data...")
    h1_candles = load_h1_data(r'C:/Users/projets/botTrading/EURUSD60.csv')
    h1_by_date = build_h1_index(h1_candles)
    print(f"  Loaded {len(h1_candles)} H1 candles")

    print("Loading M15 data...")
    m15_candles = load_m15_data(r'C:/Users/projets/botTrading/EURUSD15_cut.csv')
    m15_index = build_m15_index(m15_candles)
    print(f"  Loaded {len(m15_candles)} M15 candles")

    print()
    analyze_and_report(trades, h1_by_date, m15_index)
