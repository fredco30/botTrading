#!/usr/bin/env python3
"""M0 tick probe: download Dukascopy hourly tick files for EURUSD sample days.

Public endpoint (no key):
  https://datafeed.dukascopy.com/datafeed/EURUSD/{y}/{mm0}/{dd}/{HH}h_ticks.bi5
where mm0 is 0-indexed month. Files are LZMA-compressed raw tick records.

Stores raw .bi5 under data_raw/tick_m0/EURUSD/{YYYYMMDD}/{HH}h_ticks.bi5
(gitignored). Idempotent: skips files already on disk (unless --force).
"""
import argparse
import lzma
import os
import sys
import time

import requests

BASE = "https://datafeed.dukascopy.com/datafeed/{sym}/{y}/{m:02d}/{d:02d}/{h:02d}h_ticks.bi5"
UA = {"User-Agent": "Mozilla/5.0 (research-data-download)"}
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
RAW_DIR = os.path.join(ROOT, "data_raw", "tick_m0")


def path_for(sym, y, m, d, h):
    return os.path.join(RAW_DIR, sym, f"{y:04d}{m:02d}{d:02d}", f"{h:02d}h_ticks.bi5")


def fetch_one(sym, y, m, d, h, force=False, retries=6):
    """Returns (status, path_or_err). status in {ok, cached, missing, empty, corrupt, fail:<msg>}"""
    out = path_for(sym, y, m, d, h)
    if os.path.exists(out) and not force:
        return "cached", out
    url = BASE.format(sym=sym, y=y, m=m - 1, d=d, h=h)
    last = "?"
    for k in range(retries):
        try:
            r = requests.get(url, headers=UA, timeout=45)
            if r.status_code == 404:
                return "missing", out
            if r.status_code in (429, 503):
                last = f"http {r.status_code}"
                time.sleep(2.0 * (k + 1))
                continue
            if r.status_code != 200:
                last = f"http {r.status_code}"
                time.sleep(1.0 * (k + 1))
                continue
            raw = r.content
            if len(raw) == 0:
                # Empty 200 body = no ticks in this hour (e.g. FX weekend close). Keep marker.
                os.makedirs(os.path.dirname(out), exist_ok=True)
                with open(out, "wb") as f:
                    f.write(raw)
                return "empty", out
            try:
                buf = lzma.decompress(raw, format=lzma.FORMAT_ALONE)
            except Exception:
                return "corrupt", out
            if len(buf) == 0:
                # Weekend / no-data hour: legit empty payload, keep it.
                os.makedirs(os.path.dirname(out), exist_ok=True)
                with open(out, "wb") as f:
                    f.write(raw)
                return "empty", out
            if len(buf) % 20 != 0:
                return "corrupt", out
            os.makedirs(os.path.dirname(out), exist_ok=True)
            tmp = out + ".tmp"
            with open(tmp, "wb") as f:
                f.write(raw)
            os.replace(tmp, out)
            return "ok", out
        except requests.exceptions.RequestException as e:
            last = str(e)[:80]
            time.sleep(1.0 * (k + 1))
    return f"fail:{last}", out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="EURUSD")
    ap.add_argument("--dates", nargs="*", required=True, help="YYYY-MM-DD list")
    args = ap.parse_args()

    from datetime import date

    counts = {}
    for ds in args.dates:
        y, m, dd = (int(x) for x in ds.split("-"))
        d = date(y, m, dd)
        if d.weekday() >= 5:
            print(f"{ds}: weekend, skipped")
            continue
        for h in range(24):
            status, info = fetch_one(args.symbol, y, m, dd, h)
            counts[status] = counts.get(status, 0) + 1
            if status.startswith("fail") or status == "corrupt":
                print(f"  PROBLEM {ds} h={h:02d}: {status}", flush=True)
        print(f"{ds}: {counts}", flush=True)
    bad = sum(v for k, v in counts.items() if k.startswith("fail") or k == "corrupt")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
