#!/usr/bin/env python3
"""Frozen-rule replay on a half-year window. Discovery ran on H1 ticks only;
this script applies the IDENTICAL frozen rules to H2 (confirmation).
No parameters may be changed between discovery freeze and confirmation run."""
import sys
import numpy as np
import pandas as pd
import aedis_lib as A
import ledger as L

HALF = sys.argv[1] if len(sys.argv) > 1 else "H2"
P = 1e-4
b = A.load_bars(HALF)
ts, bid, ask = A.load_half(HALF)
n = len(b["close"])
close = b["close"]

# gaps
month_nums = range(1, 7) if HALF == "H1" else range(7, 13)
parts = []
for m in month_nums:
    lo = int(pd.Timestamp(f"2017-{m:02d}-01T00:00:00Z").value)
    hi = int(pd.Timestamp(f"2017-{m+1:02d}-01T00:00:00Z").value) if m < 12 \
        else int(pd.Timestamp("2018-01-01T00:00:00Z").value)
    parts.append(ts[(ts >= lo) & (ts < hi)])
prev_last, gaps = None, []
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


def bar_decision_ns(i):
    return int(b["start"][i]) + 60 * int(1e9)


def replay(sig_idx, side, stop_p, tp_p, tmax, latency_ns, slip_pips, label):
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
        if r["status"] == "GAP":
            continue
        net = side * (r["exit_price"] - entry) / P
        trades.append({"i": int(i), "net": float(net), "exit": r["status"]})
        occ_until = i + 1 + tmax
    nt = np.array([t["net"] for t in trades])
    if len(nt) == 0:
        print(f"{label}: NO TRADES")
        return None
    wins, losses = nt[nt > 0], nt[nt < 0]
    pf = min(float(wins.sum() / abs(losses.sum())), 999.0) if len(losses) and losses.sum() else 999.0
    rb = A.mtf_lib.remove_best_1pct(nt)
    exp_r = float(np.mean(nt / stop_p))
    exits = {s: sum(1 for t in trades if t["exit"] == s)
             for s in ("STOP", "TARGET", "TIME")}
    print(f"{label}: N={len(nt)} mean={nt.mean():.2f}p PF={pf:.2f} expR={exp_r:.3f} "
          f"rb={rb:.2f} WR={(nt>0).mean():.2f} exits={exits}")
    return {"trades": trades, "nt": nt, "pf": pf, "rb": rb, "exp_r": exp_r}


# ---------- frozen signal construction (identical to discovery) ----------
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

print(f"=== FROZEN REPLAY {HALF} — baseline (5s, 0 slip)")
t1L = replay(c1_long, 1, 12, 12, 60, A.LATENCY_NS, 0.0, "C1 LONG")
t1S = replay(c1_short, -1, 12, 12, 60, A.LATENCY_NS, 0.0, "C1 SHORT")
t2L = replay(c2_long, 1, 15, 15, 120, A.LATENCY_NS, 0.0, "C2 LONG")
t2S = replay(c2_short, -1, 15, 15, 120, A.LATENCY_NS, 0.0, "C2 SHORT")

print(f"=== FROZEN REPLAY {HALF} — stress (30s, 0.5 pip/side)")
replay(c1_long, 1, 12, 12, 60, A.LATENCY_STRESS_NS, 0.5, "C1 LONG")
replay(c1_short, -1, 12, 12, 60, A.LATENCY_STRESS_NS, 0.5, "C1 SHORT")
replay(c2_long, 1, 15, 15, 120, A.LATENCY_STRESS_NS, 0.5, "C2 LONG")
replay(c2_short, -1, 15, 15, 120, A.LATENCY_STRESS_NS, 0.5, "C2 SHORT")

months = pd.to_datetime(b["start"], utc=True).month
for res, nm in ((t1L, "C1 LONG"), (t1S, "C1 SHORT"),
                (t2L, "C2 LONG"), (t2S, "C2 SHORT")):
    if not res:
        continue
    print(f"--- {nm} monthly")
    mon = np.array([months[min(t["i"] + 1, n - 1)] for t in res["trades"]])
    nt = res["nt"]
    for mth in (range(1, 7) if HALF == "H1" else range(7, 13)):
        sel = nt[mon == mth]
        if len(sel):
            print(f"   2017-{mth:02d} N={len(sel):4d} mean={sel.mean():7.2f}p tot={sel.sum():8.1f}p")
