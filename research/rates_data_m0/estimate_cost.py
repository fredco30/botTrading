"""Cost estimate for the ZT/ZF/ZN ohlcv-1m historical request.

Prints the estimated USD cost. Exit code 1 if over budget cap.
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
            key = line.split("=", 1)[1].strip().strip('"')
            return key
    return os.environ.get("DATABENTO_API_KEY")

DATASET = "GLBX.MDP3"
SYMBOLS = ["ZT.v.0", "ZF.v.0", "ZN.v.0"]
SCHEMA = "ohlcv-1m"
START = "2010-06-06T00:00:00"
END = "2019-01-01T00:00:00"  # exclusive
BUDGET_CAP_USD = 30.00


def main() -> int:
    key = load_key_from_config()
    if not key:
        print("NO_API_KEY")
        return 2
    client = databento.Historical(key=key)
    cost = client.metadata.get_cost(
        dataset=DATASET,
        symbols=SYMBOLS,
        schema=SCHEMA,
        start=START,
        end=END,
    )
    print(f"ESTIMATED_COST_USD={cost / 100:.2f}")
    print(f"databento client version={databento.__version__}")
    if cost / 100 > BUDGET_CAP_USD:
        print(f"OVER_BUDGET cap={BUDGET_CAP_USD:.2f}")
        return 1
    print("WITHIN_BUDGET")
    return 0


if __name__ == "__main__":
    sys.exit(main())
