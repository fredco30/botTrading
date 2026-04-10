"""
Analyse V2 : le reverse comme amortisseur de DD
Questions :
1. Le reverse reduit-il le DD effectif ?
2. Le reverse est-il meilleur apres N pertes consecutives ?
3. Quel lot optimal pour le reverse (0.5x, 1.0x, 1.5x) ?
4. Simulation : equity curve avec/sans reverse
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
                    'hour': hour,
                    'sl_price_initial': sl, 'tp_price': tp,
                    'open_minutes': year * 525600 + month * 43200 + day * 1440 + hour * 60 + minute,
                }
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
                    if t['type'] == 'buy':
                        t['sl_pips'] = abs(t['open_price'] - t['sl_price_initial']) * 10000
                    else:
                        t['sl_pips'] = abs(t['sl_price_initial'] - t['open_price']) * 10000
                    trades.append(t)
                    del pending[ticket]
    return trades

def detect_reverses(trades):
    for i, t in enumerate(trades):
        t['is_reverse'] = False
        if i == 0:
            continue
        prev = trades[i - 1]
        if prev['close_action'] == 's/l' and prev['profit'] <= 0:
            time_diff = t['open_minutes'] - prev['close_minutes']
            if 0 <= time_diff <= 120:
                if t['type'] != prev['type']:
                    t['is_reverse'] = True

def assign_levels(trades):
    """Assign pyramid levels, skipping reverses for streak counting"""
    streak = 0
    for t in trades:
        if t['is_reverse']:
            t['level'] = 'REV'
            continue
        t['level'] = 'L0' if streak == 0 else ('L1' if streak == 1 else 'L2')
        if t['profit'] > 0:
            streak = min(streak + 1, 2)
        else:
            streak = 0

def analyze(filepath):
    trades = parse_trades(filepath)
    detect_reverses(trades)
    assign_levels(trades)

    normals = [t for t in trades if not t['is_reverse']]
    reverses = [t for t in trades if t['is_reverse']]

    print(f"Fichier: {filepath}")
    print(f"Total: {len(trades)} | Normaux: {len(normals)} | Reverses: {len(reverses)}")

    # ============================================================
    # 1. EQUITY CURVE : avec vs sans reverse
    # ============================================================
    print("\n" + "=" * 90)
    print("EQUITY CURVE : AVEC vs SANS REVERSE")
    print("=" * 90)

    # With reverse (actual)
    equity_with = 10000.0
    max_equity_with = equity_with
    max_dd_with = 0.0
    dd_episodes_with = []

    # Without reverse (simulated - remove reverse trades)
    equity_without = 10000.0
    max_equity_without = equity_without
    max_dd_without = 0.0

    for t in trades:
        equity_with += t['profit']
        max_equity_with = max(max_equity_with, equity_with)
        dd = (max_equity_with - equity_with) / max_equity_with * 100
        max_dd_with = max(max_dd_with, dd)

        if not t['is_reverse']:
            equity_without += t['profit']
            max_equity_without = max(max_equity_without, equity_without)
            dd_no = (max_equity_without - equity_without) / max_equity_without * 100
            max_dd_without = max(max_dd_without, dd_no)

    print(f"AVEC reverse:  Final ${equity_with:.2f}, DD max {max_dd_with:.1f}%")
    print(f"SANS reverse:  Final ${equity_without:.2f}, DD max {max_dd_without:.1f}%")
    print(f"Delta:         ${equity_with - equity_without:+.2f}, DD {max_dd_with - max_dd_without:+.1f}%")

    # Per period
    for period_name, y_range in [("2010-2019", range(2010, 2020)), ("2020-2026", range(2020, 2027))]:
        pt = [t for t in trades if t['year'] in y_range]
        eq_w = 10000.0
        eq_wo = 10000.0
        max_w = eq_w
        max_wo = eq_wo
        dd_w = 0.0
        dd_wo = 0.0

        for t in pt:
            eq_w += t['profit']
            max_w = max(max_w, eq_w)
            dd_w = max(dd_w, (max_w - eq_w) / max_w * 100)

            if not t['is_reverse']:
                eq_wo += t['profit']
                max_wo = max(max_wo, eq_wo)
                dd_wo = max(dd_wo, (max_wo - eq_wo) / max_wo * 100)

        rev_profit = sum(t['profit'] for t in pt if t['is_reverse'])
        print(f"\n{period_name}:")
        print(f"  AVEC reverse:  DD max {dd_w:.1f}%, reverses net {rev_profit:+.2f}")
        print(f"  SANS reverse:  DD max {dd_wo:.1f}%")
        print(f"  DD reduction:  {dd_wo - dd_w:+.1f}%")

    # ============================================================
    # 2. REVERSE APRES N PERTES CONSECUTIVES
    # ============================================================
    print("\n" + "=" * 90)
    print("REVERSE : PERFORMANCE APRES N PERTES CONSECUTIVES (normales)")
    print("=" * 90)

    # Count consecutive normal losses before each reverse
    consec_losses = 0
    for i, t in enumerate(trades):
        if t['is_reverse']:
            t['consec_losses_before'] = consec_losses
            # Don't reset consec_losses — the reverse doesn't count
        else:
            if t['profit'] <= 0:
                consec_losses += 1
            else:
                consec_losses = 0
            t['consec_losses_before'] = consec_losses

    # Bucket reverses by consec losses before them
    bins = defaultdict(lambda: {'n': 0, 'wins': 0, 'profit': 0.0, 'gw': 0.0, 'gl': 0.0})
    for t in reverses:
        n = min(t.get('consec_losses_before', 0), 5)
        bins[n]['n'] += 1
        bins[n]['profit'] += t['profit']
        if t['profit'] > 0:
            bins[n]['wins'] += 1
            bins[n]['gw'] += t['profit']
        else:
            bins[n]['gl'] += abs(t['profit'])

    print(f"{'After N losses':<18} {'N':>4} {'WR%':>6} {'Net $':>10} {'PF':>6}")
    for n in sorted(bins.keys()):
        d = bins[n]
        wr = d['wins'] / d['n'] * 100 if d['n'] > 0 else 0
        pf = d['gw'] / d['gl'] if d['gl'] > 0 else 999
        label = f"{n} losses" if n < 5 else "5+ losses"
        print(f"  {label:<16} {d['n']:>4} {wr:>5.1f}% {d['profit']:>+10.2f} {pf:>6.2f}")

    # ============================================================
    # 3. REVERSE : BUY vs SELL
    # ============================================================
    print("\n" + "=" * 90)
    print("REVERSE : BUY vs SELL (direction du reverse)")
    print("=" * 90)

    for direction in ['buy', 'sell']:
        dt = [t for t in reverses if t['type'] == direction]
        if not dt: continue
        wins = sum(1 for t in dt if t['profit'] > 0)
        gw = sum(t['profit'] for t in dt if t['profit'] > 0)
        gl = sum(abs(t['profit']) for t in dt if t['profit'] <= 0)
        net = sum(t['profit'] for t in dt)
        pf = gw / gl if gl > 0 else 999
        print(f"  {direction.upper()}: {len(dt)} trades, WR {wins/len(dt)*100:.1f}%, Net {net:+.2f}, PF {pf:.2f}")

    # ============================================================
    # 4. SIMULATION : reverse avec lot reduit (0.5x)
    # ============================================================
    print("\n" + "=" * 90)
    print("SIMULATION : REVERSE LOT SCALING")
    print("=" * 90)

    for mult in [0.25, 0.5, 0.75, 1.0, 1.5]:
        eq = 10000.0
        max_eq = eq
        max_dd = 0.0

        for t in trades:
            if t['is_reverse']:
                eq += t['profit'] * mult
            else:
                eq += t['profit']
            max_eq = max(max_eq, eq)
            dd = (max_eq - eq) / max_eq * 100
            max_dd = max(max_dd, dd)

        rev_net = sum(t['profit'] * mult for t in reverses)
        norm_net = sum(t['profit'] for t in normals)
        print(f"  RevLot {mult:.2f}x: Final ${eq:.2f}, DD max {max_dd:.1f}%, Rev net {rev_net:+.2f}")

    # ============================================================
    # 5. REVERSE PAR HEURE
    # ============================================================
    print("\n" + "=" * 90)
    print("REVERSE PAR HEURE D'OUVERTURE")
    print("=" * 90)

    hours = defaultdict(lambda: {'n': 0, 'wins': 0, 'profit': 0.0, 'gw': 0.0, 'gl': 0.0})
    for t in reverses:
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
        print(f"{h:>4}h  {d['n']:>4} {wr:>5.1f}% {d['profit']:>+10.2f} {pf:>6.2f}")

    # ============================================================
    # 6. DD EPISODES : quand le reverse sauve vs quand il aggrave
    # ============================================================
    print("\n" + "=" * 90)
    print("DD EPISODES MAJEURS (>5% DD) — impact du reverse")
    print("=" * 90)

    # Track DD episodes with and without reverse
    eq_w = 10000.0
    eq_wo = 10000.0
    max_w = eq_w
    max_wo = eq_wo
    in_dd = False
    dd_start = None
    dd_trades_with = 0
    dd_trades_without = 0
    episodes = []

    for t in trades:
        eq_w += t['profit']
        max_w = max(max_w, eq_w)
        dd_pct = (max_w - eq_w) / max_w * 100

        if not t['is_reverse']:
            eq_wo += t['profit']
            max_wo = max(max_wo, eq_wo)

        if dd_pct > 5 and not in_dd:
            in_dd = True
            dd_start = t['open_date']
            dd_rev_profit = 0
            dd_norm_profit = 0
            dd_peak_with = dd_pct
            dd_rev_count = 0

        if in_dd:
            if t['is_reverse']:
                dd_rev_profit += t['profit']
                dd_rev_count += 1
            else:
                dd_norm_profit += t['profit']
            dd_peak_with = max(dd_peak_with, dd_pct)

            if dd_pct < 1:  # DD recovered
                in_dd = False
                episodes.append({
                    'start': dd_start,
                    'end': t['close_date'],
                    'peak_dd': dd_peak_with,
                    'rev_count': dd_rev_count,
                    'rev_profit': dd_rev_profit,
                    'year': int(dd_start.split('.')[0]),
                })

    for ep in episodes[:15]:  # top 15
        rev_impact = "HELPED" if ep['rev_profit'] > 0 else "HURT" if ep['rev_profit'] < 0 else "NEUTRAL"
        print(f"  {ep['start']} -> {ep['end']}: DD {ep['peak_dd']:.1f}%, {ep['rev_count']} rev trades, rev net {ep['rev_profit']:+.2f} [{rev_impact}]")

if __name__ == '__main__':
    filepath = sys.argv[1] if len(sys.argv) > 1 else 'resultats_regime_pyramidV2-16ans_agressif_v1.txt'
    analyze(filepath)
