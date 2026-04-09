"""
Analyse 2: explorer filtres, pattern des REV gagnants, distribution pertes.
"""
from datetime import datetime
from collections import defaultdict

PATH = r"C:\Users\projets\botTrading\resultats_martingale3.txt"

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
                'type': op['action'], 'lots': op['lots'],
                'open_dt': op['dt'], 'close_dt': t['dt'],
                'open_price': op['price'], 'sl': op['sl'], 'tp': op['tp'],
                'profit': t['profit'], 'balance_after': t['balance'],
                'result': t['action'],
                'duration_min': (t['dt'] - op['dt']).total_seconds() / 60.0
            })
            del opens[t['ticket']]

# Classifier
for i, tr in enumerate(trades):
    tr['kind'] = 'INIT'
    if i > 0 and trades[i-1]['result'] == 's/l':
        ratio = tr['lots'] / trades[i-1]['lots'] if trades[i-1]['lots'] > 0 else 0
        gap = (tr['open_dt'] - trades[i-1]['close_dt']).total_seconds() / 60.0
        if 1.5 < ratio < 2.5 and gap < 2880:
            tr['kind'] = 'REV'
            tr['prev_init'] = trades[i-1]

init_trades = [t for t in trades if t['kind'] == 'INIT']
rev_trades = [t for t in trades if t['kind'] == 'REV']

# ==================================================
# 1. FILTRE HEURES/JOURS sur INIT seul
# ==================================================
print("=" * 60)
print("1. SIMULATION INIT AVEC FILTRES")
print("=" * 60)

# Heures blockees identifiees
bad_hours = {8, 12, 14, 18, 20, 21}
bad_days = {1, 4}  # Mardi=1, Vendredi=4

def sim(trs, name, hour_filter=None, day_filter=None):
    filt = []
    for t in trs:
        h = t['open_dt'].hour
        d = t['open_dt'].weekday()
        if hour_filter and h in hour_filter:
            continue
        if day_filter and d in day_filter:
            continue
        filt.append(t)
    if not filt:
        print(f"{name}: vide")
        return
    wins = [x for x in filt if x['profit'] > 0]
    losses = [x for x in filt if x['profit'] <= 0]
    gw = sum(x['profit'] for x in wins)
    gl = abs(sum(x['profit'] for x in losses))
    pf = gw/gl if gl else 0
    wr = len(wins)/len(filt)*100
    net = gw - gl
    print(f"{name}: N={len(filt):4d} | WR={wr:5.1f}% | PF={pf:.2f} | Net={net:+8.2f}")

sim(init_trades, "Baseline (tout)")
sim(init_trades, "Ex heures   ", hour_filter=bad_hours)
sim(init_trades, "Ex jours    ", day_filter=bad_days)
sim(init_trades, "Ex H+J      ", hour_filter=bad_hours, day_filter=bad_days)

# Test sessions
london = {8,9,10,11}
ny = {13,14,15,16,17}
asia = {0,1,2,3,4,5,6,7}
sim(init_trades, "London only ", hour_filter=set(range(24))-london)
sim(init_trades, "NY only     ", hour_filter=set(range(24))-ny)
sim(init_trades, "London+NY   ", hour_filter=set(range(24))-(london|ny))

# ==================================================
# 2. MATRICE HEURE x JOUR
# ==================================================
print("\n" + "=" * 60)
print("2. MATRICE HEURE x JOUR (INIT)")
print("=" * 60)
mat = defaultdict(lambda: defaultdict(lambda: {'n': 0, 'pnl': 0}))
for t in init_trades:
    h = t['open_dt'].hour
    d = t['open_dt'].weekday()
    mat[d][h]['n'] += 1
    mat[d][h]['pnl'] += t['profit']

jours = ['Lun', 'Mar', 'Mer', 'Jeu', 'Ven']
hours = sorted(set(h for t in init_trades for h in [t['open_dt'].hour]))
print(f"{'H':>3}", end='')
for j in range(5):
    print(f" {jours[j]:>8}", end='')
print()
for h in hours:
    print(f"{h:>3}", end='')
    for d in range(5):
        pnl = mat[d][h]['pnl']
        n = mat[d][h]['n']
        mark = '+' if pnl > 50 else ('-' if pnl < -50 else '.')
        print(f" {mark}{pnl:>+7.0f}", end='')
    print()

# ==================================================
# 3. ANALYSE DES 69 REV GAGNANTS
# ==================================================
print("\n" + "=" * 60)
print("3. PATTERN DES REV GAGNANTS")
print("=" * 60)

rev_win = [t for t in rev_trades if t['profit'] > 0]
rev_lose = [t for t in rev_trades if t['profit'] <= 0]

# Duree moyenne INIT qui precede un REV
def avg_init_dur(rev_list):
    durs = [r['prev_init']['duration_min'] for r in rev_list if 'prev_init' in r]
    return sum(durs)/len(durs) if durs else 0

print(f"Duree moyenne INIT avant REV gagnant: {avg_init_dur(rev_win):.0f} min ({avg_init_dur(rev_win)/60:.1f}h)")
print(f"Duree moyenne INIT avant REV perdant: {avg_init_dur(rev_lose):.0f} min ({avg_init_dur(rev_lose)/60:.1f}h)")

# Taille perte INIT avant REV gagnant vs perdant
def avg_init_loss(rev_list):
    losses = [abs(r['prev_init']['profit']) for r in rev_list if 'prev_init' in r]
    return sum(losses)/len(losses) if losses else 0

print(f"Perte INIT moyenne avant REV gagnant: {avg_init_loss(rev_win):.2f}")
print(f"Perte INIT moyenne avant REV perdant: {avg_init_loss(rev_lose):.2f}")

# Heure d'ouverture REV gagnant
print("\nHeures REV gagnants vs perdants:")
hw = defaultdict(int)
hl = defaultdict(int)
for r in rev_win:
    hw[r['open_dt'].hour] += 1
for r in rev_lose:
    hl[r['open_dt'].hour] += 1
print(f"{'H':>3} {'Win':>5} {'Lose':>5} {'WR%':>6}")
for h in sorted(set(hw.keys())|set(hl.keys())):
    w = hw[h]; l = hl[h]
    total = w+l
    wr = w/total*100 if total else 0
    print(f"{h:>3} {w:>5} {l:>5} {wr:>6.1f}")

# ==================================================
# 4. DISTRIBUTION DES PERTES CONSECUTIVES (INIT seul)
# ==================================================
print("\n" + "=" * 60)
print("4. DISTRIBUTION PERTES CONSECUTIVES (INIT seul, sans REV)")
print("=" * 60)

streaks = defaultdict(int)
cur = 0
for t in init_trades:
    if t['profit'] <= 0:
        cur += 1
    else:
        if cur > 0:
            streaks[cur] += 1
        cur = 0
if cur > 0:
    streaks[cur] += 1

print(f"{'Streak':>7} {'Count':>6} {'%':>6}")
total_streaks = sum(streaks.values())
for k in sorted(streaks.keys()):
    pct = streaks[k]/total_streaks*100
    print(f"{k:>7} {streaks[k]:>6} {pct:>6.1f}%")

# Probabilites d'atteindre X pertes d'affilee
print("\nProba cumulative d'avoir au moins X pertes d'affilee:")
total_losses = sum(1 for t in init_trades if t['profit'] <= 0)
# Approche: si la streak max = N, combien de fois on a atteint au moins 1,2,3...
for x in range(1, 11):
    count = sum(c for k, c in streaks.items() if k >= x)
    print(f"  >= {x} pertes: {count:4d} fois")

# ==================================================
# 5. CHECK — PEUT-ON AVOIR UN INIT PF > 1.3 ?
# ==================================================
print("\n" + "=" * 60)
print("5. OPTIMISATION EXHAUSTIVE DU FILTRE INIT")
print("=" * 60)

# Tester: retirer les (heure, jour) avec net < -150
toxic_cells = set()
for d in range(5):
    for h in hours:
        pnl = mat[d][h]['pnl']
        n = mat[d][h]['n']
        if pnl < -150 and n >= 5:
            toxic_cells.add((d, h))

filt = [t for t in init_trades if (t['open_dt'].weekday(), t['open_dt'].hour) not in toxic_cells]
wins = [x for x in filt if x['profit'] > 0]
losses = [x for x in filt if x['profit'] <= 0]
gw = sum(x['profit'] for x in wins)
gl = abs(sum(x['profit'] for x in losses))
pf = gw/gl if gl else 0
print(f"Apres retrait cellules toxiques ({len(toxic_cells)} combos H*J):")
print(f"N={len(filt)} | WR={len(wins)/len(filt)*100:.1f}% | PF={pf:.2f} | Net={gw-gl:+.2f}")
print(f"Cellules retirees:")
for d, h in sorted(toxic_cells):
    print(f"  {jours[d]} {h}h (n={mat[d][h]['n']}, pnl={mat[d][h]['pnl']:+.0f})")

# ==================================================
# 6. SIMULATION MARTINGALE CLASSIQUE (meme direction apres loss)
# ==================================================
print("\n" + "=" * 60)
print("6. MARTINGALE CLASSIQUE SIMULEE SUR INIT SEUL")
print("=" * 60)
# On simule: apres chaque SL INIT, on "aurait ouvert" le MEME trade en double
# Comme on n'a pas les trades suivants, on approxime avec la meme distribution
# Plus simple: regarder si trades consecutifs mean-reversent ou trendent
same_dir_after_loss = 0
opp_dir_after_loss = 0
next_win_same = 0
next_loss_same = 0
next_win_opp = 0
next_loss_opp = 0

for i in range(len(init_trades)-1):
    cur = init_trades[i]
    nxt = init_trades[i+1]
    if cur['profit'] > 0:
        continue
    # cur a perdu
    if nxt['type'] == cur['type']:
        same_dir_after_loss += 1
        if nxt['profit'] > 0:
            next_win_same += 1
        else:
            next_loss_same += 1
    else:
        opp_dir_after_loss += 1
        if nxt['profit'] > 0:
            next_win_opp += 1
        else:
            next_loss_opp += 1

print(f"Apres INIT perdant, prochain INIT:")
print(f"  Meme direction : {same_dir_after_loss} fois | WR {next_win_same}/{same_dir_after_loss} = {next_win_same/same_dir_after_loss*100 if same_dir_after_loss else 0:.1f}%")
print(f"  Direction oppo : {opp_dir_after_loss} fois | WR {next_win_opp}/{opp_dir_after_loss} = {next_win_opp/opp_dir_after_loss*100 if opp_dir_after_loss else 0:.1f}%")
