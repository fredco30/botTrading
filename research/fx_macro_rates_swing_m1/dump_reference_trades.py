#!/usr/bin/env python3
"""Reference trade-list extraction for the final independent audit.

Runs the EXISTING frozen implementations (no changes) and dumps per-trade
records for the three audit sets. The audit itself (run_final_audit.py)
imports nothing from the research code.

Set C records entry/exit prices in addition to run_stage_b.py's fields —
recording-only change, identical arithmetic (frozen Stage-B shim).
"""
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import mrlib as MR
import swing_lib as SW
from run_screens import sig_rate_fx_divergence

PARAMS = {"tf": "H4", "thr": 2.5, "cap": 0.0, "stop_mult": 2.5,
          "rates_sym": "ZN"}
HOLD = 48
sig_rate_fx_divergence.signal_tf = "H4"
KEYS = ("decision_ts", "side", "entry_ts", "entry", "exit_ts", "exit_px",
        "reason", "net_pips", "r", "risk_pips")

out = {}

# ---- Set A: EURUSD discovery (engine path) ----
stop_fn = lambda b, i, sym, p: float(SW.atr(sym, b["H4_high"], b["H4_low"],
                                            b["H4_close"], 14)[i]
                                      * PARAMS["stop_mult"])
bars = SW.build_discovery_bars("EURUSD")
side = sig_rate_fx_divergence(bars, "EURUSD", PARAMS)
ct = bars["H4_close_time"]
idx = np.flatnonzero(side != 0)
dec = {"ts": ct[idx], "side": side[idx]}
d = np.array([stop_fn(bars, i, "EURUSD", PARAMS) for i in idx])
tr = SW.bar_replay("EURUSD", ct, dec, d, d, HOLD, stress=False)
out["A_eurusd_discovery"] = [{k: t[k] for k in KEYS} for t in tr]

# ---- Set B: USDJPY Stage A (engine path, as run_stage_a.py) ----
SW.PIP["USDJPY"] = 1e-2
SW.SPREAD_PIPS["USDJPY"] = 0.9
bars = SW.build_discovery_bars("USDJPY")
side = sig_rate_fx_divergence(bars, "USDJPY", PARAMS)
ct = bars["H4_close_time"]
idx = np.flatnonzero(side != 0)
dec = {"ts": ct[idx], "side": side[idx]}
d = np.array([stop_fn(bars, i, "USDJPY", PARAMS) for i in idx])
tr = SW.bar_replay("USDJPY", ct, dec, d, d, HOLD, stress=False)
out["B_usdjpy_stage_a"] = [{k: t[k] for k in KEYS} for t in tr]

# ---- Set C: EURUSD 2018H2 (Stage-B shim, run_stage_b.py logic verbatim
#      plus entry/exit_px recorded) ----
MR.set_window("2018-05-25", "2019-01-01")
d5 = SW.load_5m("EURUSD", SW.window_ns("2018-07-01", "2019-01-01")[0],
                SW.window_ns("2018-07-01", "2019-01-01")[1] - 1, "STAGE_B")
bars = {"5m_" + k: d5[k] for k in ("ts", "open", "high", "low", "close")}
for name, tfm in SW.TFS.items():
    bb = SW.bars_from_5m(d5, tfm)
    for k in SW.BAR_KEYS:
        bars[f"{name}_{k}"] = bb[k]
side = sig_rate_fx_divergence(bars, "EURUSD", PARAMS)
ct = bars["H4_close_time"]
atr_pips = SW.atr("EURUSD", bars["H4_high"], bars["H4_low"],
                  bars["H4_close"], 14)            # already pips
c = bars["H4_close"]
fx = np.zeros(len(c))
fx[6:] = np.log(c[6:] / c[:-6]) / np.maximum(atr_pips[6:], 1e-9)
valid = np.isfinite(atr_pips) & (atr_pips > 0)
T_B = SW.window_ns("2018-07-01", "2019-01-01")[0]
idx = [i for i in range(len(ct))
       if side[i] != 0 and ct[i] >= T_B and valid[i]]
dist = np.array([float(atr_pips[i] * PARAMS["stop_mult"]) for i in idx])
ts5 = bars["5m_ts"]; o5 = bars["5m_open"]; h5 = bars["5m_high"]
l5 = bars["5m_low"]; c5 = bars["5m_close"]
pip = SW.PIP["EURUSD"]; spread = SW.SPREAD_PIPS["EURUSD"] * pip
tr_c = []
last_exit = -1
for j in range(len(idx)):
    s = int(side[idx[j]]); dt = int(ct[idx[j]])
    if dt < last_exit:
        continue
    k = int(np.searchsorted(ts5, dt, side="left"))
    if k >= len(ts5) - 1:
        break
    sd = float(dist[j]) * pip; td = sd
    if s == 1:
        entry = float(o5[k]) + spread
        stop = entry - sd; tgt = entry + td
    else:
        entry = float(o5[k])
        stop_bid = entry + sd - spread; stop = entry + sd
        tgt_bid = entry - td - spread; tgt = entry - td
    m_end = int(np.searchsorted(ts5, int(ts5[k]) + HOLD * 3600 * MR.NS,
                                side="right")) - 1
    m0 = k + 1
    exit_px = None; exit_ts = None; reason = "OPEN"
    if m_end >= m0:
        hs = h5[m0:m_end + 1]; ls = l5[m0:m_end + 1]
        os_ = o5[m0:m_end + 1]
        i_s = np.flatnonzero(ls <= stop) if s == 1 \
            else np.flatnonzero(hs >= stop_bid)
        i_t = np.flatnonzero(hs >= tgt) if s == 1 \
            else np.flatnonzero(ls <= tgt_bid)
        i_s = int(i_s[0]) if len(i_s) else 10 ** 12
        i_t = int(i_t[0]) if len(i_t) else 10 ** 12
        if i_s <= i_t and i_s < 10 ** 12:
            m = m0 + i_s
            exit_px = (min(stop, float(os_[i_s])) if s == 1
                       else max(stop, float(os_[i_s]) + spread))
            exit_ts = int(ts5[m]); reason = "STOP"
        elif i_t < 10 ** 12:
            m = m0 + i_t
            exit_px = float(tgt)
            exit_ts = int(ts5[m]); reason = "TARGET"
        else:
            m = m_end
            exit_px = float(c5[m]) if s == 1 else float(c5[m]) + spread
            exit_ts = int(ts5[m]) + 300 * MR.NS; reason = "TIME"
    net = s * (exit_px - entry) / pip
    tr_c.append({"decision_ts": dt, "side": s, "entry_ts": int(ts5[k]),
                 "entry": float(entry), "exit_ts": int(exit_ts),
                 "exit_px": float(exit_px), "reason": reason,
                 "net_pips": float(net), "r": float(net / (sd / pip)),
                 "risk_pips": float(sd / pip)})
    last_exit = int(exit_ts)
out["C_eurusd_2018h2"] = tr_c

for k, v in out.items():
    print(k, "N =", len(v))
json.dump(out, open(os.path.join(HERE, "cache",
                                 "reference_trades_final.json"), "w"),
          indent=1)
