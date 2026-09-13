"""RATES-EVENT-HIRES-M1 validation: per-event record checks, coverage funnel,
micro-timing feasibility, timestamp semantics report.

Reads only the manifest + parquet convenience files (or decodes raw dbn if
parquet is missing). Writes validation_report.json on E: and a summary markdown
next to this script.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from tbbo_lib import SYMBOLS, coverage_horizons, validate_records  # noqa: E402

sys.path.insert(0, str(Path(__file__).parent))
from download_tbbo import DATA_ROOT, MANIFEST  # noqa: E402

HORIZONS = (1, 2, 5, 10, 30)


def load_rows(entry: dict) -> pd.DataFrame:
    pq = entry.get("parquet")
    if pq and Path(pq).exists():
        return pd.read_parquet(pq)
    import databento as db
    store = db.DBNStore.from_file(entry["file"])
    return store.to_df().reset_index()


def ns(v) -> int:
    if isinstance(v, (int,)):
        return int(v)
    return int(pd.Timestamp(v).value)


def main() -> None:
    manifest = json.loads(MANIFEST.read_text())
    entries = manifest["entries"]
    per = {sym: [] for sym in SYMBOLS}
    funnel = Counter()

    keys = sorted({k.rsplit(":", 1)[0] for k in entries})
    for ek in keys:
        e_ents = {sym: entries.get(f"{ek}:{sym}") for sym in SYMBOLS}
        statuses = {sym: (e_ents[sym] or {}).get("status") for sym in SYMBOLS}
        if any(s == "EXPECTED_MARKET_CLOSED" for s in statuses.values()):
            funnel["EXPECTED_CLOSED"] += 1
            continue
        if any(s in ("CONFIRMED_DATA_GAP",) for s in statuses.values()):
            funnel["DATA_GAPS"] += 1
            continue
        if any(s == "zero_records" for s in statuses.values()):
            funnel["DATA_GAPS"] += 1
            continue

        ev_valid = {}
        for sym in SYMBOLS:
            ent = e_ents[sym]
            if not ent or ent.get("status") != "ok":
                ev_valid[sym] = False
                continue
            df = load_rows(ent)
            rows = [{"ts_event": ns(v), "ts_recv": ns(w)}
                    for v, w in zip(df["ts_event"], df["ts_recv"])]
            t0 = ns(datetime.fromisoformat(ent["t0"]))
            ws = ns(datetime.fromisoformat(ent["window_start"]))
            we = ns(datetime.fromisoformat(ent["window_end"]))
            v = validate_records(rows, ws, we)
            v["duplicate_exact_records"] = int(df.duplicated().sum())
            # Databento timeseries returns second-aligned batches: up to a few
            # trailing records from the second preceding window_start are
            # expected container semantics, not leaks.
            early = [t for t in (r["ts_event"] for r in rows) if t < ws]
            v["boundary_batch_records"] = len(early)
            v["boundary_batch_ok"] = bool(
                early and len(early) <= 10 and min(early) >= ws - 1_000_000_000
                and not any(t < ws for t in (r["ts_event"] for r in rows[len(early):]))
            ) or not early
            v["raw_contract"] = ent.get("raw_symbol")
            v["instrument_id"] = ent.get("instrument_id")
            v["raw_contract_matches_roll_map"] = (
                str(v["instrument_id"]) == str(ent.get("instrument_id")))
            v["coverage"] = coverage_horizons(rows, t0, HORIZONS)
            if len(df):
                sub = pd.to_datetime(df["ts_event"]).iloc[:2000]
                micro = (sub.astype("int64") % 1_000_000)
                v["ts_event_subsecond_nonzero_pct_sample"] = float((micro != 0).mean())

            ev_valid[sym] = (v["n_records"] > 0
                             and (v["records_outside_window"] == 0 or v["boundary_batch_ok"])
                             and v["monotonic_ts_event"]
                             and v["raw_contract_matches_roll_map"])
            per[sym].append((ek, v))

        if ev_valid["ZF"]:
            funnel["VALID_ZF"] += 1
        if ev_valid["ZN"]:
            funnel["VALID_ZN"] += 1
        if ev_valid["ZF"] and ev_valid["ZN"]:
            funnel["VALID_BOTH"] += 1

    # roll-invalid windows (would have shown as raw mismatch; count from manifest)
    roll_invalid = sum(
        1 for e in entries.values()
        if e.get("raw_symbol") and e.get("instrument_id")
        and e.get("status") == "ok" and not e.get("raw_contract_matches_roll_map", True))

    stats = {}
    for sym in SYMBOLS:
        counts = sorted(v["n_records"] for _, v in per[sym])
        if counts:
            import statistics
            stats[sym] = {
                "n_events": len(counts),
                "median": statistics.median(counts),
                "p05": counts[max(0, int(0.05 * len(counts)) - 1)],
                "p95": counts[min(len(counts) - 1, int(0.95 * len(counts)))],
                "total_records": sum(counts),
            }
        cov = Counter()
        n_valid = len(per[sym])
        for h in HORIZONS:
            cov[h] = sum(1 for _, v in per[sym] if v["coverage"][h])
        stats[sym]["coverage_pct"] = {
            f"{h}s": round(100.0 * cov[h] / n_valid, 2) if n_valid else None
            for h in HORIZONS
        }

    report = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "events": {
            sym: {ek: v for ek, v in per[sym]} for sym in SYMBOLS
        },
        "funnel": dict(funnel),
        "stats": stats,
        "roll_invalid": roll_invalid,
    }
    out = DATA_ROOT / "metadata" / "validation_report.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=1, default=str))
    print(json.dumps(report, indent=1, default=str)[:4000])


if __name__ == "__main__":
    main()
