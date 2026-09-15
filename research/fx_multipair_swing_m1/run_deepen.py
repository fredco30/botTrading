#!/usr/bin/env python3
"""Stage 2 deepens: complete strategies (context/setup/entry/stop/exit) for
the gross-screen leads. Net-of-cost bar replay on EURUSD+GBPUSD 2010-2017,
per-pair split, stress scenario, survival test. One ledger row per config."""
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import swing_lib as S
import families_sw as F


def atr_at(sym, bars, tf, i, n=14):
    a = S.atr(sym, bars[f"{tf}_high"], bars[f"{tf}_low"], bars[f"{tf}_close"], n)
    return a[i]


def stop_atr(tf, n=14, mult=2.5):
    def fn(bars, i, sym, params):
        v = atr_at(sym, bars, tf, i, n) * mult
        return v if np.isfinite(v) else 9999.0
    return fn


def no_tp(bars, i, sym, params):
    return 10 ** 9


def run_config(fam, mech, signal_fn, params, hold_hours, stop_mult,
               stop_n=14, tp_mult=None, gate_causality=False):
    stop_fn = stop_atr(signal_fn.signal_tf, stop_n, stop_mult)
    tp_fn = no_tp if tp_mult is None else stop_atr(signal_fn.signal_tf,
                                                   stop_n, tp_mult)
    trades = S.run_pooled(signal_fn, params, stop_fn, tp_fn, hold_hours)
    stress = S.run_pooled(signal_fn, params, stop_fn, tp_fn, hold_hours,
                          stress=True)
    label = f"{fam}|{params}|hold={hold_hours}h|stop={stop_mult}xATR{stop_n}"
    m = S.agg_metrics(trades, label)
    per = {}
    for sym in S.DISCOVERY_PAIRS:
        t = [x for x in trades if x["sym"] == sym]
        per[sym] = {"N": len(t),
                    "mean_pips": round(float(np.mean([x["net_pips"] for x in t])), 2) if t else None,
                    "PF": round(S.pf_of(np.array([x["net_pips"] for x in t])), 3) if t else None,
                    "expR": round(float(np.mean([x["r"] for x in t])), 4) if t else None}
    # stress-common on shared decision keys
    b, s = S.stress_common(trades, stress)
    stress_ev = (float(np.mean([x["net_pips"] for x in s])) if s else None)
    surv = S.survival_veto(trades)
    expR = m.get("expectancy_r")
    S.log(fam, mech, "PASS" if gate_causality else "PENDING",
          f"{params}|hold={hold_hours}h|stop={stop_mult}xATR{stop_n}",
          N=m.get("N"), mean_pips=m.get("mean_pips"), PF=m.get("PF"),
          expectancy_R=expR,
          stress_pips=stress_ev,
          remove_best_pips=m.get("remove_best"),
          status="DEEPEN",
          reason=f"per-pair={per} surv_final={surv.get('final_capital') if isinstance(surv, dict) else surv}")
    print(f"=== {label}")
    S.print_metrics(m)
    print(f"  per-pair: {per}")
    print(f"  stress-common: {stress_ev} pips | survival: {surv}")
    return trades, m, surv, stress_ev


def main():
    which = sys.argv[1] if len(sys.argv) > 1 else "all"

    if which in ("all", "g11"):
        fn = F.g11_vol_regime
        # candidate A: p80 crossing, 5-day hold (screen lead)
        run_config("G11", "vol_regime_transition", fn,
                   {"win": 252, "ma_n": 20, "hi": 0.8, "lo": 0.2},
                   hold_hours=120, stop_mult=2.5)
        # candidate B: p80 crossing, 10-day hold
        run_config("G11", "vol_regime_transition", fn,
                   {"win": 252, "ma_n": 20, "hi": 0.8, "lo": 0.2},
                   hold_hours=240, stop_mult=2.5)
        # candidate C: stricter p90 crossing, 10-day hold, wider stop
        run_config("G11", "vol_regime_transition", fn,
                   {"win": 252, "ma_n": 20, "hi": 0.9, "lo": 0.2},
                   hold_hours=240, stop_mult=3.0)

    if which in ("all", "g08"):
        fn = F.g08_efficiency
        run_config("G08", "efficiency_extreme", fn,
                   {"k": 20, "eff": 0.45}, hold_hours=120, stop_mult=2.5)

    if which in ("all", "g06"):
        fn = F.g06_compression
        run_config("G06", "compression_breakout", fn,
                   {"ratio": 0.7}, hold_hours=120, stop_mult=2.0)

    if which in ("all", "g07"):
        fn = F.g07_displacement
        run_config("G07", "displacement_continuation", fn,
                   {"mult": 2.5}, hold_hours=8, stop_mult=1.5)

    if which in ("all", "g12"):
        fn = F.g12_monday_range
        run_config("G12", "monday_range_break", fn,
                   {"end_hr": 8}, hold_hours=8, stop_mult=2.0)


if __name__ == "__main__":
    main()
