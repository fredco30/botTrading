"""Build the continuous-contract roll map for ZT/ZF/ZN.

For each symbol and each calendar month in the requested range, resolve the
volume-ranked continuous symbol to the actual raw contract via the (free)
symbology API, then map instrument_ids to raw symbols.

Output: E:\\ResearchData\\botTrading\\rates\\databento\\metadata\\roll_map.csv
Columns: symbol,instrument_id,raw_symbol,start_date,end_date
(start/end inclusive, UTC dates)
"""
import csv
import sys
from datetime import date
from pathlib import Path

import databento

from estimate_cost import DATASET, END, START, SYMBOLS, load_key_from_config

META_DIR = Path(r"E:\ResearchData\botTrading\rates\databento\metadata")


def month_iter(start: date, end: date):
    y, m = start.year, start.month
    while (y, m) < (end.year, end.month):
        yield date(y, m, 1)
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


def merge_intervals(intervals):
    """intervals: list of (d0, d1, value) -> merged adjacent same-value spans."""
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
    rows = []
    for sym in SYMBOLS:
        base = sym.split(".")[0]
        intervals = []
        id_to_raw = {}
        for month_start in month_iter(date.fromisoformat(START[:10]), date.fromisoformat(END[:10])):
            if month_start == date(2010, 6, 1):
                month_start = date.fromisoformat(START[:10])  # dataset floor is 2010-06-06
            month_end = month_start
            # end of month
            ny, nm = (month_start.year + 1, 1) if month_start.month == 12 else (month_start.year, month_start.month + 1)
            from datetime import timedelta
            month_end = date(ny, nm, 1) - timedelta(days=1)
            res = client.symbology.resolve(
                dataset=DATASET, symbols=[sym], stype_in="continuous",
                stype_out="instrument_id", start_date=month_start, end_date=month_end,
            )["result"][sym]
            for iv in res:
                intervals.append((date.fromisoformat(iv["d0"]), date.fromisoformat(iv["d1"]), iv["s"]))
        merged = merge_intervals(intervals)
        # resolve instrument_id -> raw_symbol scoped to each interval's dates
        id_to_raw = {}
        for d0, d1, iid in merged:
            if iid in id_to_raw:
                continue
            lo = max(d0, date.fromisoformat(START[:10]))
            res = client.symbology.resolve(
                dataset=DATASET, symbols=[iid], stype_in="instrument_id",
                stype_out="raw_symbol", start_date=lo.isoformat(), end_date=d1.isoformat(),
            )
            id_to_raw[iid] = res["result"][iid][0]["s"]
        for d0, d1, iid in merged:
            rows.append({
                "symbol": base,
                "instrument_id": iid,
                "raw_symbol": id_to_raw.get(iid, f"UNKNOWN_{iid}"),
                "start_date": d0.isoformat(),
                "end_date": d1.isoformat(),
            })
            print(base, d0, d1, iid, id_to_raw.get(iid))
    out = META_DIR / "roll_map.csv"
    with out.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["symbol", "instrument_id", "raw_symbol", "start_date", "end_date"])
        w.writeheader()
        w.writerows(rows)
    print(f"WROTE {out} rows={len(rows)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
