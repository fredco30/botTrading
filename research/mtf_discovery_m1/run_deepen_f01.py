#!/usr/bin/env python3
"""Deepen F01 (H4 z-band fade) — causality gate then tick-exact replay.

Strategy (structure-derived, no money management tuning):
  SHORT when H4 close z >= +2.0 (z vs SMA50/std50 of H4 closes)
  LONG  when H4 close z <= -2.0
  TP = SMA50 level frozen at decision (return to mean)
  SL = entry -/+ 2*sigma50 (same distance as TP -> 1:1 geometry)
  T-exit = 5760 min (4 trading days)
  Entry = first tick 5..35 s after the completed H4 bar close, exec side.
  One position at a time. No session restriction (H4 mechanism).
"""
import json
import numpy as np

import m3lib as L

PIP = L.PIP


def f01_decisions(bars, zthr=2.0, L1=50, sl_sigma=2.0, adx_filter=False,
                  tp_mode="midband"):
    c = bars["H4_close"]
    sma = L.sma(c, L1)
    sd = L.std(c, L1)
    z = (c - sma) / sd
    n = len(c)
    side = np.zeros(n, dtype=np.int8)
    ok = np.isfinite(z) & np.isfinite(sma) & np.isfinite(sd) & (sd > 0)
    if adx_filter:
        adx = L.adx(bars["H4_high"], bars["H4_low"], c, 14)
        ok &= np.isfinite(adx) & (adx < 20)
    side[ok & (z <= -zthr)] = 1
    side[ok & (z >= zthr)] = -1
    fire = np.flatnonzero(side != 0)
    tp = (sma[fire] if tp_mode == "midband"
          else np.full(len(fire), np.nan))          # NaN -> no TARGET exit
    sl = c[fire] - side[fire] * sl_sigma * sd[fire]  # symmetric stop level
    return {"ts": bars["H4_close_time"][fire], "side": side[fire],
            "tp": tp, "sl": sl, "idx": fire}


def replay_year(y, zthr=2.0, L1=50, sl_sigma=2.0, tmin=5760, stress=False,
                adx_filter=False, tp_mode="midband"):
    import infra_lib as I
    ts, bid, ask = I.load_year(y)
    dec = f01_decisions(L.build_year(y), zthr, L1, sl_sigma, adx_filter,
                        tp_mode)
    tr, nf = L.mtf_replay(ts, bid, ask, dec, None, None, tmin,
                          latency_ns=(30 if stress else 5) * L.NS,
                          slip_pips=0.5 if stress else 0.0,
                          tp_levels=dec["tp"], sl_levels=dec["sl"])
    return tr, nf


def full_run(label, exp_reason, status, stress=False, log_row=True, **kw):
    trades = []
    for y in L.DISCOVERY_YEARS:
        tr, nf = replay_year(y, stress=stress, **kw)
        trades += tr
    m = L.agg_metrics(trades, label)
    sv = L.survival_veto(trades)
    m["survival"] = sv
    m["veto_fail"] = L.veto_fail(sv)
    m["veto_warn"] = L.veto_warn(sv)
    sc = None
    n_stress = None
    if not stress:
        tr_s = []
        for y in L.DISCOVERY_YEARS:
            tr, _ = replay_year(y, stress=True, **kw)
            tr_s += tr
        n_stress = len(tr_s)
        cb, cs = L.stress_common(trades, tr_s)
        sc = (float(np.mean([t["net_pips"] for t in cs])) if cs else None)
    m["stress_common_ev"] = sc
    print(f"=== {label} ({'STRESS' if stress else 'BASELINE'}) ===")
    L.print_metrics(m)
    print(f"  stress_common={sc} (common of base {len(trades)} / "
          f"stress {n_stress})  survival={sv['FINAL_CAPITAL']} "
          f"dd={sv['MAX_DRAWDOWN_PERCENT']}% lowest={sv['LOWEST_EQUITY']}")
    print(f"  yearly pips={m['yearly_pips']}")
    if log_row:
        L.log("F01", "H4 z-band fade SMA50 tick replay", "PASS",
              f"{exp_reason} stress={stress}", N=m["N"],
              mean_pips=m["mean_pips"], PF=m["PF"],
              expectancy_R=m["expectancy_r"], stress_pips=sc,
              remove_best_pips=m["remove_best"], status=status,
              reason=json.dumps({"yearlyR": m["yearly_r"],
                                 "veto": sv["MAX_DRAWDOWN_PERCENT"]})[:380])
    L.save_trades(trades, f"trades_{label}.json")
    return m


if __name__ == "__main__":
    import sys
    sys.path.insert(0, L.M1DIR)
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    if which in ("gate", "all"):
        import families_m3 as F
        ok, tested, trace = L.mtf_causality_gate(
            "F01", F.f01_band_fade(False, 2.0, 50))
        L.save_trace("F01", trace)
        print(f"F01 GATE {'PASS' if ok else 'FAIL'} ({tested} traces)")
        if not ok:
            sys.exit(1)
    if which in ("base", "all"):
        full_run("f01a_base", "z2.0 L50 SL=2sig TP=midband T=5760", "DEEPEN")
    if which in ("f01b", "all"):
        full_run("f01b_adx", "z2.0 L50 ADX<20 SL=2sig TP=midband T=1440",
                 "DEEPEN", adx_filter=True, tmin=1440)
    if which in ("widestop", "all"):
        full_run("f01a_wide4sig",
                 "z2.0 L50 SL=4sig TP=none T=5760 (drift capture)",
                 "DEEPEN", sl_sigma=4.0, tp_mode="none")
    if which in ("plateau", "all"):
        full_run("f01a_z175", "PLATEAU z1.75", "PLATEAU", zthr=1.75)
        full_run("f01a_L100", "PLATEAU L=100", "PLATEAU", L1=100)
        full_run("f01a_sl3sig", "PLATEAU SL=3sig", "PLATEAU", sl_sigma=3.0)
