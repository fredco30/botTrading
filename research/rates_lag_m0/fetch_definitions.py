"""RATES-LAG-M0: resolve min_price_increment per raw ZF/ZN contract from Databento
instrument definitions (authoritative, not hard-coded).

Idempotent: results cached at E:\ResearchData\botTrading\rates\databento_event_tbbo\
metadata\instrument_definitions.json; a compact tick-size map (tiny, no bulk data)
is written into the repo as instrument_tick_sizes.json.

Usage: python fetch_definitions.py            # fetch missing + write JSONs
       python fetch_definitions.py --report   # print the tick-size map
"""
from __future__ import annotations

import configparser
import json
import sys
from datetime import date, timedelta
from pathlib import Path

import databento as db

MANIFEST = Path(r"E:\ResearchData\botTrading\rates\databento_event_tbbo\manifests\manifest.json")
DEF_CACHE = Path(r"E:\ResearchData\botTrading\rates\databento_event_tbbo\metadata\instrument_definitions.json")
TICK_SIZES_OUT = Path(__file__).resolve().parent / "instrument_tick_sizes.json"
COST_CAP_USD = 1.00  # safety cap; expected total is < 0.001 USD


def load_key() -> str:
    cfg = configparser.ConfigParser()
    cfg.read(Path.home() / ".databento" / "config")
    return cfg["databento"]["key"].strip().strip('"').strip("'")


def distinct_contracts() -> dict[str, str]:
    """raw_symbol -> earliest valid-event t0 (representative query day)."""
    m = json.loads(MANIFEST.read_text())
    earliest: dict[str, str] = {}
    for e in m["entries"].values():
        if e["status"] != "ok":
            continue
        raw = e["raw_symbol"]
        if raw not in earliest or e["t0"] < earliest[raw]:
            earliest[raw] = e["t0"]
    return dict(sorted(earliest.items()))


def day_window(iso_day: str) -> tuple[str, str]:
    d = date.fromisoformat(iso_day)
    return iso_day, (d + timedelta(days=1)).isoformat()


def main() -> int:
    contracts = distinct_contracts()
    cache = json.loads(DEF_CACHE.read_text()) if DEF_CACHE.exists() else {}
    todo = {k: v for k, v in contracts.items() if k not in cache}
    print(f"{len(cache)}/{len(contracts)} cached, {len(todo)} to fetch")

    if todo:
        client = db.Historical(key=load_key())
        est = 0.0
        for raw, d in sorted(todo.items()):
            s, e = day_window(d[:10])
            est += client.metadata.get_cost(
                dataset="GLBX.MDP3", start=s, end=e,
                symbols=[raw], stype_in="raw_symbol", schema="definition")
        print(f"estimated cost: {est:.6f} USD (cap {COST_CAP_USD})")
        if est > COST_CAP_USD:
            print("STOP_OVER_CAP")
            return 2
        for i, (raw, d) in enumerate(sorted(todo.items()), 1):
            s, e = day_window(d[:10])
            r = client.timeseries.get_range(
                dataset="GLBX.MDP3", start=s, end=e,
                symbols=[raw], stype_in="raw_symbol", schema="definition")
            df = r.to_df()
            if df.empty:
                print(f"  {raw}: EMPTY definition on {s}")
                continue
            row = df.iloc[-1]
            cache[raw] = {
                "instrument_id": str(int(row["instrument_id"])),
                "query_date": s,
                "min_price_increment": float(row["min_price_increment"]),
                "min_price_increment_amount": float(row["min_price_increment_amount"])
                    if "min_price_increment_amount" in df.columns else None,
                "unit_of_measure": str(row["unit_of_measure"])
                    if "unit_of_measure" in df.columns else None,
                "expiration": str(row["expiration"]) if "expiration" in df.columns else None,
            }
            print(f"  [{i}/{len(todo)}] {raw}: tick={cache[raw]['min_price_increment']}")
            DEF_CACHE.parent.mkdir(parents=True, exist_ok=True)
            DEF_CACHE.write_text(json.dumps(cache, indent=1, sort_keys=True))

    missing = [k for k in contracts if k not in cache]
    if missing:
        print(f"MISSING definitions: {missing}")
        return 3
    ticks = {raw: {"symbol": raw[:2], "min_price_increment": cache[raw]["min_price_increment"],
                   "instrument_id": cache[raw]["instrument_id"]}
             for raw in contracts}
    TICK_SIZES_OUT.write_text(json.dumps(ticks, indent=1, sort_keys=True))
    print(f"wrote {TICK_SIZES_OUT} ({len(ticks)} contracts)")
    per_sym = {s: sorted({v["min_price_increment"] for k, v in ticks.items() if k.startswith(s)})
               for s in ("ZF", "ZN")}
    print("unique tick sizes per symbol:", per_sym)
    return 0


if __name__ == "__main__":
    if "--report" in sys.argv:
        print(TICK_SIZES_OUT.read_text())
        raise SystemExit(0)
    raise SystemExit(main())
