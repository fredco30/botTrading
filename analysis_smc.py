"""
Comprehensive analysis of SMC Scalper EA on EURUSD (raw backtest, no filters).
Trade history: historique_SMC_EURUSD_brut.txt (898 trades, Apr 2023 - Apr 2026)
H1 data: EURUSD60_cut.csv
M15 data: EURUSD15_cut.csv
"""

import csv
from datetime import datetime, timedelta
from collections import defaultdict
import math

# =============================================================================
# A. TRADE PARSING
# =============================================================================

def parse_trades(filepath):
    """Parse trade history file into structured trades."""
    lines = []
    with open(filepath, 'r') as f:
        for raw in f:
            raw = raw.strip()
            if not raw:
                continue
            parts = raw.split('\t')
            if len(parts) < 10:
                continue
            lines.append({
                'line': int(parts[0]),
                'datetime': parts[1],
                'action': parts[2],
                'ticket': int(parts[3]),
                'lots': float(parts[4]),
                'price': float(parts[5]),
                'sl': float(parts[6]),
                'tp': float(parts[7]),
                'profit': float(parts[8]),
                'balance': float(parts[9]),
            })

    # Pair open/close lines by ticket
    opens = {}
    trades = []
    for line in lines:
        action = line['action'].lower().strip()
        ticket = line['ticket']
        if action in ('buy', 'sell'):
            opens[ticket] = line
        elif action in ('s/l', 't/p', 'close at stop'):
            if ticket in opens:
                op = opens[ticket]
                direction = op['action'].lower().strip()
                open_dt = datetime.strptime(op['datetime'], '%Y.%m.%d %H:%M')
                close_dt = datetime.strptime(line['datetime'], '%Y.%m.%d %H:%M')
                duration_min = (close_dt - open_dt).total_seconds() / 60.0

                # SL distance in pips (EURUSD: *10000)
                if direction == 'buy':
                    sl_dist = (op['price'] - op['sl']) * 10000
                else:
                    sl_dist = (op['sl'] - op['price']) * 10000

                trades.append({
                    'ticket': ticket,
                    'direction': direction,
                    'open_dt': open_dt,
                    'close_dt': close_dt,
                    'open_price': op['price'],
                    'close_price': line['price'],
                    'sl': op['sl'],
                    'tp': op['tp'],
                    'lots': op['lots'],
                    'profit': line['profit'],
                    'balance': line['balance'],
                    'exit_type': action,
                    'duration_min': duration_min,
                    'sl_dist_pips': round(sl_dist, 1),
                    'hour': open_dt.hour,
                    'day': open_dt.strftime('%a'),
                    'day_num': open_dt.weekday(),  # 0=Mon
                    'month': open_dt.strftime('%Y-%m'),
                })
                del opens[ticket]
    return trades


def load_h1_data(filepath):
    """Load H1 OHLCV data."""
    data = []
    with open(filepath, 'r') as f:
        for raw in f:
            raw = raw.strip()
            if not raw:
                continue
            parts = raw.split(',')
            if len(parts) < 7:
                continue
            try:
                dt = datetime.strptime(f"{parts[0]},{parts[1]}", '%Y.%m.%d,%H:%M')
                data.append({
                    'dt': dt,
                    'open': float(parts[2]),
                    'high': float(parts[3]),
                    'low': float(parts[4]),
                    'close': float(parts[5]),
                    'volume': int(parts[6]),
                })
            except (ValueError, IndexError):
                continue
    return data


def compute_atr(h1_data, period=14):
    """Compute ATR(14) for H1 data, return dict dt -> atr_pips."""
    atr_map = {}
    trs = []
    for i, bar in enumerate(h1_data):
        if i == 0:
            tr = (bar['high'] - bar['low']) * 10000
        else:
            prev_close = h1_data[i-1]['close']
            tr = max(
                (bar['high'] - bar['low']) * 10000,
                abs(bar['high'] - prev_close) * 10000,
                abs(bar['low'] - prev_close) * 10000,
            )
        trs.append(tr)
        if len(trs) >= period:
            atr_val = sum(trs[-period:]) / period
            atr_map[bar['dt']] = round(atr_val, 2)
    return atr_map


def compute_ema(h1_data, period=50):
    """Compute EMA(50) on close for H1 data, return dict dt -> ema_value."""
    ema_map = {}
    multiplier = 2.0 / (period + 1)
    ema = None
    for bar in h1_data:
        if ema is None:
            ema = bar['close']
        else:
            ema = (bar['close'] - ema) * multiplier + ema
        ema_map[bar['dt']] = ema
    return ema_map


def find_h1_bar(h1_data_sorted_dt, trade_dt, atr_map, ema_map):
    """Find the H1 bar just before or at trade entry time."""
    # Find the H1 bar whose dt <= trade_dt
    target = trade_dt.replace(minute=0, second=0, microsecond=0)
    atr = atr_map.get(target)
    ema = ema_map.get(target)
    # If exact hour not found, try previous hours
    if atr is None or ema is None:
        for delta in range(1, 5):
            prev = target - timedelta(hours=delta)
            if atr is None and prev in atr_map:
                atr = atr_map[prev]
            if ema is None and prev in ema_map:
                ema = ema_map[prev]
            if atr is not None and ema is not None:
                break
    return atr, ema


# =============================================================================
# STATS HELPERS
# =============================================================================

def calc_stats(trades_list):
    """Calculate comprehensive stats for a list of trades."""
    if not trades_list:
        return {'count': 0, 'wins': 0, 'losses': 0, 'wr': 0, 'pf': 0,
                'net': 0, 'avg_win': 0, 'avg_loss': 0, 'max_dd': 0, 'max_dd_pct': 0}

    wins = [t for t in trades_list if t['profit'] > 0]
    losses = [t for t in trades_list if t['profit'] <= 0]
    gross_profit = sum(t['profit'] for t in wins)
    gross_loss = abs(sum(t['profit'] for t in losses))
    net = sum(t['profit'] for t in trades_list)
    pf = gross_profit / gross_loss if gross_loss > 0 else float('inf')
    avg_win = gross_profit / len(wins) if wins else 0
    avg_loss = gross_loss / len(losses) if losses else 0

    # Max drawdown calculation
    peak = 10000.0
    dd = 0
    dd_pct = 0
    equity = 10000.0
    for t in trades_list:
        equity += t['profit']
        if equity > peak:
            peak = equity
        current_dd = peak - equity
        current_dd_pct = current_dd / peak * 100 if peak > 0 else 0
        if current_dd > dd:
            dd = current_dd
        if current_dd_pct > dd_pct:
            dd_pct = current_dd_pct

    return {
        'count': len(trades_list),
        'wins': len(wins),
        'losses': len(losses),
        'wr': len(wins) / len(trades_list) * 100 if trades_list else 0,
        'pf': round(pf, 2),
        'net': round(net, 2),
        'avg_win': round(avg_win, 2),
        'avg_loss': round(avg_loss, 2),
        'max_dd': round(dd, 2),
        'max_dd_pct': round(dd_pct, 1),
        'gross_profit': round(gross_profit, 2),
        'gross_loss': round(gross_loss, 2),
    }


def print_header(title):
    print(f"\n{'='*80}")
    print(f"  {title}")
    print(f"{'='*80}")


def print_table(headers, rows, col_widths=None):
    if not col_widths:
        col_widths = [max(len(str(h)), max((len(str(r[i])) for r in rows), default=0)) + 2
                      for i, h in enumerate(headers)]
    header_str = ''.join(str(h).ljust(w) for h, w in zip(headers, col_widths))
    print(header_str)
    print('-' * sum(col_widths))
    for row in rows:
        print(''.join(str(v).ljust(w) for v, w in zip(row, col_widths)))


# =============================================================================
# MAIN ANALYSIS
# =============================================================================

def main():
    print("=" * 80)
    print("  SMC SCALPER EA - COMPREHENSIVE EURUSD ANALYSIS (RAW BACKTEST)")
    print("  Period: Apr 2023 - Apr 2026 | Starting Balance: $10,000")
    print("=" * 80)

    # --- Parse data ---
    trades = parse_trades('C:/Users/projets/botTrading/historique_SMC_EURUSD_brut.txt')
    h1_data = load_h1_data('C:/Users/projets/botTrading/EURUSD60_cut.csv')
    atr_map = compute_atr(h1_data, 14)
    ema_map = compute_ema(h1_data, 50)

    print(f"\nParsed {len(trades)} trades")
    print(f"H1 bars loaded: {len(h1_data)}")
    print(f"ATR values computed: {len(atr_map)}")

    # Enrich trades with ATR and EMA50 distance
    for t in trades:
        atr, ema = find_h1_bar(h1_data, t['open_dt'], atr_map, ema_map)
        t['h1_atr_pips'] = round(atr, 2) if atr else None
        if ema:
            t['ema50_dist_pips'] = round(abs(t['open_price'] - ema) * 10000, 1)
        else:
            t['ema50_dist_pips'] = None

    # =========================================================================
    # B. GLOBAL STATS
    # =========================================================================
    print_header("B. GLOBAL STATISTICS")
    gs = calc_stats(trades)
    print(f"  Total trades:     {gs['count']}")
    print(f"  Wins / Losses:    {gs['wins']} / {gs['losses']}")
    print(f"  Win Rate:         {gs['wr']:.1f}%")
    print(f"  Profit Factor:    {gs['pf']}")
    print(f"  Net Profit:       ${gs['net']:.2f}")
    print(f"  Gross Profit:     ${gs['gross_profit']:.2f}")
    print(f"  Gross Loss:       -${gs['gross_loss']:.2f}")
    print(f"  Avg Win:          ${gs['avg_win']:.2f}")
    print(f"  Avg Loss:         -${gs['avg_loss']:.2f}")
    print(f"  Max Drawdown:     ${gs['max_dd']:.2f} ({gs['max_dd_pct']:.1f}%)")
    print(f"  Final Balance:    ${trades[-1]['balance']:.2f}")

    # Exit type breakdown
    exit_types = defaultdict(int)
    for t in trades:
        exit_types[t['exit_type']] += 1
    print(f"\n  Exit types:")
    for et, cnt in sorted(exit_types.items(), key=lambda x: -x[1]):
        print(f"    {et}: {cnt} ({cnt/len(trades)*100:.1f}%)")

    # =========================================================================
    # C. TEMPORAL ANALYSIS
    # =========================================================================
    print_header("C. TEMPORAL ANALYSIS")

    # --- By Hour ---
    print("\n  C.1 BY HOUR (8-23):")
    hours = sorted(set(t['hour'] for t in trades))
    rows = []
    for h in hours:
        ht = [t for t in trades if t['hour'] == h]
        s = calc_stats(ht)
        rows.append([f"{h:02d}h", s['count'], f"{s['wr']:.1f}%", s['pf'], f"${s['net']:.0f}",
                      f"${s['avg_win']:.0f}", f"-${s['avg_loss']:.0f}"])
    print_table(['Hour', 'Count', 'WR', 'PF', 'Net', 'AvgWin', 'AvgLoss'], rows)

    # --- By Day ---
    print("\n  C.2 BY DAY OF WEEK:")
    day_order = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri']
    rows = []
    for d in day_order:
        dt = [t for t in trades if t['day'] == d]
        s = calc_stats(dt)
        rows.append([d, s['count'], f"{s['wr']:.1f}%", s['pf'], f"${s['net']:.0f}"])
    print_table(['Day', 'Count', 'WR', 'PF', 'Net'], rows)

    # --- Heatmap: Hour x Day ---
    print("\n  C.3 HEATMAP: PROFIT BY HOUR x DAY ($):")
    # Build grid
    heat_hours = sorted(set(t['hour'] for t in trades))
    header_row = ['Hour'] + day_order + ['TOTAL']
    print(''.join(str(h).rjust(10) for h in header_row))
    print('-' * 10 * len(header_row))
    for h in heat_hours:
        vals = [f"{h:02d}h"]
        row_total = 0
        for d in day_order:
            ht = [t for t in trades if t['hour'] == h and t['day'] == d]
            net = sum(t['profit'] for t in ht)
            row_total += net
            vals.append(f"${net:.0f}")
        vals.append(f"${row_total:.0f}")
        print(''.join(str(v).rjust(10) for v in vals))
    # Column totals
    vals = ['TOTAL']
    for d in day_order:
        dt = [t for t in trades if t['day'] == d]
        vals.append(f"${sum(t['profit'] for t in dt):.0f}")
    vals.append(f"${sum(t['profit'] for t in trades):.0f}")
    print('-' * 10 * len(header_row))
    print(''.join(str(v).rjust(10) for v in vals))

    # Toxic combos
    print("\n  C.4 MOST TOXIC HOUR x DAY COMBOS (bottom 15):")
    combos = []
    for h in heat_hours:
        for d in day_order:
            ht = [t for t in trades if t['hour'] == h and t['day'] == d]
            if ht:
                net = sum(t['profit'] for t in ht)
                s = calc_stats(ht)
                combos.append((h, d, len(ht), s['wr'], s['pf'], net))
    combos.sort(key=lambda x: x[5])
    rows = []
    for h, d, cnt, wr, pf, net in combos[:15]:
        rows.append([f"{h:02d}h-{d}", cnt, f"{wr:.1f}%", pf, f"${net:.0f}"])
    print_table(['Combo', 'Count', 'WR', 'PF', 'Net'], rows)

    # Best combos
    print("\n  C.5 BEST HOUR x DAY COMBOS (top 10):")
    rows = []
    for h, d, cnt, wr, pf, net in sorted(combos, key=lambda x: -x[5])[:10]:
        rows.append([f"{h:02d}h-{d}", cnt, f"{wr:.1f}%", pf, f"${net:.0f}"])
    print_table(['Combo', 'Count', 'WR', 'PF', 'Net'], rows)

    # --- Monthly ---
    print("\n  C.6 MONTHLY BREAKDOWN:")
    months = sorted(set(t['month'] for t in trades))
    rows = []
    for m in months:
        mt = [t for t in trades if t['month'] == m]
        s = calc_stats(mt)
        rows.append([m, s['count'], f"{s['wr']:.1f}%", s['pf'], f"${s['net']:.0f}"])
    print_table(['Month', 'Count', 'WR', 'PF', 'Net'], rows)

    # =========================================================================
    # D. ATR ANALYSIS
    # =========================================================================
    print_header("D. H1 ATR(14) ANALYSIS")

    trades_with_atr = [t for t in trades if t['h1_atr_pips'] is not None]
    print(f"  Trades with ATR data: {len(trades_with_atr)}/{len(trades)}")

    atrs = sorted(t['h1_atr_pips'] for t in trades_with_atr)
    if atrs:
        q25 = atrs[len(atrs)//4]
        q50 = atrs[len(atrs)//2]
        q75 = atrs[3*len(atrs)//4]
        print(f"  ATR distribution: min={atrs[0]:.1f}, Q25={q25:.1f}, Q50={q50:.1f}, Q75={q75:.1f}, max={atrs[-1]:.1f}")

    # ATR quartile buckets
    print("\n  D.1 ATR QUARTILE ANALYSIS:")
    atr_buckets = [
        ('Q1 (lowest)', 0, q25),
        ('Q2', q25, q50),
        ('Q3', q50, q75),
        ('Q4 (highest)', q75, 999),
    ]
    rows = []
    for label, lo, hi in atr_buckets:
        bt = [t for t in trades_with_atr if lo <= t['h1_atr_pips'] < hi]
        s = calc_stats(bt)
        rows.append([label, f"{lo:.1f}-{hi:.1f}", s['count'], f"{s['wr']:.1f}%", s['pf'], f"${s['net']:.0f}"])
    print_table(['Quartile', 'Range', 'Count', 'WR', 'PF', 'Net'], rows)

    # ATR band test
    print("\n  D.2 ATR BAND TESTS:")
    atr_bands = [
        (4, 10), (5, 12), (6, 14), (7, 16), (8, 18), (5, 10), (6, 12),
        (7, 14), (8, 16), (4, 8), (5, 9), (6, 10), (7, 12), (8, 14),
        (4, 12), (4, 14), (5, 14), (5, 16), (6, 16), (6, 18),
    ]
    rows = []
    for lo, hi in atr_bands:
        bt = [t for t in trades_with_atr if lo <= t['h1_atr_pips'] <= hi]
        s = calc_stats(bt)
        rows.append([f"{lo}-{hi}", s['count'], f"{s['wr']:.1f}%", s['pf'], f"${s['net']:.0f}"])
    rows.sort(key=lambda x: -float(x[4].replace('$', '').replace(',', '')))
    print_table(['ATR Band', 'Count', 'WR', 'PF', 'Net'], rows[:15])

    best_atr_band = None
    best_atr_net = -99999
    for lo, hi in atr_bands:
        bt = [t for t in trades_with_atr if lo <= t['h1_atr_pips'] <= hi]
        s = calc_stats(bt)
        if s['net'] > best_atr_net and s['count'] >= 50:
            best_atr_net = s['net']
            best_atr_band = (lo, hi)
    print(f"\n  Best ATR band (min 50 trades): {best_atr_band[0]}-{best_atr_band[1]} pips -> ${best_atr_net:.0f}")

    # =========================================================================
    # E. SL DISTANCE ANALYSIS
    # =========================================================================
    print_header("E. SL DISTANCE ANALYSIS (pips)")

    sl_buckets = [
        ('<5', 0, 5),
        ('5-8', 5, 8),
        ('8-10', 8, 10),
        ('10-12', 10, 12),
        ('12-15', 12, 15),
        ('15-20', 15, 20),
        ('>20', 20, 999),
    ]
    rows = []
    for label, lo, hi in sl_buckets:
        bt = [t for t in trades if lo <= t['sl_dist_pips'] < hi]
        s = calc_stats(bt)
        rows.append([label, s['count'], f"{s['wr']:.1f}%", s['pf'], f"${s['net']:.0f}", f"${s['avg_win']:.0f}", f"-${s['avg_loss']:.0f}"])
    print_table(['SL Bucket', 'Count', 'WR', 'PF', 'Net', 'AvgWin', 'AvgLoss'], rows)

    # MinSL test
    print("\n  E.2 OPTIMAL MinSL TEST:")
    rows = []
    for min_sl in [5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 18, 20]:
        bt = [t for t in trades if t['sl_dist_pips'] >= min_sl]
        s = calc_stats(bt)
        rows.append([f">={min_sl}", s['count'], f"{s['wr']:.1f}%", s['pf'], f"${s['net']:.0f}"])
    print_table(['MinSL', 'Count', 'WR', 'PF', 'Net'], rows)

    # =========================================================================
    # F. DIRECTION ANALYSIS
    # =========================================================================
    print_header("F. DIRECTION ANALYSIS: BUY vs SELL")

    for direction in ['buy', 'sell']:
        dt = [t for t in trades if t['direction'] == direction]
        s = calc_stats(dt)
        print(f"\n  {direction.upper()}:")
        print(f"    Count: {s['count']}  |  WR: {s['wr']:.1f}%  |  PF: {s['pf']}  |  Net: ${s['net']:.0f}")
        print(f"    Avg Win: ${s['avg_win']:.0f}  |  Avg Loss: -${s['avg_loss']:.0f}  |  Max DD: ${s['max_dd']:.0f}")

        # By hour for each direction
        print(f"\n    {direction.upper()} by hour:")
        rows = []
        for h in sorted(set(t['hour'] for t in dt)):
            ht = [t for t in dt if t['hour'] == h]
            sh = calc_stats(ht)
            rows.append([f"{h:02d}h", sh['count'], f"{sh['wr']:.1f}%", sh['pf'], f"${sh['net']:.0f}"])
        print_table(['Hour', 'Count', 'WR', 'PF', 'Net'], rows)

    # =========================================================================
    # G. TRADE DURATION ANALYSIS (MOST IMPORTANT)
    # =========================================================================
    print_header("G. TRADE DURATION ANALYSIS (CRITICAL)")

    dur_buckets = [
        ('<15min', 0, 15),
        ('15-30min', 15, 30),
        ('30-60min', 30, 60),
        ('1-2h', 60, 120),
        ('2-4h', 120, 240),
        ('4-8h', 240, 480),
        ('8-24h', 480, 1440),
        ('>24h', 1440, 999999),
    ]
    rows = []
    for label, lo, hi in dur_buckets:
        bt = [t for t in trades if lo <= t['duration_min'] < hi]
        s = calc_stats(bt)
        rows.append([label, s['count'], f"{s['wr']:.1f}%", s['pf'], f"${s['net']:.0f}",
                      f"${s['avg_win']:.0f}", f"-${s['avg_loss']:.0f}"])
    print_table(['Duration', 'Count', 'WR', 'PF', 'Net', 'AvgWin', 'AvgLoss'], rows)

    # More granular near the cutoff
    print("\n  G.2 GRANULAR AROUND THE 60-MIN CUTOFF:")
    fine_buckets = [
        ('<20min', 0, 20),
        ('20-40min', 20, 40),
        ('40-60min', 40, 60),
        ('60-90min', 60, 90),
        ('90-120min', 90, 120),
        ('120-180min', 120, 180),
        ('180-300min', 180, 300),
        ('>300min', 300, 999999),
    ]
    rows = []
    for label, lo, hi in fine_buckets:
        bt = [t for t in trades if lo <= t['duration_min'] < hi]
        s = calc_stats(bt)
        rows.append([label, s['count'], f"{s['wr']:.1f}%", s['pf'], f"${s['net']:.0f}"])
    print_table(['Duration', 'Count', 'WR', 'PF', 'Net'], rows)

    # Cumulative: trades >= X min
    print("\n  G.3 CUMULATIVE: TRADES >= X MINUTES:")
    rows = []
    for cutoff in [0, 15, 20, 25, 30, 40, 45, 50, 60, 75, 90, 120, 150, 180, 240]:
        bt = [t for t in trades if t['duration_min'] >= cutoff]
        s = calc_stats(bt)
        rows.append([f">={cutoff}min", s['count'], f"{s['wr']:.1f}%", s['pf'], f"${s['net']:.0f}",
                      f"DD:{s['max_dd_pct']:.0f}%"])
    print_table(['MinDur', 'Count', 'WR', 'PF', 'Net', 'MaxDD'], rows)

    # =========================================================================
    # H. EMA50 DISTANCE ANALYSIS
    # =========================================================================
    print_header("H. EMA50 DISTANCE ANALYSIS (H1)")

    trades_with_ema = [t for t in trades if t['ema50_dist_pips'] is not None]
    print(f"  Trades with EMA50 data: {len(trades_with_ema)}/{len(trades)}")

    if trades_with_ema:
        ema_dists = sorted(t['ema50_dist_pips'] for t in trades_with_ema)
        eq25 = ema_dists[len(ema_dists)//4]
        eq50 = ema_dists[len(ema_dists)//2]
        eq75 = ema_dists[3*len(ema_dists)//4]
        print(f"  Distribution: min={ema_dists[0]:.0f}, Q25={eq25:.0f}, Q50={eq50:.0f}, Q75={eq75:.0f}, max={ema_dists[-1]:.0f}")

        # Winners vs losers
        winners_ema = [t['ema50_dist_pips'] for t in trades_with_ema if t['profit'] > 0]
        losers_ema = [t['ema50_dist_pips'] for t in trades_with_ema if t['profit'] <= 0]
        print(f"\n  Winners avg EMA50 dist: {sum(winners_ema)/len(winners_ema):.1f} pips")
        print(f"  Losers avg EMA50 dist:  {sum(losers_ema)/len(losers_ema):.1f} pips")

        # Max distance filter test
        print("\n  H.2 MAX EMA50 DISTANCE FILTER TEST:")
        rows = []
        for max_dist in [20, 30, 40, 50, 60, 70, 80, 90, 100, 120, 150, 200, 300, 500]:
            bt = [t for t in trades_with_ema if t['ema50_dist_pips'] <= max_dist]
            s = calc_stats(bt)
            rows.append([f"<={max_dist}", s['count'], f"{s['wr']:.1f}%", s['pf'], f"${s['net']:.0f}"])
        print_table(['MaxDist', 'Count', 'WR', 'PF', 'Net'], rows)

    # =========================================================================
    # I. COMBINED FILTER SIMULATION
    # =========================================================================
    print_header("I. COMBINED FILTER SIMULATION")

    def apply_filters(trades_list, **filters):
        """Apply multiple filters and return filtered trades."""
        filtered = trades_list[:]
        if 'block_days' in filters:
            filtered = [t for t in filtered if t['day'] not in filters['block_days']]
        if 'block_hours' in filters:
            filtered = [t for t in filtered if t['hour'] not in filters['block_hours']]
        if 'min_sl' in filters:
            filtered = [t for t in filtered if t['sl_dist_pips'] >= filters['min_sl']]
        if 'atr_min' in filters:
            filtered = [t for t in filtered if t['h1_atr_pips'] is not None and t['h1_atr_pips'] >= filters['atr_min']]
        if 'atr_max' in filters:
            filtered = [t for t in filtered if t['h1_atr_pips'] is not None and t['h1_atr_pips'] <= filters['atr_max']]
        if 'max_ema_dist' in filters:
            filtered = [t for t in filtered if t['ema50_dist_pips'] is not None and t['ema50_dist_pips'] <= filters['max_ema_dist']]
        if 'direction' in filters:
            filtered = [t for t in filtered if t['direction'] == filters['direction']]
        if 'min_duration' in filters:
            filtered = [t for t in filtered if t['duration_min'] >= filters['min_duration']]
        return filtered

    # Define scenarios
    scenarios = {}
    scenarios['S0: Baseline (no filters)'] = {}
    scenarios['S1: Block Fri+Wed'] = {'block_days': ['Fri', 'Wed']}
    scenarios['S2: S1 + Block 09h+10h+16h'] = {'block_days': ['Fri', 'Wed'], 'block_hours': [9, 10, 16]}
    scenarios['S3: S2 + MinSL 10'] = {'block_days': ['Fri', 'Wed'], 'block_hours': [9, 10, 16], 'min_sl': 10}
    if best_atr_band:
        scenarios[f'S4: S3 + ATR {best_atr_band[0]}-{best_atr_band[1]}'] = {
            'block_days': ['Fri', 'Wed'], 'block_hours': [9, 10, 16], 'min_sl': 10,
            'atr_min': best_atr_band[0], 'atr_max': best_atr_band[1]}
        scenarios[f'S5: S4 + EMA50 max 100'] = {
            'block_days': ['Fri', 'Wed'], 'block_hours': [9, 10, 16], 'min_sl': 10,
            'atr_min': best_atr_band[0], 'atr_max': best_atr_band[1], 'max_ema_dist': 100}
    scenarios['S6: S2 + MinSL 12'] = {'block_days': ['Fri', 'Wed'], 'block_hours': [9, 10, 16], 'min_sl': 12}
    scenarios['S7: Block Fri + 09h+10h+16h + MinSL 10'] = {'block_days': ['Fri'], 'block_hours': [9, 10, 16], 'min_sl': 10}
    scenarios['S8a: Sell-only'] = {'direction': 'sell'}
    scenarios['S8b: Sell-only + Block Fri+Wed'] = {'direction': 'sell', 'block_days': ['Fri', 'Wed']}
    scenarios['S8c: Sell-only + S2 filters'] = {'direction': 'sell', 'block_days': ['Fri', 'Wed'], 'block_hours': [9, 10, 16]}
    scenarios['S8d: Sell-only + S3 filters'] = {'direction': 'sell', 'block_days': ['Fri', 'Wed'], 'block_hours': [9, 10, 16], 'min_sl': 10}
    scenarios['S9: S2 + MinDuration 60min'] = {'block_days': ['Fri', 'Wed'], 'block_hours': [9, 10, 16], 'min_duration': 60}
    scenarios['S10: MinDuration 60min only'] = {'min_duration': 60}
    scenarios['S11: Block Fri + Block 09h+10h+16h'] = {'block_days': ['Fri'], 'block_hours': [9, 10, 16]}
    scenarios['S12: S2 + MinSL 10 + EMA50<=100'] = {
        'block_days': ['Fri', 'Wed'], 'block_hours': [9, 10, 16], 'min_sl': 10, 'max_ema_dist': 100}
    scenarios['S13: S2 + MinSL 10 + EMA50<=80'] = {
        'block_days': ['Fri', 'Wed'], 'block_hours': [9, 10, 16], 'min_sl': 10, 'max_ema_dist': 80}
    scenarios['S14: Sell + S2 + MinSL 10 + EMA50<=100'] = {
        'direction': 'sell', 'block_days': ['Fri', 'Wed'], 'block_hours': [9, 10, 16], 'min_sl': 10, 'max_ema_dist': 100}

    # Duration-based scenarios
    scenarios['S15: MinDur 45min'] = {'min_duration': 45}
    scenarios['S16: MinDur 45min + Block Fri+Wed + Block 09h+10h+16h'] = {
        'min_duration': 45, 'block_days': ['Fri', 'Wed'], 'block_hours': [9, 10, 16]}
    scenarios['S17: MinDur 30min + S2'] = {
        'min_duration': 30, 'block_days': ['Fri', 'Wed'], 'block_hours': [9, 10, 16]}
    scenarios['S18: MinDur 60min + Block 09h+10h+16h'] = {
        'min_duration': 60, 'block_hours': [9, 10, 16]}

    # More aggressive sell-only combos
    scenarios['S19: Sell + MinDur 60min'] = {'direction': 'sell', 'min_duration': 60}
    scenarios['S20: Sell + MinDur 60min + Block Fri'] = {'direction': 'sell', 'min_duration': 60, 'block_days': ['Fri']}

    results = []
    for name, filters in scenarios.items():
        ft = apply_filters(trades, **filters)
        s = calc_stats(ft)
        results.append((name, s))

    # Sort by net profit
    results.sort(key=lambda x: -x[1]['net'])

    rows = []
    for name, s in results:
        rows.append([name[:50], s['count'], f"{s['wr']:.1f}%", s['pf'],
                      f"${s['net']:.0f}", f"{s['max_dd_pct']:.0f}%"])
    print_table(['Scenario', 'Trades', 'WR', 'PF', 'Net', 'MaxDD%'],
                rows, col_widths=[52, 8, 8, 8, 10, 8])

    # =========================================================================
    # EXTRA: Brute-force best filter combo targeting PF>1.5, DD<10%, trades>80
    # =========================================================================
    print_header("I.2 BRUTE-FORCE OPTIMAL FILTER SEARCH (PF>1.5, DD<10%, trades>80)")

    best_combos = []
    block_day_options = [[], ['Fri'], ['Wed'], ['Fri', 'Wed']]
    block_hour_options = [[], [9, 10, 16], [9, 10], [9, 16], [10, 16], [9], [10], [16]]
    min_sl_options = [0, 8, 10, 12, 15]
    direction_options = [None, 'sell']
    min_dur_options = [0, 30, 45, 60, 90]

    count = 0
    for bd in block_day_options:
        for bh in block_hour_options:
            for msl in min_sl_options:
                for dirn in direction_options:
                    for mdur in min_dur_options:
                        filters = {}
                        if bd:
                            filters['block_days'] = bd
                        if bh:
                            filters['block_hours'] = bh
                        if msl > 0:
                            filters['min_sl'] = msl
                        if dirn:
                            filters['direction'] = dirn
                        if mdur > 0:
                            filters['min_duration'] = mdur

                        ft = apply_filters(trades, **filters)
                        if len(ft) < 80:
                            continue
                        s = calc_stats(ft)
                        if s['pf'] >= 1.2:  # wider net, filter later
                            desc_parts = []
                            if bd:
                                desc_parts.append(f"Block:{'+'.join(bd)}")
                            if bh:
                                desc_parts.append(f"NoH:{bh}")
                            if msl > 0:
                                desc_parts.append(f"MinSL:{msl}")
                            if dirn:
                                desc_parts.append(f"Dir:{dirn}")
                            if mdur > 0:
                                desc_parts.append(f"MinDur:{mdur}")
                            desc = ' | '.join(desc_parts) if desc_parts else 'None'
                            best_combos.append((desc, s))
                            count += 1

    best_combos.sort(key=lambda x: -x[1]['pf'])
    print(f"\n  Tested combinations, found {count} with PF>=1.2 and trades>=80")

    # Show top 25 by PF
    print("\n  TOP 25 BY PROFIT FACTOR:")
    rows = []
    for desc, s in best_combos[:25]:
        marker = ""
        if s['pf'] >= 1.5 and s['max_dd_pct'] <= 10:
            marker = " ***TARGET***"
        elif s['pf'] >= 1.5:
            marker = " *PF>1.5*"
        rows.append([desc[:55], s['count'], f"{s['wr']:.1f}%", s['pf'],
                      f"${s['net']:.0f}", f"{s['max_dd_pct']:.0f}%", marker])
    print_table(['Filters', 'Trades', 'WR', 'PF', 'Net', 'DD%', 'Flag'],
                rows, col_widths=[57, 8, 8, 8, 10, 8, 16])

    # Show top by net profit (min PF 1.3)
    pf_filtered = [(d, s) for d, s in best_combos if s['pf'] >= 1.3]
    pf_filtered.sort(key=lambda x: -x[1]['net'])
    print("\n  TOP 15 BY NET PROFIT (PF>=1.3):")
    rows = []
    for desc, s in pf_filtered[:15]:
        rows.append([desc[:55], s['count'], f"{s['wr']:.1f}%", s['pf'],
                      f"${s['net']:.0f}", f"{s['max_dd_pct']:.0f}%"])
    print_table(['Filters', 'Trades', 'WR', 'PF', 'Net', 'DD%'],
                rows, col_widths=[57, 8, 8, 8, 10, 8])

    # =========================================================================
    # J. FINAL RECOMMENDATIONS
    # =========================================================================
    print_header("J. FINAL RECOMMENDATIONS")

    print("""
  KEY FINDINGS:
  =============

  1. RAW PERFORMANCE: 898 trades, WR 25.9%, PF 0.87, Net -$5,685
     The unfiltered bot is a net loser. BUT hidden edge exists with filters.

  2. DURATION IS THE #1 FILTER:
     - Trades < 60min: catastrophic losers (9% WR, massive losses)
     - Trades >= 60min: profitable (41%+ WR, PF > 1.0)
     - This is the single most impactful filter

  3. TOXIC TIME SLOTS:
     - Hours 09h, 10h, 16h are consistent losers
     - Friday and Wednesday are worst days
     - Combination of toxic hours + toxic days amplifies losses

  4. SELL > BUY significantly
     - Sells are near breakeven or slightly profitable
     - Buys account for vast majority of losses

  5. SL DISTANCE: Very tight SLs (<10 pips) get stopped out too often
     - MinSL 10+ improves results significantly

  RECOMMENDED PRESETS (ranked by confidence):
  ==========================================
""")

    # Print the best viable presets
    print("  PRESET 1 (CONSERVATIVE - Duration filter):")
    print("    MinDuration: 60min (or implement as hold-time logic)")
    print("    Block hours: 09, 10, 16")
    print("    Block days: Fri")
    ft = apply_filters(trades, min_duration=60, block_hours=[9, 10, 16], block_days=['Fri'])
    s = calc_stats(ft)
    print(f"    -> {s['count']} trades | WR: {s['wr']:.1f}% | PF: {s['pf']} | Net: ${s['net']:.0f} | DD: {s['max_dd_pct']:.0f}%")

    print("\n  PRESET 2 (BALANCED - Time + SL filters):")
    print("    Block hours: 09, 10, 16")
    print("    Block days: Fri, Wed")
    print("    MinSL: 10 pips")
    ft = apply_filters(trades, block_days=['Fri', 'Wed'], block_hours=[9, 10, 16], min_sl=10)
    s = calc_stats(ft)
    print(f"    -> {s['count']} trades | WR: {s['wr']:.1f}% | PF: {s['pf']} | Net: ${s['net']:.0f} | DD: {s['max_dd_pct']:.0f}%")

    print("\n  PRESET 3 (AGGRESSIVE - All filters):")
    print("    Block hours: 09, 10, 16")
    print("    Block days: Fri, Wed")
    print("    MinSL: 10 pips")
    print("    MinDuration: 60min")
    ft = apply_filters(trades, block_days=['Fri', 'Wed'], block_hours=[9, 10, 16], min_sl=10, min_duration=60)
    s = calc_stats(ft)
    print(f"    -> {s['count']} trades | WR: {s['wr']:.1f}% | PF: {s['pf']} | Net: ${s['net']:.0f} | DD: {s['max_dd_pct']:.0f}%")

    print("\n  PRESET 4 (SELL-ONLY + Filters):")
    print("    Direction: SELL only")
    print("    Block hours: 09, 10, 16")
    print("    Block days: Fri, Wed")
    print("    MinSL: 10 pips")
    ft = apply_filters(trades, direction='sell', block_days=['Fri', 'Wed'], block_hours=[9, 10, 16], min_sl=10)
    s = calc_stats(ft)
    print(f"    -> {s['count']} trades | WR: {s['wr']:.1f}% | PF: {s['pf']} | Net: ${s['net']:.0f} | DD: {s['max_dd_pct']:.0f}%")

    print("\n  PRESET 5 (SELL-ONLY + Duration):")
    print("    Direction: SELL only")
    print("    MinDuration: 60min")
    ft = apply_filters(trades, direction='sell', min_duration=60)
    s = calc_stats(ft)
    print(f"    -> {s['count']} trades | WR: {s['wr']:.1f}% | PF: {s['pf']} | Net: ${s['net']:.0f} | DD: {s['max_dd_pct']:.0f}%")

    print("\n  IMPLEMENTATION NOTES:")
    print("  - Duration filter requires a 'MinHoldTime' input in the EA")
    print("    that prevents closing trades before X minutes (except SL hit)")
    print("  - OR: only count trades that naturally last >60min as the edge signal")
    print("  - Toxic hours filter is straightforward: block new entries at 09, 10, 16")
    print("  - Day filter: block new entries on Friday (and optionally Wednesday)")
    print("  - MinSL: reject setups where OB-based SL is < 10 pips")
    print("  - Sell-only mode: most conservative but cuts trade count significantly")

    print("\n" + "=" * 80)
    print("  END OF ANALYSIS")
    print("=" * 80)


if __name__ == '__main__':
    main()
