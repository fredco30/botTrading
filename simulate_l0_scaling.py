"""
Simulation : que se passe-t-il si on reduit le lot L0 ?
L0 = ticket d'entree pour L1, pas un profit center.

On simule sur les trades V1 (sans reverse) en scalant les profits L0.
Mode AGGRESSIVE actuel : L0=2.0, L1=7.0, L2=2.5
Simulation : L0=0.5 ou L0=0.25 (micro lot, juste pour tester le streak)
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

            if action in ('buy', 'sell'):
                pending[ticket] = {
                    'ticket': ticket, 'type': action, 'lot': lot,
                    'open_price': price, 'open_date': date_str,
                    'year': year,
                    'sl_price_initial': sl, 'tp_price': tp,
                }
            elif action in ('t/p', 's/l', 'close'):
                if ticket in pending:
                    t = pending[ticket]
                    t['close_action'] = action
                    t['profit'] = profit
                    t['balance'] = balance
                    trades.append(t)
                    del pending[ticket]
    return trades

def classify_and_get_base_lot(trades):
    """
    Classify trades into L0/L1/L2 and estimate the base lot.
    In AGGRESSIVE mode: L0=2.0x, L1=7.0x, L2=4.0x
    So: base_lot = L0_lot / 2.0
    We detect L0 by streak logic, then derive ratios.
    """
    streak = 0
    for t in trades:
        if streak == 0:
            t['level'] = 'L0'
            t['lot_mult'] = 2.0  # AGGRESSIVE L0
        elif streak == 1:
            t['level'] = 'L1'
            t['lot_mult'] = 7.0  # AGGRESSIVE L1
        else:
            t['level'] = 'L2'
            t['lot_mult'] = 4.0  # AGGRESSIVE L2

        if t['profit'] > 0:
            streak = min(streak + 1, 2)
        else:
            streak = 0

def simulate(trades, l0_mult, l1_mult, l2_mult, label=""):
    """Simulate equity curve with custom lot multipliers.
    We scale each trade's profit by (new_mult / original_mult).
    This is an approximation (ignores compounding effects on balance)
    but gives directional insight.
    """
    equity = 10000.0
    max_equity = equity
    max_dd = 0.0
    max_dd_dollars = 0.0
    total_profit = 0.0

    yearly = defaultdict(lambda: {'profit': 0.0, 'n': 0})

    for t in trades:
        orig_mult = t['lot_mult']
        if t['level'] == 'L0':
            new_mult = l0_mult
        elif t['level'] == 'L1':
            new_mult = l1_mult
        else:
            new_mult = l2_mult

        # Scale profit proportionally
        if orig_mult > 0:
            scaled_profit = t['profit'] * (new_mult / orig_mult)
        else:
            scaled_profit = t['profit']

        equity += scaled_profit
        total_profit += scaled_profit
        max_equity = max(max_equity, equity)
        dd_pct = (max_equity - equity) / max_equity * 100
        dd_dollars = max_equity - equity
        max_dd = max(max_dd, dd_pct)
        max_dd_dollars = max(max_dd_dollars, dd_dollars)

        yearly[t['year']]['profit'] += scaled_profit
        yearly[t['year']]['n'] += 1

    return {
        'label': label,
        'l0': l0_mult, 'l1': l1_mult, 'l2': l2_mult,
        'equity': equity,
        'profit': total_profit,
        'max_dd_pct': max_dd,
        'max_dd_dollars': max_dd_dollars,
        'yearly': dict(yearly),
    }

def print_result(r):
    print(f"\n  {r['label']}")
    print(f"  L0={r['l0']:.1f} L1={r['l1']:.1f} L2={r['l2']:.1f}")
    print(f"  Final: ${r['equity']:.2f} | Profit: {r['profit']:+.2f} | DD max: {r['max_dd_pct']:.1f}% (${r['max_dd_dollars']:.0f})")

    # Per period
    p1 = sum(r['yearly'].get(y, {}).get('profit', 0) for y in range(2010, 2020))
    p2 = sum(r['yearly'].get(y, {}).get('profit', 0) for y in range(2020, 2027))
    print(f"  2010-2019: {p1:+.2f} | 2020-2026: {p2:+.2f}")

    # Return/DD ratio
    if r['max_dd_pct'] > 0:
        rdd = r['profit'] / r['max_dd_dollars'] if r['max_dd_dollars'] > 0 else 999
        print(f"  Return/DD ratio: {rdd:.2f}")

def main():
    filepath = sys.argv[1] if len(sys.argv) > 1 else 'resultats_martingale_EMAPullback16ans.txt'
    trades = parse_trades(filepath)
    classify_and_get_base_lot(trades)

    print(f"Fichier: {filepath}")
    print(f"Trades: {len(trades)}")

    l0_count = sum(1 for t in trades if t['level'] == 'L0')
    l1_count = sum(1 for t in trades if t['level'] == 'L1')
    l2_count = sum(1 for t in trades if t['level'] == 'L2')
    print(f"L0: {l0_count} | L1: {l1_count} | L2: {l2_count}")

    print("\n" + "=" * 90)
    print("SIMULATION : DIFFERENT L0 MULTIPLIERS (L1=7.0, L2=4.0 fixes)")
    print("=" * 90)

    configs = [
        (2.0, 7.0, 4.0, "ACTUEL AGGRESSIVE (L0=2.0)"),
        (1.0, 7.0, 4.0, "L0 REDUIT (L0=1.0) — mode SAFE L0"),
        (0.5, 7.0, 4.0, "L0 MICRO (L0=0.5) — ticket d'entree"),
        (0.25, 7.0, 4.0, "L0 MINIMAL (L0=0.25) — pur signal"),
        (0.1, 7.0, 4.0, "L0 NEGLIGEABLE (L0=0.1) — quasi zero"),
    ]

    results = []
    for l0, l1, l2, label in configs:
        r = simulate(trades, l0, l1, l2, label)
        results.append(r)
        print_result(r)

    print("\n" + "=" * 90)
    print("SIMULATION : L0 REDUIT + L2 REDUIT (L1 = profit engine)")
    print("=" * 90)

    configs2 = [
        (2.0, 7.0, 4.0, "ACTUEL AGGRESSIVE"),
        (0.5, 7.0, 4.0, "L0=0.5, L2=4.0 (L0 micro, L2 inchange)"),
        (0.5, 7.0, 2.5, "L0=0.5, L2=2.5 (L0 micro, L2 SAFE)"),
        (0.5, 7.0, 1.0, "L0=0.5, L2=1.0 (L0 micro, L2 micro)"),
        (0.25, 7.0, 2.0, "L0=0.25, L2=2.0 (pur signal, L2 modere)"),
        (0.5, 8.0, 2.5, "L0=0.5, L1=8.0, L2=2.5 (boost L1)"),
        (0.5, 9.0, 2.0, "L0=0.5, L1=9.0, L2=2.0 (max L1)"),
    ]

    for l0, l1, l2, label in configs2:
        r = simulate(trades, l0, l1, l2, label)
        print_result(r)

    # Yearly detail for best configs
    print("\n" + "=" * 90)
    print("DETAIL PAR ANNEE — TOP CONFIGS")
    print("=" * 90)

    best_configs = [
        (2.0, 7.0, 4.0, "ACTUEL"),
        (0.5, 7.0, 4.0, "L0=0.5"),
        (0.5, 7.0, 2.5, "L0=0.5 L2=2.5"),
    ]

    print(f"{'Year':<6}", end="")
    for _, _, _, label in best_configs:
        print(f" {label:>16}", end="")
    print()

    results_detail = []
    for l0, l1, l2, label in best_configs:
        r = simulate(trades, l0, l1, l2, label)
        results_detail.append(r)

    for y in range(2010, 2027):
        print(f"{y:<6}", end="")
        for r in results_detail:
            p = r['yearly'].get(y, {}).get('profit', 0)
            print(f" {p:>+16.2f}", end="")
        print()

if __name__ == '__main__':
    main()
