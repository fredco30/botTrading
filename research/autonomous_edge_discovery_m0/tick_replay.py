#!/usr/bin/env python3
"""Tick-exact replay of FROZEN discovery configs (mission §6 realistic
execution): real BID/ASK entry/exit sides, 5s baseline latency, 30s+0.5pip/side
stress. One position at a time per strategy. No tuning after this — results
are accept/reject only.

FROZEN CONFIGS (from M1-sim stage, committed to ledger before this run):
  C1 (F07): trend H1 close>EMA20(H1) | 15min impulse > +4p  -> LONG
            trend H1 close<EMA20(H1) | 15min impulse < -4p  -> SHORT
            SL=12p TP=12p T=60min
  C2 (F12): 4h return > +10p -> LONG ; < -10p -> SHORT
            SL=15p TP=15p T=120min
"""
import numpy as np
import pandas as pd
import aedis_lib as A
import ledger as L

P = 1e-4
b = A.load_bars("H1")
ts, bid, ask = A.load_half("H1")
n = len(b["close"])
close, opn = b["close"], b["open"]

# gap list within the window (weekends excluded by rule) — mtf_lib rule
parts = []
for m in range(1, 7):
    lo = int(pd.Timestamp(f"2017-{m:02d}-01T00:00:00Z").value)
    hi = int(pd.Timestamp(f"2017-{m+1:02d}-01T00:00:00Z").value)
    parts.append(ts[(ts >= lo) & (ts < hi)])
prev_last = None
gaps = []
for t_m in parts:
    if len(t_m) == 0:
        continue
    if prev_last is not None and A.mtf_lib.is_data_gap(int(prev_last), int(t_m[0])):
        gaps.append((int(prev_last), int(t_m[0])))
    d = np.diff(t_m)
    for i in np.flatnonzero(d > 3600 * int(1e9)):
        t1, t2 = int(t_m[i]), int(t_m[i + 1])
        if A.mtf_lib.is_data_gap(t1, t2):
            gaps.append((t1, t2))
    prev_last = t_m[-1]
gap_starts = np.array([g[0] for g in gaps], dtype=np.int64)
print(f"gaps in window: {len(gaps)}")


def bar_decision_ns(i):
    return int(b["start"][i]) + 60 * int(1e9)


def replay(sig_idx, side, stop_p, tp_p, tmax, latency_ns, slip_pips, label,
           family):
    slip = slip_pips * P
    trades = []
    occ_until = -1
    n_no_fill = 0
    for i in sig_idx:
        if i <= occ_until:
            continue
        d = bar_decision_ns(i)
        e = A.tick_entry(ts, bid, ask, d, side, gap_starts, latency_ns)
        if e is None:
            n_no_fill += 1
            continue
        entry = e["price"] + (slip if side == 1 else -slip)
        stop = entry - side * stop_p * P
        tgt = entry + side * tp_p * P
        r = A.tick_resolve(ts, bid, ask, side, e["idx"], e["ts"], stop, tgt,
                           e["ts"] + tmax * 60 * int(1e9), gap_starts, slip)
        if r["status"] in ("GAP",):
            continue
        net = side * (r["exit_price"] - entry) / P
        trades.append({"i": int(i), "net": float(net),
                       "exit": r["status"], "entry_ts": e["ts"]})
        occ_until = i + 1 + tmax  # occupancy in bar units (approx, matches sim)
    nt = np.array([t["net"] for t in trades])
    if len(nt) == 0:
        print(f"{label}: NO TRADES (no_fill={n_no_fill})")
        return
    wins, losses = nt[nt > 0], nt[nt < 0]
    pf = min(float(wins.sum() / abs(losses.sum())), 999.0) if len(losses) and losses.sum() else 999.0
    rb = A.mtf_lib.remove_best_1pct(nt)
    exp_r = float(np.mean(nt / stop_p))
    exits = {s: sum(1 for t in trades if t["exit"] == s)
             for s in ("STOP", "TARGET", "TIME")}
    status = "TICK_REPLAY"
    print(f"{label}: N={len(nt)} mean={nt.mean():.2f}p PF={pf:.2f} expR={exp_r:.3f} "
          f"stressOK rb={rb:.2f} WR={(nt>0).mean():.2f} exits={exits}")
    L.log(family, "tick replay (5s/30s)", label, len(nt), nt.mean(), PF=pf,
          expectancy_R=exp_r,
          stress_R=(nt.mean() - 1.0) if slip_pips == 0 else np.nan,
          remove_best=rb, status=status,
          reason=f"latency={latency_ns/1e9:.0f}s slip={slip_pips}p/side "
                 f"exits={exits} nofill={n_no_fill}")
    return trades


# ---------------- signal construction (frozen) ----------------
# C1: H1 EMA20 trend + 15-min impulse
h1_start = (b["start"] // (3600 * int(1e9))) * (3600 * int(1e9))
hu, inv = np.unique(h1_start, return_inverse=True)
hc = np.array([close[inv == i][-1] for i in range(len(hu))])
ema20 = A.mtf_lib.ema(hc, 20)
trend = np.where(hc > ema20, 1, np.where(hc < ema20, -1, 0))[inv]
ret15 = np.full(n, np.nan)
ret15[15:] = (close[15:] - close[:-15]) / P
ok1 = np.isfinite(ret15) & np.isfinite(trend)
c1_long = np.flatnonzero(ok1 & (trend == 1) & (ret15 > 4))
c1_short = np.flatnonzero(ok1 & (trend == -1) & (ret15 < -4))

# C2: 4h momentum
H4NS = 4 * 3600 * int(1e9)
h4 = b["start"] // H4NS
hu4, inv4 = np.unique(h4, return_inverse=True)
hc4 = np.array([close[inv4 == i][-1] for i in range(len(hu4))])
r4 = np.full(len(hu4), np.nan)
r4[4:] = (hc4[4:] - hc4[:-4]) / P
r4now = r4[inv4]
ok2 = np.isfinite(r4now)
c2_long = np.flatnonzero(ok2 & (r4now > 10))
c2_short = np.flatnonzero(ok2 & (r4now < -10))

print("=== TICK-EXACT REPLAY — FROZEN, baseline (5s, 0 slip)")
t1L = replay(c1_long, 1, 12, 12, 60, A.LATENCY_NS, 0.0, "C1 LONG", "F07t")
t1S = replay(c1_short, -1, 12, 12, 60, A.LATENCY_NS, 0.0, "C1 SHORT", "F07t")
t2L = replay(c2_long, 1, 15, 15, 120, A.LATENCY_NS, 0.0, "C2 LONG", "F12t")
t2S = replay(c2_short, -1, 15, 15, 120, A.LATENCY_NS, 0.0, "C2 SHORT", "F12t")

print("=== TICK-EXACT REPLAY — STRESS (30s latency, 0.5 pip/side)")
replay(c1_long, 1, 12, 12, 60, A.LATENCY_STRESS_NS, 0.5, "C1 LONG", "F07t_s")
replay(c1_short, -1, 12, 12, 60, A.LATENCY_STRESS_NS, 0.5, "C1 SHORT", "F07t_s")
replay(c2_long, 1, 15, 15, 120, A.LATENCY_STRESS_NS, 0.5, "C2 LONG", "F12t_s")
replay(c2_short, -1, 15, 15, 120, A.LATENCY_STRESS_NS, 0.5, "C2 SHORT", "F12t_s")

# monthly split of baseline tick trades
months = pd.to_datetime(b["start"], utc=True).month


def month_split(trades, nm):
    if not trades:
        return
    print(f"--- {nm} monthly (tick baseline)")
    mon = np.array([months[min(t["i"] + 1, n - 1)] for t in trades])
    nt = np.array([t["net"] for t in trades])
    for mth in range(1, 7):
        sel = nt[mon == mth]
        if len(sel):
            print(f"   2017-{mth:02d} N={len(sel):4d} mean={sel.mean():7.2f}p tot={sel.sum():8.1f}p")


for trades, nm in ((t1L, "C1 LONG"), (t1S, "C1 SHORT"),
                   (t2L, "C2 LONG"), (t2S, "C2 SHORT")):
    month_split(trades, nm)
