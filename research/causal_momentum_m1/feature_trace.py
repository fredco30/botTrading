#!/usr/bin/env python3
"""CAUSAL_MOMENTUM_M1 — CRITICAL FEATURE TRACE (mission 17).
20 randomly sampled SIGNALS per hypothesis, full provenance, written to
feature_trace.json. Asserts MAX_FEATURE_INPUT_TS <= DECISION_TS for every one."""
import json
import numpy as np
import cm_lib as C

NS = C.NS
PIP = C.PIP

ts, bid, ask = C.load_year(2017)
bars = C.m1_bars(ts, bid, ask)
h4_end, h4_close, h4_idx = C.h4_closes(bars["close_time"], bars["close"])
h4_ltts = bars["last_tick_ts"][h4_idx]
out = {}
ok_all = True
for which in ("H1", "H2"):
    sig = C.signals_all(bars, (h4_end, h4_close, h4_ltts), which)
    idx = np.flatnonzero(sig != 0)
    rng = np.random.default_rng(7)
    picks = rng.choice(idx, size=20, replace=False)
    rows = []
    for j in picks:
        if which == "H1":
            mom, cur_ts, ref_ts = C.mom4h_rolling(bars, int(j))
        else:
            mom, cur_ts, ref_ts = C.mom16h_h4_completed(bars, int(j), h4_end,
                                                        h4_close, h4_ltts)
        d_ts = int(bars["close_time"][j])
        row = {
            "DECISION_TS_UTC": str(np.datetime64(d_ts, "ns")),
            "CURRENT_CLOSE_TS_UTC": str(np.datetime64(cur_ts, "ns")),
            "REFERENCE_CLOSE_TS_UTC": str(np.datetime64(ref_ts, "ns")),
            "MAX_FEATURE_INPUT_TS_UTC": str(np.datetime64(max(cur_ts, ref_ts), "ns")),
            "LOOKBACK_CLOCK_HOURS": round((d_ts - ref_ts) / 3600.0 / NS, 3),
            "MOMENTUM_PIPS": round(mom, 2),
            "DIRECTION": "LONG" if sig[j] == 1 else "SHORT",
        }
        assert max(cur_ts, ref_ts) <= d_ts, "CAUSALITY VIOLATION"
        rows.append(row)
    lks = [r["LOOKBACK_CLOCK_HOURS"] for r in rows]
    print(f"{which}: 20 signal traces OK; lookback hours "
          f"min={min(lks):.2f} median={np.median(lks):.2f} max={max(lks):.2f} "
          f"(values >4.5h = weekend/session effect)")
    out[which] = rows
    ok_all &= all(r["MAX_FEATURE_INPUT_TS_UTC"] <= r["DECISION_TS_UTC"] for r in rows)
with open("feature_trace.json", "w") as f:
    json.dump(out, f, indent=1)
print("TRACE_ASSERT_MAX_INPUT_LE_DECISION:", "PASS" if ok_all else "FAIL")
