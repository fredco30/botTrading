"""
Analyse des trades EMA_Pullback_pyramid sur 16 ans (2010-2026)
Objectif : comprendre pourquoi 2010-2019 est négatif
"""
import re
from collections import defaultdict

def parse_trades(filepath):
    trades = []
    pending = {}

    with open(filepath, 'r') as f:
        for line in f:
            parts = line.strip().split('\t')
            if len(parts) < 10:
                continue

            # Format: idx \t "date time" \t action \t ticket \t lot \t price \t sl \t tp \t profit \t balance
            row_num = int(parts[0])
            datetime_parts = parts[1].split(' ')
            date_str = datetime_parts[0]
            time_str = datetime_parts[1] if len(datetime_parts) > 1 else ""
            action = parts[2]
            ticket = int(parts[3])
            lot = float(parts[4])
            price = float(parts[5])
            sl = float(parts[6])
            tp = float(parts[7])
            profit = float(parts[8])
            balance = float(parts[9])

            year = int(date_str.split('.')[0])

            if action in ('buy', 'sell'):
                pending[ticket] = {
                    'ticket': ticket,
                    'type': action,
                    'lot': lot,
                    'open_price': price,
                    'open_date': date_str,
                    'open_time': time_str,
                    'year': year,
                    'sl': sl,
                    'tp': tp,
                }
            elif action in ('t/p', 's/l', 'close'):
                if ticket in pending:
                    t = pending[ticket]
                    t['close_date'] = date_str
                    t['close_time'] = time_str
                    t['close_action'] = action
                    t['profit'] = profit
                    t['balance'] = balance
                    t['close_year'] = year
                    trades.append(t)
                    del pending[ticket]

    return trades

def classify_levels(trades):
    """Classify trades into L0/L1/L2 based on lot size patterns"""
    # The pyramid multiplies base lot: L0=1x, L1=4x, L2=2.5x
    # We can detect level by comparing lot to estimated base lot
    streak = 0
    for t in trades:
        if streak == 0:
            t['level'] = 'L0'
        elif streak == 1:
            t['level'] = 'L1'
        else:
            t['level'] = 'L2'

        if t['profit'] > 0:
            streak = min(streak + 1, 2)
        else:
            streak = 0

def analyze(filepath='resultats_martingale_EMAPullback16ans.txt'):
    trades = parse_trades(filepath)
    print(f"Fichier: {filepath}")
    classify_levels(trades)

    print(f"Total trades: {len(trades)}")
    print(f"Balance finale: ${trades[-1]['balance']:.2f}" if trades else "No trades")
    print()

    # Per year analysis
    years = defaultdict(lambda: {'trades': [], 'wins': 0, 'losses': 0, 'profit': 0.0,
                                  'gross_win': 0.0, 'gross_loss': 0.0})

    for t in trades:
        y = t['year']
        years[y]['trades'].append(t)
        years[y]['profit'] += t['profit']
        if t['profit'] > 0:
            years[y]['wins'] += 1
            years[y]['gross_win'] += t['profit']
        else:
            years[y]['losses'] += 1
            years[y]['gross_loss'] += abs(t['profit'])

    print("=" * 90)
    print(f"{'Year':<6} {'Trades':>7} {'Wins':>5} {'WR%':>6} {'Net $':>10} {'Gross W':>10} {'Gross L':>10} {'PF':>6}")
    print("=" * 90)

    cumul = 0
    for y in sorted(years.keys()):
        d = years[y]
        n = len(d['trades'])
        wr = d['wins'] / n * 100 if n > 0 else 0
        pf = d['gross_win'] / d['gross_loss'] if d['gross_loss'] > 0 else 999
        cumul += d['profit']
        print(f"{y:<6} {n:>7} {d['wins']:>5} {wr:>5.1f}% {d['profit']:>+10.2f} {d['gross_win']:>10.2f} {d['gross_loss']:>10.2f} {pf:>6.2f}  cumul: {cumul:>+10.2f}")

    # Per level analysis
    print("\n" + "=" * 90)
    print("ANALYSE PAR NIVEAU (L0/L1/L2)")
    print("=" * 90)

    levels = defaultdict(lambda: {'n': 0, 'wins': 0, 'profit': 0.0, 'gross_win': 0.0, 'gross_loss': 0.0})
    for t in trades:
        lv = t['level']
        levels[lv]['n'] += 1
        levels[lv]['profit'] += t['profit']
        if t['profit'] > 0:
            levels[lv]['wins'] += 1
            levels[lv]['gross_win'] += t['profit']
        else:
            levels[lv]['gross_loss'] += abs(t['profit'])

    print(f"{'Level':<6} {'N':>5} {'WR%':>6} {'Net $':>10} {'PF':>6}")
    for lv in ['L0', 'L1', 'L2']:
        d = levels[lv]
        wr = d['wins'] / d['n'] * 100 if d['n'] > 0 else 0
        pf = d['gross_win'] / d['gross_loss'] if d['gross_loss'] > 0 else 999
        print(f"{lv:<6} {d['n']:>5} {wr:>5.1f}% {d['profit']:>+10.2f} {pf:>6.2f}")

    # Per level per period
    print("\n" + "=" * 90)
    print("NIVEAUX PAR PÉRIODE")
    print("=" * 90)

    for period_name, y_range in [("2010-2019", range(2010, 2020)), ("2020-2026", range(2020, 2027))]:
        print(f"\n--- {period_name} ---")
        period_levels = defaultdict(lambda: {'n': 0, 'wins': 0, 'profit': 0.0, 'gross_win': 0.0, 'gross_loss': 0.0})
        period_trades = [t for t in trades if t['year'] in y_range]

        for t in period_trades:
            lv = t['level']
            period_levels[lv]['n'] += 1
            period_levels[lv]['profit'] += t['profit']
            if t['profit'] > 0:
                period_levels[lv]['wins'] += 1
                period_levels[lv]['gross_win'] += t['profit']
            else:
                period_levels[lv]['gross_loss'] += abs(t['profit'])

        total_n = len(period_trades)
        total_wins = sum(1 for t in period_trades if t['profit'] > 0)
        total_profit = sum(t['profit'] for t in period_trades)
        print(f"Total: {total_n} trades, WR {total_wins/total_n*100:.1f}%, Net {total_profit:+.2f}")

        print(f"{'Level':<6} {'N':>5} {'WR%':>6} {'Net $':>10} {'PF':>6}")
        for lv in ['L0', 'L1', 'L2']:
            d = period_levels[lv]
            if d['n'] == 0:
                continue
            wr = d['wins'] / d['n'] * 100
            pf = d['gross_win'] / d['gross_loss'] if d['gross_loss'] > 0 else 999
            print(f"{lv:<6} {d['n']:>5} {wr:>5.1f}% {d['profit']:>+10.2f} {pf:>6.2f}")

    # Analyse des SL distances et durée des trades
    print("\n" + "=" * 90)
    print("ANALYSE SL DISTANCE PAR PÉRIODE")
    print("=" * 90)

    for period_name, y_range in [("2010-2019", range(2010, 2020)), ("2020-2026", range(2020, 2027))]:
        period_trades = [t for t in trades if t['year'] in y_range]
        sl_dists = []
        for t in period_trades:
            if t['type'] == 'buy':
                sl_dist = abs(t['open_price'] - t['sl']) * 10000  # pips
            else:
                sl_dist = abs(t['sl'] - t['open_price']) * 10000
            sl_dists.append(sl_dist)

        if sl_dists:
            avg_sl = sum(sl_dists) / len(sl_dists)
            min_sl = min(sl_dists)
            max_sl = max(sl_dists)
            print(f"{period_name}: SL avg={avg_sl:.1f} pips, min={min_sl:.1f}, max={max_sl:.1f}")

    # Win streaks analysis
    print("\n" + "=" * 90)
    print("STREAKS CONSÉCUTIFS (wins consécutifs avant L1)")
    print("=" * 90)

    for period_name, y_range in [("2010-2019", range(2010, 2020)), ("2020-2026", range(2020, 2027))]:
        period_trades = [t for t in trades if t['year'] in y_range]

        # Count L1 trades and their WR
        l1_trades = [t for t in period_trades if t['level'] == 'L1']
        l1_wins = sum(1 for t in l1_trades if t['profit'] > 0)
        l1_wr = l1_wins / len(l1_trades) * 100 if l1_trades else 0

        # Count consecutive win streaks
        streaks = []
        current_streak = 0
        for t in period_trades:
            if t['profit'] > 0:
                current_streak += 1
            else:
                if current_streak > 0:
                    streaks.append(current_streak)
                current_streak = 0
        if current_streak > 0:
            streaks.append(current_streak)

        avg_streak = sum(streaks) / len(streaks) if streaks else 0
        max_streak = max(streaks) if streaks else 0
        streak_1plus = sum(1 for s in streaks if s >= 2)  # at least 2 wins = L1 triggered

        print(f"{period_name}:")
        print(f"  L1 trades: {len(l1_trades)}, L1 WR: {l1_wr:.1f}%")
        print(f"  Win streaks: avg={avg_streak:.1f}, max={max_streak}")
        print(f"  Streaks >=2 (L1 triggered): {streak_1plus}/{len(streaks)} ({streak_1plus/len(streaks)*100:.0f}%)" if streaks else "  No streaks")

    # Trades per month density
    print("\n" + "=" * 90)
    print("DENSITÉ DE TRADES (par mois)")
    print("=" * 90)
    for period_name, y_range in [("2010-2019", range(2010, 2020)), ("2020-2026", range(2020, 2027))]:
        period_trades = [t for t in trades if t['year'] in y_range]
        n_months = len(y_range) * 12
        print(f"{period_name}: {len(period_trades)} trades / {n_months} mois = {len(period_trades)/n_months:.1f} trades/mois")

if __name__ == '__main__':
    import sys
    filepath = sys.argv[1] if len(sys.argv) > 1 else 'resultats_martingale_EMAPullback16ans.txt'
    analyze(filepath)
