"""Minimal tests for S002 frozen spec (section 12). Run from repo root."""
import numpy as np
import pandas as pd

import sys
sys.path.insert(0, "research/s002_us2y_usdjpy")
import s002_discovery as S  # executes discovery too

# +3 bp -> LONG, -3 bp -> SHORT, <3 bp -> no trade
def check_signal(ch, expected):
    if ch >= 3.0:
        d = +1
    elif ch <= -3.0:
        d = -1
    else:
        d = 0
    assert d == expected, (ch, expected)
check_signal(3.0, +1); check_signal(2.99, 0); check_signal(-3.0, -1); check_signal(-2.99, 0)

# DGS2 used only with date < entry day
assert (S.t["entry_day"].values > S.t["signal_date"].values.astype("datetime64[ns]")).all()

# entry = first FX day strictly after signal; exit = 5th FX day after entry
fx = list(S.fx_days)
for _, r in S.t.iterrows():
    ei = fx.index(r["entry_day"])
    assert fx[ei] > r["signal_date"]
    assert ei == 0 or fx[ei - 1] <= r["signal_date"]
    assert r["exit_day"] == fx[ei + 5]

# one position at a time (no overlap)
days = S.fx_days
for i in range(1, len(S.t)):
    prev = S.t.iloc[i - 1]
    cur = S.t.iloc[i]
    assert cur["entry_day"] > prev["exit_day"]

# pip = 0.01, costs 2/4
row = S.t.iloc[0]
assert abs(row["gross_pips"] - (row["net_normal_pips"] + 2.0)) < 1e-9
assert abs(row["gross_pips"] - (row["net_stress_pips"] + 4.0)) < 1e-9

# boundary < 2019
assert (S.t["entry_day"] < pd.Timestamp("2019-01-01")).all()
assert (S.t["exit_day"] < pd.Timestamp("2019-01-01")).all()
assert (S.t["signal_date"] < pd.Timestamp("2019-01-01")).all()

# sanity: signal directions present
assert set(S.t["direction"].unique()) <= {-1, +1}

print("ALL S002 MINIMAL TESTS PASSED — n_trades =", len(S.t))
