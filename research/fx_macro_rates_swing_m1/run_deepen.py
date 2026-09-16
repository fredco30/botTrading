#!/usr/bin/env python3
"""Deepen round: B (rate/FX divergence) plateau + pair diagnosis, plus
last cheap probes on C-steep and K. Budget-aware, no parameter rescue:
this is the §19/§25 mandatory plateau evidence for the only promoter."""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import mrlib as MR
import swing_lib as SW
from run_screens import (run, sig_rate_fx_divergence, sig_curve_regime,
                         sig_regime_machine)

sig_rate_fx_divergence.signal_tf = "H4"
sig_curve_regime.signal_tf = "D1"
sig_regime_machine.signal_tf = "H4"

RES = {}

# --- B plateau: threshold / hold / cap / maturity axes (one config each) ---
RES["b_thr2.5"] = run("B", "div_z2.5_h48", sig_rate_fx_divergence,
                      {"tf": "H4", "thr": 2.5, "cap": 0.0, "stop_mult": 2.5}, 48)
RES["b_hold24"] = run("B", "div_z2.0_h24", sig_rate_fx_divergence,
                      {"tf": "H4", "thr": 2.0, "cap": 0.0, "stop_mult": 2.5}, 24)
RES["b_hold120"] = run("B", "div_z2.0_h120", sig_rate_fx_divergence,
                       {"tf": "H4", "thr": 2.0, "cap": 0.0, "stop_mult": 2.5}, 120)
RES["b_cap-0.5"] = run("B", "div_z2.0_cap-0.5_h48", sig_rate_fx_divergence,
                       {"tf": "H4", "thr": 2.0, "cap": -0.5, "stop_mult": 2.5}, 48)
RES["b_zf"] = run("B", "div_z2.0_ZF_h48", sig_rate_fx_divergence,
                  {"tf": "H4", "thr": 2.0, "cap": 0.0, "stop_mult": 2.5,
                   "rates_sym": "ZF"}, 48)
RES["b_stop3.0"] = run("B", "div_z2.0_stop3.0_h48", sig_rate_fx_divergence,
                       {"tf": "H4", "thr": 2.0, "cap": 0.0, "stop_mult": 3.0}, 48)

# --- C-steep and K: single probe each on their most plausible axis ---
RES["c_steep_thr1.5"] = run("C", "curve_steep_usddn_thr1.5_h5d",
                            sig_curve_regime,
                            {"tf": "D1", "thr": 1.5,
                             "variant": "steep_short_usd", "stop_mult": 2.0}, 120)
RES["k_thr1.5"] = run("K", "regime_don30_z1.5_h48", sig_regime_machine,
                      {"tf": "H4", "don": 30, "thr": 1.5, "stop_mult": 2.5}, 48)

json.dump({k: {"metrics": v[1], "per_pair": {} } for k, v in RES.items()},
          open(os.path.join(HERE, "cache", "deepen.json"), "w"),
          indent=1, default=str)
print(f"\nEXPERIMENTS_USED={MR.experiments_used()} "
      f"FAMILIES_USED={MR.families_used()}")
