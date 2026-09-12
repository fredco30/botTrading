#!/usr/bin/env python3
"""Download Dukascopy daily 1-minute BID candle files (no API key).

Keep-alive sessions per worker + 503 backoff. Stores raw .bi5 (LZMA) files
under data_raw/<SYM>/<YYYY>/<YYYYMMDD>.bi5 (gitignored).
"""
import argparse
import concurrent.futures as cf
import lzma
import os
import threading
import time
from datetime import date, timedelta

import requests

BASE = "https://datafeed.dukascopy.com/datafeed/{sym}/{y}/{m:02d}/{d:02d}/BID_candles_min_1.bi5"
UA = {"User-Agent": "Mozilla/5.0 (research-data-download)"}

DEFAULT_INSTRUMENTS = ["EURUSD", "GBPUSD", "USDJPY", "USA500IDXUSD", "USATECHIDXUSD"]
START = date(2010, 1, 1)
END = date(2026, 4, 8)

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
RAW_DIR = os.path.join(ROOT, "data_raw")

_local = threading.local()


def session():
    if getattr(_local, "s", None) is None:
        s = requests.Session()
        s.headers.update(UA)
        _local.s = s
    return _local.s


def path_for(sym, d):
    return os.path.join(RAW_DIR, sym, str(d.year), f"{d:%Y%m%d}.bi5")


MISSING_DAYS = set()


def work(job):
    sym, d = job
    out = path_for(sym, d)
    if os.path.exists(out):
        return (sym, d, "cached")
    url = BASE.format(sym=sym, y=d.year, m=d.month - 1, d=d.day)
    last = "?"
    for k in range(6):
        try:
            r = session().get(url, timeout=45)
            if r.status_code == 404:
                return (sym, d, "missing")
            if r.status_code in (429, 503):
                last = f"http {r.status_code}"
                time.sleep(2.0 * (k + 1))
                continue
            if r.status_code != 200:
                last = f"http {r.status_code}"
                time.sleep(1.0)
                continue
            raw = r.content
            try:
                buf = lzma.decompress(raw, format=lzma.FORMAT_ALONE)
            except Exception:
                return (sym, d, "corrupt")
            if len(buf) < 24 or len(buf) % 24 != 0:
                return (sym, d, "corrupt")
            os.makedirs(os.path.dirname(out), exist_ok=True)
            tmp = out + ".tmp"
            with open(tmp, "wb") as f:
                f.write(raw)
            os.replace(tmp, out)
            return (sym, d, "ok")
        except requests.exceptions.RequestException as e:
            last = str(e)[:60]
            time.sleep(1.0 * (k + 1))
    return (sym, d, f"fail:{last}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--instruments", nargs="*", default=DEFAULT_INSTRUMENTS)
    ap.add_argument("--workers", type=int, default=10)
    args = ap.parse_args()

    jobs = []
    for sym in args.instruments:
        d = START
        while d <= END:
            if d.weekday() < 5:
                jobs.append((sym, d))
            d += timedelta(days=1)
    print(f"{len(jobs)} download jobs", flush=True)

    counts = {}
    t0 = time.time()
    with cf.ThreadPoolExecutor(max_workers=args.workers) as ex:
        for i, (sym, d, status) in enumerate(ex.map(work, jobs)):
            counts[status] = counts.get(status, 0) + 1
            if status.startswith("fail"):
                print(f"  RETRY-NEEDED {sym} {d}: {status}", flush=True)
            if (i + 1) % 1000 == 0:
                rate = (i + 1) / (time.time() - t0)
                eta = (len(jobs) - i - 1) / max(rate, 0.1) / 60
                print(f"  {i+1}/{len(jobs)} ({rate:.1f}/s, ETA {eta:.0f} min) {counts}", flush=True)
    print("DONE", counts, f"{time.time()-t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
