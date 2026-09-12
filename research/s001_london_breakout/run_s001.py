"""Run the frozen S001 discovery backtest (2010-2019 window only).

Usage: python run_s001.py
Writes s001_results.json and prints a summary.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pandas as pd

import s001_lib as S

HERE = os.path.dirname(os.path.abspath(__file__))
PARQUET = os.path.join(HERE, "..", "..", "data_raw", "parquet", "GBPUSD_5m.parquet")


def main():
    bars = S.load_discovery_bars(PARQUET)
    assert bars.index.max() < pd.Timestamp("2019-01-01", tz="UTC"), "2019+ leak"
    trades, meta = S.run_backtest(bars)
    m = S.compute_metrics(trades, meta)

    out = {
        "strategy": "S001_GBPUSD_LONDON_ASIAN_RANGE_BREAKOUT",
        "window": "2010-01-01 -> 2019-01-01 EXCLUSIVE (discovery)",
        **m,
    }
    with open(os.path.join(HERE, "s001_results.json"), "w") as f:
        json.dump(out, f, indent=2, default=str)

    print(f"bars: {meta['first_bar']} -> {meta['last_bar']}  n={meta['n_bars']}")
    print(f"days_with_range={meta['n_days_with_range']}  "
          f"time_fallback={meta['n_time_fallback']}")
    for k in ["n_trades", "trades_per_year", "gross_mean_pips",
              "net_normal_mean_pips", "net_stress_mean_pips", "median_net_pips",
              "win_rate", "avg_win_pips", "avg_loss_pips", "profit_factor_normal",
              "expectancy_r_normal", "total_net_pips", "max_drawdown_pips",
              "max_consecutive_losses", "positive_years",
              "remove_best_1_percent_net_mean", "ci95_mean_net_normal",
              "reason_counts", "direction_counts", "classification"]:
        print(f"{k} = {m.get(k)}")
    print("criteria =", m.get("criteria"))
    print("by_year:")
    for r in m.get("by_year", []):
        print(f"  {r['year']}: n={r['n']} net={r['net_pips']} "
              f"mean={r['mean_net']} pf={r['profit_factor']}")


if __name__ == "__main__":
    main()
