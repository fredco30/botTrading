"""
Analyse du martingale_anti_filtered.mq4 v5 sur 3 ans (2023-2026).
Compare au regime_pyramid_EA v2 avec meme config (L0=0.3, L1=1.5, L2=2.25).
"""
from datetime import datetime
from collections import defaultdict

PATH = r"C:\Users\projets\botTrading\resultats_martingale_antifiltred.txt"

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
print("DECOMPOSITION PAR ANNEE")
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

# Drawdown
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

print(f"\nMax DD: {max_dd_abs:.2f} USD ({max_dd_pct:.1f}%)")

# COMPARAISON avec regime_pyramid (meme config L0=0.3)
print("\n" + "=" * 75)
print("COMPARAISON 3 ANS (meme config L0=0.3/L1=1.5/L2=2.25)")
print("=" * 75)
print(f"{'Systeme':<45} {'Net':>10} {'DD%':>7} {'PF':>5} {'Trades':>7}")
print(f"{'regime_pyramid v2 (avec filtres regime)':<45} {'+5200':>10} {'11.84':>7} {'1.21':>5} {'370':>7}")
net = trades[-1]['balance_after'] - 10000
print(f"{'martingale_anti_filtered v5 (sans regime)':<45} {f'+{net:.0f}':>10} {f'{max_dd_pct:.2f}':>7} {'1.17':>5} {len(trades):>7}")

print(f"\nDelta:")
print(f"  Net: +${net-5200:.0f} ({(net/5200-1)*100:.0f}% de plus sans filtre)")
print(f"  Trades: +{len(trades)-370} ({len(trades)/370:.1f}x)")
print(f"  DD: +{max_dd_pct-11.84:.1f} points")

# Ratio Return/DD
print(f"\n--- Ratio Return/DD ---")
print(f"regime_pyramid v2:        5200 / 11.84 = {5200/11.84:.0f}")
print(f"anti_filtered v5:         {net:.0f} / {max_dd_pct:.2f} = {net/max_dd_pct:.0f}")

# Par annee avec regime_pyramid pour comparaison
print(f"\n--- COMPARAISON PAR ANNEE (regime v2 vs anti v5) ---")
ref_regime = {
    2023: (+1114.70, 157),
    2024: (+3162.95, 96),
    2025: (-135.68, 94),
    2026: (+641.93, 23),
}
print(f"{'Year':>5} {'regime_net':>11} {'antif_net':>11} {'regime_N':>9} {'antif_N':>9} {'Delta$':>10}")
for y in sorted(by_year.keys()):
    d = by_year[y]
    anti_net = d['gw'] - d['gl']
    reg_net, reg_n = ref_regime.get(y, (0, 0))
    delta = anti_net - reg_net
    print(f"{y:>5} {reg_net:>+11.2f} {anti_net:>+11.2f} {reg_n:>9} {d['n']:>9} {delta:>+10.2f}")
