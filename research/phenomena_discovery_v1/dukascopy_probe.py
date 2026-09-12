#!/usr/bin/env python3
"""Probe Dukascopy public datafeed for instrument availability.

Checks (all without any API key):
  * which instrument IDs exist (USA500IDXUSD, USA100IDXUSD, USA30IDXUSD,
    EURUSD, GBPUSD, USDJPY, and stock CFD candidates);
  * trading-hours coverage on a sample day (does the 04:00-09:30 ET
    pre-market window exist?);
  * earliest available year (binary probe).
"""
import lzma
import struct
import time
import urllib.error
import urllib.request
from datetime import date

BASE = "https://datafeed.dukascopy.com/datafeed/{sym}/{y}/{m:02d}/{d:02d}/BID_candles_min_1.bi5"
UA = {"User-Agent": "Mozilla/5.0 (research-data-probe)"}

CANDLE = struct.Struct(">i5f")  # offset_sec, open, close, low, high, volume


def fetch(url, tries=4):
    last = None
    for k in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=40) as r:
                return r.read()
        except Exception as e:  # transient network issues observed
            last = e
            time.sleep(1.5 * (k + 1))
    raise last


def day_candles(sym, y, m, d):
    """Return list of (ts_sec_utc, open, close, low, high, vol) or None."""
    url = BASE.format(sym=sym, y=y, m=m - 1, d=d)  # Dukascopy month is 0-based
    try:
        raw = fetch(url)
    except urllib.error.HTTPError as e:
        return None
    try:
        buf = lzma.decompress(raw, format=lzma.FORMAT_ALONE)
    except Exception:
        return None
    out = []
    for i in range(0, len(buf) - CANDLE.size + 1, CANDLE.size):
        off, o, c, l, h, v = CANDLE.unpack_from(buf, i)
        ts = date(y, m, d).toordinal() * 86400 + off  # placeholder, real epoch below
        out.append((off, o, c, l, h, v))
    return out


def check_consistency(rows):
    bad = 0
    for off, o, c, l, h, v in rows:
        if not (h >= max(o, c) - 1e-9 and l <= min(o, c) + 1e-9):
            bad += 1
    return bad


def hours(sym, y, m, d):
    rows = day_candles(sym, y, m, d)
    if rows is None:
        return None
    hh = sorted({r[0] // 3600 for r in rows})
    bad = check_consistency(rows)
    vol_nonzero = any(r[5] > 0 for r in rows)
    return len(rows), hh, bad, vol_nonzero


def first_year(sym, lo=2003, hi=2025):
    """Probe January 15 of each year until a file exists."""
    for y in range(lo, hi):
        r = day_candles(sym, y, 1, 15)
        if r:
            return y, len(r)
    return None, 0


if __name__ == "__main__":
    import sys
    syms = sys.argv[1:] or ["USA500IDXUSD", "USA100IDXUSD", "USA30IDXUSD",
                            "EURUSD", "GBPUSD", "USDJPY"]
    print("== sample day 2020-03-10 (UTC hours present) ==")
    for s in syms:
        r = hours(s, 2020, 3, 10)
        print(f"{s}: {r}")
    print("== sample day 2020-03-09 (Sunday) ==")
    for s in syms[:3]:
        r = hours(s, 2020, 3, 8)
        print(f"{s}: {r}")
    print("== first year with data ==")
    for s in syms:
        y, n = first_year(s)
        print(f"{s}: first_year={y} rows_that_day={n}")
