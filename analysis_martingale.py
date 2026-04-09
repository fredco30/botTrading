"""
Analyse complete du bot martingale_invert_EA (Pure Reverse 75%).
Detecte INIT vs REV, calcule metriques, identifie points faibles.
"""
import re
from collections import defaultdict
from datetime import datetime

PATH = r"C:\Users\projets\botTrading\resultats_martingale3.txt"

# Parser: chaque ligne = date | type | ticket | lots | price | sl | tp | profit | balance
trades_raw = []
with open(PATH, 'r', encoding='utf-8', errors='ignore') as f:
    for line in f:
        parts = line.strip().split('\t')
        if len(parts) < 10:
            continue
        try:
            # col 0 = row number, skip
            dt = datetime.strptime(parts[1], '%Y.%m.%d %H:%M')
            action = parts[2]
            ticket = int(parts[3])
            lots = float(parts[4])
            price = float(parts[5])
            sl = float(parts[6])
            tp = float(parts[7])
            profit = float(parts[8])
            balance = float(parts[9])
            trades_raw.append({
                'dt': dt, 'action': action, 'ticket': ticket,
                'lots': lots, 'price': price, 'sl': sl, 'tp': tp,
                'profit': profit, 'balance': balance
            })
        except:
            continue

# Pair open/close par ticket
opens = {}
trades = []  # Liste de trades complets
for t in trades_raw:
    if t['action'] in ('buy', 'sell'):
        opens[t['ticket']] = t
    elif t['action'] in ('s/l', 't/p', 'close'):
        if t['ticket'] in opens:
            op = opens[t['ticket']]
            trades.append({
                'ticket': t['ticket'],
                'type': op['action'],  # buy/sell
                'lots': op['lots'],
                'open_dt': op['dt'],
                'close_dt': t['dt'],
                'open_price': op['price'],
                'close_price': t['price'],
                'sl': op['sl'],
                'tp': op['tp'],
                'profit': t['profit'],
                'balance_after': t['balance'],
                'result': t['action'],  # s/l or t/p
                'duration_min': (t['dt'] - op['dt']).total_seconds() / 60.0
            })
            del opens[t['ticket']]

print(f"Total trades: {len(trades)}")
print(f"Periode: {trades[0]['open_dt']} -> {trades[-1]['close_dt']}")
print(f"Balance: {10000:.2f} -> {trades[-1]['balance_after']:.2f}")
print(f"Resultat net: {trades[-1]['balance_after']-10000:.2f} USD ({(trades[-1]['balance_after']-10000)/100:.1f}%)")

# --- Classification INIT vs REV ---
# Un REV arrive juste apres un s/l, et lots = 2x les lots du s/l precedent
# On accepte une marge car le lot size du REV est arrondi
for i, tr in enumerate(trades):
    tr['kind'] = 'INIT'
    if i > 0:
        prev = trades[i-1]
        if prev['result'] == 's/l':
            ratio = tr['lots'] / prev['lots'] if prev['lots'] > 0 else 0
            # gap temps <= 48h et lots approx 2x
            gap_min = (tr['open_dt'] - prev['close_dt']).total_seconds() / 60.0
            if 1.5 < ratio < 2.5 and gap_min < 2880:
                tr['kind'] = 'REV'

init_trades = [t for t in trades if t['kind'] == 'INIT']
rev_trades = [t for t in trades if t['kind'] == 'REV']

print(f"\n--- CLASSIFICATION ---")
print(f"INIT trades: {len(init_trades)}")
print(f"REV  trades: {len(rev_trades)}")

# --- Metriques globales ---
def stats(trs, label):
    if not trs:
        print(f"{label}: aucun trade")
        return
    wins = [t for t in trs if t['profit'] > 0]
    losses = [t for t in trs if t['profit'] <= 0]
    gross_win = sum(t['profit'] for t in wins)
    gross_loss = abs(sum(t['profit'] for t in losses))
    pf = gross_win / gross_loss if gross_loss > 0 else 0
    wr = len(wins) / len(trs) * 100
    avg_win = gross_win / len(wins) if wins else 0
    avg_loss = gross_loss / len(losses) if losses else 0
    print(f"\n--- {label} ---")
    print(f"N={len(trs)} | WR={wr:.1f}% | PF={pf:.2f}")
    print(f"Gross Win: {gross_win:.2f} | Gross Loss: -{gross_loss:.2f}")
    print(f"Net: {gross_win-gross_loss:.2f}")
    print(f"Avg Win: {avg_win:.2f} | Avg Loss: -{avg_loss:.2f}")
    print(f"RR moyen: {avg_win/avg_loss:.2f}" if avg_loss > 0 else "")

stats(trades, "TOUS LES TRADES")
stats(init_trades, "INIT SEULS")
stats(rev_trades, "REV SEULS")

# --- Drawdown max ---
balances = [10000] + [t['balance_after'] for t in trades]
peak = balances[0]
max_dd_pct = 0
max_dd_abs = 0
peak_idx = 0
dd_idx = 0
for i, b in enumerate(balances):
    if b > peak:
        peak = b
        peak_idx = i
    dd = peak - b
    dd_pct = dd / peak * 100
    if dd_pct > max_dd_pct:
        max_dd_pct = dd_pct
        max_dd_abs = dd
        dd_idx = i

print(f"\n--- DRAWDOWN ---")
print(f"Max DD: {max_dd_abs:.2f} USD ({max_dd_pct:.1f}%)")
print(f"Peak balance: {peak:.2f}")
print(f"DD peak idx={peak_idx}, bottom idx={dd_idx}")

# --- Analyse des chaines de pertes consecutives ---
max_streak_loss = 0
cur_streak = 0
worst_streak_val = 0
cur_val = 0
for t in trades:
    if t['profit'] <= 0:
        cur_streak += 1
        cur_val += t['profit']
        if cur_streak > max_streak_loss:
            max_streak_loss = cur_streak
            worst_streak_val = cur_val
    else:
        cur_streak = 0
        cur_val = 0

print(f"\nMax pertes consecutives: {max_streak_loss} trades")
print(f"Pire chaine cumul: {worst_streak_val:.2f}")

# --- Efficacite du REV (recovery 75%) ---
# Un REV suit un INIT s/l. On calcule combien il recupere par rapport a la perte initiale.
recovery_ok = 0  # REV gagnant
recovery_ko = 0  # REV perdant
total_init_loss = 0
total_rev_result = 0
for i, tr in enumerate(trades):
    if tr['kind'] == 'REV' and i > 0:
        prev = trades[i-1]
        init_loss = abs(prev['profit'])
        rev_pnl = tr['profit']
        total_init_loss += init_loss
        total_rev_result += rev_pnl
        if rev_pnl > 0:
            recovery_ok += 1
        else:
            recovery_ko += 1

print(f"\n--- EFFICACITE DU REVERSE ---")
print(f"REV gagnants: {recovery_ok}")
print(f"REV perdants: {recovery_ko}")
if rev_trades:
    print(f"WR REV: {recovery_ok/len(rev_trades)*100:.1f}%")
print(f"Total pertes INIT suivies d'un REV: -{total_init_loss:.2f}")
print(f"Total PnL des REV: {total_rev_result:+.2f}")
print(f"Recovery net: {(total_init_loss+total_rev_result)/total_init_loss*100 if total_init_loss else 0:.1f}% recupere")

# --- Pattern: INIT perdu + REV perdu = catastrophe ---
double_loss = 0
double_loss_val = 0
for i, tr in enumerate(trades):
    if tr['kind'] == 'REV' and tr['profit'] <= 0 and i > 0:
        prev = trades[i-1]
        if prev['profit'] <= 0:
            double_loss += 1
            double_loss_val += prev['profit'] + tr['profit']

print(f"\n--- DOUBLE PERTES (INIT SL + REV SL) ---")
print(f"Occurrences: {double_loss}")
print(f"Cumul degats: {double_loss_val:.2f}")
print(f"Moyenne par double-perte: {double_loss_val/double_loss if double_loss else 0:.2f}")

# --- Analyse par annee ---
print(f"\n--- PAR ANNEE ---")
by_year = defaultdict(lambda: {'n': 0, 'pnl': 0, 'wins': 0, 'losses': 0})
for t in trades:
    y = t['close_dt'].year
    by_year[y]['n'] += 1
    by_year[y]['pnl'] += t['profit']
    if t['profit'] > 0:
        by_year[y]['wins'] += 1
    else:
        by_year[y]['losses'] += 1
for y in sorted(by_year.keys()):
    d = by_year[y]
    wr = d['wins']/d['n']*100
    print(f"{y}: N={d['n']:4d} | PnL={d['pnl']:+9.2f} | WR={wr:4.1f}%")

# --- Par heure d'entree INIT ---
print(f"\n--- PAR HEURE (INIT seulement) ---")
by_hour = defaultdict(lambda: {'n': 0, 'pnl': 0, 'wins': 0})
for t in init_trades:
    h = t['open_dt'].hour
    by_hour[h]['n'] += 1
    by_hour[h]['pnl'] += t['profit']
    if t['profit'] > 0:
        by_hour[h]['wins'] += 1
print(f"{'Hr':>3} {'N':>5} {'PnL':>10} {'WR%':>6} {'Avg':>8}")
for h in sorted(by_hour.keys()):
    d = by_hour[h]
    wr = d['wins']/d['n']*100 if d['n'] else 0
    avg = d['pnl']/d['n'] if d['n'] else 0
    print(f"{h:>3} {d['n']:>5} {d['pnl']:>+10.2f} {wr:>6.1f} {avg:>+8.2f}")

# --- Par jour de semaine ---
print(f"\n--- PAR JOUR (INIT seulement) ---")
jours = ['Lun', 'Mar', 'Mer', 'Jeu', 'Ven', 'Sam', 'Dim']
by_dow = defaultdict(lambda: {'n': 0, 'pnl': 0, 'wins': 0})
for t in init_trades:
    d = t['open_dt'].weekday()
    by_dow[d]['n'] += 1
    by_dow[d]['pnl'] += t['profit']
    if t['profit'] > 0:
        by_dow[d]['wins'] += 1
for d in sorted(by_dow.keys()):
    dd = by_dow[d]
    wr = dd['wins']/dd['n']*100 if dd['n'] else 0
    print(f"{jours[d]}: N={dd['n']:4d} | PnL={dd['pnl']:+9.2f} | WR={wr:4.1f}%")

# --- Trades losers les plus gros ---
print(f"\n--- 10 PIRES PERTES ---")
sorted_losers = sorted(trades, key=lambda x: x['profit'])[:10]
for t in sorted_losers:
    print(f"{t['open_dt']} {t['type']:4s} {t['kind']:4s} lot={t['lots']:.2f} pnl={t['profit']:+.2f}")

# --- Duree moyenne ---
avg_dur_init = sum(t['duration_min'] for t in init_trades) / len(init_trades) if init_trades else 0
avg_dur_rev = sum(t['duration_min'] for t in rev_trades) / len(rev_trades) if rev_trades else 0
print(f"\n--- DUREE ---")
print(f"INIT: {avg_dur_init:.0f} min ({avg_dur_init/60:.1f}h)")
print(f"REV : {avg_dur_rev:.0f} min ({avg_dur_rev/60:.1f}h)")
