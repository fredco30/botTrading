#!/usr/bin/env python3
"""AUDIT (read-only) — FX_PDH_001 independent consistency check.

Independent re-derivation of the frozen candidate straight from the parquet,
trade-by-trade against candidates/FX_PDH_001/FX_PDH_001_TRADES.csv, plus:

  V0  faithful re-implementation (must match CSV exactly)
  V1  causally-strict variant:
      - trailing stop uses ATR[i-1] (stop level set at prior close, not the
        current bar's own range), and
      - the ENTRY BAR's low is checked against the initial stop (the original
        replay began exit checks on the bar after entry).
      Quantifies whether either detail materially moves the verdict.

Also re-derives sizing/equity numbers and every integrity check requested.
No parameters are tuned; no 2026 data is touched.
"""
import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import tmlab as T

PIP = 1e-2                    # USDJPY pip = 0.01 JPY (checked below)
SPREAD = 0.9                  # pips
STOP_ATR, TRAIL_ATR, MAX_HOLD = 1.0, 3.0, 48
CAPITAL, MIN_LOT, STEP = 500.0, 0.01, 0.01

df5 = T.load_5m("USDJPY", "2020-01-01", "2025-12-31 23:59")
assert df5.index.max() <= T.SEAL_UTC, "2026 seal violated in audit load"
h1 = T.resample_ohlcv(df5, "1h")
o = h1["open"].to_numpy(); h = h1["high"].to_numpy()
l = h1["low"].to_numpy(); c = h1["close"].to_numpy()
idx = h1.index
n = len(c)
day = np.array([ts.date() for ts in idx])
yrs = np.array([ts.year for ts in idx])

# ---- independent ATR(14) RMA --------------------------------------------
tr = T.true_range(h, l, c)
atr = np.full(n, np.nan)
acc = np.nan; s = 0.0; cnt = 0
for i, v in enumerate(tr):
    if np.isnan(acc):
        s += v; cnt += 1
        if cnt == 14:
            acc = s / 14
    else:
        acc = (acc * 13 + v) / 14
    atr[i] = acc

# ---- independent PDH (prior COMPLETED UTC day's high) --------------------
pdh = np.full(n, np.nan)
prev = np.nan
for d in sorted(set(day)):
    m = day == d
    ii = np.nonzero(m)[0]
    pdh[ii] = prev
    prev = np.max(h[m])

# ---- independent events: first bar of day with high > PDH ----------------
sig = []
for d in sorted(set(day)):
    ii = np.nonzero(day == d)[0]
    if len(ii) < 4 or not np.isfinite(pdh[ii[0]]):
        continue
    brk = ii[h[ii] > pdh[ii]]
    if len(brk):
        sig.append(brk[0])
sig = np.array(sig, "int64")
print(f"independent events: {len(sig)}")


def replay(strict=False, slip=0.0):
    """One-position-at-a-time replay of the frozen rules.

    Sequencing matches the frozen backtest: a bar that EXITS a position
    cannot also trigger a new entry (no fall-through).
    """
    trades = []
    pos = None
    spread_abs = SPREAD * PIP
    slip_abs = slip * PIP
    for i in range(n):
        if pos is not None:
            k = pos["k"]
            if i == k:
                # entry bar: original never exit-checks it (V0 behaviour).
                # strict V1 DOES check the initial stop on the entry bar.
                if strict and l[i] <= pos["stop"]:
                    px = min(o[i], pos["stop"]) - slip_abs
                    trades.append((k, i, px, "stop_entrybar"))
                    pos = None
                    continue
                continue
            hh = pos["hh"]
            if strict:
                a = atr[i - 1] if i >= 1 else np.nan      # stop set at prior close
            else:
                a = atr[i]
            eff_stop = pos["stop"]
            if np.isfinite(a):
                eff_stop = max(pos["stop"], hh - TRAIL_ATR * a)
            stop_hit = l[i] <= eff_stop
            time_hit = (i - k) >= MAX_HOLD
            if stop_hit:
                px = min(o[i], eff_stop) - slip_abs
                trades.append((k, i, px, "stop"))
                pos = None
                continue                                   # no same-bar re-entry
            elif time_hit:
                trades.append((k, i, c[i] - slip_abs, "time"))
                pos = None
                continue                                   # no same-bar re-entry
            pos["hh"] = max(pos["hh"], h[i])
        if pos is None:
            j = np.searchsorted(sig, i, side="right") - 1
            if j >= 0 and sig[j] == i and i + 1 < n and np.isfinite(atr[i]):
                k = i + 1
                entry = o[k] + spread_abs + slip_abs
                pos = {"k": k, "entry": entry,
                       "stop": entry - STOP_ATR * atr[i], "hh": h[k],
                       "sig": i}
    rows = []
    for k, i, px, reason in trades:
        gross = (px - (o[k] + SPREAD * PIP + slip_abs)) / PIP
        rows.append({"entry_i": k, "exit_i": i, "reason": reason,
                     "gross_pips": gross,
                     "net_pips": gross - (SPREAD + slip) - 0.0})
    return pd.DataFrame(rows)


csv = pd.read_csv(os.path.join(HERE, "candidates", "FX_PDH_001",
                               "FX_PDH_001_TRADES.csv"))
v0 = replay(strict=False)
v1 = replay(strict=True)

print("\n=== V0 vs frozen CSV (trade-by-trade) ===")
same_n = len(v0) == len(csv)
m = same_n and np.allclose(v0["entry_i"], csv["entry_i"]) and \
    np.allclose(v0["exit_i"], csv["exit_i"]) and \
    np.allclose(v0["net_pips"], csv["net_pips"], atol=1e-8)
print(f"n: v0={len(v0)} csv={len(csv)} identical={same_n}")
print(f"entry/exit indices + net pips identical: {m}")

def stats(df, label):
    r = df["net_pips"].to_numpy()
    wins = r[r > 0]; losses = r[r <= 0]
    pf = wins.sum() / -losses.sum() if losses.sum() != 0 else np.inf
    se = np.std(r, ddof=1) / np.sqrt(len(r))
    k = max(1, int(round(0.01 * len(r))))
    rb1 = np.mean(np.sort(r)[:-k])
    y = np.array([yrs[df["entry_i"].iloc[i]] for i in range(len(df))])
    byy = {int(yy): float(np.mean(r[y == yy])) for yy in sorted(set(y))}
    tot = float(r.sum())
    c2022 = byy.get(2022, 0) / tot * 100 if tot else np.nan
    print(f"[{label}] n={len(r)} PF={pf:.3f} mean={np.mean(r):+.3f} "
          f"win={np.mean(r>0):.3f} rb1={rb1:+.3f} "
          f"2022share={c2022:.1f}% 2025={byy.get(2025, 0):+.2f}")
    print("   by year: " + " ".join(f"{yy}:{v:+.2f}" for yy, v in byy.items()))
    return {"n": len(r), "pf": pf, "mean": float(np.mean(r)), "rb1": float(rb1),
            "by_year": byy}

s0 = stats(v0, "V0 faithful")
s1 = stats(v1, "V1 strict")

# stress
v1s = replay(strict=True, slip=0.5)
ss = stats(v1s, "V1 strict STRESS")
v0s = replay(strict=False, slip=0.5)
ss0 = stats(v0s, "V0 faithful STRESS")

# entry-bar stop exposure in V0 (trades the original never exit-checked on bar k)
atrk = atr[csv["entry_i"].to_numpy()]
l0 = l[csv["entry_i"].to_numpy()]
stop0 = o[csv["entry_i"].to_numpy()] + SPREAD * PIP - STOP_ATR * atrk
n_exposed = int(np.sum(l0 <= stop0))
print(f"\nentry-bar stop exposure (V0 skipped these exit checks): "
      f"{n_exposed}/{len(csv)} trades ({100*n_exposed/len(csv):.1f}%)")

# integrity: no double counting / no overlap / timestamps
ei = csv["entry_i"].to_numpy(); xi = csv["exit_i"].to_numpy()
print(f"\nunique entry bars: {len(np.unique(ei)) == len(ei)}; "
      f"strictly increasing: {bool(np.all(np.diff(ei) > 0))}; "
      f"no overlap (exit_i < next entry_i): {bool(np.all(xi[:-1] < ei[1:]))}")
print(f"entry always = signal+1: "
      f"{bool(np.all(np.isin(ei - 1, sig)))}")
tmax = idx[xi.max()]
print(f"last exit timestamp: {tmax}  (2026 untouched: {tmax.year <= 2025})")
print(f"all exit_i > entry_i: {bool(np.all(xi > ei))}")

# pip value & sizing re-derivation
print(f"\nPIP const = {PIP} (USDJPY 0.01 JPY); "
      f"0.01-lot pip USD = 1000*{PIP}/USDJPY")
eur5 = T.load_5m("EURUSD", "2020-01-01", "2025-12-31 23:59")
eurc = eur5["close"].to_numpy(); euri = eur5.index
upx = c[ei]
pip_eur = 1000.0 * PIP / upx * eurc[np.searchsorted(euri, idx[ei], side="right") - 1]
stop_pips = STOP_ATR * atrk / PIP
risk_min = stop_pips * pip_eur
lot05 = np.maximum(MIN_LOT, np.floor((0.005 * CAPITAL / (stop_pips * pip_eur * 100)) / STEP) * STEP)
lot10 = np.maximum(MIN_LOT, np.floor((0.01 * CAPITAL / (stop_pips * pip_eur * 100)) / STEP) * STEP)
print(f"stop_pips median={np.median(stop_pips):.1f}; risk@minlot median="
      f"EUR {np.median(risk_min):.2f} ({100*np.median(risk_min)/CAPITAL:.2f}%)")

def equity(lots):
    rm = stop_pips * pip_eur * (lots / MIN_LOT)
    eq = CAPITAL + np.cumsum((v0["net_pips"].to_numpy() / stop_pips) * rm)
    return eq

for lots, name in ((lot05, "0.5%"), (lot10, "1.0%")):
    eq = equity(lots)
    peak = np.maximum.accumulate(eq)
    dd = (peak - eq) / peak
    print(f"equity {name}: end EUR {eq[-1]:.0f}  maxDD {100*dd.max():.1f}%")
