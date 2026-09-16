"""NQ continuous-contract roll map (free symbology API; rates-data-m0 method).

Output: E:\\ResearchData\\botTrading\\nq\\databento\\manifest\\roll_map.csv
Columns: symbol,instrument_id,raw_symbol,start_date,end_date (inclusive UTC dates).
Also writes manifest/symbology_resolution.json for provenance.
"""
import csv
import json
import sys
from datetime import date, timedelta
from pathlib import Path

import databento
from estimate_cost import DATASET, load_key_from_config

META_DIR = Path(r"E:\ResearchData\botTrading\nq\databento\manifest")
SYMBOL = "NQ.v.0"
START = date(2020, 1, 1)
END = date(2026, 1, 1)  # exclusive — 2026 SEALED


def month_iter(start: date, end: date):
    y, m = start.year, start.month
    while (y, m) < (end.year, end.month):
        yield date(y, m, 1)
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


def merge_intervals(intervals):
    if not intervals:
        return []
    intervals.sort()
    merged = [list(intervals[0])]
    for d0, d1, val in intervals[1:]:
        prev = merged[-1]
        if val == prev[2]:
            prev[1] = max(prev[1], d1)
        else:
            merged.append([d0, d1, val])
    return merged


def main() -> int:
    META_DIR.mkdir(parents=True, exist_ok=True)
    client = databento.Historical(key=load_key_from_config())
    intervals = []
    raw_all = []
    for month_start in month_iter(START, END):
        ny, nm = (month_start.year + 1, 1) if month_start.month == 12 else \
                 (month_start.year, month_start.month + 1)
        month_end = date(ny, nm, 1) - timedelta(days=1)
        if month_end >= END:
            month_end = END - timedelta(days=1)
        res = client.symbology.resolve(
            dataset=DATASET, symbols=[SYMBOL], stype_in="continuous",
            stype_out="instrument_id", start_date=month_start, end_date=month_end,
        )["result"][SYMBOL]
        raw_all.append({"month": month_start.isoformat(), "result": res})
        for iv in res:
            intervals.append((date.fromisoformat(iv["d0"]),
                              date.fromisoformat(iv["d1"]), iv["s"]))
    merged = merge_intervals(intervals)
    id_to_raw = {}
    for d0, d1, iid in merged:
        if iid in id_to_raw:
            continue
        res = client.symbology.resolve(
            dataset=DATASET, symbols=[iid], stype_in="instrument_id",
            stype_out="raw_symbol", start_date=max(d0, START).isoformat(),
            end_date=d1.isoformat(),
        )
        id_to_raw[iid] = res["result"][iid][0]["s"]
    rows = []
    for d0, d1, iid in merged:
        rows.append({"symbol": "NQ", "instrument_id": iid,
                     "raw_symbol": id_to_raw.get(iid, f"UNKNOWN_{iid}"),
                     "start_date": d0.isoformat(), "end_date": d1.isoformat()})
        print("NQ", d0, d1, iid, id_to_raw.get(iid))
    out = META_DIR / "roll_map.csv"
    with out.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["symbol", "instrument_id",
                                           "raw_symbol", "start_date", "end_date"])
        w.writeheader()
        w.writerows(rows)
    (META_DIR / "symbology_resolution.json").write_text(json.dumps(raw_all, indent=1))
    print(f"WROTE {out} rows={len(rows)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
