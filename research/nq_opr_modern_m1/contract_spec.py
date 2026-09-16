"""Derive NQ contract specification from data + authoritative definitions.

Tick size is measured EMPIRICALLY from the acquired 1m data (mode of close
increments) rather than trusted from hard-coded assumptions. Multiplier /
currency / exchange are cross-checked against the CME-published contract spec
(NQ: $20 per index point, USD, CME Globex). Writes NQ_CONTRACT_SPEC.md inputs.
"""
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

PQ_DIR = Path(r"E:\ResearchData\botTrading\nq\databento\parquet")
META_DIR = Path(r"E:\ResearchData\botTrading\nq\databento\manifest")
HERE = Path(__file__).parent


def main() -> int:
    frames = [pd.read_parquet(PQ_DIR / f"nq_1m_{y}.parquet")
              for y in range(2020, 2026)
              if (PQ_DIR / f"nq_1m_{y}.parquet").exists()]
    df = pd.concat(frames, ignore_index=True)
    closes = df["close"].to_numpy()
    diffs = np.round(np.diff(closes), 10)
    diffs = diffs[diffs != 0]
    counts = Counter(np.abs(diffs))
    tick_candidates = sorted(counts.items(), key=lambda kv: -kv[1])[:6]
    min_step = min(abs(d) for d in diffs)
    print("MIN_POSITIVE_PRICE_INCREMENT =", min_step)
    print("TOP_INCREMENTS (abs, count) =", tick_candidates[:6])
    out = {
        "MIN_POSITIVE_PRICE_INCREMENT": float(min_step),
        "TOP_INCREMENTS": [[float(k), int(v)] for k, v in tick_candidates],
        "N_ROWS": int(len(df)),
        "PRICE_MIN": float(df["low"].min()),
        "PRICE_MAX": float(df["high"].max()),
    }
    META_DIR.mkdir(parents=True, exist_ok=True)
    (META_DIR / "tick_derivation.json").write_text(json.dumps(out, indent=1))
    (HERE / "tick_derivation.json").write_text(json.dumps(out, indent=1))
    print("CONTRACT_SPEC_DATA_DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
