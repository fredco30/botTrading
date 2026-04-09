"""
Analyse du rapport resultats_6ans_finalv3.txt
Verification que les 27 cellules H*J + ATR 15 pips fixe s'appliquent bien.
"""
from datetime import datetime
from collections import defaultdict

PATH = r"C:\Users\projets\botTrading\resultats_6ans_finalv3.txt"

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
    elif t['action'] in ('s/l', 't/p', 'close at stop', 'close'):
        if t['ticket'] in opens:
            op = opens[t['ticket']]
            trades.append({
                'ticket': t['ticket'],
                'type': op['action'],
                'lots': op['lots'],
                'open_dt': op['dt'],
                'close_dt': t['dt'],
                'profit': t['profit'],
                'balance_after': t['balance'],
                'result': t['action']
            })
            del opens[t['ticket']]

print(f"Total trades: {len(trades)}")
print(f"Periode: {trades[0]['open_dt']} -> {trades[-1]['close_dt']}")
print(f"Balance: 10000 -> {trades[-1]['balance_after']:.2f}")
print(f"Net: {trades[-1]['balance_after']-10000:+.2f}")

# ============================================================
# VERIFICATION : est-ce que les cellules toxiques sont actives ?
# ============================================================
TOXIC_CELLS = {
    (1, 10), (1, 16), (1, 18),
    (2, 8), (2, 10), (2, 12), (2, 13), (2, 14), (2, 19), (2, 20), (2, 21),
    (3, 8), (3, 14), (3, 19), (3, 21),
    (4, 11), (4, 12), (4, 15), (4, 18), (4, 20),
    (5, 11), (5, 12), (5, 13), (5, 14), (5, 16), (5, 17), (5, 18),
}

in_toxic = 0
out_toxic = 0
by_cell = defaultdict(int)
for t in trades:
    # Python weekday(): Mon=0, Tue=1, ..., Fri=4
    # MQL4 DayOfWeek(): Mon=1, Tue=2, ..., Fri=5
    # Toxic cells set uses MQL4 convention, donc +1
    d = t['open_dt'].weekday() + 1
    h = t['open_dt'].hour
    if (d, h) in TOXIC_CELLS:
        in_toxic += 1
        by_cell[(d, h)] += 1
    else:
        out_toxic += 1

print(f"\n--- VERIFICATION FILTRE H*J ---")
print(f"Trades dans cellules toxiques: {in_toxic}")
print(f"Trades hors cellules toxiques: {out_toxic}")
print(f"Pourcentage toxic: {in_toxic/len(trades)*100:.1f}%")
if in_toxic > 50:
    print("!!! ALERTE: trop de trades dans les cellules toxiques, le filtre H*J n'est PAS actif !!!")
    print("Top cellules toxiques avec trades:")
    for (d, h), c in sorted(by_cell.items(), key=lambda x: -x[1])[:10]:
        jours = ['Lun', 'Mar', 'Mer', 'Jeu', 'Ven']
        print(f"  {jours[d]} {h}h: {c} trades")
else:
    print("Filtre H*J bien actif")

# ============================================================
# Par annee
# ============================================================
print(f"\n--- PAR ANNEE ---")
by_year = defaultdict(lambda: {'n': 0, 'wins': 0, 'gw': 0, 'gl': 0})
for t in trades:
    y = t['open_dt'].year
    by_year[y]['n'] += 1
    if t['profit'] > 0:
        by_year[y]['wins'] += 1
        by_year[y]['gw'] += t['profit']
    else:
        by_year[y]['gl'] += abs(t['profit'])

print(f"{'Year':>5} {'N':>5} {'WR%':>6} {'Net':>11} {'PF':>6}")
for y in sorted(by_year.keys()):
    d = by_year[y]
    wr = d['wins']/d['n']*100
    net = d['gw']-d['gl']
    pf = d['gw']/d['gl'] if d['gl'] else 0
    print(f"{y:>5} {d['n']:>5} {wr:>6.1f} {net:>+11.2f} {pf:>6.2f}")

# ============================================================
# Drawdown
# ============================================================
balances = [10000] + [t['balance_after'] for t in trades]
peak = balances[0]
max_dd_pct = 0
max_dd_abs = 0
for b in balances:
    if b > peak: peak = b
    dd = peak - b
    dd_pct = dd/peak*100
    if dd_pct > max_dd_pct:
        max_dd_pct = dd_pct
        max_dd_abs = dd

print(f"\n--- DRAWDOWN ---")
print(f"Max DD: {max_dd_abs:.2f} USD ({max_dd_pct:.1f}%)")

# Stats globales
wins = [t for t in trades if t['profit'] > 0]
losses = [t for t in trades if t['profit'] <= 0]
gw = sum(t['profit'] for t in wins)
gl = abs(sum(t['profit'] for t in losses))
pf = gw/gl if gl else 0
wr = len(wins)/len(trades)*100
print(f"\n--- STATS GLOBALES ---")
print(f"WR: {wr:.1f}% ({len(wins)} wins / {len(losses)} losses)")
print(f"PF: {pf:.2f}")
print(f"Gross Win: {gw:.2f} | Gross Loss: -{gl:.2f}")
print(f"Net: {gw-gl:+.2f}")

# Comparaison avec le test precedent 6 ans
print(f"\n--- COMPARAISON 6 ANS ---")
print(f"{'Test':<35} {'Net':>10} {'DD%':>7} {'PF':>6} {'Trades':>7}")
print(f"{'Precedent (rolling ATR)':<35} {'+733.58':>10} {'69.8%':>7} {'1.01':>6} {'2607':>7}")
print(f"{'Actuel (ATR 15 pips fixe)':<35} {trades[-1]['balance_after']-10000:>+10.2f} {f'{max_dd_pct:.1f}%':>7} {pf:>6.2f} {len(trades):>7}")
