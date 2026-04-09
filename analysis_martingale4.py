"""
Analyse complete du backtest martingale_classic_filtered.mq4 (resultats_martingale4).
Identifie cycles, WR par niveau, DD, et les causes de perte.
"""
from datetime import datetime
from collections import defaultdict

PATH = r"C:\Users\projets\botTrading\resultats_martingale4.txt"

# ============================================================
# 1. Parse trades
# ============================================================
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
                'type': op['action'], 'lots': op['lots'],
                'open_dt': op['dt'], 'close_dt': t['dt'],
                'open_price': op['price'], 'sl': op['sl'], 'tp': op['tp'],
                'profit': t['profit'], 'balance_after': t['balance'],
                'result': t['action'],
                'duration_min': (t['dt'] - op['dt']).total_seconds() / 60.0
            })
            del opens[t['ticket']]

print(f"Total trades: {len(trades)}")
print(f"Periode: {trades[0]['open_dt']} -> {trades[-1]['close_dt']}")
print(f"Balance: 10000 -> {trades[-1]['balance_after']:.2f}")
print(f"Resultat: {trades[-1]['balance_after']-10000:+.2f} USD ({(trades[-1]['balance_after']-10000)/100:.1f}%)")

# ============================================================
# 2. Detecter les cycles et leur niveau
# ============================================================
# Un Mg est un trade dont le lot = 2x lot precedent, meme direction, peu de temps apres un SL
# Un INIT est un trade independant

for i, tr in enumerate(trades):
    tr['level'] = 0  # INIT par defaut
    tr['cycle_id'] = 0

cycle_id = 0
for i, tr in enumerate(trades):
    if i == 0:
        cycle_id = 1
        tr['cycle_id'] = cycle_id
        tr['level'] = 0
        continue
    prev = trades[i-1]
    # Si prev a perdu et meme direction et lot ~2x -> c'est un Mg du meme cycle
    if (prev['result'] == 's/l' and
        prev['type'] == tr['type'] and
        tr['lots'] > prev['lots'] * 1.5 and
        tr['lots'] < prev['lots'] * 2.5):
        tr['cycle_id'] = prev['cycle_id']
        tr['level'] = prev['level'] + 1
    else:
        cycle_id += 1
        tr['cycle_id'] = cycle_id
        tr['level'] = 0

init = [t for t in trades if t['level'] == 0]
mg1  = [t for t in trades if t['level'] == 1]
mg2  = [t for t in trades if t['level'] == 2]
mg3  = [t for t in trades if t['level'] >= 3]

print(f"\n--- REPARTITION PAR NIVEAU ---")
print(f"INIT (L0): {len(init)}")
print(f"Mg1  (L1): {len(mg1)}")
print(f"Mg2  (L2): {len(mg2)}")
print(f"Mg3+ (L3+): {len(mg3)}")

# WR par niveau
def wr_stats(trs, label):
    if not trs:
        print(f"{label}: aucun")
        return
    wins = [t for t in trs if t['profit'] > 0]
    losses = [t for t in trs if t['profit'] <= 0]
    gw = sum(t['profit'] for t in wins)
    gl = abs(sum(t['profit'] for t in losses))
    pf = gw/gl if gl else 0
    wr = len(wins)/len(trs)*100
    net = gw - gl
    print(f"{label}: N={len(trs):4d} | WR={wr:5.1f}% | PF={pf:.2f} | Net={net:+9.2f} | avgW={gw/len(wins) if wins else 0:+7.2f} | avgL={-gl/len(losses) if losses else 0:+7.2f}")

print("\n--- WR PAR NIVEAU ---")
wr_stats(init, "INIT (L0)")
wr_stats(mg1,  "Mg1  (L1)")
wr_stats(mg2,  "Mg2  (L2)")
wr_stats(mg3,  "Mg3+ (L3)")

# ============================================================
# 3. Analyse par cycle complet
# ============================================================
cycles = defaultdict(list)
for t in trades:
    cycles[t['cycle_id']].append(t)

cycle_stats = []
for cid in sorted(cycles.keys()):
    c = cycles[cid]
    net = sum(t['profit'] for t in c)
    max_level = max(t['level'] for t in c)
    last_result = c[-1]['result']
    # Classer
    if last_result == 't/p':
        outcome = 'win'  # Mg a gagne ou INIT a gagne directement
    else:
        outcome = 'lost'  # Dernier trade = SL (cap atteint ou timeout)
    cycle_stats.append({
        'id': cid, 'n': len(c), 'net': net,
        'max_level': max_level, 'outcome': outcome
    })

n_cycles = len(cycle_stats)
n_win = sum(1 for c in cycle_stats if c['outcome'] == 'win')
n_lost = n_cycles - n_win
print(f"\n--- ANALYSE PAR CYCLE ---")
print(f"Total cycles: {n_cycles}")
print(f"Cycles gagnants: {n_win} ({n_win/n_cycles*100:.1f}%)")
print(f"Cycles perdants: {n_lost} ({n_lost/n_cycles*100:.1f}%)")

# Par niveau max atteint
by_max_level = defaultdict(lambda: {'n': 0, 'net': 0, 'wins': 0})
for c in cycle_stats:
    by_max_level[c['max_level']]['n'] += 1
    by_max_level[c['max_level']]['net'] += c['net']
    if c['outcome'] == 'win':
        by_max_level[c['max_level']]['wins'] += 1

print(f"\n--- CYCLES PAR NIVEAU MAX ATTEINT ---")
print(f"{'Lvl':>3} {'N':>5} {'Wins':>5} {'WR%':>6} {'NetTotal':>10} {'NetMoyen':>10}")
for lvl in sorted(by_max_level.keys()):
    d = by_max_level[lvl]
    wr = d['wins']/d['n']*100 if d['n'] else 0
    avg = d['net']/d['n'] if d['n'] else 0
    print(f"{lvl:>3} {d['n']:>5} {d['wins']:>5} {wr:>6.1f} {d['net']:>+10.2f} {avg:>+10.2f}")

# Distribution du net par cycle
print(f"\n--- DISTRIBUTION NET PAR CYCLE ---")
buckets = [(-10000,-500),(-500,-200),(-200,-100),(-100,-50),(-50,0),(0,50),(50,100),(100,200),(200,500),(500,10000)]
for lo, hi in buckets:
    count = sum(1 for c in cycle_stats if lo <= c['net'] < hi)
    net_in_bucket = sum(c['net'] for c in cycle_stats if lo <= c['net'] < hi)
    print(f"  [{lo:+6} ; {hi:+6}[: {count:4d} cycles | net bucket = {net_in_bucket:+9.2f}")

# ============================================================
# 4. Drawdown
# ============================================================
balances = [10000] + [t['balance_after'] for t in trades]
peak = balances[0]
max_dd_pct = 0
max_dd_abs = 0
for b in balances:
    if b > peak:
        peak = b
    dd = peak - b
    dd_pct = dd/peak*100
    if dd_pct > max_dd_pct:
        max_dd_pct = dd_pct
        max_dd_abs = dd

print(f"\n--- DRAWDOWN ---")
print(f"Max DD: {max_dd_abs:.2f} USD ({max_dd_pct:.1f}%)")
print(f"Peak: {peak:.2f}")

# ============================================================
# 5. Par annee
# ============================================================
print(f"\n--- PAR ANNEE ---")
by_year = defaultdict(lambda: {'n': 0, 'pnl': 0, 'wins': 0})
for t in trades:
    y = t['close_dt'].year
    by_year[y]['n'] += 1
    by_year[y]['pnl'] += t['profit']
    if t['profit'] > 0: by_year[y]['wins'] += 1
for y in sorted(by_year.keys()):
    d = by_year[y]
    wr = d['wins']/d['n']*100
    print(f"{y}: N={d['n']:4d} | PnL={d['pnl']:+9.2f} | WR={wr:4.1f}%")

# ============================================================
# 6. Pertes consecutives de cycles
# ============================================================
streak = 0
max_streak = 0
worst_streak_val = 0
cur_val = 0
for c in cycle_stats:
    if c['outcome'] == 'lost':
        streak += 1
        cur_val += c['net']
        if streak > max_streak:
            max_streak = streak
            worst_streak_val = cur_val
    else:
        streak = 0
        cur_val = 0

print(f"\n--- STREAKS DE CYCLES PERDANTS ---")
print(f"Max cycles perdants consecutifs: {max_streak}")
print(f"Pire cumul sur streak: {worst_streak_val:.2f}")

# ============================================================
# 7. Comparaison avec l'analyse V1 (baseline reverse)
# ============================================================
print(f"\n--- COMPARAISON V1 vs V4 ---")
print(f"{'Metrique':<25} {'V1 Reverse':>15} {'V4 Classic':>15}")
print(f"{'Net':<25} {'-4236.80':>15} {trades[-1]['balance_after']-10000:>+15.2f}")
print(f"{'DD max':<25} {'66.9%':>15} {f'{max_dd_pct:.1f}%':>15}")
print(f"{'Trades':<25} {'2285':>15} {len(trades):>15}")
print(f"{'PF global':<25}", end='')
all_wins = [t for t in trades if t['profit'] > 0]
all_losses = [t for t in trades if t['profit'] <= 0]
gw = sum(t['profit'] for t in all_wins)
gl = abs(sum(t['profit'] for t in all_losses))
print(f"{'0.96':>15} {gw/gl if gl else 0:>15.2f}")
print(f"{'Cycles':<25}", end='')
print(f"{'N/A':>15} {n_cycles:>15}")
print(f"{'Cycles WR':<25}", end='')
print(f"{'N/A':>15} {f'{n_win/n_cycles*100:.1f}%':>15}")

# ============================================================
# 8. Les pires cycles
# ============================================================
print(f"\n--- TOP 10 PIRES CYCLES ---")
sorted_cycles = sorted(cycle_stats, key=lambda c: c['net'])[:10]
for c in sorted_cycles:
    first = cycles[c['id']][0]
    print(f"Cycle #{c['id']:4d} lvl_max={c['max_level']} net={c['net']:+.2f} ({first['open_dt']})")
