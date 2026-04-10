#!/usr/bin/env python3
"""
Analyse EMA_Pullback_pyramid_v2 — 16 ans
Focus: L0 normaux vs L0 inversés (REV)
"""
from collections import defaultdict
from datetime import datetime

import sys
FILE = sys.argv[1] if len(sys.argv) > 1 else "EMA_Pullback_pyramid_v2Test01_16ans.txt"

# Parse — skip modify lines, pair opens with closes
events = []
with open(FILE) as f:
    for line in f:
        parts = line.strip().split("\t")
        if len(parts) < 10:
            continue
        try:
            action = parts[2].strip()
            if action == "modify":
                continue
            events.append({
                "idx": int(parts[0]),
                "date": parts[1].strip(),
                "action": action,
                "ticket": int(parts[3]),
                "lots": float(parts[4]),
                "price": float(parts[5]),
                "sl": float(parts[6]),
                "tp": float(parts[7]),
                "pnl": float(parts[8]),
                "balance": float(parts[9])
            })
        except (ValueError, IndexError):
            continue

# Pair opens and closes
opens = {}
closed = []
for e in events:
    if e["action"] in ("buy", "sell"):
        opens[e["ticket"]] = e
    elif e["action"] in ("s/l", "t/p", "close at stop"):
        if e["ticket"] in opens:
            op = opens[e["ticket"]]
            closed.append({
                "ticket": e["ticket"],
                "type": op["action"],  # buy or sell
                "open_date": op["date"],
                "close_date": e["date"],
                "lots": op["lots"],
                "open_price": op["price"],
                "close_price": e["price"],
                "sl": op["sl"],
                "tp": op["tp"],
                "pnl": e["pnl"],
                "balance": e["balance"],
                "exit": e["action"]
            })

print(f"{'='*70}")
print(f"ANALYSE v2 — 16 ans ({FILE})")
print(f"{'='*70}")
print(f"Trades fermes: {len(closed)}")
print(f"Balance initiale: $10,000")
print(f"Balance finale: ${closed[-1]['balance']:,.2f}" if closed else "N/A")
net = sum(t["pnl"] for t in closed)
print(f"Net profit: ${net:,.2f}")

# --- Detect reverse trades ---
# A reverse trade opens at the same minute (or within 1 min) as the previous SL,
# in the opposite direction, and the previous trade was L0
# First: reconstruct pyramid levels and tag reverse trades

streak = 0
tagged = []  # each trade gets: level, is_reverse

for i, t in enumerate(closed):
    # Check if this is a reverse trade:
    # - previous trade was a loss
    # - previous trade was L0 (streak was 0 when it opened)
    # - this trade opens at same minute as previous close
    # - this trade is opposite direction
    is_reverse = False
    if i > 0:
        prev = closed[i-1]
        prev_tag = tagged[i-1]
        # Time check: open at same time or within 1 minute of prev close
        try:
            dt_prev_close = datetime.strptime(prev["close_date"], "%Y.%m.%d %H:%M")
            dt_this_open = datetime.strptime(t["open_date"], "%Y.%m.%d %H:%M")
            time_diff = abs((dt_this_open - dt_prev_close).total_seconds())
        except:
            time_diff = 9999

        # Reverse conditions:
        # 1. Previous was a loss (but could be BE with tiny pnl, so check exit = s/l and pnl <= small)
        # 2. Previous was L0 and not already a reverse
        # 3. Opens within 1 minute
        # 4. Opposite direction
        prev_was_loss = prev["pnl"] < 0 or (prev["exit"] == "s/l" and prev["pnl"] <= 5)  # BE trades have tiny positive pnl
        prev_was_l0_normal = prev_tag["level"] == 0 and not prev_tag["is_reverse"]
        opposite_dir = (prev["type"] != t["type"])

        if prev_was_loss and prev_was_l0_normal and time_diff <= 60 and opposite_dir:
            is_reverse = True

    if is_reverse:
        level = 0  # reverse is always L0
        # Reverse does not affect streak
        tag = {"level": level, "is_reverse": True}
    else:
        level = min(streak, 2)
        tag = {"level": level, "is_reverse": False}
        # Update streak
        if t["pnl"] > 0:
            streak = min(streak + 1, 2)
        else:
            streak = 0

    tagged.append(tag)

# --- Now compute stats by category ---
categories = {
    "L0 Normal": [],
    "L0 Reverse (REV)": [],
    "L1": [],
    "L2": []
}

for i, t in enumerate(closed):
    tag = tagged[i]
    if tag["is_reverse"]:
        categories["L0 Reverse (REV)"].append(t)
    elif tag["level"] == 0:
        categories["L0 Normal"].append(t)
    elif tag["level"] == 1:
        categories["L1"].append(t)
    else:
        categories["L2"].append(t)

print(f"\n{'='*70}")
print(f"DECOMPOSITION PAR CATEGORIE")
print(f"{'='*70}")
print(f"{'Categorie':<20} {'N':>5} {'Wins':>5} {'WR%':>6} {'Net':>12} {'Gains':>12} {'Pertes':>12} {'PF':>6} {'AvgW':>8} {'AvgL':>8}")
print("-" * 105)

for cat_name in ["L0 Normal", "L0 Reverse (REV)", "L1", "L2"]:
    trades = categories[cat_name]
    if not trades:
        print(f"{cat_name:<20} {'0':>5}")
        continue
    wins = [t for t in trades if t["pnl"] > 0]
    losses = [t for t in trades if t["pnl"] <= 0]
    total_w = sum(t["pnl"] for t in wins)
    total_l = sum(t["pnl"] for t in losses)
    net_c = total_w + total_l
    pf = total_w / abs(total_l) if total_l != 0 else 999
    wr = 100 * len(wins) / len(trades)
    avg_w = total_w / len(wins) if wins else 0
    avg_l = total_l / len(losses) if losses else 0
    print(f"{cat_name:<20} {len(trades):>5} {len(wins):>5} {wr:>5.1f}% ${net_c:>10,.2f} ${total_w:>10,.2f} ${total_l:>10,.2f} {pf:>5.2f} ${avg_w:>7,.0f} ${avg_l:>7,.0f}")

# --- L0 Normal vs L0 Reverse deep dive ---
print(f"\n{'='*70}")
print(f"DEEP DIVE: L0 REVERSE")
print(f"{'='*70}")

rev_trades = categories["L0 Reverse (REV)"]
if rev_trades:
    # Exit type
    print(f"\n--- Type de sortie REV ---")
    exit_types = defaultdict(lambda: {"count": 0, "pnl": 0})
    for t in rev_trades:
        exit_types[t["exit"]]["count"] += 1
        exit_types[t["exit"]]["pnl"] += t["pnl"]
    for ex in sorted(exit_types):
        d = exit_types[ex]
        print(f"  {ex:>15}: {d['count']:>4} trades | Net ${d['pnl']:>10,.2f}")

    # Par direction
    print(f"\n--- REV par direction ---")
    for direction in ["buy", "sell"]:
        dir_trades = [t for t in rev_trades if t["type"] == direction]
        if not dir_trades:
            continue
        w = sum(1 for t in dir_trades if t["pnl"] > 0)
        profit = sum(t["pnl"] for t in dir_trades if t["pnl"] > 0)
        loss = sum(t["pnl"] for t in dir_trades if t["pnl"] <= 0)
        net_d = profit + loss
        pf = profit / abs(loss) if loss != 0 else 999
        wr = 100 * w / len(dir_trades)
        print(f"  {direction.upper():>5}: {len(dir_trades):>4} trades | WR {wr:>5.1f}% | Net ${net_d:>10,.2f} | PF {pf:.2f}")

    # SL distance des REV
    print(f"\n--- REV SL distance (pips) ---")
    sl_dists = []
    for t in rev_trades:
        if t["type"] == "buy":
            sl_dist = abs(t["open_price"] - t["sl"]) * 10000
        else:
            sl_dist = abs(t["sl"] - t["open_price"]) * 10000
        sl_dists.append(sl_dist)
    if sl_dists:
        print(f"  Min: {min(sl_dists):.1f} | Avg: {sum(sl_dists)/len(sl_dists):.1f} | Max: {max(sl_dists):.1f}")
        # Distribution
        buckets = [(0,15), (15,25), (25,35), (35,50), (50,100), (100,999)]
        for lo, hi in buckets:
            bucket_trades = [(t, d) for t, d in zip(rev_trades, sl_dists) if lo <= d < hi]
            if not bucket_trades:
                continue
            bw = sum(1 for t, d in bucket_trades if t["pnl"] > 0)
            bp = sum(t["pnl"] for t, d in bucket_trades if t["pnl"] > 0)
            bl = sum(t["pnl"] for t, d in bucket_trades if t["pnl"] <= 0)
            bpf = bp / abs(bl) if bl != 0 else 999
            bwr = 100 * bw / len(bucket_trades)
            print(f"  {lo:>3}-{hi:<3} pips: {len(bucket_trades):>3} trades | WR {bwr:>5.1f}% | PF {bpf:.2f} | Net ${bp+bl:>8,.2f}")

    # Par annee
    print(f"\n--- REV par annee ---")
    yearly_rev = defaultdict(lambda: {"trades": 0, "wins": 0, "pnl": 0})
    for t in rev_trades:
        y = t["close_date"][:4]
        yearly_rev[y]["trades"] += 1
        yearly_rev[y]["pnl"] += t["pnl"]
        if t["pnl"] > 0:
            yearly_rev[y]["wins"] += 1
    print(f"  {'Year':<6} {'N':>4} {'Wins':>4} {'WR%':>6} {'Net':>10}")
    for y in sorted(yearly_rev):
        d = yearly_rev[y]
        wr = 100 * d["wins"] / d["trades"] if d["trades"] > 0 else 0
        print(f"  {y:<6} {d['trades']:>4} {d['wins']:>4} {wr:>5.1f}% ${d['pnl']:>9,.2f}")

# --- Impact global: avec vs sans REV ---
print(f"\n{'='*70}")
print(f"IMPACT GLOBAL: AVEC vs SANS REVERSE")
print(f"{'='*70}")

all_normal = [t for i, t in enumerate(closed) if not tagged[i]["is_reverse"]]
all_rev = [t for i, t in enumerate(closed) if tagged[i]["is_reverse"]]

normal_net = sum(t["pnl"] for t in all_normal)
rev_net = sum(t["pnl"] for t in all_rev)
total_net = normal_net + rev_net

normal_wins = sum(t["pnl"] for t in all_normal if t["pnl"] > 0)
normal_loss = sum(t["pnl"] for t in all_normal if t["pnl"] <= 0)
rev_wins = sum(t["pnl"] for t in all_rev if t["pnl"] > 0)
rev_loss = sum(t["pnl"] for t in all_rev if t["pnl"] <= 0)

pf_normal = normal_wins / abs(normal_loss) if normal_loss != 0 else 999
pf_total = (normal_wins + rev_wins) / abs(normal_loss + rev_loss) if (normal_loss + rev_loss) != 0 else 999

print(f"  Sans REV:  {len(all_normal):>4} trades | Net ${normal_net:>10,.2f} | PF {pf_normal:.2f}")
print(f"  REV seul:  {len(all_rev):>4} trades | Net ${rev_net:>10,.2f}")
print(f"  TOTAL:     {len(closed):>4} trades | Net ${total_net:>10,.2f} | PF {pf_total:.2f}")
print(f"  REV contribution: ${rev_net:>+10,.2f} ({100*rev_net/total_net:.1f}% du profit total)" if total_net != 0 else "")

# --- DD analysis ---
print(f"\n{'='*70}")
print(f"DRAWDOWN")
print(f"{'='*70}")

balances = [10000.0]
for t in closed:
    balances.append(t["balance"])

peak = balances[0]
max_dd = 0
max_dd_pct = 0
for bal in balances:
    if bal > peak:
        peak = bal
    dd_pct = (peak - bal) / peak * 100 if peak > 0 else 0
    if dd_pct > max_dd_pct:
        max_dd_pct = dd_pct
        max_dd = peak - bal

print(f"  Max DD: ${max_dd:,.2f} ({max_dd_pct:.1f}%)")
print(f"  Balance peak: ${max(balances):,.2f}")
print(f"  Balance finale: ${balances[-1]:,.2f}")

# --- Stats par annee (toutes categories) ---
print(f"\n{'='*70}")
print(f"STATS PAR ANNEE")
print(f"{'='*70}")
yearly = defaultdict(lambda: {"trades": 0, "wins": 0, "profit": 0, "loss": 0, "rev_trades": 0, "rev_net": 0})
for i, t in enumerate(closed):
    y = t["close_date"][:4]
    yearly[y]["trades"] += 1
    if t["pnl"] > 0:
        yearly[y]["wins"] += 1
        yearly[y]["profit"] += t["pnl"]
    else:
        yearly[y]["loss"] += t["pnl"]
    if tagged[i]["is_reverse"]:
        yearly[y]["rev_trades"] += 1
        yearly[y]["rev_net"] += t["pnl"]

print(f"{'Year':<6} {'Trades':>7} {'WR%':>6} {'Net':>10} {'PF':>6} | {'REV N':>5} {'REV Net':>10}")
for y in sorted(yearly):
    d = yearly[y]
    net_y = d["profit"] + d["loss"]
    wr = 100 * d["wins"] / d["trades"] if d["trades"] > 0 else 0
    pf = d["profit"] / abs(d["loss"]) if d["loss"] != 0 else 999
    print(f"{y:<6} {d['trades']:>7} {wr:>5.1f}% ${net_y:>9,.2f} {pf:>5.2f} | {d['rev_trades']:>5} ${d['rev_net']:>9,.2f}")

print(f"\n{'='*70}")
print("FIN ANALYSE")
print(f"{'='*70}")
