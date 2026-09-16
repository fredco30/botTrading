#!/usr/bin/env python3
"""Estimate the EXACT MBP-1 cost for the ambiguity set ONLY (no download).

Ambiguity classes eligible for escalation (material, not cosmetic):
  TRIM_QUEUE_UNCERTAIN  - MBP-1 could prove/disprove the passive trim fill
  ENTRY_NEVER_MARKETABLE- entry never triggered within the window
  NO_QUOTE_60S_*        - missing/late quotes around a decision
Windows: +/-5 minutes around the relevant frozen decision timestamp.
"""
import json
import os
import sys
from pathlib import Path

import pandas as pd
import databento

HERE = Path(__file__).parent
DATASET = "GLBX.MDP3"


def load_key():
    cfg = Path.home() / ".databento" / "config"
    if cfg.exists():
        for line in cfg.read_text().splitlines():
            line = line.strip()
            if line.startswith("key"):
                return line.split("=", 1)[1].strip().strip('"')
    return os.environ.get("DATABENTO_API_KEY")


def main() -> int:
    rep = pd.read_csv(HERE / "results" / "bbo_replay_trades.csv")
    amb = rep[rep["FLAG"].astype(str).str.startswith(("AMBIGUOUS", "ERROR"))]
    trades = pd.read_csv(HERE / "FROZEN_TRADE_LIST.csv")
    m = trades.merge(amb[["TRADE_ID", "AMBIGUITY"]], on="TRADE_ID", how="inner")
    m["AMB"] = m["AMBIGUITY"].fillna("")
    m.to_csv(HERE / "MBP1_AMBIGUITY_LIST.csv", index=False)
    key = load_key()
    client = databento.Historical(key=key)
    total = 0.0
    per = {}
    for _, r in m.iterrows():
        day = str(pd.Timestamp(r["ORDER_ACTIVATION_TIMESTAMP"]).date())
        start = (pd.Timestamp(r["ORDER_ACTIVATION_TIMESTAMP"])
                 - pd.Timedelta(5, "min")).floor("10min")
        end = (pd.Timestamp(r["MODELED_FINAL_EXIT_TIMESTAMP"])
               + pd.Timedelta(5, "min")).ceil("10min")
        key_id = f"{day}_{r['ACTUAL_FUTURES_CONTRACT']}"
        if key_id in per:
            continue
        try:
            c = client.metadata.get_cost(
                dataset=DATASET, symbols=[r["ACTUAL_FUTURES_CONTRACT"]],
                schema="mbp-1", start=start.strftime("%Y-%m-%dT%H:%M:%S"),
                end=end.strftime("%Y-%m-%dT%H:%M:%S"), stype_in="raw_symbol")
            per[key_id] = float(c)
            total += float(c)
        except Exception as e:  # noqa: BLE001
            per[key_id] = f"ERROR:{type(e).__name__}"
    json.dump({"AMBIGUOUS_TRADES": int(len(m)),
               "AMBIGUOUS_FRACTION": round(len(m) / max(len(rep), 1), 4),
               "windows": len(per),
               "MBP1_EXACT_ESTIMATE_USD_RAW": total,
               "per_window": per},
              open(HERE / "results" / "mbp1_ambiguity_cost.json", "w"), indent=1)
    print(f"AMBIGUOUS_TRADES={len(m)} windows={len(per)} "
          f"MBP1_EXACT_ESTIMATE_USD={total:.4f}")
    print("NO DOWNLOAD EXECUTED — MBP-1 requires separate authorization.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
