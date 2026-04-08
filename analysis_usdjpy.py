#!/usr/bin/env python3
"""
USDJPY EMA Pullback EA - Comprehensive Trade Analysis
Backtest: Apr 2023 - Sep 2025, 349 trades, raw (no filters)
IMPORTANT: USDJPY pip = 0.01, so pip conversion = *100
"""

import csv
import math
from datetime import datetime, timedelta
from collections import defaultdict

# ============================================================
# CONFIG
# ============================================================
TRADE_FILE = r"C:\Users\projets\botTrading\historique trade usdjpy 3ans.txt"
H1_FILE = r"C:\Users\projets\botTrading\USDJPY60_cut.csv"
M15_FILE = r"C:\Users\projets\botTrading\USDJPY15_cut.csv"

PIP_MULT = 100  # USDJPY: 1 pip = 0.01, so distance * 100 = pips
INITIAL_BALANCE = 10000.0

# ============================================================
# PARSE H1 DATA
# ============================================================
def parse_h1_data(filepath):
    """Parse H1 OHLCV data. Returns list of dicts sorted by datetime."""
    bars = []
    with open(filepath, 'r') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            fields = line.split(',')
            if len(fields) < 6:
                continue
            try:
                dt = datetime.strptime(f"{fields[0]},{fields[1]}", "%Y.%m.%d,%H:%M")
                bars.append({
                    'datetime': dt,
                    'open': float(fields[2]),
                    'high': float(fields[3]),
                    'low': float(fields[4]),
                    'close': float(fields[5]),
                    'volume': int(fields[6]) if len(fields) > 6 else 0
                })
            except (ValueError, IndexError):
                continue
    bars.sort(key=lambda x: x['datetime'])
    return bars

def compute_atr(bars, period=14):
    """Compute ATR for each bar. Returns dict datetime -> ATR value."""
    atr_map = {}
    if len(bars) < period + 1:
        return atr_map

    trs = []
    for i in range(1, len(bars)):
        high = bars[i]['high']
        low = bars[i]['low']
        prev_close = bars[i-1]['close']
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        trs.append(tr)

    # First ATR = SMA of first `period` TRs
    if len(trs) < period:
        return atr_map

    atr = sum(trs[:period]) / period
    atr_map[bars[period]['datetime']] = atr

    for i in range(period, len(trs)):
        atr = (atr * (period - 1) + trs[i]) / period
        atr_map[bars[i+1]['datetime']] = atr

    return atr_map

def compute_ema(bars, period=50):
    """Compute EMA for each bar. Returns dict datetime -> EMA value."""
    ema_map = {}
    if len(bars) < period:
        return ema_map

    # SMA for initial value
    sma = sum(b['close'] for b in bars[:period]) / period
    multiplier = 2.0 / (period + 1)

    ema_map[bars[period-1]['datetime']] = sma
    ema = sma

    for i in range(period, len(bars)):
        ema = (bars[i]['close'] - ema) * multiplier + ema
        ema_map[bars[i]['datetime']] = ema

    return ema_map

def find_nearest_bar_value(value_map, target_dt, max_hours=2):
    """Find the nearest value from a datetime-keyed map."""
    best_dt = None
    best_diff = timedelta(hours=max_hours)

    for dt in value_map:
        diff = abs(dt - target_dt)
        if diff < best_diff:
            best_diff = diff
            best_dt = dt

    if best_dt is not None:
        return value_map[best_dt]
    return None

# ============================================================
# PARSE TRADES
# ============================================================
def parse_trades(filepath):
    """Parse trade history into structured trade records."""
    lines = []
    with open(filepath, 'r') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.split('\t')
            # Format: LineNum  DateTime  Action  Ticket  Lots  Price  SL  TP  Profit  Balance
            # (10 fields, no separate seq column)
            if len(parts) < 10:
                continue
            try:
                rec = {
                    'line_num': int(parts[0]),
                    'datetime': datetime.strptime(parts[1], "%Y.%m.%d %H:%M"),
                    'action': parts[2].strip().lower(),
                    'ticket': int(parts[3]),
                    'lots': float(parts[4]),
                    'price': float(parts[5]),
                    'sl': float(parts[6]),
                    'tp': float(parts[7]),
                    'profit': float(parts[8]),
                    'balance': float(parts[9]),
                }
                lines.append(rec)
            except (ValueError, IndexError):
                continue

    # Group by ticket
    ticket_groups = defaultdict(list)
    for rec in lines:
        ticket_groups[rec['ticket']].append(rec)

    trades = []
    for ticket in sorted(ticket_groups.keys()):
        events = sorted(ticket_groups[ticket], key=lambda x: x['datetime'])

        # Find open event (buy or sell)
        open_event = None
        close_event = None

        for e in events:
            if e['action'] in ('buy', 'sell'):
                open_event = e
            elif e['action'] in ('s/l', 't/p', 'close'):
                close_event = e

        if open_event is None or close_event is None:
            continue

        direction = open_event['action']  # 'buy' or 'sell'
        entry_price = open_event['price']
        entry_sl = open_event['sl']
        entry_tp = open_event['tp']
        close_price = close_event['price']
        profit = close_event['profit']
        lots = open_event['lots']

        # SL distance in pips
        sl_distance_pips = abs(entry_price - entry_sl) * PIP_MULT

        # Duration
        duration_minutes = (close_event['datetime'] - open_event['datetime']).total_seconds() / 60

        # Determine result
        if profit > 5:
            result = 'WIN'
        elif profit < -5:
            result = 'LOSS'
        else:
            result = 'BE'

        # Was there a modify (BE move)?
        had_modify = any(e['action'] == 'modify' for e in events)

        trades.append({
            'ticket': ticket,
            'direction': direction,
            'entry_time': open_event['datetime'],
            'close_time': close_event['datetime'],
            'entry_price': entry_price,
            'close_price': close_price,
            'sl': entry_sl,
            'tp': entry_tp,
            'sl_distance_pips': sl_distance_pips,
            'lots': lots,
            'profit': profit,
            'balance_after': close_event['balance'],
            'duration_min': duration_minutes,
            'result': result,
            'close_type': close_event['action'],
            'had_modify': had_modify,
            'hour': open_event['datetime'].hour,
            'day': open_event['datetime'].weekday(),  # 0=Mon
            'month': open_event['datetime'].strftime('%Y-%m'),
        })

    return trades

# ============================================================
# STATS HELPERS
# ============================================================
def calc_stats(trades):
    """Compute basic stats for a list of trades."""
    if not trades:
        return {'count': 0, 'wins': 0, 'losses': 0, 'bes': 0, 'winrate': 0, 'pf': 0, 'net': 0, 'gross_profit': 0, 'gross_loss': 0, 'avg_win': 0, 'avg_loss': 0}

    wins = [t for t in trades if t['result'] == 'WIN']
    losses = [t for t in trades if t['result'] == 'LOSS']
    bes = [t for t in trades if t['result'] == 'BE']

    gross_profit = sum(t['profit'] for t in wins)
    gross_loss = abs(sum(t['profit'] for t in losses))
    net = sum(t['profit'] for t in trades)

    winrate = len(wins) / len(trades) * 100 if trades else 0
    pf = gross_profit / gross_loss if gross_loss > 0 else float('inf')
    avg_win = gross_profit / len(wins) if wins else 0
    avg_loss = gross_loss / len(losses) if losses else 0

    return {
        'count': len(trades),
        'wins': len(wins),
        'losses': len(losses),
        'bes': len(bes),
        'winrate': winrate,
        'pf': pf,
        'net': net,
        'gross_profit': gross_profit,
        'gross_loss': gross_loss,
        'avg_win': avg_win,
        'avg_loss': avg_loss,
    }

def max_consecutive_losses(trades):
    """Find max consecutive losses."""
    max_cl = 0
    current = 0
    for t in trades:
        if t['result'] == 'LOSS':
            current += 1
            max_cl = max(max_cl, current)
        else:
            current = 0
    return max_cl

def max_drawdown(trades):
    """Compute max drawdown from trade sequence."""
    peak = INITIAL_BALANCE
    max_dd = 0
    balance = INITIAL_BALANCE

    for t in trades:
        balance += t['profit']
        if balance > peak:
            peak = balance
        dd = peak - balance
        if dd > max_dd:
            max_dd = dd

    dd_pct = max_dd / INITIAL_BALANCE * 100
    return max_dd, dd_pct

def print_separator(char='=', length=80):
    print(char * length)

def print_header(title):
    print()
    print_separator()
    print(f"  {title}")
    print_separator()

# ============================================================
# MAIN ANALYSIS
# ============================================================
def main():
    print("=" * 80)
    print("  USDJPY EMA PULLBACK EA - COMPREHENSIVE ANALYSIS")
    print("  Backtest: Apr 2023 - Sep 2025 | Raw (no filters)")
    print("  Pip calculation: *100 (JPY pair)")
    print("=" * 80)

    # Parse data
    print("\nLoading data...")
    trades = parse_trades(TRADE_FILE)
    print(f"  Trades parsed: {len(trades)}")

    h1_bars = parse_h1_data(H1_FILE)
    print(f"  H1 bars loaded: {len(h1_bars)}")

    # Compute indicators
    atr_map = compute_atr(h1_bars, 14)
    ema50_map = compute_ema(h1_bars, 50)
    print(f"  ATR values computed: {len(atr_map)}")
    print(f"  EMA50 values computed: {len(ema50_map)}")

    # Enrich trades with ATR and EMA50
    for t in trades:
        atr_val = find_nearest_bar_value(atr_map, t['entry_time'], max_hours=2)
        ema_val = find_nearest_bar_value(ema50_map, t['entry_time'], max_hours=2)

        t['atr_raw'] = atr_val  # In price units (e.g., 0.50)
        t['atr_pips'] = atr_val * PIP_MULT if atr_val else None  # In pips (e.g., 50)
        t['ema50'] = ema_val
        t['ema50_distance_pips'] = abs(t['entry_price'] - ema_val) * PIP_MULT if ema_val else None

    # ========================================================
    # A. GLOBAL STATS
    # ========================================================
    print_header("A. GLOBAL STATISTICS")

    stats = calc_stats(trades)
    max_dd, max_dd_pct = max_drawdown(trades)
    max_cl = max_consecutive_losses(trades)

    print(f"  Total trades:        {stats['count']}")
    print(f"  Wins:                {stats['wins']} | Losses: {stats['losses']} | BE: {stats['bes']}")
    print(f"  Win rate:            {stats['winrate']:.1f}%")
    print(f"  Profit Factor:       {stats['pf']:.2f}")
    print(f"  Net profit:          ${stats['net']:.2f}")
    print(f"  Gross profit:        ${stats['gross_profit']:.2f}")
    print(f"  Gross loss:          ${stats['gross_loss']:.2f}")
    print(f"  Avg win:             ${stats['avg_win']:.2f}")
    print(f"  Avg loss:            ${stats['avg_loss']:.2f}")
    print(f"  Avg win/loss ratio:  {stats['avg_win']/stats['avg_loss']:.2f}" if stats['avg_loss'] > 0 else "  Avg win/loss ratio:  N/A")
    print(f"  Max drawdown:        ${max_dd:.2f} ({max_dd_pct:.1f}%)")
    print(f"  Max consec. losses:  {max_cl}")
    print(f"  Balance: ${INITIAL_BALANCE:.0f} -> ${trades[-1]['balance_after']:.2f}")

    # ========================================================
    # B. TEMPORAL ANALYSIS - BY HOUR
    # ========================================================
    print_header("B. TEMPORAL ANALYSIS - BY HOUR")

    by_hour = defaultdict(list)
    for t in trades:
        by_hour[t['hour']].append(t)

    print(f"  {'Hour':>4} | {'Count':>5} | {'WR%':>5} | {'PF':>5} | {'Net $':>8} | {'AvgWin':>7} | {'AvgLoss':>7} | Note")
    print(f"  {'-'*4} | {'-'*5} | {'-'*5} | {'-'*5} | {'-'*8} | {'-'*7} | {'-'*7} | {'-'*10}")

    toxic_hours = []
    for h in sorted(by_hour.keys()):
        s = calc_stats(by_hour[h])
        note = ""
        if s['pf'] < 0.8 and s['count'] >= 5:
            note = "** TOXIC **"
            toxic_hours.append(h)
        elif s['pf'] < 1.0 and s['count'] >= 5:
            note = "* weak *"
            toxic_hours.append(h)
        elif s['pf'] > 2.0 and s['count'] >= 5:
            note = "STRONG"
        print(f"  {h:>4} | {s['count']:>5} | {s['winrate']:>5.1f} | {s['pf']:>5.2f} | {s['net']:>8.2f} | {s['avg_win']:>7.2f} | {s['avg_loss']:>7.2f} | {note}")

    # ========================================================
    # C. TEMPORAL ANALYSIS - BY DAY
    # ========================================================
    print_header("C. TEMPORAL ANALYSIS - BY DAY OF WEEK")

    day_names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    by_day = defaultdict(list)
    for t in trades:
        by_day[t['day']].append(t)

    print(f"  {'Day':>10} | {'Count':>5} | {'WR%':>5} | {'PF':>5} | {'Net $':>8} | {'AvgWin':>7} | {'AvgLoss':>7} | Note")
    print(f"  {'-'*10} | {'-'*5} | {'-'*5} | {'-'*5} | {'-'*8} | {'-'*7} | {'-'*7} | {'-'*10}")

    toxic_days = []
    for d in sorted(by_day.keys()):
        s = calc_stats(by_day[d])
        note = ""
        if s['pf'] < 0.8 and s['count'] >= 10:
            note = "** TOXIC **"
            toxic_days.append(d)
        elif s['pf'] < 1.0 and s['count'] >= 10:
            note = "* weak *"
            toxic_days.append(d)
        elif s['pf'] > 2.0 and s['count'] >= 10:
            note = "STRONG"
        print(f"  {day_names[d]:>10} | {s['count']:>5} | {s['winrate']:>5.1f} | {s['pf']:>5.2f} | {s['net']:>8.2f} | {s['avg_win']:>7.2f} | {s['avg_loss']:>7.2f} | {note}")

    # ========================================================
    # D. TEMPORAL ANALYSIS - BY MONTH
    # ========================================================
    print_header("D. TEMPORAL ANALYSIS - BY MONTH")

    by_month = defaultdict(list)
    for t in trades:
        by_month[t['month']].append(t)

    print(f"  {'Month':>7} | {'Count':>5} | {'WR%':>5} | {'PF':>5} | {'Net $':>8}")
    print(f"  {'-'*7} | {'-'*5} | {'-'*5} | {'-'*5} | {'-'*8}")

    for m in sorted(by_month.keys()):
        s = calc_stats(by_month[m])
        print(f"  {m:>7} | {s['count']:>5} | {s['winrate']:>5.1f} | {s['pf']:>5.2f} | {s['net']:>8.2f}")

    # ========================================================
    # E. ATR ANALYSIS
    # ========================================================
    print_header("E. VOLATILITY ANALYSIS - H1 ATR(14)")

    trades_with_atr = [t for t in trades if t['atr_pips'] is not None]
    print(f"  Trades with ATR data: {len(trades_with_atr)}/{len(trades)}")

    if trades_with_atr:
        atr_values = [t['atr_pips'] for t in trades_with_atr]
        print(f"  ATR range: {min(atr_values):.1f} - {max(atr_values):.1f} pips")
        print(f"  ATR mean:  {sum(atr_values)/len(atr_values):.1f} pips")

        # Quartiles
        sorted_atr = sorted(atr_values)
        q1 = sorted_atr[len(sorted_atr)//4]
        q2 = sorted_atr[len(sorted_atr)//2]
        q3 = sorted_atr[3*len(sorted_atr)//4]
        print(f"  Quartiles: Q1={q1:.1f} | Q2={q2:.1f} | Q3={q3:.1f}")

        # ATR buckets
        atr_buckets = [
            ('< 30', 0, 30),
            ('30-45', 30, 45),
            ('45-60', 45, 60),
            ('60-80', 60, 80),
            ('80-100', 80, 100),
            ('100-130', 100, 130),
            ('> 130', 130, 999),
        ]

        print(f"\n  {'ATR Pips':>10} | {'Count':>5} | {'WR%':>5} | {'PF':>5} | {'Net $':>8} | Note")
        print(f"  {'-'*10} | {'-'*5} | {'-'*5} | {'-'*5} | {'-'*8} | {'-'*10}")

        for label, lo, hi in atr_buckets:
            bucket = [t for t in trades_with_atr if lo <= t['atr_pips'] < hi]
            if bucket:
                s = calc_stats(bucket)
                note = ""
                if s['pf'] < 0.8 and s['count'] >= 5:
                    note = "** TOXIC **"
                elif s['pf'] < 1.0 and s['count'] >= 5:
                    note = "* weak *"
                elif s['pf'] > 1.5 and s['count'] >= 5:
                    note = "GOOD"
                print(f"  {label:>10} | {s['count']:>5} | {s['winrate']:>5.1f} | {s['pf']:>5.2f} | {s['net']:>8.2f} | {note}")

        # Finer ATR buckets for optimization
        print(f"\n  --- Finer ATR buckets (10-pip steps) ---")
        print(f"  {'ATR Pips':>10} | {'Count':>5} | {'WR%':>5} | {'PF':>5} | {'Net $':>8}")
        print(f"  {'-'*10} | {'-'*5} | {'-'*5} | {'-'*5} | {'-'*8}")

        for lo in range(20, 160, 10):
            hi = lo + 10
            bucket = [t for t in trades_with_atr if lo <= t['atr_pips'] < hi]
            if len(bucket) >= 3:
                s = calc_stats(bucket)
                print(f"  {lo:>3}-{hi:<3}    | {s['count']:>5} | {s['winrate']:>5.1f} | {s['pf']:>5.2f} | {s['net']:>8.2f}")

        # Test ATR bands
        print(f"\n  --- ATR Band Tests (min-max) ---")
        print(f"  {'Band':>12} | {'Count':>5} | {'WR%':>5} | {'PF':>5} | {'Net $':>8} | {'Removed':>7}")
        print(f"  {'-'*12} | {'-'*5} | {'-'*5} | {'-'*5} | {'-'*8} | {'-'*7}")

        best_atr_band = None
        best_atr_pf = 0

        for min_atr in [0, 20, 30, 40, 50]:
            for max_atr in [80, 100, 120, 150, 200, 999]:
                if min_atr >= max_atr:
                    continue
                band = [t for t in trades_with_atr if min_atr <= t['atr_pips'] <= max_atr]
                removed = len(trades_with_atr) - len(band)
                if len(band) >= 50:
                    s = calc_stats(band)
                    if s['pf'] > best_atr_pf:
                        best_atr_pf = s['pf']
                        best_atr_band = (min_atr, max_atr, s, removed)
                    label = f"{min_atr}-{max_atr}"
                    print(f"  {label:>12} | {s['count']:>5} | {s['winrate']:>5.1f} | {s['pf']:>5.2f} | {s['net']:>8.2f} | {removed:>7}")

        if best_atr_band:
            print(f"\n  >> BEST ATR BAND: {best_atr_band[0]}-{best_atr_band[1]} pips")
            print(f"     PF={best_atr_band[2]['pf']:.2f}, Trades={best_atr_band[2]['count']}, Net=${best_atr_band[2]['net']:.2f}, Removed={best_atr_band[3]}")

    # ========================================================
    # F. EMA50 DISTANCE ANALYSIS
    # ========================================================
    print_header("F. EMA50 DISTANCE ANALYSIS")

    trades_with_ema = [t for t in trades if t['ema50_distance_pips'] is not None]
    print(f"  Trades with EMA50 data: {len(trades_with_ema)}/{len(trades)}")

    if trades_with_ema:
        ema_dists = [t['ema50_distance_pips'] for t in trades_with_ema]
        print(f"  EMA50 distance range: {min(ema_dists):.1f} - {max(ema_dists):.1f} pips")
        print(f"  EMA50 distance mean:  {sum(ema_dists)/len(ema_dists):.1f} pips")

        # Winners vs losers
        win_dists = [t['ema50_distance_pips'] for t in trades_with_ema if t['result'] == 'WIN']
        loss_dists = [t['ema50_distance_pips'] for t in trades_with_ema if t['result'] == 'LOSS']

        if win_dists:
            print(f"  Winners avg EMA dist: {sum(win_dists)/len(win_dists):.1f} pips")
        if loss_dists:
            print(f"  Losers avg EMA dist:  {sum(loss_dists)/len(loss_dists):.1f} pips")

        # EMA distance buckets
        ema_buckets = [
            ('< 30', 0, 30),
            ('30-60', 30, 60),
            ('60-100', 60, 100),
            ('100-150', 100, 150),
            ('150-200', 150, 200),
            ('200-300', 200, 300),
            ('> 300', 300, 9999),
        ]

        print(f"\n  {'EMA Dist':>10} | {'Count':>5} | {'WR%':>5} | {'PF':>5} | {'Net $':>8} | Note")
        print(f"  {'-'*10} | {'-'*5} | {'-'*5} | {'-'*5} | {'-'*8} | {'-'*10}")

        for label, lo, hi in ema_buckets:
            bucket = [t for t in trades_with_ema if lo <= t['ema50_distance_pips'] < hi]
            if bucket:
                s = calc_stats(bucket)
                note = ""
                if s['pf'] < 0.8 and s['count'] >= 5:
                    note = "** TOXIC **"
                elif s['pf'] < 1.0 and s['count'] >= 5:
                    note = "* weak *"
                elif s['pf'] > 1.5 and s['count'] >= 5:
                    note = "GOOD"
                print(f"  {label:>10} | {s['count']:>5} | {s['winrate']:>5.1f} | {s['pf']:>5.2f} | {s['net']:>8.2f} | {note}")

        # Max EMA distance filter tests
        print(f"\n  --- Max EMA50 Distance Filter Tests ---")
        print(f"  {'MaxDist':>8} | {'Count':>5} | {'WR%':>5} | {'PF':>5} | {'Net $':>8} | {'Removed':>7}")
        print(f"  {'-'*8} | {'-'*5} | {'-'*5} | {'-'*5} | {'-'*8} | {'-'*7}")

        best_ema_dist = None
        best_ema_pf = 0

        for max_dist in [50, 75, 100, 125, 150, 175, 200, 250, 300, 400, 500]:
            filtered = [t for t in trades_with_ema if t['ema50_distance_pips'] <= max_dist]
            removed = len(trades_with_ema) - len(filtered)
            if len(filtered) >= 50:
                s = calc_stats(filtered)
                if s['pf'] > best_ema_pf:
                    best_ema_pf = s['pf']
                    best_ema_dist = (max_dist, s, removed)
                print(f"  {max_dist:>8} | {s['count']:>5} | {s['winrate']:>5.1f} | {s['pf']:>5.2f} | {s['net']:>8.2f} | {removed:>7}")

        if best_ema_dist:
            print(f"\n  >> BEST EMA50 MAX DISTANCE: {best_ema_dist[0]} pips")
            print(f"     PF={best_ema_dist[1]['pf']:.2f}, Trades={best_ema_dist[1]['count']}, Net=${best_ema_dist[1]['net']:.2f}, Removed={best_ema_dist[2]}")

    # ========================================================
    # G. SL DISTANCE ANALYSIS
    # ========================================================
    print_header("G. SL DISTANCE ANALYSIS")

    sl_dists = [t['sl_distance_pips'] for t in trades]
    print(f"  SL range: {min(sl_dists):.1f} - {max(sl_dists):.1f} pips")
    print(f"  SL mean:  {sum(sl_dists)/len(sl_dists):.1f} pips")

    # Winners vs losers SL
    win_sl = [t['sl_distance_pips'] for t in trades if t['result'] == 'WIN']
    loss_sl = [t['sl_distance_pips'] for t in trades if t['result'] == 'LOSS']

    if win_sl:
        print(f"  Winners avg SL: {sum(win_sl)/len(win_sl):.1f} pips")
    if loss_sl:
        print(f"  Losers avg SL:  {sum(loss_sl)/len(loss_sl):.1f} pips")

    sl_buckets = [
        ('< 10', 0, 10),
        ('10-15', 10, 15),
        ('15-20', 15, 20),
        ('20-25', 20, 25),
        ('25-30', 25, 30),
        ('30-35', 30, 35),
        ('> 35', 35, 999),
    ]

    print(f"\n  {'SL Pips':>10} | {'Count':>5} | {'WR%':>5} | {'PF':>5} | {'Net $':>8} | Note")
    print(f"  {'-'*10} | {'-'*5} | {'-'*5} | {'-'*5} | {'-'*8} | {'-'*10}")

    for label, lo, hi in sl_buckets:
        bucket = [t for t in trades if lo <= t['sl_distance_pips'] < hi]
        if bucket:
            s = calc_stats(bucket)
            note = ""
            if s['pf'] < 0.8 and s['count'] >= 5:
                note = "** TOXIC **"
            elif s['pf'] < 1.0 and s['count'] >= 5:
                note = "* weak *"
            elif s['pf'] > 1.5 and s['count'] >= 5:
                note = "GOOD"
            print(f"  {label:>10} | {s['count']:>5} | {s['winrate']:>5.1f} | {s['pf']:>5.2f} | {s['net']:>8.2f} | {note}")

    # MinSL filter tests
    print(f"\n  --- MinSL Filter Tests ---")
    print(f"  {'MinSL':>6} | {'Count':>5} | {'WR%':>5} | {'PF':>5} | {'Net $':>8} | {'Removed':>7}")
    print(f"  {'-'*6} | {'-'*5} | {'-'*5} | {'-'*5} | {'-'*8} | {'-'*7}")

    best_minsl = None
    best_minsl_pf = 0

    for min_sl in [0, 10, 12, 15, 17, 20, 22, 25, 28, 30]:
        filtered = [t for t in trades if t['sl_distance_pips'] >= min_sl]
        removed = len(trades) - len(filtered)
        if len(filtered) >= 50:
            s = calc_stats(filtered)
            if s['pf'] > best_minsl_pf:
                best_minsl_pf = s['pf']
                best_minsl = (min_sl, s, removed)
            print(f"  {min_sl:>6} | {s['count']:>5} | {s['winrate']:>5.1f} | {s['pf']:>5.2f} | {s['net']:>8.2f} | {removed:>7}")

    if best_minsl:
        print(f"\n  >> BEST MinSL: {best_minsl[0]} pips")
        print(f"     PF={best_minsl[1]['pf']:.2f}, Trades={best_minsl[1]['count']}, Net=${best_minsl[1]['net']:.2f}, Removed={best_minsl[2]}")

    # MaxSL filter tests
    print(f"\n  --- MaxSL Filter Tests ---")
    print(f"  {'MaxSL':>6} | {'Count':>5} | {'WR%':>5} | {'PF':>5} | {'Net $':>8} | {'Removed':>7}")
    print(f"  {'-'*6} | {'-'*5} | {'-'*5} | {'-'*5} | {'-'*8} | {'-'*7}")

    for max_sl in [20, 25, 30, 35, 40, 45, 50, 60, 999]:
        filtered = [t for t in trades if t['sl_distance_pips'] <= max_sl]
        removed = len(trades) - len(filtered)
        if len(filtered) >= 50:
            s = calc_stats(filtered)
            label = f"{max_sl}" if max_sl < 999 else "None"
            print(f"  {label:>6} | {s['count']:>5} | {s['winrate']:>5.1f} | {s['pf']:>5.2f} | {s['net']:>8.2f} | {removed:>7}")

    # ========================================================
    # H. DIRECTION ANALYSIS
    # ========================================================
    print_header("H. DIRECTION ANALYSIS - BUY vs SELL")

    buys = [t for t in trades if t['direction'] == 'buy']
    sells = [t for t in trades if t['direction'] == 'sell']

    buy_stats = calc_stats(buys)
    sell_stats = calc_stats(sells)

    print(f"  {'':>6} | {'Count':>5} | {'WR%':>5} | {'PF':>5} | {'Net $':>8} | {'AvgWin':>7} | {'AvgLoss':>7}")
    print(f"  {'-'*6} | {'-'*5} | {'-'*5} | {'-'*5} | {'-'*8} | {'-'*7} | {'-'*7}")
    print(f"  {'BUY':>6} | {buy_stats['count']:>5} | {buy_stats['winrate']:>5.1f} | {buy_stats['pf']:>5.2f} | {buy_stats['net']:>8.2f} | {buy_stats['avg_win']:>7.2f} | {buy_stats['avg_loss']:>7.2f}")
    print(f"  {'SELL':>6} | {sell_stats['count']:>5} | {sell_stats['winrate']:>5.1f} | {sell_stats['pf']:>5.2f} | {sell_stats['net']:>8.2f} | {sell_stats['avg_win']:>7.2f} | {sell_stats['avg_loss']:>7.2f}")

    # ========================================================
    # I. TRADE DURATION ANALYSIS
    # ========================================================
    print_header("I. TRADE DURATION ANALYSIS")

    win_durations = [t['duration_min'] for t in trades if t['result'] == 'WIN']
    loss_durations = [t['duration_min'] for t in trades if t['result'] == 'LOSS']
    be_durations = [t['duration_min'] for t in trades if t['result'] == 'BE']

    if win_durations:
        print(f"  WIN  avg duration: {sum(win_durations)/len(win_durations):.0f} min ({sum(win_durations)/len(win_durations)/60:.1f}h)")
        print(f"         min: {min(win_durations):.0f} min, max: {max(win_durations):.0f} min")
    if loss_durations:
        print(f"  LOSS avg duration: {sum(loss_durations)/len(loss_durations):.0f} min ({sum(loss_durations)/len(loss_durations)/60:.1f}h)")
        print(f"         min: {min(loss_durations):.0f} min, max: {max(loss_durations):.0f} min")
    if be_durations:
        print(f"  BE   avg duration: {sum(be_durations)/len(be_durations):.0f} min ({sum(be_durations)/len(be_durations)/60:.1f}h)")

    # Duration buckets
    dur_buckets = [
        ('< 30min', 0, 30),
        ('30-60min', 30, 60),
        ('1-2h', 60, 120),
        ('2-4h', 120, 240),
        ('4-8h', 240, 480),
        ('> 8h', 480, 99999),
    ]

    print(f"\n  {'Duration':>10} | {'Count':>5} | {'WR%':>5} | {'PF':>5} | {'Net $':>8}")
    print(f"  {'-'*10} | {'-'*5} | {'-'*5} | {'-'*5} | {'-'*8}")

    for label, lo, hi in dur_buckets:
        bucket = [t for t in trades if lo <= t['duration_min'] < hi]
        if bucket:
            s = calc_stats(bucket)
            print(f"  {label:>10} | {s['count']:>5} | {s['winrate']:>5.1f} | {s['pf']:>5.2f} | {s['net']:>8.2f}")

    # ========================================================
    # J. SESSION ANALYSIS
    # ========================================================
    print_header("J. SESSION ANALYSIS")

    def get_session(hour):
        if 8 <= hour < 12:
            return 'London AM'
        elif 12 <= hour < 14:
            return 'Overlap'
        elif 14 <= hour < 17:
            return 'New York PM'
        elif 17 <= hour < 21:
            return 'Late US'
        else:
            return 'Off-hours'

    by_session = defaultdict(list)
    for t in trades:
        by_session[get_session(t['hour'])].append(t)

    print(f"  {'Session':>14} | {'Count':>5} | {'WR%':>5} | {'PF':>5} | {'Net $':>8}")
    print(f"  {'-'*14} | {'-'*5} | {'-'*5} | {'-'*5} | {'-'*8}")

    for session in ['London AM', 'Overlap', 'New York PM', 'Late US', 'Off-hours']:
        if session in by_session:
            s = calc_stats(by_session[session])
            print(f"  {session:>14} | {s['count']:>5} | {s['winrate']:>5.1f} | {s['pf']:>5.2f} | {s['net']:>8.2f}")

    # ========================================================
    # K. RECOMMENDATIONS
    # ========================================================
    print_header("K. SPECIFIC RECOMMENDATIONS FOR USDJPY PRESET")

    # Individual filter impact analysis
    print("  --- Individual Filter Impact (standalone) ---\n")

    # 1. Hour blocks - only truly toxic ones
    hours_to_block_candidates = []
    for h in sorted(by_hour.keys()):
        s = calc_stats(by_hour[h])
        if s['pf'] < 0.8 and s['count'] >= 10 and s['net'] < -500:
            hours_to_block_candidates.append((h, s['net'], s['pf'], s['count']))
            print(f"  Hour {h}: PF={s['pf']:.2f}, Net=${s['net']:.0f}, Count={s['count']} -> BLOCK")
        elif s['pf'] < 1.0 and s['count'] >= 10 and s['net'] < -200:
            hours_to_block_candidates.append((h, s['net'], s['pf'], s['count']))
            print(f"  Hour {h}: PF={s['pf']:.2f}, Net=${s['net']:.0f}, Count={s['count']} -> BLOCK (weak)")

    # 2. Day blocks - only clearly toxic
    days_to_block_candidates = []
    for d in sorted(by_day.keys()):
        s = calc_stats(by_day[d])
        if s['pf'] < 0.8 and s['count'] >= 15 and s['net'] < -500:
            days_to_block_candidates.append((d, s['net'], s['pf'], s['count']))
            print(f"  {day_names[d]}: PF={s['pf']:.2f}, Net=${s['net']:.0f}, Count={s['count']} -> BLOCK")

    # ========================================================
    # L. SIMULATED PERFORMANCE - SMART COMBINATION SEARCH
    # ========================================================
    print_header("L. SIMULATED PERFORMANCE - COMBINATION SEARCH")

    # Test many combinations, find best ones with >50 trades
    def apply_filters(trades_list, block_hours=set(), block_days=set(),
                      min_atr=0, max_atr=999, max_ema=9999, min_sl=0):
        result = []
        for t in trades_list:
            if t['hour'] in block_hours:
                continue
            if t['day'] in block_days:
                continue
            if t['atr_pips'] is not None and (t['atr_pips'] < min_atr or t['atr_pips'] > max_atr):
                continue
            if t['ema50_distance_pips'] is not None and t['ema50_distance_pips'] > max_ema:
                continue
            if t['sl_distance_pips'] < min_sl:
                continue
            result.append(t)
        return result

    # Candidate hour sets (conservative - don't block too many)
    hour_sets = [
        (set(), "no hour block"),
        ({9, 11}, "block 9,11"),
        ({9}, "block 9"),
        ({11}, "block 11"),
        ({9, 11, 16}, "block 9,11,16"),
    ]

    # Candidate day sets (conservative)
    day_sets = [
        (set(), "no day block"),
        ({0}, "block Mon"),
        ({0, 4}, "block Mon,Fri"),
        ({0, 1}, "block Mon,Tue"),
    ]

    # ATR options (USDJPY has narrow range 10-43 pips, so limited)
    atr_options = [
        (0, 999, "no ATR filter"),
        (15, 999, "ATR>=15"),
        (18, 999, "ATR>=18"),
        (20, 999, "ATR>=20"),
    ]

    # EMA options
    ema_options = [
        (9999, "no EMA filter"),
        (100, "EMA<=100"),
        (75, "EMA<=75"),
    ]

    # MinSL options (range 15-25, so be careful)
    sl_options = [
        (0, "no MinSL"),
        (17, "MinSL>=17"),
        (18, "MinSL>=18"),
        (20, "MinSL>=20"),
    ]

    print(f"  Testing {len(hour_sets)*len(day_sets)*len(atr_options)*len(ema_options)*len(sl_options)} combinations...\n")

    best_combos = []

    for h_set, h_label in hour_sets:
        for d_set, d_label in day_sets:
            for min_atr, max_atr, atr_label in atr_options:
                for max_ema, ema_label in ema_options:
                    for min_sl, sl_label in sl_options:
                        filtered = apply_filters(trades, h_set, d_set, min_atr, max_atr, max_ema, min_sl)
                        if len(filtered) < 50:
                            continue
                        s = calc_stats(filtered)
                        dd_val, dd_pct_val = max_drawdown(filtered)
                        combo = {
                            'hours': h_set, 'days': d_set,
                            'min_atr': min_atr, 'max_atr': max_atr,
                            'max_ema': max_ema, 'min_sl': min_sl,
                            'label': f"{h_label} | {d_label} | {atr_label} | {ema_label} | {sl_label}",
                            'stats': s, 'dd_pct': dd_pct_val,
                            'count': s['count'], 'pf': s['pf'], 'net': s['net'],
                        }
                        best_combos.append(combo)

    # Sort by PF (primary) then by trade count (secondary)
    best_combos.sort(key=lambda x: (x['pf'], x['count']), reverse=True)

    print(f"  Found {len(best_combos)} valid combinations (>50 trades)")
    print(f"\n  --- TOP 15 COMBINATIONS (by PF, min 50 trades) ---")
    print(f"  {'#':>2} | {'Count':>5} | {'WR%':>5} | {'PF':>5} | {'Net $':>8} | {'DD%':>5} | Filters")
    print(f"  {'-'*2} | {'-'*5} | {'-'*5} | {'-'*5} | {'-'*8} | {'-'*5} | {'-'*50}")

    for i, c in enumerate(best_combos[:15]):
        print(f"  {i+1:>2} | {c['count']:>5} | {c['stats']['winrate']:>5.1f} | {c['pf']:>5.2f} | {c['net']:>8.2f} | {c['dd_pct']:>5.1f} | {c['label']}")

    # Also show best combos with relaxed criteria (>80 trades for robustness)
    robust_combos = [c for c in best_combos if c['count'] >= 80]
    if robust_combos:
        robust_combos.sort(key=lambda x: x['pf'], reverse=True)
        print(f"\n  --- TOP 10 ROBUST COMBINATIONS (min 80 trades) ---")
        print(f"  {'#':>2} | {'Count':>5} | {'WR%':>5} | {'PF':>5} | {'Net $':>8} | {'DD%':>5} | Filters")
        print(f"  {'-'*2} | {'-'*5} | {'-'*5} | {'-'*5} | {'-'*8} | {'-'*5} | {'-'*50}")
        for i, c in enumerate(robust_combos[:10]):
            print(f"  {i+1:>2} | {c['count']:>5} | {c['stats']['winrate']:>5.1f} | {c['pf']:>5.2f} | {c['net']:>8.2f} | {c['dd_pct']:>5.1f} | {c['label']}")

    # Pick RECOMMENDED combo: best PF with >60 trades and DD<15%
    recommended = [c for c in best_combos if c['count'] >= 60 and c['dd_pct'] < 15]
    if recommended:
        recommended.sort(key=lambda x: x['pf'], reverse=True)
        rec = recommended[0]
    elif best_combos:
        rec = best_combos[0]
    else:
        rec = None

    if rec:
        print_header("M. RECOMMENDED PRESET")
        print(f"  Filters: {rec['label']}")
        print(f"  Block hours: {sorted(rec['hours']) if rec['hours'] else 'none'}")
        print(f"  Block days:  {[day_names[d] for d in sorted(rec['days'])] if rec['days'] else 'none'}")
        print(f"  ATR min:     {rec['min_atr']} pips")
        print(f"  ATR max:     {rec['max_atr']} pips")
        print(f"  EMA50 max:   {rec['max_ema']} pips")
        print(f"  MinSL:       {rec['min_sl']} pips")

        print(f"\n  --- BEFORE (Raw) ---")
        print(f"  Trades: {stats['count']} | WR: {stats['winrate']:.1f}% | PF: {stats['pf']:.2f} | Net: ${stats['net']:.2f} | DD: {max_dd_pct:.1f}%")

        sim_stats = rec['stats']
        print(f"\n  --- AFTER (Filtered) ---")
        print(f"  Trades: {sim_stats['count']} | WR: {sim_stats['winrate']:.1f}% | PF: {sim_stats['pf']:.2f} | Net: ${sim_stats['net']:.2f} | DD: {rec['dd_pct']:.1f}%")
        print(f"  Trades removed: {stats['count'] - sim_stats['count']} ({(stats['count'] - sim_stats['count'])/stats['count']*100:.1f}%)")

        filtered_trades = apply_filters(trades, rec['hours'], rec['days'],
                                         rec['min_atr'], rec['max_atr'],
                                         rec['max_ema'], rec['min_sl'])
        sim_cl = max_consecutive_losses(filtered_trades)
        print(f"  Max consec losses: {sim_cl}")

        # Check targets
        print(f"\n  --- TARGET CHECK ---")
        pf_ok = sim_stats['pf'] > 1.5
        dd_ok = rec['dd_pct'] < 10
        trades_ok = sim_stats['count'] > 50
        print(f"  PF > 1.5:     {'PASS' if pf_ok else 'FAIL'} ({sim_stats['pf']:.2f})")
        print(f"  DD < 10%:     {'PASS' if dd_ok else 'FAIL'} ({rec['dd_pct']:.1f}%)")
        print(f"  Trades > 50:  {'PASS' if trades_ok else 'FAIL'} ({sim_stats['count']})")

        # Incremental filter impact for recommended combo
        print(f"\n  --- INCREMENTAL FILTER IMPACT (recommended) ---")
        print(f"  {'Filter':>25} | {'Count':>5} | {'WR%':>5} | {'PF':>5} | {'Net $':>8} | {'DD%':>5}")
        print(f"  {'-'*25} | {'-'*5} | {'-'*5} | {'-'*5} | {'-'*8} | {'-'*5}")

        s0 = calc_stats(trades)
        dd0, dd0_pct = max_drawdown(trades)
        print(f"  {'Raw baseline':>25} | {s0['count']:>5} | {s0['winrate']:>5.1f} | {s0['pf']:>5.2f} | {s0['net']:>8.2f} | {dd0_pct:>5.1f}")

        f1 = [t for t in trades if t['hour'] not in rec['hours']] if rec['hours'] else trades
        if rec['hours']:
            s1 = calc_stats(f1)
            dd1, dd1_pct = max_drawdown(f1)
            print(f"  {'+ Block hours':>25} | {s1['count']:>5} | {s1['winrate']:>5.1f} | {s1['pf']:>5.2f} | {s1['net']:>8.2f} | {dd1_pct:>5.1f}")

        f2 = [t for t in f1 if t['day'] not in rec['days']] if rec['days'] else f1
        if rec['days']:
            s2 = calc_stats(f2)
            dd2, dd2_pct = max_drawdown(f2)
            print(f"  {'+ Block days':>25} | {s2['count']:>5} | {s2['winrate']:>5.1f} | {s2['pf']:>5.2f} | {s2['net']:>8.2f} | {dd2_pct:>5.1f}")

        if rec['min_atr'] > 0:
            f3 = [t for t in f2 if t['atr_pips'] is not None and t['atr_pips'] >= rec['min_atr']]
            s3 = calc_stats(f3)
            dd3, dd3_pct = max_drawdown(f3)
            print(f"  {'+ ATR filter':>25} | {s3['count']:>5} | {s3['winrate']:>5.1f} | {s3['pf']:>5.2f} | {s3['net']:>8.2f} | {dd3_pct:>5.1f}")
        else:
            f3 = f2

        if rec['max_ema'] < 9999:
            f4 = [t for t in f3 if t['ema50_distance_pips'] is not None and t['ema50_distance_pips'] <= rec['max_ema']]
            s4 = calc_stats(f4)
            dd4, dd4_pct = max_drawdown(f4)
            print(f"  {'+ EMA50 filter':>25} | {s4['count']:>5} | {s4['winrate']:>5.1f} | {s4['pf']:>5.2f} | {s4['net']:>8.2f} | {dd4_pct:>5.1f}")
        else:
            f4 = f3

        if rec['min_sl'] > 0:
            f5 = [t for t in f4 if t['sl_distance_pips'] >= rec['min_sl']]
            s5 = calc_stats(f5)
            dd5, dd5_pct = max_drawdown(f5)
            print(f"  {'+ MinSL':>25} | {s5['count']:>5} | {s5['winrate']:>5.1f} | {s5['pf']:>5.2f} | {s5['net']:>8.2f} | {dd5_pct:>5.1f}")

    # ========================================================
    # FINAL SUMMARY
    # ========================================================
    print_header("FINAL SUMMARY - USDJPY PRESET PARAMETERS")

    if rec:
        print(f"  Pair:            USDJPY")
        print(f"  MinSL:           {rec['min_sl']} pips")
        print(f"  ATR Min:         {rec['min_atr']} pips")
        print(f"  ATR Max:         {rec['max_atr']} pips")
        print(f"  EMA50 Max Dist:  {rec['max_ema']} pips")
        print(f"  Blocked Hours:   {sorted(rec['hours']) if rec['hours'] else 'none'}")
        print(f"  Blocked Days:    {[day_names[d] for d in sorted(rec['days'])] if rec['days'] else 'none'}")

        print(f"\n  Expected performance:")
        print(f"    Trades:  {rec['stats']['count']} (from {stats['count']})")
        print(f"    WR:      {rec['stats']['winrate']:.1f}%")
        print(f"    PF:      {rec['stats']['pf']:.2f}")
        print(f"    Net:     ${rec['stats']['net']:.2f}")
        print(f"    DD:      {rec['dd_pct']:.1f}%")
    else:
        print(f"  No valid combination found meeting criteria.")

    print("\n" + "=" * 80)
    print("  END OF ANALYSIS")
    print("=" * 80)

if __name__ == '__main__':
    main()
