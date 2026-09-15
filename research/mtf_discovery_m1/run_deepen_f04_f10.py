#!/usr/bin/env python3
"""Deepen F04b (PDH/PDL fade) and F10b (prev-week H/L fade) — M15 triggers,
tick-exact replay, coarse fixed SL/TP appropriate to M15 scale, time exit
matching the screened horizon. Gates run first."""
import sys
import numpy as np

import m3lib as L
import families_m3 as F


def decisions_from_side(bars, side):
    ct = bars["M15_close_time"]
    fire = np.flatnonzero(side != 0)
    return {"ts": ct[fire], "side": side[fire]}


def replay_year(y, fn, sl_pips, tp_pips, tmin, stress=False):
    import infra_lib as I
    ts, bid, ask = I.load_year(y)
    bars = L.build_year(y)
    side = fn(bars, y)
    dec = decisions_from_side(bars, side)
    tr, nf = L.mtf_replay(ts, bid, ask, dec, sl_pips, tp_pips, tmin,
                          latency_ns=(30 if stress else 5) * L.NS,
                          slip_pips=0.5 if stress else 0.0)
    return tr, nf


def full_run(fam, label, fn, sl_pips, tp_pips, tmin, status="DEEPEN"):
    trades = []
    for y in L.DISCOVERY_YEARS:
        tr, _ = replay_year(y, fn, sl_pips, tp_pips, tmin)
        trades += tr
    m = L.agg_metrics(trades, label)
    sv = L.survival_veto(trades)
    tr_s = []
    for y in L.DISCOVERY_YEARS:
        tr, _ = replay_year(y, fn, sl_pips, tp_pips, tmin, stress=True)
        tr_s += tr
    cb, cs = L.stress_common(trades, tr_s)
    sc = float(np.mean([t["net_pips"] for t in cs])) if cs else None
    m["stress_common_ev"] = sc
    m["survival"] = sv
    print(f"=== {label} ===")
    L.print_metrics(m)
    print(f"  stress_common={sc} (common {len(cb)}) survival={sv['FINAL_CAPITAL']} "
          f"dd={sv['MAX_DRAWDOWN_PERCENT']}%")
    L.log(fam, fn.desc + " tick replay", "PASS",
          f"SL{sl_pips}/TP{tp_pips}/T{tmin}", N=m["N"],
          mean_pips=m["mean_pips"], PF=m["PF"],
          expectancy_R=m["expectancy_r"], stress_pips=sc,
          remove_best_pips=m["remove_best"], status=status,
          reason=f"yearlyR={m['yearly_r']} ddR={m['max_dd_r']}"[:380])
    L.save_trades(trades, f"trades_{label}.json")
    return m


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    if which in ("gate", "all"):
        for fam, fn in (("F04", F.f04_prev_day("fade")),
                        ("F10", F.f10_prev_week("fade"))):
            ok, tested, trace = L.mtf_causality_gate(fam, fn)
            L.save_trace(fam, trace)
            if not ok:
                print(f"{fam} GATE FAIL — no replay")
                sys.exit(1)
    if which in ("f04", "all"):
        full_run("F04", "f04b_pdh_fade", F.f04_prev_day("fade"),
                 sl_pips=20, tp_pips=30, tmin=240)
    if which in ("f10", "all"):
        full_run("F10", "f10b_pw_fade", F.f10_prev_week("fade"),
                 sl_pips=25, tp_pips=40, tmin=480)
