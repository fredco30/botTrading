#!/usr/bin/env python3
"""Minimal synthetic tests for tick_m0 decode/aggregation. Run: python test_tick_m0.py"""
import datetime
import struct
import sys

import numpy as np

sys.path.insert(0, "research/tick_m0")
import decode_ticks as dt

PASS = []
FAIL = []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append((name, detail))


def encode_tick(ms, ask, bid, av, bv):
    return struct.pack(">IIIff", ms, int(round(ask * 1e5)), int(round(bid * 1e5)), av, bv)


HS = datetime.datetime.fromisoformat("2018-06-04T12:00:00+00:00")

# 1. decode a 20-byte record: timestamp, scaling, volumes
buf = encode_tick(1500, 1.17000, 1.16997, 2.5, 1.5)
t = dt.decode_buf(buf, HS)
check("record_size_divisible", True)
check("timestamp_ms_offset", t["timestamp_ns"][0] == int(HS.timestamp()) * 1_000_000_000 + 1_500_000_000, str(t["timestamp_ns"][0]))
check("ask_scaling", abs(t["ask"][0] - 1.17000) < 1e-9, str(t["ask"][0]))
check("bid_scaling", abs(t["bid"][0] - 1.16997) < 1e-9, str(t["bid"][0]))
check("ask_volume", abs(t["ask_volume"][0] - 2.5) < 1e-6)
check("bid_volume", abs(t["bid_volume"][0] - 1.5) < 1e-6)

# 2. spread pips
sp = (t["ask"] - t["bid"])[0] / 1e-4
check("spread_pips", abs(sp - 0.3) < 1e-9, str(sp))

# 3. corrupted record (19 bytes) rejected
try:
    dt.decode_buf(buf[:-1], HS, strict=True)
    check("corrupt_rejected", False, "no exception")
except ValueError:
    check("corrupt_rejected", True)

# 4. ASK < BID detected
buf_bad = encode_tick(2000, 1.16990, 1.16997, 1.0, 1.0)
errs = dt.validate(dt.decode_buf(buf_bad, HS, strict=False), HS)
check("ask_lt_bid_detected", any("ASK < BID" in e for e in errs), str(errs))

# 5. monotone timestamp check: out-of-hour ms rejected
buf_far = encode_tick(4_000_000, 1.17, 1.1699, 1.0, 1.0)  # > 1h offset
errs = dt.validate(dt.decode_buf(buf_far, HS, strict=False), HS)
check("hour_bounds_enforced", any("outside hour bounds" in e for e in errs), str(errs))

# 6. monotonic timestamps: decode concatenation of two ordered records stays monotone
buf2 = encode_tick(1000, 1.17, 1.1699, 1.0, 1.0) + encode_tick(2000, 1.17, 1.1699, 1.0, 1.0)
t2 = dt.decode_buf(buf2, HS, strict=False)
check("monotonic_ok", bool(np.all(np.diff(t2["timestamp_ns"]) >= 0)))
buf3 = encode_tick(2000, 1.17, 1.1699, 1.0, 1.0) + encode_tick(1000, 1.17, 1.1699, 1.0, 1.0)
t3 = dt.decode_buf(buf3, HS, strict=False)
errs = dt.validate(t3, HS)
check("non_monotonic_detected", any("not monotone" in e for e in errs), str(errs))

# 7. negative volume rejected
recs_bad = np.frombuffer(encode_tick(1000, 1.17, 1.1699, 1.0, -1.0),
                         dtype=[("ms", ">u4"), ("a", ">u4"), ("b", ">u4"), ("av", ">f4"), ("bv", ">f4")]).copy()
recs_bad["bv"] = np.float32(-1.0)
errs = dt.validate(dt.decode_buf(recs_bad.tobytes(), HS, strict=False), HS)
check("negative_volume_detected", any("negative volumes" in e for e in errs), str(errs))

# 8. 5m aggregation causally correct: buckets [t, t+5m), left-labeled
import pandas as pd

ts = [int(HS.timestamp() * 1e9) + m * 60_000_000_000 for m in (0, 1, 4, 5, 6)]
t4 = {"timestamp_ns": np.array(ts, dtype=np.int64),
      "bid": np.array([1.10, 1.12, 1.11, 1.20, 1.13]),
      "ask": np.array([1.10, 1.12, 1.11, 1.20, 1.13]),
      "bid_volume": np.ones(5), "ask_volume": np.ones(5)}
bars = dt.aggregate_5m_bid(t4)
check("agg_bucket_count", len(bars) == 2, str(bars))
b0 = bars.iloc[0]
check("agg_open_first", abs(b0["open"] - 1.10) < 1e-12, str(b0["open"]))
check("agg_close_last", abs(b0["close"] - 1.11) < 1e-12, str(b0["close"]))
check("agg_high_low", abs(b0["high"] - 1.12) < 1e-12 and abs(b0["low"] - 1.10) < 1e-12)
check("agg_second_bucket_start", bars.index[1] == pd.Timestamp("2018-06-04T12:05:00Z"), str(bars.index[1]))

print(f"PASS {len(PASS)}  FAIL {len(FAIL)}")
for n, d in FAIL:
    print(f"  FAIL: {n} {d}")
sys.exit(1 if FAIL else 0)
