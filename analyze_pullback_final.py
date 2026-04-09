"""
Analyse du EMA Pullback pyramid avec config ULTRA aggressive:
L0=2.0, L1=7.0, L2=4.0 sur 3 ans.
"""
from datetime import datetime
from collections import defaultdict

PATH = r"C:\Users\projets\botTrading\resultats_martingale_EMAPullback3ansFinal.txt"

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
    elif t['action'] == 'modify':
        if t['ticket'] in opens:
            opens[t['ticket']]['sl'] = t['sl']
    elif t['action'] in ('s/l', 't/p', 'close at stop', 'close'):
        if t['ticket'] in opens:
            op = opens[t['ticket']]
            trades.append({
                'ticket': t['ticket'],
                'type': op['action'], 'lots': op['lots'],
                'open_dt': op['dt'], 'close_dt': t['dt'],
                'open_price': op['price'], 'sl': op['sl'],
                'profit': t['profit'], 'balance_after': t['balance'],
                'result': t['action']
            })
            del opens[t['ticket']]

print(f"Total trades: {len(trades)}")
print(f"Periode: {trades[0]['open_dt']} -> {trades[-1]['close_dt']}")
print(f"Balance: 10000 -> {trades[-1]['balance_after']:.2f}")
print(f"Net: +${trades[-1]['balance_after']-10000:.2f} (+{(trades[-1]['balance_after']/10000-1)*100:.0f}%)")

# Par annee
print("\n" + "=" * 75)
print("PAR ANNEE")
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

print(f"{'Year':>5} {'N':>5} {'WR%':>6} {'Net':>12} {'PF':>6}")
for y in sorted(by_year.keys()):
    d = by_year[y]
    wr_y = d['wins']/d['n']*100 if d['n'] else 0
    net = d['gw']-d['gl']
    pf_y = d['gw']/d['gl'] if d['gl'] else 0
    print(f"{y:>5} {d['n']:>5} {wr_y:>6.1f} {net:>+12.2f} {pf_y:>6.2f}")

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

print(f"{'Lvl':>4} {'N':>5} {'WR%':>6} {'Net':>12} {'PF':>6} {'AvgLot':>8} {'AvgWin':>10} {'AvgLoss':>10}")
for lv in sorted(by_lvl.keys()):
    d = by_lvl[lv]
    wr = d['wins']/d['n']*100
    net = d['gw']-d['gl']
    pf = d['gw']/d['gl'] if d['gl'] else 0
    avg_lot = sum(d['lots'])/len(d['lots']) if d['lots'] else 0
    avg_w = d['gw']/d['wins'] if d['wins'] else 0
    avg_l = d['gl']/(d['n']-d['wins']) if (d['n']-d['wins']) else 0
    print(f"{lv:>4} {d['n']:>5} {wr:>6.1f} {net:>+12.2f} {pf:>6.2f} {avg_lot:>8.2f} {avg_w:>+10.2f} {avg_l:>10.2f}")

# DD
balances = [10000] + [t['balance_after'] for t in trades]
peak = balances[0]
max_dd_pct = 0
max_dd_abs = 0
dd_location = None
for i, b in enumerate(balances):
    if b > peak: peak = b
    dd = peak - b
    dd_pct = dd/peak*100 if peak > 0 else 0
    if dd_pct > max_dd_pct:
        max_dd_pct = dd_pct
        max_dd_abs = dd
        dd_location = i

print(f"\n--- DRAWDOWN ---")
print(f"Max DD: {max_dd_abs:.2f} USD ({max_dd_pct:.1f}%)")
if dd_location and dd_location > 0:
    print(f"DD bottom: trade #{dd_location}, balance ${balances[dd_location]:.0f}")

# Top
print("\n--- TOP 10 WINS ---")
for t in sorted(trades, key=lambda x: -x['profit'])[:10]:
    print(f"  {t['open_dt']} lv={t['level']} lot={t['lots']:.2f} +${t['profit']:.2f}")
print("\n--- TOP 10 LOSSES ---")
for t in sorted(trades, key=lambda x: x['profit'])[:10]:
    print(f"  {t['open_dt']} lv={t['level']} lot={t['lots']:.2f} ${t['profit']:.2f}")

# Courbe d'equity trimestrielle
print("\n--- EQUITY PAR TRIMESTRE ---")
by_q = defaultdict(lambda: 0)
for t in trades:
    y = t['open_dt'].year
    q = (t['open_dt'].month - 1)//3 + 1
    by_q[f"{y}Q{q}"] += t['profit']

cumul = 10000
for key in sorted(by_q.keys()):
    cumul += by_q[key]
    pnl = by_q[key]
    mark = '+' if pnl >= 0 else '-'
    bar = '#' * min(30, int(abs(pnl)/500))
    print(f"  {key}: {pnl:>+11.2f}  cumul={cumul:>10.2f}  {mark} {bar}")

# Comparaison configs
print("\n" + "=" * 75)
print("COMPARAISON 3 ANS DES CONFIGS EMA PULLBACK")
print("=" * 75)
net = trades[-1]['balance_after'] - 10000
print(f"{'Config':<35} {'Net':>10} {'DD%':>7} {'PF':>5} {'Exp/trade':>10}")
print(f"{'baseline (no pyramid)':<35} {'+7075':>10} {'6.3':>7} {'2.12':>5} {'+57':>10}")
print(f"{'pyramid 1.0/1.5/2.25':<35} {'+9568':>10} {'11.9':>7} {'1.98':>5} {'+85':>10}")
print(f"{'pyramid 1.0/4.0/2.5':<35} {'+?':>10} {'?':>7} {'?':>5} {'?':>10}")
print(f"{'pyramid 2.0/7.0/4.0 (CURRENT)':<35} {f'+{net:.0f}':>10} {f'{max_dd_pct:.1f}':>7} {'2.18':>5} {'+778':>10}")
