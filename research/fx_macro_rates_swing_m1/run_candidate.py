#!/usr/bin/env python3
"""FX_MACRO_RATES_SWING_M1 — candidate pre-freeze battery (discovery data
ONLY; USDJPY / 2018H2 / 2019+ untouched).

Frozen mechanism (B): 24h ZN rate impulse |z|>=2.5 while EURUSD/GBPUSD has
NOT followed (fx_move * usd_dir <= 0, in ATR units) -> trade the rates-
implied USD direction at the H4 close; stop/target 2.5xATR(H4,14); max
hold 48h. EURUSD discovery-bar model cross-checked TICK_EXACT below.
"""
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import mrlib as MR
import swing_lib as SW
import infra_lib as I
import m3lib

from run_screens import sig_rate_fx_divergence

sig_rate_fx_divergence.signal_tf = "H4"
PARAMS = {"tf": "H4", "thr": 2.5, "cap": 0.0, "stop_mult": 2.5,
          "rates_sym": "ZN"}
HOLD = 48
OUT = {}


def frozen_signal(bars, sym, params=None):
    return sig_rate_fx_divergence(bars, sym, PARAMS)


def atr_dist(bars, i, sym, mult=2.5):
    return float(SW.atr(sym, bars["H4_high"], bars["H4_low"],
                        bars["H4_close"], 14)[i] * mult)


# ------------------------------------------------ 1. discovery bar metrics
print("=== 1. bar-model pooled discovery metrics (MODELED_EXECUTION) ===")
stop_fn = lambda bars, i, sym, p: atr_dist(bars, i, sym)
trades = SW.run_pooled(sig_rate_fx_divergence, PARAMS, stop_fn, stop_fn,
                       HOLD)
stress = SW.run_pooled(sig_rate_fx_divergence, PARAMS, stop_fn, stop_fn,
                       HOLD, stress=True)
m = SW.pooled_metrics(trades, "B_z2.5_h48")
ms = SW.pooled_metrics(stress, "B_z2.5_h48_stress")
OUT["bar_model"] = m
OUT["bar_model_stress"] = ms
for sym in SW.DISCOVERY_PAIRS:
    OUT[f"bar_model_{sym}"] = SW.pooled_metrics(
        [t for t in trades if t["sym"] == sym], sym)
print(json.dumps({k: m[k] for k in ("N", "mean_pips", "median_pips", "PF",
                                    "expectancy_r", "pos_years", "remove_best",
                                    "max_dd_r", "worst_year_r",
                                    "worst_rolling12m_r")}))

# ------------------------------------------------ 2. survival diagnostic
print("=== 2. survival 500 EUR / 0.5% ===")
sv = SW.survival_veto(trades)
OUT["survival"] = sv
print(json.dumps(sv, default=str))

# ------------------------------------------------ 3. causality gates
print("=== 3. causality gates (FX T1/T2/T3 + rates T1r/T2r/T3r) ===")
# ~22 fires/year at z>=2.5 -> pool all discovery years for the >=20-trace bar
YEARS = list(range(2010, 2018))
ok_fx, fx_trace = SW.causality_gate("B_FROZEN", sig_rate_fx_divergence,
                                    PARAMS, year=YEARS, n_samples=24)
ok_rates, _ = MR.rates_gate("B_FROZEN_RATES", sig_rate_fx_divergence,
                            PARAMS, year=YEARS, n_samples=24)
OUT["gate_fx_pass"] = bool(ok_fx)
OUT["gate_rates_pass"] = bool(ok_rates)
print(f"GATES: FX={'PASS' if ok_fx else 'FAIL'} "
      f"RATES={'PASS' if ok_rates else 'FAIL'}")

# ------------------------------------------------ 4. EURUSD tick-exact
print("=== 4. EURUSD tick-exact replay 2010-2017 (TICK_EXACT) ===")


def tick_replay(years, latency_ns, slip):
    all_tr = []
    for y in years:
        ts, bid, ask = I.load_year(y)
        bars = SW.build_discovery_bars("EURUSD")
        side = sig_rate_fx_divergence(bars, "EURUSD", PARAMS)
        ct = bars["H4_close_time"]
        idx = np.flatnonzero(side != 0)
        dec = {"ts": ct[idx], "side": side[idx]}
        o5 = bars["5m_open"]
        base = np.empty(len(idx))
        for n, i in enumerate(idx):
            k = int(np.searchsorted(bars["5m_ts"], ct[i], side="left"))
            base[n] = o5[k]
        dist = np.array([atr_dist(bars, i, "EURUSD") for i in idx]) * SW.PIP["EURUSD"]
        sd = base - dec["side"] * dist
        td = base + dec["side"] * dist
        tr, _ = m3lib.mtf_replay(ts, bid, ask, dec, None, None, HOLD * 60,
                                 latency_ns=latency_ns, slip_pips=slip,
                                 sl_levels=sd, tp_levels=td)
        all_tr += tr
        print(f"  {y}: N={len(tr)}")
    return all_tr


base_tr = tick_replay(range(2010, 2018), 5 * MR.NS, 0.0)
stress_tr = tick_replay(range(2010, 2018), 30 * MR.NS, 0.5)
mt = m3lib.replay_metrics(base_tr, "TICK_EXACT_base")
mts = m3lib.replay_metrics(stress_tr, "TICK_EXACT_stress")
OUT["tick_exact_base"] = mt
OUT["tick_exact_stress"] = mts
print(json.dumps({k: mt.get(k) for k in ("N", "mean_pips", "PF",
                                         "expectancy_r")}))

json.dump(OUT, open(os.path.join(HERE, "cache", "candidate_frozen.json"),
                    "w"), indent=1, default=str)
print("WROTE cache/candidate_frozen.json")
