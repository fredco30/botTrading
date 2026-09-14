"""PO3-BASE-M0 data manifest: hash + metadata the validated EURUSD tick store.

Read-only. Computes SHA256, row count and min/max timestamp per monthly parquet
partition. No strategy logic, no outcomes. Output feeds the frozen spec.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pyarrow.parquet as pq

STORE = Path(r"E:\ResearchData\botTrading\ticks\parquet\EURUSD")
OUT = Path(__file__).with_name("data_manifest.json")


def sha256_file(path: Path, buf: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(buf)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    entries = {}
    years = sorted(p for p in STORE.iterdir() if p.name.startswith("year="))
    for ydir in years:
        year = int(ydir.name.split("=")[1])
        if not (2010 <= year <= 2018):
            raise SystemExit(f"FORBIDDEN partition in store listing: {ydir}")
        for mdir in sorted(ydir.iterdir()):
            if not mdir.name.startswith("month="):
                continue
            month = int(mdir.name.split("=")[1])
            f = mdir / "ticks.parquet"
            md = pq.read_metadata(f)
            first_ts = pq.read_table(f, columns=["timestamp_utc"]).column(0)[0]
            # min/max via statistics on the timestamp column (no full decode)
            col = md.row_group(0).column(0)
            stats = col.statistics
            entries[f"{year}-{month:02d}"] = {
                "path": str(f),
                "sha256": sha256_file(f),
                "bytes": f.stat().st_size,
                "rows": md.num_rows,
                "row_groups": md.num_row_groups,
                "ts_min": str(stats.min) if stats else None,
                "ts_max": str(stats.max) if stats else None,
                "first_row_ts": str(first_ts),
            }
        print(f"hashed {ydir.name}", flush=True)
    total_rows = sum(e["rows"] for e in entries.values())
    out = {
        "store": str(STORE),
        "partition_count": len(entries),
        "total_rows": total_rows,
        "schema": "timestamp_utc[ns,UTC], bid, ask, mid, spread_pips, bid_volume, ask_volume",
        "entries": entries,
    }
    OUT.write_text(json.dumps(out, indent=1))
    print(json.dumps({"partition_count": len(entries), "total_rows": total_rows}))


if __name__ == "__main__":
    sys.exit(main())
