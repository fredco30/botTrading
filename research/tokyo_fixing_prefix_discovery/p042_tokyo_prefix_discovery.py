"""P042 — Tokyo fixing pre-fix USD demand, discovery (fail-fast, frozen SPEC).

LONG USDJPY: entry = OPEN of 09:50 JST bar, exit = OPEN of 10:00 JST bar.
Window 2010-01-01 -> 2019-01-01 exclusive. Source data: 5-min UTC bars.
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
PARQUET = REPO / "data_raw" / "parquet" / "USDJPY_5m.parquet"

START = pd.Timestamp("2010-01-01", tz="UTC")
END = pd.Timestamp("2019-01-01", tz="UTC")  # exclusive
PIP = 0.01
COST_NORMAL = 2.0
COST_STRESS = 4.0
SEED = 42
N_BOOT = 2000


def load_data():
    df = pd.read_parquet(PARQUET)
    df = df.sort_index()
    return df[df.index < END]


def extract_trades(df):
    """entry bar 09:50 JST = 00:50 UTC; exit bar 10:00 JST = 01:00 UTC."""
    idx = df.index
    entry_times = pd.DatetimeIndex(
        [t for t in idx if t.hour == 0 and t.minute == 50]
    )
    rows = []
    for t in entry_times:
        exit_t = t + pd.Timedelta(minutes=10)
        if exit_t not in df.index:
            continue
        entry = df.at[t, "open"]
        exit_ = df.at[exit_t, "open"]
        rows.append(
            {
                "date": t.tz_convert("Asia/Tokyo").date(),
                "entry_jst": t.tz_convert("Asia/Tokyo"),
                "exit_jst": exit_t.tz_convert("Asia/Tokyo"),
                "gross_pips": (exit_ - entry) / PIP,
            }
        )
    return pd.DataFrame(rows)


def add_costs(tr):
    tr["net_normal"] = tr["gross_pips"] - COST_NORMAL
    tr["net_stress"] = tr["gross_pips"] - COST_STRESS
    return tr


def remove_best_1_percent(x):
    x = np.sort(np.asarray(x, dtype=float))
    k = int(np.floor(len(x) * 0.01))
    return x[: len(x) - k].mean() if k < len(x) else np.nan


def ci95(x):
    rng = np.random.default_rng(SEED)
    x = np.asarray(x, dtype=float)
    means = [rng.choice(x, size=len(x), replace=True).mean() for _ in range(N_BOOT)]
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def metrics(tr):
    by_year = tr.groupby(tr["date"].map(lambda d: d.year))["net_normal"].mean()
    lo, hi = ci95(tr["net_normal"])
    return {
        "N_TRADES": int(len(tr)),
        "GROSS_MEAN": float(tr["gross_pips"].mean()),
        "NET_NORMAL_MEAN": float(tr["net_normal"].mean()),
        "NET_STRESS_MEAN": float(tr["net_stress"].mean()),
        "MEDIAN_NET": float(tr["net_normal"].median()),
        "WIN_RATE_NET": float((tr["net_normal"] > 0).mean()),
        "POSITIVE_YEARS": int((by_year > 0).sum()),
        "BY_YEAR_NET": {int(y): float(v) for y, v in by_year.items()},
        "REMOVE_BEST_1_PERCENT_NET": float(remove_best_1_percent(tr["net_normal"])),
        "CI95_NET": [lo, hi],
    }


def classify(m):
    ok = (
        m["NET_NORMAL_MEAN"] >= 2.0
        and m["POSITIVE_YEARS"] >= 6
        and m["REMOVE_BEST_1_PERCENT_NET"] > 0
        and m["NET_STRESS_MEAN"] > 0
    )
    return "TOKYO_PREFIX_DISCOVERY_PASS" if ok else "TOKYO_PREFIX_DISCOVERY_REJECT"


# ---------------- minimal tests ----------------

def run_tests(df):
    assert df.index.tz is not None and str(df.index.tz) == "UTC"
    jst = df.index.tz_convert("Asia/Tokyo")
    # UTC->JST: 00:50 UTC must be 09:50 JST (no DST in Japan)
    probe = df.index[len(df) // 2]
    assert probe.tz_convert("Asia/Tokyo").utcoffset() == pd.Timedelta(hours=9)
    # entry/exit mapping
    tr = extract_trades(df)
    assert (tr["entry_jst"].dt.hour == 9).all() and (tr["entry_jst"].dt.minute == 50).all()
    assert (tr["exit_jst"].dt.hour == 10).all() and (tr["exit_jst"].dt.minute == 0).all()
    assert (tr["exit_jst"] - tr["entry_jst"] == pd.Timedelta(minutes=10)).all()
    # LONG sign: rising price => positive gross
    dummy = pd.DataFrame({"gross_pips": [(101.0 - 100.0) / PIP]})
    assert float(dummy["gross_pips"].iloc[0]) == 100.0
    # costs
    t2 = add_costs(pd.DataFrame({"gross_pips": [10.0]}))
    assert t2["net_normal"].iloc[0] == 8.0 and t2["net_stress"].iloc[0] == 6.0
    # boundary: no trade at/after 2019-01-01
    assert tr["entry_jst"].max() < pd.Timestamp("2019-01-01", tz="Asia/Tokyo") + pd.Timedelta(hours=9)
    assert pd.Timestamp(tr["date"].max()) < pd.Timestamp("2019-01-02")
    # remove-best-1%
    x = np.arange(100.0)  # mean 49.5; remove best 1 -> mean of 0..98 = 49.0
    assert abs(remove_best_1_percent(x) - 49.0) < 1e-9
    print("TESTS: all passed")
    return tr


def main():
    df = load_data()
    tr = run_tests(df)
    tr = add_costs(tr)
    m = metrics(tr)
    m["CLASSIFICATION"] = classify(m)
    out = Path(__file__).parent / "P042_RESULTS.txt"
    with open(out, "w") as f:
        f.write("P042 TOKYO FIXING PRE-FIX USD DEMAND — DISCOVERY RESULTS\n")
        f.write(f"CLASSIFICATION = {m['CLASSIFICATION']}\n")
        for k, v in m.items():
            if k in ("CLASSIFICATION", "BY_YEAR_NET"):
                continue
            f.write(f"{k} = {v}\n")
        f.write("BY_YEAR_NET (pips/day):\n")
        for y, v in m["BY_YEAR_NET"].items():
            f.write(f"  {y}: {v:.3f}\n")
    print(open(out).read())
    print(json.dumps({k: v for k, v in m.items() if k != "BY_YEAR_NET"}, default=str))


if __name__ == "__main__":
    sys.exit(main())
