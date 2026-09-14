#!/usr/bin/env python3
"""CAUSAL_MOMENTUM_M1 — DISCOVERY on 2017 (mission 11/12).
Exactly two hypotheses, exactly the frozen parameters (10/15/15/120min).
Baseline + stress; native AND common-intersection samples for stress."""
import json
import numpy as np
import pandas as pd
import cm_lib as C

NS = C.NS
ts, bid, ask = C.load_year(2017)
print(f"2017 ticks: {len(ts):,}")
bars = C.m1_bars(ts, bid, ask)
h4_end, h4_close, h4_idx = C.h4_closes(bars["close_time"], bars["close"])
h4_ltts = bars["last_tick_ts"][h4_idx]
h4 = (h4_end, h4_close, h4_ltts)
months = pd.to_datetime(bars["close_time"], utc=True).month.to_numpy()

results = {}
for which in ("H1", "H2"):
    sig = C.signals_all(bars, h4, which)
    print(f"{which}: signal bars = {int((sig != 0).sum()):,}")
    base, nf_b = C.replay(ts, bid, ask, bars, sig,
                          latency_ns=C.LATENCY_NS, slip_pips=0.0)
    stress, nf_s = C.replay(ts, bid, ask, bars, sig,
                            latency_ns=30 * NS, slip_pips=0.50)
    bc, sc = C.common_sample(base, stress)
    mb = C.metrics(base, months, f"{which} BASELINE native")
    ms = C.metrics(stress, months, f"{which} STRESS native")
    mbc = C.metrics(bc, months, f"{which} BASELINE common")
    msc = C.metrics(sc, months, f"{which} STRESS common")
    mbc["no_fill_base"], mbc["no_fill_stress"] = nf_b, nf_s
    msc["intersection_n"] = len(bc)
    results[which] = {"baseline": mb, "stress": ms,
                      "baseline_common": mbc, "stress_common": msc}
    for m in (mb, ms, mbc, msc):
        print(json.dumps(m))
    gate, fails = C.gate_check(mb)
    results[which]["gate_pass"] = gate
    results[which]["gate_fails"] = fails
    print(f"{which} GATE: {'PASS' if gate else 'FAIL ' + ','.join(fails)}")

with open("discovery_results.json", "w") as f:
    json.dump(results, f, indent=1)
print("DISCOVERY_DONE")
