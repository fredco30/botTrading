#!/usr/bin/env python3
"""
Analyse complete de resultats_6ans_finalv4.txt
EMA_Pullback_pyramid — historique 6 ans
"""
import re
from collections import defaultdict
from datetime import datetime

FILE = "resultats_6ans_finalv4.txt"

# Parse trades
# Format: idx \t date \t action \t ticket \t lots \t price \t sl \t tp \t pnl \t balance
trades = []
with open(FILE, "r") as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) < 10:
            continue
        try:
            idx = int(parts[0])
            date_str = parts[1].strip()
            action = parts[2].strip()
            ticket = int(parts[3])
            lots = float(parts[4])
            price = float(parts[5])
            sl = float(parts[6])
            tp = float(parts[7])
            pnl = float(parts[8])
            balance = float(parts[9])
        except (ValueError, IndexError):
            continue

        trades.append({
            "idx": idx,
            "date": date_str,
            "action": action,
            "ticket": ticket,
            "lots": lots,
            "price": price,
            "sl": sl,
            "tp": tp,
            "pnl": pnl,
            "balance": balance
        })

# Separate opens and closes
opens = {}
closed_trades = []
for t in trades:
    if t["action"] in ("buy", "sell"):
        opens[t["ticket"]] = t
    elif t["action"] in ("s/l", "t/p", "close at stop"):
        if t["ticket"] in opens:
            op = opens[t["ticket"]]
            closed_trades.append({
                "ticket": t["ticket"],
                "open_date": op["date"],
                "close_date": t["date"],
                "type": op["action"],
                "lots": op["lots"],
                "open_price": op["price"],
                "close_price": t["price"],
                "sl": op["sl"],
                "tp": op["tp"],
                "pnl": t["pnl"],
                "balance": t["balance"],
                "exit": t["action"]
            })

print(f"=" * 70)
print(f"ANALYSE: resultats_6ans_finalv4.txt")
print(f"=" * 70)
print(f"Total lignes: {len(trades)}")
print(f"Trades ouverts+fermes: {len(closed_trades)}")
print(f"Balance initiale: ${trades[0]['balance']:.2f}" if trades else "N/A")
print(f"Balance finale: ${trades[-1]['balance']:.2f}" if trades else "N/A")

# --- Stats globales ---
wins = [t for t in closed_trades if t["pnl"] > 0]
losses = [t for t in closed_trades if t["pnl"] <= 0]
total_profit = sum(t["pnl"] for t in wins)
total_loss = sum(t["pnl"] for t in losses)
net = sum(t["pnl"] for t in closed_trades)

print(f"\n--- STATS GLOBALES ---")
print(f"Trades fermes: {len(closed_trades)}")
print(f"Wins: {len(wins)} ({100*len(wins)/len(closed_trades):.1f}%)")
print(f"Losses: {len(losses)} ({100*len(losses)/len(closed_trades):.1f}%)")
print(f"Net profit: ${net:,.2f}")
print(f"Total gains: ${total_profit:,.2f}")
print(f"Total pertes: ${total_loss:,.2f}")
print(f"Profit Factor: {total_profit / abs(total_loss):.2f}" if total_loss != 0 else "N/A")
print(f"Avg win: ${total_profit/len(wins):.2f}" if wins else "N/A")
print(f"Avg loss: ${total_loss/len(losses):.2f}" if losses else "N/A")

# --- Max Drawdown ---
balances = [trades[0]["balance"]]  # initial
for t in closed_trades:
    balances.append(t["balance"])

peak = balances[0]
max_dd = 0
max_dd_pct = 0
dd_start = ""
dd_end = ""
current_peak_idx = 0
for i, bal in enumerate(balances):
    if bal > peak:
        peak = bal
        current_peak_idx = i
    dd = peak - bal
    dd_pct = dd / peak * 100 if peak > 0 else 0
    if dd_pct > max_dd_pct:
        max_dd = dd
        max_dd_pct = dd_pct
        if i > 0 and i-1 < len(closed_trades):
            dd_end = closed_trades[i-1]["close_date"] if i-1 < len(closed_trades) else "?"

print(f"\n--- DRAWDOWN ---")
print(f"Max Drawdown: ${max_dd:,.2f} ({max_dd_pct:.1f}%)")

# --- Par annee ---
print(f"\n--- STATS PAR ANNEE ---")
yearly = defaultdict(lambda: {"wins": 0, "losses": 0, "profit": 0, "loss": 0, "trades": 0, "start_bal": None, "end_bal": None})
for t in closed_trades:
    year = t["close_date"][:4]
    yearly[year]["trades"] += 1
    if t["pnl"] > 0:
        yearly[year]["wins"] += 1
        yearly[year]["profit"] += t["pnl"]
    else:
        yearly[year]["losses"] += 1
        yearly[year]["loss"] += t["pnl"]
    yearly[year]["end_bal"] = t["balance"]
    if yearly[year]["start_bal"] is None:
        yearly[year]["start_bal"] = t["balance"] - t["pnl"]

print(f"{'Year':<6} {'Trades':>7} {'Wins':>5} {'WR%':>6} {'Net':>10} {'Gains':>10} {'Pertes':>10} {'PF':>6} {'Bal fin':>10}")
for year in sorted(yearly.keys()):
    y = yearly[year]
    wr = 100 * y["wins"] / y["trades"] if y["trades"] > 0 else 0
    net_y = y["profit"] + y["loss"]
    pf = y["profit"] / abs(y["loss"]) if y["loss"] != 0 else 999
    print(f"{year:<6} {y['trades']:>7} {y['wins']:>5} {wr:>5.1f}% ${net_y:>9,.2f} ${y['profit']:>9,.2f} ${y['loss']:>9,.2f} {pf:>5.2f} ${y['end_bal']:>9,.2f}")

# --- Analyse par niveau pyramid (lot size pattern) ---
# Detect pyramid level from lot size relative to previous trades
# The pattern: after a win, lot goes up (L1), after another win L2, after loss -> L0
print(f"\n--- ANALYSE PYRAMID (reconstruction par sequence W/L) ---")
streak = 0
levels = {0: [], 1: [], 2: []}
for i, t in enumerate(closed_trades):
    level = min(streak, 2)
    levels[level].append(t)
    if t["pnl"] > 0:
        streak = min(streak + 1, 2)
    else:
        streak = 0

for lvl in [0, 1, 2]:
    trades_l = levels[lvl]
    if not trades_l:
        continue
    w = sum(1 for t in trades_l if t["pnl"] > 0)
    l = sum(1 for t in trades_l if t["pnl"] <= 0)
    profit = sum(t["pnl"] for t in trades_l if t["pnl"] > 0)
    loss = sum(t["pnl"] for t in trades_l if t["pnl"] <= 0)
    net_l = profit + loss
    pf = profit / abs(loss) if loss != 0 else 999
    wr = 100 * w / len(trades_l) if trades_l else 0
    print(f"L{lvl}: {len(trades_l):>4} trades | WR {wr:>5.1f}% | Net ${net_l:>10,.2f} | Gains ${profit:>10,.2f} | Pertes ${loss:>10,.2f} | PF {pf:.2f}")

# --- Streaks analysis ---
print(f"\n--- STREAKS ---")
current_streak = 0
max_win_streak = 0
max_loss_streak = 0
current_type = None
for t in closed_trades:
    if t["pnl"] > 0:
        if current_type == "win":
            current_streak += 1
        else:
            current_streak = 1
            current_type = "win"
        max_win_streak = max(max_win_streak, current_streak)
    else:
        if current_type == "loss":
            current_streak += 1
        else:
            current_streak = 1
            current_type = "loss"
        max_loss_streak = max(max_loss_streak, current_streak)

print(f"Max win streak: {max_win_streak}")
print(f"Max loss streak: {max_loss_streak}")

# --- Exit type analysis ---
print(f"\n--- TYPE DE SORTIE ---")
exit_types = defaultdict(lambda: {"count": 0, "pnl": 0})
for t in closed_trades:
    exit_types[t["exit"]]["count"] += 1
    exit_types[t["exit"]]["pnl"] += t["pnl"]
for ex, data in sorted(exit_types.items()):
    print(f"{ex:>15}: {data['count']:>5} trades | Net ${data['pnl']:>10,.2f}")

# --- Analyse par direction (buy/sell) ---
print(f"\n--- PAR DIRECTION ---")
for direction in ["buy", "sell"]:
    dir_trades = [t for t in closed_trades if t["type"] == direction]
    if not dir_trades:
        continue
    w = sum(1 for t in dir_trades if t["pnl"] > 0)
    profit = sum(t["pnl"] for t in dir_trades if t["pnl"] > 0)
    loss = sum(t["pnl"] for t in dir_trades if t["pnl"] <= 0)
    net_d = profit + loss
    pf = profit / abs(loss) if loss != 0 else 999
    wr = 100 * w / len(dir_trades)
    print(f"{direction.upper():>5}: {len(dir_trades):>4} trades | WR {wr:>5.1f}% | Net ${net_d:>10,.2f} | PF {pf:.2f}")

# --- Analyse par mois ---
print(f"\n--- STATS PAR MOIS (mois calendaire) ---")
monthly = defaultdict(lambda: {"wins": 0, "losses": 0, "profit": 0, "loss": 0, "trades": 0})
for t in closed_trades:
    ym = t["close_date"][:7]  # YYYY.MM
    monthly[ym]["trades"] += 1
    if t["pnl"] > 0:
        monthly[ym]["wins"] += 1
        monthly[ym]["profit"] += t["pnl"]
    else:
        monthly[ym]["losses"] += 1
        monthly[ym]["loss"] += t["pnl"]

positive_months = 0
negative_months = 0
for ym in sorted(monthly.keys()):
    m = monthly[ym]
    net_m = m["profit"] + m["loss"]
    if net_m > 0:
        positive_months += 1
    else:
        negative_months += 1

print(f"Mois positifs: {positive_months} / {positive_months + negative_months} ({100*positive_months/(positive_months+negative_months):.0f}%)")
print(f"Mois negatifs: {negative_months}")

# Show worst 10 months
print(f"\n--- 10 PIRES MOIS ---")
monthly_list = []
for ym in sorted(monthly.keys()):
    m = monthly[ym]
    net_m = m["profit"] + m["loss"]
    monthly_list.append((ym, net_m, m["trades"], m["wins"]))

monthly_list.sort(key=lambda x: x[1])
for ym, net_m, trades_m, wins_m in monthly_list[:10]:
    wr_m = 100 * wins_m / trades_m if trades_m > 0 else 0
    print(f"  {ym}: ${net_m:>8,.2f} ({trades_m} trades, WR {wr_m:.0f}%)")

# Show best 10 months
print(f"\n--- 10 MEILLEURS MOIS ---")
monthly_list.sort(key=lambda x: x[1], reverse=True)
for ym, net_m, trades_m, wins_m in monthly_list[:10]:
    wr_m = 100 * wins_m / trades_m if trades_m > 0 else 0
    print(f"  {ym}: ${net_m:>8,.2f} ({trades_m} trades, WR {wr_m:.0f}%)")

# --- Analyse par heure d'ouverture ---
print(f"\n--- STATS PAR HEURE D'OUVERTURE ---")
hourly = defaultdict(lambda: {"wins": 0, "losses": 0, "profit": 0, "loss": 0, "trades": 0})
for t in closed_trades:
    hour = int(t["open_date"].split(" ")[1].split(":")[0])
    hourly[hour]["trades"] += 1
    if t["pnl"] > 0:
        hourly[hour]["wins"] += 1
        hourly[hour]["profit"] += t["pnl"]
    else:
        hourly[hour]["losses"] += 1
        hourly[hour]["loss"] += t["pnl"]

print(f"{'Heure':>5} {'Trades':>7} {'WR%':>6} {'Net':>10} {'PF':>6}")
for h in sorted(hourly.keys()):
    hr = hourly[h]
    wr = 100 * hr["wins"] / hr["trades"] if hr["trades"] > 0 else 0
    net_h = hr["profit"] + hr["loss"]
    pf = hr["profit"] / abs(hr["loss"]) if hr["loss"] != 0 else 999
    print(f"{h:>5}h {hr['trades']:>7} {wr:>5.1f}% ${net_h:>9,.2f} {pf:>5.2f}")

# --- Analyse par jour de la semaine ---
print(f"\n--- STATS PAR JOUR DE LA SEMAINE ---")
dow_names = {0: "Lun", 1: "Mar", 2: "Mer", 3: "Jeu", 4: "Ven", 5: "Sam", 6: "Dim"}
daily = defaultdict(lambda: {"wins": 0, "losses": 0, "profit": 0, "loss": 0, "trades": 0})
for t in closed_trades:
    dt = datetime.strptime(t["open_date"], "%Y.%m.%d %H:%M")
    dow = dt.weekday()
    daily[dow]["trades"] += 1
    if t["pnl"] > 0:
        daily[dow]["wins"] += 1
        daily[dow]["profit"] += t["pnl"]
    else:
        daily[dow]["losses"] += 1
        daily[dow]["loss"] += t["pnl"]

print(f"{'Jour':>5} {'Trades':>7} {'WR%':>6} {'Net':>10} {'PF':>6}")
for d in sorted(daily.keys()):
    dd = daily[d]
    wr = 100 * dd["wins"] / dd["trades"] if dd["trades"] > 0 else 0
    net_d = dd["profit"] + dd["loss"]
    pf = dd["profit"] / abs(dd["loss"]) if dd["loss"] != 0 else 999
    print(f"{dow_names[d]:>5} {dd['trades']:>7} {wr:>5.1f}% ${net_d:>9,.2f} {pf:>5.2f}")

# --- Avg trade duration ---
print(f"\n--- DUREE MOYENNE DES TRADES ---")
durations_win = []
durations_loss = []
for t in closed_trades:
    try:
        dt_open = datetime.strptime(t["open_date"], "%Y.%m.%d %H:%M")
        dt_close = datetime.strptime(t["close_date"], "%Y.%m.%d %H:%M")
        dur = (dt_close - dt_open).total_seconds() / 3600  # hours
        if t["pnl"] > 0:
            durations_win.append(dur)
        else:
            durations_loss.append(dur)
    except:
        pass

if durations_win:
    print(f"Duree avg wins: {sum(durations_win)/len(durations_win):.1f}h")
if durations_loss:
    print(f"Duree avg losses: {sum(durations_loss)/len(durations_loss):.1f}h")

# --- DD episodes (> 10%) ---
print(f"\n--- EPISODES DE DRAWDOWN (> 10% du peak) ---")
peak = balances[0]
dd_start_bal = peak
dd_start_date = closed_trades[0]["open_date"] if closed_trades else ""
in_dd = False
dd_episodes = []

for i in range(len(balances)):
    bal = balances[i]
    if bal >= peak:
        if in_dd:
            dd_end_date = closed_trades[i-1]["close_date"] if i > 0 and i-1 < len(closed_trades) else "?"
            dd_episodes.append({
                "start": dd_start_date,
                "end": dd_end_date,
                "peak": dd_start_bal,
                "trough": min_in_dd,
                "dd_pct": (dd_start_bal - min_in_dd) / dd_start_bal * 100,
                "dd_usd": dd_start_bal - min_in_dd
            })
            in_dd = False
        peak = bal
        dd_start_bal = bal
        if i > 0 and i-1 < len(closed_trades):
            dd_start_date = closed_trades[i-1]["close_date"]
    else:
        if not in_dd:
            in_dd = True
            min_in_dd = bal
        else:
            min_in_dd = min(min_in_dd, bal)

# Check if still in DD at end
if in_dd:
    dd_episodes.append({
        "start": dd_start_date,
        "end": closed_trades[-1]["close_date"] if closed_trades else "?",
        "peak": dd_start_bal,
        "trough": min_in_dd,
        "dd_pct": (dd_start_bal - min_in_dd) / dd_start_bal * 100,
        "dd_usd": dd_start_bal - min_in_dd
    })

big_dds = [ep for ep in dd_episodes if ep["dd_pct"] > 10]
for ep in big_dds:
    print(f"  {ep['start']} -> {ep['end']}: -{ep['dd_pct']:.1f}% (${ep['dd_usd']:,.0f}) | Peak ${ep['peak']:,.0f} -> Trough ${ep['trough']:,.0f}")

if not big_dds:
    print("  Aucun episode > 10%")

# --- Lot size distribution ---
print(f"\n--- DISTRIBUTION DES LOTS ---")
lot_ranges = [(0, 0.5), (0.5, 1.0), (1.0, 1.5), (1.5, 2.0), (2.0, 3.0), (3.0, 99)]
for lo, hi in lot_ranges:
    range_trades = [t for t in closed_trades if lo <= t["lots"] < hi]
    if not range_trades:
        continue
    w = sum(1 for t in range_trades if t["pnl"] > 0)
    profit = sum(t["pnl"] for t in range_trades if t["pnl"] > 0)
    loss = sum(t["pnl"] for t in range_trades if t["pnl"] <= 0)
    net_r = profit + loss
    pf = profit / abs(loss) if loss != 0 else 999
    wr = 100 * w / len(range_trades)
    print(f"  {lo:.1f}-{hi:.1f} lots: {len(range_trades):>4} trades | WR {wr:>5.1f}% | Net ${net_r:>10,.2f} | PF {pf:.2f}")

print(f"\n{'=' * 70}")
print(f"FIN ANALYSE")
print(f"{'=' * 70}")
