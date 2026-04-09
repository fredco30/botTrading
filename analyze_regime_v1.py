"""
Analyse complete du regime_pyramid_EA v1 sur 6 ans.
"""
from datetime import datetime
from collections import defaultdict

PATH = r"C:\Users\projets\botTrading\resultats_regime_pyramid_v1.txt"

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
print("DECOMPOSITION PAR ANNEE (regime_pyramid_EA v1)")
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

# Reference: le test precedent sans filtres regime
ref_by_year = {
    2020: {'n': 334, 'net': -1568.64, 'wr': 42.8},
    2021: {'n': 487, 'net': -2241.88, 'wr': 39.6},
    2022: {'n': 294, 'net': -1315.57, 'wr': 39.8},
    2023: {'n': 484, 'net': +1042.30, 'wr': 44.4},
    2024: {'n': 519, 'net': +2514.90, 'wr': 44.3},
    2025: {'n': 385, 'net': +672.92, 'wr': 43.1},
    2026: {'n': 87,  'net': +1605.61, 'wr': 49.4},
}

print(f"{'Year':>5} {'N_old':>6} {'N_new':>6} {'skip%':>6} {'WR_old':>7} {'WR_new':>7} {'Net_old':>10} {'Net_new':>10}")
for y in sorted(by_year.keys()):
    d = by_year[y]
    wr = d['wins']/d['n']*100 if d['n'] else 0
    net = d['gw']-d['gl']
    ref = ref_by_year.get(y, {'n': 0, 'net': 0, 'wr': 0})
    skip_pct = (1 - d['n']/ref['n'])*100 if ref['n'] else 0
    print(f"{y:>5} {ref['n']:>6} {d['n']:>6} {skip_pct:>5.1f}% {ref['wr']:>6.1f} {wr:>6.1f} {ref['net']:>+10.2f} {net:>+10.2f}")

# DD
balances = [10000] + [t['balance_after'] for t in trades]
peak = balances[0]
max_dd_pct = 0
for b in balances:
    if b > peak: peak = b
    dd_pct = (peak-b)/peak*100 if peak > 0 else 0
    if dd_pct > max_dd_pct: max_dd_pct = dd_pct

print(f"\nMax DD: {max_dd_pct:.1f}%")

# Par niveau pyramide (streak)
print("\n" + "=" * 75)
print("PAR NIVEAU PYRAMIDE")
print("=" * 75)
streak = 0
for t in trades:
    t['level'] = streak
    if t['profit'] > 0: streak = min(streak+1, 2)  # cap 2
    else: streak = 0

by_lvl = defaultdict(lambda: {'n': 0, 'wins': 0, 'gw': 0, 'gl': 0})
for t in trades:
    lv = t['level']
    by_lvl[lv]['n'] += 1
    if t['profit'] > 0:
        by_lvl[lv]['wins'] += 1
        by_lvl[lv]['gw'] += t['profit']
    else:
        by_lvl[lv]['gl'] += abs(t['profit'])

print(f"{'Lvl':>4} {'N':>5} {'WR%':>6} {'Net':>11} {'avgW':>8} {'avgL':>8} {'PF':>6}")
for lv in sorted(by_lvl.keys()):
    d = by_lvl[lv]
    wr = d['wins']/d['n']*100
    net = d['gw']-d['gl']
    avgW = d['gw']/d['wins'] if d['wins'] else 0
    avgL = d['gl']/(d['n']-d['wins']) if (d['n']-d['wins']) else 0
    pf = d['gw']/d['gl'] if d['gl'] else 0
    print(f"{lv:>4} {d['n']:>5} {wr:>6.1f} {net:>+11.2f} {avgW:>+8.2f} {avgL:>-8.2f} {pf:>6.2f}")

# Balance trajectory par trimestre
print("\n" + "=" * 75)
print("BALANCE PAR TRIMESTRE (voir la progression)")
print("=" * 75)
by_q = defaultdict(lambda: 0)
for t in trades:
    y = t['open_dt'].year
    q = (t['open_dt'].month - 1)//3 + 1
    by_q[f"{y}Q{q}"] += t['profit']

cumul = 10000
for key in sorted(by_q.keys()):
    cumul += by_q[key]
    pnl = by_q[key]
    bar = '#' * min(20, int(abs(pnl)/100))
    mark = '+' if pnl >= 0 else '-'
    print(f"  {key}: {pnl:>+9.2f}  cumul={cumul:>9.2f}  {mark} {bar}")

# Rappel comparaison totale
print("\n" + "=" * 75)
print("COMPARAISON 6 ANS - TOUTES VERSIONS")
print("=" * 75)
print(f"{'Version':<40} {'Net':>10} {'DD%':>8} {'PF':>6} {'Trades':>7}")
print(f"{'AntiMart baseline (pas H*J)':<40} {'+733':>10} {'69.8%':>8} {'1.01':>6} {'2607':>7}")
print(f"{'AntiMart + 27 cells + ATR15p':<40} {'+709':>10} {'69.6%':>8} {'1.00':>6} {'2590':>7}")
net_final = trades[-1]['balance_after'] - 10000
print(f"{'regime_pyramid_EA v1':<40} {f'+{net_final:.0f}':>10} {f'{max_dd_pct:.1f}%':>8} {'1.09':>6} {len(trades):>7}")
