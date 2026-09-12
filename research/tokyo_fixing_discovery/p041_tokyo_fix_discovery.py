"""P041 — Tokyo Fixing Post-Fix Reversal — DISCOVERY (fail-fast, frozen rule).

Short USDJPY at open of 10:00 JST bar, exit at open of 10:30 JST bar.
Discovery window: [2010-01-01, 2019-01-01) UTC. 2019+ never loaded.
"""
import numpy as np
import pandas as pd

DATA = "data_raw/parquet/USDJPY_5m.parquet"
START = pd.Timestamp("2010-01-01", tz="UTC")
END = pd.Timestamp("2019-01-01", tz="UTC")  # exclusive
PIP = 0.01
COST_NORMAL = 2.0   # pips round-trip
COST_STRESS = 4.0   # pips round-trip
SEED = 42
N_BOOT = 2000

# --- Load strictly < 2019-01-01 UTC ---
df = pd.read_parquet(DATA)
if df.index.tz is None:
    raise SystemExit("index not tz-aware")
df.index = pd.to_datetime(df.index, utc=True)
tcol = "ts"
df[tcol] = df.index
df = df[df[tcol] < END].copy()  # hard cut BEFORE any other access
assert df[tcol].max() < END, "2019+ data accessed"
df = df[df[tcol] >= START]

df["jst"] = df[tcol].dt.tz_convert("Asia/Tokyo")
df["date"] = df["jst"].dt.date
df["hm"] = df["jst"].dt.strftime("%H:%M")

open_col = "open" if "open" in df.columns else df.columns[1]

# --- UTC->JST conversion test: known instant ---
probe = df[tcol].iloc[0]
jst_probe = probe.tz_convert("Asia/Tokyo")
assert jst_probe.utcoffset().total_seconds() == 9 * 3600
assert jst_probe.hour == (probe.hour + 9) % 24
sample = df[df["hm"] == "10:00"].iloc[0]
assert sample["jst"].hour == 10 and sample["jst"].minute == 0
assert sample[tcol].hour == 1  # 10:00 JST == 01:00 UTC
print(f"[TEST] UTC->JST conversion OK (JST = UTC+9 fixed, e.g. {probe} -> {jst_probe})")

entry = df[df["hm"] == "10:00"].set_index("date")[open_col].rename("entry")
exit_ = df[df["hm"] == "10:30"].set_index("date")[open_col].rename("exit")
assert entry.index.is_unique and exit_.index.is_unique
trades = pd.concat([entry, exit_], axis=1).dropna()

# entry/exit time test
e_times = sorted(df[df["date"].isin(trades.index)]["jst"].dt.time.unique())
t1000 = df[df["hm"] == "10:00"]["jst"].dt.time.unique()
t1030 = df[df["hm"] == "10:30"]["jst"].dt.time.unique()
assert all(str(t) == "10:00:00" for t in t1000) and all(str(t) == "10:30:00" for t in t1030)
print("[TEST] entry=10:00 JST, exit=10:30 JST exact OK")

# --- Short PnL: short profits when price falls -> (entry - exit) ---
trades["gross_pips"] = (trades["entry"] - trades["exit"]) / PIP
# signed-PnL test
chk = pd.DataFrame({"entry": [150.00, 150.00], "exit": [149.50, 150.50]})
chk_gross = (chk["entry"] - chk["exit"]) / PIP
assert chk_gross.tolist() == [50.0, -50.0]
print("[TEST] short PnL sign OK (down-move = +, up-move = -)")

trades["net_normal"] = trades["gross_pips"] - COST_NORMAL
trades["net_stress"] = trades["gross_pips"] - COST_STRESS
trades["year"] = pd.Index([d.year for d in trades.index])
# cost test
c = pd.Series([100.0])
assert (c - COST_NORMAL).iloc[0] == 98.0 and (c - COST_STRESS).iloc[0] == 96.0
print("[TEST] costs 2/4 pips OK")

# --- remove-best-1% test (synthetic) ---
syn = pd.Series([1.0] * 99 + [1000.0])
k = max(1, int(np.ceil(0.01 * len(syn))))
assert syn.sort_values(ascending=False).iloc[k:].mean() == 1.0
print("[TEST] remove-best-1% logic OK")

n = len(trades)
gross_mean = trades["gross_pips"].mean()
net_mean = trades["net_normal"].mean()
stress_mean = trades["net_stress"].mean()
median_net = trades["net_normal"].median()
win_rate = (trades["net_normal"] > 0).mean() * 100

by_year = trades.groupby("year")["net_normal"].mean()
positive_years = int((by_year > 0).sum())

k = max(1, int(np.ceil(0.01 * n)))
trimmed = trades["net_normal"].sort_values(ascending=False).iloc[k:]
remove_best = trimmed.mean()

rng = np.random.default_rng(SEED)
arr = trades["net_normal"].to_numpy()
boot = np.array([arr[rng.integers(0, n, n)].mean() for _ in range(N_BOOT)])
ci_lo, ci_hi = np.percentile(boot, [2.5, 97.5])

print("\n=== P041 TOKYO FIXING POST-FIX REVERSAL — DISCOVERY ===")
print(f"N_TRADES={n}")
print(f"GROSS_MEAN_PIPS={gross_mean:.3f}")
print(f"NET_NORMAL_MEAN_PIPS={net_mean:.3f}")
print(f"NET_STRESS_MEAN_PIPS={stress_mean:.3f}")
print(f"MEDIAN_NET_NORMAL={median_net:.3f}")
print(f"WIN_RATE_NET_NORMAL={win_rate:.2f}%")
print("BY_YEAR_NET_NORMAL:")
for y, v in by_year.items():
    print(f"  {y}: {v:.3f}")
print(f"POSITIVE_YEARS={positive_years}/{len(by_year)}")
print(f"REMOVE_BEST_1_PERCENT_NET={remove_best:.3f}")
print(f"CI95_NET_NORMAL=[{ci_lo:.3f}, {ci_hi:.3f}]")

c1 = net_mean >= 2.0
c2 = positive_years >= 6
c3 = remove_best > 0
c4 = stress_mean > 0
verdict = "PASS" if (c1 and c2 and c3 and c4) else "REJECT"
print(f"\nGATE: net>=2.0={c1} | pos_years>=6={c2} | remove_best>0={c3} | stress>0={c4}")
print(f"CLASSIFICATION=TOKYO_FIX_DISCOVERY_{verdict}")
if verdict == "REJECT":
    print("REJECT -> STOP IMMEDIATE. No variants.")
