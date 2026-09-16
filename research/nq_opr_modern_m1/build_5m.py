"""Deterministic 5m bars from validated 1m NQ data (mission section 10).

Bucket label = 5-minute bucket START (UTC ns int64), identical to the frozen
p000 convention. OHLCV aggregation: first open, max high, min low, last close,
sum volume. NO forward filling. n_min = number of contributing 1m bars;
n_instr = distinct instrument ids in bucket (roll straddle detector).

Output: E:\\...\\nq\\databento\\parquet\\nq_5m_2020_2025.parquet
"""
import sys
from pathlib import Path

import pandas as pd

DATA_ROOT = Path(r"E:\ResearchData\botTrading\nq\databento")
PQ_DIR = DATA_ROOT / "parquet"
YEARS = [2020, 2021, 2022, 2023, 2024, 2025]


def main() -> int:
    frames = []
    for year in YEARS:
        p = PQ_DIR / f"nq_1m_{year}.parquet"
        if p.exists():
            frames.append(pd.read_parquet(p))
    df = pd.concat(frames, ignore_index=True).sort_values("ts").reset_index(drop=True)
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    bucket = df["ts"].dt.floor("5min")
    agg = df.assign(bucket=bucket).groupby("bucket").agg(
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
        volume=("volume", "sum"),
        n_min=("close", "size"),
        n_instr=("instrument_id", "nunique"),
        instrument_id=("instrument_id", "last"),
    ).reset_index().rename(columns={"bucket": "ts"})
    agg["ts"] = agg["ts"].astype("int64")
    agg.to_parquet(PQ_DIR / "nq_5m_2020_2025.parquet", index=False)
    print(f"5m rows={len(agg)} span={agg['ts'].iloc[0]}..{agg['ts'].iloc[-1]}")
    print("BUILD_5M_DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
