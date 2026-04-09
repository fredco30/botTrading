"""
Simulation de l'anti-martingale sur les INIT trades du backtest V4 (classic).
Applique la pyramide lot x 1.5^streak sur la sequence d'INIT reels.
"""
from datetime import datetime
from collections import defaultdict

PATH = r"C:\Users\projets\botTrading\resultats_martingale4.txt"

# Parse les trades
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
                'open_price': op['price'],
                'profit': t['profit'], 'result': t['action']
            })
            del opens[t['ticket']]

# Identifier les INIT (niveau 0 = pas un Mg du classic)
# Un INIT = pas precede immediatement d'un s/l + meme direction + lot 2x
for i, tr in enumerate(trades):
    tr['is_init'] = True
    if i > 0:
        prev = trades[i-1]
        if (prev['result'] == 's/l' and
            prev['type'] == tr['type'] and
            tr['lots'] > prev['lots'] * 1.5 and
            tr['lots'] < prev['lots'] * 2.5):
            tr['is_init'] = False

init_trades = [t for t in trades if t['is_init']]
print(f"INIT trades (sequence pour anti-martingale): {len(init_trades)}")

# Calcul PnL "normalise" par lot (PnL/lot = pips × tickval)
# On va simuler avec base_lot = 0.1 et appliquer multiplicateur
# Chaque INIT real trade avait un lot variable. On extrait juste le PnL/lot pour le normaliser.
for t in init_trades:
    t['pnl_per_lot'] = t['profit'] / t['lots'] if t['lots'] > 0 else 0
    # ex: INIT de 0.43 lot avec perte -98.90 -> pnl_per_lot = -230/lot

# ============================================================
# Simulation anti-martingale
# ============================================================

def simulate_anti_mart(trades_list, mg_mult=1.5, max_level=2, base_lot=0.1, pyramid_on=True, name=""):
    balance = 10000.0
    streak = 0
    max_streak = 0
    total_pnl = 0
    wins = 0
    losses = 0
    peak = balance
    max_dd_pct = 0
    max_dd_abs = 0
    streak_wins_history = []  # enregistrer combien atteignent chaque streak
    streak_counts = defaultdict(int)

    for t in trades_list:
        # Lot actuel selon le streak
        if pyramid_on:
            lot = base_lot * (mg_mult ** streak)
        else:
            lot = base_lot

        # PnL proportionnel au lot
        pnl = t['pnl_per_lot'] * lot
        total_pnl += pnl
        balance += pnl

        # Tracking peak/DD
        if balance > peak:
            peak = balance
        dd_abs = peak - balance
        dd_pct = dd_abs/peak*100 if peak > 0 else 0
        if dd_pct > max_dd_pct:
            max_dd_pct = dd_pct
            max_dd_abs = dd_abs

        # Update streak
        streak_counts[streak] += 1
        if pnl > 0:
            wins += 1
            if pyramid_on:
                streak += 1
                if streak > max_level:
                    streak = max_level
            if streak > max_streak:
                max_streak = streak
        else:
            losses += 1
            streak = 0

    pf_gross_win = sum(max(0, t['pnl_per_lot'] * base_lot * (mg_mult ** min(max_level, max_streak))) for t in trades_list if t['pnl_per_lot'] > 0)
    # Simple PF
    wins_pnl = sum(base_lot * (mg_mult ** 0) * t['pnl_per_lot'] for t in trades_list if t['pnl_per_lot'] > 0)
    losses_pnl = sum(base_lot * (mg_mult ** 0) * abs(t['pnl_per_lot']) for t in trades_list if t['pnl_per_lot'] <= 0)

    print(f"\n--- {name} ---")
    print(f"Base lot: {base_lot} | MgMult: {mg_mult} | MaxLevel: {max_level} | Pyramid: {pyramid_on}")
    print(f"Balance: 10000 -> {balance:.2f}")
    print(f"Net: {total_pnl:+.2f} USD ({total_pnl/100:.1f}%)")
    print(f"Trades: {len(trades_list)} | Wins: {wins} | Losses: {losses} | WR: {wins/len(trades_list)*100:.1f}%")
    print(f"Max DD: {max_dd_abs:.2f} ({max_dd_pct:.1f}%)")
    print(f"Max streak atteint: {max_streak}")
    print(f"Distribution du streak d'entree: {dict(sorted(streak_counts.items()))}")
    return total_pnl, max_dd_pct, max_streak

# ============================================================
# Variantes a tester
# ============================================================

print("\n" + "=" * 70)
print("BASELINE: pas de pyramide (= INIT filtre seul, equivalent Option Z)")
print("=" * 70)
simulate_anti_mart(init_trades, mg_mult=1.0, max_level=0, pyramid_on=False, name="Baseline (no pyramid)")

print("\n" + "=" * 70)
print("ANTI-MARTINGALE variantes")
print("=" * 70)
simulate_anti_mart(init_trades, mg_mult=1.5, max_level=1, pyramid_on=True, name="MgMult 1.5, cap 1 level (1x, 1.5x)")
simulate_anti_mart(init_trades, mg_mult=1.5, max_level=2, pyramid_on=True, name="MgMult 1.5, cap 2 levels (1x, 1.5x, 2.25x)")
simulate_anti_mart(init_trades, mg_mult=1.5, max_level=3, pyramid_on=True, name="MgMult 1.5, cap 3 levels (1x, 1.5x, 2.25x, 3.375x)")
simulate_anti_mart(init_trades, mg_mult=2.0, max_level=2, pyramid_on=True, name="MgMult 2.0, cap 2 levels (1x, 2x, 4x)")
simulate_anti_mart(init_trades, mg_mult=2.0, max_level=1, pyramid_on=True, name="MgMult 2.0, cap 1 level (1x, 2x)")

# ============================================================
# Analyse des streaks reelles
# ============================================================
print("\n" + "=" * 70)
print("ANALYSE DES STREAKS DE WINS (sequence reelle des INIT)")
print("=" * 70)

streaks = []
cur = 0
for t in init_trades:
    if t['pnl_per_lot'] > 0:
        cur += 1
    else:
        if cur > 0:
            streaks.append(cur)
        cur = 0
if cur > 0:
    streaks.append(cur)

print(f"Nombre de streaks de wins: {len(streaks)}")
dist = defaultdict(int)
for s in streaks:
    dist[s] += 1
print("Distribution:")
for length in sorted(dist.keys()):
    print(f"  {length} win(s) d'affilee : {dist[length]} fois")

max_s = max(streaks) if streaks else 0
print(f"Plus longue streak: {max_s}")
