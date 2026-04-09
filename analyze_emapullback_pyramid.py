"""
Analyse du EMA_Pullback_pyramid sur 3 ans.
Decompose par niveau de pyramide pour identifier optimisations possibles.
"""
from datetime import datetime
from collections import defaultdict

PATH = r"C:\Users\projets\botTrading\resultats_martingale_EMAPullback3ans.txt"

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
        # modify = BE move, update SL but keep tracking
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
print(f"Net: +${trades[-1]['balance_after']-10000:.2f}")

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

print(f"{'Year':>5} {'N':>5} {'WR%':>6} {'Net':>11} {'PF':>5}")
for y in sorted(by_year.keys()):
    d = by_year[y]
    wr = d['wins']/d['n']*100 if d['n'] else 0
    net = d['gw']-d['gl']
    pf = d['gw']/d['gl'] if d['gl'] else 0
    print(f"{y:>5} {d['n']:>5} {wr:>6.1f} {net:>+11.2f} {pf:>5.2f}")

# Par niveau pyramide (streak tracking)
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

print(f"{'Lvl':>4} {'N':>5} {'WR%':>6} {'Net':>11} {'PF':>6} {'AvgLot':>8} {'AvgWin':>9} {'AvgLoss':>9}")
for lv in sorted(by_lvl.keys()):
    d = by_lvl[lv]
    wr = d['wins']/d['n']*100
    net = d['gw']-d['gl']
    pf = d['gw']/d['gl'] if d['gl'] else 0
    avg_lot = sum(d['lots'])/len(d['lots']) if d['lots'] else 0
    avg_w = d['gw']/d['wins'] if d['wins'] else 0
    avg_l = d['gl']/(d['n']-d['wins']) if (d['n']-d['wins']) else 0
    print(f"{lv:>4} {d['n']:>5} {wr:>6.1f} {net:>+11.2f} {pf:>6.2f} {avg_lot:>8.2f} {avg_w:>+9.2f} {avg_l:>9.2f}")

# Streaks analysis
print("\n" + "=" * 75)
print("DISTRIBUTION DES STREAKS DE WINS")
print("=" * 75)
streak_lengths = []
cur = 0
for t in trades:
    if t['profit'] > 0:
        cur += 1
    else:
        if cur > 0: streak_lengths.append(cur)
        cur = 0
if cur > 0: streak_lengths.append(cur)

streak_dist = defaultdict(int)
for s in streak_lengths:
    streak_dist[s] += 1

print(f"Nombre total de streaks de wins: {len(streak_lengths)}")
print(f"{'Streak':>7} {'Count':>6} {'Contribution L-levels':>25}")
for length in sorted(streak_dist.keys()):
    count = streak_dist[length]
    # streak de N = N L0 wins + (N-1) L1 + (N-2) L2 ...
    # Actually streak N means: 1 trade that was L0 win, 1 that was L1 win, etc.
    l0_triggered = count
    l1_triggered = max(0, count if length >= 2 else 0)
    l2_triggered = max(0, count if length >= 3 else 0)
    print(f"{length:>7} {count:>6}   (each triggers {min(length, 3)} pyramid levels)")

print(f"Plus longue streak: {max(streak_lengths) if streak_lengths else 0}")

# DD
balances = [10000] + [t['balance_after'] for t in trades]
peak = balances[0]
max_dd_pct = 0
max_dd_abs = 0
for b in balances:
    if b > peak: peak = b
    dd = peak - b
    dd_pct = dd/peak*100 if peak > 0 else 0
    if dd_pct > max_dd_pct:
        max_dd_pct = dd_pct
        max_dd_abs = dd
print(f"\n--- DRAWDOWN ---")
print(f"Max DD: {max_dd_abs:.2f} USD ({max_dd_pct:.1f}%)")

# Projection avec plus aggressif (L1=2.5 L2=3.5)
print("\n" + "=" * 75)
print("PROJECTION: optimisation L1/L2 (scaling lineaire naif)")
print("=" * 75)

# Current: L0=1.0, L1=1.5, L2=2.25
l0_net = by_lvl[0]['gw'] - by_lvl[0]['gl']
l1_net = by_lvl[1]['gw'] - by_lvl[1]['gl']
l2_net = by_lvl[2]['gw'] - by_lvl[2]['gl']
current_total = l0_net + l1_net + l2_net

print(f"Current (L0=1.0/L1=1.5/L2=2.25):")
print(f"  L0 net: {l0_net:+.2f}")
print(f"  L1 net: {l1_net:+.2f}")
print(f"  L2 net: {l2_net:+.2f}")
print(f"  Total:  {current_total:+.2f}")
print()

configs = [
    ("L1=2.0, L2=3.0", 2.0/1.5, 3.0/2.25),
    ("L1=2.5, L2=3.5", 2.5/1.5, 3.5/2.25),
    ("L1=3.0, L2=4.0", 3.0/1.5, 4.0/2.25),
    ("L1=3.5, L2=5.0", 3.5/1.5, 5.0/2.25),
    ("L1=4.0, L2=6.0", 4.0/1.5, 6.0/2.25),
]
print(f"{'Config':>20} {'L0':>10} {'L1_scaled':>12} {'L2_scaled':>12} {'Total':>10} {'Delta':>9}")
print(f"{'current':>20} {l0_net:>+10.2f} {l1_net:>+12.2f} {l2_net:>+12.2f} {current_total:>+10.2f} {'':>9}")
for label, l1_scale, l2_scale in configs:
    new_l1 = l1_net * l1_scale
    new_l2 = l2_net * l2_scale
    new_total = l0_net + new_l1 + new_l2
    delta = new_total - current_total
    print(f"{label:>20} {l0_net:>+10.2f} {new_l1:>+12.2f} {new_l2:>+12.2f} {new_total:>+10.2f} {delta:>+9.2f}")

print("\nATTENTION: projection lineaire naive, ignore le compound effect.")
print("Le compound peut AMPLIFIER positivement (plus de balance = plus de lot) ou")
print("negativement (plus de DD impact). Toujours valider par backtest reel.")
