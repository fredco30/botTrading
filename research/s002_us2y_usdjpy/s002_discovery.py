"""S002 discovery: US 2Y rate shock -> USDJPY directional trade (J+5, gross + costs).

Frozen spec: research/s002_us2y_usdjpy/S002_FROZEN_SPEC.md
Discovery window: [2010-01-01, 2019-01-01). No 2019+, no protected OOS.
"""
import numpy as np
import pandas as pd

DATA_DGS2 = "data_raw/official/DGS2.csv"
DATA_FX = "USDJPY15.csv"
OUT_DIR = "research/s002_us2y_usdjpy"

DISC_START = pd.Timestamp("2010-01-01")
DISC_END = pd.Timestamp("2019-01-01")  # exclusive
THRESHOLD_BP = 3.0
PIP = 0.01
COST_NORMAL = 2.0
COST_STRESS = 4.0
HOLD_FX_DAYS = 5
BOOTSTRAP_N = 2000
BOOTSTRAP_SEED = 42

# ---------- data ----------
dgs2 = pd.read_csv(DATA_DGS2, parse_dates=["observation_date"]).sort_values("observation_date")
dgs2 = dgs2.dropna(subset=["DGS2"]).reset_index(drop=True)
dgs2["rate_change_bp"] = dgs2["DGS2"].diff() * 100.0
dgs2["prev_date"] = dgs2["observation_date"].shift(1)

fx = pd.read_csv(DATA_FX, names=["date", "time", "o", "h", "l", "c", "v"],
                 dtype={"date": str, "time": str})
fx["dt"] = pd.to_datetime(fx["date"], format="%Y.%m.%d")
# daily open = open of first bar of each FX day
daily_open = fx.groupby("dt")["o"].first().sort_index()
fx_days = daily_open.index  # only days with data

fx_day_arr = fx_days.values

def first_fx_day_after(ts):
    """First FX day strictly after ts."""
    i = np.searchsorted(fx_day_arr, np.datetime64(ts, "ns"), side="right")
    return i if i < len(fx_day_arr) else None

# ---------- signals ----------
signals = []  # (rate_change_date, direction)
for k in range(1, len(dgs2)):
    d = dgs2.loc[k, "observation_date"]
    if not (DISC_START <= d < DISC_END):
        continue
    ch = dgs2.loc[k, "rate_change_bp"]
    if ch >= THRESHOLD_BP:
        signals.append((d, +1))
    elif ch <= -THRESHOLD_BP:
        signals.append((d, -1))

# ---------- execution: one position at a time, signal during position ignored ----------
trades = []
pos_open_until_idx = -1  # index into fx_days of exit day of current position
for d, direction in signals:
    ei = first_fx_day_after(d)
    if ei is None or ei >= len(fx_days):
        continue
    entry_day = fx_days[ei]
    if not (DISC_START <= entry_day < DISC_END):
        continue  # discovery boundary
    if ei <= pos_open_until_idx:
        continue  # position already open -> ignore
    xi = ei + HOLD_FX_DAYS
    if xi >= len(fx_days):
        continue
    exit_day = fx_days[xi]
    if exit_day >= DISC_END:
        # exit crosses boundary; keep trade but exit uses data <2019 only if possible
        continue
    entry = daily_open.iloc[ei]
    exit_ = daily_open.iloc[xi]
    gross_pips = (exit_ - entry) / PIP * direction
    trades.append({
        "signal_date": d, "entry_day": entry_day, "exit_day": exit_day,
        "direction": direction, "gross_pips": gross_pips,
        "net_normal_pips": gross_pips - COST_NORMAL,
        "net_stress_pips": gross_pips - COST_STRESS,
    })
    pos_open_until_idx = xi

t = pd.DataFrame(trades)
net = t["net_normal_pips"].values

# ---------- metrics ----------
years = t["entry_day"].dt.year
n_years_span = 9  # 2010..2018
n_trades = len(t)
trades_per_year = n_trades / n_years_span
gross_mean = t["gross_pips"].mean()
net_normal_mean = net.mean()
net_stress_mean = t["net_stress_pips"].mean()
median_net = np.median(net)
win_rate = (net > 0).mean()
wins = net[net > 0]
losses = net[net <= 0]
avg_win = wins.mean() if len(wins) else 0.0
avg_loss = losses.mean() if len(losses) else 0.0
gross_wins = net[net > 0].sum()
gross_losses = -net[net <= 0].sum()
profit_factor = gross_wins / gross_losses if gross_losses > 0 else float("inf")
total_net = net.sum()
equity = np.cumsum(net)
max_dd = (np.maximum.accumulate(np.concatenate([[0], equity])) - np.concatenate([[0], equity])).max()
# max consecutive losses
max_consec = cur = 0
for v in net:
    cur = cur + 1 if v <= 0 else 0
    max_consec = max(max_consec, cur)

by_year = []
for y in range(2010, 2019):
    s = t[years == y]["net_normal_pips"]
    w = s[s > 0].sum()
    l = -s[s <= 0].sum()
    by_year.append({
        "year": y, "n": len(s), "net_pips": s.sum(), "mean_net": s.mean() if len(s) else float("nan"),
        "pf": (w / l) if l > 0 else float("inf"),
    })
by_year_df = pd.DataFrame(by_year)
positive_years = int((by_year_df["net_pips"] > 0).sum())

sorted_net = np.sort(net)
k = max(1, int(np.ceil(0.01 * n_trades)))
remove_best_mean = sorted_net[:-k].mean() if n_trades > k else float("nan")

rng = np.random.default_rng(BOOTSTRAP_SEED)
boots = np.array([rng.choice(net, size=n_trades, replace=True).mean() for _ in range(BOOTSTRAP_N)])
ci_lo, ci_hi = np.percentile(boots, [2.5, 97.5])

# ---------- verdict ----------
promising = (net_normal_mean >= 5.0 and profit_factor >= 1.20 and positive_years >= 6
             and remove_best_mean > 0 and total_net > 0)
fail_fast = (net_normal_mean <= 0 or profit_factor <= 1.0 or remove_best_mean <= 0)
classification = "S002_DISCOVERY_PROMISING" if promising else ("REJECT_FAIL_FAST" if fail_fast else "NOT_PROMISING")

report = f"""S002_US2Y_USDJPY_DISCOVERY

N_TRADES={n_trades}
TRADES_PER_YEAR={trades_per_year:.2f}

GROSS_MEAN={gross_mean:.3f}
NET_NORMAL_MEAN={net_normal_mean:.3f}
NET_STRESS_MEAN={net_stress_mean:.3f}

MEDIAN_NET={median_net:.3f}
WIN_RATE={win_rate:.4f}
AVG_WIN={avg_win:.3f}
AVG_LOSS={avg_loss:.3f}

PROFIT_FACTOR_NORMAL={profit_factor:.3f}

TOTAL_NET_PIPS={total_net:.2f}
MAX_DRAWDOWN_PIPS={max_dd:.2f}
MAX_CONSECUTIVE_LOSSES={max_consec}

POSITIVE_YEARS={positive_years}/9
BY_YEAR:
{by_year_df.to_string(index=False)}

REMOVE_BEST_1_PERCENT_NET_MEAN={remove_best_mean:.3f}
CI95_MEAN_NET_NORMAL=[{ci_lo:.3f}, {ci_hi:.3f}]

CLASSIFICATION={classification}
"""
print(report)
with open(f"{OUT_DIR}/s002_discovery_report.txt", "w") as f:
    f.write(report + "\n")
t.to_csv(f"{OUT_DIR}/s002_trades.csv", index=False)
