"""
Analyse walk-forward du backtest anti-martingale 6 ans (2020-04 -> 2026-04).
Objectif: trouver quelles cellules H*J sont robustes sur toutes les periodes.
"""
from datetime import datetime
from collections import defaultdict

PATH = r"C:\Users\projets\botTrading\resultats6ans_anti-martingale_filtreATR_Max2.txt"

# Parse
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

# ============================================================
# Par annee - stats completes
# ============================================================
print("\n" + "=" * 80)
print("DECOMPOSITION PAR ANNEE")
print("=" * 80)
by_year = defaultdict(lambda: {'n': 0, 'wins': 0, 'gw': 0, 'gl': 0, 'trades': []})
for t in trades:
    y = t['open_dt'].year
    by_year[y]['n'] += 1
    by_year[y]['trades'].append(t)
    if t['profit'] > 0:
        by_year[y]['wins'] += 1
        by_year[y]['gw'] += t['profit']
    else:
        by_year[y]['gl'] += abs(t['profit'])

print(f"{'Year':>5} {'N':>5} {'WR%':>6} {'Net':>10} {'Gross W':>10} {'Gross L':>10} {'PF':>5}")
for y in sorted(by_year.keys()):
    d = by_year[y]
    wr = d['wins']/d['n']*100
    net = d['gw'] - d['gl']
    pf = d['gw']/d['gl'] if d['gl'] else 0
    print(f"{y:>5} {d['n']:>5} {wr:>6.1f} {net:>+10.2f} {d['gw']:>10.2f} -{d['gl']:>9.2f} {pf:>5.2f}")

# ============================================================
# Balance trajectory + DD par periode
# ============================================================
balances = [10000] + [t['balance_after'] for t in trades]
peak = balances[0]
peak_date = trades[0]['open_dt']
max_dd_pct = 0
max_dd_abs = 0
max_dd_start = None
max_dd_end = None
cur_peak = balances[0]
cur_peak_date = trades[0]['open_dt']

for i, b in enumerate(balances[1:], 1):
    t = trades[i-1]
    if b > cur_peak:
        cur_peak = b
        cur_peak_date = t['close_dt']
    dd = cur_peak - b
    dd_pct = dd/cur_peak*100 if cur_peak > 0 else 0
    if dd_pct > max_dd_pct:
        max_dd_pct = dd_pct
        max_dd_abs = dd
        max_dd_start = cur_peak_date
        max_dd_end = t['close_dt']

print(f"\n--- DRAWDOWN MAX ---")
print(f"DD abs: {max_dd_abs:.2f} USD ({max_dd_pct:.1f}%)")
print(f"Du {max_dd_start} au {max_dd_end}")

# ============================================================
# Courbe d'equity cumulative par mois
# ============================================================
print(f"\n--- NET CUMULATIF PAR SEMESTRE ---")
by_sem = defaultdict(lambda: 0)
for t in trades:
    y = t['open_dt'].year
    sem = 'H1' if t['open_dt'].month <= 6 else 'H2'
    key = f"{y}-{sem}"
    by_sem[key] += t['profit']

cumul = 0
for key in sorted(by_sem.keys()):
    cumul += by_sem[key]
    pnl = by_sem[key]
    mark = '+' if pnl > 0 else '-'
    bar = '#' * min(20, int(abs(pnl)/200))
    print(f"  {key}: {pnl:>+9.2f} cumul={10000+cumul:>9.2f} {mark} {bar}")

# ============================================================
# Calibration toxic cells PAR sous-periode
# ============================================================
print(f"\n" + "=" * 80)
print("CALIBRATION TOXIC CELLS - walk-forward")
print("=" * 80)

def get_toxic_cells(trades_list, min_n=5, max_pnl=-50):
    """Retourne les cellules H*J toxiques sur ce set de trades."""
    mat = defaultdict(lambda: {'n': 0, 'pnl': 0})
    for t in trades_list:
        d = t['open_dt'].weekday()  # 0=Lun, 4=Ven
        h = t['open_dt'].hour
        if d >= 5: continue  # skip weekend
        mat[(d, h)]['n'] += 1
        mat[(d, h)]['pnl'] += t['profit']

    toxic = set()
    for (d, h), stats in mat.items():
        if stats['n'] >= min_n and stats['pnl'] < max_pnl:
            toxic.add((d, h))
    return toxic, mat

# Split 1: 2020-2022 (train) vs 2023-2026 (test)
split1_train = [t for t in trades if t['open_dt'].year in [2020, 2021, 2022]]
split1_test  = [t for t in trades if t['open_dt'].year in [2023, 2024, 2025, 2026]]

# Split 2: 2023-2026 (train) vs 2020-2022 (test)
split2_train = split1_test
split2_test  = split1_train

toxic1, mat1 = get_toxic_cells(split1_train, min_n=5, max_pnl=-50)
toxic2, mat2 = get_toxic_cells(split2_train, min_n=5, max_pnl=-50)

print(f"\nSplit 1 (train 2020-2022, N={len(split1_train)}):")
print(f"  Toxic cells trouvees: {len(toxic1)}")
print(f"\nSplit 2 (train 2023-2026, N={len(split2_train)}):")
print(f"  Toxic cells trouvees: {len(toxic2)}")

# Intersection - cellules robustes
robust_toxic = toxic1 & toxic2
only1 = toxic1 - toxic2
only2 = toxic2 - toxic1
print(f"\nCellules ROBUSTES (communes): {len(robust_toxic)}")
print(f"Cellules seulement 2020-2022: {len(only1)}")
print(f"Cellules seulement 2023-2026: {len(only2)}")

jours = ['Lun', 'Mar', 'Mer', 'Jeu', 'Ven']
print(f"\n--- CELLULES ROBUSTES (train OK sur 2 splits) ---")
for (d, h) in sorted(robust_toxic):
    pnl1 = mat1[(d, h)]['pnl']
    pnl2 = mat2[(d, h)]['pnl']
    n1 = mat1[(d, h)]['n']
    n2 = mat2[(d, h)]['n']
    print(f"  {jours[d]} {h:>2}h: 2020-22 pnl={pnl1:+8.2f} (n={n1}) | 2023-26 pnl={pnl2:+8.2f} (n={n2})")

print(f"\n--- CELLULES NON-ROBUSTES (train 2020-2022 seulement) ---")
for (d, h) in sorted(only1):
    pnl1 = mat1[(d, h)]['pnl']
    pnl2 = mat2[(d, h)]['pnl'] if (d, h) in mat2 else 0
    n1 = mat1[(d, h)]['n']
    n2 = mat2[(d, h)]['n'] if (d, h) in mat2 else 0
    mark = '!!' if pnl2 > 0 else ''
    print(f"  {jours[d]} {h:>2}h: 2020-22 pnl={pnl1:+8.2f} (n={n1}) | 2023-26 pnl={pnl2:+8.2f} (n={n2}) {mark}")

print(f"\n--- CELLULES NON-ROBUSTES (train 2023-2026 seulement) ---")
for (d, h) in sorted(only2):
    pnl2 = mat2[(d, h)]['pnl']
    pnl1 = mat1[(d, h)]['pnl'] if (d, h) in mat1 else 0
    n2 = mat2[(d, h)]['n']
    n1 = mat1[(d, h)]['n'] if (d, h) in mat1 else 0
    mark = '!!' if pnl1 > 0 else ''
    print(f"  {jours[d]} {h:>2}h: 2023-26 pnl={pnl2:+8.2f} (n={n2}) | 2020-22 pnl={pnl1:+8.2f} (n={n1}) {mark}")

# ============================================================
# Simulation des 3 filtres
# ============================================================
print(f"\n" + "=" * 80)
print("SIMULATION DES FILTRES SUR 6 ANS")
print("=" * 80)

# Cellules originales (27) - celles du code actuel
ORIGINAL_CELLS = {
    (1, 10), (1, 16), (1, 18),
    (2, 8), (2, 10), (2, 12), (2, 13), (2, 14), (2, 19), (2, 20), (2, 21),
    (3, 8), (3, 14), (3, 19), (3, 21),
    (4, 11), (4, 12), (4, 15), (4, 18), (4, 20),
    (5, 11), (5, 12), (5, 13), (5, 14), (5, 16), (5, 17), (5, 18),
}

def simulate_filter(trades_list, toxic_set, name):
    """Simule: retire les trades dans les cellules toxiques."""
    kept = [t for t in trades_list if (t['open_dt'].weekday(), t['open_dt'].hour) not in toxic_set]
    skipped = len(trades_list) - len(kept)
    if not kept:
        return None
    wins = [t for t in kept if t['profit'] > 0]
    losses = [t for t in kept if t['profit'] <= 0]
    gw = sum(t['profit'] for t in wins)
    gl = abs(sum(t['profit'] for t in losses))
    pf = gw/gl if gl else 0
    wr = len(wins)/len(kept)*100
    net = gw - gl
    print(f"\n{name} ({len(toxic_set)} cellules, skip {skipped}):")
    print(f"  N={len(kept)} WR={wr:.1f}% PF={pf:.2f} Net={net:+.2f}")
    # Par annee
    by_y = defaultdict(lambda: 0)
    for t in kept:
        by_y[t['open_dt'].year] += t['profit']
    for y in sorted(by_y.keys()):
        print(f"    {y}: {by_y[y]:+.2f}")
    return net, pf, wr

simulate_filter(trades, set(), "AUCUN FILTRE H*J")
simulate_filter(trades, ORIGINAL_CELLS, "FILTRE ORIGINAL (27 cellules)")
simulate_filter(trades, robust_toxic, f"FILTRE ROBUSTE ({len(robust_toxic)} cellules communes)")
simulate_filter(trades, toxic1, f"FILTRE 2020-2022 CALIBRATION ({len(toxic1)} cellules)")
simulate_filter(trades, toxic2, f"FILTRE 2023-2026 CALIBRATION ({len(toxic2)} cellules)")

# Union: toutes cellules jamais toxiques
union_toxic = toxic1 | toxic2
simulate_filter(trades, union_toxic, f"FILTRE UNION ({len(union_toxic)} cellules)")
