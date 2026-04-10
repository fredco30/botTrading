"""
Analyse approfondie : qu'est-ce qui différencie les trades 2010-2019 vs 2020-2026 ?
On cherche des patterns exploitables pour filtrer.
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
            month = int(date_str.split('.')[1])
            day = int(date_str.split('.')[2])
            hour = int(time_str.split(':')[0]) if time_str else 0

            if action in ('buy', 'sell'):
                pending[ticket] = {
                    'ticket': ticket, 'type': action, 'lot': lot,
                    'open_price': price, 'open_date': date_str,
                    'open_time': time_str, 'year': year, 'month': month,
                    'day_of_week': None, 'hour': hour,
                    'sl_price_initial': sl, 'tp_price': tp,
                    'sl_price': sl,
                }
            elif action == 'modify' and ticket in pending:
                pending[ticket]['sl_price'] = sl
                pending[ticket]['tp_price'] = tp
                # Keep initial SL untouched
            elif action in ('t/p', 's/l', 'close'):
                if ticket in pending:
                    t = pending[ticket]
                    t['close_action'] = action
                    t['profit'] = profit
                    t['balance'] = balance
                    t['close_price'] = price
                    # SL distance in pips (use INITIAL SL, not modified BE)
                    if t['type'] == 'buy':
                        t['sl_pips'] = abs(t['open_price'] - t['sl_price_initial']) * 10000
                    else:
                        t['sl_pips'] = abs(t['sl_price_initial'] - t['open_price']) * 10000
                    trades.append(t)
                    del pending[ticket]
    # Classify levels
    streak = 0
    for t in trades:
        t['level'] = 'L0' if streak == 0 else ('L1' if streak == 1 else 'L2')
        if t['profit'] > 0:
            streak = min(streak + 1, 2)
        else:
            streak = 0
    return trades

def analyze(filepath):
    trades = parse_trades(filepath)
    print(f"Fichier: {filepath}")
    print(f"Total trades: {len(trades)}")

    # ============================================================
    # 1. ANALYSE PAR HEURE - 2010-2019 vs 2020-2026
    # ============================================================
    print("\n" + "=" * 100)
    print("ANALYSE PAR HEURE D'ENTREE")
    print("=" * 100)

    for period_name, y_range in [("2010-2019", range(2010, 2020)), ("2020-2026", range(2020, 2027))]:
        print(f"\n--- {period_name} ---")
        hours = defaultdict(lambda: {'n': 0, 'wins': 0, 'profit': 0.0, 'gw': 0.0, 'gl': 0.0})
        for t in [x for x in trades if x['year'] in y_range]:
            h = t['hour']
            hours[h]['n'] += 1
            hours[h]['profit'] += t['profit']
            if t['profit'] > 0:
                hours[h]['wins'] += 1
                hours[h]['gw'] += t['profit']
            else:
                hours[h]['gl'] += abs(t['profit'])

        print(f"{'Hour':<6} {'N':>4} {'WR%':>6} {'Net $':>10} {'PF':>6}")
        for h in sorted(hours.keys()):
            d = hours[h]
            wr = d['wins'] / d['n'] * 100 if d['n'] > 0 else 0
            pf = d['gw'] / d['gl'] if d['gl'] > 0 else 999
            marker = " ***" if d['n'] >= 5 and pf < 0.7 else ""
            print(f"{h:>4}h  {d['n']:>4} {wr:>5.1f}% {d['profit']:>+10.2f} {pf:>6.2f}{marker}")

    # ============================================================
    # 2. ANALYSE PAR MOIS DE L'ANNEE
    # ============================================================
    print("\n" + "=" * 100)
    print("ANALYSE PAR MOIS DE L'ANNEE")
    print("=" * 100)

    for period_name, y_range in [("2010-2019", range(2010, 2020)), ("2020-2026", range(2020, 2027))]:
        print(f"\n--- {period_name} ---")
        months = defaultdict(lambda: {'n': 0, 'wins': 0, 'profit': 0.0, 'gw': 0.0, 'gl': 0.0})
        for t in [x for x in trades if x['year'] in y_range]:
            m = t['month']
            months[m]['n'] += 1
            months[m]['profit'] += t['profit']
            if t['profit'] > 0:
                months[m]['wins'] += 1
                months[m]['gw'] += t['profit']
            else:
                months[m]['gl'] += abs(t['profit'])

        print(f"{'Month':<6} {'N':>4} {'WR%':>6} {'Net $':>10} {'PF':>6}")
        month_names = ['', 'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                       'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
        for m in sorted(months.keys()):
            d = months[m]
            wr = d['wins'] / d['n'] * 100 if d['n'] > 0 else 0
            pf = d['gw'] / d['gl'] if d['gl'] > 0 else 999
            marker = " ***" if d['n'] >= 5 and pf < 0.7 else ""
            print(f"{month_names[m]:<6} {d['n']:>4} {wr:>5.1f}% {d['profit']:>+10.2f} {pf:>6.2f}{marker}")

    # ============================================================
    # 3. ANALYSE PAR SL DISTANCE (buckets)
    # ============================================================
    print("\n" + "=" * 100)
    print("ANALYSE PAR SL DISTANCE (pips)")
    print("=" * 100)

    for period_name, y_range in [("2010-2019", range(2010, 2020)), ("2020-2026", range(2020, 2027))]:
        print(f"\n--- {period_name} ---")
        buckets = defaultdict(lambda: {'n': 0, 'wins': 0, 'profit': 0.0, 'gw': 0.0, 'gl': 0.0})
        for t in [x for x in trades if x['year'] in y_range]:
            sl = t['sl_pips']
            if sl < 17:
                b = '15-17'
            elif sl < 19:
                b = '17-19'
            elif sl < 21:
                b = '19-21'
            elif sl < 23:
                b = '21-23'
            else:
                b = '23-25'
            buckets[b]['n'] += 1
            buckets[b]['profit'] += t['profit']
            if t['profit'] > 0:
                buckets[b]['wins'] += 1
                buckets[b]['gw'] += t['profit']
            else:
                buckets[b]['gl'] += abs(t['profit'])

        print(f"{'SL':>6} {'N':>4} {'WR%':>6} {'Net $':>10} {'PF':>6}")
        for b in ['15-17', '17-19', '19-21', '21-23', '23-25']:
            d = buckets[b]
            if d['n'] == 0: continue
            wr = d['wins'] / d['n'] * 100
            pf = d['gw'] / d['gl'] if d['gl'] > 0 else 999
            print(f"{b:>6} {d['n']:>4} {wr:>5.1f}% {d['profit']:>+10.2f} {pf:>6.2f}")

    # ============================================================
    # 4. ANALYSE BUY vs SELL
    # ============================================================
    print("\n" + "=" * 100)
    print("ANALYSE BUY vs SELL")
    print("=" * 100)

    for period_name, y_range in [("2010-2019", range(2010, 2020)), ("2020-2026", range(2020, 2027))]:
        print(f"\n--- {period_name} ---")
        for direction in ['buy', 'sell']:
            dt = [t for t in trades if t['year'] in y_range and t['type'] == direction]
            if not dt: continue
            wins = sum(1 for t in dt if t['profit'] > 0)
            gw = sum(t['profit'] for t in dt if t['profit'] > 0)
            gl = sum(abs(t['profit']) for t in dt if t['profit'] <= 0)
            pf = gw / gl if gl > 0 else 999
            print(f"  {direction.upper()}: {len(dt)} trades, WR {wins/len(dt)*100:.1f}%, Net {sum(t['profit'] for t in dt):+.2f}, PF {pf:.2f}")

    # ============================================================
    # 5. ANALYSE TRADE DURATION (rapide vs lent)
    # ============================================================
    print("\n" + "=" * 100)
    print("ANALYSE WIN vs LOSS - CLOSE TYPE (TP vs SL vs BE)")
    print("=" * 100)

    for period_name, y_range in [("2010-2019", range(2010, 2020)), ("2020-2026", range(2020, 2027))]:
        print(f"\n--- {period_name} ---")
        close_types = defaultdict(lambda: {'n': 0, 'profit': 0.0})
        for t in [x for x in trades if x['year'] in y_range]:
            ct = t['close_action']
            # Detect BE (SL hit but profit ~0 or tiny positive)
            if ct == 's/l' and t['profit'] > 0 and t['profit'] < t['lot'] * 20:
                ct = 'BE'
            close_types[ct]['n'] += 1
            close_types[ct]['profit'] += t['profit']

        for ct in ['t/p', 's/l', 'BE']:
            d = close_types[ct]
            if d['n'] == 0: continue
            print(f"  {ct}: {d['n']} trades, Net {d['profit']:+.2f}, Avg {d['profit']/d['n']:+.2f}")

    # ============================================================
    # 6. ANALYSE CONSECUTIVE PATTERNS (L0 win rate after N losses)
    # ============================================================
    print("\n" + "=" * 100)
    print("L0 WIN RATE APRES N PERTES CONSECUTIVES")
    print("=" * 100)

    for period_name, y_range in [("2010-2019", range(2010, 2020)), ("2020-2026", range(2020, 2027))]:
        print(f"\n--- {period_name} ---")
        period_trades = [t for t in trades if t['year'] in y_range]
        loss_streak = 0
        loss_bins = defaultdict(lambda: {'n': 0, 'wins': 0})
        for t in period_trades:
            if t['level'] == 'L0':
                bin_key = min(loss_streak, 5)  # cap at 5+
                loss_bins[bin_key]['n'] += 1
                if t['profit'] > 0:
                    loss_bins[bin_key]['wins'] += 1
            if t['profit'] > 0:
                loss_streak = 0
            else:
                loss_streak += 1

        print(f"{'After N losses':<16} {'N':>4} {'WR%':>6}")
        for n in sorted(loss_bins.keys()):
            d = loss_bins[n]
            wr = d['wins'] / d['n'] * 100 if d['n'] > 0 else 0
            label = f"{n} losses" if n < 5 else "5+ losses"
            print(f"  {label:<14} {d['n']:>4} {wr:>5.1f}%")

    # ============================================================
    # 7. PROFIT MOYEN PAR TRADE WIN/LOSS (RR effectif)
    # ============================================================
    print("\n" + "=" * 100)
    print("RR EFFECTIF (avg win / avg loss)")
    print("=" * 100)

    for period_name, y_range in [("2010-2019", range(2010, 2020)), ("2020-2026", range(2020, 2027))]:
        period_trades = [t for t in trades if t['year'] in y_range and t['level'] == 'L0']
        wins = [t for t in period_trades if t['profit'] > 0]
        losses = [t for t in period_trades if t['profit'] < 0]
        bes = [t for t in period_trades if t['profit'] >= 0 and t['profit'] < 5]

        if wins and losses:
            avg_win = sum(t['profit'] for t in wins) / len(wins)
            avg_loss = sum(abs(t['profit']) for t in losses) / len(losses)
            rr = avg_win / avg_loss
            print(f"{period_name} L0: avg_win={avg_win:.2f}, avg_loss={avg_loss:.2f}, RR={rr:.2f}, BE_trades={len(bes)}")

if __name__ == '__main__':
    import sys
    filepath = sys.argv[1] if len(sys.argv) > 1 else 'resultats_martingale_EMAPullback16ans.txt'
    analyze(filepath)
