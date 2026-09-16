"""NQ OPR MODERN M1 — COST GUARD (mission section 4).

Exact Databento cost estimate for:
  GLBX.MDP3 / NQ.v.0 / ohlcv-1m / 2020-01-01 -> 2026-01-01 (exclusive).
Never prints or exposes the API key.
"""
import os
import sys
from pathlib import Path

import databento


def load_key_from_config() -> str | None:
    """Read the key from ~/.databento/config without ever printing it."""
    cfg = Path.home() / ".databento" / "config"
    if not cfg.exists():
        return os.environ.get("DATABENTO_API_KEY")
    for line in cfg.read_text().splitlines():
        line = line.strip()
        if line.startswith("key"):
            return line.split("=", 1)[1].strip().strip('"')
    return os.environ.get("DATABENTO_API_KEY")


DATASET = "GLBX.MDP3"
SYMBOLS = ["NQ.v.0"]
SCHEMA = "ohlcv-1m"
START = "2020-01-01T00:00:00"
END = "2026-01-01T00:00:00"  # exclusive — 2026 SEALED


def main() -> int:
    key = load_key_from_config()
    if not key:
        print("NO_API_KEY")
        return 2
    client = databento.Historical(key=key)
    kwargs = dict(dataset=DATASET, symbols=SYMBOLS, schema=SCHEMA,
                  start=START, end=END, stype_in="continuous")
    cost_cents = client.metadata.get_cost(**kwargs)
    print(f"ESTIMATED_COST_USD={cost_cents / 100:.2f}")
    try:
        nbytes = client.metadata.get_billable_size(**kwargs)
        print(f"ESTIMATED_BYTES={nbytes}")
    except Exception as e:  # noqa: BLE001
        print(f"ESTIMATED_BYTES=UNAVAILABLE ({type(e).__name__})")
    try:
        recs = client.metadata.get_record_count(**kwargs)
        print(f"ESTIMATED_RECORDS={recs}")
    except Exception as e:  # noqa: BLE001
        print(f"ESTIMATED_RECORDS=UNAVAILABLE ({type(e).__name__})")
    if cost_cents <= 0:
        print("COST_ZERO_CONTINUE")
        return 0
    print("COST_NONZERO_STOP_BEFORE_PURCHASE")
    print("DATA_PURCHASE_AUTH_REQUIRED")
    return 1


if __name__ == "__main__":
    sys.exit(main())
