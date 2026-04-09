"""
Simulation: tester differents cooldowns post-loss sur la sequence anti-martingale.
Objectif: trouver la duree optimale qui maximise le PF et minimise le DD.
"""
from datetime import datetime, timedelta
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
                'type': op['action'], 'lots': op['lots'],
                'open_dt': op['dt'], 'close_dt': t['dt'],
                'profit': t['profit'], 'result': t['action']
            })
            del opens[t['ticket']]

print(f"Total trades: {len(trades)}")

# Normaliser: PnL par unite de lot (pnl/lot) pour pouvoir resimuler avec d'autres lots
for t in trades:
    t['pnl_per_lot'] = t['profit'] / t['lots'] if t['lots'] > 0 else 0

# ============================================================
# Fonction de simulation avec cooldown post-loss
# ============================================================
def simulate(trades_in, cooldown_hours, mg_mult=1.5, max_level=2, base_lot=0.1):
    """
    Simule la strategie avec:
    - Cooldown: apres une perte, skip tous les trades pendant X heures
    - Pyramid: lot = base_lot * mg_mult^streak (cap a max_level)
    """
    balance = 10000.0
    peak = balance
    max_dd_abs = 0
    max_dd_pct = 0
    streak = 0
    skip_until = None  # datetime jusqu'auquel on skippe
    wins = 0
    losses = 0
    skipped = 0
    total_pnl = 0
    gross_w = 0
    gross_l = 0

    for t in trades_in:
        # Check cooldown
        if skip_until is not None and t['open_dt'] < skip_until:
            skipped += 1
            continue

        # Lot selon streak (avec cap)
        capped = min(streak, max_level)
        lot = base_lot * (mg_mult ** capped)
        # PnL proportionnel
        pnl = t['pnl_per_lot'] * lot
        total_pnl += pnl
        balance += pnl

        # Stats
        if balance > peak:
            peak = balance
        dd_abs = peak - balance
        dd_pct = dd_abs/peak*100
        if dd_pct > max_dd_pct:
            max_dd_pct = dd_pct
            max_dd_abs = dd_abs

        if pnl > 0:
            wins += 1
            gross_w += pnl
            streak += 1
            skip_until = None  # reset cooldown sur win
        else:
            losses += 1
            gross_l += abs(pnl)
            streak = 0
            # Activer cooldown
            if cooldown_hours > 0:
                skip_until = t['close_dt'] + timedelta(hours=cooldown_hours)

    taken = wins + losses
    wr = wins/taken*100 if taken else 0
    pf = gross_w/gross_l if gross_l else 0
    return {
        'taken': taken, 'skipped': skipped,
        'wins': wins, 'losses': losses, 'wr': wr,
        'pf': pf, 'net': total_pnl, 'dd_pct': max_dd_pct, 'dd_abs': max_dd_abs,
        'final': balance
    }

# ============================================================
# Test: plusieurs durees de cooldown
# ============================================================
print("\n" + "=" * 80)
print("SIMULATION COOLDOWN POST-LOSS (base_lot=0.1, mult 1.5, cap 2)")
print("=" * 80)
print(f"{'CD hrs':>7} {'Taken':>6} {'Skip':>5} {'WR%':>6} {'PF':>6} {'Net':>10} {'Final':>9} {'DD%':>6}")

cooldowns = [0, 1, 2, 3, 4, 6, 8, 12, 18, 24, 36, 48]
results = []
for cd in cooldowns:
    r = simulate(trades, cooldown_hours=cd)
    results.append((cd, r))
    print(f"{cd:>7} {r['taken']:>6} {r['skipped']:>5} {r['wr']:>6.1f} {r['pf']:>6.3f} {r['net']:>+10.2f} {r['final']:>9.0f} {r['dd_pct']:>5.1f}%")

# ============================================================
# Meme chose mais avec mult 2.0 cap 1 (l'optimum theorique precedent)
# ============================================================
print("\n" + "=" * 80)
print("SIMULATION COOLDOWN: pyramid mult=2.0 cap=1 (1x, 2x)")
print("=" * 80)
print(f"{'CD hrs':>7} {'Taken':>6} {'Skip':>5} {'WR%':>6} {'PF':>6} {'Net':>10} {'Final':>9} {'DD%':>6}")
for cd in cooldowns:
    r = simulate(trades, cooldown_hours=cd, mg_mult=2.0, max_level=1)
    print(f"{cd:>7} {r['taken']:>6} {r['skipped']:>5} {r['wr']:>6.1f} {r['pf']:>6.3f} {r['net']:>+10.2f} {r['final']:>9.0f} {r['dd_pct']:>5.1f}%")

# ============================================================
# Meme chose mais sans pyramide (baseline)
# ============================================================
print("\n" + "=" * 80)
print("SIMULATION COOLDOWN: NO PYRAMID (baseline = INIT seul)")
print("=" * 80)
print(f"{'CD hrs':>7} {'Taken':>6} {'Skip':>5} {'WR%':>6} {'PF':>6} {'Net':>10} {'Final':>9} {'DD%':>6}")
for cd in cooldowns:
    r = simulate(trades, cooldown_hours=cd, mg_mult=1.0, max_level=0)
    print(f"{cd:>7} {r['taken']:>6} {r['skipped']:>5} {r['wr']:>6.1f} {r['pf']:>6.3f} {r['net']:>+10.2f} {r['final']:>9.0f} {r['dd_pct']:>5.1f}%")

# ============================================================
# Par annee pour le cooldown optimal (detecte au dessus)
# ============================================================
print("\n" + "=" * 80)
print("DETAIL PAR ANNEE pour le meilleur cooldown")
print("=" * 80)

# On trouve le meilleur cooldown par PF
best = max(results, key=lambda x: x[1]['pf'])
best_cd = best[0]
print(f"\nMeilleur cooldown (par PF): {best_cd}h")

# Simuler par annee
balance = 10000.0
streak = 0
skip_until = None
by_year = defaultdict(lambda: {'n': 0, 'wins': 0, 'pnl': 0, 'start': 0, 'end': 0})
cur_year = None

for t in trades:
    if skip_until is not None and t['open_dt'] < skip_until:
        continue

    y = t['close_dt'].year
    if y != cur_year:
        if cur_year is not None:
            by_year[cur_year]['end'] = balance
        by_year[y]['start'] = balance
        cur_year = y

    capped = min(streak, 2)
    lot = 0.1 * (1.5 ** capped)
    pnl = t['pnl_per_lot'] * lot
    balance += pnl

    by_year[y]['n'] += 1
    by_year[y]['pnl'] += pnl
    if pnl > 0:
        by_year[y]['wins'] += 1
        streak += 1
    else:
        streak = 0
        if best_cd > 0:
            skip_until = t['close_dt'] + timedelta(hours=best_cd)

by_year[cur_year]['end'] = balance

print(f"{'Year':>5} {'N':>5} {'WR%':>6} {'PnL':>10} {'Start':>9} {'End':>9}")
for y in sorted(by_year.keys()):
    d = by_year[y]
    wr_y = d['wins']/d['n']*100 if d['n'] else 0
    print(f"{y:>5} {d['n']:>5} {wr_y:>6.1f} {d['pnl']:>+10.2f} {d['start']:>9.2f} {d['end']:>9.2f}")
