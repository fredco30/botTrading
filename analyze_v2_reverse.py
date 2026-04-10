"""
Analyse V2 : identifier les trades REVERSE vs NORMAL
Un reverse = trade ouvert juste apres un SL, dans le sens oppose, sans nouveau signal.
Detection : meme jour ou jour suivant, direction inversee, apres un s/l.
"""
import sys
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
            hour = int(time_str.split(':')[0]) if ':' in time_str else 0
            minute = int(time_str.split(':')[1]) if ':' in time_str else 0

            if action in ('buy', 'sell'):
                pending[ticket] = {
                    'ticket': ticket, 'type': action, 'lot': lot,
                    'open_price': price, 'open_date': date_str,
                    'open_time': time_str, 'year': year, 'month': month,
                    'hour': hour, 'minute': minute,
                    'sl_price_initial': sl, 'tp_price': tp,
                    'open_minutes': year * 525600 + month * 43200 + day * 1440 + hour * 60 + minute,
                }
            elif action == 'modify' and ticket in pending:
                pass  # ignore modifies for this analysis
            elif action in ('t/p', 's/l', 'close'):
                if ticket in pending:
                    t = pending[ticket]
                    t['close_action'] = action
                    t['profit'] = profit
                    t['balance'] = balance
                    t['close_date'] = date_str
                    t['close_time'] = time_str
                    close_hour = int(time_str.split(':')[0]) if ':' in time_str else 0
                    close_minute = int(time_str.split(':')[1]) if ':' in time_str else 0
                    close_year = int(date_str.split('.')[0])
                    close_month = int(date_str.split('.')[1])
                    close_day = int(date_str.split('.')[2])
                    t['close_minutes'] = close_year * 525600 + close_month * 43200 + close_day * 1440 + close_hour * 60 + close_minute
                    # SL distance in pips
                    if t['type'] == 'buy':
                        t['sl_pips'] = abs(t['open_price'] - t['sl_price_initial']) * 10000
                    else:
                        t['sl_pips'] = abs(t['sl_price_initial'] - t['open_price']) * 10000
                    trades.append(t)
                    del pending[ticket]
    return trades

def detect_reverses(trades):
    """Detect reverse trades: opened just after a SL, in opposite direction"""
    for i, t in enumerate(trades):
        t['is_reverse'] = False
        if i == 0:
            continue
        prev = trades[i - 1]
        # Reverse conditions:
        # 1. Previous trade was a SL (or BE that's basically SL)
        # 2. Current trade opens very shortly after previous close (< 120 min)
        # 3. Current trade is in OPPOSITE direction
        if prev['close_action'] == 's/l' and prev['profit'] <= 0:
            time_diff = t['open_minutes'] - prev['close_minutes']
            if 0 <= time_diff <= 120:  # within 2 hours
                if t['type'] != prev['type']:  # opposite direction
                    t['is_reverse'] = True

def analyze(filepath):
    trades = parse_trades(filepath)
    detect_reverses(trades)

    reverses = [t for t in trades if t['is_reverse']]
    normals = [t for t in trades if not t['is_reverse']]

    print(f"Fichier: {filepath}")
    print(f"Total: {len(trades)} trades | Normaux: {len(normals)} | Reverses: {len(reverses)}")

    # === REVERSE STATS ===
    print("\n" + "=" * 90)
    print("TRADES REVERSE (isoles)")
    print("=" * 90)

    for period_name, y_range in [("GLOBAL", range(2000, 2030)), ("2010-2019", range(2010, 2020)), ("2020-2026", range(2020, 2027))]:
        rt = [t for t in reverses if t['year'] in y_range]
        if not rt:
            continue
        wins = sum(1 for t in rt if t['profit'] > 0)
        gw = sum(t['profit'] for t in rt if t['profit'] > 0)
        gl = sum(abs(t['profit']) for t in rt if t['profit'] <= 0)
        net = sum(t['profit'] for t in rt)
        pf = gw / gl if gl > 0 else 999
        wr = wins / len(rt) * 100
        avg_sl = sum(t['sl_pips'] for t in rt) / len(rt) if rt else 0
        print(f"\n{period_name}: {len(rt)} trades, WR {wr:.1f}%, Net {net:+.2f}, PF {pf:.2f}, Avg SL {avg_sl:.1f} pips")

        # By close type
        tp_trades = [t for t in rt if t['close_action'] == 't/p']
        sl_trades = [t for t in rt if t['close_action'] == 's/l' and t['profit'] <= 0]
        be_trades = [t for t in rt if t['close_action'] == 's/l' and t['profit'] > 0]
        print(f"  TP: {len(tp_trades)}, SL: {len(sl_trades)}, BE: {len(be_trades)}")

        if wins > 0 and (len(rt) - wins) > 0:
            avg_win = gw / wins
            avg_loss = gl / (len(rt) - wins) if (len(rt) - wins) > 0 else 0
            rr = avg_win / avg_loss if avg_loss > 0 else 999
            print(f"  Avg win: {avg_win:.2f}, Avg loss: {avg_loss:.2f}, RR effectif: {rr:.2f}")

    # === NORMAL STATS (sans reverses) ===
    print("\n" + "=" * 90)
    print("TRADES NORMAUX (sans reverses) — pour comparaison avec V1")
    print("=" * 90)

    # Classify levels on normals only
    streak = 0
    for t in normals:
        t['level'] = 'L0' if streak == 0 else ('L1' if streak == 1 else 'L2')
        if t['profit'] > 0:
            streak = min(streak + 1, 2)
        else:
            streak = 0

    for period_name, y_range in [("GLOBAL", range(2000, 2030)), ("2010-2019", range(2010, 2020)), ("2020-2026", range(2020, 2027))]:
        pt = [t for t in normals if t['year'] in y_range]
        if not pt:
            continue
        wins = sum(1 for t in pt if t['profit'] > 0)
        net = sum(t['profit'] for t in pt)
        gw = sum(t['profit'] for t in pt if t['profit'] > 0)
        gl = sum(abs(t['profit']) for t in pt if t['profit'] <= 0)
        pf = gw / gl if gl > 0 else 999

        print(f"\n{period_name}: {len(pt)} trades, WR {wins/len(pt)*100:.1f}%, Net {net:+.2f}, PF {pf:.2f}")

        levels = defaultdict(lambda: {'n': 0, 'wins': 0, 'profit': 0.0, 'gw': 0.0, 'gl': 0.0})
        for t in pt:
            lv = t['level']
            levels[lv]['n'] += 1
            levels[lv]['profit'] += t['profit']
            if t['profit'] > 0:
                levels[lv]['wins'] += 1
                levels[lv]['gw'] += t['profit']
            else:
                levels[lv]['gl'] += abs(t['profit'])

        print(f"  {'Level':<6} {'N':>5} {'WR%':>6} {'Net $':>10} {'PF':>6}")
        for lv in ['L0', 'L1', 'L2']:
            d = levels[lv]
            if d['n'] == 0: continue
            wr = d['wins'] / d['n'] * 100
            pf = d['gw'] / d['gl'] if d['gl'] > 0 else 999
            print(f"  {lv:<6} {d['n']:>5} {wr:>5.1f}% {d['profit']:>+10.2f} {pf:>6.2f}")

    # === REVERSE PAR ANNEE ===
    print("\n" + "=" * 90)
    print("REVERSE PAR ANNEE")
    print("=" * 90)
    years = sorted(set(t['year'] for t in reverses))
    print(f"{'Year':<6} {'N':>4} {'WR%':>6} {'Net $':>10} {'PF':>6}")
    for y in years:
        yt = [t for t in reverses if t['year'] == y]
        wins = sum(1 for t in yt if t['profit'] > 0)
        gw = sum(t['profit'] for t in yt if t['profit'] > 0)
        gl = sum(abs(t['profit']) for t in yt if t['profit'] <= 0)
        net = sum(t['profit'] for t in yt)
        pf = gw / gl if gl > 0 else 999
        wr = wins / len(yt) * 100
        print(f"{y:<6} {len(yt):>4} {wr:>5.1f}% {net:>+10.2f} {pf:>6.2f}")

    # === REVERSE APRES QUEL NIVEAU ===
    print("\n" + "=" * 90)
    print("REVERSE : APRES QUEL TRADE (L0 loss vs L2 loss)")
    print("=" * 90)

    # Re-detect with level info
    streak = 0
    all_trades_with_level = []
    for t in trades:
        if not t['is_reverse']:
            t['trade_level'] = 'L0' if streak == 0 else ('L1' if streak == 1 else 'L2')
            if t['profit'] > 0:
                streak = min(streak + 1, 2)
            else:
                streak = 0
        else:
            t['trade_level'] = 'REV'
        all_trades_with_level.append(t)

    # For each reverse, find what level preceded it
    for i, t in enumerate(all_trades_with_level):
        if t['is_reverse'] and i > 0:
            prev = all_trades_with_level[i - 1]
            t['rev_after'] = prev.get('trade_level', '?')

    rev_after_l0 = [t for t in reverses if t.get('rev_after') == 'L0']
    rev_after_l1 = [t for t in reverses if t.get('rev_after') == 'L1']
    rev_after_l2 = [t for t in reverses if t.get('rev_after') == 'L2']
    rev_after_other = [t for t in reverses if t.get('rev_after') not in ('L0', 'L1', 'L2')]

    for label, group in [("After L0 loss", rev_after_l0), ("After L1 loss", rev_after_l1),
                          ("After L2 loss", rev_after_l2), ("After other", rev_after_other)]:
        if not group: continue
        wins = sum(1 for t in group if t['profit'] > 0)
        net = sum(t['profit'] for t in group)
        gw = sum(t['profit'] for t in group if t['profit'] > 0)
        gl = sum(abs(t['profit']) for t in group if t['profit'] <= 0)
        pf = gw / gl if gl > 0 else 999
        print(f"  {label}: {len(group)} trades, WR {wins/len(group)*100:.1f}%, Net {net:+.2f}, PF {pf:.2f}")

if __name__ == '__main__':
    filepath = sys.argv[1] if len(sys.argv) > 1 else 'resultats_regime_pyramidV2-16ans_agressif_v1.txt'
    analyze(filepath)
