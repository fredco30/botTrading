"""
Analyse complete de EMA_Pullback_pyramid sur 6 ans.
Config: L0=1.0, L1=4.0, L2=2.5
"""
from datetime import datetime
from collections import defaultdict

PATH = r"C:\Users\projets\botTrading\resultats_martingale_EMAPullback6ans.txt"

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

# Stats globales
wins = [t for t in trades if t['profit'] > 0]
losses = [t for t in trades if t['profit'] <= 0]
gw = sum(t['profit'] for t in wins)
gl = abs(sum(t['profit'] for t in losses))
pf = gw/gl if gl else 0
wr = len(wins)/len(trades)*100

print(f"\n--- GLOBAL ---")
print(f"WR: {wr:.1f}% ({len(wins)} wins / {len(losses)} losses)")
print(f"PF: {pf:.2f}")
print(f"Gross Win: {gw:.2f} | Gross Loss: {gl:.2f}")
print(f"Avg Win: {gw/len(wins):.2f} | Avg Loss: {gl/len(losses):.2f}")
print(f"Expectancy: {(gw-gl)/len(trades):.2f} per trade")

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
    wr_y = d['wins']/d['n']*100 if d['n'] else 0
    net = d['gw']-d['gl']
    pf_y = d['gw']/d['gl'] if d['gl'] else 0
    print(f"{y:>5} {d['n']:>5} {wr_y:>6.1f} {net:>+11.2f} {pf_y:>5.2f}")

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

print(f"{'Lvl':>4} {'N':>5} {'WR%':>6} {'Net':>11} {'PF':>6} {'AvgLot':>8} {'AvgWin':>9} {'AvgLoss':>9}")
for lv in sorted(by_lvl.keys()):
    d = by_lvl[lv]
    wr_lv = d['wins']/d['n']*100
    net = d['gw']-d['gl']
    pf_lv = d['gw']/d['gl'] if d['gl'] else 0
    avg_lot = sum(d['lots'])/len(d['lots']) if d['lots'] else 0
    avg_w = d['gw']/d['wins'] if d['wins'] else 0
    avg_l = d['gl']/(d['n']-d['wins']) if (d['n']-d['wins']) else 0
    print(f"{lv:>4} {d['n']:>5} {wr_lv:>6.1f} {net:>+11.2f} {pf_lv:>6.2f} {avg_lot:>8.2f} {avg_w:>+9.2f} {avg_l:>9.2f}")

# DD
balances = [10000] + [t['balance_after'] for t in trades]
peak = balances[0]
max_dd_pct = 0
max_dd_abs = 0
max_dd_peak = 0
for b in balances:
    if b > peak: peak = b
    dd = peak - b
    dd_pct = dd/peak*100 if peak > 0 else 0
    if dd_pct > max_dd_pct:
        max_dd_pct = dd_pct
        max_dd_abs = dd
        max_dd_peak = peak

print(f"\n--- DRAWDOWN ---")
print(f"Max DD: {max_dd_abs:.2f} USD ({max_dd_pct:.1f}%) from peak ${max_dd_peak:.0f}")

# Streaks
print("\n" + "=" * 75)
print("STREAKS")
print("=" * 75)
max_win_streak = 0
max_lose_streak = 0
cur_w = 0; cur_l = 0
for t in trades:
    if t['profit'] > 0:
        cur_w += 1; cur_l = 0
        if cur_w > max_win_streak: max_win_streak = cur_w
    else:
        cur_l += 1; cur_w = 0
        if cur_l > max_lose_streak: max_lose_streak = cur_l
print(f"Max win streak: {max_win_streak}")
print(f"Max lose streak: {max_lose_streak}")

# Top wins/losses
print("\n--- TOP 5 WINS ---")
for t in sorted(trades, key=lambda x: -x['profit'])[:5]:
    print(f"  {t['open_dt']} lv={t['level']} lot={t['lots']:.2f} +{t['profit']:.2f}")
print("\n--- TOP 5 LOSSES ---")
for t in sorted(trades, key=lambda x: x['profit'])[:5]:
    print(f"  {t['open_dt']} lv={t['level']} lot={t['lots']:.2f} {t['profit']:.2f}")

# Comparison with previous systems
print("\n" + "=" * 75)
print("COMPARAISON SYSTEMES 6 ANS")
print("=" * 75)
net = trades[-1]['balance_after'] - 10000
ratio = net / max_dd_pct if max_dd_pct > 0 else 0
print(f"{'Systeme':<45} {'Net':>10} {'DD%':>7} {'PF':>5} {'Trades':>7} {'R/DD':>6}")
print(f"{'regime_pyramid v2 (0.5/1.5/2.25)':<45} {'+12824':>10} {'20.6':>7} {'1.18':>5} {'716':>7} {'623':>6}")
print(f"{'regime_pyramid v3 (0.05/3.0/4.0)':<45} {'+43409':>10} {'39.2':>7} {'1.25':>5} {'716':>7} {'1106':>6}")
print(f"{'EMA Pullback pyramid (1.0/4.0/2.5)':<45} {f'+{net:.0f}':>10} {f'{max_dd_pct:.1f}':>7} {f'{pf:.2f}':>5} {len(trades):>7} {f'{ratio:.0f}':>6}")
