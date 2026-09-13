"""RATES-EVENT-HIRES-M1 downloader: TBBO event windows for ZF/ZN from Databento GLBX.MDP3.

Restart-safe: every event/instrument is downloaded at most once. A validated raw
file recorded in the manifest is never re-downloaded. Bulk data stays on E:.

Usage:
    python download_tbbo.py --plan            # free pre-flight: cost check only
    python download_tbbo.py --download        # download (after cost gate passes)
"""
from __future__ import annotations

import argparse
import configparser
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import databento as db

sys.path.insert(0, str(Path(__file__).parent))
from tbbo_lib import (  # noqa: E402
    CONTINUOUS, DATASET, SCHEMA, SYMBOLS,
    Event, RollMap, classify_zero_window, is_expected_closed, load_events,
    sha256_file,
)

REPO = Path(__file__).resolve().parent.parent
EVENTS_CSV = REPO / "rates_macro_m1" / "data" / "macro_events_2010_2018_aligned.csv"
ROLL_MAP_CSV = REPO / "rates_data_m0" / "roll_map.csv" if (REPO / "rates_data_m0" / "roll_map.csv").exists() else None
DATA_ROOT = Path(r"E:\ResearchData\botTrading\rates\databento_event_tbbo")
M0_PARQUET = Path(r"E:\ResearchData\botTrading\rates\databento\parquet")
COST_CAP_USD = 15.00
MANIFEST = DATA_ROOT / "manifests" / "manifest.json"


def load_key() -> str:
    cfg = configparser.ConfigParser()
    cfg.read(Path.home() / ".databento" / "config")
    return cfg["databento"]["key"].strip().strip('"').strip("'")


def find_roll_map() -> Path:
    for cand in [REPO / "rates_data_m0" / "roll_map.csv",
                 Path(r"E:\ResearchData\botTrading\rates\databento\metadata\roll_map.csv")]:
        if cand.exists():
            return cand
    raise FileNotFoundError("roll_map.csv not found")


def ohlcv_bars_in_window(symbol: str, start: datetime, end: datetime) -> int:
    f = M0_PARQUET / f"{symbol}.parquet"
    if not f.exists():
        return -1
    import pandas as pd
    df = pd.read_parquet(f, columns=["symbol"])
    m = (df.index >= pd.Timestamp(start)) & (df.index < pd.Timestamp(end))
    return int(m.sum())


def load_manifest() -> dict:
    if MANIFEST.exists():
        return json.loads(MANIFEST.read_text())
    return {"mission": "RATES-EVENT-HIRES-M1", "dataset": DATASET, "schema": SCHEMA,
            "entries": {}}


def save_manifest(m: dict) -> None:
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(m, indent=1))


def key_for(event: Event, symbol: str) -> str:
    return f"{event.event_id}:{symbol}"


def build_client(key: str) -> db.Historical:
    return db.Historical(key=key)


def plan(client: db.Historical, events: list[Event], roll: RollMap, manifest: dict) -> float:
    """Free pre-flight: cost for every non-excluded event/instrument window."""
    jobs = []
    for ev in events:
        if is_expected_closed(ev):
            continue
        if ev.t0.date() == datetime(2014, 10, 3, tzinfo=timezone.utc).date():
            continue  # diagnosed full-day gap, excluded (see README)
        for sym in SYMBOLS:
            k = key_for(ev, sym)
            ent = manifest["entries"].get(k)
            if ent and ent.get("status") == "ok":
                continue  # idempotent: already validated
            jobs.append((ev, sym))

    def cost(job):
        ev, sym = job
        return client.metadata.get_cost(
            dataset=DATASET, start=ev.window_start, end=ev.window_end,
            symbols=[CONTINUOUS[sym]], stype_in="continuous", schema=SCHEMA)

    total = 0.0
    with ThreadPoolExecutor(max_workers=8) as ex:
        for (ev, sym), c in zip(jobs, ex.map(cost, jobs)):
            total += c
    return total


def download_all(client: db.Historical, events: list[Event], roll: RollMap,
                 manifest: dict) -> None:
    raw_dir = DATA_ROOT / "raw"
    pq_dir = DATA_ROOT / "parquet"
    todo = []
    for ev in events:
        k_date = ev.t0.date()
        expected = is_expected_closed(ev)
        for sym in SYMBOLS:
            k = key_for(ev, sym)
            ent = manifest["entries"].get(k)
            if ent and ent.get("status") == "ok" and ent.get("sha256"):
                continue
            raw_syms = roll.resolve(sym, ev.t0)
            base = {
                "event_id": ev.event_id, "family": ev.family, "t0": ev.t0.isoformat(),
                "symbol": sym, "continuous_symbol": CONTINUOUS[sym],
                "raw_symbol": raw_syms[0] if raw_syms else None,
                "instrument_id": raw_syms[1] if raw_syms else None,
                "window_start": ev.window_start.isoformat(),
                "window_end": ev.window_end.isoformat(),
            }
            if expected:
                base.update(status="EXPECTED_MARKET_CLOSED", record_count=0)
                manifest["entries"][k] = base
                continue
            if k_date == datetime(2014, 10, 3, tzinfo=timezone.utc).date():
                # Diagnosed: zero records for continuous AND raw contracts AND
                # ohlcv-1m for the entire day on Databento -> upstream gap.
                base.update(
                    status="CONFIRMED_DATA_GAP",
                    classification="CONFIRMED_DATA_GAP",
                    note=("2014-10-03 NFP: entire session absent from Databento "
                          "GLBX.MDP3 (tbbo and ohlcv-1m, continuous and raw "
                          "contracts ZFZ4=116721 / ZNZ4=354456). Excluded, no "
                          "fabrication."),
                    record_count=0)
                manifest["entries"][k] = base
                continue
            todo.append((ev, sym, base))
    save_manifest(manifest)

    import pandas as pd

    def fetch(job):
        ev, sym, base = job
        k = key_for(ev, sym)
        cost = client.metadata.get_cost(
            dataset=DATASET, start=ev.window_start, end=ev.window_end,
            symbols=[CONTINUOUS[sym]], stype_in="continuous", schema=SCHEMA)
        count = client.metadata.get_record_count(
            dataset=DATASET, start=ev.window_start, end=ev.window_end,
            symbols=[CONTINUOUS[sym]], stype_in="continuous", schema=SCHEMA)
        if count == 0:
            bars = ohlcv_bars_in_window(sym, ev.window_start, ev.window_end)
            raw_cnt = 0
            if base.get("raw_symbol"):
                raw_cnt = client.metadata.get_record_count(
                    dataset=DATASET, start=ev.window_start, end=ev.window_end,
                    symbols=[base["instrument_id"]], stype_in="instrument_id",
                    schema=SCHEMA)
            base.update(status="zero_records", cost_usd=0.0, record_count=0,
                        classification=classify_zero_window(bars, count, raw_cnt),
                        ohlcv_bars_in_window=bars)
            return k, base, 0
        raw_dir.mkdir(parents=True, exist_ok=True)
        out = raw_dir / f"{ev.event_id}_{sym}.dbn.zst"
        if not out.exists():  # idempotent: never re-download an existing raw file
            client.timeseries.get_range(
                dataset=DATASET, start=ev.window_start, end=ev.window_end,
                symbols=[CONTINUOUS[sym]], stype_in="continuous", schema=SCHEMA,
                path=out)
        store = db.DBNStore.from_file(out)
        df = store.to_df()
        df = df.reset_index()
        pq_dir.mkdir(parents=True, exist_ok=True)
        pq = pq_dir / f"{ev.event_id}_{sym}.parquet"
        df.to_parquet(pq)
        base.update(
            status="ok", cost_usd=cost, record_count=int(len(df)),
            file=str(out), parquet=str(pq), sha256=sha256_file(out),
            raw_contract=int(df["instrument_id"].iloc[0]) if len(df) else None,
            dbschema=str(store.schema) if hasattr(store, "schema") else SCHEMA,
        )
        return k, base, cost

    done = 0
    with ThreadPoolExecutor(max_workers=4) as ex:
        for k, base, cost in ex.map(fetch, todo):
            manifest["entries"][k] = base
            done += 1
            if done % 20 == 0:
                save_manifest(manifest)
                print(f"{done}/{len(todo)} done, running cost {sum(e.get('cost_usd') or 0 for e in manifest['entries'].values()):.4f} USD", flush=True)
    save_manifest(manifest)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", action="store_true")
    ap.add_argument("--download", action="store_true")
    args = ap.parse_args()

    events = load_events(str(EVENTS_CSV))
    roll = RollMap.from_csv(str(find_roll_map()))
    manifest = load_manifest()
    client = build_client(load_key())

    if args.plan:
        total = plan(client, events, roll, manifest)
        print(f"PREFLIGHT_ESTIMATED_COST_USD={total:.4f}")
        print("GATE:", "PASS" if total <= COST_CAP_USD else "STOP_OVER_CAP")
        return 0 if total <= COST_CAP_USD else 2

    if args.download:
        total = plan(client, events, roll, manifest)
        print(f"PREFLIGHT_ESTIMATED_COST_USD={total:.4f}")
        if total > COST_CAP_USD:
            print("STOP: estimated cost over cap — no download.")
            return 2
        download_all(client, events, roll, manifest)
        total_cost = sum(e.get("cost_usd") or 0 for e in manifest["entries"].values())
        print(f"ACTUAL_COST_USD(sum of per-window get_cost)={total_cost:.4f}")
        print("STATUS=done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
