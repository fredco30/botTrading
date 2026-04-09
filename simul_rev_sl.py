"""
Simulation: pour chaque INIT qui a perdu, on teste un REVERSE unique avec
differents niveaux de SL, sur l'historique EURUSD H1 reel.

Question: un seul reverse avec un SL plus large est-il profitable ?

Setup REV:
  - Entree = prix du SL de l'INIT (niveau exact)
  - Direction = opposee a l'INIT
  - Lot = 2x le lot de l'INIT
  - Target profit = 75% de la perte initiale (CORRECT, pas le bug x10)
  - SL teste en plusieurs valeurs
  - TP = distance calculee correctement

Simulation: on avance bar par bar sur EURUSD H1 apres le SL,
on regarde si TP ou SL est touche en premier (logique conservatrice:
si les 2 dans la meme bougie, on assume SL touche en premier).
"""
from datetime import datetime
from collections import defaultdict

TRADES_PATH = r"C:\Users\projets\botTrading\resultats_martingale3.txt"
BARS_PATH   = r"C:\Users\projets\botTrading\EURUSD60_cut.csv"

# ============================================================
# 1. Charger les bougies EURUSD H1
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
                'dt': dt,
                'o': float(p[2]), 'h': float(p[3]),
                'l': float(p[4]), 'c': float(p[5])
            })
        except:
            continue

# Index par timestamp pour recherche rapide
bar_idx = {b['dt']: i for i, b in enumerate(bars)}
print(f"Bars chargees: {len(bars)} | {bars[0]['dt']} -> {bars[-1]['dt']}")

# ============================================================
# 2. Charger les trades et extraire les INIT perdants
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
                'profit': t['profit'], 'result': t['action']
            })
            del opens[t['ticket']]

# Classifier INIT
for i, tr in enumerate(trades):
    tr['kind'] = 'INIT'
    if i > 0 and trades[i-1]['result'] == 's/l':
        ratio = tr['lots'] / trades[i-1]['lots'] if trades[i-1]['lots'] > 0 else 0
        gap = (tr['open_dt'] - trades[i-1]['close_dt']).total_seconds() / 60.0
        if 1.5 < ratio < 2.5 and gap < 2880:
            tr['kind'] = 'REV'

# INITs qui ont perdu (= cas ou on aurait declenche un reverse)
init_losers = [t for t in trades if t['kind'] == 'INIT' and t['result'] == 's/l']
print(f"INIT perdants: {len(init_losers)}")

# ============================================================
# 3. Fonction de simulation REV
# ============================================================
PIP = 0.0001  # EURUSD pip
TICKVAL_PER_LOT_PIP = 10.0  # USD per pip per 1.0 lot (standard EURUSD)

def simulate_rev(init_loser, sl_pips, recovery_pct=75.0, max_hold_hours=24):
    """
    Simule un REV unique avec SL fixe en pips.
    Retourne (pnl, outcome) ou outcome = 'tp', 'sl', 'timeout'.
    """
    # Direction opposee a l'INIT
    init_type = init_loser['type']  # 'buy' ou 'sell'
    rev_type = 'sell' if init_type == 'buy' else 'buy'

    # Entree au niveau du SL de l'INIT
    entry = init_loser['sl']
    rev_lots = init_loser['lots'] * 2.0

    # Perte de l'INIT (valeur absolue)
    init_loss = abs(init_loser['profit'])

    # TP = distance telle que profit = 75% * init_loss
    # profit = lots * distance_pips * TICKVAL_PER_LOT_PIP
    target_profit = init_loss * recovery_pct / 100.0
    tp_pips = target_profit / (rev_lots * TICKVAL_PER_LOT_PIP)

    # Prix TP et SL
    if rev_type == 'buy':
        tp_price = entry + tp_pips * PIP
        sl_price = entry - sl_pips * PIP
    else:
        tp_price = entry - tp_pips * PIP
        sl_price = entry + sl_pips * PIP

    # Trouver la bougie de depart: celle qui contient close_dt de l'INIT
    # ou la premiere qui commence apres
    start_dt = init_loser['close_dt']
    # Aligner sur l'heure H1 suivante
    start_hour = start_dt.replace(minute=0, second=0, microsecond=0)
    if start_dt > start_hour:
        # Utiliser la bougie en cours (on suppose que le reverse entre pendant cette bougie)
        # Pour simplification conservatrice: on attend la prochaine bougie
        from datetime import timedelta
        start_hour = start_hour + timedelta(hours=1)

    if start_hour not in bar_idx:
        return None  # hors range donnees

    start_i = bar_idx[start_hour]
    max_bars = max_hold_hours

    # Scan forward
    for j in range(max_bars):
        i = start_i + j
        if i >= len(bars):
            break
        b = bars[i]

        if rev_type == 'buy':
            # SL en dessous, TP au dessus
            sl_hit = b['l'] <= sl_price
            tp_hit = b['h'] >= tp_price
            if sl_hit and tp_hit:
                # Conservateur: SL en premier
                return (-rev_lots * sl_pips * TICKVAL_PER_LOT_PIP, 'sl')
            if sl_hit:
                return (-rev_lots * sl_pips * TICKVAL_PER_LOT_PIP, 'sl')
            if tp_hit:
                return (+target_profit, 'tp')
        else:
            # SL au dessus, TP en dessous
            sl_hit = b['h'] >= sl_price
            tp_hit = b['l'] <= tp_price
            if sl_hit and tp_hit:
                return (-rev_lots * sl_pips * TICKVAL_PER_LOT_PIP, 'sl')
            if sl_hit:
                return (-rev_lots * sl_pips * TICKVAL_PER_LOT_PIP, 'sl')
            if tp_hit:
                return (+target_profit, 'tp')

    # Timeout: on sort au close de la derniere bougie
    last = bars[min(start_i + max_bars - 1, len(bars)-1)]
    if rev_type == 'buy':
        exit_price = last['c']
        exit_pips = (exit_price - entry) / PIP
    else:
        exit_price = last['c']
        exit_pips = (entry - exit_price) / PIP
    pnl = rev_lots * exit_pips * TICKVAL_PER_LOT_PIP
    return (pnl, 'timeout')

# ============================================================
# 4. Tester plusieurs SL
# ============================================================
sl_variants = [10, 15, 20, 25, 30, 40, 50, 75, 100]
recovery_variants = [50, 75, 100]

print("\n" + "=" * 80)
print("SIMULATION REV UNIQUE: recovery=75%, SL variable")
print("=" * 80)
print(f"{'SL pips':>8} {'N':>5} {'WR%':>6} {'Wins':>5} {'Losses':>6} {'Timeouts':>9} {'PF':>6} {'Net':>10} {'AvgW':>7} {'AvgL':>7}")

results_75 = {}
for sl_pips in sl_variants:
    wins = 0
    losses = 0
    timeouts = 0
    total_pnl = 0
    gross_win = 0
    gross_loss = 0
    for il in init_losers:
        r = simulate_rev(il, sl_pips, recovery_pct=75.0)
        if r is None:
            continue
        pnl, outcome = r
        total_pnl += pnl
        if outcome == 'tp':
            wins += 1
            gross_win += pnl
        elif outcome == 'sl':
            losses += 1
            gross_loss += abs(pnl)
        else:
            timeouts += 1
            if pnl > 0:
                gross_win += pnl
                wins += 1
            else:
                gross_loss += abs(pnl)
                losses += 1
    n = wins + losses
    wr = wins/n*100 if n else 0
    pf = gross_win/gross_loss if gross_loss > 0 else 0
    avg_w = gross_win/wins if wins else 0
    avg_l = gross_loss/losses if losses else 0
    results_75[sl_pips] = (n, wr, pf, total_pnl)
    print(f"{sl_pips:>8} {n:>5} {wr:>6.1f} {wins:>5} {losses:>6} {timeouts:>9} {pf:>6.2f} {total_pnl:>+10.2f} {avg_w:>7.2f} {avg_l:>7.2f}")

# ============================================================
# 5. Meme chose avec recovery 50% et 100%
# ============================================================
for rec in [50, 100]:
    print(f"\n--- Recovery {rec}% ---")
    print(f"{'SL pips':>8} {'N':>5} {'WR%':>6} {'PF':>6} {'Net':>10}")
    for sl_pips in sl_variants:
        wins = 0; losses = 0; gross_win = 0; gross_loss = 0; total_pnl = 0
        for il in init_losers:
            r = simulate_rev(il, sl_pips, recovery_pct=rec)
            if r is None: continue
            pnl, outcome = r
            total_pnl += pnl
            if pnl > 0:
                wins += 1; gross_win += pnl
            else:
                losses += 1; gross_loss += abs(pnl)
        n = wins + losses
        wr = wins/n*100 if n else 0
        pf = gross_win/gross_loss if gross_loss > 0 else 0
        print(f"{sl_pips:>8} {n:>5} {wr:>6.1f} {pf:>6.2f} {total_pnl:>+10.2f}")

# ============================================================
# 6. Calcul net combine: INIT loss + REV result
# ============================================================
print("\n" + "=" * 80)
print("IMPACT GLOBAL: perte INIT + resultat REV cumules")
print("=" * 80)
print(f"Perte totale cumulee sur les INIT: {sum(t['profit'] for t in init_losers):+.2f}")
print()
print("(SL REV, recovery) -> Net total systeme (INIT perdus + REV appliques)")
for rec in [50, 75, 100]:
    print(f"\n--- Recovery {rec}% ---")
    print(f"{'SL':>6} {'Net INIT':>10} {'Net REV':>10} {'Net Total':>11}")
    init_net = sum(t['profit'] for t in init_losers)
    for sl_pips in sl_variants:
        total_rev = 0
        for il in init_losers:
            r = simulate_rev(il, sl_pips, recovery_pct=rec)
            if r is None: continue
            total_rev += r[0]
        total = init_net + total_rev
        print(f"{sl_pips:>6} {init_net:>+10.2f} {total_rev:>+10.2f} {total:>+11.2f}")
