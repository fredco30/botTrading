"""Convert acquired raw DBN (ohlcv-1m) yearly files to normalized Parquet.

Input : E:\\ResearchData\\botTrading\\nq\\databento\\raw\\glbx-mdp3-<year>.ohlcv-1m.dbn.zst
Output: E:\\ResearchData\\botTrading\\nq\\databento\\parquet\\nq_1m_<year>.parquet
Columns: ts (UTC ns int64), open, high, low, close, volume, instrument_id.
No fabrication, no forward filling — raw bars only.
"""
import json
import sys
from pathlib import Path

import pandas as pd
from databento import DBNStore

DATA_ROOT = Path(r"E:\ResearchData\botTrading\nq\databento")
RAW_DIR = DATA_ROOT / "raw"
OUT_DIR = DATA_ROOT / "parquet"
YEARS = [2020, 2021, 2022, 2023, 2024, 2025]


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for year in YEARS:
        srcs = sorted((RAW_DIR / str(year)).glob("**/*.dbn.zst"))
        dst = OUT_DIR / f"nq_1m_{year}.parquet"
        if not srcs:
            print(f"{year}: MISSING raw files, skip")
            continue
        if dst.exists():
            print(f"{year}: parquet exists, skip")
            continue
        parts = []
        for src in srcs:
            parts.append(DBNStore.from_file(str(src)).to_df().reset_index())
        df = pd.concat(parts, ignore_index=True)
        # ts_event column (UTC). Keep only what we need.
        cols = {"ts_event": "ts", "open": "open", "high": "high",
                "low": "low", "close": "close", "volume": "volume",
                "instrument_id": "instrument_id"}
        df = df[[c for c in cols if c in df.columns]].rename(columns=cols)
        df["ts"] = df["ts"].astype("int64")
        df = df.sort_values("ts").reset_index(drop=True)
        df.to_parquet(dst, index=False)
        stats = {"year": year, "rows": int(len(df)),
                 "first_ts": str(pd.Timestamp(df["ts"].iloc[0], unit="ns", tz="UTC")),
                 "last_ts": str(pd.Timestamp(df["ts"].iloc[-1], unit="ns", tz="UTC")),
                 "instruments": sorted(df["instrument_id"].unique().tolist())}
        print(json.dumps(stats))
    print("CONVERT_DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
