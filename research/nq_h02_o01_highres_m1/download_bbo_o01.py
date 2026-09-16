#!/usr/bin/env python3
"""Download BBO-1s for the 420 frozen P000 execution windows.

AUTHORIZATION: human-approved 2026-09-16, BBO-1S ONLY, hard ceiling USD 4.00
(estimate 3.128). Any other schema/purchase = forbidden. 2026 sealed.
Timeseries API, one call per merged window, raw contract symbol (raw_symbol).
Stores original DBN outside git under E:\\...\\highres\\bbo_1s\\ with a
per-window manifest (sha256, start/end, record count). Resumable.
"""
import hashlib
import json
import os
import sys
import time
from pathlib import Path

import pandas as pd
import databento

HERE = Path(__file__).parent
OUT_DIR = Path(r"E:/ResearchData/botTrading/nq/databento/highres/bbo_1s_o01")
MANIFEST = HERE / "BBO_DOWNLOAD_MANIFEST_O01.json"
DATASET = "GLBX.MDP3"
SCHEMA = "bbo-1s"


def load_key():
    cfg = Path.home() / ".databento" / "config"
    if cfg.exists():
        for line in cfg.read_text().splitlines():
            line = line.strip()
            if line.startswith("key"):
                return line.split("=", 1)[1].strip().strip('"')
    return os.environ.get("DATABENTO_API_KEY")


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    key = load_key()
    client = databento.Historical(key=key)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    man = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {
        "authorization": "O01 BBO-1S ONLY, ceiling USD 2.00, human-approved 2026-09-16",
        "windows": {},
    }
    wins = pd.read_csv(HERE / "O01_union_windows.csv")
    wins["START"] = pd.to_datetime(wins["START"], utc=True)
    wins["END"] = pd.to_datetime(wins["END"], utc=True)
    merged = wins.sort_values("DATE")
    done = 0
    for k, r in merged.iterrows():
        wid = f"{r['DATE']}_{r['CONTRACT']}"
        if wid in man["windows"]:
            continue
        f = OUT_DIR / f"{wid}.dbn.zst"
        if not f.exists() or f.stat().st_size == 0:
            store = client.timeseries.get_range(
                dataset=DATASET, symbols=[r["CONTRACT"]], schema=SCHEMA,
                start=r["START"].strftime("%Y-%m-%dT%H:%M:%S"),
                end=r["END"].strftime("%Y-%m-%dT%H:%M:%S"),
                stype_in="raw_symbol")
            store.to_file(str(f))
            recs = len(store.data) if hasattr(store, "data") else None
            time.sleep(0.2)
        else:
            recs = None
        man["windows"][wid] = {
            "file": str(f), "size_bytes": f.stat().st_size,
            "sha256": sha256_file(f),
            "start": r["START"].strftime("%Y-%m-%dT%H:%M:%S"),
            "end": r["END"].strftime("%Y-%m-%dT%H:%M:%S"),
            "record_count": recs,
        }
        done += 1
        if done % 25 == 0:
            MANIFEST.write_text(json.dumps(man, indent=1))
            print(f"{k + 1}/{len(merged)} downloaded cumulative={done}", flush=True)
    MANIFEST.write_text(json.dumps(man, indent=1))
    total_bytes = sum(w["size_bytes"] for w in man["windows"].values())
    print(f"DOWNLOAD_COMPLETE windows={len(man['windows'])} "
          f"total_bytes={total_bytes} ({total_bytes/1e6:.1f} MB)", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
