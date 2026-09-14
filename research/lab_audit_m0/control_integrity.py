#!/usr/bin/python3
"""LAB_AUDIT_M0 — data integrity reconfirmation (mission section 15).
Expectations frozen in LAB_AUDIT_M0_SPEC.md section 11 BEFORE execution."""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import lab_audit_lib as AL

SPOT_CHECK_MONTHS = [(2010, 1), (2014, 6), (2018, 12)]   # frozen in spec


def main() -> dict:
    man = AL.load_manifest()
    entries = man["entries"]
    part_paths = sorted((AL.STORE).glob("year=*"))
    n_dirs = len(part_paths)
    n_parts = 0
    total_rows_footer = 0
    row_mismatches = []
    mono_viol = 0
    bid_gt_ask = 0
    non_positive = 0
    dup_ts = 0
    nan_count = 0
    ts_min_global = None
    ts_max_global = None
    bounds_outside_manifest = []

    import pyarrow.parquet as pq
    for ydir in part_paths:
        year = int(ydir.name.split("=")[1])
        for mdir in sorted(ydir.glob("month=*")):
            month = int(mdir.name.split("=")[1])
            rel = f"{AL.STORE}\\year={year}\\month={month:02d}\\ticks.parquet"
            entry = entries[f"{year}-{month:02d}"]
            assert entry["path"] == rel, f"manifest path mismatch {rel}"
            n_parts += 1
            pf = pq.ParquetFile(rel)
            rows_footer = pf.metadata.num_rows
            total_rows_footer += rows_footer
            if rows_footer != entry["rows"]:
                row_mismatches.append(f"{year}-{month:02d}: {rows_footer} != {entry['rows']}")
            ts, bid, ask, mid, spread = AL.load_partition_raw(year, month)
            if len(ts):
                lo, hi = int(ts[0]), int(ts[-1])
                ts_min_global = lo if ts_min_global is None else min(ts_min_global, lo)
                ts_max_global = hi if ts_max_global is None else max(ts_max_global, hi)
                # manifest bounds are ISO strings; compare at microsecond tolerance
                e_lo = int(datetime.fromisoformat(entry["ts_min"]).timestamp() * 1e9)
                e_hi = int(datetime.fromisoformat(entry["ts_max"]).timestamp() * 1e9)
                if not (abs(e_lo - lo) <= 1000 and abs(e_hi - hi) <= 1000):
                    bounds_outside_manifest.append(f"{year}-{month:02d}")
            nan_count += int((~np.isfinite(bid)).sum() + (~np.isfinite(ask)).sum())
            non_positive += int(((bid <= 0) | (ask <= 0)).sum())
            bad = (~np.isfinite(bid)) | (~np.isfinite(ask)) | (bid <= 0) | (ask <= 0)
            b = bid[~bad]; a = ask[~bad]
            bid_gt_ask += int((b > a).sum())
            d = np.diff(ts)
            mono_viol += int((d < 0).sum())
            dup_ts += int(len(ts) - len(np.unique(ts)))
            del ts, bid, ask, mid, spread

    # SHA256 spot-check (no full re-hash; manifest independently spot-checked)
    spot = {}
    for (y, m) in SPOT_CHECK_MONTHS:
        rel = AL.partition_path(y, m)
        got = AL.sha256_file(rel)
        ok = got == entries[f"{y}-{m:02d}"]["sha256"]
        spot[f"{y}-{m:02d}"] = {"match": bool(ok), "sha256": got}
        if not ok:
            spot[f"{y}-{m:02d}"]["expected"] = entries[f"{y}-{m:02d}"]["sha256"]

    res = {
        "partition_count": n_parts,
        "partition_count_expected": 108,
        "total_rows_footer": total_rows_footer,
        "total_rows_expected": 209_682_628,
        "row_count_mismatches": row_mismatches,
        "ts_bounds_mismatches": bounds_outside_manifest,
        "first_ts_utc": None if ts_min_global is None else
            np.datetime64(ts_min_global, "ns").astype("datetime64[us]").astype(str),
        "last_ts_utc": None if ts_max_global is None else
            np.datetime64(ts_max_global, "ns").astype("datetime64[us]").astype(str),
        "monotonic_violations": mono_viol,
        "bid_gt_ask_count": bid_gt_ask,
        "non_positive_quote_count": non_positive + nan_count,
        "duplicate_timestamp_count": dup_ts,
        "sha256_spot_checks": spot,
        "spot_check_months": SPOT_CHECK_MONTHS,
    }
    checks = {
        "partition_count_108": n_parts == 108,
        "rows_match_manifest": total_rows_footer == 209_682_628 and not row_mismatches,
        "ts_bounds_match_manifest": not bounds_outside_manifest,
        "monotonic": mono_viol == 0,
        "bid_le_ask": bid_gt_ask == 0,
        "positive_quotes": (non_positive + nan_count) == 0,
        "sha_spot_checks_pass": all(v["match"] for v in spot.values()),
    }
    res["checks"] = checks
    res["PASS"] = all(checks.values())
    return res


if __name__ == "__main__":
    r = main()
    out = Path(__file__).parent / "RESULTS_integrity.json"
    out.write_text(json.dumps(r, indent=1))
    print(json.dumps(r, indent=1))
    print("INTEGRITY_PASS" if r["PASS"] else "INTEGRITY_FAIL")
