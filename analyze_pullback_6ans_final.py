"""
Analyse profonde du test 6 ans avec config ultra-agressive:
L0=2.0, L1=7.0, L2=4.0
Objectif: identifier QUAND s'est produit le DD 47% et les pertes concentrees.
"""
from datetime import datetime
from collections import defaultdict

PATH = r"C:\Users\projets\botTrading\resultats_martingale_EMAPullback6ansFinal.txt"

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
print("DECOMPOSITION PAR ANNEE")
print("=" * 75)
by_year = defaultdict(lambda: {'n': 0, 'wins': 0, 'gw': 0, 'gl': 0, 'start': 0, 'end': 0})
for t in trades:
    y = t['open_dt'].year
    by_year[y]['n'] += 1
    if t['profit'] > 0:
        by_year[y]['wins'] += 1
        by_year[y]['gw'] += t['profit']
    else:
        by_year[y]['gl'] += abs(t['profit'])

# Start/end balance per year
cur_year = None
last_bal = 10000
for t in trades:
    y = t['open_dt'].year
    if y != cur_year:
        if cur_year is not None:
            by_year[cur_year]['end'] = last_bal
        by_year[y]['start'] = last_bal
        cur_year = y
    last_bal = t['balance_after']
by_year[cur_year]['end'] = last_bal

print(f"{'Year':>5} {'N':>5} {'WR%':>6} {'Net':>11} {'PF':>5} {'Start':>10} {'End':>10} {'Gain%':>7}")
for y in sorted(by_year.keys()):
    d = by_year[y]
    wr_y = d['wins']/d['n']*100 if d['n'] else 0
    net = d['gw']-d['gl']
    pf_y = d['gw']/d['gl'] if d['gl'] else 0
    gain_pct = (d['end']-d['start'])/d['start']*100 if d['start'] else 0
    print(f"{y:>5} {d['n']:>5} {wr_y:>6.1f} {net:>+11.2f} {pf_y:>5.2f} {d['start']:>10.2f} {d['end']:>10.2f} {gain_pct:>+6.1f}%")

# DD analysis - find EVERY DD episode
print("\n" + "=" * 75)
print("EPISODES DE DRAWDOWN SIGNIFICATIFS")
print("=" * 75)

balances = [(trades[0]['open_dt'], 10000)]
for t in trades:
    balances.append((t['close_dt'], t['balance_after']))

# Trouver tous les DD > 10%
peak = balances[0][1]
peak_dt = balances[0][0]
current_dd_start = None
dd_episodes = []

for dt, b in balances:
    if b > peak:
        # Nouveau peak
        if current_dd_start is not None:
            # On ferme un episode de DD
            pass  # On le gardera dans la liste meme s'il n'est pas fini
        peak = b
        peak_dt = dt
        current_dd_start = None
    else:
        dd_pct = (peak - b) / peak * 100
        if dd_pct > 10 and current_dd_start is None:
            current_dd_start = (dt, b, peak_dt, peak)
        if current_dd_start is not None:
            # On traque le bottom
            start_dt, start_b, cpeak_dt, cpeak = current_dd_start
            cur_dd = (cpeak - b) / cpeak * 100
            if b < start_b:
                current_dd_start = (dt, b, cpeak_dt, cpeak)

# Simpler: track max DD and list episodes
peak = 10000
max_dd_episodes = []  # (peak_dt, peak_val, bottom_dt, bottom_val, dd_pct)
cur_peak_dt = balances[0][0]
cur_peak_val = 10000

for dt, b in balances:
    if b >= peak:
        if peak - min([x[1] for x in balances[balances.index((dt, b))-50:balances.index((dt, b))+1] if True] + [peak]) > 0:
            pass
        peak = b
        cur_peak_dt = dt
        cur_peak_val = b

# Simpler DD walker
peak = 10000
peak_dt = balances[0][0]
in_dd = False
dd_bottom = peak
dd_bottom_dt = peak_dt
episodes = []

for dt, b in balances:
    if b > peak:
        if in_dd and (peak - dd_bottom)/peak > 0.10:
            episodes.append({
                'peak_dt': peak_dt,
                'peak_val': peak,
                'bottom_dt': dd_bottom_dt,
                'bottom_val': dd_bottom,
                'dd_abs': peak - dd_bottom,
                'dd_pct': (peak - dd_bottom)/peak * 100
            })
        peak = b
        peak_dt = dt
        dd_bottom = b
        dd_bottom_dt = dt
        in_dd = False
    else:
        if b < dd_bottom:
            dd_bottom = b
            dd_bottom_dt = dt
        in_dd = True

# Dernier episode si encore en DD
if in_dd and (peak - dd_bottom)/peak > 0.10:
    episodes.append({
        'peak_dt': peak_dt,
        'peak_val': peak,
        'bottom_dt': dd_bottom_dt,
        'bottom_val': dd_bottom,
        'dd_abs': peak - dd_bottom,
        'dd_pct': (peak - dd_bottom)/peak * 100
    })

episodes.sort(key=lambda x: -x['dd_pct'])
print(f"{'Peak date':<20} {'Peak $':>10} {'Bottom date':<20} {'Bottom $':>10} {'DD %':>7} {'DD $':>10}")
for e in episodes[:10]:
    print(f"{str(e['peak_dt']):<20} {e['peak_val']:>10.0f} {str(e['bottom_dt']):<20} {e['bottom_val']:>10.0f} {e['dd_pct']:>6.1f}% {e['dd_abs']:>10.0f}")

# Par niveau pyramide
print("\n" + "=" * 75)
print("PAR NIVEAU PYRAMIDE (6 ans)")
print("=" * 75)
streak = 0
for t in trades:
    t['level'] = streak
    if t['profit'] > 0: streak = min(streak+1, 2)
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

print(f"{'Lvl':>4} {'N':>5} {'WR%':>6} {'Net':>12} {'PF':>6}")
for lv in sorted(by_lvl.keys()):
    d = by_lvl[lv]
    wr = d['wins']/d['n']*100
    net = d['gw']-d['gl']
    pf = d['gw']/d['gl'] if d['gl'] else 0
    print(f"{lv:>4} {d['n']:>5} {wr:>6.1f} {net:>+12.2f} {pf:>6.2f}")

# Courbe trimestrielle
print("\n" + "=" * 75)
print("COURBE TRIMESTRIELLE")
print("=" * 75)
by_q = defaultdict(lambda: 0)
for t in trades:
    y = t['open_dt'].year
    q = (t['open_dt'].month - 1)//3 + 1
    by_q[f"{y}Q{q}"] += t['profit']

cumul = 10000
q_balances = {}
for key in sorted(by_q.keys()):
    cumul += by_q[key]
    q_balances[key] = cumul
    pnl = by_q[key]
    mark = '+' if pnl >= 0 else '-'
    bar = '#' * min(40, int(abs(pnl)/500))
    print(f"  {key}: {pnl:>+11.2f}  cumul={cumul:>10.2f}  {mark} {bar}")

# Worst trades
print("\n--- TOP 10 WORST TRADES (losses) ---")
for t in sorted(trades, key=lambda x: x['profit'])[:10]:
    print(f"  {t['open_dt']} lv={t['level']} lot={t['lots']:.2f} pnl=${t['profit']:.2f} balance_after=${t['balance_after']:.2f}")
