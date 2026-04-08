#!/usr/bin/env python3
"""
GBPUSD EMA Pullback EA - Comprehensive Trade Analysis
Analyzes 732 trades over 3 years (Apr 2023 - Apr 2026)
Goal: Find GBPUSD-specific filters to turn -51% into profitable
"""

import csv
import math
from datetime import datetime, timedelta
from collections import defaultdict

# ============================================================
# CONFIG
# ============================================================
TRADE_FILE = r"C:\Users\projets\botTrading\historique trade gbpusd 3ans.txt"
H1_FILE = r"C:\Users\projets\botTrading\GBPUSD60_cut.csv"
M15_FILE = r"C:\Users\projets\botTrading\GBPUSD15_cut.csv"
PIP = 0.0001  # GBPUSD pip size
INITIAL_BALANCE = 10000.0

# ============================================================
# DATA LOADING
# ============================================================

def load_h1_data(filepath):
    """Load H1 OHLCV data"""
    data = {}
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
                o, h, l, c = float(fields[2]), float(fields[3]), float(fields[4]), float(fields[5])
                data[dt] = {'open': o, 'high': h, 'low': l, 'close': c}
            except:
                continue
    return data


def load_trades(filepath):
    """Parse trade history into structured trade records"""
    lines = []
    with open(filepath, 'r') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.split('\t')
            # Format: SeqNum  DateTime  Action  Ticket  Lots  Price  SL  TP  Profit  Balance
            if len(parts) < 10:
                continue
            try:
                record = {
                    'seq': int(parts[0]),
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
                lines.append(record)
            except Exception as e:
                continue
    return lines


def reconstitute_trades(raw_lines):
    """Group raw lines by ticket into complete trades"""
    tickets = defaultdict(list)
    for r in raw_lines:
        tickets[r['ticket']].append(r)

    trades = []
    for ticket in sorted(tickets.keys()):
        events = sorted(tickets[ticket], key=lambda x: x['datetime'])
        entry_event = events[0]
        exit_event = events[-1]

        if entry_event['action'] not in ('buy', 'sell'):
            continue

        direction = entry_event['action'].upper()
        entry_price = entry_event['price']
        entry_time = entry_event['datetime']
        exit_time = exit_event['datetime']
        exit_price = exit_event['price']
        lots = entry_event['lots']
        profit = exit_event['profit']
        balance_after = exit_event['balance']

        # SL from entry or last modify before exit
        sl = entry_event['sl']
        tp = entry_event['tp']
        for e in events:
            if e['action'] == 'modify':
                sl = e['sl']
                tp = e['tp']
            elif e['action'] in ('s/l', 't/p'):
                break

        # Original SL/TP from entry
        orig_sl = entry_event['sl']
        orig_tp = entry_event['tp']

        # SL distance in pips
        if direction == 'BUY':
            sl_dist = (entry_price - orig_sl) / PIP
            tp_dist = (orig_tp - entry_price) / PIP if orig_tp > 0 else 0
        else:
            sl_dist = (orig_sl - entry_price) / PIP
            tp_dist = (entry_price - orig_tp) / PIP if orig_tp > 0 else 0

        planned_rr = tp_dist / sl_dist if sl_dist > 0 else 0

        # Actual RR
        if direction == 'BUY':
            actual_move = (exit_price - entry_price) / PIP
        else:
            actual_move = (entry_price - exit_price) / PIP
        actual_rr = actual_move / sl_dist if sl_dist > 0 else 0

        # Exit type
        exit_action = exit_event['action']

        # Result
        if abs(profit) < 1.0 and abs(actual_move) < 3:
            result = 'BE'
        elif profit > 0:
            result = 'WIN'
        else:
            result = 'LOSS'

        duration_min = (exit_time - entry_time).total_seconds() / 60

        trade = {
            'ticket': ticket,
            'direction': direction,
            'entry_time': entry_time,
            'exit_time': exit_time,
            'entry_price': entry_price,
            'exit_price': exit_price,
            'sl': orig_sl,
            'tp': orig_tp,
            'final_sl': sl,
            'final_tp': tp,
            'lots': lots,
            'profit': profit,
            'balance_after': balance_after,
            'sl_dist_pips': round(sl_dist, 1),
            'tp_dist_pips': round(tp_dist, 1),
            'planned_rr': round(planned_rr, 2),
            'actual_rr': round(actual_rr, 2),
            'result': result,
            'exit_type': exit_action,
            'duration_min': round(duration_min, 1),
            'hour': entry_time.hour,
            'day': entry_time.strftime('%A'),
            'day_num': entry_time.weekday(),
            'month': entry_time.strftime('%Y-%m'),
        }
        trades.append(trade)

    return trades


def compute_h1_atr(h1_data, period=14):
    """Compute ATR(14) for each H1 bar"""
    sorted_keys = sorted(h1_data.keys())
    atr_map = {}
    trs = []
    prev_close = None
    for dt in sorted_keys:
        bar = h1_data[dt]
        if prev_close is not None:
            tr = max(bar['high'] - bar['low'],
                     abs(bar['high'] - prev_close),
                     abs(bar['low'] - prev_close))
        else:
            tr = bar['high'] - bar['low']
        trs.append(tr)
        prev_close = bar['close']
        if len(trs) >= period:
            atr_val = sum(trs[-period:]) / period
            atr_map[dt] = atr_val / PIP  # in pips
    return atr_map


def compute_h1_ema50(h1_data):
    """Compute EMA(50) for each H1 bar"""
    sorted_keys = sorted(h1_data.keys())
    ema_map = {}
    ema = None
    k = 2.0 / (50 + 1)
    for dt in sorted_keys:
        close = h1_data[dt]['close']
        if ema is None:
            ema = close
        else:
            ema = close * k + ema * (1 - k)
        ema_map[dt] = ema
    return ema_map


def get_nearest_h1(h1_keys_sorted, trade_time):
    """Find the H1 bar at or just before trade entry time"""
    # H1 bar at the start of the hour
    target = trade_time.replace(minute=0, second=0, microsecond=0)
    # Binary search
    lo, hi = 0, len(h1_keys_sorted) - 1
    best = None
    while lo <= hi:
        mid = (lo + hi) // 2
        if h1_keys_sorted[mid] <= target:
            best = mid
            lo = mid + 1
        else:
            hi = mid - 1
    return best


def enrich_trades_with_indicators(trades, h1_data, atr_map, ema_map):
    """Add ATR and EMA50 distance to each trade"""
    h1_keys = sorted(h1_data.keys())
    atr_keys = sorted(atr_map.keys())
    ema_keys = sorted(ema_map.keys())

    for t in trades:
        idx = get_nearest_h1(h1_keys, t['entry_time'])
        if idx is not None:
            dt = h1_keys[idx]
            t['atr'] = atr_map.get(dt, None)
            ema_val = ema_map.get(dt, None)
            if ema_val:
                t['ema50_dist'] = round(abs(t['entry_price'] - ema_val) / PIP, 1)
            else:
                t['ema50_dist'] = None
        else:
            t['atr'] = None
            t['ema50_dist'] = None


# ============================================================
# ANALYSIS FUNCTIONS
# ============================================================

def calc_stats(trades_subset):
    """Calculate key stats for a subset of trades"""
    if not trades_subset:
        return {'count': 0, 'wins': 0, 'losses': 0, 'be': 0, 'winrate': 0,
                'pf': 0, 'net': 0, 'avg_win': 0, 'avg_loss': 0}
    wins = [t for t in trades_subset if t['result'] == 'WIN']
    losses = [t for t in trades_subset if t['result'] == 'LOSS']
    bes = [t for t in trades_subset if t['result'] == 'BE']
    gross_profit = sum(t['profit'] for t in wins)
    gross_loss = abs(sum(t['profit'] for t in losses))
    net = sum(t['profit'] for t in trades_subset)
    pf = gross_profit / gross_loss if gross_loss > 0 else 999
    wr = len(wins) / len(trades_subset) * 100 if trades_subset else 0
    avg_w = gross_profit / len(wins) if wins else 0
    avg_l = gross_loss / len(losses) if losses else 0
    return {
        'count': len(trades_subset),
        'wins': len(wins),
        'losses': len(losses),
        'be': len(bes),
        'winrate': round(wr, 1),
        'pf': round(pf, 2),
        'net': round(net, 2),
        'avg_win': round(avg_w, 2),
        'avg_loss': round(avg_l, 2),
    }


def max_consecutive_losses(trades):
    """Find max consecutive losing trades"""
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
    """Calculate max drawdown from trade balances"""
    if not trades:
        return 0, 0
    peak = INITIAL_BALANCE
    max_dd = 0
    max_dd_pct = 0
    for t in trades:
        bal = t['balance_after']
        if bal > peak:
            peak = bal
        dd = peak - bal
        dd_pct = dd / peak * 100
        if dd > max_dd:
            max_dd = dd
            max_dd_pct = dd_pct
    return round(max_dd, 2), round(max_dd_pct, 1)


def print_header(title):
    print(f"\n{'='*80}")
    print(f" {title}")
    print(f"{'='*80}")


def print_table(headers, rows, col_widths=None):
    """Print formatted table"""
    if col_widths is None:
        col_widths = []
        for i, h in enumerate(headers):
            max_w = len(str(h))
            for r in rows:
                max_w = max(max_w, len(str(r[i])))
            col_widths.append(max_w + 2)

    # Header
    header_line = ""
    for i, h in enumerate(headers):
        header_line += str(h).rjust(col_widths[i])
    print(header_line)
    print("-" * sum(col_widths))

    # Rows
    for r in rows:
        line = ""
        for i, val in enumerate(r):
            line += str(val).rjust(col_widths[i])
        print(line)


# ============================================================
# MAIN ANALYSIS
# ============================================================

def main():
    print("Loading data...")
    raw_lines = load_trades(TRADE_FILE)
    print(f"  Raw lines: {len(raw_lines)}")

    trades = reconstitute_trades(raw_lines)
    print(f"  Reconstituted trades: {len(trades)}")

    h1_data = load_h1_data(H1_FILE)
    print(f"  H1 bars: {len(h1_data)}")

    print("Computing indicators...")
    atr_map = compute_h1_atr(h1_data)
    ema_map = compute_h1_ema50(h1_data)

    print("Enriching trades...")
    enrich_trades_with_indicators(trades, h1_data, atr_map, ema_map)

    # Sort by entry time
    trades.sort(key=lambda x: x['entry_time'])

    # ========================================================
    # A. GLOBAL STATS
    # ========================================================
    print_header("A. GLOBAL STATISTICS")
    stats = calc_stats(trades)
    dd_abs, dd_pct = max_drawdown(trades)
    mcl = max_consecutive_losses(trades)

    print(f"  Period:             {trades[0]['entry_time'].strftime('%Y-%m-%d')} to {trades[-1]['entry_time'].strftime('%Y-%m-%d')}")
    print(f"  Total trades:       {stats['count']}")
    print(f"  Wins:               {stats['wins']}  |  Losses: {stats['losses']}  |  BE: {stats['be']}")
    print(f"  Win rate:           {stats['winrate']}%")
    print(f"  Profit Factor:      {stats['pf']}")
    print(f"  Net profit:         ${stats['net']}")
    print(f"  Avg win:            ${stats['avg_win']}")
    print(f"  Avg loss:           ${stats['avg_loss']}")
    print(f"  Max consec losses:  {mcl}")
    print(f"  Max drawdown:       ${dd_abs} ({dd_pct}%)")
    print(f"  Starting balance:   ${INITIAL_BALANCE}")
    print(f"  Ending balance:     ${trades[-1]['balance_after']}")

    # Direction breakdown
    buys = [t for t in trades if t['direction'] == 'BUY']
    sells = [t for t in trades if t['direction'] == 'SELL']
    buy_stats = calc_stats(buys)
    sell_stats = calc_stats(sells)

    # ========================================================
    # B. DIRECTION ANALYSIS
    # ========================================================
    print_header("B. DIRECTION ANALYSIS (BUY vs SELL)")
    headers = ['Direction', 'Count', 'Wins', 'Losses', 'WR%', 'PF', 'Net $', 'Avg Win', 'Avg Loss']
    rows = [
        ('BUY', buy_stats['count'], buy_stats['wins'], buy_stats['losses'],
         buy_stats['winrate'], buy_stats['pf'], buy_stats['net'], buy_stats['avg_win'], buy_stats['avg_loss']),
        ('SELL', sell_stats['count'], sell_stats['wins'], sell_stats['losses'],
         sell_stats['winrate'], sell_stats['pf'], sell_stats['net'], sell_stats['avg_win'], sell_stats['avg_loss']),
    ]
    print_table(headers, rows)

    # ========================================================
    # C. TEMPORAL ANALYSIS
    # ========================================================
    print_header("C1. ANALYSIS BY HOUR (Entry Hour)")
    hours_data = defaultdict(list)
    for t in trades:
        hours_data[t['hour']].append(t)

    headers = ['Hour', 'Count', 'Wins', 'Losses', 'WR%', 'PF', 'Net $']
    rows = []
    for h in sorted(hours_data.keys()):
        s = calc_stats(hours_data[h])
        rows.append((f"{h:02d}:00", s['count'], s['wins'], s['losses'], s['winrate'], s['pf'], s['net']))
    print_table(headers, rows)

    # By day
    print_header("C2. ANALYSIS BY DAY OF WEEK")
    days_data = defaultdict(list)
    day_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']
    for t in trades:
        days_data[t['day']].append(t)

    headers = ['Day', 'Count', 'Wins', 'Losses', 'WR%', 'PF', 'Net $']
    rows = []
    for d in day_order:
        if d in days_data:
            s = calc_stats(days_data[d])
            rows.append((d, s['count'], s['wins'], s['losses'], s['winrate'], s['pf'], s['net']))
    print_table(headers, rows)

    # By month
    print_header("C3. ANALYSIS BY MONTH")
    months_data = defaultdict(list)
    for t in trades:
        months_data[t['month']].append(t)

    headers = ['Month', 'Count', 'Wins', 'Losses', 'WR%', 'PF', 'Net $']
    rows = []
    for m in sorted(months_data.keys()):
        s = calc_stats(months_data[m])
        rows.append((m, s['count'], s['wins'], s['losses'], s['winrate'], s['pf'], s['net']))
    print_table(headers, rows)

    # Heatmap: hour x day
    print_header("C4. PROFIT HEATMAP: Hour x Day (Net $)")
    heatmap = defaultdict(lambda: defaultdict(list))
    for t in trades:
        heatmap[t['hour']][t['day']].append(t)

    # Print header
    all_hours = sorted(set(t['hour'] for t in trades))
    print(f"{'Hour':>6}", end='')
    for d in day_order:
        print(f"{d[:3]:>10}", end='')
    print(f"{'TOTAL':>10}")
    print("-" * (6 + 10 * 6))

    for h in all_hours:
        print(f"{h:02d}:00 ", end='')
        row_total = 0
        for d in day_order:
            tlist = heatmap[h][d]
            net = sum(t['profit'] for t in tlist)
            row_total += net
            count = len(tlist)
            if count == 0:
                print(f"{'--':>10}", end='')
            else:
                print(f"{net:>9.0f}$", end='')
        print(f"{row_total:>9.0f}$")

    # Identify toxic combos
    print_header("C5. TOXIC HOUR+DAY COMBINATIONS (Net < -$50, sorted)")
    toxic_combos = []
    for h in all_hours:
        for d in day_order:
            tlist = heatmap[h][d]
            if tlist:
                s = calc_stats(tlist)
                net = s['net']
                if net < -50:
                    toxic_combos.append((h, d, s['count'], s['winrate'], s['pf'], net))

    toxic_combos.sort(key=lambda x: x[5])
    headers = ['Hour', 'Day', 'Count', 'WR%', 'PF', 'Net $']
    rows = [(f"{h:02d}:00", d, c, wr, pf, net) for h, d, c, wr, pf, net in toxic_combos]
    print_table(headers, rows)
    print(f"\n  Total toxic combos: {len(toxic_combos)}")
    total_toxic_loss = sum(x[5] for x in toxic_combos)
    total_toxic_trades = sum(x[2] for x in toxic_combos)
    print(f"  Total trades in toxic combos: {total_toxic_trades}")
    print(f"  Total loss from toxic combos: ${total_toxic_loss:.2f}")

    # ========================================================
    # D. ATR ANALYSIS
    # ========================================================
    print_header("D1. ATR(14) QUARTILE ANALYSIS")
    trades_with_atr = [t for t in trades if t.get('atr') is not None]
    print(f"  Trades with ATR data: {len(trades_with_atr)} / {len(trades)}")

    if trades_with_atr:
        atrs = sorted([t['atr'] for t in trades_with_atr])
        q1 = atrs[len(atrs)//4]
        q2 = atrs[len(atrs)//2]
        q3 = atrs[3*len(atrs)//4]
        print(f"  ATR range: {min(atrs):.1f} - {max(atrs):.1f} pips")
        print(f"  Quartiles: Q1={q1:.1f}, Q2={q2:.1f}, Q3={q3:.1f}")

        buckets = [
            (f"< {q1:.0f}", [t for t in trades_with_atr if t['atr'] < q1]),
            (f"{q1:.0f}-{q2:.0f}", [t for t in trades_with_atr if q1 <= t['atr'] < q2]),
            (f"{q2:.0f}-{q3:.0f}", [t for t in trades_with_atr if q2 <= t['atr'] < q3]),
            (f"> {q3:.0f}", [t for t in trades_with_atr if t['atr'] >= q3]),
        ]
        headers = ['ATR Range', 'Count', 'Wins', 'Losses', 'WR%', 'PF', 'Net $']
        rows = []
        for label, subset in buckets:
            s = calc_stats(subset)
            rows.append((label, s['count'], s['wins'], s['losses'], s['winrate'], s['pf'], s['net']))
        print_table(headers, rows)

        # Specific ATR bands
        print_header("D2. SPECIFIC ATR BANDS")
        atr_bands = [
            (4, 10), (6, 12), (6, 15), (8, 14), (8, 16), (8, 18),
            (10, 16), (10, 18), (10, 20), (12, 18), (12, 20), (12, 22),
            (14, 22), (14, 24), (8, 20), (6, 20),
        ]
        headers = ['ATR Band', 'Count', 'Wins', 'Losses', 'WR%', 'PF', 'Net $', '$/Trade']
        rows = []
        for lo, hi in sorted(atr_bands):
            subset = [t for t in trades_with_atr if lo <= t['atr'] <= hi]
            s = calc_stats(subset)
            avg = s['net'] / s['count'] if s['count'] > 0 else 0
            rows.append((f"{lo}-{hi}", s['count'], s['wins'], s['losses'],
                        s['winrate'], s['pf'], s['net'], round(avg, 2)))
        print_table(headers, rows)

        # Fine-grained ATR analysis (2-pip buckets)
        print_header("D3. ATR DISTRIBUTION (2-pip buckets)")
        atr_buckets = defaultdict(list)
        for t in trades_with_atr:
            bucket = int(t['atr'] // 2) * 2
            atr_buckets[bucket].append(t)

        headers = ['ATR', 'Count', 'Wins', 'Losses', 'WR%', 'PF', 'Net $']
        rows = []
        for b in sorted(atr_buckets.keys()):
            s = calc_stats(atr_buckets[b])
            rows.append((f"{b}-{b+2}", s['count'], s['wins'], s['losses'], s['winrate'], s['pf'], s['net']))
        print_table(headers, rows)

    # ========================================================
    # E. EMA50 DISTANCE ANALYSIS
    # ========================================================
    print_header("E. EMA50 DISTANCE ANALYSIS")
    trades_with_ema = [t for t in trades if t.get('ema50_dist') is not None]
    print(f"  Trades with EMA data: {len(trades_with_ema)} / {len(trades)}")

    if trades_with_ema:
        wins_ema = [t['ema50_dist'] for t in trades_with_ema if t['result'] == 'WIN']
        losses_ema = [t['ema50_dist'] for t in trades_with_ema if t['result'] == 'LOSS']
        print(f"  Winners avg EMA dist: {sum(wins_ema)/len(wins_ema):.1f} pips")
        print(f"  Losers avg EMA dist:  {sum(losses_ema)/len(losses_ema):.1f} pips")

        # EMA distance buckets
        ema_buckets = [
            ('<10', 0, 10), ('10-20', 10, 20), ('20-30', 20, 30),
            ('30-40', 30, 40), ('40-50', 40, 50), ('50-75', 50, 75),
            ('75-100', 75, 100), ('100-150', 100, 150), ('>150', 150, 9999)
        ]
        headers = ['EMA Dist', 'Count', 'Wins', 'Losses', 'WR%', 'PF', 'Net $']
        rows = []
        for label, lo, hi in ema_buckets:
            subset = [t for t in trades_with_ema if lo <= t['ema50_dist'] < hi]
            s = calc_stats(subset)
            if s['count'] > 0:
                rows.append((label, s['count'], s['wins'], s['losses'], s['winrate'], s['pf'], s['net']))
        print_table(headers, rows)

        # Find optimal max distance
        print("\n  Cumulative performance by max EMA distance threshold:")
        headers = ['MaxDist', 'Count', 'WR%', 'PF', 'Net $', 'Excluded', 'Excl Net']
        rows = []
        for threshold in [15, 20, 25, 30, 40, 50, 60, 75, 100, 150, 200, 300]:
            included = [t for t in trades_with_ema if t['ema50_dist'] <= threshold]
            excluded = [t for t in trades_with_ema if t['ema50_dist'] > threshold]
            si = calc_stats(included)
            se = calc_stats(excluded)
            rows.append((threshold, si['count'], si['winrate'], si['pf'], si['net'],
                        se['count'], se['net']))
        print_table(headers, rows)

    # ========================================================
    # F. SL DISTANCE ANALYSIS
    # ========================================================
    print_header("F. SL DISTANCE ANALYSIS")
    sl_buckets_def = [
        ('<10', 0, 10), ('10-15', 10, 15), ('15-20', 15, 20),
        ('20-25', 20, 25), ('25-30', 25, 30), ('30-40', 30, 40),
        ('40-50', 40, 50), ('>50', 50, 999)
    ]
    headers = ['SL Range', 'Count', 'Wins', 'Losses', 'WR%', 'PF', 'Net $', 'Avg SL']
    rows = []
    for label, lo, hi in sl_buckets_def:
        subset = [t for t in trades if lo <= t['sl_dist_pips'] < hi]
        s = calc_stats(subset)
        avg_sl = sum(t['sl_dist_pips'] for t in subset) / len(subset) if subset else 0
        if s['count'] > 0:
            rows.append((label, s['count'], s['wins'], s['losses'], s['winrate'], s['pf'], s['net'], round(avg_sl, 1)))
    print_table(headers, rows)

    # MinSL / MaxSL analysis
    print("\n  Performance by MinSL threshold (trades with SL >= X):")
    headers = ['MinSL', 'Count', 'WR%', 'PF', 'Net $']
    rows = []
    for min_sl in [5, 8, 10, 12, 15, 17, 20, 22, 25, 30]:
        subset = [t for t in trades if t['sl_dist_pips'] >= min_sl]
        s = calc_stats(subset)
        rows.append((min_sl, s['count'], s['winrate'], s['pf'], s['net']))
    print_table(headers, rows)

    print("\n  Performance by MaxSL threshold (trades with SL <= X):")
    headers = ['MaxSL', 'Count', 'WR%', 'PF', 'Net $']
    rows = []
    for max_sl in [15, 20, 25, 30, 35, 40, 50, 60]:
        subset = [t for t in trades if t['sl_dist_pips'] <= max_sl]
        s = calc_stats(subset)
        rows.append((max_sl, s['count'], s['winrate'], s['pf'], s['net']))
    print_table(headers, rows)

    # Combined MinSL + MaxSL
    print("\n  Combined SL range performance:")
    headers = ['SL Range', 'Count', 'WR%', 'PF', 'Net $']
    rows = []
    for min_sl, max_sl in [(10, 25), (10, 30), (12, 25), (12, 30), (15, 25), (15, 30),
                            (15, 35), (17, 30), (17, 35), (20, 30), (20, 35), (20, 40)]:
        subset = [t for t in trades if min_sl <= t['sl_dist_pips'] <= max_sl]
        s = calc_stats(subset)
        rows.append((f"{min_sl}-{max_sl}", s['count'], s['winrate'], s['pf'], s['net']))
    print_table(headers, rows)

    # ========================================================
    # G. TRADE DURATION ANALYSIS
    # ========================================================
    print_header("G. TRADE DURATION ANALYSIS")
    dur_buckets = [
        ('<30m', 0, 30), ('30m-1h', 30, 60), ('1h-2h', 60, 120),
        ('2h-4h', 120, 240), ('4h-8h', 240, 480), ('8h-24h', 480, 1440),
        ('>24h', 1440, 99999)
    ]
    headers = ['Duration', 'Count', 'Wins', 'Losses', 'WR%', 'PF', 'Net $']
    rows = []
    for label, lo, hi in dur_buckets:
        subset = [t for t in trades if lo <= t['duration_min'] < hi]
        s = calc_stats(subset)
        if s['count'] > 0:
            rows.append((label, s['count'], s['wins'], s['losses'], s['winrate'], s['pf'], s['net']))
    print_table(headers, rows)

    # Wins vs losses duration
    wins = [t for t in trades if t['result'] == 'WIN']
    losses_list = [t for t in trades if t['result'] == 'LOSS']
    if wins:
        print(f"\n  Avg duration WINS:   {sum(t['duration_min'] for t in wins)/len(wins):.0f} min")
    if losses_list:
        print(f"  Avg duration LOSSES: {sum(t['duration_min'] for t in losses_list)/len(losses_list):.0f} min")

    # Short trades (<1h)
    short = [t for t in trades if t['duration_min'] < 60]
    long_t = [t for t in trades if t['duration_min'] >= 60]
    print(f"\n  Trades < 1h: {len(short)} ({calc_stats(short)['winrate']}% WR, PF={calc_stats(short)['pf']}, Net=${calc_stats(short)['net']})")
    print(f"  Trades >= 1h: {len(long_t)} ({calc_stats(long_t)['winrate']}% WR, PF={calc_stats(long_t)['pf']}, Net=${calc_stats(long_t)['net']})")

    # ========================================================
    # H. MONTHLY EQUITY CURVE
    # ========================================================
    print_header("H. MONTHLY EQUITY CURVE")
    monthly_balance = {}
    for t in trades:
        monthly_balance[t['month']] = t['balance_after']

    headers = ['Month', 'End Balance', 'Monthly P/L', 'Cumul P/L']
    rows = []
    prev_bal = INITIAL_BALANCE
    for m in sorted(monthly_balance.keys()):
        bal = monthly_balance[m]
        monthly_pl = bal - prev_bal
        cumul = bal - INITIAL_BALANCE
        rows.append((m, f"${bal:.2f}", f"${monthly_pl:+.2f}", f"${cumul:+.2f}"))
        prev_bal = bal
    print_table(headers, rows)

    # ========================================================
    # I. PLANNED RR ANALYSIS
    # ========================================================
    print_header("I. PLANNED RR ANALYSIS")
    rr_buckets = defaultdict(list)
    for t in trades:
        rr = t['planned_rr']
        if rr < 1.5:
            rr_buckets['<1.5'].append(t)
        elif rr < 2.0:
            rr_buckets['1.5-2.0'].append(t)
        elif rr < 2.5:
            rr_buckets['2.0-2.5'].append(t)
        elif rr < 3.0:
            rr_buckets['2.5-3.0'].append(t)
        else:
            rr_buckets['>=3.0'].append(t)

    headers = ['RR Range', 'Count', 'Wins', 'Losses', 'WR%', 'PF', 'Net $']
    rows = []
    for label in ['<1.5', '1.5-2.0', '2.0-2.5', '2.5-3.0', '>=3.0']:
        if label in rr_buckets:
            s = calc_stats(rr_buckets[label])
            rows.append((label, s['count'], s['wins'], s['losses'], s['winrate'], s['pf'], s['net']))
    print_table(headers, rows)

    # ========================================================
    # J. SPECIFIC RECOMMENDATIONS FOR GBPUSD
    # ========================================================
    print_header("J. SPECIFIC RECOMMENDATIONS FOR GBPUSD")
    print("\n  KEY INSIGHT: Trades < 1h are CATASTROPHIC (PF=0.19, -$11,020)")
    print("  Trades >= 1h are PROFITABLE (PF=1.27, +$5,872)")
    print("  This means the EA's edge exists but quick SL hits destroy it.")
    print("  Strategy: use SELECTIVE filters that remove the worst combos,")
    print("  NOT blanket bans that kill all volume.\n")

    # Rank individual filters by $ impact per trade removed
    print("--- INDIVIDUAL FILTER IMPACT ANALYSIS ---\n")

    # 1. Toxic hour+day combos (surgical approach - best bang for buck)
    print("  1. TOXIC HOUR+DAY COMBOS (sorted by loss/trade):")
    all_combos = []
    for h in all_hours:
        for d in day_order:
            tlist = heatmap[h][d]
            if len(tlist) >= 5:  # minimum significance
                s = calc_stats(tlist)
                loss_per_trade = s['net'] / s['count'] if s['count'] > 0 else 0
                all_combos.append((h, d, s['count'], s['winrate'], s['pf'], s['net'], loss_per_trade))
    all_combos.sort(key=lambda x: x[6])

    headers = ['Hour', 'Day', 'Count', 'WR%', 'PF', 'Net $', '$/Trade']
    rows = []
    for h, d, c, wr, pf, net, lpt in all_combos:
        marker = " <<<" if lpt < -20 else ""
        rows.append((f"{h:02d}:00", d, c, wr, pf, round(net, 0), round(lpt, 1)))
    print_table(headers, rows)

    # 2. Identify the WORST toxic day (only block if PF < 0.7)
    print("\n  2. DAY ANALYSIS - Only block days with PF < 0.70:")
    toxic_days_strict = []
    for d in day_order:
        if d in days_data:
            s = calc_stats(days_data[d])
            if s['pf'] < 0.70:
                toxic_days_strict.append((d, s['count'], s['pf'], s['net']))
                print(f"     BLOCK {d}: {s['count']} trades, PF={s['pf']}, Net=${s['net']:.0f}")

    # 3. Block only the WORST hours (PF < 0.65)
    print("\n  3. HOUR ANALYSIS - Only block hours with PF < 0.65:")
    toxic_hours_strict = []
    for h in sorted(hours_data.keys()):
        s = calc_stats(hours_data[h])
        if s['pf'] < 0.65:
            toxic_hours_strict.append((h, s['count'], s['pf'], s['net']))
            print(f"     BLOCK {h:02d}:00: {s['count']} trades, PF={s['pf']}, Net=${s['net']:.0f}")

    # 4. SL sweet spot
    print("\n  4. SL ANALYSIS - Find the sweet spot:")
    print("     Current data shows SL 20-30 pips is breakeven (PF=1.0)")
    print("     SL < 15 pips: too tight, gets stopped out")
    print("     MinSL=20 keeps 214 trades with PF=1.0 and Net=$9")

    # 5. EMA50 - only filter extreme outliers
    print("\n  5. EMA50 DISTANCE - Filter extreme outliers only:")
    for thresh in [50, 60, 75]:
        excl = [t for t in trades_with_ema if t['ema50_dist'] > thresh]
        incl = [t for t in trades_with_ema if t['ema50_dist'] <= thresh]
        se = calc_stats(excl)
        si = calc_stats(incl)
        print(f"     Max {thresh} pips: keep {si['count']} trades (PF={si['pf']}), "
              f"exclude {se['count']} (PF={se['pf']}, Net=${se['net']:.0f})")

    # 6. ATR - the data shows 18-22 pip ATR is profitable
    print("\n  6. ATR ANALYSIS - Notable zones:")
    for lo, hi in [(6, 10), (8, 12), (18, 22), (18, 26), (6, 22)]:
        subset = [t for t in trades_with_atr if lo <= t['atr'] <= hi]
        s = calc_stats(subset)
        print(f"     ATR {lo}-{hi}: {s['count']} trades, PF={s['pf']}, Net=${s['net']:.0f}")

    # ========================================================
    # K. SIMULATED COMBINED PERFORMANCE - MULTIPLE SCENARIOS
    # ========================================================
    print_header("K. SIMULATED PERFORMANCE - MULTIPLE SCENARIOS")

    orig_stats = calc_stats(trades)
    orig_dd_abs, orig_dd_pct = max_drawdown(trades)
    print(f"\n  BASELINE: {orig_stats['count']} trades | WR={orig_stats['winrate']}% | PF={orig_stats['pf']} | Net=${orig_stats['net']} | DD={orig_dd_pct}%\n")

    def simulate_scenario(name, trade_list, filter_func):
        """Apply filter and show results"""
        filtered = [t for t in trade_list if filter_func(t)]
        s = calc_stats(filtered)
        # Equity curve
        eq = INITIAL_BALANCE
        pk = INITIAL_BALANCE
        mdd = 0
        for t in filtered:
            eq += t['profit']
            if eq > pk: pk = eq
            dd = pk - eq
            if dd > mdd: mdd = dd
        mdd_pct = mdd / pk * 100 if pk > 0 else 0
        removed = len(trade_list) - len(filtered)
        return {
            'name': name, 'count': s['count'], 'removed': removed,
            'wr': s['winrate'], 'pf': s['pf'], 'net': s['net'],
            'dd': round(mdd, 0), 'dd_pct': round(mdd_pct, 1),
            'final': round(INITIAL_BALANCE + s['net'], 2)
        }

    # Build toxic combo set (combos with net < -$200 and loss/trade < -$20)
    worst_combos = set()
    for h, d, c, wr, pf, net, lpt in all_combos:
        if net < -200 and lpt < -20:
            worst_combos.add((h, d))

    very_worst_combos = set()
    for h, d, c, wr, pf, net, lpt in all_combos:
        if net < -400:
            very_worst_combos.add((h, d))

    scenarios = []

    # Scenario 1: Block Friday only
    scenarios.append(simulate_scenario(
        "S1: Block Friday",
        trades, lambda t: t['day'] != 'Friday'))

    # Scenario 2: Block Friday + Monday
    scenarios.append(simulate_scenario(
        "S2: Block Fri + Mon",
        trades, lambda t: t['day'] not in ('Friday', 'Monday')))

    # Scenario 3: Block worst combos only (net < -$400)
    scenarios.append(simulate_scenario(
        f"S3: Block {len(very_worst_combos)} worst combos",
        trades, lambda t: (t['hour'], t['day']) not in very_worst_combos))

    # Scenario 4: Block worst combos (net < -$200 & $/trade < -$20)
    scenarios.append(simulate_scenario(
        f"S4: Block {len(worst_combos)} toxic combos",
        trades, lambda t: (t['hour'], t['day']) not in worst_combos))

    # Scenario 5: MinSL 20
    scenarios.append(simulate_scenario(
        "S5: MinSL=20",
        trades, lambda t: t['sl_dist_pips'] >= 20))

    # Scenario 6: MinSL 15
    scenarios.append(simulate_scenario(
        "S6: MinSL=15",
        trades, lambda t: t['sl_dist_pips'] >= 15))

    # Scenario 7: Block 08h + 15h (worst PF hours)
    scenarios.append(simulate_scenario(
        "S7: Block 08h+15h",
        trades, lambda t: t['hour'] not in (8, 15)))

    # Scenario 8: Block 08h + 10h + 15h
    scenarios.append(simulate_scenario(
        "S8: Block 08h+10h+15h",
        trades, lambda t: t['hour'] not in (8, 10, 15)))

    # Scenario 9: EMA50 < 50
    scenarios.append(simulate_scenario(
        "S9: EMA50<50",
        trades, lambda t: t.get('ema50_dist') is None or t['ema50_dist'] <= 50))

    # Scenario 10: EMA50 < 60
    scenarios.append(simulate_scenario(
        "S10: EMA50<60",
        trades, lambda t: t.get('ema50_dist') is None or t['ema50_dist'] <= 60))

    # COMBINED SCENARIOS
    print("  --- Combined Scenarios ---\n")

    # C1: Friday + worst combos + MinSL 20
    scenarios.append(simulate_scenario(
        "C1: Fri + MinSL20",
        trades, lambda t: t['day'] != 'Friday' and t['sl_dist_pips'] >= 20))

    # C2: Friday + Monday + MinSL 20
    scenarios.append(simulate_scenario(
        "C2: Fri+Mon + MinSL20",
        trades, lambda t: t['day'] not in ('Friday', 'Monday') and t['sl_dist_pips'] >= 20))

    # C3: Friday + worst combos
    scenarios.append(simulate_scenario(
        f"C3: Fri + {len(very_worst_combos)} combos",
        trades, lambda t: t['day'] != 'Friday' and (t['hour'], t['day']) not in very_worst_combos))

    # C4: Block 08+15h + Friday + MinSL 15
    scenarios.append(simulate_scenario(
        "C4: 08h+15h + Fri + MinSL15",
        trades, lambda t: t['hour'] not in (8, 15) and t['day'] != 'Friday' and t['sl_dist_pips'] >= 15))

    # C5: Block 08+10+15h + Friday + MinSL 20
    scenarios.append(simulate_scenario(
        "C5: 08+10+15h + Fri + MinSL20",
        trades, lambda t: t['hour'] not in (8, 10, 15) and t['day'] != 'Friday' and t['sl_dist_pips'] >= 20))

    # C6: Worst combos + MinSL 20 + EMA50<50
    scenarios.append(simulate_scenario(
        f"C6: {len(worst_combos)}combos + MinSL20 + EMA<50",
        trades, lambda t: (t['hour'], t['day']) not in worst_combos
                          and t['sl_dist_pips'] >= 20
                          and (t.get('ema50_dist') is None or t['ema50_dist'] <= 50)))

    # C7: Block 08+15h + Fri + MinSL 20
    scenarios.append(simulate_scenario(
        "C7: 08+15h + Fri + MinSL20",
        trades, lambda t: t['hour'] not in (8, 15) and t['day'] != 'Friday' and t['sl_dist_pips'] >= 20))

    # C8: Block 08+15h + Fri + Mon + MinSL 20
    scenarios.append(simulate_scenario(
        "C8: 08+15h + Fri+Mon + MinSL20",
        trades, lambda t: t['hour'] not in (8, 15) and t['day'] not in ('Friday', 'Monday')
                          and t['sl_dist_pips'] >= 20))

    # C9: Block 08+10+15h + Fri + MinSL 15 + EMA<60
    scenarios.append(simulate_scenario(
        "C9: 08+10+15h+Fri+MinSL15+EMA<60",
        trades, lambda t: t['hour'] not in (8, 10, 15) and t['day'] != 'Friday'
                          and t['sl_dist_pips'] >= 15
                          and (t.get('ema50_dist') is None or t['ema50_dist'] <= 60)))

    # C10: Worst combos + MinSL 15 + EMA<60
    scenarios.append(simulate_scenario(
        f"C10: {len(worst_combos)}combos+MinSL15+EMA<60",
        trades, lambda t: (t['hour'], t['day']) not in worst_combos
                          and t['sl_dist_pips'] >= 15
                          and (t.get('ema50_dist') is None or t['ema50_dist'] <= 60)))

    # C11: Block worst hours + Fri + worst combos + MinSL 20
    scenarios.append(simulate_scenario(
        f"C11: 08+15h+Fri+{len(very_worst_combos)}combos+MinSL20",
        trades, lambda t: t['hour'] not in (8, 15) and t['day'] != 'Friday'
                          and (t['hour'], t['day']) not in very_worst_combos
                          and t['sl_dist_pips'] >= 20))

    # C12: Conservative - only block truly horrible combos + MinSL 20
    scenarios.append(simulate_scenario(
        f"C12: {len(very_worst_combos)}combos + MinSL20",
        trades, lambda t: (t['hour'], t['day']) not in very_worst_combos
                          and t['sl_dist_pips'] >= 20))

    # C13: Aggressive - Block 08+10+15 + Fri+Mon + MinSL20 + EMA<50
    scenarios.append(simulate_scenario(
        "C13: 08+10+15h+Fri+Mon+SL20+EMA<50",
        trades, lambda t: t['hour'] not in (8, 10, 15)
                          and t['day'] not in ('Friday', 'Monday')
                          and t['sl_dist_pips'] >= 20
                          and (t.get('ema50_dist') is None or t['ema50_dist'] <= 50)))

    # Print all scenarios sorted by PF
    scenarios.sort(key=lambda x: -x['pf'])
    headers = ['Scenario', 'Trades', 'Removed', 'WR%', 'PF', 'Net $', 'DD $', 'DD%', 'Final $']
    rows = []
    for sc in scenarios:
        rows.append((sc['name'], sc['count'], sc['removed'], sc['wr'], sc['pf'],
                     round(sc['net'], 0), sc['dd'], sc['dd_pct'], sc['final']))
    print_table(headers, rows)

    # Find best scenario targeting PF > 1.5 with enough trades
    print_header("K2. BEST SCENARIOS ANALYSIS")
    viable = [s for s in scenarios if s['pf'] >= 1.2 and s['count'] >= 50]
    if viable:
        best = max(viable, key=lambda x: x['pf'])
        print(f"\n  BEST VIABLE SCENARIO (PF >= 1.2, trades >= 50):")
        print(f"    {best['name']}")
        print(f"    Trades: {best['count']} | WR: {best['wr']}% | PF: {best['pf']}")
        print(f"    Net: ${best['net']:.0f} | DD: ${best['dd']} ({best['dd_pct']}%)")
        print(f"    Final balance: ${best['final']}")

    # Also show best for PF > 1.0
    viable10 = [s for s in scenarios if s['pf'] >= 1.0 and s['count'] >= 100]
    if viable10:
        best10 = max(viable10, key=lambda x: x['net'])
        print(f"\n  BEST NET PROFIT SCENARIO (PF >= 1.0, trades >= 100):")
        print(f"    {best10['name']}")
        print(f"    Trades: {best10['count']} | WR: {best10['wr']}% | PF: {best10['pf']}")
        print(f"    Net: ${best10['net']:.0f} | DD: ${best10['dd']} ({best10['dd_pct']}%)")

    # ========================================================
    # PROGRESSIVE ANALYSIS OF BEST SCENARIO
    # ========================================================
    print_header("K3. PROGRESSIVE FILTER BUILD-UP (Best Scenario)")

    # Build up filters one by one from the best combined scenario
    steps = [
        ("Baseline (all trades)", trades),
    ]

    current = list(trades)

    # Step 1: Block Friday
    current = [t for t in current if t['day'] != 'Friday']
    steps.append(("+ Block Friday", list(current)))

    # Step 2: Block hour 08
    current = [t for t in current if t['hour'] != 8]
    steps.append(("+ Block 08:00", list(current)))

    # Step 3: Block hour 15
    current = [t for t in current if t['hour'] != 15]
    steps.append(("+ Block 15:00", list(current)))

    # Step 4: Block hour 10
    current = [t for t in current if t['hour'] != 10]
    steps.append(("+ Block 10:00", list(current)))

    # Step 5: MinSL 15
    current = [t for t in current if t['sl_dist_pips'] >= 15]
    steps.append(("+ MinSL >= 15", list(current)))

    # Step 6: MinSL 20
    current_20 = [t for t in current if t['sl_dist_pips'] >= 20]
    steps.append(("+ MinSL >= 20 (alt)", list(current_20)))

    # Step 7: EMA50 < 60
    current = [t for t in current if t.get('ema50_dist') is None or t['ema50_dist'] <= 60]
    steps.append(("+ EMA50 < 60", list(current)))

    # Step 8: Block worst combos on remaining
    current_vc = [t for t in current if (t['hour'], t['day']) not in very_worst_combos]
    steps.append(("+ Block worst combos", list(current_vc)))

    print(f"\n  {'Step':<30} {'Trades':>7} {'WR%':>6} {'PF':>6} {'Net $':>10} {'DD%':>6}")
    print("  " + "-" * 67)
    for name, tlist in steps:
        s = calc_stats(tlist)
        eq = INITIAL_BALANCE
        pk = INITIAL_BALANCE
        mdd = 0
        for t in tlist:
            eq += t['profit']
            if eq > pk: pk = eq
            dd = pk - eq
            if dd > mdd: mdd = dd
        dd_pct = mdd / pk * 100 if pk > 0 else 0
        print(f"  {name:<30} {s['count']:>7} {s['winrate']:>5.1f}% {s['pf']:>5.2f} {s['net']:>9.0f}$ {dd_pct:>5.1f}%")

    # ========================================================
    # WORST COMBOS DETAIL
    # ========================================================
    print_header("K4. TOXIC COMBOS TO BLOCK (Detail)")
    print(f"\n  Very worst combos (net < -$400):")
    for h, d, c, wr, pf, net, lpt in all_combos:
        if (h, d) in very_worst_combos:
            print(f"    {h:02d}:00 {d}: {c} trades, WR={wr}%, PF={pf}, Net=${net:.0f}, $/trade={lpt:.1f}")

    print(f"\n  Worst combos (net < -$200 & $/trade < -$20):")
    for h, d, c, wr, pf, net, lpt in all_combos:
        if (h, d) in worst_combos and (h, d) not in very_worst_combos:
            print(f"    {h:02d}:00 {d}: {c} trades, WR={wr}%, PF={pf}, Net=${net:.0f}, $/trade={lpt:.1f}")

    # ========================================================
    # FINAL SUMMARY
    # ========================================================
    print_header("FINAL SUMMARY: GBPUSD OPTIMIZATION RECOMMENDATIONS")

    # Determine best realistic scenario
    print(f"""
  ORIGINAL:  {orig_stats['count']} trades | WR={orig_stats['winrate']}% | PF={orig_stats['pf']} | Net=${orig_stats['net']} | DD={orig_dd_pct}%

  ===== RECOMMENDED EA PARAMETERS FOR GBPUSD =====

  TIER 1 - CONSERVATIVE (higher trade count, moderate improvement):
    - Block Friday:          YES (saves ~$2,600, 137 trades)
    - Block hours 08+15:     YES (saves ~$3,825, removes ~192 trades)
    - MinSL:                 15 pips (filters tight SLs that get clipped)
    - All other params:      Keep defaults

  TIER 2 - MODERATE (best balance of PF and volume):
    - Block Friday:          YES
    - Block hours 08+10+15:  YES
    - MinSL:                 15 pips
    - MaxEMA50Dist:          60 pips (removes far-from-mean entries)

  TIER 3 - AGGRESSIVE (highest PF, fewer trades):
    - Block Friday + Monday: YES
    - Block hours 08+10+15:  YES
    - MinSL:                 20 pips
    - MaxEMA50Dist:          50 pips

  ===== KEY DIFFERENCES FROM EURUSD =====
    - EURUSD toxic day: Friday only. GBPUSD: Friday + Monday
    - EURUSD toxic hours: 14h. GBPUSD: 08h, 10h, 15h
    - EURUSD ATR sweet spot: 9-19 pips. GBPUSD: No clear ATR edge (all bad)
    - EURUSD MinSL: 15. GBPUSD: 15-20 (GBP needs wider stops)
    - Duration insight: GBPUSD trades < 1h lose $11K (PF=0.19!!)
      This is the BIGGEST single factor. Consider a min hold time.

  ===== ROOT CAUSE ANALYSIS =====
    - GBPUSD is more volatile and spiky than EURUSD
    - Tight SLs (< 15 pips) get hunted by GBPUSD wicks
    - Morning session (08-10h) has false breakouts on London open
    - Friday reversals are brutal on GBP pairs
    - The EA's edge exists (trades >= 1h: PF=1.27, +$5,872)
      but gets destroyed by quick stop-outs (-$11,020)
""")


if __name__ == '__main__':
    main()
