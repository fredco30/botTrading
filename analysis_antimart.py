"""
Analyse complete du backtest anti-martingale (resultats_anti-martingale.txt).
"""
from datetime import datetime
from collections import defaultdict

PATH = r"C:\Users\projets\botTrading\resultats_anti-martingale.txt"

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
print(f"Resultat: +{trades[-1]['balance_after']-10000:.2f} USD (+{(trades[-1]['balance_after']-10000)/100:.1f}%)")

# ============================================================
# Stats globales
# ============================================================
wins = [t for t in trades if t['profit'] > 0]
losses = [t for t in trades if t['profit'] <= 0]
gross_win = sum(t['profit'] for t in wins)
gross_loss = abs(sum(t['profit'] for t in losses))
pf = gross_win/gross_loss if gross_loss else 0
wr = len(wins)/len(trades)*100

print(f"\n--- STATS GLOBALES ---")
print(f"Wins: {len(wins)} | Losses: {len(losses)} | WR: {wr:.1f}%")
print(f"PF: {pf:.2f}")
print(f"Gross Win: {gross_win:.2f} | Gross Loss: -{gross_loss:.2f}")
print(f"Avg Win: {gross_win/len(wins):.2f} | Avg Loss: {-gross_loss/len(losses):.2f}")
print(f"Expectancy: {(gross_win-gross_loss)/len(trades):.2f} per trade")

# ============================================================
# Detection du niveau pyramide (lot ratio vs base)
# Le niveau se calcule: streak de wins consecutifs avant ce trade
# ============================================================
streak = 0
for i, tr in enumerate(trades):
    tr['level'] = streak
    if tr['profit'] > 0:
        streak += 1
        if streak > 10:  # safety cap
            streak = 10
    else:
        streak = 0

# Stats par niveau pyramide
by_level = defaultdict(lambda: {'n': 0, 'wins': 0, 'net': 0, 'gross_w': 0, 'gross_l': 0})
for t in trades:
    lv = t['level']
    by_level[lv]['n'] += 1
    by_level[lv]['net'] += t['profit']
    if t['profit'] > 0:
        by_level[lv]['wins'] += 1
        by_level[lv]['gross_w'] += t['profit']
    else:
        by_level[lv]['gross_l'] += abs(t['profit'])

print(f"\n--- PAR NIVEAU PYRAMIDE (niveau = streak avant ce trade) ---")
print(f"{'Lvl':>3} {'N':>5} {'Wins':>5} {'WR%':>6} {'Net':>11} {'AvgW':>8} {'AvgL':>8} {'PF':>5}")
for lv in sorted(by_level.keys()):
    d = by_level[lv]
    wr_lv = d['wins']/d['n']*100 if d['n'] else 0
    avg_w = d['gross_w']/d['wins'] if d['wins'] else 0
    avg_l = d['gross_l']/(d['n']-d['wins']) if (d['n']-d['wins']) else 0
    pf_lv = d['gross_w']/d['gross_l'] if d['gross_l'] else 0
    print(f"{lv:>3} {d['n']:>5} {d['wins']:>5} {wr_lv:>6.1f} {d['net']:>+11.2f} {avg_w:>+8.2f} {avg_l:>-8.2f} {pf_lv:>5.2f}")

# ============================================================
# Drawdown
# ============================================================
balances = [10000] + [t['balance_after'] for t in trades]
peak = balances[0]
max_dd_pct = 0
max_dd_abs = 0
peak_bal = 0
for b in balances:
    if b > peak:
        peak = b
    dd = peak - b
    dd_pct = dd/peak*100
    if dd_pct > max_dd_pct:
        max_dd_pct = dd_pct
        max_dd_abs = dd
        peak_bal = peak

print(f"\n--- DRAWDOWN ---")
print(f"Max DD: {max_dd_abs:.2f} USD ({max_dd_pct:.1f}%)")
print(f"Peak balance: {max(balances):.2f}")

# ============================================================
# Par annee
# ============================================================
print(f"\n--- PAR ANNEE ---")
by_year = defaultdict(lambda: {'n': 0, 'pnl': 0, 'wins': 0, 'start': 0, 'end': 0})
for t in trades:
    y = t['close_dt'].year
    by_year[y]['n'] += 1
    by_year[y]['pnl'] += t['profit']
    if t['profit'] > 0: by_year[y]['wins'] += 1

# End balance per year
cur_year = None
for t in trades:
    y = t['close_dt'].year
    if y != cur_year:
        if cur_year is not None:
            by_year[cur_year]['end'] = last_bal
        by_year[y]['start'] = t['balance_after'] - t['profit']
        cur_year = y
    last_bal = t['balance_after']
by_year[cur_year]['end'] = last_bal

print(f"{'Year':>5} {'N':>5} {'WR%':>6} {'PnL':>11} {'Start':>10} {'End':>10} {'Gain%':>7}")
for y in sorted(by_year.keys()):
    d = by_year[y]
    wr_y = d['wins']/d['n']*100
    gain_pct = (d['end']-d['start'])/d['start']*100 if d['start'] else 0
    print(f"{y:>5} {d['n']:>5} {wr_y:>6.1f} {d['pnl']:>+11.2f} {d['start']:>10.2f} {d['end']:>10.2f} {gain_pct:>+6.1f}%")

# ============================================================
# Streaks
# ============================================================
max_win_streak = 0
max_lose_streak = 0
cur_w = 0
cur_l = 0
for t in trades:
    if t['profit'] > 0:
        cur_w += 1
        cur_l = 0
        if cur_w > max_win_streak: max_win_streak = cur_w
    else:
        cur_l += 1
        cur_w = 0
        if cur_l > max_lose_streak: max_lose_streak = cur_l

print(f"\n--- STREAKS ---")
print(f"Max win streak: {max_win_streak}")
print(f"Max lose streak: {max_lose_streak}")

# Top wins / losses
print(f"\n--- TOP 10 WINS ---")
for t in sorted(trades, key=lambda x: -x['profit'])[:10]:
    print(f"{t['open_dt']} lv={t['level']} lot={t['lots']:.2f} +{t['profit']:.2f}")

print(f"\n--- TOP 10 LOSSES ---")
for t in sorted(trades, key=lambda x: x['profit'])[:10]:
    print(f"{t['open_dt']} lv={t['level']} lot={t['lots']:.2f} {t['profit']:.2f}")

# ============================================================
# Comparaison vs les autres EAs
# ============================================================
print(f"\n--- COMPARAISON ---")
print(f"{'EA':<25} {'Net':>12} {'DD%':>8} {'PF':>6} {'Trades':>7}")
print(f"{'V1 Reverse buggy':<25} {'-4236.80':>12} {'66.9%':>8} {'0.96':>6} {'2285':>7}")
print(f"{'V2 Reverse fix delai':<25} {'~-2800':>12} {'~50%':>8} {'~1.00':>6} {'~1500':>7}")
print(f"{'V4 Classic Mg':<25} {'-2622.04':>12} {'59.1%':>8} {'0.98':>6} {'1477':>7}")
print(f"{'Anti-Mart Filtered':<25} {trades[-1]['balance_after']-10000:>+12.2f} {f'{max_dd_pct:.1f}%':>8} {pf:>6.2f} {len(trades):>7}")

# ============================================================
# Lot distribution
# ============================================================
print(f"\n--- DISTRIBUTION DES LOTS ---")
lot_buckets = defaultdict(int)
for t in trades:
    lot_buckets[round(t['lots'], 1)] += 1
print(f"{'Lot':>6} {'Count':>6}")
for lot in sorted(lot_buckets.keys()):
    print(f"{lot:>6.1f} {lot_buckets[lot]:>6}")
