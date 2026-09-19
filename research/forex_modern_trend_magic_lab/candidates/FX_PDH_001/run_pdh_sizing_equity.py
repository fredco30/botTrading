#!/usr/bin/env python3
"""FX_PDH_001 — EUR 500 position sizing gate (sections 18/19/20) and
equity-path simulation with realistic rounded lots (section 33).

Sizing uses per-trade ACTUAL stop distances (1*ATR at entry, H1) and the
real conversion chain pip -> USD (1/USDJPY) -> EUR (x EURUSD), evaluated
causally at each entry date from the 5m parquet closes.
"""
import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import tmlab as T

CAPITAL = 500.0
MIN_LOT = 0.01
LOT_STEP = 0.01
PIP = T.PIP["USDJPY"]

trades = pd.read_csv(os.path.join(HERE, "FX_PDH_001_TRADES.csv"))
trades["entry_time"] = pd.to_datetime(trades["entry_i"].map(lambda _: np.nan))
# recover entry timestamps from the h1 index
df5 = T.load_5m("USDJPY", "2020-01-01", "2025-12-31 23:59")
h1 = T.resample_ohlcv(df5, "1h")
idx = h1.index
usdjpy_close = h1["close"].to_numpy()

eurusd = T.load_5m("EURUSD", "2020-01-01", "2025-12-31 23:59")
eur_close = eurusd["close"].to_numpy()
eur_idx = eurusd.index


def eur_rate(when, usdjpy_px):
    """EUR value of 1 pip (0.0001*1000 JPY... for USDJPY pip=0.01 JPY per
    0.01 lot => pip USD value = 1000 * 0.01 / usdjpy)."""
    j = np.searchsorted(idx, when, side="right") - 1
    pip_usd = 1000.0 * PIP / usdjpy_px          # 0.01 lot: 1000 USD notional
    k = np.searchsorted(eur_idx, when, side="right") - 1
    return pip_usd * eur_close[k]               # EUR per pip at 0.01 lot


rows = []
for _, t in trades.iterrows():
    when = idx[int(t["entry_i"])]
    px = usdjpy_close[int(t["entry_i"])]
    pip_eur = eur_rate(when, px)
    stop_pips = 1.0 * float(t["atr_entry"]) / PIP
    risk_min = stop_pips * pip_eur                       # EUR at 0.01 lot
    # standard-lot pip value = 100 x min-lot pip value
    lot_05 = 0.005 * CAPITAL / (stop_pips * pip_eur * 100) if risk_min > 0 else 0
    lot_05_r = max(MIN_LOT, np.floor(lot_05 / LOT_STEP) * LOT_STEP)
    lot_1 = 0.01 * CAPITAL / (stop_pips * pip_eur * 100)
    lot_1_r = max(MIN_LOT, np.floor(lot_1 / LOT_STEP) * LOT_STEP)
    rows.append({"entry_i": int(t["entry_i"]), "year": int(t["year"]),
                 "stop_pips": stop_pips, "pip_eur_at_minlot": pip_eur,
                 "risk_eur_minlot": risk_min,
                 "risk_pct_minlot": 100 * risk_min / CAPITAL,
                 "lot_for_05": lot_05, "lot_05_rounded": lot_05_r,
                 "lot_for_1": lot_1, "lot_1_rounded": lot_1_r,
                 "r_multiple": float(t["net_pips"]) / stop_pips})

sdf = pd.DataFrame(rows)
sdf.to_csv(os.path.join(HERE, "FX_PDH_001_SIZING.csv"), index=False)

print("=== EUR 500 SIZING GATE (FX_PDH_001, stop = 1*ATR H1) ===")
print(f"CAPITAL_EUR=500  MIN_LOT=0.01  LOT_STEP=0.01")
print(f"stop_pips: med={sdf['stop_pips'].median():.1f} "
      f"p10={sdf['stop_pips'].quantile(.1):.1f} p90={sdf['stop_pips'].quantile(.9):.1f}")
print(f"pip value at 0.01 lot: med EUR {sdf['pip_eur_at_minlot'].median():.4f}")
print(f"RISK at min lot: med EUR {sdf['risk_eur_minlot'].median():.2f} "
      f"= {sdf['risk_pct_minlot'].median():.2f}% of capital "
      f"(p90 {sdf['risk_pct_minlot'].quantile(.9):.2f}%)")
print(f"lot for 0.5% risk: med {sdf['lot_for_05'].median():.3f} -> rounded "
      f"med {sdf['lot_05_rounded'].median():.2f}")
print(f"lot for 1.0% risk: med {sdf['lot_for_1'].median():.3f} -> rounded "
      f"med {sdf['lot_1_rounded'].median():.2f}")

# ---- equity simulation at 0.5% intended risk, realistic rounded lots ----
def simulate(sdf, risk):
    lot_col = "lot_05_rounded" if risk == 0.005 else "lot_1_rounded"
    eq = CAPITAL
    path = []
    for _, r in sdf.iterrows():
        lot = max(r[lot_col], MIN_LOT)
        # risk actually taken at this lot
        risk_eur = r["stop_pips"] * r["pip_eur_at_minlot"] * (lot / MIN_LOT)
        pnl = r["r_multiple"] * risk_eur
        eq += pnl
        path.append((r["entry_i"], r["year"], eq))
    return np.array([p[2] for p in path])

for risk, name in ((0.005, "0.5%"), (0.01, "1.0%")):
    eq = simulate(sdf, risk)
    peak = np.maximum.accumulate(eq)
    dd = (peak - eq) / peak
    yrs = sdf["year"].to_numpy()
    ret_year = {int(y): (eq[np.nonzero(yrs == y)[0][-1]] /
                         (eq[np.nonzero(yrs == y)[0][0] - 1] if np.nonzero(yrs == y)[0][0] > 0 else CAPITAL) - 1) * 100
                for y in sorted(set(yrs))}
    # worst rolling 12m (approx by trades window): use yearly for simplicity + max losing streak
    streak = worst = 0
    for r in sdf["r_multiple"]:
        if r <= 0:
            streak += 1
            worst = max(worst, streak)
        else:
            streak = 0
    print(f"\n=== EQUITY SIM risk={name} (rounded lots) ===")
    print(f"ending equity EUR {eq[-1]:.2f} | max DD {100*dd.max():.1f}% "
          f"(EUR {np.max(peak-eq):.2f}) | max losing streak {worst}")
    print("  by year %: " + " ".join(f"{y}:{v:+.1f}" for y, v in ret_year.items()))
    veto = (100*dd.max() >= 50 or eq.min() <= 250 or
            min(ret_year.values()) <= -40)
    warn = (100*dd.max() >= 30 or min(ret_year.values()) <= -25)
    print(f"  VETO={'YES' if veto else 'no'}  WARN={'YES' if warn else 'no'}")

# margin scenarios
notional_usd = 100000.0 * sdf["lot_1_rounded"].median()   # 1.0 lot = 100k USD
print(f"\nmedian rounded lot at 1% risk: {sdf['lot_1_rounded'].median():.2f} "
      f"-> notional ~${notional_usd:,.0f}")
for lev in (20, 30):
    print(f"  margin at 1:{lev} ~ EUR {notional_usd/lev/eur_close[-1]:.0f} "
          f"(SCENARIO - NOT BROKER VERIFIED)")
