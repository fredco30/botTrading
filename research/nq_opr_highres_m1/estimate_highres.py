#!/usr/bin/env python3
"""HIGH-RES COST GUARD (mission sections 4-11). ESTIMATION ONLY — NO PURCHASE.

Probes schema availability (bbo-1s / mbp-1 / tbbo / trades) per calendar year,
then estimates the exact Databento cost of the merged execution windows for
bbo-1s and mbp-1 using the ACTUAL raw contract symbol of each trade.
All cost values are RAW API returns in US DOLLARS — never divided by anything.
Writes COST_MANIFEST.json progressively (resumable). Never exposes the key.
"""
import json
import os
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import databento

HERE = Path(__file__).parent
DATASET = "GLBX.MDP3"
YEARS = [2020, 2021, 2022, 2023, 2024, 2025]
SCHEMAS = ["bbo-1s", "mbp-1", "tbbo", "trades"]
OUT = HERE / "COST_MANIFEST.json"


def load_key():
    cfg = Path.home() / ".databento" / "config"
    if cfg.exists():
        for line in cfg.read_text().splitlines():
            line = line.strip()
            if line.startswith("key"):
                return line.split("=", 1)[1].strip().strip('"')
    return os.environ.get("DATABENTO_API_KEY")


def load_manifest() -> dict:
    if OUT.exists():
        return json.loads(OUT.read_text())
    return {"schema_availability": {}, "bbo1s_windows": {}, "mbp1_windows": {},
            "mbp1_pilot": {}, "raw_cost_values_note": "get_cost returns USD directly; recorded raw"}


def main() -> int:
    key = load_key()
    if not key:
        print("NO_API_KEY")
        return 2
    client = databento.Historical(key=key)
    man = load_manifest()

    # ---- 1) schema availability per year (record counts; 0 = no coverage) ----
    avail = man["schema_availability"]
    if not avail:
        for schema in SCHEMAS:
            avail[schema] = {}
            for year in YEARS:
                try:
                    n = client.metadata.get_record_count(
                        dataset=DATASET, symbols=["NQ.v.0"], schema=schema,
                        start=f"{year}-01-01T00:00:00", end=f"{year + 1}-01-01T00:00:00",
                        stype_in="continuous")
                except Exception as e:  # noqa: BLE001
                    n = f"ERROR:{type(e).__name__}"
                avail[schema][str(year)] = n
                print(f"avail {schema} {year}: {n}", flush=True)
        man["schema_availability"] = avail
        OUT.write_text(json.dumps(man, indent=1))

    # ---- 2) merged execution windows (per date+contract, rounded outward) ----
    wins = pd.read_csv(HERE / "execution_windows_raw.csv")
    wins["START"] = pd.to_datetime(wins["START_UTC"], utc=True).dt.floor("10min")
    wins["END"] = pd.to_datetime(wins["END_UTC"], utc=True).dt.ceil("10min")
    merged = wins.groupby(["DATE", "CONTRACT"], as_index=False).agg(
        START=("START", "min"), END=("END", "max"))
    merged = merged.sort_values("DATE").reset_index(drop=True)
    total_hours = float((merged["END"] - merged["START"]).dt.total_seconds().sum() / 3600)
    man["BBO1S_WINDOWS"] = {"n_windows": int(len(merged)),
                            "total_hours_rounded": round(total_hours, 2)}
    print(f"merged windows: {len(merged)}  total_hours={total_hours:.2f}", flush=True)

    # ---- 3) per-window cost estimates ----
    for schema, store_key in (("bbo-1s", "bbo1s_windows"), ("mbp-1", "mbp1_windows")):
        store = man.setdefault(store_key, {})
        costs = store.get("per_window_cost_usd", {})
        for k, r in merged.iterrows():
            key_id = f"{r['DATE']}_{r['CONTRACT']}"
            if key_id in costs:
                continue
            try:
                c = client.metadata.get_cost(
                    dataset=DATASET, symbols=[r["CONTRACT"]], schema=schema,
                    start=r["START"].strftime("%Y-%m-%dT%H:%M:%S"),
                    end=r["END"].strftime("%Y-%m-%dT%H:%M:%S"),
                    stype_in="raw_symbol")
                costs[key_id] = float(c)
            except Exception as e:  # noqa: BLE001
                costs[key_id] = f"ERROR:{type(e).__name__}:{e}"
            if k % 50 == 0:
                done_vals = [v for v in costs.values() if isinstance(v, float)]
                print(f"{schema} {k}/{len(merged)} sum_so_far=${sum(done_vals):.2f}", flush=True)
                store["per_window_cost_usd"] = costs
                OUT.write_text(json.dumps(man, indent=1))
        store["per_window_cost_usd"] = costs
        vals = [v for v in costs.values() if isinstance(v, float)]
        errs = [v for v in costs.values() if not isinstance(v, float)]
        man[store_key]["n_windows"] = len(costs)
        man[store_key]["n_errors"] = len(errs)
        man[store_key]["ESTIMATED_COST_USD_RAW_SUM"] = float(sum(vals))
        OUT.write_text(json.dumps(man, indent=1))
        print(f"{schema} DONE windows={len(costs)} errors={len(errs)} "
              f"ESTIMATED_COST_USD={sum(vals):.2f}", flush=True)

    # ---- 4) MBP-1 pilot: 100 deterministic 10-minute windows ----
    trades = pd.read_csv(HERE / "FROZEN_TRADE_LIST.csv", usecols=[
        "TRADE_ID", "BREAKOUT_TIMESTAMP", "SIDE"])
    trades["ts"] = pd.to_datetime(trades["BREAKOUT_TIMESTAMP"], utc=True)
    trades = trades.sort_values("TRADE_ID").reset_index(drop=True)
    idx = np.linspace(0, len(trades) - 1, 100).astype(int)
    pilot = trades.iloc[idx]
    store = man.setdefault("mbp1_pilot", {})
    pcosts = store.get("per_window_cost_usd", {})
    contract_map = wins.drop_duplicates("DATE").set_index("DATE")["CONTRACT"]
    for k, (_, r) in enumerate(pilot.iterrows()):
        day = str(pd.Timestamp(r["ts"]).date())
        contract = contract_map.get(day, None)
        if contract is None:
            continue
        key_id = f"{day}_{contract}"
        if key_id in pcosts:
            continue
        start = (r["ts"] - pd.Timedelta(5, "min")).floor("10min")
        end = (r["ts"] + pd.Timedelta(5, "min")).ceil("10min")
        try:
            c = client.metadata.get_cost(
                dataset=DATASET, symbols=[contract], schema="mbp-1",
                start=start.strftime("%Y-%m-%dT%H:%M:%S"),
                end=end.strftime("%Y-%m-%dT%H:%M:%S"), stype_in="raw_symbol")
            pcosts[key_id] = float(c)
        except Exception as e:  # noqa: BLE001
            pcosts[key_id] = f"ERROR:{type(e).__name__}:{e}"
        if k % 25 == 0:
            print(f"pilot {k}/100", flush=True)
            store["per_window_cost_usd"] = pcosts
            OUT.write_text(json.dumps(man, indent=1))
    store["per_window_cost_usd"] = pcosts
    vals = [v for v in pcosts.values() if isinstance(v, float)]
    man["mbp1_pilot"]["n_windows"] = len(pcosts)
    man["mbp1_pilot"]["ESTIMATED_COST_USD_RAW_SUM"] = float(sum(vals))
    OUT.write_text(json.dumps(man, indent=1))
    print(f"PILOT DONE n={len(pcosts)} ESTIMATED_COST_USD={sum(vals):.2f}", flush=True)
    print("COST_ESTIMATION_COMPLETE", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
