"""
Simulation : ConsecLosses=3 applique a L1 et L2
Idee : apres 3 pertes consecutives, reduire ou skipper les L1/L2
Options simulees :
- Skip L1/L2 apres 3 losses (ne trade qu'en L0 jusqu'au prochain win)
- Reduire L1/L2 lot apres 3 losses (ex: L1 passe de 7x a 3x)
- Reset streak apres 3 losses (forcer retour L0)
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

def classify(trades):
    """Classify trades with AGGRESSIVE multipliers"""
    streak = 0
    for t in trades:
        if streak == 0:
            t['level'] = 'L0'
            t['lot_mult'] = 2.0
        elif streak == 1:
            t['level'] = 'L1'
            t['lot_mult'] = 7.0
        else:
            t['level'] = 'L2'
            t['lot_mult'] = 4.0

        if t['profit'] > 0:
            streak = min(streak + 1, 2)
        else:
            streak = 0

def simulate(trades, label, scale_fn):
    """
    scale_fn(trade, consec_losses) -> multiplier to apply to profit
    1.0 = normal, 0.0 = skip, 0.5 = half lot etc.
    """
    equity = 10000.0
    max_equity = equity
    max_dd_pct = 0.0
    consec_losses = 0
    total_profit = 0.0
    yearly = defaultdict(float)

    skipped = 0
    reduced = 0

    for t in trades:
        scale = scale_fn(t, consec_losses)
        scaled_profit = t['profit'] * scale

        if scale == 0:
            skipped += 1
        elif scale < 1.0:
            reduced += 1

        equity += scaled_profit
        total_profit += scaled_profit
        max_equity = max(max_equity, equity)
        dd = (max_equity - equity) / max_equity * 100
        max_dd_pct = max(max_dd_pct, dd)
        yearly[t['year']] += scaled_profit

        # Update consec losses (on original trade, not scaled)
        if t['profit'] > 0:
            consec_losses = 0
        else:
            consec_losses += 1

    p1 = sum(yearly.get(y, 0) for y in range(2010, 2020))
    p2 = sum(yearly.get(y, 0) for y in range(2020, 2027))
    rdd = total_profit / (max_dd_pct / 100 * max_equity) if max_dd_pct > 0 else 999

    print(f"\n  {label}")
    print(f"  Final: ${equity:.0f} | Profit: {total_profit:+.0f} | DD max: {max_dd_pct:.1f}%")
    print(f"  2010-2019: {p1:+.0f} | 2020-2026: {p2:+.0f}")
    if skipped > 0 or reduced > 0:
        print(f"  Trades skipped: {skipped}, reduced: {reduced}")

    return {'label': label, 'equity': equity, 'profit': total_profit,
            'dd': max_dd_pct, 'p1': p1, 'p2': p2, 'yearly': dict(yearly)}

def main():
    filepath = sys.argv[1] if len(sys.argv) > 1 else 'resultats_martingale_EMAPullback16ans.txt'
    trades = parse_trades(filepath)
    classify(trades)

    print(f"Fichier: {filepath}")
    print(f"Trades: {len(trades)}")

    # === SCENARIO 1: SKIP L1/L2 apres N consec losses ===
    print("\n" + "=" * 90)
    print("SCENARIO 1 : SKIP L1/L2 apres N pertes consecutives")
    print("(trade quand meme en L0 lot, mais pas en L1/L2 gros lot)")
    print("=" * 90)

    # Baseline
    simulate(trades, "BASELINE AGGRESSIVE (aucun filtre)",
             lambda t, cl: 1.0)

    for threshold in [2, 3, 4, 5]:
        def make_fn(th):
            def fn(t, cl):
                if cl >= th and t['level'] in ('L1', 'L2'):
                    # Scale down to L0 lot (2.0) instead of L1(7.0) or L2(4.0)
                    return 2.0 / t['lot_mult']
                return 1.0
            return fn
        simulate(trades, f"Skip L1/L2 apres {threshold} losses (trade en L0 lot)", make_fn(threshold))

    # === SCENARIO 2: REDUCE L1/L2 lot apres N consec losses ===
    print("\n" + "=" * 90)
    print("SCENARIO 2 : REDUIRE L1/L2 de moitie apres N pertes consecutives")
    print("=" * 90)

    for threshold in [2, 3, 4]:
        def make_fn2(th):
            def fn(t, cl):
                if cl >= th and t['level'] in ('L1', 'L2'):
                    return 0.5  # half lot
                return 1.0
            return fn
        simulate(trades, f"L1/L2 lot x0.5 apres {threshold} losses", make_fn2(threshold))

    # === SCENARIO 3: SKIP uniquement L1 (garder L2) ===
    print("\n" + "=" * 90)
    print("SCENARIO 3 : SKIP L1 seulement apres N losses (L2 inchange)")
    print("=" * 90)

    for threshold in [2, 3, 4]:
        def make_fn3(th):
            def fn(t, cl):
                if cl >= th and t['level'] == 'L1':
                    return 2.0 / 7.0  # scale to L0 lot
                return 1.0
            return fn
        simulate(trades, f"Skip L1 (->L0 lot) apres {threshold} losses", make_fn3(threshold))

    # === SCENARIO 4: SKIP L2 seulement ===
    print("\n" + "=" * 90)
    print("SCENARIO 4 : SKIP L2 seulement apres N losses (L1 inchange)")
    print("=" * 90)

    for threshold in [2, 3]:
        def make_fn4(th):
            def fn(t, cl):
                if cl >= th and t['level'] == 'L2':
                    return 2.0 / 4.0  # scale to L0 lot
                return 1.0
            return fn
        simulate(trades, f"Skip L2 (->L0 lot) apres {threshold} losses", make_fn4(threshold))

    # === SCENARIO 5: COMBINAISON — L1 protege + reverse conceptuel ===
    print("\n" + "=" * 90)
    print("SCENARIO 5 : SKIP L1+L2 apres 3 losses + details par annee")
    print("=" * 90)

    r_base = simulate(trades, "BASELINE", lambda t, cl: 1.0)

    def skip_l1l2_3(t, cl):
        if cl >= 3 and t['level'] in ('L1', 'L2'):
            return 2.0 / t['lot_mult']
        return 1.0
    r_skip = simulate(trades, "SKIP L1/L2 apres 3 losses", skip_l1l2_3)

    print(f"\n  {'Year':<6} {'BASELINE':>12} {'SKIP_3':>12} {'Delta':>12}")
    for y in range(2010, 2027):
        b = r_base['yearly'].get(y, 0)
        s = r_skip['yearly'].get(y, 0)
        print(f"  {y:<6} {b:>+12.0f} {s:>+12.0f} {s-b:>+12.0f}")

if __name__ == '__main__':
    main()
