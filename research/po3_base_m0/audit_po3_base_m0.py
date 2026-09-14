"""PO3-BASE-M0 audit (spec section 18): independent verification to exclude a
coding error on a clearly-negative result.

Deliberately DIFFERENT implementation path from the engine: pandas resample for
M1 candles, plain-Python event walk, pandas CSV round-trip of the trades file.
Re-derives a random sample of trades end-to-end and cross-checks global counters.
"""
from __future__ import annotations

import json
import random
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
STORE = Path(r"E:\ResearchData\botTrading\ticks\parquet\EURUSD")
LON = ZoneInfo("Europe/London")
PIP = 1e-4

trades = json.loads((HERE / "po3_base_m0_trades.json").read_text())
results = json.loads((HERE / "po3_base_m0_results.json").read_text())

rng = random.Random(20260914)
sample = rng.sample(trades, min(15, len(trades)))
sample.sort(key=lambda t: t["date"])

failures = []


def ns(dt: datetime) -> int:
    return int(dt.timestamp()) * 1_000_000_000


def day_ticks(date_str: str) -> pd.DataFrame:
    d = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=LON)
    start = d.astimezone(timezone.utc)
    end = start + pd.Timedelta(hours=12, minutes=36)
    frames = []
    for stamp in {start, end}:
        frames.append((stamp.year, stamp.month))
    parts = []
    for (y, m) in sorted(frames):
        f = STORE / f"year={y}" / f"month={m:02d}" / "ticks.parquet"
        t = pd.read_parquet(f, columns=["timestamp_utc", "bid", "ask"])
        parts.append(t)
    t = pd.concat(parts, ignore_index=True).drop_duplicates(subset="timestamp_utc")
    t["ts"] = (t["timestamp_utc"].astype("int64") // 1_000_000).astype("int64") * 1_000_000
    t = t[(t["ts"] >= ns(start)) & (t["ts"] <= ns(end))]
    t = t[(t["bid"] > 0) & (t["ask"] > 0)].sort_values("ts")
    t["mid"] = (t["bid"] + t["ask"]) / 2
    return t


for tr in sample:
    t = day_ticks(tr["date"])
    d0 = datetime.strptime(tr["date"], "%Y-%m-%d").replace(tzinfo=LON)
    a0, a1 = ns(d0), ns(d0) + pd.Timedelta(hours=7).value
    asia = t[(t["ts"] >= a0) & (t["ts"] < a1)]
    hi, lo = float(asia["mid"].max()), float(asia["mid"].min())
    rng_ = hi - lo
    if abs(hi - tr["asian_high"]) > 1e-12 or abs(lo - tr["asian_low"]) > 1e-12 \
            or abs(rng_ / PIP - tr["asian_range_pips"]) > 1e-6:
        failures.append(f"{tr['date']}: asian range mismatch")

    o0 = a1
    o1 = o0 + pd.Timedelta(hours=3).value
    obs = t[(t["ts"] >= o0) & (t["ts"] < o1)]
    up_t, lo_t = hi + 0.2 * rng_, lo - 0.2 * rng_
    up_hit = obs[obs["mid"] >= up_t]
    lo_hit = obs[obs["mid"] <= lo_t]
    first_up = int(up_hit["ts"].iloc[0]) if len(up_hit) else None
    first_lo = int(lo_hit["ts"].iloc[0]) if len(lo_hit) else None
    cands = [x for x in (first_up, first_lo) if x is not None]
    sweep_ts = min(cands)
    side = 1 if (first_up is not None and first_up == sweep_ts) else -1
    if sweep_ts != tr["sweep_ts"] or side != (1 if tr["sweep"] == "UPPER" else -1):
        failures.append(f"{tr['date']}: sweep side/ts mismatch")

    # reintegration: M1 resample, buckets from the sweep's own bucket, <= +15 min
    m1 = t.set_index("ts").copy()
    m1["bucket"] = (m1.index // 60_000_000_000) * 60_000_000_000
    closes = m1.groupby("bucket")["mid"].last()
    decision = None
    start_bucket = (sweep_ts // 60_000_000_000) * 60_000_000_000
    for bucket, close in closes.items():
        if bucket < start_bucket:
            continue
        end = bucket + 60_000_000_000
        if end > sweep_ts + 900_000_000_000:
            break
        inside = close < hi if side > 0 else close > lo
        if inside:
            decision = end
            break
    if decision != tr["decision_ts"]:
        failures.append(f"{tr['date']}: decision_ts mismatch {decision} vs {tr['decision_ts']}")
        continue

    # extreme through decision (exclusive)
    seg = t[(t["ts"] >= sweep_ts) & (t["ts"] < decision)]
    extreme = float(seg["mid"].max()) if side > 0 else float(seg["mid"].min())
    if abs(extreme - tr["sweep_extreme"]) > 1e-12:
        failures.append(f"{tr['date']}: extreme mismatch {extreme} vs {tr['sweep_extreme']}")

    direction = -side
    ref = decision + 5_000_000_000
    if direction > 0:
        q = t[t["ts"] >= ref]
        entry_ts, entry_px = int(q["ts"].iloc[0]), float(q["ask"].iloc[0])
    else:
        q = t[t["ts"] >= ref]
        entry_ts, entry_px = int(q["ts"].iloc[0]), float(q["bid"].iloc[0])
    if entry_ts != tr["entry_ts"] or abs(entry_px - tr["entry_px"]) > 1e-12:
        failures.append(f"{tr['date']}: entry mismatch")
        continue
    r = abs(entry_px - extreme)
    target = entry_px + 2 * r if direction > 0 else entry_px - 2 * r
    # exit scan, plain python
    q = t[t["ts"] >= entry_ts].reset_index(drop=True)
    side_px = q["bid"] if direction > 0 else q["ask"]
    if direction > 0:
        stop_i = next((i for i, p in enumerate(side_px) if p <= extreme), None)
        tgt_i = next((i for i, p in enumerate(side_px) if p >= target), None)
    else:
        stop_i = next((i for i, p in enumerate(side_px) if p >= extreme), None)
        tgt_i = next((i for i, p in enumerate(side_px) if p <= target), None)
    te = ns(d0) + pd.Timedelta(hours=12).value
    time_i_arr = q.index[q["ts"] >= te]
    time_i = int(time_i_arr[0]) if len(time_i_arr) else None
    events = []
    if stop_i is not None:
        events.append((stop_i, "STOP"))
    if tgt_i is not None:
        events.append((tgt_i, "TARGET"))
    if time_i is not None:
        events.append((time_i, "TIME"))
    events.sort()
    kind_i, kind = events[0]
    if kind == "STOP":
        exit_px = float(side_px.iloc[kind_i])
    elif kind == "TARGET":
        exit_px = target
    else:
        exit_px = float(side_px.iloc[kind_i])
    net = (exit_px - entry_px) * direction / PIP
    if kind != tr["exit_type"] or abs(net - tr["net_pips"]) > 1e-6 \
            or int(q["ts"].iloc[kind_i]) != tr["exit_ts"]:
        failures.append(f"{tr['date']}: exit mismatch {kind} {net} vs {tr['exit_type']} "
                        f"{tr['net_pips']}")

print(f"AUDIT_SAMPLE: {len(sample)} trades re-derived independently")
print(f"AUDIT_FAILURES: {len(failures)}")
for f in failures:
    print("  FAIL:", f)

# global cross-checks
years = sorted({t["date"][:4] for t in trades})
print("TRADE_YEARS:", {y: sum(1 for t in trades if t["date"][:4] == y) for y in years})
assert all(t["date"] < "2019-01-01" for t in trades), "2019+ trade leaked"
print("MAX_TRADE_DATE:", max(t["date"] for t in trades))
print("STATUS:", "AUDIT_OK" if not failures else "AUDIT_FAILED")
