#!/usr/bin/env python3
"""BBO-1s cost estimation for H02 / O01 / union windows. NO PURCHASE.

metadata.get_cost returns USD directly — recorded raw, never divided.
Resumable via COST_MANIFEST_H02_O01.json.
"""
import json
import os
import sys
from pathlib import Path

import pandas as pd
import databento

HERE = Path(__file__).parent
OUT = HERE / "COST_MANIFEST_H02_O01.json"
DATASET = "GLBX.MDP3"


def load_key():
    cfg = Path.home() / ".databento" / "config"
    if cfg.exists():
        for line in cfg.read_text().splitlines():
            line = line.strip()
            if line.startswith("key"):
                return line.split("=", 1)[1].strip().strip('"')
    return os.environ.get("DATABENTO_API_KEY")


def estimate(client, wins_csv, store_key, man):
    w = pd.read_csv(wins_csv)
    store = man.setdefault(store_key, {"per_window_cost_usd": {}})
    costs = store["per_window_cost_usd"]
    for k, r in w.iterrows():
        key_id = f"{r['DATE']}_{r['CONTRACT']}_{k}"
        if key_id in costs:
            continue
        try:
            c = client.metadata.get_cost(
                dataset=DATASET, symbols=[r["CONTRACT"]], schema="bbo-1s",
                start=pd.Timestamp(r["START"]).strftime("%Y-%m-%dT%H:%M:%S"),
                end=pd.Timestamp(r["END"]).strftime("%Y-%m-%dT%H:%M:%S"),
                stype_in="raw_symbol")
            costs[key_id] = float(c)
        except Exception as e:  # noqa: BLE001
            costs[key_id] = f"ERROR:{type(e).__name__}:{e}"
        if k % 50 == 0:
            vals = [v for v in costs.values() if isinstance(v, float)]
            print(f"{store_key} {k}/{len(w)} sum=${sum(vals):.2f}", flush=True)
            OUT.write_text(json.dumps(man, indent=1))
    store["per_window_cost_usd"] = costs
    vals = [v for v in costs.values() if isinstance(v, float)]
    store["n_windows"] = len(costs)
    store["n_errors"] = len([v for v in costs.values() if not isinstance(v, float)])
    store["ESTIMATED_COST_USD_RAW_SUM"] = float(sum(vals))
    OUT.write_text(json.dumps(man, indent=1))
    print(f"{store_key} DONE n={len(costs)} EST_USD={sum(vals):.4f}", flush=True)


def main() -> int:
    key = load_key()
    client = databento.Historical(key=key)
    man = json.loads(OUT.read_text()) if OUT.exists() else {}
    estimate(client, HERE / "H02_union_windows.csv", "H02_BBO1S", man)
    estimate(client, HERE / "O01_union_windows.csv", "O01_BBO1S", man)
    estimate(client, HERE / "combined_execution_windows.csv", "COMBINED_BBO1S", man)
    print("COST_ESTIMATION_COMPLETE", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
