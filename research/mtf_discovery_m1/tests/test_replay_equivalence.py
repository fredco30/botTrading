#!/usr/bin/env python3
"""Equivalence test: m3lib.mtf_replay (vectorized exit scan) must produce
byte-identical trades to the audited m2lib.m2_replay (pure per-tick loop) on
the same M1-bar decision stream. Run on 2010 H1 decisions, several SL/TP/T
cells and both latency/stress settings."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import numpy as np
import m3lib as L
import m2lib
import infra_lib as I

ts, bid, ask = I.load_year(2010)
m1 = I.m1_bars(ts, bid, ask)

# deterministic pseudo-signal: every 37th completed H1 bar, alternating sides
ct = m1["close_time"]
h1 = L.bars_from_m1(m1, 60)
sig = np.zeros(len(h1["close"]), dtype=np.int8)
idx = np.arange(50, len(sig) - 500, 37)
sig[idx] = np.where(np.arange(len(idx)) % 2 == 0, 1, -1)

# embed the same decisions into an M1-level sig for m2_replay
sig_m1 = np.zeros(len(ct), dtype=np.int8)
pos = np.searchsorted(ct, h1["close_time"][idx])
sig_m1[pos] = sig[idx]
decisions = {"ts": h1["close_time"][idx], "side": sig[idx]}

fails = 0
for sl, tp, tmin, lat, slip in [
        (15, 15, 120, 5, 0.0), (40, 60, 1440, 5, 0.0),
        (30, 90, 4320, 30, 0.5), (25, 25, 600, 30, 0.5)]:
    t_loop, nf_loop = m2lib.m2_replay(ts, bid, ask, m1, sig_m1, sl, tp, tmin,
                                      latency_ns=lat * L.NS, slip_pips=slip)
    t_vec, nf_vec = L.mtf_replay(ts, bid, ask, decisions, sl, tp, tmin,
                                 latency_ns=lat * L.NS, slip_pips=slip)
    assert nf_loop == nf_vec, "no_fill mismatch"
    same = len(t_loop) == len(t_vec) and all(
        a["decision_ts"] == b["decision_ts"] and a["side"] == b["side"]
        and a["entry_ts"] == b["entry_ts"] and a["entry"] == b["entry"]
        and a["exit_ts"] == b["exit_ts"] and a["exit_px"] == b["exit_px"]
        and a["reason"] == b["reason"] and a["net_pips"] == b["net_pips"]
        for a, b in zip(t_loop, t_vec))
    print(f"SL{sl}/TP{tp}/T{tmin} lat{lat}s slip{slip}: n={len(t_loop)} "
          f"identical={same} no_fill={nf_loop}")
    fails += 0 if same else 1

# tp_levels (absolute target) path: with target=NaN no TARGET can fire;
# exits must be STOP or TIME only (target comparisons with NaN are False).
lv = np.full(len(idx), np.nan)
t_vec, _ = L.mtf_replay(ts, bid, ask, decisions, 30, np.nan, 1440,
                        tp_levels=lv)
print("nan tp_levels never TARGETs:",
      all(t["reason"] in ("STOP", "TIME") for t in t_vec))

print("EQUIVALENCE:", "PASS" if fails == 0 else f"FAIL({fails})")
sys.exit(1 if fails else 0)
