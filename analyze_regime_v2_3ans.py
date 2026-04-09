"""
Analyse du regime_pyramid_EA v2 (L0 x 0.5) sur 3 ans.
Compare au 6 ans pour verifier la robustesse.
"""
from datetime import datetime
from collections import defaultdict

PATH = r"C:\Users\projets\botTrading\resultats_regime_pyramid-3ans_v1.txt"

trades_raw = []
with open(PATH, 'r', encoding='utf-8', errors='ignore') as f:
    for line in f:
        parts = line.strip().split('\t')
        if len(parts) < 10: continue
        try:
            dt = datetime.strptime(parts[1], '%Y.%m.%d %H:%M')
            trades_raw.append({
                'dt': dt, 'action': parts[2], 'ticket': int(parts[3]),
                'lots': float(parts[4]), 'price': float(parts[5]),
                'sl': float(parts[6]), 'tp': float(parts[7]),
                'profit': float(parts[8]), 'balance': float(parts[9])
            })
        except: continue

opens = {}
trades = []
for t in trades_raw:
    if t['action'] in ('buy', 'sell'):
        opens[t['ticket']] = t
    elif t['action'] in ('s/l', 't/p', 'close at stop', 'close'):
        if t['ticket'] in opens:
            op = opens[t['ticket']]
            trades.append({
                'type': op['action'], 'lots': op['lots'],
                'open_dt': op['dt'], 'close_dt': t['dt'],
                'profit': t['profit'], 'balance_after': t['balance'],
                'result': t['action']
            })
            del opens[t['ticket']]

print(f"Total trades: {len(trades)}")
print(f"Periode: {trades[0]['open_dt']} -> {trades[-1]['close_dt']}")
print(f"Balance: 10000 -> {trades[-1]['balance_after']:.2f}")
print(f"Net: +${trades[-1]['balance_after']-10000:.2f}")

# Par annee
print("\n" + "=" * 75)
print("PAR ANNEE (regime_pyramid_EA v2 sur 3 ans)")
print("=" * 75)
by_year = defaultdict(lambda: {'n': 0, 'wins': 0, 'gw': 0, 'gl': 0})
for t in trades:
    y = t['open_dt'].year
    by_year[y]['n'] += 1
    if t['profit'] > 0:
        by_year[y]['wins'] += 1
        by_year[y]['gw'] += t['profit']
    else:
        by_year[y]['gl'] += abs(t['profit'])

print(f"{'Year':>5} {'N':>5} {'WR%':>6} {'Net':>10} {'PF':>5}")
for y in sorted(by_year.keys()):
    d = by_year[y]
    wr = d['wins']/d['n']*100 if d['n'] else 0
    net = d['gw']-d['gl']
    pf = d['gw']/d['gl'] if d['gl'] else 0
    print(f"{y:>5} {d['n']:>5} {wr:>6.1f} {net:>+10.2f} {pf:>5.2f}")

# Par niveau pyramide
print("\n" + "=" * 75)
print("PAR NIVEAU PYRAMIDE")
print("=" * 75)
streak = 0
for t in trades:
    t['level'] = streak
    if t['profit'] > 0: streak = min(streak+1, 2)
    else: streak = 0

by_lvl = defaultdict(lambda: {'n': 0, 'wins': 0, 'gw': 0, 'gl': 0, 'lots': []})
for t in trades:
    lv = t['level']
    by_lvl[lv]['n'] += 1
    by_lvl[lv]['lots'].append(t['lots'])
    if t['profit'] > 0:
        by_lvl[lv]['wins'] += 1
        by_lvl[lv]['gw'] += t['profit']
    else:
        by_lvl[lv]['gl'] += abs(t['profit'])

print(f"{'Lvl':>4} {'N':>5} {'WR%':>6} {'Net':>11} {'PF':>6} {'AvgLot':>8}")
for lv in sorted(by_lvl.keys()):
    d = by_lvl[lv]
    wr = d['wins']/d['n']*100
    net = d['gw']-d['gl']
    pf = d['gw']/d['gl'] if d['gl'] else 0
    avg_lot = sum(d['lots'])/len(d['lots']) if d['lots'] else 0
    print(f"{lv:>4} {d['n']:>5} {wr:>6.1f} {net:>+11.2f} {pf:>6.2f} {avg_lot:>8.2f}")

# DD
balances = [10000] + [t['balance_after'] for t in trades]
peak = balances[0]
max_dd_pct = 0
for b in balances:
    if b > peak: peak = b
    dd_pct = (peak-b)/peak*100 if peak > 0 else 0
    if dd_pct > max_dd_pct: max_dd_pct = dd_pct

# Comparaison regime_pyramid v1 vs v2 sur 6 ans par annee
print("\n" + "=" * 75)
print("COMPARAISON 6ANS v1 vs v2")
print("=" * 75)
v1_6ans = {
    2020: (+677.01,  109),
    2021: (+325.00,  110),
    2022: (+1707.61, 99),
    2023: (-700.97,  169),
    2024: (+3180.08, 96),
    2025: (+423.06,  94),
    2026: (+135.64,  23),
}
# On n'a que 2023-2026 sur ce test 3 ans
print(f"{'Year':>5} {'v1_6ans':>10} {'v2_3ans':>10} {'Delta':>10}")
for y in sorted(by_year.keys()):
    d = by_year[y]
    v2_net = d['gw']-d['gl']
    v1_net = v1_6ans.get(y, (0, 0))[0]
    delta = v2_net - v1_net
    print(f"{y:>5} {v1_net:>+10.2f} {v2_net:>+10.2f} {delta:>+10.2f}")

# Comparaison resume systemes
print("\n" + "=" * 75)
print("COMPARAISON SYSTEMES (meme periode 2023-2026)")
print("=" * 75)
print(f"{'Systeme':<40} {'Net':>10} {'DD%':>7} {'PF':>6} {'Trades':>7}")
print(f"{'AntiMart (sans regime filter)':<40} {'+16414':>10} {'32.8':>7} {'1.09':>6} {'1397':>7}")
print(f"{'Regime pyramid v1 (3ans partial)':<40} {'?':>10} {'?':>7} {'?':>6} {'?':>7}")
net = trades[-1]['balance_after'] - 10000
print(f"{'Regime pyramid v2 (L0 x 0.5)':<40} {f'+{net:.0f}':>10} {f'{max_dd_pct:.2f}':>7} {'1.18':>6} {len(trades):>7}")

# Return / DD ratio
print(f"\n--- RATIO Return/DD ---")
print(f"AntiMart:         16414 / 32.83 = {16414/32.83:.0f}")
print(f"Regime v2 (3ans): {net:.0f} / {max_dd_pct:.2f} = {net/max_dd_pct:.0f}")
