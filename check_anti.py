"""Investigation des lots anormaux et verification du cap pyramid."""
from datetime import datetime
from collections import defaultdict

PATH = r"C:\Users\projets\botTrading\resultats_anti-martingale.txt"

trades_raw = []
with open(PATH, 'r', encoding='utf-8', errors='ignore') as f:
    for line in f:
        parts = line.strip().split('\t')
        if len(parts) < 10:
            continue
        try:
            dt = datetime.strptime(parts[1], '%Y.%m.%d %H:%M')
            trades_raw.append({
                'dt': dt, 'action': parts[2], 'ticket': int(parts[3]),
                'lots': float(parts[4]), 'price': float(parts[5]),
                'sl': float(parts[6]), 'tp': float(parts[7]),
                'profit': float(parts[8]), 'balance': float(parts[9])
            })
        except:
            continue

opens = {}
trades = []
for t in trades_raw:
    if t['action'] in ('buy', 'sell'):
        opens[t['ticket']] = t
    elif t['action'] in ('s/l', 't/p'):
        if t['ticket'] in opens:
            op = opens[t['ticket']]
            # Compute SL distance in pips
            sl_dist = abs(op['price'] - op['sl']) * 10000  # pips
            trades.append({
                'type': op['action'], 'lots': op['lots'],
                'open_dt': op['dt'], 'close_dt': t['dt'],
                'open_price': op['price'], 'sl': op['sl'],
                'sl_pips': sl_dist,
                'profit': t['profit'],
                'balance_before': op['balance'],  # balance at open (same as balance before SL)
                'balance_after': t['balance'],
                'result': t['action']
            })
            del opens[t['ticket']]

# Trace the streak and calculate what the expected lot SHOULD be
# with cap at 2 and mult 1.5
streak = 0
print(f"{'#':>5} {'date':<17} {'streak':>6} {'lots':>6} {'sl_p':>5} {'bal':>10} {'base_exp':>9} {'cap_exp':>9} {'ratio':>7} {'result':>6}")
anomalies = []
for i, t in enumerate(trades):
    # Expected base lot from 1% of balance before this trade opened
    # For the FIRST trade, balance_before = 10000
    # But balance_before from history is balance AFTER previous close, which is our start.
    # Actually opens[t]['balance'] is what? Let me use the prev close balance
    if i == 0:
        bal = 10000
    else:
        bal = trades[i-1]['balance_after']
    risk = bal * 0.01
    sl_p = t['sl_pips']
    expected_base = risk / (sl_p * 10) if sl_p > 0 else 0
    capped_streak = min(streak, 2)
    expected_lot_cap = expected_base * (1.5 ** capped_streak)
    ratio = t['lots'] / expected_lot_cap if expected_lot_cap > 0 else 0

    # Anomaly if actual lot > 1.3x expected
    if ratio > 1.3 and t['lots'] > 0.5:
        anomalies.append({
            'i': i, 'dt': t['open_dt'], 'streak': streak, 'lots': t['lots'],
            'sl_pips': sl_p, 'bal': bal,
            'exp_base': expected_base, 'exp_cap': expected_lot_cap, 'ratio': ratio,
            'profit': t['profit']
        })

    # Print first 30 and any anomaly
    if i < 30:
        mark = '!!' if ratio > 1.3 else ''
        print(f"{i+1:>5} {str(t['open_dt']):<17} {streak:>6} {t['lots']:>6.2f} {sl_p:>5.1f} {bal:>10.2f} {expected_base:>9.3f} {expected_lot_cap:>9.3f} {ratio:>7.2f} {t['result']:>6} {mark}")

    # Update streak
    if t['profit'] > 0:
        streak += 1
        # NO cap here - we track raw streak for detection
    else:
        streak = 0

print(f"\n--- ANOMALIES (lot > 1.3x expected) ---")
print(f"Total anomalies: {len(anomalies)}")
if anomalies:
    print(f"\nPremieres 20 anomalies:")
    for a in anomalies[:20]:
        print(f"  #{a['i']+1:4d} {a['dt']} streak={a['streak']:2d} lot={a['lots']:.2f} exp_cap={a['exp_cap']:.2f} ratio={a['ratio']:.2f}x bal={a['bal']:.0f} sl={a['sl_pips']:.1f}p")

# Statistiques sur les ratios
print(f"\n--- DISTRIBUTION DES RATIOS LOT/EXPECTED ---")
ratios = []
streak = 0
for i, t in enumerate(trades):
    if i == 0:
        bal = 10000
    else:
        bal = trades[i-1]['balance_after']
    risk = bal * 0.01
    expected_base = risk / (t['sl_pips'] * 10) if t['sl_pips'] > 0 else 0
    capped_streak = min(streak, 2)
    expected_lot_cap = expected_base * (1.5 ** capped_streak)
    if expected_lot_cap > 0:
        ratios.append(t['lots'] / expected_lot_cap)
    if t['profit'] > 0: streak += 1
    else: streak = 0

buckets = [(0.5, 0.9), (0.9, 1.1), (1.1, 1.3), (1.3, 1.5), (1.5, 2.0), (2.0, 3.0), (3.0, 10)]
for lo, hi in buckets:
    c = sum(1 for r in ratios if lo <= r < hi)
    print(f"  [{lo:.1f} ; {hi:.1f}[: {c} trades")
