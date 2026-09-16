#!/usr/bin/env python3
"""FX_MACRO_RATES_SWING_M1 — VALIDATION STAGE B: EURUSD 2018H2.

Run ONLY because Stage A passed. STAGE_B sentinel created after Stage A.
Frozen rule, frozen parameters; no tuning, no filters, no rescue.
Rates grid: window 2018-05-25..2019-01-01 (30d trailing-vol burn-in;
rates data is not a protected window). FX decisions counted only from
2018-07-01; H4 ATR/fx24 burn-in uses the first valid bars inside the
sentinel-gated window itself (first ~3.5 days produce NaN features ->
no trades), so no data outside the seal is read.
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
T_B_NS = SW.window_ns("2018-07-01", "2019-01-01")[0]

MR.set_window("2018-05-25", "2019-01-01")
SW.PIP["EURUSD"] = 1e-4
sig_rate_fx_divergence.signal_tf = "H4"

d5 = SW.load_5m("EURUSD", SW.window_ns("2018-07-01", "2019-01-01")[0],
                SW.window_ns("2018-07-01", "2019-01-01")[1] - 1,
                "STAGE_B")   # t1-1ns: swing_lib guard is t1-inclusive at 2019
bars = {"5m_" + k: d5[k] for k in ("ts", "open", "high", "low", "close")}
for name, tfm in SW.TFS.items():
    bb = SW.bars_from_5m(d5, tfm)
    for k in SW.BAR_KEYS:
        bars[f"{name}_{k}"] = bb[k]

side = sig_rate_fx_divergence(bars, "EURUSD", PARAMS)
ct = bars["H4_close_time"]
atr = SW.atr("EURUSD", bars["H4_high"], bars["H4_low"], bars["H4_close"], 14)
atr_pips = atr                      # SW.atr already returns PIPS
c = bars["H4_close"]
fx = np.zeros(len(c))
fx[6:] = np.log(c[6:] / c[:-6]) / np.maximum(atr_pips[6:], 1e-9)
valid = np.isfinite(atr_pips) & (atr_pips > 0)
idx = [i for i in range(len(ct))
       if side[i] != 0 and ct[i] >= T_B_NS and valid[i]]
dec = {"ts": np.array([ct[i] for i in idx]),
       "side": np.array([side[i] for i in idx])}
dist = np.array([float(atr_pips[i] * PARAMS["stop_mult"]) for i in idx])
stop_fn = lambda b, i, sym, p: dist[idx.index(i)]


def replay(trades_dec, stress):
    """Stage-B replay on the H2 5m frame (same fill model as swing_lib
    bar_replay, which is hardwired to discovery bars)."""
    ts5 = bars["5m_ts"]; o5 = bars["5m_open"]; h5 = bars["5m_high"]
    l5 = bars["5m_low"]; c5 = bars["5m_close"]
    pip = SW.PIP["EURUSD"]; spread = SW.SPREAD_PIPS["EURUSD"] * pip
    slip = (SW.SLIP_STRESS_PIPS * pip) if stress else 0.0
    out = []
    last_exit = -1
    for j in range(len(trades_dec["ts"])):
        s = int(trades_dec["side"][j]); d = int(trades_dec["ts"][j])
        if d < last_exit:
            continue
        k = int(np.searchsorted(ts5, d, side="left"))
        if k >= len(ts5) - 1:
            break
        sd = float(dist[j]) * pip; td = sd
        if s == 1:
            entry = float(o5[k]) + spread + slip
            stop = entry - sd; tgt = entry + td
        else:
            entry = float(o5[k]) - slip
            stop_bid = entry + sd - spread; stop = entry + sd
            tgt_bid = entry - td - spread; tgt = entry - td
        m_end = int(np.searchsorted(ts5, int(ts5[k]) + HOLD * 3600 * MR.NS,
                                    side="right")) - 1
        m0 = k + 1
        exit_px = exit_ts = None; reason = "OPEN"
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
                exit_px = (min(stop, float(os_[i_s])) - slip if s == 1
                           else max(stop, float(os_[i_s]) + spread) + slip)
                exit_ts = int(ts5[m]); reason = "STOP"
            elif i_t < 10 ** 12:
                m = m0 + i_t
                exit_px = float(tgt) - slip if s == 1 else float(tgt) + slip
                exit_ts = int(ts5[m]); reason = "TARGET"
            else:
                m = m_end
                exit_px = (float(c5[m]) - slip if s == 1
                           else float(c5[m]) + spread + slip)
                exit_ts = int(ts5[m]) + 300 * MR.NS; reason = "TIME"
        net = s * (exit_px - entry) / pip
        out.append({"sym": "EURUSD", "side": s, "decision_ts": d,
                    "entry_ts": int(ts5[k]), "exit_ts": int(exit_ts),
                    "net_pips": float(net), "r": float(net / (sd / pip)),
                    "reason": reason})
        last_exit = int(exit_ts)
    return out


trades = replay(dec, stress=False)
stress_tr = replay(dec, stress=True)
m = SW.pooled_metrics(trades, "EURUSD_2018H2")
ms = SW.pooled_metrics(stress_tr, "EURUSD_2018H2_stress")
res = {"metrics": m, "stress_mean": ms.get("mean_pips"),
       "months": SW.year_table(trades),
       "decisions_in_window": len(idx)}
print(json.dumps({k: m[k] for k in ("N", "mean_pips", "total_pips", "PF",
                                    "expectancy_r", "remove_best",
                                    "max_dd_r", "win_rate")}))
print("stress:", ms.get("mean_pips"), "| months:", m["yearly_pips"])
print("exits:", m.get("exits"))
ok = (m.get("N", 0) > 0 and m.get("mean_pips", -1) > 0
      and m.get("PF", 0) >= 1.10 and m.get("expectancy_r", -1) > 0
      and m.get("remove_best", -1) > 0 and ms.get("mean_pips", -1) >= 0)
res["stage_b_pass"] = bool(ok)
print(f"STAGE_B_VERDICT: {'PASS' if ok else 'FAIL'}")
json.dump(res, open(os.path.join(HERE, "cache", "stage_b_2018h2.json"),
                    "w"), indent=1, default=str)
