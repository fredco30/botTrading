"""
Validation du seuil ATR fixe: quel pips-max donne le meilleur resultat
sur la sequence reelle des trades de l'anti-martingale (baseline).
"""
from datetime import datetime
from collections import defaultdict

BARS_PATH = r"C:\Users\projets\botTrading\EURUSD60_cut.csv"
TRADES_PATH = r"C:\Users\projets\botTrading\resultats_anti-martingale.txt"

# Charger bougies + ATR14
bars = []
with open(BARS_PATH, 'r') as f:
    for line in f:
        p = line.strip().split(',')
        if len(p) < 6: continue
        try:
            dt = datetime.strptime(p[0]+' '+p[1], '%Y.%m.%d %H:%M')
            bars.append({'dt': dt, 'o': float(p[2]), 'h': float(p[3]),
                         'l': float(p[4]), 'c': float(p[5])})
        except: continue

# ATR14
for i in range(len(bars)):
    if i == 0:
        bars[i]['tr'] = bars[i]['h'] - bars[i]['l']
    else:
        b = bars[i]; prev = bars[i-1]
        bars[i]['tr'] = max(b['h']-b['l'], abs(b['h']-prev['c']), abs(b['l']-prev['c']))
for i in range(len(bars)):
    if i < 14:
        bars[i]['atr'] = bars[i]['tr']
    else:
        bars[i]['atr'] = sum(bars[j]['tr'] for j in range(i-13, i+1)) / 14

bar_idx = {b['dt']: i for i, b in enumerate(bars)}

# Charger trades
trades_raw = []
with open(TRADES_PATH, 'r', encoding='utf-8', errors='ignore') as f:
    for line in f:
        parts = line.strip().split('\t')
        if len(parts) < 10: continue
        try:
            dt = datetime.strptime(parts[1], '%Y.%m.%d %H:%M')
            trades_raw.append({'dt': dt, 'action': parts[2], 'ticket': int(parts[3]),
                               'lots': float(parts[4]), 'profit': float(parts[8])})
        except: continue

opens = {}
trades = []
for t in trades_raw:
    if t['action'] in ('buy', 'sell'):
        opens[t['ticket']] = t
    elif t['action'] in ('s/l', 't/p'):
        if t['ticket'] in opens:
            op = opens[t['ticket']]
            # ATR au moment de l'open
            key = op['dt'].replace(minute=0, second=0, microsecond=0)
            atr_pips = None
            if key in bar_idx:
                atr_pips = bars[bar_idx[key]]['atr'] * 10000
            trades.append({
                'open_dt': op['dt'], 'profit': t['profit'],
                'atr_pips': atr_pips
            })
            del opens[t['ticket']]

# Tester plusieurs seuils fixes en pips
print("=" * 80)
print("SEUIL ATR FIXE - Impact sur PnL, WR, PF")
print("=" * 80)
print(f"{'Max pips':>10} {'Pris':>6} {'Skip':>5} {'WR%':>6} {'Net':>10} {'PF':>6} {'2023':>9} {'2024':>9} {'2025':>9} {'2026':>9}")

for max_pips in [None, 25, 22, 20, 18, 16, 15, 14, 13, 12, 11, 10]:
    if max_pips is None:
        taken = trades
        label = 'Off'
    else:
        taken = [t for t in trades if t['atr_pips'] is None or t['atr_pips'] <= max_pips]
        label = f'{max_pips}'

    wins = [t for t in taken if t['profit'] > 0]
    losses = [t for t in taken if t['profit'] <= 0]
    gw = sum(t['profit'] for t in wins)
    gl = abs(sum(t['profit'] for t in losses))
    pf = gw/gl if gl else 0
    net = gw - gl
    wr = len(wins)/len(taken)*100 if taken else 0
    skipped = len(trades) - len(taken)

    # Par annee
    by_year = defaultdict(lambda: 0)
    for t in taken:
        by_year[t['open_dt'].year] += t['profit']

    print(f"{label:>10} {len(taken):>6} {skipped:>5} {wr:>6.1f} {net:>+10.2f} {pf:>6.3f} "
          f"{by_year[2023]:>+9.0f} {by_year[2024]:>+9.0f} {by_year[2025]:>+9.0f} {by_year[2026]:>+9.0f}")
