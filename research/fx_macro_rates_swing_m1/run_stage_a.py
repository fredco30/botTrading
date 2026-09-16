#!/usr/bin/env python3
"""FX_MACRO_RATES_SWING_M1 — VALIDATION STAGE A: USDJPY replication.

First USDJPY access (STAGE_A sentinel created AFTER the freeze commit
708cfab). Frozen rule only — no thresholds changed, no adaptation.
Pass condition (registered in the frozen spec): NOT clearly negative =
net mean pips > 0 AND PF > 1.0 AND expR > 0. Clear failure => STOP,
EURUSD 2018H2 stays sealed.
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

SW.PIP["USDJPY"] = 1e-2
SW.SPREAD_PIPS["USDJPY"] = 0.9          # conservative major estimate
sig_rate_fx_divergence.signal_tf = "H4"

bars = SW.build_discovery_bars("USDJPY")
side = sig_rate_fx_divergence(bars, "USDJPY", PARAMS)
ct = bars["H4_close_time"]
idx = np.flatnonzero(side != 0)
dec = {"ts": ct[idx], "side": side[idx]}
stop_fn = lambda b, i, sym, p: float(SW.atr(sym, b["H4_high"], b["H4_low"],
                                            b["H4_close"], 14)[i]
                                      * PARAMS["stop_mult"])
trades = SW.bar_replay("USDJPY", ct, dec,
                       np.array([stop_fn(bars, i, "USDJPY", PARAMS)
                                 for i in idx]),
                       np.array([stop_fn(bars, i, "USDJPY", PARAMS)
                                 for i in idx]), HOLD, stress=False)
stress = SW.bar_replay("USDJPY", ct, dec,
                       np.array([stop_fn(bars, i, "USDJPY", PARAMS)
                                 for i in idx]),
                       np.array([stop_fn(bars, i, "USDJPY", PARAMS)
                                 for i in idx]), HOLD, stress=True)
m = SW.pooled_metrics(trades, "USDJPY_STAGE_A")
ms = SW.pooled_metrics(stress, "USDJPY_STAGE_A_stress")
sv = SW.survival_veto(trades)
res = {"metrics": m, "stress_mean": ms.get("mean_pips"),
       "years": SW.year_table(trades), "survival": sv}
print(json.dumps({k: m[k] for k in ("N", "mean_pips", "median_pips", "PF",
                                    "expectancy_r", "pos_years",
                                    "remove_best", "max_dd_r",
                                    "long_r", "short_r")}))
print("stress:", ms.get("mean_pips"), "| yearly:", m["yearly_pips"])
print("survival:", {k: sv[k] for k in ("FINAL_CAPITAL", "MAX_DRAWDOWN_PERCENT",
                                       "LOWEST_EQUITY")})
ok = (m.get("N", 0) > 0 and m.get("mean_pips", -1) > 0
      and m.get("PF", 0) > 1.0 and m.get("expectancy_r", -1) > 0)
res["stage_a_pass"] = bool(ok)
print(f"STAGE_A_VERDICT: {'PASS' if ok else 'FAIL'}")
json.dump(res, open(os.path.join(HERE, "cache", "stage_a_usdjpy.json"),
                    "w"), indent=1, default=str)
