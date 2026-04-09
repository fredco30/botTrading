"""
Analyse du regime marche 2025 vs 2023-2024 sur EURUSD H1.
Verifier l'hypothese "Trump news -> chaos" avec les donnees reelles.
"""
from datetime import datetime
from collections import defaultdict
import statistics

BARS_PATH = r"C:\Users\projets\botTrading\EURUSD60_cut.csv"
TRADES_PATH = r"C:\Users\projets\botTrading\resultats_anti-martingale.txt"

# ============================================================
# Charger les bougies H1 avec ATR calcule
# ============================================================
bars = []
with open(BARS_PATH, 'r') as f:
    for line in f:
        p = line.strip().split(',')
        if len(p) < 6:
            continue
        try:
            dt = datetime.strptime(p[0]+' '+p[1], '%Y.%m.%d %H:%M')
            bars.append({
                'dt': dt, 'o': float(p[2]), 'h': float(p[3]),
                'l': float(p[4]), 'c': float(p[5])
            })
        except:
            continue

# ATR(14) approximation: True Range sur 14 bars
for i in range(len(bars)):
    if i == 0:
        bars[i]['tr'] = bars[i]['h'] - bars[i]['l']
    else:
        b = bars[i]; prev = bars[i-1]
        tr = max(b['h']-b['l'], abs(b['h']-prev['c']), abs(b['l']-prev['c']))
        bars[i]['tr'] = tr

for i in range(len(bars)):
    if i < 14:
        bars[i]['atr'] = bars[i]['tr']
    else:
        bars[i]['atr'] = sum(bars[j]['tr'] for j in range(i-13, i+1)) / 14

# ============================================================
# ATR moyen par annee / mois
# ============================================================
print("=" * 70)
print("ATR EURUSD H1 PAR PERIODE")
print("=" * 70)

by_year = defaultdict(list)
by_month = defaultdict(list)
for b in bars:
    if b['atr'] == 0:
        continue
    y = b['dt'].year
    ym = b['dt'].strftime('%Y-%m')
    by_year[y].append(b['atr'] * 10000)  # en pips
    by_month[ym].append(b['atr'] * 10000)

print(f"{'Annee':>6} {'N bars':>7} {'ATR moy':>9} {'ATR median':>11} {'ATR p90':>9} {'ATR max':>9}")
for y in sorted(by_year.keys()):
    atrs = by_year[y]
    atrs_sorted = sorted(atrs)
    avg = sum(atrs)/len(atrs)
    med = atrs_sorted[len(atrs_sorted)//2]
    p90 = atrs_sorted[int(len(atrs_sorted)*0.9)]
    mx = max(atrs)
    print(f"{y:>6} {len(atrs):>7} {avg:>9.2f} {med:>11.2f} {p90:>9.2f} {mx:>9.2f}")

# ============================================================
# Par mois
# ============================================================
print(f"\n--- ATR MOYEN PAR MOIS (pips) ---")
print(f"{'Mois':>8} {'ATR moy':>9} {'ATR p90':>9} {'Delta vs 2023':>14}")
base_year_atr = sum(by_year[2023])/len(by_year[2023])
for ym in sorted(by_month.keys()):
    atrs = by_month[ym]
    avg = sum(atrs)/len(atrs)
    p90 = sorted(atrs)[int(len(atrs)*0.9)]
    delta = (avg/base_year_atr - 1) * 100
    marker = ' !' if abs(delta) > 30 else '  '
    print(f"{ym:>8} {avg:>9.2f} {p90:>9.2f} {delta:>+13.1f}% {marker}")

# ============================================================
# Charger les trades anti-mart
# ============================================================
trades_raw = []
with open(TRADES_PATH, 'r', encoding='utf-8', errors='ignore') as f:
    for line in f:
        parts = line.strip().split('\t')
        if len(parts) < 10:
            continue
        try:
            dt = datetime.strptime(parts[1], '%Y.%m.%d %H:%M')
            trades_raw.append({
                'dt': dt, 'action': parts[2], 'ticket': int(parts[3]),
                'lots': float(parts[4]), 'price': float(parts[5]),
                'profit': float(parts[8])
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
            trades.append({
                'open_dt': op['dt'], 'profit': t['profit'],
                'result': t['action']
            })
            del opens[t['ticket']]

# Index bars par dt pour lookup rapide
bar_idx = {b['dt']: i for i, b in enumerate(bars)}

# ============================================================
# Correlation: ATR au moment du trade vs gagnant/perdant
# ============================================================
print("\n" + "=" * 70)
print("ATR AU MOMENT DU TRADE - WR PAR BUCKET")
print("=" * 70)

# Pour chaque trade, trouver l'ATR au moment de l'open
for t in trades:
    # Aligner sur l'heure H1
    key = t['open_dt'].replace(minute=0, second=0, microsecond=0)
    if key in bar_idx:
        i = bar_idx[key]
        t['atr_at_open'] = bars[i]['atr'] * 10000  # pips
    else:
        t['atr_at_open'] = None

# Buckets ATR
buckets = [(0, 5), (5, 10), (10, 15), (15, 20), (20, 25), (25, 30), (30, 40), (40, 60), (60, 200)]
stats = defaultdict(lambda: {'n': 0, 'wins': 0, 'pnl': 0})
for t in trades:
    if t['atr_at_open'] is None:
        continue
    a = t['atr_at_open']
    for lo, hi in buckets:
        if lo <= a < hi:
            key = (lo, hi)
            stats[key]['n'] += 1
            if t['profit'] > 0:
                stats[key]['wins'] += 1
            stats[key]['pnl'] += t['profit']
            break

print(f"{'ATR bucket (pips)':>20} {'N':>5} {'WR%':>6} {'PnL':>10}")
for (lo, hi), d in sorted(stats.items()):
    wr = d['wins']/d['n']*100 if d['n'] else 0
    print(f"  [{lo:>3} ; {hi:>3}[ pips {d['n']:>5} {wr:>6.1f} {d['pnl']:>+10.2f}")

# ============================================================
# Meme analyse mais par annee (2023 vs 2024 vs 2025 vs 2026)
# ============================================================
print(f"\n--- CORRELATION ATR x WR PAR ANNEE ---")
for year in [2023, 2024, 2025, 2026]:
    tyear = [t for t in trades if t['open_dt'].year == year and t['atr_at_open'] is not None]
    if not tyear:
        continue
    atrs = sorted([t['atr_at_open'] for t in tyear])
    avg = sum(atrs)/len(atrs)
    print(f"\n{year}: {len(tyear)} trades")
    print(f"  ATR moyen au trade: {avg:.1f} pips")
    # WR sur ATR bas vs haut (median split)
    median = atrs[len(atrs)//2]
    low_atr = [t for t in tyear if t['atr_at_open'] <= median]
    high_atr = [t for t in tyear if t['atr_at_open'] > median]
    for name, grp in [('ATR bas (< median)', low_atr), ('ATR haut (> median)', high_atr)]:
        if not grp:
            continue
        wins = sum(1 for t in grp if t['profit'] > 0)
        pnl = sum(t['profit'] for t in grp)
        wr = wins/len(grp)*100
        print(f"  {name}: N={len(grp)} WR={wr:.1f}% PnL={pnl:+.2f}")

# ============================================================
# Simulation: filtre ATR > seuil
# ============================================================
print("\n" + "=" * 70)
print("SIMULATION: filtre ATR > seuil (en multiples de ATR moyen 2023-2024)")
print("=" * 70)

# ATR moyen de reference (2023+2024)
ref_atrs = [b['atr']*10000 for b in bars if b['dt'].year in [2023, 2024] and b['atr'] > 0]
ref_mean = sum(ref_atrs)/len(ref_atrs)
print(f"ATR moyen reference 2023-2024: {ref_mean:.1f} pips")

print(f"\n{'Seuil':>10} {'Trades pris':>12} {'Skipped':>9} {'WR%':>6} {'PnL':>10} {'PF':>6}")

for mult in [None, 2.0, 1.8, 1.6, 1.5, 1.4, 1.3, 1.2, 1.1]:
    if mult is None:
        threshold = None
        label = 'No filter'
    else:
        threshold = ref_mean * mult
        label = f'>{mult:.1f}x mean'

    taken = [t for t in trades if t['atr_at_open'] is None or threshold is None or t['atr_at_open'] <= threshold]
    skipped = len(trades) - len(taken)

    if not taken:
        continue
    wins = [t for t in taken if t['profit'] > 0]
    losses = [t for t in taken if t['profit'] <= 0]
    gw = sum(t['profit'] for t in wins)
    gl = abs(sum(t['profit'] for t in losses))
    pf = gw/gl if gl else 0
    net = gw - gl
    wr = len(wins)/len(taken)*100

    print(f"{label:>10} {len(taken):>12} {skipped:>9} {wr:>6.1f} {net:>+10.2f} {pf:>6.2f}")

# Par annee avec filtre optimal
print(f"\n--- AVEC FILTRE ATR > 1.5x mean PAR ANNEE ---")
threshold = ref_mean * 1.5
for year in [2023, 2024, 2025, 2026]:
    taken = [t for t in trades if t['open_dt'].year == year and (t['atr_at_open'] is None or t['atr_at_open'] <= threshold)]
    skipped = sum(1 for t in trades if t['open_dt'].year == year) - len(taken)
    if not taken:
        continue
    wins = [t for t in taken if t['profit'] > 0]
    pnl = sum(t['profit'] for t in taken)
    wr = len(wins)/len(taken)*100
    print(f"{year}: pris={len(taken)} skip={skipped} WR={wr:.1f}% PnL={pnl:+.2f}")
