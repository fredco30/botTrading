#!/usr/bin/env python3
"""TICK-M1 downloader: Dukascopy hourly EURUSD tick files over a date range.

Extends the TICK-M0 probe (`research/tick_m0/dukascopy_tick_probe.py`) to a
bulk, resumable, threaded downloader:

  URL: https://datafeed.dukascopy.com/datafeed/EURUSD/{y}/{mm0}/{dd}/{HH}h_ticks.bi5
  (mm0 = 0-indexed month on the wire, validated in TICK-M0)

Server behaviour (TICK-M0 + M1 field experience):
  - 200, empty body  -> no ticks in this hour (weekend close); persisted as a
    0-byte .bi5 marker.
  - 404              -> USUALLY no-data hour, BUT the CDN also serves SPURIOUS
    404s for existing files (observed 2026-09). Therefore 404 is retried with
    spaced backoff like any other soft error; only after retries are exhausted
    is a `<file>.missing` marker persisted. A verification pass
    (--verify-missing) re-requests every .missing marker once at the end so
    false markers can be repaired by re-running.
  - 429/503/5xx, remote disconnect -> retried with exponential backoff.
  - 200, payload     -> LZMA .bi5; validated at download time (decompresses,
    length % 20 == 0) before atomic persist; corrupt payloads are never
    persisted (they count as `corrupt` and are retried on the next run).

Idempotent/resumable: existing .bi5 and .missing files are skipped.
Politeness: per-worker pacing between requests; workers configurable.

Data root: --data-root > env BOTTRADING_TICK_DATA_ROOT > repo-relative default.
Nothing is written outside the resolved data root.
"""
import argparse
import json
import lzma
import os
import random
import sys
import threading
import time
from datetime import date, timedelta

import requests

import data_root

BASE = "https://datafeed.dukascopy.com/datafeed/{sym}/{y}/{m:02d}/{d:02d}/{h:02d}h_ticks.bi5"
UA = {"User-Agent": "Mozilla/5.0 (research-data-download)"}

_lock = threading.Lock()


def _write_atomic(path, data=b""):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, path)


def _persist_empty(out_path):
    _write_atomic(out_path, b"")  # 0-byte .bi5 = no ticks this hour


def _fetch_once(session, url):
    """One GET. Returns (raw_bytes_or_None, status_tag)."""
    try:
        r = session.get(url, headers=UA, timeout=(10, 20))
        if r.status_code == 200:
            return r.content, "ok200"
        return None, f"http{r.status_code}"
    except requests.exceptions.RequestException as e:
        return None, f"net:{type(e).__name__}"


def fetch_hour(session, out_path, symbol, y, m, d, h, retries=8, pace=0.0):
    """Fetch one hour. Status: cached|ok|empty|missing|corrupt|fail:<msg>.

    404 is retried like a soft error (spurious 404s observed on the CDN);
    only a 404 that survives all retries becomes a persistent .missing mark.
    """
    if os.path.exists(out_path) or os.path.exists(out_path + ".missing"):
        return "cached"
    url = BASE.format(sym=symbol, y=y, m=m - 1, d=d, h=h)
    last = "?"
    for k in range(retries):
        if pace:
            time.sleep(pace * (0.5 + random.random()))
        raw, tag = _fetch_once(session, url)
        if tag == "ok200":
            if len(raw) == 0:
                _persist_empty(out_path)
                return "empty"
            try:
                buf = lzma.decompress(raw, format=lzma.FORMAT_ALONE)
            except Exception:
                last = "corrupt"
                time.sleep(min(30.0, 2.0 * (k + 1)))
                continue
            if len(buf) == 0:
                _persist_empty(out_path)
                return "empty"
            if len(buf) % 20 != 0:
                last = "corrupt"
                time.sleep(min(30.0, 2.0 * (k + 1)))
                continue
            _write_atomic(out_path, raw)
            return "ok"
        last = tag
        if tag == "http404":
            # could be genuine no-data OR spurious; spaced retry, then accept
            time.sleep(min(20.0, 1.5 * (k + 1)))
            continue
        time.sleep(min(45.0, 2.0 * (k + 1)))
    if last == "http404":
        _write_atomic(out_path + ".missing", b"")
        return "missing"
    return f"fail:{last}"


def iter_hours(start: date, end_excl: date):
    d = start
    while d < end_excl:
        for h in range(24):
            yield d.year, d.month, d.day, h
        d += timedelta(days=1)


def run_download(paths, symbol, workers, retries, pace, progress_every, total):
    counts = {}
    counts_lock = threading.Lock()
    stop = threading.Event()

    def worker(chunk):
        session = requests.Session()
        for (y, m, d, h, p) in chunk:
            if stop.is_set():
                return
            st = fetch_hour(session, p, symbol, y, m, d, h, retries, pace)
            with counts_lock:
                counts[st] = counts.get(st, 0) + 1
                total_done = sum(counts.values())
                if total_done % progress_every == 0:
                    print(f"progress {total_done}/{total} {counts}", flush=True)

    from concurrent.futures import ThreadPoolExecutor

    chunks = [paths[i::workers] for i in range(workers)]
    with ThreadPoolExecutor(max_workers=workers) as ex:
        list(ex.map(worker, chunks))
    return counts


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--symbol", default="EURUSD")
    ap.add_argument("--start", required=True, help="YYYY-MM-DD inclusive")
    ap.add_argument("--end", required=True, help="YYYY-MM-DD exclusive (hard cut)")
    ap.add_argument("--data-root", default=None,
                    help="large-data root; env BOTTRADING_TICK_DATA_ROOT otherwise")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--retries", type=int, default=8)
    ap.add_argument("--pace", type=float, default=0.30,
                    help="mean polite delay per request per worker, seconds")
    ap.add_argument("--progress-every", type=int, default=500)
    ap.add_argument("--verify-missing", action="store_true",
                    help="re-request every .missing marker once (repairs false "
                         "markers); successful fetch replaces the marker")
    args = ap.parse_args()

    root = data_root.resolve_data_root(args.data_root)
    raw = data_root.raw_dir(root, args.symbol)
    y0, m0, d0 = (int(x) for x in args.start.split("-"))
    y1, m1, d1 = (int(x) for x in args.end.split("-"))
    start, end_excl = date(y0, m0, d0), date(y1, m1, d1)
    print(f"data_root={root}", flush=True)

    if args.verify_missing:
        marks = []
        for dirpath, _dirnames, filenames in os.walk(raw):
            for fn in filenames:
                if fn.endswith(".missing"):
                    p = os.path.join(dirpath, fn)
                    base = p[:-len(".missing")]
                    stem = os.path.basename(base)          # HHh_ticks.bi5
                    day_dir = os.path.basename(dirpath)    # YYYYMMDD
                    y, m, d = int(day_dir[:4]), int(day_dir[4:6]), int(day_dir[6:8])
                    h = int(stem[:2])
                    marks.append((y, m, d, h, base))
        print(f"verify_missing: {len(marks)} markers found", flush=True)
        repaired = 0
        for (y, m, d, h, base) in marks:
            os.remove(base + ".missing")
            session = requests.Session()
            st = fetch_hour(session, base, args.symbol, y, m, d, h, retries=4)
            if st in ("ok", "empty"):
                repaired += 1
                print(f"  repaired {base} -> {st}", flush=True)
        print(f"verify_missing: {repaired} markers repaired "
              f"({len(marks) - repaired} confirmed missing)", flush=True)
        return 0

    paths = [(y, m, d, h, data_root.hour_path(raw, y, m, d, h))
             for (y, m, d, h) in iter_hours(start, end_excl)]
    print(f"hours_to_ensure={len(paths)} range=[{start} .. {end_excl})", flush=True)

    t0 = time.time()
    counts = run_download(paths, args.symbol, max(1, args.workers),
                          args.retries, args.pace, args.progress_every, len(paths))
    hard_fail = counts.get("corrupt", 0) + sum(v for k, v in counts.items()
                                               if k.startswith("fail"))
    summary = {
        "symbol": args.symbol,
        "start": str(start),
        "end_exclusive": str(end_excl),
        "data_root": root,
        "hours_ensured": len(paths),
        "counts": counts,
        "hard_fail": hard_fail,
        "elapsed_sec": round(time.time() - t0, 1),
    }
    os.makedirs(raw, exist_ok=True)
    with open(os.path.join(raw, "_download_summary.json"), "w") as f:
        json.dump(summary, f, indent=2)
    print("SUMMARY " + json.dumps(summary), flush=True)
    return 1 if hard_fail else 0


if __name__ == "__main__":
    sys.exit(main())
