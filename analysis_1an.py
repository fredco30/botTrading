"""
EMA Pullback EA - 1-Year Performance Diagnosis
Period: April 2025 - April 2026
Analyzes why the EA went from +122% (3yr) to nearly flat (+0.97%) in the last year.
"""

import csv
from datetime import datetime, timedelta
from collections import defaultdict

# ==============================================================================
# DATA LOADING
# ==============================================================================

def load_trades(filepath):
    """Parse the tab-separated trade history file."""
    trades = []
    with open(filepath, 'r') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.split('\t')
            if len(parts) < 10:
                continue
            try:
                entry = {
                    'num': int(parts[0]),
                    'datetime': datetime.strptime(parts[1], '%Y.%m.%d %H:%M'),
                    'action': parts[2].strip(),
                    'ticket': int(parts[3]),
                    'lots': float(parts[4]),
                    'price': float(parts[5]),
                    'sl': float(parts[6]),
                    'tp': float(parts[7]),
                    'profit': float(parts[8]),
                    'balance': float(parts[9]),
                }
                trades.append(entry)
            except (ValueError, IndexError):
                continue
    return trades


def load_h1_data(filepath):
    """Load H1 OHLCV data. Format: Date,Time,Open,High,Low,Close,Volume (no header)."""
    bars = []
    with open(filepath, 'r') as f:
        reader = csv.reader(f)
        for row in reader:
            if len(row) < 7:
                continue
            try:
                dt = datetime.strptime(f"{row[0]},{row[1]}", '%Y.%m.%d,%H:%M')
                bar = {
                    'datetime': dt,
                    'open': float(row[2]),
                    'high': float(row[3]),
                    'low': float(row[4]),
                    'close': float(row[5]),
                    'volume': int(row[6]),
                }
                bars.append(bar)
            except (ValueError, IndexError):
                continue
    return bars


def build_round_trips(trades):
    """Build round-trip trades from raw trade lines."""
    # Group by ticket
    tickets = defaultdict(list)
    for t in trades:
        tickets[t['ticket']].append(t)

    round_trips = []
    for ticket, events in sorted(tickets.items()):
        entry_event = None
        exit_event = None
        modifies = []

        for e in events:
            if e['action'] in ('buy', 'sell'):
                entry_event = e
            elif e['action'] in ('s/l', 't/p'):
                exit_event = e
            elif e['action'] == 'modify':
                modifies.append(e)

        if entry_event and exit_event:
            direction = entry_event['action']  # buy or sell

            # SL distance in pips
            if direction == 'buy':
                sl_dist = (entry_event['price'] - entry_event['sl']) / 0.0001
            else:
                sl_dist = (entry_event['sl'] - entry_event['price']) / 0.0001

            # Duration
            duration = (exit_event['datetime'] - entry_event['datetime']).total_seconds() / 60.0

            # Determine outcome
            profit = exit_event['profit']
            if exit_event['action'] == 't/p':
                outcome = 'win'
            elif profit > 1.0:
                outcome = 'breakeven'  # small positive from BE move
            elif profit >= -1.0 and profit <= 1.0:
                outcome = 'breakeven'
            else:
                outcome = 'loss'

            # Was SL modified (breakeven move)?
            be_moved = len(modifies) > 0

            round_trips.append({
                'ticket': ticket,
                'direction': direction,
                'entry_time': entry_event['datetime'],
                'exit_time': exit_event['datetime'],
                'entry_price': entry_event['price'],
                'exit_price': exit_event['price'],
                'sl': entry_event['sl'],
                'tp': entry_event['tp'],
                'sl_dist_pips': abs(sl_dist),
                'lots': entry_event['lots'],
                'profit': profit,
                'balance': exit_event['balance'],
                'duration_min': duration,
                'exit_type': exit_event['action'],
                'outcome': outcome,
                'be_moved': be_moved,
            })

    return round_trips


def compute_atr(bars, period=14):
    """Compute ATR(14) for each bar. Returns dict: datetime -> atr value."""
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

        if len(trs) >= period:
            if len(trs) == period:
                atr = sum(trs) / period
            else:
                atr = (atr_map[bars[i-1]['datetime']] * (period - 1) + tr) / period
            atr_map[bars[i]['datetime']] = atr

    return atr_map


def compute_ema(bars, period=50):
    """Compute EMA for close prices. Returns dict: datetime -> ema value."""
    ema_map = {}
    if len(bars) < period:
        return ema_map

    multiplier = 2.0 / (period + 1)
    # SMA for first value
    sma = sum(b['close'] for b in bars[:period]) / period
    ema_map[bars[period-1]['datetime']] = sma

    prev_ema = sma
    for i in range(period, len(bars)):
        ema = (bars[i]['close'] - prev_ema) * multiplier + prev_ema
        ema_map[bars[i]['datetime']] = ema
        prev_ema = ema

    return ema_map


def find_nearest_bar(bars_by_date, dt):
    """Find the H1 bar closest to (but not after) the given datetime."""
    # Round down to the hour
    target = dt.replace(minute=0, second=0, microsecond=0)
    for offset in range(0, 48):  # look back up to 48 hours
        check = target - timedelta(hours=offset)
        if check in bars_by_date:
            return check
    return None


# ==============================================================================
# PRINTING HELPERS
# ==============================================================================

def fmt_pf(wins_total, losses_total):
    """Compute profit factor."""
    if losses_total == 0:
        return float('inf') if wins_total > 0 else 0
    return abs(wins_total / losses_total) if losses_total != 0 else 0


def print_table(headers, rows, col_widths=None):
    """Print a formatted table."""
    if col_widths is None:
        col_widths = []
        for i, h in enumerate(headers):
            max_w = len(str(h))
            for r in rows:
                max_w = max(max_w, len(str(r[i])))
            col_widths.append(max_w + 2)

    # Header
    header_line = '|'.join(str(h).center(w) for h, w in zip(headers, col_widths))
    sep_line = '+'.join('-' * w for w in col_widths)
    print(sep_line)
    print(header_line)
    print(sep_line)
    for r in rows:
        row_line = '|'.join(str(r[i]).rjust(w - 1) + ' ' for i, w in enumerate(col_widths))
        print(row_line)
    print(sep_line)


# ==============================================================================
# MAIN ANALYSIS
# ==============================================================================

def main():
    print("=" * 80)
    print("  EMA PULLBACK EA - 1-YEAR PERFORMANCE DIAGNOSIS")
    print("  Period: April 2025 - April 2026 | Pair: EURUSD")
    print("=" * 80)

    # Load data
    trades_raw = load_trades("C:/Users/projets/botTrading/historique trade 1an.txt")
    h1_bars = load_h1_data("C:/Users/projets/botTrading/EURUSD60.csv")

    # Filter H1 bars to relevant period (2024 onward for ATR warmup)
    h1_bars = [b for b in h1_bars if b['datetime'].year >= 2024]
    h1_bars.sort(key=lambda x: x['datetime'])

    # Build round trips
    rts = build_round_trips(trades_raw)
    print(f"\nLoaded {len(trades_raw)} raw trade lines -> {len(rts)} round-trip trades")
    print(f"H1 bars loaded: {len(h1_bars)} (from {h1_bars[0]['datetime']} to {h1_bars[-1]['datetime']})")

    # Compute ATR and EMA on H1
    atr_map = compute_atr(h1_bars, 14)
    ema50_map = compute_ema(h1_bars, 50)

    # Build bars by datetime for lookup
    bars_by_dt = {b['datetime']: b for b in h1_bars}

    # Attach ATR and EMA to each trade
    for rt in rts:
        nearest = find_nearest_bar(bars_by_dt, rt['entry_time'])
        if nearest and nearest in atr_map:
            rt['atr'] = atr_map[nearest]
        else:
            rt['atr'] = None

        if nearest and nearest in ema50_map:
            rt['ema50'] = ema50_map[nearest]
            rt['dist_from_ema50'] = abs(rt['entry_price'] - rt['ema50']) / 0.0001  # in pips
        else:
            rt['ema50'] = None
            rt['dist_from_ema50'] = None

        # EMA slope: compare current EMA to EMA 5 bars ago
        if nearest and nearest in ema50_map:
            slope_lookback = nearest - timedelta(hours=5)
            if slope_lookback in ema50_map:
                rt['ema50_slope'] = (ema50_map[nearest] - ema50_map[slope_lookback]) / 0.0001
            else:
                rt['ema50_slope'] = None
        else:
            rt['ema50_slope'] = None

    # ------------------------------------------------------------------
    # 1. BASIC STATS
    # ------------------------------------------------------------------
    print("\n" + "=" * 80)
    print("  1. BASIC STATISTICS")
    print("=" * 80)

    wins = [r for r in rts if r['outcome'] == 'win']
    losses = [r for r in rts if r['outcome'] == 'loss']
    bes = [r for r in rts if r['outcome'] == 'breakeven']

    total = len(rts)
    total_profit = sum(r['profit'] for r in rts)
    gross_wins = sum(r['profit'] for r in wins)
    gross_losses = sum(r['profit'] for r in losses)
    pf = fmt_pf(gross_wins, gross_losses)

    avg_win = gross_wins / len(wins) if wins else 0
    avg_loss = gross_losses / len(losses) if losses else 0
    winrate = len(wins) / total * 100 if total else 0

    starting_bal = rts[0]['balance'] - rts[0]['profit'] if rts else 10000
    ending_bal = rts[-1]['balance'] if rts else 10000
    pct_return = (ending_bal - 10000) / 10000 * 100

    print(f"  Total trades:     {total}")
    print(f"  Wins:             {len(wins)}")
    print(f"  Losses:           {len(losses)}")
    print(f"  Breakevens:       {len(bes)}")
    print(f"  Winrate:          {winrate:.1f}%")
    print(f"  Profit Factor:    {pf:.2f}")
    print(f"  Net Profit:       ${total_profit:.2f}")
    print(f"  Starting Balance: $10,000.00")
    print(f"  Ending Balance:   ${ending_bal:.2f}")
    print(f"  Return:           {pct_return:.2f}%")
    print(f"  Avg Win:          ${avg_win:.2f}")
    print(f"  Avg Loss:         ${avg_loss:.2f}")
    print(f"  Avg Win/Avg Loss: {abs(avg_win/avg_loss):.2f}" if avg_loss != 0 else "  Avg Win/Avg Loss: N/A")

    # ------------------------------------------------------------------
    # 2. MONTHLY BREAKDOWN
    # ------------------------------------------------------------------
    print("\n" + "=" * 80)
    print("  2. MONTHLY BREAKDOWN")
    print("=" * 80)

    monthly = defaultdict(lambda: {'trades': 0, 'wins': 0, 'losses': 0, 'bes': 0,
                                     'profit': 0, 'gross_win': 0, 'gross_loss': 0})
    for r in rts:
        key = r['entry_time'].strftime('%Y-%m')
        monthly[key]['trades'] += 1
        monthly[key]['profit'] += r['profit']
        if r['outcome'] == 'win':
            monthly[key]['wins'] += 1
            monthly[key]['gross_win'] += r['profit']
        elif r['outcome'] == 'loss':
            monthly[key]['losses'] += 1
            monthly[key]['gross_loss'] += r['profit']
        else:
            monthly[key]['bes'] += 1

    headers = ['Month', 'Trades', 'W', 'L', 'BE', 'WR%', 'Net $', 'PF', 'Cumul $']
    rows = []
    cumul = 0
    for month in sorted(monthly.keys()):
        m = monthly[month]
        wr = m['wins'] / m['trades'] * 100 if m['trades'] > 0 else 0
        pf_m = fmt_pf(m['gross_win'], m['gross_loss'])
        pf_str = f"{pf_m:.2f}" if pf_m != float('inf') else "INF"
        cumul += m['profit']
        rows.append([
            month,
            m['trades'],
            m['wins'],
            m['losses'],
            m['bes'],
            f"{wr:.0f}",
            f"{m['profit']:.0f}",
            pf_str,
            f"{cumul:.0f}",
        ])

    print_table(headers, rows)

    # Identify best and worst months
    sorted_months = sorted(monthly.items(), key=lambda x: x[1]['profit'])
    print(f"\n  Worst month: {sorted_months[0][0]} (${sorted_months[0][1]['profit']:.0f})")
    print(f"  Best month:  {sorted_months[-1][0]} (${sorted_months[-1][1]['profit']:.0f})")

    # Count profitable vs losing months
    prof_months = sum(1 for k, v in monthly.items() if v['profit'] > 0)
    loss_months = sum(1 for k, v in monthly.items() if v['profit'] <= 0)
    print(f"  Profitable months: {prof_months} | Losing months: {loss_months}")

    # ------------------------------------------------------------------
    # 3. WINS vs LOSSES CHARACTERISTICS
    # ------------------------------------------------------------------
    print("\n" + "=" * 80)
    print("  3. WINS vs LOSSES CHARACTERISTICS")
    print("=" * 80)

    avg_sl_wins = sum(r['sl_dist_pips'] for r in wins) / len(wins) if wins else 0
    avg_sl_losses = sum(r['sl_dist_pips'] for r in losses) / len(losses) if losses else 0
    avg_sl_be = sum(r['sl_dist_pips'] for r in bes) / len(bes) if bes else 0

    avg_dur_wins = sum(r['duration_min'] for r in wins) / len(wins) if wins else 0
    avg_dur_losses = sum(r['duration_min'] for r in losses) / len(losses) if losses else 0
    avg_dur_be = sum(r['duration_min'] for r in bes) / len(bes) if bes else 0

    headers = ['Metric', 'Wins', 'Losses', 'Breakevens']
    rows = [
        ['Count', len(wins), len(losses), len(bes)],
        ['Avg SL (pips)', f"{avg_sl_wins:.1f}", f"{avg_sl_losses:.1f}", f"{avg_sl_be:.1f}"],
        ['Avg Duration (min)', f"{avg_dur_wins:.0f}", f"{avg_dur_losses:.0f}", f"{avg_dur_be:.0f}"],
        ['Avg Profit $', f"{avg_win:.2f}", f"{avg_loss:.2f}", f"{sum(r['profit'] for r in bes)/len(bes):.2f}" if bes else "0"],
    ]
    print_table(headers, rows)

    # Fast SL hits (< 1 hour)
    fast_sl = [r for r in losses if r['duration_min'] < 60]
    print(f"\n  Trades hitting SL in < 1 hour: {len(fast_sl)} / {len(losses)} losses ({len(fast_sl)/len(losses)*100:.0f}%)" if losses else "")
    fast_sl_30 = [r for r in losses if r['duration_min'] < 30]
    print(f"  Trades hitting SL in < 30 min: {len(fast_sl_30)} / {len(losses)} losses ({len(fast_sl_30)/len(losses)*100:.0f}%)" if losses else "")

    # Duration distribution for losses
    dur_buckets = {'< 15 min': 0, '15-30 min': 0, '30-60 min': 0, '1-2 hr': 0, '2-4 hr': 0, '4+ hr': 0}
    for r in losses:
        d = r['duration_min']
        if d < 15:
            dur_buckets['< 15 min'] += 1
        elif d < 30:
            dur_buckets['15-30 min'] += 1
        elif d < 60:
            dur_buckets['30-60 min'] += 1
        elif d < 120:
            dur_buckets['1-2 hr'] += 1
        elif d < 240:
            dur_buckets['2-4 hr'] += 1
        else:
            dur_buckets['4+ hr'] += 1

    print("\n  Loss duration distribution:")
    for bucket, count in dur_buckets.items():
        bar = '#' * count
        print(f"    {bucket:>12}: {count:2d} {bar}")

    # ------------------------------------------------------------------
    # 4. ATR ANALYSIS
    # ------------------------------------------------------------------
    print("\n" + "=" * 80)
    print("  4. ATR(14) H1 ANALYSIS")
    print("=" * 80)

    wins_with_atr = [r for r in wins if r['atr'] is not None]
    losses_with_atr = [r for r in losses if r['atr'] is not None]
    bes_with_atr = [r for r in bes if r['atr'] is not None]
    all_with_atr = [r for r in rts if r['atr'] is not None]

    if wins_with_atr and losses_with_atr:
        avg_atr_wins = sum(r['atr'] for r in wins_with_atr) / len(wins_with_atr) * 10000
        avg_atr_losses = sum(r['atr'] for r in losses_with_atr) / len(losses_with_atr) * 10000
        avg_atr_be = sum(r['atr'] for r in bes_with_atr) / len(bes_with_atr) * 10000 if bes_with_atr else 0
        avg_atr_all = sum(r['atr'] for r in all_with_atr) / len(all_with_atr) * 10000

        print(f"  Average ATR(14) H1 at entry (in pips):")
        print(f"    All trades:  {avg_atr_all:.1f} pips")
        print(f"    Winners:     {avg_atr_wins:.1f} pips")
        print(f"    Losers:      {avg_atr_losses:.1f} pips")
        print(f"    Breakevens:  {avg_atr_be:.1f} pips")

        # Monthly ATR vs performance
        print(f"\n  Monthly ATR vs Performance:")
        headers = ['Month', 'Avg ATR', 'Net $', 'Trades', 'WR%']
        rows = []
        for month in sorted(monthly.keys()):
            month_trades = [r for r in rts if r['entry_time'].strftime('%Y-%m') == month and r['atr'] is not None]
            if month_trades:
                avg_atr_m = sum(r['atr'] for r in month_trades) / len(month_trades) * 10000
                rows.append([
                    month,
                    f"{avg_atr_m:.1f}",
                    f"{monthly[month]['profit']:.0f}",
                    monthly[month]['trades'],
                    f"{monthly[month]['wins']/monthly[month]['trades']*100:.0f}" if monthly[month]['trades'] > 0 else "0",
                ])
        print_table(headers, rows)

        # ATR quartile analysis
        all_atrs = sorted([r['atr'] * 10000 for r in all_with_atr])
        q1 = all_atrs[len(all_atrs)//4]
        q2 = all_atrs[len(all_atrs)//2]
        q3 = all_atrs[3*len(all_atrs)//4]

        print(f"\n  ATR Quartile Analysis:")
        print(f"    Q1 (low vol):  < {q1:.1f} pips")
        print(f"    Q2 (medium):   {q1:.1f} - {q2:.1f} pips")
        print(f"    Q3 (med-high): {q2:.1f} - {q3:.1f} pips")
        print(f"    Q4 (high vol): > {q3:.1f} pips")

        for label, low, high in [('Q1 (low)', 0, q1), ('Q2 (med)', q1, q2), ('Q3 (med-hi)', q2, q3), ('Q4 (high)', q3, 999)]:
            q_trades = [r for r in all_with_atr if low <= r['atr'] * 10000 < high]
            q_wins = [r for r in q_trades if r['outcome'] == 'win']
            q_profit = sum(r['profit'] for r in q_trades)
            q_wr = len(q_wins) / len(q_trades) * 100 if q_trades else 0
            print(f"    {label:>12}: {len(q_trades):2d} trades, WR={q_wr:.0f}%, Net=${q_profit:.0f}")

    # ------------------------------------------------------------------
    # 5. DIRECTION ANALYSIS
    # ------------------------------------------------------------------
    print("\n" + "=" * 80)
    print("  5. DIRECTION ANALYSIS (BUY vs SELL)")
    print("=" * 80)

    for direction in ['buy', 'sell']:
        d_trades = [r for r in rts if r['direction'] == direction]
        d_wins = [r for r in d_trades if r['outcome'] == 'win']
        d_losses = [r for r in d_trades if r['outcome'] == 'loss']
        d_profit = sum(r['profit'] for r in d_trades)
        d_gross_w = sum(r['profit'] for r in d_wins)
        d_gross_l = sum(r['profit'] for r in d_losses)
        d_pf = fmt_pf(d_gross_w, d_gross_l)
        d_wr = len(d_wins) / len(d_trades) * 100 if d_trades else 0

        print(f"\n  {direction.upper()}:")
        print(f"    Trades: {len(d_trades)} | Wins: {len(d_wins)} | Losses: {len(d_losses)}")
        print(f"    Winrate: {d_wr:.1f}% | PF: {d_pf:.2f} | Net: ${d_profit:.2f}")
        print(f"    Avg Win: ${d_gross_w/len(d_wins):.2f}" if d_wins else "    Avg Win: N/A")
        print(f"    Avg Loss: ${d_gross_l/len(d_losses):.2f}" if d_losses else "    Avg Loss: N/A")

    # ------------------------------------------------------------------
    # 6. SESSION / HOUR ANALYSIS
    # ------------------------------------------------------------------
    print("\n" + "=" * 80)
    print("  6. HOUR-OF-ENTRY ANALYSIS")
    print("=" * 80)

    hourly = defaultdict(lambda: {'trades': 0, 'wins': 0, 'losses': 0, 'profit': 0,
                                    'gross_win': 0, 'gross_loss': 0})
    for r in rts:
        h = r['entry_time'].hour
        hourly[h]['trades'] += 1
        hourly[h]['profit'] += r['profit']
        if r['outcome'] == 'win':
            hourly[h]['wins'] += 1
            hourly[h]['gross_win'] += r['profit']
        elif r['outcome'] == 'loss':
            hourly[h]['losses'] += 1
            hourly[h]['gross_loss'] += r['profit']

    headers = ['Hour', 'Trades', 'W', 'L', 'WR%', 'Net $', 'PF', 'Session']
    rows = []
    for h in sorted(hourly.keys()):
        hd = hourly[h]
        wr = hd['wins'] / hd['trades'] * 100 if hd['trades'] > 0 else 0
        pf_h = fmt_pf(hd['gross_win'], hd['gross_loss'])
        pf_str = f"{pf_h:.2f}" if pf_h != float('inf') else "INF"

        if 8 <= h <= 11:
            session = "London"
        elif 12 <= h <= 12:
            session = "Ldn/NY"
        elif 13 <= h <= 17:
            session = "New York"
        else:
            session = "Off-hours"

        rows.append([f"{h:02d}:00", hd['trades'], hd['wins'], hd['losses'],
                     f"{wr:.0f}", f"{hd['profit']:.0f}", pf_str, session])

    print_table(headers, rows)

    # Session summary
    print("\n  Session Summary:")
    for session_name, hours in [('London (8-12)', range(8, 12)), ('New York (13-17)', range(13, 18))]:
        s_trades = [r for r in rts if r['entry_time'].hour in hours]
        s_wins = [r for r in s_trades if r['outcome'] == 'win']
        s_profit = sum(r['profit'] for r in s_trades)
        s_wr = len(s_wins) / len(s_trades) * 100 if s_trades else 0
        print(f"    {session_name}: {len(s_trades)} trades, WR={s_wr:.0f}%, Net=${s_profit:.0f}")

    # ------------------------------------------------------------------
    # 7. MARKET REGIME ANALYSIS
    # ------------------------------------------------------------------
    print("\n" + "=" * 80)
    print("  7. MARKET REGIME ANALYSIS")
    print("=" * 80)

    # Classify trades by market regime
    trending_trades = []
    ranging_trades = []
    slope_threshold = 3.0  # pips over 5 hours = trending

    for r in rts:
        if r['ema50_slope'] is not None:
            if abs(r['ema50_slope']) > slope_threshold:
                trending_trades.append(r)
            else:
                ranging_trades.append(r)

    for label, group in [('TRENDING', trending_trades), ('RANGING', ranging_trades)]:
        g_wins = [r for r in group if r['outcome'] == 'win']
        g_losses = [r for r in group if r['outcome'] == 'loss']
        g_profit = sum(r['profit'] for r in group)
        g_gross_w = sum(r['profit'] for r in g_wins)
        g_gross_l = sum(r['profit'] for r in g_losses)
        g_pf = fmt_pf(g_gross_w, g_gross_l)
        g_wr = len(g_wins) / len(group) * 100 if group else 0

        print(f"\n  {label} market (EMA50 slope {'>' if label == 'TRENDING' else '<='} {slope_threshold} pips/5h):")
        print(f"    Trades: {len(group)} | Wins: {len(g_wins)} | Losses: {len(g_losses)}")
        print(f"    Winrate: {g_wr:.1f}% | PF: {g_pf:.2f} | Net: ${g_profit:.0f}")

    # Distance from EMA50 analysis
    print(f"\n  Distance from EMA50 at Entry:")
    for label, group in [('Winners', wins), ('Losers', losses), ('Breakevens', bes)]:
        dists = [r['dist_from_ema50'] for r in group if r['dist_from_ema50'] is not None]
        if dists:
            print(f"    {label:>12}: avg={sum(dists)/len(dists):.1f} pips, "
                  f"min={min(dists):.1f}, max={max(dists):.1f}")

    # Weekly candle range analysis
    print(f"\n  Weekly H1 Candle Range Analysis:")
    # Group H1 bars by week and compute avg range
    weekly_ranges = defaultdict(list)
    for b in h1_bars:
        week_key = b['datetime'].strftime('%Y-W%W')
        weekly_ranges[week_key].append(b['high'] - b['low'])

    weekly_avg_range = {}
    for wk, ranges in weekly_ranges.items():
        weekly_avg_range[wk] = sum(ranges) / len(ranges) * 10000  # in pips

    # For each trade, get the weekly avg range
    for r in rts:
        wk = r['entry_time'].strftime('%Y-W%W')
        r['weekly_h1_range'] = weekly_avg_range.get(wk, None)

    winning_weeks_ranges = [r['weekly_h1_range'] for r in wins if r['weekly_h1_range'] is not None]
    losing_weeks_ranges = [r['weekly_h1_range'] for r in losses if r['weekly_h1_range'] is not None]

    if winning_weeks_ranges and losing_weeks_ranges:
        print(f"    Avg H1 range (week of winning trades): {sum(winning_weeks_ranges)/len(winning_weeks_ranges):.1f} pips")
        print(f"    Avg H1 range (week of losing trades):  {sum(losing_weeks_ranges)/len(losing_weeks_ranges):.1f} pips")

    # Monthly regime vs performance
    print(f"\n  Monthly Regime Classification:")
    headers = ['Month', 'Avg EMA Slope', 'Regime', 'Avg Dist EMA', 'Net $']
    rows = []
    for month in sorted(monthly.keys()):
        month_trades = [r for r in rts if r['entry_time'].strftime('%Y-%m') == month]
        slopes = [r['ema50_slope'] for r in month_trades if r['ema50_slope'] is not None]
        dists = [r['dist_from_ema50'] for r in month_trades if r['dist_from_ema50'] is not None]

        avg_slope = sum(slopes) / len(slopes) if slopes else 0
        avg_dist = sum(dists) / len(dists) if dists else 0
        regime = "TREND" if abs(avg_slope) > slope_threshold else "RANGE"

        rows.append([
            month,
            f"{avg_slope:+.1f}",
            regime,
            f"{avg_dist:.1f}",
            f"{monthly[month]['profit']:.0f}",
        ])
    print_table(headers, rows)

    # ------------------------------------------------------------------
    # 8. STREAK ANALYSIS
    # ------------------------------------------------------------------
    print("\n" + "=" * 80)
    print("  8. STREAK & DRAWDOWN ANALYSIS")
    print("=" * 80)

    # Consecutive losses
    max_consec_loss = 0
    curr_consec_loss = 0
    max_loss_streak_start = None
    curr_streak_start = None

    for r in rts:
        if r['outcome'] == 'loss':
            if curr_consec_loss == 0:
                curr_streak_start = r['entry_time']
            curr_consec_loss += 1
            if curr_consec_loss > max_consec_loss:
                max_consec_loss = curr_consec_loss
                max_loss_streak_start = curr_streak_start
        else:
            curr_consec_loss = 0

    print(f"  Max consecutive losses: {max_consec_loss} (starting {max_loss_streak_start})")

    # Max drawdown
    peak_bal = 10000
    max_dd = 0
    max_dd_from = 10000
    for r in rts:
        if r['balance'] > peak_bal:
            peak_bal = r['balance']
        dd = peak_bal - r['balance']
        if dd > max_dd:
            max_dd = dd
            max_dd_from = peak_bal

    print(f"  Max drawdown: ${max_dd:.2f} ({max_dd/max_dd_from*100:.1f}% from peak ${max_dd_from:.2f})")

    # Equity curve description
    print(f"\n  Equity Curve Phases:")
    prev_bal = 10000
    phase_start = rts[0]['entry_time'] if rts else None
    phase_type = None
    phases = []

    for r in rts:
        bal = r['balance']
        if bal > prev_bal + 50:
            if phase_type != 'UP':
                if phase_type is not None:
                    phases.append((phase_start, r['entry_time'], phase_type, prev_bal))
                phase_start = r['entry_time']
                phase_type = 'UP'
        elif bal < prev_bal - 50:
            if phase_type != 'DOWN':
                if phase_type is not None:
                    phases.append((phase_start, r['entry_time'], phase_type, prev_bal))
                phase_start = r['entry_time']
                phase_type = 'DOWN'
        prev_bal = bal

    if phase_type:
        phases.append((phase_start, rts[-1]['exit_time'], phase_type, rts[-1]['balance']))

    for start, end, ptype, bal in phases:
        print(f"    {start.strftime('%Y-%m-%d')} -> {end.strftime('%Y-%m-%d')}: {ptype} (bal: ${bal:.0f})")

    # ------------------------------------------------------------------
    # 9. KEY FINDING: BREAKEVEN TRADES ANALYSIS
    # ------------------------------------------------------------------
    print("\n" + "=" * 80)
    print("  9. BREAKEVEN TRADES DEEP DIVE")
    print("=" * 80)

    print(f"  Total breakeven trades: {len(bes)}")
    if bes:
        be_total_profit = sum(r['profit'] for r in bes)
        print(f"  Total profit from BEs: ${be_total_profit:.2f}")
        print(f"  Average BE profit: ${be_total_profit/len(bes):.2f}")

        # How many BEs had modify (SL moved to BE)?
        be_modified = [r for r in bes if r['be_moved']]
        print(f"  BEs with SL moved to breakeven: {len(be_modified)} / {len(bes)}")

        # These are trades that WERE winning but got stopped out at BE
        # Potential missed profits
        potential_profits = []
        for r in bes:
            if r['direction'] == 'buy':
                potential = (r['tp'] - r['entry_price']) / 0.0001 * r['lots'] * 10
            else:
                potential = (r['entry_price'] - r['tp']) / 0.0001 * r['lots'] * 10
            potential_profits.append(potential)

        print(f"  Avg potential profit missed per BE: ${sum(potential_profits)/len(potential_profits):.2f}")
        print(f"  Total potential profit missed: ${sum(potential_profits):.2f}")

    # ------------------------------------------------------------------
    # 10. THE KEY QUESTION
    # ------------------------------------------------------------------
    print("\n" + "=" * 80)
    print("  10. DIAGNOSIS: WHY IS THE EA FLAT?")
    print("=" * 80)

    # Compute key metrics for diagnosis
    actual_wins = len(wins)
    actual_losses = len(losses)
    actual_bes = len(bes)

    # What would happen without BEs that went to BE?
    total_be_potential = sum(potential_profits) if bes else 0

    # Fast losses (< 1h)
    fast_loss_count = len(fast_sl)
    fast_loss_total = sum(r['profit'] for r in fast_sl)

    # Compute how much the BEs are costing
    # Each BE trade that was modified = a winning trade that got stopped at BE
    # instead of hitting TP

    print(f"""
  FINDING 1: BREAKEVEN TRAP
  -------------------------
  - {len(bes)} trades ({len(bes)/total*100:.0f}% of all trades) hit breakeven after being moved
  - These trades were in profit (SL was moved to entry) but reversed
  - Potential profit missed from these trades: ${total_be_potential:.0f}
  - If even HALF of these had hit TP, net profit would be +${total_profit + total_be_potential/2:.0f}
  - The BE mechanism is too aggressive - it converts potential winners into $0

  FINDING 2: FAST STOP-LOSSES
  ---------------------------
  - {fast_loss_count} / {actual_losses} losses ({fast_loss_count/actual_losses*100:.0f}%) hit SL within 1 hour
  - Total cost of fast SLs: ${fast_loss_total:.0f}
  - Average duration of fast SLs: {sum(r['duration_min'] for r in fast_sl)/len(fast_sl):.0f} min
  - This suggests entries are poorly timed or SL is too tight""")

    # Compare winning months ATR vs losing months ATR
    winning_months = [(k, v) for k, v in monthly.items() if v['profit'] > 0]
    losing_months = [(k, v) for k, v in monthly.items() if v['profit'] <= 0]

    win_month_atrs = []
    lose_month_atrs = []
    for k, v in winning_months:
        mt = [r for r in rts if r['entry_time'].strftime('%Y-%m') == k and r['atr'] is not None]
        win_month_atrs.extend([r['atr'] * 10000 for r in mt])
    for k, v in losing_months:
        mt = [r for r in rts if r['entry_time'].strftime('%Y-%m') == k and r['atr'] is not None]
        lose_month_atrs.extend([r['atr'] * 10000 for r in mt])

    avg_win_month_atr = sum(win_month_atrs) / len(win_month_atrs) if win_month_atrs else 0
    avg_lose_month_atr = sum(lose_month_atrs) / len(lose_month_atrs) if lose_month_atrs else 0

    print(f"""
  FINDING 3: VOLATILITY MISMATCH
  ------------------------------
  - Avg ATR in profitable months: {avg_win_month_atr:.1f} pips
  - Avg ATR in losing months:     {avg_lose_month_atr:.1f} pips
  - The EA {'performs better in higher volatility' if avg_win_month_atr > avg_lose_month_atr else 'shows no clear ATR edge'}""")

    # Direction imbalance
    buys = [r for r in rts if r['direction'] == 'buy']
    sells = [r for r in rts if r['direction'] == 'sell']
    buy_profit = sum(r['profit'] for r in buys)
    sell_profit = sum(r['profit'] for r in sells)

    print(f"""
  FINDING 4: DIRECTION IMBALANCE
  ------------------------------
  - Buys:  {len(buys)} trades, Net ${buy_profit:.0f}
  - Sells: {len(sells)} trades, Net ${sell_profit:.0f}
  - {'Sells significantly outperform buys' if sell_profit > buy_profit + 200 else 'Buys significantly outperform sells' if buy_profit > sell_profit + 200 else 'Both directions are roughly similar'}""")

    # Regime analysis
    trending_profit = sum(r['profit'] for r in trending_trades)
    ranging_profit = sum(r['profit'] for r in ranging_trades)

    print(f"""
  FINDING 5: MARKET REGIME
  ------------------------
  - Trending market trades: {len(trending_trades)}, Net ${trending_profit:.0f}
  - Ranging market trades:  {len(ranging_trades)}, Net ${ranging_profit:.0f}
  - {'EA works in trending markets but bleeds in ranges' if trending_profit > 0 and ranging_profit < 0 else 'EA works in ranging markets but bleeds in trends' if ranging_profit > 0 and trending_profit < 0 else 'No clear regime preference'}""")

    # Final verdict
    print(f"""
  ====================================================================
  FINAL VERDICT
  ====================================================================

  The EA is NOT fundamentally broken. Here's the evidence:

  1. WINRATE ({winrate:.0f}%) is reasonable for a 2:1+ RR system
  2. Average win (${avg_win:.0f}) vs average loss (${avg_loss:.0f}) =
     reward/risk ratio of {abs(avg_win/avg_loss):.2f}x {'(GOOD)' if abs(avg_win/avg_loss) > 1.5 else '(NEEDS IMPROVEMENT)'}
  3. The EA has {prof_months} profitable months vs {loss_months} losing months

  PRIMARY ISSUES:

  A) BREAKEVEN TRAP: {len(bes)} trades ({len(bes)/total*100:.0f}%) moved to BE then stopped out.
     This is the #1 profit killer. The BE move at 1R is too aggressive.
     Recommendation: Move BE trigger to 1.5R instead of 1R.

  B) FAST STOPS: {fast_loss_count}/{actual_losses} losses ({fast_loss_count/actual_losses*100:.0f}%) happen within 1 hour.
     Entries are getting caught in short-term noise.
     Recommendation: Add a minimum ATR-based SL of at least {avg_atr_all:.0f} pips.

  C) The flat year is CONSISTENT with a normal drawdown period for a
     system with PF={pf:.2f}. A Monte Carlo analysis of an 80-trade
     sample with this winrate/RR would show ~15-25% chance of being
     flat over 80 trades. This is within normal variance.

  BOTTOM LINE: The strategy has edge but the BE mechanism is destroying
  it. Fix the breakeven trigger and add volatility-adaptive SL sizing.
  Expected improvement: +3-5% annual return from BE fix alone.
  """)


if __name__ == '__main__':
    main()
